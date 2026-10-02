import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent


def load_installer():
    spec = importlib.util.spec_from_file_location("managed_skills", ROOT / "install-managed-skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManagedSkillTests(unittest.TestCase):
    def test_bundled_skills_validate(self):
        module = load_installer()
        rows = module.validate_tree(ROOT / "skills", len(module.BUNDLED_SKILLS), module.BUNDLED_SKILLS)
        self.assertEqual({row["name"] for row in rows}, {
            "bmc-headless-browser", "bmc-html5-kvm", "ipmi-redfish-bmc", "prime-nvidia-catalog", "lan-web-host",
        })

    def test_symlink_is_rejected(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "unsafe"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: unsafe\ndescription: test\n---\n")
            (skill / "link").symlink_to("SKILL.md")
            with self.assertRaises(ValueError):
                module.validate_tree(root)

    def test_inventory_publishes_installed_and_lazy_catalog_metadata(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            skill = state / "skills/example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: example\ndescription: Installed skill\n---\n")
            catalog = state / "catalogs/nvidia"
            catalog.mkdir(parents=True)
            (catalog / "manifest.json").write_text(json.dumps({"skills": [{"name": "cuda", "directory": "cuda", "description": "CUDA help"}]}))
            with mock.patch.object(module.pwd, "getpwnam", return_value=mock.Mock(pw_dir=str(root))), mock.patch.object(module.os, "chown"):
                module.publish_inventory("alice", state, 1000, 1000)
            rows = json.loads((root / ".prime/agent/skill-inventory.json").read_text())
            self.assertEqual([row["id"] for row in rows["skills"]], ["managed:example", "nvidia:cuda"])

    def test_power_mutations_are_confirmation_gated(self):
        source = (ROOT / "skills/ipmi-redfish-bmc/src/ipmi_redfish_bmc/__init__.py").read_text()
        self.assertIn("if not confirm:", source)
        self.assertIn("IPMI_PASSWORD", source)
        self.assertIn("class SOLSession", source)
        self.assertIn('"sol", "activate"', source)
        self.assertIn('"sol", "deactivate"', source)
        self.assertIn("pty.openpty()", source)
        self.assertIn("pyte.Screen", source)
        browser = (ROOT / "skills/bmc-headless-browser/src/bmc_headless_browser/__init__.py").read_text()
        self.assertIn("confirmed_click", browser)
        self.assertNotIn("apt-get", browser)
        self.assertNotIn("playwright install", browser)
        self.assertIn('TemporaryDirectory(prefix="prime-bmc-chromium-", dir="/tmp")', browser)
        self.assertIn("XDG_CONFIG_HOME", browser)
        self.assertIn('"--disable-gpu"', browser)
        self.assertIn('"--no-zygote"', browser)
        self.assertIn("subprocess.Popen", browser)
        self.assertIn("asyncio.to_thread", browser)
        self.assertIn("Browser step '{action}' timed out", browser)
        self.assertIn('"-m", "bmc_headless_browser", "--worker"', browser)
        self.assertIn("def _daemon_main", browser)
        self.assertIn("socket.AF_UNIX", browser)
        self.assertTrue((ROOT / "skills/bmc-headless-browser/src/bmc_headless_browser/__main__.py").is_file())

    def test_immutable_kernel_contains_managed_modules(self):
        containerfile = (ROOT.parent / "container/Containerfile").read_text()
        installer = (ROOT.parent / "openshell/install.sh").read_text()
        self.assertIn("COPY --chown=root:root managed-skills /opt/prime-managed-skills", containerfile)
        self.assertIn("playwright==1.63.0", containerfile)
        self.assertIn("pyte==0.8.2", containerfile)
        entrypoint = (ROOT.parent / "container/prime-container-entrypoint.sh").read_text()
        self.assertIn("bmc_headless_browser --daemon", entrypoint)
        self.assertIn("BMC_BROWSER_BROKER", entrypoint)
        self.assertIn("-name __pycache__", installer)
        self.assertIn("-name '*.pyc'", installer)
        self.assertIn('-type f -exec chmod 0644', installer)
        self.assertIn('-type d -exec chmod 0755', installer)
        for name in load_installer().BUNDLED_SKILLS:
            if name == 'lan-web-host':
                self.assertTrue((ROOT / 'skills/lan-web-host/scripts/prime_web_host.py').is_file())
                self.assertNotIn('/opt/prime-managed-skills/lan-web-host', containerfile)
                continue
            self.assertIn(f"/opt/prime-managed-skills/{name}", containerfile)
            self.assertIn("$repo/deploy/spark/prime/skills/$skill", installer)


if __name__ == "__main__":
    unittest.main()
