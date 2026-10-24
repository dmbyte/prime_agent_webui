"""Socket-level regressions: actual broker/client code, no BMC or gateway."""
import base64
import errno
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'container'))
sys.path.insert(0, str(ROOT/'prime/skills/bmc-html5-kvm/src'))
import kvm_broker
import bmc_html5_kvm as client


class KVMTransportTests(unittest.TestCase):
    def broker_reply(self, result, request=b'{"action":"capture"}\n', disconnect=False):
        broker = object.__new__(kvm_broker.KVMBroker)
        broker.dispatch = mock.Mock(return_value=result)
        sender, receiver = socket.socketpair()
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        receiver.settimeout(5)
        thread = threading.Thread(target=broker._client, args=(sender,), daemon=True)
        thread.start()
        try:
            receiver.sendall(request)
            try:
                receiver.shutdown(socket.SHUT_WR)
            except OSError as error:
                # A small reply may already have closed the peer on macOS.
                if error.errno != errno.ENOTCONN:
                    raise
            if disconnect:
                receiver.close()
                return b'', broker
            # Delay consuming so a single unbuffered write reliably comes up short.
            time.sleep(.02)
            chunks=[]
            while chunk := receiver.recv(8192):
                chunks.append(chunk)
                time.sleep(.0001)
            return b''.join(chunks), broker
        finally:
            receiver.close()
            thread.join(5)
            self.assertFalse(thread.is_alive(), 'Broker response handler did not finish')

    def test_large_jpeg_png_complete_under_backpressure(self):
        for kind,signature in [('jpeg',b'\xff\xd8'),('png',b'\x89PNG\r\n\x1a\n')]:
            with self.subTest(kind=kind):
                frame=signature+b'A'*(client.MAX_FRAME-len(signature))
                result={kind:base64.b64encode(frame).decode()}
                raw,_=self.broker_reply(result)
                self.assertTrue(raw.endswith(b'\n'))
                self.assertEqual(json.loads(raw),{'ok':True,'result':result})
                self.assertEqual(base64.b64decode(json.loads(raw)['result'][kind]),frame)

    def test_small_metadata_and_oversized_response(self):
        raw,_=self.broker_reply({'status':'ready'})
        self.assertEqual(json.loads(raw)['result']['status'],'ready')
        raw,_=self.broker_reply({'jpeg':'A'*3_500_000})
        self.assertFalse(json.loads(raw)['ok'])
        self.assertIn('exceeds limit',json.loads(raw)['error'])

    def test_disconnected_reader_does_not_poison_next_request(self):
        self.broker_reply({'jpeg':'A'*300000},disconnect=True)
        raw,_=self.broker_reply({'status':'ready'})
        self.assertTrue(json.loads(raw)['ok'])

    def test_unterminated_and_over_limit_requests_never_dispatch(self):
        for request in (b'{"action":"capture"}',b'A'*16_385+b'\n'):
            # Oversized requests can cause a reset when unread bytes remain.
            try:
                raw,broker=self.broker_reply({},request)
            except ConnectionResetError:
                continue
            self.assertFalse(raw)
            broker.dispatch.assert_not_called()

    def reply_server(self, raw, callback, chunked=False):
        with tempfile.TemporaryDirectory(dir='/tmp') as directory:
            path=Path(directory)/'kvm.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                listener.bind(str(path)); listener.listen(1); listener.settimeout(5)
                def serve():
                    connection,_=listener.accept()
                    with connection:
                        with connection.makefile('rb') as stream:
                            stream.readline(16_385)
                        try:
                            if chunked:
                                for offset in range(0,len(raw),157):
                                    connection.sendall(raw[offset:offset+157])
                            else:
                                connection.sendall(raw)
                        except (BrokenPipeError,ConnectionResetError):
                            pass
                thread=threading.Thread(target=serve,daemon=True); thread.start()
                try:
                    with mock.patch.dict('os.environ',{'PRIME_KVM_SOCKET':str(path)}):
                        return callback(path)
                finally:
                    thread.join(5)
                    self.assertFalse(thread.is_alive())

    def test_clients_accept_fragmented_complete_response(self):
        expected={'jpeg':'A'*300000}
        raw=json.dumps({'ok':True,'result':expected}).encode()+b'\n'
        for callback in (lambda path:client._broker({'action':'capture'}),
                         lambda path:kvm_broker._worker_call(path,'capture')):
            self.assertEqual(self.reply_server(raw,callback,True),expected)

    def test_clients_reject_eof_invalid_json_and_oversize_explicitly(self):
        for raw,message in [(b'{"ok":true,"result":{"jpeg":"abc','incomplete'),
                            (b'{bad}\n','invalid JSON'),(b'[]\n','invalid response object'),
                            (b'A'*3_500_001,'bound')]:
            for callback in (lambda path:client._broker({'action':'capture'}),
                             lambda path:kvm_broker._worker_call(path,'capture')):
                with self.subTest(message=message,callback=callback),self.assertRaisesRegex(RuntimeError,message):
                    self.reply_server(raw,callback)

    def test_failed_capture_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'frame.png'; target.write_bytes(b'existing frame')
            with mock.patch.dict('os.environ',{'PRIME_WORKSPACE':directory}):
                with self.assertRaisesRegex(RuntimeError,'incomplete'):
                    self.reply_server(b'{"ok":true,"result":{"png":"cut',
                        lambda path:client.KVMClient('a'*32).capture(target))
            self.assertEqual(target.read_bytes(),b'existing frame')
