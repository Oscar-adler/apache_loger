import os
from logagg import create_app

app = create_app()

if __name__ == "__main__":
    cfg = app.config["LOGAGG_CFG"]
    app.run(
        host=cfg.server.get("host", "0.0.0.0"),
        port=int(cfg.server.get("port", 5000)),
        debug=bool(cfg.server.get("debug", False)),
        use_reloader=False,   # важно: reloader дублирует scheduler
    )
