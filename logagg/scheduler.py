from apscheduler.schedulers.background import BackgroundScheduler
from .models import db
from .parser import run_import


def start_scheduler(app, cfg):
    if not cfg.scheduler.get("enabled"):
        return None
    sched = BackgroundScheduler(daemon=True)

    def job():
        with app.app_context():
            try:
                run_import(cfg, triggered_by="cron")
            except Exception as e:
                app.logger.exception("Scheduler import failed: %s", e)

    interval = int(cfg.scheduler.get("interval_minutes", 5))
    sched.add_job(job, "interval", minutes=interval, id="import-job", replace_existing=True)
    sched.start()
    return sched
