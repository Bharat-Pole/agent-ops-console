"""Test fixtures: real FastAPI app + real DB (SQLite locally; set
PLATFORM_DATABASE_URL to run the same suite against Postgres in compose/CI).
"""
from __future__ import annotations

import os
import tempfile

# Must be set BEFORE app modules import (engine binds at import time).
_tmpdir = tempfile.mkdtemp(prefix="platform-test-")
os.environ.setdefault("PLATFORM_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ.setdefault("PLATFORM_SESSION_SECRET", "test-secret")
os.environ.setdefault("PLATFORM_FILE_STORE_DIR", f"{_tmpdir}/filestore")

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.seed import seed


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(engine)
    seed()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    return TestClient(app)


def login(client: TestClient, email: str, password: str = "changeme!") -> TestClient:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client
