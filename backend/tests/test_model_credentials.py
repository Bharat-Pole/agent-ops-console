"""LLM API keys live in the vault like every other credential: encrypted,
rotatable without a restart, and per-model so teams can use different keys.
The env var survives only as a bootstrap fallback.
"""
from __future__ import annotations

import pytest
from conftest import login
from sqlalchemy import select

from app.adapters import models as adapters
from app.config import settings
from app.db import SessionLocal
from app.models import ModelCatalogEntry


@pytest.fixture()
def _restore_env():
    original = settings.gemini_api_key
    yield
    settings.gemini_api_key = original
    with SessionLocal() as db:
        for entry in db.scalars(select(ModelCatalogEntry)).all():
            entry.credential_ref = None
        db.commit()


def _set_model_credential(model_ref: str, secret_name: str | None) -> None:
    with SessionLocal() as db:
        entry = db.scalars(select(ModelCatalogEntry).where(
            ModelCatalogEntry.model_ref == model_ref)).first()
        entry.credential_ref = secret_name
        db.commit()


def test_vault_credential_wins_over_env(client, _restore_env):
    login(client, "engineer@platform.local")
    client.put("/api/secrets", json={"name": "team.gemini.key", "value": "vault-key-value"})
    _set_model_credential(settings.gemini_model, "team.gemini.key")
    settings.gemini_api_key = "env-key-value"

    with SessionLocal() as db:
        key, source = adapters.resolve_credential(db, settings.gemini_model)
    assert key == "vault-key-value"
    assert source == "vault:team.gemini.key"


def test_env_is_the_bootstrap_fallback(client, _restore_env):
    settings.gemini_api_key = "env-key-value"
    with SessionLocal() as db:
        key, source = adapters.resolve_credential(db, settings.gemini_model)
    assert key == "env-key-value"
    assert source == "env:PLATFORM_GEMINI_API_KEY"


def test_missing_named_secret_does_not_fall_back_to_someone_elses_key(client, _restore_env):
    """A model pointing at a secret that isn't there is a misconfiguration.
    Silently using the global env key would bill the wrong account and hide
    the mistake."""
    _set_model_credential(settings.gemini_model, "does.not.exist")
    settings.gemini_api_key = "env-key-value"

    with SessionLocal() as db:
        key, source = adapters.resolve_credential(db, settings.gemini_model)
    assert key is None
    assert "NOT FOUND" in source


def test_different_models_can_use_different_keys(client, _restore_env):
    login(client, "engineer@platform.local")
    client.put("/api/secrets", json={"name": "team.a.key", "value": "key-for-a"})
    client.put("/api/secrets", json={"name": "team.b.key", "value": "key-for-b"})
    _set_model_credential(settings.gemini_model, "team.a.key")
    _set_model_credential(settings.gemini_embedding_model, "team.b.key")

    with SessionLocal() as db:
        gen_key, _ = adapters.resolve_credential(db, settings.gemini_model)
        emb_key, _ = adapters.resolve_credential(db, settings.gemini_embedding_model)
    assert gen_key == "key-for-a"
    assert emb_key == "key-for-b"


def test_rotation_takes_effect_without_restart(client, _restore_env):
    login(client, "engineer@platform.local")
    client.put("/api/secrets", json={"name": "rotate.me", "value": "first-value"})
    _set_model_credential(settings.gemini_model, "rotate.me")
    with SessionLocal() as db:
        assert adapters.resolve_credential(db, settings.gemini_model)[0] == "first-value"

    client.put("/api/secrets", json={"name": "rotate.me", "value": "second-value"})
    with SessionLocal() as db:
        assert adapters.resolve_credential(db, settings.gemini_model)[0] == "second-value"


def test_api_rejects_a_credential_that_is_not_in_the_vault(client):
    login(client, "admin@platform.local")
    r = client.post("/api/models", json={
        "provider": "gemini", "model_ref": "ghost-model", "kind": "llm",
        "display_name": "Ghost", "credential_ref": "nope.not.here",
    })
    assert r.status_code == 422
    assert "no secret named" in r.json()["detail"]


def test_catalog_never_exposes_secret_values(client):
    login(client, "engineer@platform.local")
    client.put("/api/secrets", json={"name": "peek.key", "value": "super-secret-value"})
    _set_model_credential(settings.gemini_model, "peek.key")
    body = client.get("/api/models").text
    assert "peek.key" in body            # the NAME is useful to operators
    assert "super-secret-value" not in body  # the VALUE never leaves the server
    _set_model_credential(settings.gemini_model, None)
