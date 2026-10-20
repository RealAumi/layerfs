#!/usr/bin/env python3
"""LayerFS `ignore=git` end to end on local Docker (OrbStack, Linux/arm64).

Adapted from run-remote-e2e.py (remote-host). One Store server (A), two sandboxes:
B1 runs with `ignore=git`, B2 is a plain sandbox (warm-base builder and "other
machine"). Every container, network and volume is prefixed `ign-`; `ign-target`
(the cargo target dir) is the only thing kept between runs.

  run-ignore-e2e.py build       build the Linux binaries into $IGN_WORK/bin
  run-ignore-e2e.py e2e         scenarios 1-6 and the ignore-off comparison
  run-ignore-e2e.py transport   scenario 7 (layerfs-remote-store transport tests)
  run-ignore-e2e.py all         everything (default)

Receipts: docs/mp2/receipts/$IGN_RECEIPTS/ (default ignore01).  Work dir (binaries, seed): $IGN_WORK,
default ~/.cache/ign-e2e.
"""
import hashlib, json, os, pathlib, re, subprocess, sys, time, shutil

REPO = pathlib.Path(__file__).resolve().parents[2]
RECEIPTS = REPO / 'docs/mp2/receipts' / os.environ.get('IGN_RECEIPTS', 'ignore01')
WORK = pathlib.Path(os.environ.get('IGN_WORK', pathlib.Path.home() / '.cache/ign-e2e'))
BIN, SEED = WORK / 'bin', WORK / 'seed'
IMAGE = 'public.ecr.aws/docker/library/rust:1.85.1-bookworm'
WORKERS = os.environ.get('IGN_WORKERS', '1')  # same as the remote-host harness
A, B1, B2 = 'ign-a', 'ign-b1', 'ign-b2'
NET_A, NET_B, LINK = 'ign-server-net', 'ign-sandbox-net', 'ign-link'
V_SERVER, V_B1, V_B2, V_TARGET = 'ign-server-data', 'ign-b1-data', 'ign-b2-data', 'ign-target'
MIB = 1024 * 1024
RECEIPTS.mkdir(parents=True, exist_ok=True)
BIN.mkdir(parents=True, exist_ok=True)
SEED.mkdir(parents=True, exist_ok=True)
JSONL = RECEIPTS / 'e2e-receipts.jsonl'
CONSOLE = RECEIPTS / 'console.log'


def say(*parts):
    line = ' '.join(str(p) for p in parts)
    print(line, flush=True)
    with CONSOLE.open('a') as f:
        f.write(line + '\n')


def run(args, expected=0, wall=120, log=True, input=None):
    args = [str(x) for x in args]
    before = time.monotonic_ns()
    p = subprocess.run(args, text=True, errors='replace', stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=wall, input=input)
    elapsed = time.monotonic_ns() - before
    if log:
        out = p.stdout
        with JSONL.open('a') as f:
            f.write(json.dumps(dict(command=args, exit=p.returncode, wall_ns=elapsed,
                                    output_len=len(out), output=out[:8000] + ('...[cut]' if len(out) > 8000 else ''))) + '\n')
    if expected is not None:
        assert p.returncode == expected, (args, p.returncode, p.stdout[-4000:])
    p.wall_ns = elapsed
    return p


def docker(*args, **kw):
    return run(['docker', *args], **kw)


def out(*args, **kw):
    return docker(*args, **kw).stdout


# ---------------------------------------------------------------- build

CARGO_COMMON = ['--manifest-path', 'core/Cargo.toml', '--locked']


def cargo_container(name, *cargo):
    """cargo inside the rust image; source read-only, target dir in ign-target."""
    args = ['run', '--rm', '--name', name, '-v', f'{REPO}:/work:ro', '-v', f'{V_TARGET}:/target',
            '-w', '/work', '-e', 'CARGO_HOME=/target/cargo-home', '-e', 'CARGO_TARGET_DIR=/target/cargo',
            '-e', 'CARGO_TERM_COLOR=never']
    return [*args, IMAGE, 'cargo', *cargo]


def build():
    docker('volume', 'create', V_TARGET)
    build_dir = RECEIPTS / 'build'
    build_dir.mkdir(exist_ok=True)
    # The coordinator's tree may change between builds; record exactly what was built.
    ident = subprocess.run(['git', '-C', str(REPO), 'diff', 'HEAD'], capture_output=True).stdout
    untracked = subprocess.run(['git', '-C', str(REPO), 'ls-files', '--others', '--exclude-standard', '--', 'core'],
                               capture_output=True, text=True).stdout.split()
    h = hashlib.sha256(ident)
    for u in sorted(untracked):
        h.update((REPO / u).read_bytes())
    say('BUILD source: HEAD', subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
        'worktree-diff+untracked sha256', h.hexdigest())
    steps = [
        ('bins', ['build', *CARGO_COMMON, '--profile', 'test', '-p', 'layerfs-remote-store', '--bin', 'layerfs-store', '--bin', 'layerfs-remote']),
        ('daemon', ['build', *CARGO_COMMON, '--profile', 'test', '-p', 'layerfs-daemon', '--bin', 'layerfs-remote-daemon']),
    ]
    for label, cargo in steps:
        t = time.monotonic()
        p = docker(*cargo_container('ign-build', *cargo), wall=3000)
        (build_dir / f'{label}.log').write_text(p.stdout)
        say(f'BUILD {label}: ok in {time.monotonic() - t:.0f}s: {p.stdout.strip().splitlines()[-1]}')
    t = time.monotonic()
    args = ['docker', *cargo_container('ign-build', 'test', *CARGO_COMMON, '--no-run', '--message-format=json',
                                       '-p', 'layerfs-remote-store', '--test', 'remote_driver')]
    p = subprocess.run(args, text=True, capture_output=True, timeout=3000)
    (build_dir / 'driver.json').write_text(p.stdout)
    (build_dir / 'driver.log').write_text(p.stderr)
    assert p.returncode == 0, p.stderr[-4000:]
    driver = None
    for line in p.stdout.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get('reason') == 'compiler-artifact' and msg['target']['name'] == 'remote_driver' and msg.get('executable'):
            driver = msg['executable']
    assert driver, 'remote_driver executable not found in cargo output'
    say(f'BUILD driver: ok in {time.monotonic() - t:.0f}s: {driver}')
    docker('run', '--rm', '--name', 'ign-collect', '-v', f'{V_TARGET}:/target:ro', '-v', f'{BIN}:/out', IMAGE,
           'bash', '-c', 'set -e; for n in layerfs-store layerfs-remote layerfs-remote-daemon; do cp /target/cargo/debug/$n /out/$n; done; cp "$1" /out/remote_driver',
           'bash', driver)
    shutil.copy2(REPO / 'docs/mp2/tcp-cut.py', BIN / 'tcp-cut.py')
    lines = []
    for n in ['layerfs-store', 'layerfs-remote', 'layerfs-remote-daemon', 'remote_driver', 'tcp-cut.py']:
        lines.append(f'{hashlib.sha256((BIN / n).read_bytes()).hexdigest()}  bin/{n}')
    (RECEIPTS / 'tested-identities.txt').write_text('\n'.join(lines) + f'\nsource-sha256 {h.hexdigest()}\n')
    say('BUILD artifacts:\n' + '\n'.join(lines))


