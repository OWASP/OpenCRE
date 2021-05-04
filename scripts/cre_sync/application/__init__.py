from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from application.config import config

sqla = SQLAlchemy()


def create_app(mode: str='production',conf=None):
    app = Flask(__name__)
    if not conf:
        app.config.from_object(config[mode])
    else:
        app.config.from_object(conf)
    config[mode].init_app(app)
    sqla.init_app(app=app)

    from application.web.web_main import app as app_blueprint
    app.register_blueprint(app_blueprint)

    return app

