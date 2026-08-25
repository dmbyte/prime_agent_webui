#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prime_dashboard_api_v2", Path(__file__).with_name("api_v2.py"))
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class DashboardV2Tests(unittest.TestCase):
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