# ---------------------------------------------------------------- e2e helpers

class Mount:
    def __init__(self, b, path, ws, ns):
        self.b, self.path, self.ws, self.ns = b, path, ws, ns

    def p(self, rel):
        return self.path + '/' + rel


def execute(b, *args, **kw):
    return docker('exec', b, *args, **kw)


def sh(b, script, *args, expected=0, wall=120, env=None):
    cmd = ['exec']
    for k, v in (env or {}).items():
        cmd += ['-e', f'{k}={v}']
    return docker(*cmd, b, 'timeout', str(wall), 'bash', '-c', script, 'bash', *args, expected=expected, wall=wall + 20)


def ready(container, marker, path):
    deadline = time.monotonic() + 30
    p = None
    while time.monotonic() < deadline:
        p = subprocess.run(['docker', 'exec', container, 'cat', path], capture_output=True, text=True, timeout=5)
        if marker in p.stdout:
            return
        time.sleep(.1)
    raise AssertionError((container, marker, p.stdout, p.stderr))


def ctl(b, op, *args, expected=0):
    return docker('exec', b, 'timeout', '300', '/opt/lfs/layerfs-remote', '/state/daemon.setup', op, *args, expected=expected, wall=320)


def mount(b):
    text = ctl(b, 'mount', (SEED / 'branch').read_text().strip()).stdout
    m = re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)', text)
    assert m, text
    return Mount(b, *m.groups())


def try_unmount(scn, m, discard=False):
    """Unmount; a refusal/retention is recorded as a failed check, never swallowed."""
    p = ctl(m.b, 'unmount', m.ws, m.ns, *(['discard'] if discard else []), expected=None)
    ok = p.returncode == 0
    check(scn, f'unmount {m.b} ns{m.ns}{" (discard)" if discard else ""} clean', ok, '' if ok else p.stdout[:700])
    return ok


def commit(m, expected=0):
    """Returns (output, wall_ns of the ctl call, python wall_ns)."""
    t = time.monotonic_ns()
    p = ctl(m.b, 'commit', m.ws, m.ns, expected=expected)
    py = time.monotonic_ns() - t
    w = re.search(r'wall_ns=(\d+)', p.stdout)
    return p.stdout, int(w[1]) if w else None, py


def unmount(m, discard=False):
    return ctl(m.b, 'unmount', m.ws, m.ns, *(['discard'] if discard else [])).stdout


def stat_counter(text, key):
    r = re.search(key + r'.*?Int\((\d+)\)', text)
    assert r, text
    return int(r[1])


def stats(b):
    text = ctl(b, 'stats').stdout
    return dict(roundTrips=stat_counter(text, 'roundTrips'), uploadedObjects=stat_counter(text, 'uploadedObjects'),
                uploadedBytes=stat_counter(text, 'uploadedBytes'))


def store_bytes():
    return int(execute(A, 'bash', '-c', 'du -sb /state/store | cut -f1').stdout.strip())


def driver(mode, path=None, text=None, expect=None, expected=0):
    args = ['exec', '-e', 'LFS_MODE=' + mode]
    for key, value in [('LFS_PATH', path), ('LFS_TEXT', text), ('LFS_EXPECT', expect)]:
        if value is not None:
            args += ['-e', f'{key}={value}']
    return docker(*args, A, 'timeout', '120', '/opt/lfs/remote_driver', '--ignored', '--exact', 'drive', '--nocapture', expected=expected)


def server_read(path):
    """Published-head content of `path` via the Store SDK on A; None when it is not there."""
    p = driver('read', path, expected=None)
    if p.returncode == 0:
        r = re.search(r'SDK_READ (".*")', p.stdout)
        return json.loads(r[1])
    return None


def put(m, rel, text):
    execute(m.b, 'python3', '-c', 'import pathlib,sys;p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(sys.argv[2])', m.p(rel), text)


def cat(m, rel):
    """Exact file content, or None when the path is absent."""
    p = docker('exec', m.b, 'timeout', '20', 'python3', '-c',
               'import sys;sys.stdout.write(open(sys.argv[1],newline="").read())', m.p(rel), expected=None)
    return p.stdout if p.returncode == 0 else None


def exists(m, rel):
    return docker('exec', m.b, 'timeout', '20', 'test', '-e', m.p(rel), expected=None).returncode == 0


def size(m, rel):
    p = docker('exec', m.b, 'timeout', '20', 'stat', '-c', '%s', m.p(rel), expected=None)
    return int(p.stdout.strip()) if p.returncode == 0 else None


def sha(m, rel):
    p = docker('exec', m.b, 'timeout', '60', 'sha256sum', m.p(rel), expected=None)
    return p.stdout.split()[0] if p.returncode == 0 else None


def count_files(m, rel):
    p = docker('exec', m.b, 'timeout', '60', 'bash', '-c', 'find "$1" -type f | wc -l', 'bash', m.p(rel), expected=None)
    return int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None


