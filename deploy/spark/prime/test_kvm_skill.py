"""Boundaries for the reconnectable HTML5 KVM client and broker."""

import base64
import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
CONTAINER = ROOT.parent / "container"
sys.path.insert(0, str(CONTAINER))
sys.path.insert(0, str(ROOT / "skills/bmc-html5-kvm/src"))

import bmc_html5_kvm as client


def load_broker():
    spec = importlib.util.spec_from_file_location("kvm_broker_test", CONTAINER / "kvm_broker.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class KVMTests(unittest.TestCase):
    def test_viewer_sampling_never_extends_idle_timeout_or_sends_input(self):
        broker = load_broker()
        with tempfile.TemporaryDirectory() as directory:
            service = broker.KVMBroker('alice', Path(directory))
            session = broker.Session('a'*32, 'https://bmc.example/', {'workerSocket':Path(directory)/'worker.sock'})
            session.feed = mock.Mock()
            session.feed.watched.return_value = True
            service.sessions[session.session_id] = session
            before = session.last_used
            service.stopping = mock.Mock()
            service.stopping.wait.side_effect = [False, True]
            with mock.patch.object(broker, '_worker_call', return_value={'jpeg':base64.b64encode(b'\xff\xd8frame').decode()}) as call:
                service.observe()
            self.assertEqual(session.last_used, before)
            self.assertEqual(call.call_args.args[1], 'capture')
            self.assertEqual(call.call_args.kwargs, {'timeout':3,'format':'jpeg','viewer':True})

    def test_page_routes_and_safe_https_upgrade(self):
        self.assertEqual(client._page_origin("https://bmc.example:443/page?view=console#screen"), client._page_origin("https://bmc.example/"))
        self.assertTrue(client._allowed_initial_redirect("http://bmc.example/", "https://bmc.example/login?next=console"))
        self.assertFalse(client._allowed_initial_redirect("https://bmc.example/", "http://bmc.example/"))
        self.assertFalse(client._allowed_initial_redirect("https://bmc.example/", "https://other.example/"))
        with self.assertRaises(ValueError): client._origin("https://bmc.example/?secret=value")

    def test_png_default_is_in_workspace_and_keeps_path_boundary(self):
        kvm = client.KVMClient("a" * 32)
        png=b"\x89PNG\r\n\x1a\nfixture"
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict("os.environ", {"PRIME_WORKSPACE": ""}):
            with mock.patch.dict("os.environ", {"PRIME_WORKSPACE": directory}):
                with mock.patch.object(client, "_broker", return_value={"png":base64.b64encode(png).decode()}) as call:
                    target=kvm.capture()
                    self.assertEqual(target, Path(directory).resolve()/"kvm-frame.png")
                    self.assertEqual(target.read_bytes(),png)
                    self.assertEqual(call.call_args.args[0]["format"],"png")
                with self.assertRaises(ValueError): kvm.capture("/wrong-location.png")

    def test_console_focus_rejects_management_page(self):
        frame=mock.Mock()
        frame.evaluate.return_value=False
        with self.assertRaisesRegex(ValueError,"No focused graphical console"):
            client._require_console_focus(frame)
        with self.assertRaises(PermissionError): client.KVMClient("a"*32).focus_console()

    def test_frame_discovery_returns_selector_and_frame_without_form_values(self):
        frame=mock.Mock(url="https://bmc.example/console?view=html5")
        details={"loginFormPresent":False,"legacyPluginPresent":False,
                 "controls":[{"tag":"canvas","selector":"#screen","width":800,"height":500}]}
        with mock.patch.object(client,"_inspect_frame",return_value=details):
            row=client._frame_info(frame,1,client._page_origin("https://bmc.example/"))
        self.assertEqual(row["consoleSurfaces"],[{"frameIndex":1,"selector":"#screen","tag":"canvas","width":800,"height":500}])
        self.assertNotIn("?",row["url"])

    def test_frame_discovery_does_not_inspect_other_origins_or_fail_on_detach(self):
        frame=mock.Mock(url="https://other.example/console")
        origin=client._page_origin("https://bmc.example/")
        with mock.patch.object(client,"_inspect_frame") as inspect:
            self.assertFalse(client._frame_info(frame,1,origin)["readable"])
            inspect.assert_not_called()
        frame.url="https://bmc.example/console"
        with mock.patch.object(client,"_inspect_frame",side_effect=RuntimeError("detached")):
            self.assertFalse(client._frame_info(frame,1,origin)["readable"])

    def test_repeated_create_reuses_target_without_opening_or_reloading(self):
        broker = load_broker()
        with tempfile.TemporaryDirectory() as directory:
            service = broker.KVMBroker("alice", Path(directory))
            session = broker.Session("d" * 32, "https://bmc.example/", {}, True)
            service.sessions[session.session_id] = session
            with mock.patch.object(broker, "sandbox_spec") as create:
                result = service._new_session("https://bmc.example/another-ui-path", True)
                self.assertEqual(result["sessionId"], session.session_id)
                self.assertTrue(result["reused"])
                create.assert_not_called()

    def test_redfish_urls_rejected_before_creating_any_session(self):
        broker = load_broker()
        service = broker.KVMBroker("alice")
        with mock.patch.object(broker, "sandbox_spec") as create:
            for url in ("https://bmc.example/redfish/v1/", "https://bmc.example/%72edfish/v1"):
                with self.assertRaisesRegex(ValueError, "Redfish is an API"):
                    service._new_session(url, False)
            create.assert_not_called()

    def test_missing_control_socket_reports_mount_problem(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict("os.environ", {"PRIME_KVM_SOCKET": str(Path(directory) / "missing.sock")}):
                with self.assertRaisesRegex(RuntimeError, "KVM control socket is missing.*task socket mount"):
                    client.KVMClient.list_sessions()

    def test_client_rejects_unconfirmed_input_and_outside_frames(self):
        with self.assertRaises(ValueError):
            client.KVMClient.create("https://name:secret@bmc.example/")
        kvm = client.KVMClient("a" * 32)
        for action in (lambda: kvm.fill("#name", "secret"),
                       lambda: kvm.click("canvas"), lambda: kvm.key("F9"),
                       lambda: kvm.type_text("boot")):
            with self.assertRaises(PermissionError):
                action()
        with self.assertRaises(ValueError):
            kvm.key("Control+Alt+Delete", confirm=True)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict("os.environ", {"PRIME_WORKSPACE": directory}):
                with self.assertRaises(ValueError):
                    kvm.capture("/tmp/outside.jpg")
                jpeg = b"\xff\xd8frame\xff\xd9"
                with mock.patch.object(client, "_broker", return_value={"jpeg": base64.b64encode(jpeg).decode()}):
                    target = kvm.capture(str(Path(directory) / "frame.jpg"))
                    self.assertEqual(target.read_bytes(), jpeg)
                    self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_sandbox_spec_is_owner_lan_only_and_bounded(self):
        broker = load_broker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "images.json"
            manifest.write_text(json.dumps({"network-operations": {"image":
                "local/prime-openshell-network-operations:0.9.5-" + "a" * 12}}))
            spec = broker.sandbox_spec("dbyte", "b" * 32, manifest, root / "policy")
            policy = spec["policy"].read_text()
            create = spec["create"]
            self.assertIn("/dev/shm", policy)
            self.assertNotIn("/dev/pts", policy)
            self.assertIn("prime-dbyte-gateway-lan", " ".join(create))
            self.assertIn("prime-dbyte-kvm", " ".join(create))
            self.assertNotIn("prime-dbyte-workspace", " ".join(create))
            self.assertIn("2Gi", create)
            self.assertIn("prime.kvm=true", create)
            self.assertIn("--server", " ".join(spec["launch"]))

    def test_broker_authorizes_each_input_and_expires_idle_sessions(self):
        broker = load_broker()
        with tempfile.TemporaryDirectory() as directory:
            service = broker.KVMBroker("dbyte", Path(directory))
            session = mock.Mock()
            session.session_id = "c" * 32
            session.target = "https://bmc.example/"
            session.created = time.monotonic() - 10
            session.last_used = time.monotonic()
            service.sessions[session.session_id] = session
            with self.assertRaises(PermissionError):
                service.dispatch({"action": "key", "sessionId": session.session_id, "key": "F9"})
            session.call.assert_not_called()
            service.dispatch({"action": "key", "sessionId": session.session_id,
                              "key": "F9", "confirm": True})
            session.call.assert_called_once_with("key", key="F9", confirm=True)
            session.last_used = time.monotonic() - broker.IDLE - 1
            service.expire()
            session.close.assert_called_once()
            self.assertEqual(service.sessions, {})

    def test_restart_cleanup_reads_paged_inventory_before_deleting_only_owned_kvm(self):
        broker = load_broker()
        with tempfile.TemporaryDirectory() as directory:
            service = broker.KVMBroker("alice", Path(directory))
            owned = {"name": "pk-" + "a" * 16,
                     "labels": {"prime.kvm": "true", "prime.owner": "alice"}}
            other = {"name": "pk-" + "b" * 16,
                     "labels": {"prime.kvm": "true", "prime.owner": "bob"}}
            task = {"name": "pt-" + "c" * 16, "labels": {"prime.owner": "alice"}}
            results = [mock.Mock(stdout=json.dumps({"sandboxes": [other, task], "next_page_token": "page2"})),
                       mock.Mock(stdout=json.dumps({"sandboxes": [owned], "next_page_token": ""})),
                       mock.Mock(returncode=0)]
            with mock.patch.object(broker.subprocess, "run", side_effect=results) as run:
                service._cleanup_stale()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("--page-token", commands[1])
            self.assertEqual(commands[1][-1], "page2")
            self.assertEqual(commands[2][-3:], ["sandbox", "delete", owned["name"]])

    def test_url_validation_and_skill_metadata(self):
        broker = load_broker()
        for target in ("file:///etc/passwd", "https://u:p@bmc.example", "https://bmc.example/#fragment"):
            with self.assertRaises(ValueError):
                broker.validate_url(target)
        self.assertEqual(broker.validate_url("https://bmc.example/"), "https://bmc.example/")
        text = (ROOT / "skills/bmc-html5-kvm/SKILL.md").read_text()
        self.assertIn("name: bmc-html5-kvm", text)
        self.assertIn("HPE iLO 5", text)
        self.assertIn("eight hours", text)


if __name__ == "__main__":
    unittest.main()
