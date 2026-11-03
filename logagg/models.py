from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class LogFile(db.Model):
    __tablename__ = "log_files"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(512), unique=True, nullable=False, index=True)
    path = db.Column(db.String(1024), nullable=False)
    file_size = db.Column(db.BigInteger, default=0)          # текущий размер
    last_offset = db.Column(db.BigInteger, default=0)        # байтов прочитано
    entries_count = db.Column(db.BigInteger, default=0)
    status = db.Column(db.String(32), default="pending")     # pending|processing|done|failed
    error_message = db.Column(db.Text)
    imported_at = db.Column(db.DateTime(timezone=True))
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class LogEntry(db.Model):
    __tablename__ = "log_entries"
    id = db.Column(db.BigInteger, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey("log_files.id", ondelete="CASCADE"), index=True)
    ip = db.Column(db.String(64), index=True)
    timestamp = db.Column(db.DateTime(timezone=True), index=True)
    method = db.Column(db.String(16))
    url = db.Column(db.String(2048), index=True)
    protocol = db.Column(db.String(16))
    status_code = db.Column(db.Integer, index=True)
    size = db.Column(db.BigInteger)
    referrer = db.Column(db.Text)
    user_agent = db.Column(db.Text)


class ImportTask(db.Model):
    __tablename__ = "import_tasks"
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(16), default="running")      # running|done|failed
    triggered_by = db.Column(db.String(16), default="user")   # user|cron
    total_files = db.Column(db.Integer, default=0)
    processed_files = db.Column(db.Integer, default=0)
    total_bytes = db.Column(db.BigInteger, default=0)
    processed_bytes = db.Column(db.BigInteger, default=0)
    entries_inserted = db.Column(db.BigInteger, default=0)
    errors = db.Column(db.BigInteger, default=0)
    current_file = db.Column(db.String(1024))
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    finished_at = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        pct = 0.0
        if self.total_bytes:
            pct = round(self.processed_bytes / self.total_bytes * 100, 2)
        return {
            "id": self.id,
            "status": self.status,
            "triggered_by": self.triggered_by,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "total_bytes": self.total_bytes,
            "processed_bytes": self.processed_bytes,
            "percent": pct,
            "entries_inserted": self.entries_inserted,
            "errors": self.errors,
            "current_file": self.current_file,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
