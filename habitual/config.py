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

    # Gates /dev/styleguide (habitual/dev.py) - a token/component reference
    # page for the Colonies restyle, never meant to exist in prod. Must
    # never be set on Vercel; see .env.example.
    HABITUAL_DEV = bool(os.environ.get("HABITUAL_DEV"))

    # Which top-level nav sections (Sidebar.dc.html / PhoneNav.dc.html
    # items) actually exist yet. Only "habits", "fleet" and "profile" are
    # real pages in Phase 1 - the rest (colony, sector, galaxy, shop) are
    # later-phase game features with no backing data model yet (see
    # CLAUDE.md's roadmap). base.html/app_base.html render the shell as
    # if every item were real, just skipping the ones flagged off - no
    # empty slots. Flip a flag on once its phase actually lands; nothing
    # else about the shell's layout changes.
    NAV_FEATURES = {
        "colony": False,
        "habits": True,
        "fleet": True,
        "sector": False,
        "galaxy": False,
        "shop": False,
        "profile": True,
    }


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


class TestConfigWithCSRF(TestConfig):
    WTF_CSRF_ENABLED = True
