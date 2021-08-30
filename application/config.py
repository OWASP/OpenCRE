import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = False
    ITEMS_PER_PAGE = 20
    SLOW_DB_QUERY_TIME = 0.5


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DEV_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite://"


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("PROD_DATABASE_URL")
        or f'sqlite:///{os.path.join(basedir, "../standards_cache.sqlite")}'
    )


class CMDConfig(Config):
    def __init__(self, db_uri: str):
        self.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_uri}"


config = {
    "development": DevelopmentConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}
