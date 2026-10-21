"""Same root resource observer over Engine Exec; no product Exec admission change."""
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import time

from engine import receipts

BODY = """import json
from pathlib import Path
store=Path('/layerfs-store/global/store.sqlite').stat()
events=dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
print(json.dumps({'store_main_logical_bytes':store.st_size,'store_main_allocated_bytes':store.st_blocks*512,
 'oom':int(events['oom']),'oom_kill':int(events['oom_kill']),
 'swap_current':int(Path('/sys/fs/cgroup/memory.swap.current').read_text())}))
"""
PREFIX = '/v1.54'  # Same negotiated profile as the retained Sandbox transport.
WINDOW = 8192


def unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate Engine JSON key: ' + key)
        output[key] = value
    return output


class Deadline:
    def __init__(self, seconds):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('original guard allowance unavailable')
        self.stop = time.monotonic() + seconds

    def left(self):
        remaining = self.stop - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('original resource guard absolute deadline')
        return remaining


class Reads(io.RawIOBase):
    def __init__(self, wire, deadline):
        super().__init__()
        self.wire, self.deadline = wire, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.wire.settimeout(self.deadline.left())
        return self.wire.recv_into(buffer)


class BufferedSocket:
    def __init__(self, wire, deadline):
        self.reader = io.BufferedReader(Reads(wire, deadline), WINDOW)

    def makefile(self, mode):
        if mode != 'rb':
            raise ValueError('guard HTTP reader mode')
        return self.reader


class Exchange:
    def __init__(self, path, deadline, method, route, body=None, upgrade=False):
        self.wire = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.response = None
        try:
            self.wire.settimeout(deadline.left())
            self.wire.connect(path)
            data = b'' if body is None else json.dumps(body, separators=(',', ':')).encode()
            connection = 'Upgrade\r\nUpgrade: tcp' if upgrade else 'close'
            head = (f'{method} {PREFIX}{route} HTTP/1.1\r\nHost: localhost\r\n'
                    f'Content-Type: application/json\r\nContent-Length: {len(data)}\r\n'
                    f'Connection: {connection}\r\n\r\n').encode()
            self.wire.settimeout(deadline.left())
            self.wire.sendall(head + data)
            self.response = http.client.HTTPResponse(BufferedSocket(self.wire, deadline))
            self.response.begin()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.response is not None:
            self.response.close()
        self.wire.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def json(self, status):
        if self.response.status != status:
            raise ValueError(f'guard Engine HTTP status {self.response.status}, expected {status}')
        # Engine identity/status responses are small; stream output is handled separately.
        data = self.response.read(65537)
        if len(data) > 65536:
            raise ValueError('guard Engine status response exceeds bounded identity window')
        value = json.loads(data, object_pairs_hook=unique_object)
        if not isinstance(value, dict):
            raise ValueError('guard Engine top-level object unavailable')
        return value


def exact(reader, length):
    output = bytearray()
    while len(output) < length:
        fragment = reader.read(length - len(output))
        if not fragment:
            raise EOFError('truncated guard Engine frame')
        output.extend(fragment)
    return bytes(output)


def streams(response, deadline, stdout, stderr):
    if response.status != 101 or response.getheader('Upgrade', '').lower() != 'tcp':
        raise ValueError('guard Engine attached upgrade unavailable')
    # HTTPResponse.read() treats101 as zero-length. Its fp retains HTTP read-ahead.
    reader = response.fp
    while True:
        deadline.left()
        first = reader.read(1)
        if not first:
            return
        header = first + exact(reader, 7)
        kind, reserved, remaining = header[0], header[1:4], struct.unpack('>I', header[4:])[0]
        if reserved != b'\0\0\0' or kind not in (1, 2, 3):
            raise ValueError('invalid guard Engine frame header')
        target = stderr if kind in (2, 3) else stdout
        while remaining:
            deadline.left()
            data = reader.read(min(remaining, WINDOW))
            if not data:
                raise EOFError('truncated guard Engine payload')
            written = target.write(data)
            if written != len(data):
                raise OSError('short guard Engine output write')
            target.flush()
            remaining -= len(data)
        if kind == 3:
            raise RuntimeError('guard Engine system-error stream')