def git(m, *args, expected=0, optional_locks=True):
    env = ['-e', 'HOME=/tmp']
    if not optional_locks:
        env += ['-e', 'GIT_OPTIONAL_LOCKS=0']
    return docker('exec', *env, '-w', m.path, m.b, 'git', '-c', 'safe.directory=*', '-c', 'user.name=ign', '-c', 'user.email=ign@example.invalid',
                  '-c', 'init.defaultBranch=main', *args, expected=expected)


def status(m):
    # Optional locks off: a read-only check must not rewrite .git/index in the sandbox.
    return git(m, 'status', '--porcelain', optional_locks=False).stdout


def big_file(m, rel, mib):
    execute(m.b, 'bash', '-c', 'mkdir -p "$(dirname "$1")"; head -c $(($2*1048576)) /dev/urandom > "$1"', 'bash', m.p(rel), str(mib))


def many_files(m, rel, n):
    execute(m.b, 'python3', '-c',
            'import os,sys,pathlib\nd=pathlib.Path(sys.argv[1]);d.mkdir(parents=True,exist_ok=True)\n'
            'for i in range(int(sys.argv[2])):(d/f"m{i:04d}.js").write_bytes(b"module %d "%i+os.urandom(24).hex().encode()+b"\\n")',
            m.p(rel), str(n), wall=300)


RESULTS = {}   # scenario -> dict(checks=[...])
FACTS = {}     # measurements


def check(scn, name, ok, evidence=''):
    RESULTS.setdefault(scn, []).append(dict(check=name, ok=bool(ok), evidence=str(evidence)[:1500]))
    say(f'  [{"PASS" if ok else "FAIL"}] {scn} :: {name}' + (f' -- {str(evidence)[:300]}' if evidence != '' else ''))


def scenario(scn, fn, *a):
    say(f'=== {scn}')
    try:
        fn(*a)
    except BaseException as e:  # a crash is a FAIL with its message, never swallowed
        check(scn, 'no exception', False, repr(e)[:1500])


# ---------------------------------------------------------------- warm-up watch
# The server runs with LAYERFS_REMOTE_TRACE_READS=1, so every object/length read it serves is in
# server.log (STORE_READ opcode=2|3 ids=[...], STORE_METADATA objects=N lengths=M). After each
# B1 Commit (B2 idle) the window up to a 3 s settle must contain no read of an object that B1's
# cache still holds as local-only (cache.objects.remote=0): that would be a warm-up asking the
# server for something only the sandbox has.

WARM = []


def server_log_lines():
    return execute(A, 'cat', '/state/server.log').stdout.splitlines()


def local_only_ids(b):
    script = ('import sqlite3,sys;c=sqlite3.connect("file:/state/cache/objects.sqlite?mode=ro",uri=True);'
              'print("\\n".join(r[0].hex() for r in c.execute("SELECT id FROM objects WHERE remote=0")))')
    return set(execute(b, 'python3', '-c', script).stdout.split())


def read_kinds(b, reads):
    """Name what a window's STORE_READ lines asked for, from B1's own cache (it stored what the server sent):
    opcode, object role, size, whether the cache holds it as server-known, and the printable runs in its body
    (directory entry names, .gitignore text, the paths of a .git/index)."""
    rows = []
    for line in reads:
        op = int(re.search(r'opcode=(\d+)', line)[1])
        for h in re.findall(r'[0-9a-f]{64}', line):
            rows.append(dict(opcode=op, id=h))
    script = ('import sqlite3,sys,json,re\n'
              'c=sqlite3.connect("file:/state/cache/objects.sqlite?mode=ro",uri=True)\n'
              'out=[]\n'
              'for h in sys.argv[1:]:\n'
              ' r=c.execute("SELECT role,body,remote FROM objects WHERE id=?",(bytes.fromhex(h),)).fetchone()\n'
              ' if not r: out.append(None); continue\n'
              ' body=bytes(r[1]); runs=[x.decode() for x in re.findall(rb"[ -~\\n]{3,}",body)]\n'
              ' out.append(dict(role=r[0],size=len(body),remote=r[2],dirc=b"DIRC" in body,text="|".join(runs)[:200].replace("\\n","\\\\n")))\n'
              'print(json.dumps(out))\n')
    info = json.loads(execute(b, 'python3', '-c', script, *[r['id'] for r in rows]).stdout) if rows else []
    for r, i in zip(rows, info):
        r['id'] = r['id'][:12]
        r.update(i or dict(cached=False))
    return rows


def watched_commit(scn, m, settle=3.0, dump=None):
    """commit() plus the warm-up watch; returns commit()'s tuple."""
    n0 = len(server_log_lines())
    r0 = stats(m.b)['roundTrips']
    res = commit(m)
    r1 = stats(m.b)['roundTrips']
    time.sleep(settle)
    r2 = stats(m.b)['roundTrips']
    window = server_log_lines()[n0:]
    reads = [x for x in window if x.startswith('STORE_READ')]
    meta = [x for x in window if x.startswith('STORE_METADATA')]
    local = local_only_ids(m.b)
    asked = sorted(set(re.findall(r'[0-9a-f]{64}', ' '.join(reads))) & local)
    if dump:
        FACTS[dump] = read_kinds(m.b, reads)
        for row in FACTS[dump]:
            say('   read', json.dumps(row))
    rec = dict(scenario=scn, commit_round_trips=r1 - r0, settle_round_trips=r2 - r1, store_reads=len(reads), store_metadata=len(meta),
               local_only_in_cache=len(local), local_only_requested=len(asked))
    WARM.append(rec)
    say('  warm-up watch:', json.dumps(rec))
    check(scn, 'warm-up watch: no server read of a local-only object during/after Commit', not asked, f'{rec} asked={asked[:3]}')
    check(scn, 'warm-up watch: no server activity in the 3 s after Commit (round trips)', r2 == r1, f'commit={r1 - r0} settle={r2 - r1}')
    return res


# ---------------------------------------------------------------- scenarios

