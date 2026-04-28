import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = False
    ITEMS_PER_PAGE = 20
    SLOW_DB_QUERY_TIME = 0.5


class DevelopmentConfig(Config):
    DEBUG = True
    ENVIRONMENT = "DEVELOPMENT"
    CACHE_TYPE = "SimpleCache"
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DEV_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class TestingConfig(Config):
    ENVIRONMENT = "TESTING"
    CACHE_TYPE = "SimpleCache"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite://"


class ProductionConfig(Config):
    ENVIRONMENT = "PRODUCTION"
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 3000
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("PROD_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class CMDConfig(Config):
    ENVIRONMENT = "CLI"

    def __init__(self, db_uri: str):
        if "://" in db_uri:
            # Heroku and some tools still emit ``postgres://``; SQLAlchemy 2 expects
            # ``postgresql://`` for the psycopg dialect name.
            if db_uri.startswith("postgres://"):
                db_uri = "postgresql://" + db_uri[len("postgres://") :]
            self.SQLALCHEMY_DATABASE_URI = db_uri
        else:
            # Flask-SQLAlchemy 3+ resolves non-absolute sqlite URLs against
            # app.instance_path, not the shell cwd. CLI --cache_file should
            # follow the user's working directory.
            resolved = os.path.abspath(db_uri)
            self.SQLALCHEMY_DATABASE_URI = f"sqlite:///{resolved}"


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}