def execute(path, container, seconds, stdout, stderr, *, deadline=None):
    if not re.fullmatch('[0-9a-f]{64}', container):
        raise ValueError('exact owned guard container ID required')
    deadline = Deadline(seconds) if deadline is None else deadline
    acknowledged = None
    terminal_exit = None
    try:
        body = {'User': '0:0', 'Cmd': ['python3', '-B', '-c', BODY],
                'AttachStdout': True, 'AttachStderr': True, 'AttachStdin': False,
                'Tty': False, 'Privileged': False}
        with Exchange(path, deadline, 'POST', f'/containers/{container}/exec', body) as response:
            acknowledged = response.json(201).get('Id')
            if not isinstance(acknowledged, str) or not re.fullmatch('[0-9a-f]{64}', acknowledged):
                raise ValueError('guard Engine Exec acknowledgement unavailable')
        with Exchange(path, deadline, 'POST', f'/exec/{acknowledged}/start',
                      {'Detach': False, 'Tty': False}, upgrade=True) as response:
            streams(response.response, deadline, stdout, stderr)
        with Exchange(path, deadline, 'GET', f'/exec/{acknowledged}/json') as response:
            observed = response.json(200)
        if (observed.get('ID') != acknowledged or observed.get('ContainerID') != container
                or observed.get('Running') is not False or type(observed.get('ExitCode')) is not int):
            raise ValueError('guard Engine exact terminal identity/exit unavailable')
        terminal_exit = observed['ExitCode']
        if observed['ExitCode'] != 0:
            refused = RuntimeError(f'original root resource guard exit {observed["ExitCode"]}')
            refused.guard_exit_code = observed["ExitCode"]
            raise refused
        deadline.left()
        return 0
    except BaseException as original:
        if terminal_exit is not None:
            original.guard_exit_code = terminal_exit
        try:
            stderr.write(f'guard Exec acknowledgement={acknowledged}; remote cancellation NOT_ESTABLISHED\n'.encode())
            stderr.flush()
        except BaseException as writing:
            original.independent_receipt_failure = writing
        raise


def command(path, container, folder, label, seconds):
    """One synchronous root observation; null host-child custody is deliberate.

    The same absolute allowance covers evidence setup, transport and close.
    Disk writes are not interruptible: post-write checks refuse late success.
    Only our provisional completion link may be removed; attempt bytes remain.
    """
    started = time.monotonic_ns()
    deadline = Deadline(seconds)
    folder = Path(folder)
    record = {'argv': ['python3', '-B', '-c', BODY], 'cwd': None, 'attempts': 1,
              'wall_stop_seconds': seconds, 'status': 'ATTEMPT_DECLARED',
              'stdout': str(folder / (label + '.stdout')),
              'stderr': str(folder / (label + '.stderr')), 'exit_code': None}
    original = None
    outputs = []
    completion = folder / (label + '.completion.json')
    def fail(error):
        nonlocal original
        if original is None:
            original = error
            record.update(status='FAIL', original_failure_type=type(error).__name__,
                          original_failure=str(error), timeout=isinstance(error, TimeoutError),
                          remote_cancellation='NOT_ESTABLISHED; retain exact Docker resources')
        else:
            original.independent_receipt_failure = error
    try:
        deadline.left()
        folder.mkdir(parents=True, exist_ok=True)
        receipts.write_new(folder / (label + '.attempt.json'), record)
        deadline.left()
        receipts.write_new(folder / (label + '.host-custody.json'), {
            'host_pid': None, 'host_group': None, 'remote_cancellation': 'NOT_ESTABLISHED'})
        deadline.left()
        for field in ('stdout', 'stderr'):
            outputs.append(Path(record[field]).open('xb'))
            deadline.left()
        record['exit_code'] = execute(path, container, seconds, *outputs, deadline=deadline)
        deadline.left()
        record['status'] = 'PASS'
    except BaseException as error:
        record['exit_code'] = getattr(error, 'guard_exit_code', record['exit_code'])
        fail(error)
    finally:
        for output in reversed(outputs):
            try:
                output.close()
                deadline.left()
            except BaseException as closing:
                fail(closing)
        record['complete_wall_ns'] = time.monotonic_ns() - started
        try:
            if original is not None:
                receipts.write_new(completion, record)
            else:
                # Exact attempt is append-only; the success link requires a post-write check.
                attempt = folder / (label + '.completion.attempt.json')
                receipts.write_new(attempt, record)
                deadline.left()
                os.link(attempt, completion)
                try:
                    deadline.left()
                except BaseException:
                    completion.unlink()  # Only the link created above, never another receipt.
                    raise
        except BaseException as writing:
            fail(writing)
            if not completion.exists():
                try:
                    receipts.write_new(completion, record)
                except BaseException as recording:
                    original.independent_receipt_failure = recording
    if original is not None:
        raise original
    return record