def s1_warm_base():
    s = '1 warm base (B2, ignore off)'
    m = mount(B2)
    FACTS['m2_warm'] = m.ws
    put(m, '.gitignore', 'target/\nnode_modules/\nout/\n*.log\n')
    put(m, 'src/A.java', 'class A { int v = 1; }\n')
    git(m, 'init', '-q')
    git(m, 'add', '-A')
    git(m, 'commit', '-q', '-m', 'init')
    put(m, 'target/old.class', 'old')
    put(m, 'node_modules/x/index.js', 'module.exports = 1;\n')
    st = status(m)
    check(s, 'git status clean before Commit (ignored files hidden)', st == '', repr(st))
    check(s, 'git ls-files has .gitignore and src/A.java, not target/', all(x in git(m, 'ls-files').stdout for x in ['.gitignore', 'src/A.java']) and 'target' not in git(m, 'ls-files').stdout)
    s0 = stats(B2)
    out_, w, py = commit(m)
    s1 = stats(B2)
    FACTS['warm_commit_wall_ms'] = (w or py) / 1e6
    FACTS['warm_upload'] = {k: s1[k] - s0[k] for k in s0}
    say('  warm commit output:', out_.strip().replace('\n', ' | ')[:400])
    published = server_read('/target/old.class')
    check(s, 'warm Commit published ignored target/old.class (ignore off)', published == 'old', repr(published))
    check(s, 'published node_modules/x/index.js', server_read('/node_modules/x/index.js') == 'module.exports = 1;\n')
    check(s, 'published src/A.java v1', server_read('/src/A.java') == 'class A { int v = 1; }\n')
    check(s, 'published .git/HEAD', (server_read('/.git/HEAD') or '').startswith('ref:'))
    try_unmount(s, m)


def check_b2_view(scn, label, expect_present, expect_absent, expect_text):
    """Fresh B2 mount of the head: listed paths exist with text, others are absent."""
    m = mount(B2)
    try:
        for rel, text in expect_text.items():
            got = cat(m, rel)
            check(scn, f'{label}: B2 {rel} == {text!r}', got == text, repr(got)[:200])
        for rel in expect_present:
            check(scn, f'{label}: B2 has {rel}', exists(m, rel))
        for rel in expect_absent:
            check(scn, f'{label}: B2 has no {rel}', not exists(m, rel))
        return status(m)
    finally:
        try_unmount(scn, m, discard=True)


def s2_ignored_changes_stay_local(m1):
    s = '2 ignored changes stay local (B1 ignore=git)'
    check(s, 'B1 sees the warm base (src/A.java v1, target/old.class old)',
          cat(m1, 'src/A.java') == 'class A { int v = 1; }\n' and cat(m1, 'target/old.class') == 'old')
    put(m1, 'src/A.java', 'class A { int v = 2; }\n')
    big_file(m1, 'target/big.bin', 32)
    big_sha = sha(m1, 'target/big.bin')
    many_files(m1, 'node_modules/y', 3000)
    y_listing = execute(m1.b, 'bash', '-c', 'cd "$1" && find node_modules/y -type f | sort | xargs sha256sum | sha256sum', 'bash', m1.path, wall=120).stdout.strip()
    put(m1, 'app.log', 'log line 1\n')
    put(m1, 'target/old.class', 'rebuilt')
    FACTS['s2_ignored_bytes_written'] = 32 * MIB + 3000 * 60
    s0, store0 = stats(B1), store_bytes()
    out_, w, py = watched_commit(s, m1)
    s1, store1 = stats(B1), store_bytes()
    delta = {k: s1[k] - s0[k] for k in s0}
    FACTS['s2_ignore_on'] = dict(commit_wall_ms=(w or py) / 1e6, python_wall_ms=py / 1e6, **delta, server_store_delta_bytes=store1 - store0)
    say('  s2 commit output:', out_.strip().replace('\n', ' | ')[:500])
    check(s, '(a) client uploadedBytes far below 32 MiB (< 2 MiB)', delta['uploadedBytes'] < 2 * MIB, f'delta={delta}')
    check(s, '(a) server store grew far below 32 MiB (< 2 MiB)', store1 - store0 < 2 * MIB, f'{store0} -> {store1} (+{store1 - store0})')
    # (b) the mount still shows everything: contents AND sizes (stat), not only existence.
    check(s, '(b) B1 src/A.java edited', cat(m1, 'src/A.java') == 'class A { int v = 2; }\n')
    check(s, '(b) B1 target/big.bin stat size == 32 MiB', size(m1, 'target/big.bin') == 32 * MIB, size(m1, 'target/big.bin'))
    check(s, '(b) B1 target/big.bin content sha unchanged', sha(m1, 'target/big.bin') == big_sha, sha(m1, 'target/big.bin'))
    ls = execute(m1.b, 'bash', '-c', 'ls -l "$1"/target/big.bin "$1"/target/old.class "$1"/app.log', 'bash', m1.path, expected=None).stdout
    say('  ls -l after Commit:\n' + ls)
    check(s, '(b) ls -l shows big.bin with 33554432 bytes', '33554432' in ls, ls.strip())
    check(s, '(b) B1 node_modules/y still 3000 files', count_files(m1, 'node_modules/y') == 3000, count_files(m1, 'node_modules/y'))
    y_after = execute(m1.b, 'bash', '-c', 'cd "$1" && find node_modules/y -type f | sort | xargs sha256sum | sha256sum', 'bash', m1.path, wall=120).stdout.strip()
    check(s, '(b) B1 node_modules/y content hash unchanged', y_after == y_listing)
    sizes_ok = execute(m1.b, 'bash', '-c', 'cd "$1" && find node_modules/y -type f -printf "%s\\n" | sort -u | tr "\\n" " "', 'bash', m1.path).stdout
    check(s, '(b) B1 node_modules/y stat sizes are real (non-zero)', sizes_ok.strip() != '' and '0' not in sizes_ok.split(), sizes_ok)
    check(s, '(b) B1 app.log content + size', cat(m1, 'app.log') == 'log line 1\n' and size(m1, 'app.log') == 11, size(m1, 'app.log'))
    check(s, '(b) B1 target/old.class == rebuilt (size 7)', cat(m1, 'target/old.class') == 'rebuilt' and size(m1, 'target/old.class') == 7)
    check(s, '(b) B1 node_modules/x/index.js still readable', cat(m1, 'node_modules/x/index.js') == 'module.exports = 1;\n')
    # (c) fresh B2 mount of the head
    b2status = check_b2_view(s, '(c)', ['node_modules/x/index.js'], ['target/big.bin', 'node_modules/y', 'app.log'],
                             {'src/A.java': 'class A { int v = 2; }\n', 'target/old.class': 'old'})
    check(s, '(c) published head lacks big.bin / node_modules/y/m0000.js / app.log (Store SDK)',
          server_read('/target/big.bin') is None and server_read('/node_modules/y/m0000.js') is None and server_read('/app.log') is None)
    # (d) git status
    b1status = status(m1)
    check(s, '(d) B1 git status --porcelain == " M src/A.java"', b1status.strip('\n') == ' M src/A.java', repr(b1status))
    check(s, '(d) B2 git status --porcelain == " M src/A.java"', b2status.strip('\n') == ' M src/A.java', repr(b2status))


