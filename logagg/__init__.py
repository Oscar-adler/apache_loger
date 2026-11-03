import logging
from flask import Flask
from .config import load_config, Config
from .models import db
from .auth import login_manager, auth_bp
from .api import api_bp
from .views import views_bp
from .cli import register_cli


def create_app(config_path=None, start_sched=True):
    app = Flask(__name__)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    raw = load_config(config_path)
    cfg = Config(raw)

    app.config["SECRET_KEY"] = cfg.server["secret_key"]
    app.config["SQLALCHEMY_DATABASE_URI"] = cfg.database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["LOGAGG_CFG"] = cfg

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)
    register_cli(app)

    if start_sched:
        from .scheduler import start_scheduler
        start_scheduler(app, cfg)

    return app
