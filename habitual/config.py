import os

from dotenv import load_dotenv

load_dotenv()


def _normalize_db_url(url: str) -> str:
    # Neon (and most hosts) give us postgresql://, but SQLAlchemy needs to be
    # told to use the psycopg v3 driver explicitly.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 5,
    }

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Vercel sets VERCEL=1 for every deployment (prod and preview alike), both served
    # over https; only plain local dev should skip the Secure flag.
    SESSION_COOKIE_SECURE = bool(os.environ.get("VERCEL"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


class TestConfigWithCSRF(TestConfig):
    WTF_CSRF_ENABLED = True
