"""Root resource observations keep their exact scope without Docker CLI startup."""
import io
import json
import struct
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import receipts, resource_exec, workspace

GOOD = {"store_main_logical_bytes": 8192, "store_main_allocated_bytes": 12288,
        "oom": 0, "oom_kill": 0, "swap_current": 0}


class RootGuardTransport(unittest.TestCase):
    def test_one_exact_guard_keeps_its_receipt_without_docker_cli_launch(self):
        launches = []
        peer = Peer(replies())
        def launch(argv, **options):
            launches.append(argv)
            raise AssertionError('no host helper child may be launched')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(receipts.subprocess, "Popen", side_effect=launch), \
                    patch.object(resource_exec.socket, "socket", side_effect=peer.socket):
                row = workspace.ordinary_resource_guard(
                    SimpleNamespace(container=CONTAINER),
                    {"socket": "/exact-sealed-socket"}, output, "guard", GOOD, seconds=3)
            self.assertEqual({key: row[key] for key in GOOD}, GOOD)
            completion = json.loads((output/"guard.completion.json").read_text())
            self.assertEqual((completion["status"], completion["attempts"], completion["exit_code"]),
                             ("PASS", 1, 0))
            custody = json.loads((output/"guard.host-custody.json").read_text())
            self.assertIsNone(custody["host_pid"])
            self.assertIsNone(custody["host_group"])
            self.assertEqual(completion["argv"], ["python3", "-B", "-c", resource_exec.BODY])
            self.assertIsNone(completion["cwd"])
        self.assertEqual(len(peer.wires), 3)
        self.assertEqual(len(launches), 0,
                         "same1000 observations must not start1000 host helper processes")


CONTAINER = "a" * 64
EXEC = "b" * 64


def response(status, body):
    return (f"HTTP/1.1 {status} response\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n").encode()+body


def frame(kind, data, length=None):
    return bytes([kind, 0, 0, 0])+struct.pack(">I", len(data) if length is None else length)+data


def upgrade(data):
    return b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n"+data


def replies(stream=None, inspected=None):
    terminal = {"ID": EXEC, "ContainerID": CONTAINER, "Running": False, "ExitCode": 0}
    if inspected:
        terminal.update(inspected)
    return [response(201, json.dumps({"Id": EXEC}).encode()),
            upgrade(frame(1, json.dumps(GOOD).encode()) if stream is None else stream),
            response(200, json.dumps(terminal).encode())]


class Peer:
    def __init__(self, answers, fragment=None, clock=None, slow=None):
        self.answers, self.fragment, self.clock, self.slow = answers, fragment, clock, slow
        self.wires = []
    def socket(self, *args):
        index = len(self.wires)
        if index >= len(self.answers):
            raise AssertionError("unexpected retry or later Engine request")
        peer = self
        class Wire:
            closed = False
            def __init__(self):
                self.data = bytearray(peer.answers[index])
            def settimeout(self, value):
                self.timeout = value
            def connect(self, path):
                self.path = path
            def sendall(self, data):
                self.sent = data
            def recv_into(self, output):
                if peer.clock is not None and index == peer.slow:
                    peer.clock[0] += .4
                size = min(len(output), len(self.data), peer.fragment or len(output))
                output[:size] = self.data[:size]
                del self.data[:size]
                return size
            def close(self):
                self.closed = True
        wire = Wire(); self.wires.append(wire)
        return wire


