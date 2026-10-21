#!/usr/bin/env python3
"""Local, append-only build preparation for noignore01. Never runs workloads."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/mp2/receipts/noignore01'
HOME = pathlib.Path.home()
IMAGE = 'public.ecr.aws/docker/library/rust@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4'


def run(label, args):
    path = OUT / (label + '.log')
    start = time.monotonic_ns()
    with path.open('x') as log:
        result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT)
    record = {'label': label, 'command': [str(a).replace(str(HOME), '~') for a in args],
              'wall_ns': time.monotonic_ns() - start, 'exit': result.returncode,
              'output': path.name, 'sample_count': 1, 'phase': 'preparation'}
    with (OUT / 'preparation-commands.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    print(json.dumps(record), flush=True)
    return result.returncode


if __name__ == '__main__':
    import sys
    arm = sys.argv[1]
    assert arm in ('off', 'on')
    source = ROOT if arm == 'off' else HOME / 'Developer/cxn-ignore-source-noignore01'
    command = ['docker', 'run', '--rm', '--name', 'cxn-build-' + arm,
               '--network', 'cxn-build-net', '--platform', 'linux/arm64',
               '-v', str(source) + ':/src-' + arm + ':ro', '-v', 'cxi-target:/target', '-w', '/src-' + arm,
               '-e', 'CARGO_TARGET_DIR=/target/cxn-noignore01/cargo-' + arm, '-e', 'CARGO_HOME=/target/cargo-home',
               '-e', 'CARGO_TERM_COLOR=never', IMAGE, 'bash', '-c',
               'set -e; rustc --version; cargo --version; cargo build --manifest-path core/Cargo.toml '
               '--locked --release -j 2 -p layerfs-daemon --bin layerfs-remote-daemon '
               '-p layerfs-remote-store --bins; '
               'mkdir -p /target/cxn-noignore01/' + arm + '; '
               'cp /target/cxn-noignore01/cargo-' + arm + '/release/layerfs-remote-daemon /target/cxn-noignore01/cargo-' + arm + '/release/layerfs-store '
               '/target/cxn-noignore01/cargo-' + arm + '/release/layerfs-remote /target/cxn-noignore01/' + arm + '/; '
               'sha256sum /target/cxn-noignore01/' + arm + '/*']
    sys.exit(run('build-' + arm + '-isolated-target', command))
