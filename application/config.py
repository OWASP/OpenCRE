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
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DEV_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class TestingConfig(Config):
    ENVIRONMENT = "TESTING"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite://"


class ProductionConfig(Config):
    ENVIRONMENT = "PRODUCTION"
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("PROD_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class CMDConfig(Config):
    ENVIRONMENT = "CLI"

    def __init__(self, db_uri: str):
        self.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_uri}"


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}
