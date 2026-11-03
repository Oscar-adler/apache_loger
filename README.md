# LogAgg — агрегатор логов Apache

## Возможности
- Авторизация (пользователи в PostgreSQL)
- Парсинг логов Apache (Common / Combined), инкрементально (offset per file)
- Просмотр записей: фильтр по датам, по IP, по URL, по ключевому слову
- Группировка по IP и по дате
- JSON API
- CLI (`flask view`, `flask parse`)
- Веб-интерфейс (Bootstrap + Fetch)
- Прогресс импорта с размером и процентом
- Список импортированных файлов и списки URL
- Принудительный и плановый импорт (cron / APScheduler)

## Установка (WSL Ubuntu)

### 1. Пакеты
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip build-essential libpq-dev \
                    apache2 postgresql postgresql-contrib cron curl
sudo /etc/init.d/apache2 start
sudo service postgresql start
sudo service cron start
```

### 2. Генерация тестовых логов
```bash
for i in $(seq 1 200); do curl -s -A "test-UA" http://localhost/ >/dev/null; done
sudo chmod -R o+r /var/log/apache2 && sudo chmod o+x /var/log/apache2
```

### 3. PostgreSQL
```bash
sudo -u postgres psql <<'SQL'
CREATE USER logagg WITH PASSWORD 'logagg_pass';
CREATE DATABASE logagg OWNER logagg;
GRANT ALL PRIVILEGES ON DATABASE logagg TO logagg;
SQL
```

### 4. Проект
```bash
git clone <repo> logagg && cd logagg
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# при необходимости отредактируй config.yaml
```

### 5. Инициализация
```bash
export FLASK_APP=run.py
flask init-db
flask create-user --username admin
flask parse
```

### 6. Запуск
```bash
python run.py
# http://localhost:5000
```

## CLI
```bash
flask view [--from ISO] [--to ISO] [--ip IP] [--keyword KW] [--limit N]
flask view --group-by ip     # (используй API, либо допиши ключ при необходимости)
flask parse [--force]        # принудительный парсинг; --force сбросит offsets
flask stats
```

## API (все требуют cookie-сессии)
- `GET /api/logs?from=ISO&to=ISO&ip=&keyword=&url=&file_id=&group_by=ip|date&page=1&limit=100`
- `GET /api/urls?limit=100`
- `GET /api/files`
- `GET /api/files/<id>/entries?limit=100`
- `POST /api/import` → `{task_id}`
- `GET /api/import/status/<task_id>` → прогресс
- `GET /api/stats`

## Cron
```
*/5 * * * * /path/to/logagg/scripts/logagg_cron.sh
```
Встроенный планировщик отключается в `config.yaml: scheduler.enabled: false`.

## Конфигурация
См. `config.yaml`. Директория логов, маска, формат (common/combined), БД, host/port,
secret_key, интервал планировщика, batch_size импорта.
