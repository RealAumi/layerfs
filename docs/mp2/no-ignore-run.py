#!/usr/bin/env python3
"""Single-attempt noignore01 orchestration. Subcommands never retry a workload."""
import gzip
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/mp2/receipts/noignore01'
HOME = str(pathlib.Path.home())
IMAGE = 'cxn-tools:noignore01'
NETWORK = 'cxn-work-net-' + sys.argv[1]


def record(kind, **value):
    with (OUT / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(kind=kind, **value)).replace(HOME, '~') + '\n')


def run(label, args, limit=30, check=True):
    start = time.monotonic_ns()
    try:
        p = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=limit)
        output, code = p.stdout.decode(errors='replace'), p.returncode
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b'').decode(errors='replace')
        code = 'HOST_TIMEOUT'
    elapsed = time.monotonic_ns() - start
    log = OUT / (label + '.log')
    with log.open('x') as stream:
        stream.write(output.replace(HOME, '~'))
    row = dict(label=label, command=[str(a).replace(HOME, '~') for a in args],
               wall_ns=elapsed, exit=code, output=log.name, sample_count=1)
    record('command', **row)
    print(label, code, round(elapsed / 1e9, 3), flush=True)
    if check and code != 0:
        raise RuntimeError(json.dumps(row))
    return row, output


def docker(label, *args, **kw):
    return run(label, ['docker', *args], **kw)


def state_save(s):
    (OUT / 'runtime-state.json').write_text(json.dumps(s, indent=2) + '\n')


def ready(container, file, marker):
    # Startup readiness waits are not replay of an attempted operation.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        p = subprocess.run(['docker', 'exec', container, 'cat', file], capture_output=True)
        if marker.encode() in p.stdout:
            return
        time.sleep(.1)
    raise RuntimeError('readiness deadline: ' + container + ' ' + marker)


def proxy(s):
    script = 'import socket; s=socket.socket(socket.AF_UNIX); s.connect("/state/proxy.sock"); print(s.recv(4096).decode())'
    return json.loads(subprocess.check_output(['docker', 'exec', s['daemon'], 'python3', '-c', script], text=True))


def store_size(s):
    script = 'import pathlib,json; p=pathlib.Path("/state/store"); print(json.dumps({x.name:{"logical":x.stat().st_size,"allocated":x.stat().st_blocks*512} for x in p.iterdir() if x.is_file()}))'
    return json.loads(subprocess.check_output(['docker', 'exec', s['server'], 'python3', '-c', script], text=True))


def call(s, label, method, *fields):
    return docker(label, 'exec', s['server'], 'timeout', '25', '/bins/cxn-noignore-driver', 'call', method, *fields)


def ctl(s, label, op, *args):
    return docker(label, 'exec', s['daemon'], 'timeout', '25', '/bins/' + s['arm'] + '/layerfs-remote', '/state/daemon.setup', op, *args)


def stats(s, label):
    _, text = ctl(s, label, 'stats')
    return {k: int(v) for k, v in re.findall(r'\("(roundTrips|uploadedObjects|uploadedBytes)", Int\((\d+)\)\)', text)}


def commit(s, label):
    before = dict(transport=proxy(s), store=store_size(s), stats=stats(s, label+'-before'))
    row, text = ctl(s, label, 'commit', s['workspace'], s['namespace'])
    after = dict(transport=proxy(s), store=store_size(s), stats=stats(s, label+'-after'))
    if not any(x in text for x in ('Committed', 'UpToDate')):
        raise RuntimeError('Commit did not acknowledge success: ' + text)
    record('commit', label=label, before=before, after=after, command_wall_ns=row['wall_ns'],
           product_wall_ns=int(re.search(r'wall_ns=(\d+)', text)[1]), sample_count=1)


def workload(s, label, command, limit=600):
    before = proxy(s)
    row, text = docker(label, 'exec', '--user', '1000:1000', '-e', 'HOME=/home/runner',
                       '-w', s['path'], s['daemon'], 'timeout', str(limit), 'bash', '-c', command,
                       limit=limit+5, check=False)
    record('workload', before=before, after=proxy(s), **row)
    if row['exit'] != 0:
        raise RuntimeError('workload failed: ' + label)
    return text


