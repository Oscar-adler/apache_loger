import getpass
import sys
from datetime import datetime, timezone
from dateutil import parser as dtparser

import click
from flask.cli import with_appcontext

from .models import db, User, LogEntry, LogFile
from .parser import run_import


def register_cli(app):

    @app.cli.command("init-db")
    @with_appcontext
    def init_db_cmd():
        """Создать таблицы."""
        db.create_all()
        click.echo("OK: tables created.")

    @app.cli.command("create-user")
    @click.option("--username", prompt=True)
    @click.password_option()
    @with_appcontext
    def create_user_cmd(username, password):
        """Создать пользователя."""
        if User.query.filter_by(username=username).first():
            raise click.ClickException(f"User '{username}' already exists")
        u = User(username=username)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"User '{username}' created.")

    @app.cli.command("parse")
    @click.option("--force", is_flag=True, help="Парсить с нуля (сбросить offsets)")
    @with_appcontext
    def parse_cmd(force):
        """Принудительный парсинг логов (для cron)."""
        from flask import current_app
        cfg = current_app.config["LOGAGG_CFG"]
        try:
            if force:
                for lf in LogFile.query.all():
                    lf.last_offset = 0
                    lf.entries_count = 0
                db.session.commit()
            run_import(cfg, triggered_by="cron")
            click.echo("Import finished OK")
        except Exception as e:
            raise click.ClickException(f"Import failed: {e}")

    @app.cli.command("view")
    @click.option("--from", "from_dt", default=None, help="ISO date from")
    @click.option("--to", "to_dt", default=None, help="ISO date to")
    @click.option("--ip", default=None)
    @click.option("--keyword", default=None)
    @click.option("--limit", default=50, type=int)
    @with_appcontext
    def view_cmd(from_dt, to_dt, ip, keyword, limit):
        """Консольный просмотр записей с фильтрами."""
        q = LogEntry.query
        try:
            if from_dt:
                q = q.filter(LogEntry.timestamp >= dtparser.parse(from_dt))
            if to_dt:
                q = q.filter(LogEntry.timestamp <= dtparser.parse(to_dt))
        except (ValueError, dtparser.ParserError) as e:
            raise click.ClickException(f"Date parse error: {e}")
        if ip:
            q = q.filter(LogEntry.ip == ip)
        if keyword:
            like = f"%{keyword}%"
            q = q.filter(
                db.or_(LogEntry.url.ilike(like), LogEntry.user_agent.ilike(like),
                       LogEntry.ip.ilike(like), LogEntry.referrer.ilike(like))
            )
        items = q.order_by(LogEntry.timestamp.desc()).limit(limit).all()
        if not items:
            click.echo("No records.")
            return
        click.echo(f"{'timestamp':25} {'ip':15} {'method':6} {'status':6} {'size':>8}  url")
        for e in items:
            ts = e.timestamp.isoformat() if e.timestamp else "-"
            click.echo(f"{ts:25} {(e.ip or '-'):15} {(e.method or '-'):6} "
                       f"{e.status_code!s:6} {(e.size or 0):>8}  {e.url}")
        click.echo(f"\nTotal shown: {len(items)}")

    @app.cli.command("stats")
    @with_appcontext
    def stats_cmd():
        """Статистика."""
        click.echo(f"Files: {LogFile.query.count()}")
        click.echo(f"Entries: {LogEntry.query.count()}")
        for f in LogFile.query.all():
            click.echo(f"  {f.filename}: {f.entries_count} entries, status={f.status}")
