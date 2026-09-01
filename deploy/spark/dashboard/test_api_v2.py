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
    def test_live_task_events_publish_safe_progress_without_reasoning(self):
        task_id = "a" * 32
        api.TASKS[task_id] = {"id": task_id, "owner": "alice", "status": "running", "started": "2026-01-01T00:00:00Z", "startedEpoch": api.time.time(), "progressEvents": [], "sessionId": None}
        try:
            api.apply_task_event(task_id, {"type": "session", "id": "session-live-1234"})
            api.apply_task_event(task_id, {"type": "message_update", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "private chain"}, {"type": "text", "text": "Visible draft"}, {"type": "toolCall", "name": "search"}]}})
            row = api.task_snapshot("alice")[0]
            self.assertEqual(row["agentSessionId"], "session-live-1234")
            self.assertEqual(row["liveResponse"], "Visible draft")
            self.assertNotIn("private chain", json.dumps(row))
            self.assertEqual(row["progress"], "Using search")
            self.assertIn("Reasoning in progress", json.dumps(row))
        finally:
            api.TASKS.pop(task_id, None)

    def test_model_error_is_visible_and_marks_task_failed(self):
        task_id = "d" * 32
        api.TASKS[task_id] = {"id": task_id, "owner": "alice", "status": "running", "progressEvents": [], "runtimeEvents": []}
        try:
            api.apply_task_event(task_id, {"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "Connection error."}})
            row = api.TASKS[task_id]
            self.assertEqual(row["rpcError"], "Connection error.")
            self.assertEqual(row["progress"], "Model request failed")
            self.assertEqual(row["runtimeEvents"][-1]["kind"], "error")
        finally:
            api.TASKS.pop(task_id, None)

    def test_runtime_redaction_removes_credentials(self):
        value = api.sanitize_runtime_text("Authorization: Bearer secret-token sk-proj-" + "x" * 30)
        self.assertNotIn("secret-token", value)
        self.assertNotIn("sk-proj-", value)

    def test_full_live_log_redacts_private_reasoning_and_secrets(self):
        task = {}
        api.append_live_log(task, json.dumps({"type": "message_update", "authorization": "Bearer private", "message": {"content": [{"type": "thinking", "thinking": "hidden chain", "text": "also hidden"}, {"type": "text", "text": "visible answer"}]}, "assistantMessageEvent": {"type": "thinking_delta", "delta": "hidden fragment", "content": "hidden ending"}}))
        logged = task["liveLog"][0]["line"]
        self.assertIn("visible answer", logged)
        self.assertIn("[PRIVATE_REASONING]", logged)
        self.assertIn("[REDACTED]", logged)
        self.assertNotIn("hidden chain", logged)
        self.assertNotIn("hidden fragment", logged)
        self.assertNotIn("hidden ending", logged)
        self.assertNotIn("Bearer private", logged)

    def test_steering_is_owner_scoped_and_uses_rpc_channel(self):
        task_id = "b" * 32
        stdin = mock.Mock()
        process = mock.Mock(stdin=stdin)
        api.TASKS[task_id] = {"id": task_id, "owner": "alice", "status": "running", "rpcReady": True, "process": process, "progressEvents": []}
        def acknowledge(value):
            request = json.loads(value)
            api.TASKS[task_id].setdefault("rpcResponses", {})[request["id"]] = {"success": True}
        stdin.write.side_effect = acknowledge
        try:
            with mock.patch.object(api.legacy, "audit"):
                result = api.message_native_task(task_id, "Focus on authentication", "steer", "alice")
            self.assertTrue(result["delivered"])
            payload = json.loads(stdin.write.call_args.args[0])
            self.assertEqual(payload["type"], "steer")
            self.assertEqual(payload["message"], "Focus on authentication")
            stdin.flush.assert_called_once()
            with self.assertRaisesRegex(ValueError, "no longer running"):
                api.message_native_task(task_id, "Wrong owner", "steer", "bob")
        finally:
            api.TASKS.pop(task_id, None)

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
        with mock.patch.object(api.legacy, "session_catalog", return_value=rows), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value, root=None: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
            self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])

    def test_conversation_catalog_returns_saved_task_policy(self):
        rows = [{"id": "session-alice", "topic": "Alice", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"}]
        policy = {"profile": "finance", "executionMode": "prompt", "networkMode": "internet"}
        meta = {"conversations": {"session-alice": {"owner": "alice", "taskPolicy": policy}}}
        with mock.patch.object(api.legacy, "session_catalog", return_value=rows), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value, root=None: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
            self.assertEqual(api.conversation_catalog(user="alice")[0]["taskPolicy"], policy)

    def test_conversation_policy_is_persisted_and_role_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            meta_path = Path(directory) / "metadata.json"
            meta_path.write_text(json.dumps({"conversations": {"session-alice": {"owner": "alice"}}}))
            policy = {"profile": "development", "executionMode": "prompt", "networkMode": "internet"}
            with mock.patch.object(api, "META", meta_path), mock.patch.object(api.legacy, "session_path", return_value=Path("/tmp/session-alice.jsonl")):
                result = api.update_conversation("session-alice", "policy", policy, "alice", "user")
                self.assertEqual(result["taskPolicy"], policy)
                self.assertEqual(json.loads(meta_path.read_text())["conversations"]["session-alice"]["taskPolicy"], policy)
                with self.assertRaisesRegex(ValueError, "power-user"):
                    api.update_conversation("session-alice", "policy", {**policy, "networkMode": "full"}, "alice", "user")

    def test_new_conversation_stores_original_policy_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            meta_path = Path(directory) / "metadata.json"
            meta_path.write_text('{"conversations":{}}')
            task = {"sessionId": "session-new-1234", "thinking": "high", "provider": "p", "model": "m", "routingMode": "default", "routeReason": "default", "owner": "alice", "persistPolicyOnSessionCreate": True, "policyPreference": {"profile": "cad", "executionMode": "prompt", "networkMode": "restricted"}}
            with mock.patch.object(api, "META", meta_path):
                api.store_task_route(task)
            saved = json.loads(meta_path.read_text())["conversations"]["session-new-1234"]
            self.assertEqual(saved["taskPolicy"], task["policyPreference"])

    def test_conversation_catalog_uses_cache_during_temporary_permission_change(self):
        rows = [{"id": "session-alice", "topic": "Alice", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"}]
        meta = {"conversations": {"session-alice": {"owner": "alice"}}}
        api.SESSION_CACHE.pop("alice", None)
        with mock.patch.object(api.legacy, "session_catalog", side_effect=[rows, PermissionError("temporarily protected")]), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value, root=None: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
            self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])
            self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])
        api.SESSION_CACHE.pop("alice", None)

    def test_conversation_catalog_does_not_replace_cache_with_empty_during_task(self):
        rows = [{"id": "session-alice", "topic": "Alice", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"}]
        meta = {"conversations": {"session-alice": {"owner": "alice"}}}
        task_id = "d" * 32
        api.SESSION_CACHE.pop("alice", None)
        api.TASKS[task_id] = {"owner": "alice", "status": "running"}
        try:
            with mock.patch.object(api.legacy, "session_catalog", side_effect=[rows, []]), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value, root=None: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
                self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])
                self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])
        finally:
            api.TASKS.pop(task_id, None)
            api.SESSION_CACHE.pop("alice", None)

    def test_conversation_catalog_uses_persisted_cache_after_api_restart(self):
        rows = [{"id": "session-alice", "topic": "Alice", "modified": "2026-01-01T00:00:00Z", "provider": "p", "model": "m"}]
        meta = {"conversations": {"session-alice": {"owner": "alice"}}, "sessionCatalogCache": {"alice": rows}}
        api.SESSION_CACHE.pop("alice", None)
        try:
            with mock.patch.dict(api.os.environ, {"PRIME_TASK_CONTAINER_IMAGE": "1"}), mock.patch.object(api.os, "access", return_value=False), mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api.legacy, "session_path", side_effect=lambda value, root=None: Path(f"/tmp/{value}.jsonl")), mock.patch.object(api, "model_details", return_value={}):
                self.assertEqual([row["id"] for row in api.conversation_catalog(user="alice")], ["session-alice"])
        finally:
            api.SESSION_CACHE.pop("alice", None)

    def test_known_conversation_update_does_not_stat_protected_session(self):
        meta = {"conversations": {"session-alice": {"owner": "alice"}}}
        with mock.patch.object(api, "metadata", return_value=meta), mock.patch.object(api, "save_metadata") as save, mock.patch.object(api.legacy, "session_path", side_effect=PermissionError("protected")):
            result = api.update_conversation("session-alice", "pin", True, "alice", "user")
        self.assertTrue(result["pinned"])
        save.assert_called_once()

    def test_session_stems_tolerates_temporarily_inaccessible_tree(self):
        inaccessible = mock.Mock()
        inaccessible.glob.side_effect = PermissionError("temporarily protected")
        with mock.patch.object(api, "session_root", return_value=inaccessible):
            self.assertEqual(api.session_stems("alice"), set())

    def test_broker_exit_marks_task_failed_without_exposing_details(self):
        task_id = "c" * 32
        api.TASKS[task_id] = {"id": task_id, "owner": "alice", "status": "running", "progressEvents": []}
        try:
            api.apply_task_event(task_id, {"type": "broker_exit", "exitCode": 17})
            self.assertEqual(api.TASKS[task_id]["rpcError"], "Rootless task broker exited")
            self.assertNotIn("exitCode", api.TASKS[task_id])
        finally:
            api.TASKS.pop(task_id, None)

    def test_container_sessions_are_resolved_per_authenticated_owner(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(api.os.environ, {"PRIME_TASK_CONTAINER_IMAGE":"1", "PRIME_RUNNER_STORAGE":directory}):
            self.assertEqual(api.session_root("alice"), Path(directory)/"alice/prime/agent/sessions")
            self.assertNotEqual(api.session_root("alice"), api.session_root("bob"))
            with self.assertRaisesRegex(ValueError, "owner"):
                api.session_root("../escape")

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

    def settings(self, provider="spark-nemotron", model="nemotron-3.5-lightning", qwen=True, codex=False):
        enabled = ["spark-nemotron/nemotron-3.5-lightning"]
        if qwen:
            enabled.append("spark-qwen/qwen3.6-35b-a3b")
        if codex:
            enabled.append("openai-codex/gpt-5.6-sol")
        return {"provider": provider, "model": model, "thinking": "low", "enabledModels": enabled}

    def test_specialist_prompt_routes_to_qwen(self):
        route = api.route_task("Review this STL for printability and clearances", self.settings())
        self.assertEqual((route["provider"], route["model"]), api.QWEN_ROUTE)
        self.assertEqual(route["routingMode"], "automatic")

    def test_explicit_model_route_overrides_specialist_match(self):
        route = api.route_task("Use Nemotron to review this portfolio", self.settings())
        self.assertEqual((route["provider"], route["model"]), api.NEMOTRON_ROUTE)
        self.assertEqual(route["routingMode"], "explicit")

    def test_explicit_codex_route_uses_chatgpt_subscription_model(self):
        route = api.route_task("Ask Codex to recommend the architecture", self.settings(codex=True))
        self.assertEqual((route["provider"], route["model"]), api.CODEX_ROUTE)
        self.assertEqual(route["routingMode"], "explicit")

    def test_architecture_rule_routes_to_codex_when_nemotron_is_default(self):
        route = api.route_task("Create the software architecture plan", self.settings(codex=True))
        self.assertEqual((route["provider"], route["model"]), api.CODEX_ROUTE)
        self.assertEqual(route["routingMode"], "automatic")

    def test_routing_rule_crud_is_atomic_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            model = {"provider": "openai-codex", "model": "gpt-5.6-sol", "configured": True}
            rule = {"name": "Architecture", "priority": 750, "scope": "nemotron-default", "provider": model["provider"], "model": model["model"], "triggers": ["architecture plan"], "enabled": True}
            with mock.patch.object(api, "ROUTING_RULES", path), mock.patch.object(api.legacy, "model_catalog", return_value=[model]), mock.patch.object(api.legacy, "audit"):
                added = api.update_routing_rules({"action": "add", "rule": rule})["rules"]
                created = next(row for row in added if row["name"] == "Architecture")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                with self.assertRaisesRegex(ValueError, "confirmation"):
                    api.update_routing_rules({"action": "delete", "id": created["id"]})
                result = api.update_routing_rules({"action": "delete", "id": created["id"], "confirm": f'delete-routing-rule-{created["id"]}'})
                self.assertFalse(any(row["id"] == created["id"] for row in result["rules"]))

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
