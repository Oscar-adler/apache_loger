import fnmatch
import os
import re
import threading
from datetime import datetime

from .models import db, LogFile, LogEntry, ImportTask

# Combined:   %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i"
COMBINED_RE = re.compile(
    r'^(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<url>\S+)(?: (?P<protocol>[^"]*))?" '
    r'(?P<status>\d{3}) (?P<size>\S+)'
    r'(?: "(?P<referrer>[^"]*)" "(?P<agent>[^"]*)")?\s*$'
)

# Common: %h %l %u %t "%r" %>s %b
COMMON_RE = re.compile(
    r'^(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<url>\S+)(?: (?P<protocol>[^"]*))?" '
    r'(?P<status>\d{3}) (?P<size>\S+)\s*$'
)

REGEX_BY_FORMAT = {"combined": COMBINED_RE, "common": COMMON_RE}


def parse_line(line: str, regex):
    """Возвращает dict или None, если строка не соответствует формату."""
    m = regex.match(line)
    if not m:
        return None
    gd = m.groupdict()
    try:
        ts = datetime.strptime(gd["time"], "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    size_raw = gd.get("size") or "-"
    try:
        size = int(size_raw) if size_raw != "-" else 0
    except ValueError:
        size = 0
    try:
        status = int(gd["status"])
    except ValueError:
        return None
    return {
        "ip": gd["ip"],
        "timestamp": ts,
        "method": gd.get("method"),
        "url": gd.get("url"),
        "protocol": gd.get("protocol"),
        "status_code": status,
        "size": size,
        "referrer": gd.get("referrer"),
        "user_agent": gd.get("agent"),
    }


def discover_files(logs_cfg):
    """Возвращает список путей, соответствующих маске в директории логов."""
    directory = logs_cfg["directory"]
    mask = logs_cfg.get("mask", "*.log")
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Log directory not found: {directory}")
    files = []
    for name in sorted(os.listdir(directory)):
        full = os.path.join(directory, name)
        if os.path.isfile(full) and fnmatch.fnmatch(name, mask):
            files.append(full)
    return files


def _safe_relpath(path, root):
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def run_import(cfg, triggered_by="user", task_id=None):
    """
    Основной импорт. Может работать синхронно (cron) и асинхронно (в потоке).
    Если передан task_id — берём существующий ImportTask (для веб-триггера),
    иначе создаём новый.
    """
    app_ctx_needed = False
    task = None
    if task_id is not None:
        task = db.session.get(ImportTask, task_id)
        if not task:
            raise ValueError(f"ImportTask {task_id} not found")
    else:
        task = ImportTask(triggered_by=triggered_by, status="running")
        db.session.add(task)
        db.session.commit()

    try:
        regex = REGEX_BY_FORMAT[cfg.logs.get("format", "combined")]
        encoding = cfg.logs.get("encoding", "utf-8")
        batch_size = cfg.import_cfg.get("batch_size", 1000)

        paths = discover_files(cfg.logs)

        # Регистрируем новые файлы в БД
        records = []
        for p in paths:
            rel = _safe_relpath(p, cfg.logs["directory"])
            lf = LogFile.query.filter_by(filename=rel).first()
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            if not lf:
                lf = LogFile(filename=rel, path=p, file_size=size, status="pending")
                db.session.add(lf)
                records.append(lf)
        db.session.commit()

        # Обновляем размеры (файлы могли вырасти)
        log_files = []
        for p in paths:
            rel = _safe_relpath(p, cfg.logs["directory"])
            lf = LogFile.query.filter_by(filename=rel).first()
            if not lf:
                continue
            try:
                lf.file_size = os.path.getsize(p)
            except OSError:
                pass
            log_files.append(lf)
        db.session.commit()

        # Считаем total_bytes (то, что предстоит прочитать с текущих offset'ов)
        total_bytes = 0
        for lf in log_files:
            total_bytes += max(0, (lf.file_size or 0) - (lf.last_offset or 0))
        task.total_files = len(log_files)
        task.total_bytes = total_bytes
        db.session.commit()

        for lf in log_files:
            if (lf.last_offset or 0) >= (lf.file_size or 0):
                # нечего читать
                task.processed_files += 1
                task.processed_bytes += 0
                db.session.commit()
                continue

            task.current_file = lf.filename
            lf.status = "processing"
            db.session.commit()

            try:
                _parse_one_file(lf, task, regex, encoding, batch_size)
                lf.status = "done"
                lf.imported_at = datetime.utcnow()
            except Exception as e:
                lf.status = "failed"
                lf.error_message = str(e)
                task.errors += 1
                db.session.commit()

            task.processed_files += 1
            db.session.commit()

        task.status = "done"
        task.finished_at = datetime.utcnow()
        task.current_file = None
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        task.status = "failed"
        task.error_message = str(e)
        task.finished_at = datetime.utcnow()
        db.session.commit()
        raise


def _parse_one_file(lf, task, regex, encoding, batch_size):
    """
    Инкрементальное чтение с lf.last_offset. Пишет батчами.
    """
    with open(lf.path, "rb") as f:
        f.seek(lf.last_offset or 0)
        batch = []
        while True:
            raw = f.readline()
            if not raw:
                break
            line = raw.decode(encoding, errors="replace").rstrip("\n").rstrip("\r")
            if not line.strip():
                lf.last_offset = f.tell()
                continue
            parsed = parse_line(line, regex)
            if parsed is None:
                task.errors += 1
                lf.last_offset = f.tell()
                continue
            batch.append(LogEntry(file_id=lf.id, **parsed))
            lf.last_offset = f.tell()
            task.processed_bytes += len(raw)

            if len(batch) >= batch_size:
                db.session.bulk_save_objects(batch)
                lf.entries_count = (lf.entries_count or 0) + len(batch)
                task.entries_inserted += len(batch)
                batch = []
                db.session.commit()

        if batch:
            db.session.bulk_save_objects(batch)
            lf.entries_count = (lf.entries_count or 0) + len(batch)
            task.entries_inserted += len(batch)
        db.session.commit()


def run_import_in_thread(app, cfg, task_id):
    """Запуск в отдельном потоке с Flask app context."""
    def _worker():
        with app.app_context():
            try:
                run_import(cfg, triggered_by="user", task_id=task_id)
            except Exception:
                pass
    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    return th
