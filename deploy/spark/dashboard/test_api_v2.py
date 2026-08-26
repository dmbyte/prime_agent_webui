#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prime_dashboard_api_v2", Path(__file__).with_name("api_v2.py"))
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class DashboardV2Tests(unittest.TestCase):
    def test_update_requires_exact_confirmation(self):
        with self.assertRaisesRegex(ValueError, "confirmation"):
            api.start_update("webui", "yes")

    def test_release_versions_are_compared_numerically(self):
        self.assertEqual(api.version_tuple("v0.10.2"), (0, 10, 2))
        self.assertEqual(api.version_tuple("0.8.0"), (0, 8, 0))
        self.assertIsNone(api.version_tuple("latest"))

    def test_running_update_cannot_be_started_twice(self):
        with mock.patch.object(api, "update_status", return_value={"agent": {"active": True}}):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                api.start_update("agent", "update-agent")

    def test_conversation_catalog_is_filtered_by_owner(self):
        rows = [
            {"id": "session-alice", "topic": "Alice", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"},
            {"id": "session-bob-12", "topic": "Bob", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"},
        ]
        meta = {"conversations": {"session-alice": {"owner": "alice"}, "session-bob-12": {"owner": "bob"}}}
        with mock.patch.object(api.legacy, "session_catalog", return_value=rows), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
            self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])

    def test_initial_admin_cache_cannot_be_deleted(self):
        with self.assertRaisesRegex(ValueError, "initial administrator"):
            api.purge_user_cache("dbyte")

    def test_user_cache_purge_includes_persisted_logs_and_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions"; uploads = root / "uploads"; logs = root / "logs"
            sessions.mkdir(); uploads.mkdir(); logs.mkdir()
            (sessions / "session-alice.jsonl").write_text("{}\n")
            (uploads / "alice" ).mkdir()
            (uploads / "alice/file.txt").write_text("private")
            (logs / "task-alice.log").write_text("private log")
            meta_path = root / "metadata.json"
            meta_path.write_text(json.dumps({"conversations": {"session-alice": {"owner": "alice"}}, "files": {"alice/file.txt": {"owner": "alice"}}, "tasks": {"task-alice": {"owner": "alice"}}}))
            ledger = root / "ledger.jsonl"
            ledger.write_text(json.dumps({"owner": "alice", "taskId": "task-alice"}) + "\n" + json.dumps({"owner": "bob", "taskId": "task-bob"}) + "\n")
            with mock.patch.object(api, "META", meta_path), mock.patch.object(api, "LEDGER", ledger), mock.patch.object(api, "TASK_LOGS", logs), mock.patch.object(api, "USER_TRASH", root / "trash"), mock.patch.object(api.legacy, "SESSIONS", sessions), mock.patch.object(api.legacy, "UPLOADS", uploads), mock.patch.object(api.legacy, "audit"):
                result = api.purge_user_cache("alice")
            self.assertEqual((result["sessions"], result["files"], result["logs"], result["usageRecords"]), (1, 1, 1, 1))
            self.assertFalse((logs / "task-alice.log").exists())
            self.assertNotIn("alice", ledger.read_text())
            self.assertIn("bob", ledger.read_text())

    def test_provider_catalog_never_returns_stored_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / "auth.json"; provider_settings = root / "provider-settings.json"; models = root / "models.json"
            models.write_text('{"providers":{}}')
            with mock.patch.object(api, "PROVIDER_AUTH", auth), mock.patch.object(api.legacy, "PROVIDER_SETTINGS", provider_settings), mock.patch.object(api.legacy, "MODEL_CONFIG", models), mock.patch.object(api.legacy, "openai_env_configured", return_value=False), mock.patch.object(api.legacy, "audit"):
                api.configure_provider({"provider": "google", "values": {"apiKey": "private-test-key-value"}})
                catalog = json.dumps(api.provider_catalog())
            self.assertNotIn("private-test-key-value", catalog)
            self.assertTrue(next(row for row in json.loads(catalog) if row["id"] == "google")["configured"])
            self.assertEqual(json.loads(auth.read_text())["google"]["type"], "api_key")
            self.assertEqual(auth.stat().st_mode & 0o777, 0o600)

    def test_custom_provider_preserves_existing_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / "auth.json"; provider_settings = root / "provider-settings.json"; models = root / "models.json"
            models.write_text(json.dumps({"providers": {"spark-local": {"models": [{"id": "local"}]}}}))
            payload = {"provider": "custom-openai", "values": {"providerId": "lab-model", "baseUrl": "http://127.0.0.1:9000/v1", "apiKey": "custom-private-key", "modelId": "test-model", "contextWindow": "32768", "maxTokens": "4096"}}
            with mock.patch.object(api, "PROVIDER_AUTH", auth), mock.patch.object(api.legacy, "PROVIDER_SETTINGS", provider_settings), mock.patch.object(api.legacy, "MODEL_CONFIG", models), mock.patch.object(api.legacy, "openai_env_configured", return_value=False), mock.patch.object(api.legacy, "audit"):
                api.configure_provider(payload)
            saved = json.loads(models.read_text())["providers"]
            self.assertIn("spark-local", saved)
            self.assertEqual(saved["lab-model"]["apiKey"], "PRIME_CUSTOM_LAB_MODEL_API_KEY")
            self.assertEqual(json.loads(provider_settings.read_text())["PRIME_CUSTOM_LAB_MODEL_API_KEY"], "custom-private-key")

    def settings(self, provider="spark-nemotron", model="nemotron-3.5-lightning", qwen=True):
        enabled = ["spark-nemotron/nemotron-3.5-lightning"]
        if qwen:
            enabled.append("spark-qwen/qwen3.6-35b-a3b")
        return {"provider": provider, "model": model, "thinking": "low", "enabledModels": enabled}

    def test_specialist_prompt_routes_to_qwen(self):
        route = api.route_task("Review this STL for printability and clearances", self.settings())
        self.assertEqual((route["provider"], route["model"]), api.QWEN_ROUTE)
        self.assertEqual(route["routingMode"], "automatic")

    def test_explicit_model_route_overrides_specialist_match(self):
        route = api.route_task("Use Nemotron to review this portfolio", self.settings())
        self.assertEqual((route["provider"], route["model"]), api.NEMOTRON_ROUTE)
        self.assertEqual(route["routingMode"], "explicit")

    def test_disabled_qwen_falls_back_visibly(self):
        route = api.route_task("Use Qwen for this chart", self.settings(qwen=False))
        self.assertEqual((route["provider"], route["model"]), api.NEMOTRON_ROUTE)
        self.assertEqual(route["routingMode"], "fallback")

    def test_manual_frontier_default_is_preserved(self):
        settings = self.settings("openai", "gpt-5.4")
        route = api.route_task("Review this portfolio", settings)
        self.assertEqual((route["provider"], route["model"]), ("openai", "gpt-5.4"))
        self.assertEqual(route["routingMode"], "default")

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../../escape.txt", "no")
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                api.inspect_archive(path)

    def test_archive_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "link.zip"
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(info, "target")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                api.inspect_archive(path)

    def test_upload_identifier_cannot_escape_root(self):
        original = api.legacy.UPLOADS
        with tempfile.TemporaryDirectory() as directory:
            api.legacy.UPLOADS = Path(directory) / "uploads"
            api.legacy.UPLOADS.mkdir()
            encoded = "Li4vb3V0c2lkZQ"
            with self.assertRaisesRegex(ValueError, "File not found"):
                api.upload_path(encoded)
        api.legacy.UPLOADS = original


if __name__ == "__main__":
    unittest.main()