def start(repo):
    s = dict(repo=repo, arm='off', server='cxn-'+repo+'-server', daemon='cxn-'+repo+'-base',
             store='cxn-'+repo+'-store', local='cxn-'+repo+'-base-local')
    state_save(s)
    docker(repo+'-network', 'network', 'create', NETWORK)
    for key in ('store', 'local'):
        docker(repo+'-volume-'+key, 'volume', 'create', s[key])
    common = ['--platform', 'linux/arm64', '--network', NETWORK, '--init',
              '-v', 'cxi-target:/cache:ro', '-v', str(ROOT/'docs/mp2')+':/harness:ro',
              '-e', 'LAYERFS_CONSTRUCTION_WORKERS=1']
    docker(repo+'-server-create', 'run', '-d', '--name', s['server'], *common,
           '-v', s['store']+':/state', IMAGE, 'sleep', 'infinity')
    docker(repo+'-init', 'exec', s['server'], 'bash', '-c',
           'set -e; ln -s /cache/cxn-noignore01 /bins; mkdir -p /state/initial; '
           'chown 1000:1000 /state/initial; chmod 700 /state; timeout 10 /bins/cxn-noignore-driver init')
    call(s, repo+'-fork-base', 'branch.fork', 'name=base', 'from=main')
    docker(repo+'-server-start', 'exec', s['server'], 'bash', '-c',
           '/bins/off/layerfs-store --config /state/server.setup > /state/server.log 2>&1 &')
    ready(s['server'], '/state/server.log', 'REMOTE_STORE_READY')
    docker(repo+'-config-copy', 'run', '--rm', '--name', 'cxn-config', '--network', NETWORK,
           '-v', s['store']+':/source:ro', '-v', s['local']+':/state', IMAGE, 'bash', '-c',
           'set -e; cp /source/daemon.setup /state/daemon.setup; chmod 700 /state; '
           'sed -i "s/^server=.*/server=127.0.0.1:7900/" /state/daemon.setup')
    docker(repo+'-daemon-create', 'run', '-d', '--name', s['daemon'], *common,
           '--device', '/dev/fuse', '--cap-add', 'SYS_ADMIN', '--security-opt', 'apparmor=unconfined',
           '-v', s['local']+':/state', '-e', 'CXN_SERVER='+s['server'], IMAGE, 'sleep', 'infinity')
    docker(repo+'-proxy-start', 'exec', s['daemon'], 'bash', '-c',
           'ln -s /cache/cxn-noignore01 /bins; python3 /harness/no-ignore-proxy.py > /state/proxy.log 2>&1 &')
    ready(s['daemon'], '/state/proxy.log', 'PROXY_READY')
    docker(repo+'-daemon-start', 'exec', s['daemon'], 'bash', '-c',
           '/bins/off/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1 &')
    ready(s['daemon'], '/state/daemon.log', 'REMOTE_DAEMON_READY')
    _, branch = docker(repo+'-base-id', 'exec', s['server'], '/bins/cxn-noignore-driver', 'id', 'base')
    _, text = ctl(s, repo+'-mount-base', 'mount', branch.strip())
    match = re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)', text)
    s.update(zip(['path', 'workspace', 'namespace'], match.groups()))
    state_save(s)
    return s


def base(repo):
    s = start(repo)
    if repo.startswith('node'):
        url, sha = 'https://github.com/nestjs/nest.git', '35c3ded6dbf3f23f917ae88d0ed966932788cae6'
        clone = f'git init . && git remote add origin {url} && git fetch --depth=1 origin {sha} && git checkout --detach FETCH_HEAD'
        workload(s, repo+'-clone', clone, 120)
        workload(s, repo+'-rules', 'printf "%%include .gitignore\\n" > .lww; printf "\\n/.lww\\n" >> .git/info/exclude', 10)
        workload(s, repo+'-install', 'npm ci --registry=https://registry.npmjs.org --no-audit --no-fund', 600)
        workload(s, repo+'-build', 'npm run build', 300)
        commit(s, repo+'-base-commit')
        workload(s, repo+'-count', 'python3 -c \'import os,json; n=b=0\nfor r,ds,fs in os.walk("."):\n for f in fs:\n  p=os.path.join(r,f)\n  if not os.path.islink(p): n+=1;b+=os.stat(p).st_size\nprint(json.dumps({"files":n,"bytes":b}))\'', 25)
    else:
        raise ValueError('Maven base not yet invoked')


if __name__ == '__main__':
    try:
        base(sys.argv[1])
    except BaseException as error:
        record('failure', error=str(error), disposition='STOP; no product repair or workload replay')
        raise