class EngineGuardProtocol(unittest.TestCase):
    def run_peer(self, peer, seconds=3):
        out, err = io.BytesIO(), io.BytesIO()
        with patch.object(resource_exec.socket, "socket", side_effect=peer.socket):
            resource_exec.execute("/exact-sealed-socket", CONTAINER, seconds, out, err)
        return out.getvalue(), err.getvalue()

    def test_exact_root_three_requests_and_http_read_ahead(self):
        # The fixed script is also pinned independently in the campaign receipt.
        import hashlib
        self.assertEqual(hashlib.sha256(resource_exec.BODY.encode()).hexdigest(),
                         "22175c00865dd7386dd95d66bf04a7871bcc02a63d26c9e975b60a76f616e966")
        peer = Peer(replies(frame(1, b"first")+frame(2, b"error")+frame(1, b"")+frame(1, b"last")))
        out, err = self.run_peer(peer)
        self.assertEqual((out, err), (b"firstlast", b"error"))
        self.assertEqual(len(peer.wires), 3)
        self.assertTrue(all(w.closed and w.path == "/exact-sealed-socket" for w in peer.wires))
        expected = [f"POST /v1.54/containers/{CONTAINER}/exec",
                    f"POST /v1.54/exec/{EXEC}/start", f"GET /v1.54/exec/{EXEC}/json"]
        for wire, prefix in zip(peer.wires, expected):
            self.assertTrue(wire.sent.startswith((prefix+" HTTP/1.1\r\n").encode()))
        created = json.loads(peer.wires[0].sent.partition(b"\r\n\r\n")[2])
        self.assertEqual(created, {"User":"0:0", "Cmd":["python3","-B","-c",resource_exec.BODY],
            "AttachStdout":True,"AttachStderr":True,"AttachStdin":False,"Tty":False,"Privileged":False})

    def test_single_byte_fragmentation_preserves_stdout_and_inspection(self):
        peer = Peer(replies(), fragment=1)
        out, err = self.run_peer(peer)
        self.assertEqual(json.loads(out), GOOD)
        self.assertEqual(err, b"")
        self.assertEqual(len(peer.wires), 3)

    def test_terminal_identity_exit_and_duplicate_json_refusals_do_not_retry(self):
        for changed in ({"Running":True}, {"ExitCode":None}, {"ExitCode":True},
                        {"ExitCode":3}, {"ID":"c"*64}, {"ContainerID":"c"*64}):
            with self.subTest(changed=changed):
                peer = Peer(replies(inspected=changed))
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_peer(peer)
                self.assertEqual(len(peer.wires), 3)
                self.assertTrue(all(w.closed for w in peer.wires))
        peer = Peer([response(201, ('{"Id":"'+EXEC+'","Id":"'+EXEC+'"}').encode())])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.run_peer(peer)
        self.assertEqual(len(peer.wires), 1)

    def test_bad_headers_partial_payload_and_system_errors_never_inspect(self):
        broken = [b"\1", frame(1,b"short",100), frame(1,b"short",2**32-1),
                  b"\1\1\0\0"+struct.pack(">I",0), frame(0,b"bad"), frame(3,b"engine refused")]
        for data in broken:
            with self.subTest(data=data):
                peer = Peer(replies(stream=data))
                with self.assertRaises((ValueError, EOFError, RuntimeError)):
                    self.run_peer(peer)
                self.assertEqual(len(peer.wires), 2)
                self.assertTrue(all(w.closed for w in peer.wires))

    def test_wrong_create_status_and_non_upgrade_fail_without_replay(self):
        variants = [(response(500,b"{}"),1), (response(201,b"[]"),1)]
        for answer, calls in variants:
            peer = Peer([answer])
            with self.assertRaises(ValueError):
                self.run_peer(peer)
            self.assertEqual(len(peer.wires), calls)
        answers = replies(); answers[1] = response(200,b"ignored")
        peer = Peer(answers)
        with self.assertRaisesRegex(ValueError, "upgrade"):
            self.run_peer(peer)
        self.assertEqual(len(peer.wires), 2)

    def test_absolute_deadline_checks_each_socket_read_even_slow_http_lines(self):
        for stage in range(3):
            clock = [0.0]
            peer = Peer(replies(), fragment=1, clock=clock, slow=stage)
            with self.subTest(stage=stage), patch.object(resource_exec.time,"monotonic",side_effect=lambda:clock[0]):
                with self.assertRaises(TimeoutError):
                    self.run_peer(peer,seconds=1)
            self.assertEqual(len(peer.wires), stage+1)
            self.assertTrue(all(w.closed for w in peer.wires))

    def test_output_failure_preserves_partial_bytes_and_original_error(self):
        class Refused(io.BytesIO):
            def write(self, data):
                super().write(data[:2])
                raise OSError("original output refusal")
        out, err = Refused(), io.BytesIO(); peer = Peer(replies())
        with patch.object(resource_exec.socket,"socket",side_effect=peer.socket):
            with self.assertRaisesRegex(OSError,"original output refusal"):
                resource_exec.execute("/exact-sealed-socket",CONTAINER,3,out,err)
        self.assertEqual(out.getvalue(), b"{\"")
        self.assertIn(EXEC.encode(), err.getvalue())
        self.assertEqual(len(peer.wires),2)

    def test_short_output_write_refuses_without_replay_or_inspection(self):
        class Short(io.BytesIO):
            def write(self, data):
                return super().write(data[:2])
        out, err = Short(), io.BytesIO(); peer = Peer(replies())
        with patch.object(resource_exec.socket,"socket",side_effect=peer.socket):
            with self.assertRaisesRegex(OSError,"short guard Engine output write"):
                resource_exec.execute("/exact-sealed-socket",CONTAINER,3,out,err)
        self.assertEqual(out.getvalue(), b"{\"")
        self.assertIn(EXEC.encode(), err.getvalue())
        self.assertEqual(len(peer.wires),2)


