"""Test fixtures: isolated SQLite per-test, app instance, authenticated client."""
import os
import tempfile
import pathlib
import sys

# Ensure repo root is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Point the app at a fresh DB file for every test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("HRMS_DB_PATH", str(db_file))
    # Force reimport of db module so DB_PATH is re-evaluated.
    for mod in list(sys.modules):
        if mod.startswith("server"):
            del sys.modules[mod]
    from server import db, config
    config.DB_PATH = db_file
    db.DB_PATH = db_file
    db.init_db()
    from server.hrms import schema as hrms_db
    hrms_db.init_hrms_db()
    yield db_file


@pytest.fixture
def app(tmp_db):
    from server.app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(tmp_db):
    from server.config import DEFAULT_TENANT
    from server.hrms import schema as hrms_db
    return hrms_db.create_user(
        tenant_id=DEFAULT_TENANT, email="admin@example.com",
        password="admin", name="Admin", role="super_admin",
    )


@pytest.fixture
def tenant_id():
    from server.config import DEFAULT_TENANT
    return DEFAULT_TENANT
