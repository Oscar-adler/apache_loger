from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from sqlalchemy import func, and_
from .models import db, LogEntry, LogFile, ImportTask
from .parser import run_import_in_thread

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_dt(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"Invalid date: {s}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_filters():
    """
    Возвращает (conditions, error). conditions — список SQLAlchemy-выражений,
    который можно применить к любому Query через .filter(*conditions).
    """
    conditions = []

    try:
        from_dt = _parse_dt(request.args.get("from"))
        to_dt = _parse_dt(request.args.get("to"))
    except ValueError as e:
        return None, str(e)

    if from_dt:
        conditions.append(LogEntry.timestamp >= from_dt)
    if to_dt:
        conditions.append(LogEntry.timestamp <= to_dt)

    ip = request.args.get("ip")
    if ip:
        conditions.append(LogEntry.ip == ip)

    file_id = request.args.get("file_id")
    if file_id:
        try:
            conditions.append(LogEntry.file_id == int(file_id))
        except ValueError:
            return None, "Invalid file_id"

    url_filter = request.args.get("url")
    if url_filter:
        conditions.append(LogEntry.url == url_filter)

    keyword = request.args.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            db.or_(
                LogEntry.url.ilike(like),
                LogEntry.user_agent.ilike(like),
                LogEntry.referrer.ilike(like),
                LogEntry.ip.ilike(like),
            )
        )

    return conditions, None


@api_bp.get("/logs")
@login_required
def get_logs():
    conditions, err = _build_filters()
    if err:
        return jsonify({"error": err}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(1000, max(1, int(request.args.get("limit", 100))))
    except ValueError:
        return jsonify({"error": "Invalid page/limit"}), 400

    group_by = request.args.get("group_by")  # ip | date | None

    if group_by == "ip":
        q = (
            db.session.query(LogEntry.ip, func.count(LogEntry.id).label("cnt"))
            .filter(*conditions)
            .group_by(LogEntry.ip)
            .order_by(func.count(LogEntry.id).desc())
            .limit(limit)
        )
        rows = q.all()
        return jsonify({"group_by": "ip",
                        "items": [{"ip": r[0], "count": r[1]} for r in rows]})

    if group_by == "date":
        day = func.date_trunc("day", LogEntry.timestamp).label("d")
        q = (
            db.session.query(day, func.count(LogEntry.id).label("cnt"))
            .filter(*conditions)
            .group_by(day)
            .order_by(day)
            .limit(limit)
        )
        rows = q.all()
        return jsonify({"group_by": "date",
                        "items": [{"date": r[0].isoformat() if r[0] else None,
                                   "count": r[1]} for r in rows]})

    total = db.session.query(func.count(LogEntry.id)).filter(*conditions).scalar() or 0
    items = (
        LogEntry.query
        .filter(*conditions)
        .order_by(LogEntry.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return jsonify({
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": e.id,
                "file_id": e.file_id,
                "ip": e.ip,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "method": e.method,
                "url": e.url,
                "protocol": e.protocol,
                "status_code": e.status_code,
                "size": e.size,
                "referrer": e.referrer,
                "user_agent": e.user_agent,
            } for e in items
        ],
    })


# ----------- остальное без изменений -----------

@api_bp.get("/urls")
@login_required
def get_urls():
    try:
        limit = min(500, max(1, int(request.args.get("limit", 100))))
    except ValueError:
        return jsonify({"error": "Invalid limit"}), 400

    q = (
        db.session.query(LogEntry.url, func.count(LogEntry.id).label("cnt"))
        .group_by(LogEntry.url)
        .order_by(func.count(LogEntry.id).desc())
        .limit(limit)
    )
    keyword = request.args.get("keyword")
    if keyword:
        q = q.filter(LogEntry.url.ilike(f"%{keyword}%"))
    rows = q.all()
    return jsonify({"items": [{"url": r[0], "count": r[1]} for r in rows]})


@api_bp.get("/files")
@login_required
def get_files():
    files = LogFile.query.order_by(LogFile.updated_at.desc()).all()
    return jsonify({
        "items": [
            {
                "id": f.id,
                "filename": f.filename,
                "file_size": f.file_size,
                "last_offset": f.last_offset,
                "entries_count": f.entries_count,
                "status": f.status,
                "error_message": f.error_message,
                "imported_at": f.imported_at.isoformat() if f.imported_at else None,
            } for f in files
        ]
    })


@api_bp.get("/files/<int:file_id>/entries")
@login_required
def get_file_entries(file_id):
    f = db.session.get(LogFile, file_id)
    if not f:
        return jsonify({"error": "file not found"}), 404
    try:
        limit = min(500, max(1, int(request.args.get("limit", 100))))
    except ValueError:
        return jsonify({"error": "Invalid limit"}), 400
    items = (
        LogEntry.query.filter_by(file_id=file_id)
        .order_by(LogEntry.timestamp.desc())
        .limit(limit)
        .all()
    )
    return jsonify({
        "file": {"id": f.id, "filename": f.filename},
        "items": [
            {"id": e.id, "timestamp": e.timestamp.isoformat(), "ip": e.ip,
             "method": e.method, "url": e.url, "status_code": e.status_code,
             "size": e.size}
            for e in items
        ],
    })


@api_bp.post("/import")
@login_required
def trigger_import():
    try:
        task = ImportTask(status="running", triggered_by="user")
        db.session.add(task)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB error: {e}"}), 500

    cfg = current_app.config["LOGAGG_CFG"]
    app = current_app._get_current_object()
    run_import_in_thread(app, cfg, task.id)
    return jsonify({"task_id": task.id})


@api_bp.get("/import/status/<int:task_id>")
@login_required
def import_status(task_id):
    t = db.session.get(ImportTask, task_id)
    if not t:
        return jsonify({"error": "task not found"}), 404
    return jsonify(t.to_dict())


@api_bp.get("/stats")
@login_required
def stats():
    total_entries = db.session.query(func.count(LogEntry.id)).scalar() or 0
    total_files = db.session.query(func.count(LogFile.id)).scalar() or 0
    unique_ips = db.session.query(func.count(func.distinct(LogEntry.ip))).scalar() or 0
    unique_urls = db.session.query(func.count(func.distinct(LogEntry.url))).scalar() or 0
    return jsonify({
        "total_entries": total_entries,
        "total_files": total_files,
        "unique_ips": unique_ips,
        "unique_urls": unique_urls,
    })
