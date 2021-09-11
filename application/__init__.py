# type:ignore
from typing import Any

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_compress import Compress
from application.config import config

sqla = SQLAlchemy()
compress = Compress()
cache = Cache()


def create_app(mode: str = "production", conf: any = None) -> Any:
    app = Flask(__name__)
    if not conf:
        app.config.from_object(config[mode])
    else:
        app.config.from_object(conf)

    # config[mode].init_app(app)
    sqla.init_app(app=app)
    from application.web.web_main import app as app_blueprint

    app.register_blueprint(app_blueprint)

    CORS(app)
    app.config["CORS_HEADERS"] = "Content-Type"

    compress.init_app(app)
    cache.init_app(app)
    return app
