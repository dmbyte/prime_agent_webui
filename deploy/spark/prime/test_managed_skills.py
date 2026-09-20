import importlib.util
import tempfile
import unittest
from pathlib import Path


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
            "bmc-headless-browser", "ipmi-redfish-bmc", "prime-nvidia-catalog",
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

    def test_power_mutations_are_confirmation_gated(self):
        source = (ROOT / "skills/ipmi-redfish-bmc/src/ipmi_redfish_bmc/__init__.py").read_text()
        self.assertIn("if not confirm:", source)
        self.assertIn("IPMI_PASSWORD", source)
        browser = (ROOT / "skills/bmc-headless-browser/src/bmc_headless_browser/__init__.py").read_text()
        self.assertIn("confirmed_click", browser)
        self.assertNotIn("apt-get", browser)
        self.assertNotIn("playwright install", browser)

    def test_immutable_kernel_contains_managed_modules(self):
        containerfile = (ROOT.parent / "container/Containerfile").read_text()
        installer = (ROOT.parent / "openshell/install.sh").read_text()
        self.assertIn("COPY --chown=root:root managed-skills /opt/prime-managed-skills", containerfile)
        self.assertIn("playwright==1.63.0", containerfile)
        for name in load_installer().BUNDLED_SKILLS:
            self.assertIn(f"/opt/prime-managed-skills/{name}", containerfile)
            self.assertIn("$repo/deploy/spark/prime/skills/$skill", installer)


if __name__ == "__main__":
    unittest.main()
