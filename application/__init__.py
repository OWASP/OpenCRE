# type:ignore
import string
from typing import Any
from sqlalchemy import MetaData
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_compress import Compress
from application.config import config
import os
import random

from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor


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
tracer = None


def create_app(mode: str = "production", conf: any = None) -> Any:
    global tracer
    app = Flask(__name__)
    if not conf:
        app.config.from_object(config[mode])
    else:
        app.config.from_object(conf)
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    app.secret_key = GOOGLE_CLIENT_SECRET
    if os.environ.get("NO_LOGIN"):
        letters = string.ascii_lowercase
        app.secret_key = "".join(random.choice(letters) for i in range(20))

    # config[mode].init_app(app)
    sqla.init_app(app=app)
    from application.web.web_main import app as app_blueprint

    app.register_blueprint(app_blueprint)

    CORS(app)
    app.config["CORS_HEADERS"] = "Content-Type"

    compress.init_app(app)
    cache.init_app(app)

    if os.environ.get("ENABLE_TRACING"):
        """Configures OpenTelemetry context propagation to use Cloud Trace context"""
        set_global_textmap(CloudTraceFormatPropagator())
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        tracer = trace.get_tracer(__name__)
        FlaskInstrumentor().instrument_app(app)

        with app.app_context():
            SQLAlchemyInstrumentor().instrument(
                engine=sqla.engine, enable_commenter=True, commenter_options={}
            )

        RequestsInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={
                "framework": True,
                "route": True,
                "controller": True,
            },
        )

    return app