def s3_clean(m1):
    s = '3 clean'
    execute(m1.b, 'bash', '-c', 'cd "$1" && rm -rf target node_modules', 'bash', m1.path, wall=120)
    s0 = stats(B1)
    out_, w, py = watched_commit(s, m1)
    s1 = stats(B1)
    FACTS['s3_commit'] = dict(wall_ms=(w or py) / 1e6, uploadedBytes=s1['uploadedBytes'] - s0['uploadedBytes'])
    check(s, 'B1 no longer shows target/ and node_modules/', not exists(m1, 'target') and not exists(m1, 'node_modules'))
    b2status = check_b2_view(s, 'B2', ['node_modules/x'], [], {'target/old.class': 'old', 'node_modules/x/index.js': 'module.exports = 1;\n'})
    check(s, 'published head still has target/old.class old (Store SDK)', server_read('/target/old.class') == 'old')
    check(s, 'B2 git status unchanged (only " M src/A.java")', b2status.strip('\n') == ' M src/A.java', repr(b2status))


def s4_rebuild(m1):
    s = '4 rebuild'
    put(m1, 'target/old.class', 'again')
    s0 = stats(B1)
    watched_commit(s, m1)
    s1 = stats(B1)
    check(s, 'B1 target/old.class == again', cat(m1, 'target/old.class') == 'again')
    check(s, 'rebuild upload tiny (< 64 KiB)', s1['uploadedBytes'] - s0['uploadedBytes'] < 65536, s1['uploadedBytes'] - s0['uploadedBytes'])
    check_b2_view(s, 'B2', [], [], {'target/old.class': 'old'})
    check(s, 'published head target/old.class still old (Store SDK)', server_read('/target/old.class') == 'old')


def s5_flip(m1):
    s = '5 flip'
    # 5a: written under out/ (ignored): stays local.
    put(m1, 'out/gen.txt', 'gen from B1\n')
    watched_commit(s, m1)
    check(s, '5a B1 still shows out/gen.txt', cat(m1, 'out/gen.txt') == 'gen from B1\n')
    check_b2_view(s, '5a', [], ['out/gen.txt'], {})
    # 5b: git add -f flips it to kept.
    git(m1, 'add', '-f', 'out/gen.txt')
    watched_commit(s, m1)
    check_b2_view(s, '5b after git add -f', [], [], {'out/gen.txt': 'gen from B1\n'})
    check(s, '5b published head has out/gen.txt with B1 bytes (Store SDK)', server_read('/out/gen.txt') == 'gen from B1\n')
    # 5c: drop *.log from .gitignore, write keep.log.
    put(m1, '.gitignore', 'target/\nnode_modules/\nout/\n')
    put(m1, 'keep.log', 'keep me\n')
    watched_commit(s, m1)
    check_b2_view(s, '5c after .gitignore edit', [], [], {'keep.log': 'keep me\n', 'app.log': 'log line 1\n', '.gitignore': 'target/\nnode_modules/\nout/\n'})
    # 5d: move from an ignored directory into a kept one.
    put(m1, 'target/moved.txt', 'moved bytes\n')
    watched_commit(s, m1)
    check_b2_view(s, '5d moved-file prelude', [], ['target/moved.txt', 'src/moved.txt'], {})
    execute(m1.b, 'bash', '-c', 'mv "$1/target/moved.txt" "$1/src/moved.txt"', 'bash', m1.path)
    watched_commit(s, m1)
    check_b2_view(s, '5d after mv into src/', [], ['target/moved.txt'], {'src/moved.txt': 'moved bytes\n'})


def s6_moved_head(m1):
    s = '6 moved head'
    # Make B1 hold several local-only ignored files before the head moves.
    put(m1, 'node_modules/z/index.js', 'zzz\n')
    big_file(m1, 'target/big2.bin', 1)
    big2 = sha(m1, 'target/big2.bin')
    watched_commit(s, m1)
    before = dict(old=cat(m1, 'target/old.class'), z=cat(m1, 'node_modules/z/index.js'), big2=sha(m1, 'target/big2.bin'))
    check(s, 'prelude: B1 holds local-only ignored files', before == dict(old='again', z='zzz\n', big2=big2), before)
    # B2 adds a tracked docs/README.md and Commits (head moves under B1).
    m2 = mount(B2)
    put(m2, 'docs/README.md', 'readme from B2\n')
    git(m2, 'add', 'docs/README.md')
    out2, _, _ = commit(m2)
    say('  B2 commit output:', out2.strip().replace('\n', ' | ')[:300])
    check(s, 'B2 docs/README.md published (Store SDK)', server_read('/docs/README.md') == 'readme from B2\n')
    # B1 edits a tracked file and Commits: stale base -> the server merges.
    put(m1, 'src/A.java', 'class A { int v = 3; }\n')
    out1, w, _ = watched_commit(s, m1, dump='s6_merge_reads')
    say('  B1 merge commit output:', out1.strip().replace('\n', ' | ')[:600])
    check(s, 'B1 Commit output mentions a merge', re.search(r'[Mm]erge', out1) is not None, out1.strip()[:400])
    check(s, 'B1 Commit had no conflict', 'Conflict(' not in out1, out1.strip()[:200])
    check(s, 'B1 mount now shows docs/README.md', cat(m1, 'docs/README.md') == 'readme from B2\n', cat(m1, 'docs/README.md'))
    check(s, 'B1 mount keeps src/A.java v3', cat(m1, 'src/A.java') == 'class A { int v = 3; }\n')
    after = dict(old=cat(m1, 'target/old.class'), z=cat(m1, 'node_modules/z/index.js'), big2=sha(m1, 'target/big2.bin'))
    check(s, 'B1 still has its local-only ignored files after the merge', after == before, after)
    check(s, 'B1 target/big2.bin stat size == 1 MiB', size(m1, 'target/big2.bin') == MIB, size(m1, 'target/big2.bin'))
    st1 = status(m1)
    say('  B1 git status after merge:\n' + st1)
    check(s, 'B1 git status lists no path under target/, node_modules/, out/ (ignored stay hidden)',
          not re.search(r'(target|node_modules)/', st1), repr(st1))
    check(s, 'published head does not have B1 local-only files (Store SDK)',
          server_read('/node_modules/z/index.js') is None and server_read('/target/big2.bin') is None)
    try_unmount(s, m2, discard=True)
    check_b2_view(s, 'B2 fresh', ['docs/README.md'], ['node_modules/z', 'target/big2.bin'],
                  {'src/A.java': 'class A { int v = 3; }\n', 'docs/README.md': 'readme from B2\n', 'target/old.class': 'old'})


