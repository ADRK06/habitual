#!/usr/bin/env python3
"""Runs `flask db upgrade` against the Neon main (prod) branch.

Loads DATABASE_URL from .env.prod via python-dotenv's parser, not a shell
`source` - shell parsing mis-handles values containing &, $, backticks,
quotes, etc. (an unquoted `&` previously split the value, DATABASE_URL
silently never loaded, and the migration ran against dev instead of prod).

Refuses to run if DATABASE_URL is missing, or identical to the resolved dev
DATABASE_URL, and always asks for an explicit "yes" after showing the
password-masked target host.
"""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from habitual.config import Config, _normalize_db_url  # noqa: E402

PROD_ENV_FILE = ROOT_DIR / ".env.prod"


def mask(raw_url):
    normalized = _normalize_db_url(raw_url)
    parts = urlsplit(normalized)
    userinfo = ""
    if parts.username:
        userinfo = f"{parts.username}:****@" if parts.password else f"{parts.username}@"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{userinfo}{parts.hostname or ''}{port}{parts.path}"


def main():
    if not PROD_ENV_FILE.exists():
        print(f"Missing {PROD_ENV_FILE}", file=sys.stderr)
        print("Create it from .env.prod.example with the Neon main branch's pooled DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    prod_values = dotenv_values(PROD_ENV_FILE)
    prod_url = prod_values.get("DATABASE_URL")
    if not prod_url:
        print(f"DATABASE_URL missing or empty in {PROD_ENV_FILE}", file=sys.stderr)
        sys.exit(1)

    # Config already resolved the dev DATABASE_URL via the app's own
    # load_dotenv() search - reuse that instead of guessing where the dev
    # .env file lives.
    dev_normalized = Config.SQLALCHEMY_DATABASE_URI
    prod_normalized = _normalize_db_url(prod_url)

    if prod_normalized and prod_normalized == dev_normalized:
        print("DATABASE_URL in .env.prod is identical to the resolved dev DATABASE_URL.", file=sys.stderr)
        print("Refusing to run - this would migrate the dev database again, not prod.", file=sys.stderr)
        sys.exit(1)

    print("Dev :", mask(dev_normalized) if dev_normalized else "(not set)")
    print("Prod:", mask(prod_normalized))
    confirm = input('Type "yes" to run migrations against the PROD database above: ')
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(1)

    env = os.environ.copy()
    env["DATABASE_URL"] = prod_url
    print("Running migrations against production (Neon main)...")
    result = subprocess.run(["flask", "--app", "app", "db", "upgrade"], cwd=ROOT_DIR, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
