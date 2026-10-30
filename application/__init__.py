# type:ignore
from cre_logging import get_logger

logger = get_logger(__name__)

import string
from typing import Any
from sqlalchemy import MetaData
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_compress import Compress
from application.config import CMDConfig, config
import os
import random


convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)
sqla = SQLAlchemy(metadata=metadata)
compress = Compress()
cache = Cache()


def create_app(mode: str = "production", conf: any = None) -> Any:
    from application.utils.error_reporting import init_error_reporting

    init_error_reporting("web")  # no-op unless SENTRY_DSN is set
    app = Flask(__name__)
    if not conf:
        app.config.from_object(config[mode])
    else:
        app.config.from_object(conf)
    # CLI passes an explicit URI via ``CMDConfig`` (``cre_main.db_connect``). A
    # leftover ``SQLALCHEMY_DATABASE_URI`` in the environment (e.g. sqlite from a
    # prior shell export) must not override it — that produced sqlite errors
    # against a Heroku ``DATABASE_URL`` session.
    if os.environ.get("SQLALCHEMY_DATABASE_URI") and not isinstance(conf, CMDConfig):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
            "SQLALCHEMY_DATABASE_URI"
        )
    # A stable key, or session cookies stop verifying whenever a worker restarts
    # and every login (state kept in the session) bounces back to /auth/login.
    app.secret_key = os.environ.get("SECRET_KEY") or os.environ.get(
        "GOOGLE_CLIENT_SECRET"
    )
    # Only "1" disables login, as everywhere else; NO_LOGIN=0 is truthy as a string.
    if os.environ.get("NO_LOGIN") == "1":
        letters = string.ascii_lowercase
        app.secret_key = "".join(random.choice(letters) for i in range(20))

    # JWT API-token signing secret: env, or mint+persist once on install/boot.
    # Tests get a stable in-process default so create_app does not touch /code.
    try:
        from application.utils.api_tokens.secret import ensure_api_token_jwt_secret

        if (
            mode == "test"
            and not (os.environ.get("API_TOKEN_JWT_SECRET") or "").strip()
        ):
            os.environ["API_TOKEN_JWT_SECRET"] = (
                "test-only-api-token-jwt-secret-32bytes"
            )
        ensure_api_token_jwt_secret()
    except Exception:
        logger.exception("API_TOKEN_JWT_SECRET bootstrap failed")

    # config[mode].init_app(app)
    sqla.init_app(app=app)
    from application.web.web_main import app as app_blueprint

    app.register_blueprint(app_blueprint)

    from application.web.openapi_registry import init_openapi

    init_openapi(app)

    # Credentialed browser calls are same-origin in prod/staging; keep CORS
    # narrow so cross-site pages cannot drive cookie auth. Admin mutations also
    # require CSRF (see web_main.admin_imports_enabled_required).
    cors_origins = [
        o.strip()
        for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "").split(",")
        if o.strip()
    ]
    if cors_origins:
        CORS(app, origins=cors_origins, supports_credentials=True)
    else:
        CORS(app, supports_credentials=True)
    app.config["CORS_HEADERS"] = "Content-Type, X-CSRF-Token"

    compress.init_app(app)
    cache.init_app(app)

    if mode != "test":
        from application.utils.comprehension.shared import start_background_warm_up

        start_background_warm_up(app)  # no-op unless OWASP_WARMUP_WEB=1
    return app