class DirectGuardEvidence(unittest.TestCase):
    def call(self, peer, output, seconds=3):
        with patch.object(resource_exec.socket, 'socket', side_effect=peer.socket):
            return resource_exec.command('/exact-sealed-socket', CONTAINER, output, 'guard', seconds)

    def test_one_and_four_guards_have_equal_three_request_cost_and_zero_host_starts(self):
        for count in (1,4):
            peer=Peer(replies()*count)
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(resource_exec.socket,'socket',side_effect=peer.socket), \
                    patch.object(receipts.subprocess,'Popen',side_effect=AssertionError('host child forbidden')):
                output=Path(temporary)
                for index in range(count):
                    row=workspace.ordinary_resource_guard(SimpleNamespace(container=CONTAINER),
                        {'socket':'/exact-sealed-socket'},output,f'guard-{index}',GOOD,seconds=3)
                    self.assertEqual({key:row[key] for key in GOOD},GOOD)
                    completion=json.loads((output/f'guard-{index}.completion.json').read_text())
                    self.assertEqual((completion['status'],completion['attempts'],completion['exit_code']),('PASS',1,0))
            self.assertEqual(len(peer.wires),3*count)

    def test_known_nonzero_and_unknown_failure_keep_original_terminal_custody(self):
        for peer, expected, kind in ((Peer(replies(inspected={'ExitCode':7})),7,RuntimeError),
                                      (Peer(replies(stream=frame(1,b'short',100))),None,EOFError)):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)
                with self.assertRaises(kind): self.call(peer, output)
                row=json.loads((output/'guard.completion.json').read_text())
                self.assertEqual((row['status'],row['exit_code']),('FAIL',expected))
                self.assertIn(EXEC,(output/'guard.stderr').read_text())
                self.assertEqual(len(peer.wires),3 if expected else 2)

    def test_evidence_setup_is_inside_same_deadline_before_any_remote_request(self):
        clock=[0.0]; original=receipts.write_new; peer=Peer(replies())
        def slow_write(path,value):
            original(path,value)
            if str(path).endswith('.attempt.json'): clock[0]=2
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(resource_exec.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(receipts,'write_new',side_effect=slow_write):
            output=Path(temporary)
            with self.assertRaises(TimeoutError): self.call(peer,output,seconds=1)
            row=json.loads((output/'guard.completion.json').read_text())
            self.assertEqual((row['status'],row['exit_code'],row['timeout']),('FAIL',None,True))
        self.assertEqual(len(peer.wires),0)

    def test_same_deadline_at_all_three_exchanges_stops_without_later_inspection(self):
        for stage in range(3):
            clock=[0.0]; peer=Peer(replies(),fragment=1,clock=clock,slow=stage)
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(resource_exec.time,'monotonic',side_effect=lambda:clock[0]):
                output=Path(temporary)
                with self.assertRaises(TimeoutError): self.call(peer,output,seconds=1)
                self.assertEqual(json.loads((output/'guard.completion.json').read_text())['status'],'FAIL')
            self.assertEqual(len(peer.wires),stage+1)

    def test_late_completion_write_preserves_attempt_and_refuses_success(self):
        clock=[0.0]; original=receipts.write_new; peer=Peer(replies())
        def slow_write(path,value):
            original(path,value)
            if str(path).endswith('.completion.attempt.json'): clock[0]=2
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(resource_exec.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(receipts,'write_new',side_effect=slow_write):
            output=Path(temporary)
            with self.assertRaises(TimeoutError): self.call(peer,output,seconds=1)
            attempted=json.loads((output/'guard.completion.attempt.json').read_text())
            completed=json.loads((output/'guard.completion.json').read_text())
            self.assertEqual((attempted['status'],completed['status'],completed['exit_code']),('PASS','FAIL',0))
        self.assertEqual(len(peer.wires),3)

    def test_late_success_link_is_revoked_only_when_created_by_this_attempt(self):
        clock=[0.0]; original=resource_exec.os.link; peer=Peer(replies())
        def slow_link(source,target): original(source,target); clock[0]=2
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(resource_exec.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(resource_exec.os,'link',side_effect=slow_link):
            output=Path(temporary)
            with self.assertRaises(TimeoutError): self.call(peer,output,seconds=1)
            self.assertEqual(json.loads((output/'guard.completion.json').read_text())['status'],'FAIL')
            self.assertTrue((output/'guard.completion.attempt.json').is_file())

    def test_output_close_failure_preserves_known_exit_and_original_io_error(self):
        original=Path.open; peer=Peer(replies())
        class CloseFailure:
            def __init__(self,stream): self.stream=stream
            def write(self,data): return self.stream.write(data)
            def flush(self): return self.stream.flush()
            def close(self): self.stream.close(); raise OSError('original output close failure')
        def opened(path,*args,**kwargs):
            stream=original(path,*args,**kwargs)
            return CloseFailure(stream) if str(path).endswith('.stdout') and args==('xb',) else stream
        with tempfile.TemporaryDirectory() as temporary, patch.object(Path,'open',opened):
            output=Path(temporary)
            with self.assertRaisesRegex(OSError,'original output close failure'): self.call(peer,output)
            row=json.loads((output/'guard.completion.json').read_text())
            self.assertEqual((row['status'],row['exit_code']),('FAIL',0))
        self.assertEqual(len(peer.wires),3)

    def test_receipt_write_failure_does_not_replace_original_stream_error(self):
        original=receipts.write_new; peer=Peer(replies(stream=frame(1,b'short',100)))
        def refused(path,value):
            if str(path).endswith('.completion.json'): raise OSError('independent receipt refusal')
            original(path,value)
        with tempfile.TemporaryDirectory() as temporary, patch.object(receipts,'write_new',side_effect=refused):
            with self.assertRaises(EOFError) as caught: self.call(peer,Path(temporary))
            self.assertIsInstance(caught.exception.independent_receipt_failure,OSError)
        self.assertEqual(len(peer.wires),2)


if __name__ == "__main__":
    unittest.main()
