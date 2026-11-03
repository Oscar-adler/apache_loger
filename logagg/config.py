import os
import yaml
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path=None):
    path = Path(path or os.environ.get("LOGAGG_CONFIG", _DEFAULT_PATH))
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Валидация обязательных ключей
    required = ["database", "logs", "server"]
    for r in required:
        if r not in cfg:
            raise ValueError(f"Missing section '{r}' in config")
    return cfg


class Config:
    """Класс-обёртка для доступа по атрибутам + сборки URL БД."""
    def __init__(self, raw):
        self.raw = raw
        self.db = raw["database"]
        self.logs = raw["logs"]
        self.server = raw["server"]
        self.scheduler = raw.get("scheduler", {"enabled": False, "interval_minutes": 5})
        self.import_cfg = raw.get("import", {"batch_size": 1000, "max_entries_per_file": 1000000})

    @property
    def database_url(self):
        d = self.db
        return f"postgresql+psycopg2://{d['user']}:{d['password']}@{d['host']}:{d['port']}/{d['name']}"