def s5b_server_rule_flip(m1):
    """The server's .gitignore stops ignoring out/; B1 holds a never-published out/local.txt.

    Documented in docs/mp2/ignore.md: newly kept local bytes wait for the next projection, so
    (a) the Commit that merges the rule change leaves out/local.txt off the published head and
    (b) a second Commit with no local change publishes it."""
    s = '5b server rule flip (B2 un-ignores out/)'
    new_rules = 'target/\nnode_modules/\n'
    put(m1, 'out/local.txt', 'local out bytes\n')
    watched_commit(s, m1)
    check(s, 'prelude: B1 holds out/local.txt', cat(m1, 'out/local.txt') == 'local out bytes\n')
    check(s, 'prelude: published head has no out/local.txt (Store SDK)', server_read('/out/local.txt') is None)
    m2 = mount(B2)
    put(m2, '.gitignore', new_rules)
    commit(m2)
    try_unmount(s, m2)
    check(s, 'prelude: server head .gitignore no longer ignores out/ (Store SDK)', server_read('/.gitignore') == new_rules)
    # (a) B1's Commit after the rule change (no local change): merges the moved head.
    out1, w, py = watched_commit(s, m1)
    say('  5b(a) B1 merge Commit output:', out1.strip().replace('\n', ' | ')[:500])
    check(s, '5b(a) B1 Commit had no conflict', 'Conflict(' not in out1, out1.strip()[:300])
    check(s, '5b(a) B1 got the new .gitignore', cat(m1, '.gitignore') == new_rules, repr(cat(m1, '.gitignore')))
    check(s, '5b(a) B1 still has out/local.txt', cat(m1, 'out/local.txt') == 'local out bytes\n')
    check(s, '5b(a) EXPECTED one-Commit lag: out/local.txt is not yet on the published head (docs/mp2/ignore.md)',
          server_read('/out/local.txt') is None, repr(server_read('/out/local.txt')))
    # (b) a second Commit with no local change publishes the newly kept bytes.
    b0 = stats(B1)
    out2, w, py = watched_commit(s, m1)
    b1 = stats(B1)
    delta = {k: b1[k] - b0[k] for k in b0}
    FACTS['s5b_second_commit'] = dict(commit_wall_ms=(w or py) / 1e6, **delta)
    say('  5b(b) B1 second Commit output:', out2.strip().replace('\n', ' | ')[:500], '| upload', delta)
    check(s, '5b(b) B1 Commit had no conflict', 'Conflict(' not in out2, out2.strip()[:300])
    check(s, '5b(b) published head has out/local.txt with B1 bytes (Store SDK)', server_read('/out/local.txt') == 'local out bytes\n', repr(server_read('/out/local.txt')))
    check_b2_view(s, '5b(b) B2 fresh', [], [], {'out/local.txt': 'local out bytes\n', 'out/gen.txt': 'gen from B1\n', '.gitignore': new_rules})
    check(s, '5b(b) nothing else under ignored paths was uploaded: client upload < 64 KiB (1 MiB big2.bin is local-only)',
          delta['uploadedBytes'] < 64 * 1024, f'delta={delta}')
    check(s, '5b(b) published head still lacks target/big2.bin and node_modules/z (Store SDK)',
          server_read('/target/big2.bin') is None and server_read('/node_modules/z/index.js') is None)
    check(s, '5b(b) published head target/old.class still "old" (B1 local is "again")', server_read('/target/old.class') == 'old', repr(server_read('/target/old.class')))
    check(s, '5b(b) B1 keeps its other local-only files (old.class again, node_modules/z, big2.bin 1 MiB)',
          cat(m1, 'target/old.class') == 'again' and cat(m1, 'node_modules/z/index.js') == 'zzz\n' and size(m1, 'target/big2.bin') == MIB)


