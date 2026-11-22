import unittest
from app.agent_runtime import generate_fallback_specialist_output
from app.video_engine.orchestrator import kill_active_render, ACTIVE_RENDER_PROCESSES
from fastapi.testclient import TestClient
from app.main import app

class TestP0Stabilization(unittest.TestCase):
    def test_fallback_transparency(self):
        context = {"brief": {"topic": "Test Konusu", "language": "tr"}}
        fc_out = generate_fallback_specialist_output("fact_checker", context)
        self.assertFalse(fc_out["deliverable"].get("verified", True))
        self.assertTrue(fc_out["deliverable"].get("is_fallback"))
        self.assertEqual(fc_out["decision"], "needs_human_verification")

        qa_out = generate_fallback_specialist_output("quality_auditor", context)
        self.assertTrue(qa_out["deliverable"].get("is_fallback"))
        self.assertEqual(qa_out["decision"], "review")

    def test_kill_active_render_empty(self):
        # Should gracefully return False when id is not tracked
        res = kill_active_render("non_existent_id")
        self.assertFalse(res)

    def test_api_qa_endpoint_async(self):
        client = TestClient(app)
        # Should return 404 for non-existent script without 500 error
        res = client.get("/api/scripts/fake-uuid-not-found/qa")
        self.assertEqual(res.status_code, 404)

if __name__ == "__main__":
    unittest.main()
