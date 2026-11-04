"""Client contract and non-replay behavior; transport never holds approval authority."""
import base64
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent/'skills/bmc-html5-kvm/src'))
import bmc_html5_kvm as client

CONNECTION = 'c_'+'a'*32
SESSION = 'pc-'+'b'*16
NONCE = 'c'*32


class PrivateKVMTests(unittest.TestCase):
    def test_installer_restarts_legacy_broker_after_idle_checks(self):
        source = (Path(__file__).parents[1]/'openshell/install.sh').read_text()
        self.assertIn('sudo systemctl restart prime-kvm-broker.service', source)
        self.assertLess(source.index('Active KVM session:'), source.index('sudo systemctl restart prime-kvm-broker.service'))

    def setUp(self):
        self.kvm = client.PrivateKVMClient(CONNECTION, SESSION)

    def test_open_and_list_are_typed_and_bound_to_connection(self):
        with mock.patch.object(client, '_connection_call', return_value={'sessionId':SESSION}) as call:
            opened = client.PrivateKVMClient.open(CONNECTION, request_id=NONCE)
            self.assertEqual(opened.session_id, SESSION)
            call.assert_called_once_with('call', connection=CONNECTION, operation='kvm.open', arguments={'requestId':NONCE})
        with mock.patch.object(client, '_connection_call', return_value={'connections':[{'id':CONNECTION,'operations':['kvm.open']},{'operations':['ipmi.status']}] }):
            self.assertEqual(len(client.PrivateKVMClient.connections()), 1)
        with self.assertRaises(ValueError): client.PrivateKVMClient.open('https://target/', request_id=NONCE)

    def test_approval_returned_without_auto_poll_or_dispatch(self):
        pending = {'approvalRequired':True,'approvalId':'a_'+'a'*64}
        with mock.patch.object(client, '_connection_call', return_value=pending) as call:
            self.assertEqual(self.kvm.input(request_id=NONCE, key='f9'), pending)
            call.assert_called_once_with('call', connection=CONNECTION, operation='kvm.input',
                arguments={'sessionId':SESSION,'requestId':NONCE,'key':'f9'})

    def test_timeout_unknown_or_malformed_never_retried(self):
        with mock.patch.object(client, '_connection_call', side_effect=TimeoutError('synthetic')) as call:
            with self.assertRaises(TimeoutError): self.kvm.input(request_id=NONCE, key='f9')
            call.assert_called_once()
        for result in ({'actionReceipt':{'state':'unknown'}}, {'actionReceipt':{'state':'acknowledged'}}):
            with mock.patch.object(client, '_connection_call', return_value=result) as call:
                self.assertEqual(self.kvm.input(request_id=NONCE, key='f9'), result)
                call.assert_called_once()
        with mock.patch.object(client, '_connection_call', return_value={'sent':True}) as call:
            with self.assertRaisesRegex(ValueError,'do not repeat'): self.kvm.input(request_id=NONCE,key='f9')
            call.assert_called_once()

    def test_invalid_input_never_contacts_broker(self):
        with mock.patch.object(client, '_connection_call') as call:
            for kwargs in ({'key':'F9'}, {'key':'f9','text':'a'}, {'text':'~.'}, {'text':'a\n'}, {'text':''}, {'key':['f9']}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.kvm.input(request_id=NONCE, **kwargs)
            with self.assertRaises(ValueError): self.kvm.input(request_id='new',key='f9')
            call.assert_not_called()

    def test_receipt_lookup_does_not_need_or_recreate_session(self):
        with mock.patch.object(client, '_connection_call', return_value={'actionReceipt':{'state':'unknown'}}) as call:
            client.PrivateKVMClient.action_receipt(CONNECTION, NONCE)
            call.assert_called_once_with('call', connection=CONNECTION, operation='kvm.receipt', arguments={'requestId':NONCE})

    def test_capture_checks_png_and_workspace_before_writing(self):
        png = b'\x89PNG\r\n\x1a\nfixture'
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'PRIME_WORKSPACE':directory}):
            with mock.patch.object(client, '_connection_call', return_value={'image':base64.b64encode(png).decode(),'mimeType':'image/png'}) as call:
                self.assertEqual(self.kvm.capture().read_bytes(), png)
                with self.assertRaises(ValueError): self.kvm.capture('/outside.png')
                with self.assertRaises(ValueError): self.kvm.capture('console.jpg')
                call.assert_called_once()
            with mock.patch.object(client, '_connection_call', return_value={'image':'bad','mimeType':'text/plain'}):
                with self.assertRaises(ValueError): self.kvm.capture()
                self.assertEqual((Path(directory)/'kvm-frame.png').read_bytes(), png)

    def test_legacy_client_cannot_send_confirmed_inputs(self):
        old = client.KVMClient('a'*32)
        with mock.patch.object(client, '_broker') as call:
            for invoke in (lambda:old.key('F9',confirm=True), lambda:old.click('canvas',confirm=True),
                           lambda:old.fill('#password','not-sent',confirm=True), lambda:old.type_text('x',confirm=True),
                           lambda:old.focus_console(confirm=True)):
                with self.assertRaises(PermissionError): invoke()
            call.assert_not_called()

    def test_transport_no_token_redirect_proxy_or_error_echo(self):
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_TOKEN':''}), mock.patch.object(client.urllib.request,'build_opener') as build:
            with self.assertRaises(PermissionError): client.PrivateKVMClient.connections()
            build.assert_not_called()
        with self.assertRaises(PermissionError): client._NoRedirect().redirect_request(None)
        token = 'a'*32+'.'+'b'*64
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_TOKEN':token}), mock.patch.object(client.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect = OSError('SECRET')
            with self.assertRaisesRegex(RuntimeError, 'original request ID') as error: client.PrivateKVMClient.connections()
            self.assertNotIn('SECRET', str(error.exception))
            self.assertEqual(build.call_args.args[0].proxies, {})
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:31000/connections')
            build.return_value.open.assert_called_once()
