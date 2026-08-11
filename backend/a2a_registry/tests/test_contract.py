import sys
import unittest

sys.path.insert(0, "backend")

from a2a_registry.config import normalize_database_url
from a2a_registry.schemas import CardInput, EligibilityInput


def standardized_card(**overrides):
    value = {
        "agent_id": "agt-noc-incident-20260122-a1b2",
        "name": "NOC Incident Summarizer",
        "description": "Summarizes internal incidents.",
        "owner_team": "network-operations",
        "endpoint": "https://internal-api.example.com/a2a/noc",
        "skills": ["grounded-answer", "summarization"],
        "supported_tasks": ["incident-summary"],
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
        "capability_tier": "standardized",
        "discovery_only": True,
        "message_task_format": None,
        "artifact_exchange": False,
    }
    value.update(overrides)
    return value


class A2AContractTests(unittest.TestCase):
    def test_database_url_normalizes_raw_at_in_password(self):
        url = normalize_database_url("postgresql+psycopg://postgres:TestPassword@433@localhost:5432/a2a_registry")
        self.assertEqual(url, "postgresql+psycopg://postgres:TestPassword%40433@localhost:5432/a2a_registry")

    def test_standardized_discovery_card_is_valid(self):
        card = CardInput(**standardized_card())
        self.assertTrue(card.discovery_only)

    def test_standardized_full_exchange_is_rejected(self):
        with self.assertRaises(ValueError):
            CardInput(**standardized_card(artifact_exchange=True))

    def test_advanced_card_requires_task_format(self):
        with self.assertRaises(ValueError):
            CardInput(**standardized_card(capability_tier="advanced", discovery_only=False, artifact_exchange=True, artifact_format="json"))

    def test_advanced_card_with_full_exchange_is_valid(self):
        card = CardInput(**standardized_card(
            capability_tier="advanced",
            discovery_only=False,
            message_task_format="a2a/task-v1",
            artifact_exchange=True,
            artifact_format="json+uri",
            supported_tasks=["incident-summary", "handoff-review"],
            handoff_rules={"max_hops": 2, "require_human_approval": True, "allowed_target_skills": ["summarization"]},
        ))
        self.assertEqual(card.artifact_format, "json+uri")
        self.assertTrue(card.handoff_rules.require_human_approval)

    def test_duplicate_skills_are_rejected(self):
        with self.assertRaises(ValueError):
            CardInput(**standardized_card(skills=["summarization", "summarization"]))

    def test_duplicate_tasks_are_rejected(self):
        with self.assertRaises(ValueError):
            CardInput(**standardized_card(supported_tasks=["incident-summary", "incident-summary"]))

    def test_all_three_tracks_are_required_for_eligibility(self):
        base = {
            "source_agent_id": "agt-noc-incident-20260122-a1b2",
            "a2a_enabled": True,
            "capability_tier": "standardized",
            "lifecycle_status": "live",
            "registry_ready": True,
            "runtime_ready": True,
            "content_ready": True,
            "source_version": "1",
            "observed_at": "2026-08-04T10:00:00Z",
        }
        self.assertTrue(EligibilityInput(**base).is_eligible())
        self.assertFalse(EligibilityInput(**{**base, "content_ready": False}).is_eligible())
