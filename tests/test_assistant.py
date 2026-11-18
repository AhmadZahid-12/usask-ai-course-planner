import os
import unittest
from unittest.mock import patch

from app import create_app
from app.gpt_helper import SUMMARY_UNAVAILABLE

OFFICIAL = {"raw_text": "Official description <script>course content</script>.", "retrieved": "2026-11-18"}


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"}).test_client()

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    @patch("app.routes.summarize_course")
    @patch("app.routes.get_course_raw_info", return_value=OFFICIAL)
    def test_official_lookup_works_without_key_and_escapes_text(self, fetch, summarize):
        page = self.client.post("/summarize", data={"course_code": "cmpt141.3"})
        self.assertIn(b"Official catalogue", page.data)
        self.assertIn(b"&lt;script&gt;", page.data)
        self.assertNotIn(b"AI-generated explanation", page.data)
        fetch.assert_called_once_with("CMPT 141")
        summarize.assert_not_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"})
    @patch("app.routes.summarize_course", return_value="Generated explanation.")
    @patch("app.routes.get_course_raw_info", return_value=OFFICIAL)
    def test_only_generation_action_calls_assistant(self, fetch, summarize):
        self.client.post("/summarize", data={"course_code": "CMPT 141", "action": "lookup"})
        summarize.assert_not_called()
        page = self.client.post("/summarize", data={"course_code": "CMPT 141", "action": "generate"})
        self.assertIn(b"AI-generated explanation", page.data)
        self.assertIn(b"Generated explanation.", page.data)
        self.assertNotIn(b"test-placeholder", page.data)
        summarize.assert_called_once_with("CMPT 141", desc=OFFICIAL["raw_text"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"})
    @patch("app.routes.summarize_course", return_value=SUMMARY_UNAVAILABLE)
    @patch("app.routes.get_course_raw_info", return_value=OFFICIAL)
    def test_failed_summarization_retains_official_entry(self, fetch, summarize):
        page = self.client.post("/summarize", data={"course_code": "CMPT 141"})
        self.assertIn(b"AI summary is unavailable", page.data)
        self.assertIn(b"Official catalogue", page.data)
        self.assertNotIn(b"AI-generated explanation", page.data)