def s6b_server_delete(m1):
    """B2 deletes tracked pkg/; B1 holds ignored pkg/build/out.bin inside it."""
    s = '6b server delete (B2 deletes tracked pkg/)'
    lines = (cat(m1, '.gitignore') or '').splitlines()
    if 'build/' not in lines:
        put(m1, '.gitignore', '\n'.join(lines + ['build/']) + '\n')
    put(m1, 'pkg/a.txt', 'tracked a\n')
    put(m1, 'pkg/sub/b.txt', 'tracked b\n')
    git(m1, 'add', '.gitignore', 'pkg')
    watched_commit(s, m1)
    big_file(m1, 'pkg/build/out.bin', 1)
    put(m1, 'pkg/build/log.txt', 'build log\n')
    out_sha = sha(m1, 'pkg/build/out.bin')
    watched_commit(s, m1)
    check(s, 'prelude: published head has pkg/a.txt and pkg/sub/b.txt, not pkg/build (Store SDK)',
          server_read('/pkg/a.txt') == 'tracked a\n' and server_read('/pkg/sub/b.txt') == 'tracked b\n' and server_read('/pkg/build/out.bin') is None)
    check(s, 'prelude: B1 holds pkg/build/out.bin (1 MiB)', size(m1, 'pkg/build/out.bin') == MIB and out_sha is not None)
    st = status(m1)
    check(s, 'prelude: B1 git status does not list pkg/build', 'pkg/build' not in st, repr(st))
    # B2 deletes the tracked pkg/ and Commits.
    m2 = mount(B2)
    check(s, 'prelude: B2 sees tracked pkg/a.txt and no pkg/build', exists(m2, 'pkg/a.txt') and not exists(m2, 'pkg/build'))
    git(m2, 'rm', '-r', '-f', '-q', 'pkg')
    commit(m2)
    check(s, 'B2 mount has no pkg/ after git rm', not exists(m2, 'pkg'))
    try_unmount(s, m2)
    check(s, 'published head lost pkg/a.txt and pkg/sub/b.txt (Store SDK)', server_read('/pkg/a.txt') is None and server_read('/pkg/sub/b.txt') is None)
    # B1 edits a tracked file and Commits (stale base: the server merges).
    put(m1, 'src/A.java', 'class A { int v = 4; }\n')
    out1, w, py = watched_commit(s, m1)
    say('  B1 post-delete Commit output:', out1.strip().replace('\n', ' | ')[:500])
    check(s, 'B1 Commit had no conflict', 'Conflict(' not in out1, out1.strip()[:300])
    check(s, 'B1 still has pkg/build/out.bin (sha, size)', sha(m1, 'pkg/build/out.bin') == out_sha and size(m1, 'pkg/build/out.bin') == MIB,
          f'{sha(m1, "pkg/build/out.bin")} {size(m1, "pkg/build/out.bin")}')
    check(s, 'B1 still has pkg/build/log.txt', cat(m1, 'pkg/build/log.txt') == 'build log\n')
    check(s, 'B1 no longer has tracked pkg/a.txt', not exists(m1, 'pkg/a.txt'))
    check(s, 'B1 no longer has tracked pkg/sub (b.txt)', not exists(m1, 'pkg/sub/b.txt') and not exists(m1, 'pkg/sub'))
    check(s, 'B1 src/A.java edit kept', cat(m1, 'src/A.java') == 'class A { int v = 4; }\n')
    st = status(m1)
    say('  B1 git status after server delete:\n' + st)
    check(s, 'B1 git status lists no pkg path', 'pkg' not in st, repr(st))
    check(s, 'published head still has no pkg/ files and no pkg/build (Store SDK)',
          server_read('/pkg/a.txt') is None and server_read('/pkg/build/out.bin') is None and server_read('/pkg/build/log.txt') is None)
    check_b2_view(s, 'B2 fresh', [], ['pkg'], {'src/A.java': 'class A { int v = 4; }\n'})


def s9_logs():
    s = '9 logs and warm-up summary'
    srv = [x for x in server_log_lines() if not x.startswith(('STORE_READ', 'STORE_METADATA'))]
    bad = [x for x in srv if re.search(r'error|panic|missing|not found|refused', x, re.I)]
    check(s, 'server.log has no error lines (trace lines excluded)', not bad, bad[:3])
    for b in (B1, B2):
        n = execute(b, 'bash', '-c', 'grep -ciE "error|panic|refused|missing" /state/daemon.log', expected=None).stdout.strip()
        check(s, f'{b} daemon.log has no error lines', n == '0', n)
    FACTS['warm_up_watch'] = WARM


def s8_comparison():
    """Same shape as scenario 2, but on B2 (ignore off): everything is published."""
    s = '8 comparison (B2 ignore off, same shape as 2)'
    m = mount(B2)
    put(m, 'src/A.java', 'class A { int v = 9; }\n')
    big_file(m, 'target/big.bin', 32)
    many_files(m, 'node_modules/y', 3000)
    put(m, 'app.log', 'cmp log\n')
    put(m, 'target/old.class', 'rebuilt')
    s0, store0 = stats(B2), store_bytes()
    out_, w, py = commit(m)
    s1, store1 = stats(B2), store_bytes()
    delta = {k: s1[k] - s0[k] for k in s0}
    FACTS['s8_ignore_off'] = dict(commit_wall_ms=(w or py) / 1e6, python_wall_ms=py / 1e6, **delta, server_store_delta_bytes=store1 - store0)
    check(s, 'ignore-off Commit uploads the 32 MiB file (>= 32 MiB)', delta['uploadedBytes'] >= 32 * MIB, f'delta={delta}')
    check(s, 'published head has target/big.bin (Store SDK size)', (server_read('/target/old.class') == 'rebuilt'), '')
    try_unmount(s, m)


# ---------------------------------------------------------------- environment

