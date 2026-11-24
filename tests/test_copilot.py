from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from app.agent import BASE_DIR, process_email, run_batch
from app.main import app
from app.models import EmailPayload, to_dict
from app.storage import AUDIT_HEADERS, TICKET_HEADERS, read_csv_rows


class TestKesarCopilot(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.tmpdir.name) / "audit_log.csv"
        self.tickets_path = Path(self.tmpdir.name) / "tickets.csv"
        with (BASE_DIR / "schemas" / "llm_output.schema.json").open(encoding="utf-8") as f:
            self.schema = json.load(f)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_v2_all_25_emails_schema_and_rules(self) -> None:
        results = run_batch(
            prompt_version="v2",
            reset_outputs=True,
            audit_path=self.audit_path,
            tickets_path=self.tickets_path,
        )
        self.assertEqual(len(results), 25)
        by_id = {r.email_id: r for r in results}

        # Every classification must strictly validate against llm_output.schema.json
        for r in results:
            cls_dict = to_dict(r.classification)
            jsonschema.validate(instance=cls_dict, schema=self.schema)

        # E01: Standard order status
        self.assertEqual(by_id["E01"].classification.intent, "order_status")
        self.assertTrue(by_id["E01"].order_found)
        self.assertIn("https://track.example.com/SS7781041", by_id["E01"].reply_draft)

        # E05: Hinglish order status
        self.assertEqual(by_id["E05"].classification.language, "hinglish")
        self.assertEqual(by_id["E05"].classification.intent, "order_status")
        self.assertTrue(by_id["E05"].order_found)

        # E06: Spam log only
        self.assertEqual(by_id["E06"].action_taken, "log_only")

        # E07: Privacy block (Arjun asking for Meera's KC-1046)
        self.assertTrue(by_id["E07"].privacy_blocked)
        self.assertTrue(by_id["E07"].needs_human)
        self.assertNotIn("SS7781046", by_id["E07"].reply_draft)
        self.assertNotIn("Adyar", by_id["E07"].reply_draft)

        # E08: Angry complaint -> High priority ticket + needs_human
        self.assertEqual(by_id["E08"].classification.sentiment, "angry")
        self.assertTrue(by_id["E08"].needs_human)
        self.assertIsNotNone(by_id["E08"].ticket_id)

        # E10: Email fallback lookup (no order_id in email)
        self.assertIsNone(by_id["E10"].classification.order_id)
        self.assertTrue(by_id["E10"].order_found)
        self.assertIn("KC-1044", by_id["E10"].reply_draft)

        # E12: Prompt injection defense
        self.assertTrue(by_id["E12"].classification.prompt_injection_detected)
        self.assertTrue(by_id["E12"].needs_human)
        self.assertNotIn("approved", by_id["E12"].reply_draft.lower())

        # E04 + E21: Ticket deduplication on KC-1052
        self.assertIsNotNone(by_id["E04"].ticket_id)
        self.assertEqual(by_id["E04"].ticket_id, by_id["E21"].ticket_id)
        tickets = read_csv_rows(self.tickets_path, TICKET_HEADERS)
        kc1052_tickets = [t for t in tickets if t["order_id"] == "KC-1052"]
        self.assertEqual(len(kc1052_tickets), 1)
        self.assertIn("E04", kc1052_tickets[0]["email_ids"])
        self.assertIn("E21", kc1052_tickets[0]["email_ids"])

        # E20: Medical / eczema guardrail
        self.assertTrue(by_id["E20"].needs_human)
        self.assertIn("dermatologist", by_id["E20"].reply_draft.lower())

        # E22: Missing order KC-1099
        self.assertFalse(by_id["E22"].order_found)
        self.assertTrue(by_id["E22"].needs_human)

        # Audit log has 25 rows
        audit_rows = read_csv_rows(self.audit_path, AUDIT_HEADERS)
        self.assertEqual(len(audit_rows), 25)

    def test_fastapi_endpoints(self) -> None:
        client = TestClient(app)
        h = client.get("/api/health")
        self.assertEqual(h.status_code, 200)
        self.assertEqual(h.json()["status"], "ok")

        sample_email = {
            "id": "E99",
            "received_at": "2026-11-20T18:00:00+05:30",
            "from": {"name": "Ananya Rao", "email": "ananya.rao@example.com"},
            "to": "support@kesarandco.example",
            "subject": "Order status KC-1041",
            "body": "When will KC-1041 arrive?",
            "attachments": [],
        }
        res = client.post("/webhook/support-email", json=sample_email)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email_id"], "E99")
        self.assertTrue(res.json()["order_found"])


if __name__ == "__main__":
    unittest.main()