class Env:
    """Server A + sandboxes B1 (ignore=git) and B2 (plain), all `ign-` prefixed; removed on exit."""

    def __enter__(self):
        existing = [x for x in (out('ps', '-a', '--format', '{{.Names}}').split() + out('network', 'ls', '--format', '{{.Name}}').split()
                                + out('volume', 'ls', '--format', '{{.Name}}').split()) if x in {A, B1, B2, NET_A, NET_B, LINK, V_SERVER, V_B1, V_B2, 'ign-init', 'ign-seed'}]
        assert not existing, f'leftover ign- resources: {existing}'
        for n in ['layerfs-store', 'layerfs-remote', 'layerfs-remote-daemon', 'remote_driver', 'tcp-cut.py']:
            assert (BIN / n).is_file(), f'{n} missing: run the build phase first'
        # Empty the seed dir in place: removing and recreating a bind-mounted directory makes
        # OrbStack's file sharing hand the next container a stale dir (init then fails with ENOENT).
        SEED.mkdir(parents=True, exist_ok=True)
        for f in SEED.iterdir():
            f.unlink()
        self.owned, self.nets, self.volumes = [], [], []
        try:
            for n in [NET_A, NET_B, LINK]:
                docker('network', 'create', '--internal', n)
                self.nets.append(n)
            for v in [V_SERVER, V_B1, V_B2]:
                docker('volume', 'create', v)
                self.volumes.append(v)
            docker('run', '--rm', '--name', 'ign-init', '--network', NET_A, '-v', f'{BIN}:/opt/lfs:ro', '-v', f'{SEED}:/out', '-v', f'{V_SERVER}:/state',
                   '-e', 'LFS_MODE=init', '-e', f'LAYERFS_CONSTRUCTION_WORKERS={WORKERS}', IMAGE, 'timeout', '120', '/opt/lfs/remote_driver', '--ignored', '--exact', 'drive', '--nocapture')
            docker('run', '-d', '--name', A, '--init', '--network', NET_A, '-v', f'{BIN}:/opt/lfs:ro', '-v', f'{V_SERVER}:/state',
                   '-e', f'LAYERFS_CONSTRUCTION_WORKERS={WORKERS}', '-e', 'LAYERFS_REMOTE_TRACE_READS=1', IMAGE, 'bash', '-c', 'exec /opt/lfs/layerfs-store --config /state/server.setup > /state/server.log 2>&1')
            self.owned.append(A)
            docker('network', 'connect', '--alias', 'store', LINK, A)
            ready(A, 'REMOTE_STORE_READY', '/state/server.log')
            # B1 alone gets `ignore=git` appended to its daemon setup.
            for b, v, cfg, extra in [(B1, V_B1, 'b1.setup', 'ignore=git\\n'), (B2, V_B2, 'b2.setup', '')]:
                docker('run', '--rm', '--name', 'ign-seed', '--network', NET_B, '-v', f'{SEED}:/seed:ro', '-v', f'{v}:/state', IMAGE, 'bash', '-c',
                       f'cp /seed/{cfg} /state/daemon.setup; printf "{extra}" >> /state/daemon.setup; chmod 700 /state; chown 0:0 /state/daemon.setup; chmod 600 /state/daemon.setup')
                docker('run', '-d', '--name', b, '--init', '--network', LINK, '--device', '/dev/fuse', '--cap-add', 'SYS_ADMIN', '--cap-add', 'SYS_PTRACE',
                       '--security-opt', 'apparmor=unconfined', '--security-opt', 'no-new-privileges=true', '-v', f'{BIN}:/opt/lfs:ro', '-v', f'{v}:/state',
                       '-e', f'LAYERFS_CONSTRUCTION_WORKERS={WORKERS}', IMAGE, 'bash', '-c',
                       'python3 /opt/lfs/tcp-cut.py > /state/proxy.log 2>&1 & while ! grep -q PROXY_READY /state/proxy.log; do sleep 0.05; done; exec /opt/lfs/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1')
                self.owned.append(b)
                docker('network', 'connect', NET_B, b)
                ready(b, 'REMOTE_DAEMON_READY', '/state/daemon.log')
            say('ignore setting lines: B1', execute(B1, 'bash', '-c', 'grep -c "^ignore=git$" /state/daemon.setup').stdout.strip(),
                '| B2', execute(B2, 'bash', '-c', 'grep -c "^ignore=" /state/daemon.setup', expected=None).stdout.strip())
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for b in self.owned:
            for name in ['server.log', 'daemon.log', 'proxy.log']:
                subprocess.run(['docker', 'cp', f'{b}:/state/{name}', str(RECEIPTS / f'{b}-{name}')], capture_output=True, timeout=30)
        for b in [B1, B2]:
            if b in self.owned:
                p = subprocess.run(['docker', 'exec', b, 'bash', '-c', 'grep -ciE "error|panic|refused" /state/daemon.log'], capture_output=True, text=True)
                say(f'{b} daemon.log error-ish lines: {p.stdout.strip()}')
        for b in self.owned:
            docker('rm', '-f', b, expected=None)
        for v in self.volumes:
            docker('volume', 'rm', v, expected=None)
        for n in reversed(self.nets):
            docker('network', 'rm', n, expected=None)


def e2e():
    for f in (JSONL, CONSOLE):
        f.unlink(missing_ok=True)
    with Env():
        scenario('1 warm base (B2, ignore off)', s1_warm_base)
        m1 = mount(B1)
        say('B1 mounted', m1.path)
        scenario('2 ignored changes stay local (B1 ignore=git)', s2_ignored_changes_stay_local, m1)
        scenario('3 clean', s3_clean, m1)
        scenario('4 rebuild', s4_rebuild, m1)
        scenario('5 flip', s5_flip, m1)
        scenario('6 moved head', s6_moved_head, m1)
        scenario('5b server rule flip (B2 un-ignores out/)', s5b_server_rule_flip, m1)
        scenario('6b server delete (B2 deletes tracked pkg/)', s6b_server_delete, m1)
        scenario('8 comparison (B2 ignore off, same shape as 2)', s8_comparison)
        scenario('9 logs and warm-up summary', s9_logs)
    summary = {}
    for scn, checks in RESULTS.items():
        summary[scn] = dict(result='PASS' if all(c['ok'] for c in checks) else 'FAIL', checks=checks)
    (RECEIPTS / 'results.json').write_text(json.dumps(dict(scenarios=summary, facts=FACTS), indent=2))
    say('\nSUMMARY')
    for scn, v in summary.items():
        failed = [c['check'] for c in v['checks'] if not c['ok']]
        say(f'  {v["result"]}  {scn}  ({len(v["checks"]) - len(failed)}/{len(v["checks"])} checks)' + (f'  FAILED: {failed}' if failed else ''))
    say('FACTS', json.dumps(FACTS, indent=2))


def transport():
    s = '7 platform check (Linux transport tests)'
    docker('volume', 'create', V_TARGET)
    t = time.monotonic()
    p = docker(*cargo_container('ign-transport', 'test', *CARGO_COMMON, '-p', 'layerfs-remote-store', '--test', 'transport'), expected=None, wall=3000)
    (RECEIPTS / 'transport-tests.log').write_text(p.stdout)
    tail = '\n'.join(p.stdout.strip().splitlines()[-25:])
    say(f'=== {s}: exit {p.returncode} in {time.monotonic() - t:.0f}s\n{tail}')
    r = re.search(r'test result: (\w+)\. (\d+) passed; (\d+) failed', p.stdout)
    RESULTS[s] = [dict(check='cargo test -p layerfs-remote-store --test transport', ok=p.returncode == 0, evidence=r[0] if r else tail)]
    (RECEIPTS / 'transport-result.json').write_text(json.dumps(RESULTS[s], indent=2))


if __name__ == '__main__':
    phase = sys.argv[1] if len(sys.argv) > 1 else 'all'
    assert phase in ['build', 'e2e', 'transport', 'all'], phase
    if phase in ('build', 'all'):
        build()
    if phase in ('e2e', 'all'):
        e2e()
    if phase in ('transport', 'all'):
        transport()
