#!/usr/bin/env python3
"""Audit published receipts, including losslessly compressed terminal logs."""
import gzip
import json
import os
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
RECEIPTS = ROOT / 'receipts/noignore01'
OUTPUT = RECEIPTS / 'attempt2/hygiene.json'


def resource_names(command):
    if not command or command[0] != 'docker':
        return []
    names = []
    action = command[1]
    if action == 'run':
        for index, arg in enumerate(command[:-1]):
            value = command[index + 1]
            if arg == '--name':
                names.append(value)
            elif arg == '--network' and value != 'none':
                names.append(value)
            elif arg == '-v':
                source = value.split(':')[0]
                if not source.startswith(('/', '~')):
                    names.append(source)
    elif action in ('exec', 'cp'):
        # Exec options have values; inspect the known first container argument.
        index = 2
        while index < len(command) and command[index].startswith('-'):
            index += 2 if command[index] in ('--user', '-u', '-e', '-w', '--workdir') else 1
        if index < len(command):
            names.append(command[index].split(':')[0])
    elif action in ('rm', 'stop', 'kill', 'inspect'):
        index = 2
        while index < len(command):
            if command[index] in ('-t', '--time', '-s', '--signal', '--format'):
                index += 2
            elif command[index].startswith('-'):
                index += 1
            else:
                names.append(command[index]); index += 1
    elif action in ('network', 'volume') and len(command) > 3:
        if command[2] in ('create', 'rm', 'inspect'):
            names.append(command[3])
    return names


def commands(value):
    if isinstance(value, dict):
        if isinstance(value.get('command'), list):
            yield value['command']
        for item in value.values():
            yield from commands(item)
    elif isinstance(value, list):
        for item in value:
            yield from commands(item)


def main():
    texts = []
    resources = set()
    for path in sorted(RECEIPTS.rglob('*')):
        if not path.is_file() or path == OUTPUT:
            continue
        content = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
        text = content.decode()
        texts.append(text)
        values = []
        if path.suffix == '.json' and text.strip():
            values = [json.loads(text)]
        elif path.suffix == '.jsonl':
            values = [json.loads(line) for line in text.splitlines()]
        for value in values:
            for command in commands(value):
                resources.update(resource_names(command))
    with tempfile.NamedTemporaryFile(mode='w', prefix='cxn-hygiene-') as text_file:
        text_file.write('\n'.join(texts))
        text_file.flush()
        home = subprocess.run(['rg', '-c', '-F', str(pathlib.Path.home()), text_file.name], capture_output=True, text=True)
        # Internal identifiers are rejected, not included in the receipt. The
        # operator supplies their pattern; it is never committed.
        internal = subprocess.run(['rg', '-ci', os.environ['HYGIENE_INTERNAL_PATTERNS'], text_file.name], capture_output=True, text=True)
    bad = sorted(name for name in resources if not (name.startswith('cxn-') or name == 'cxi-target'))
    result = dict(home_path_matches=int(home.stdout.strip() or '0'),
                  out_of_prefix_resource_names=len(bad),
                  internal_host_platform_matches=int(internal.stdout.strip() or '0'),
                  named_resources=sorted(resources),
                  method='rg over all receipt text and decompressed logs; structured Docker command resource extraction',
                  disallowed_resources=bad)
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    assert not any(result[key] for key in ('home_path_matches', 'out_of_prefix_resource_names', 'internal_host_platform_matches'))


if __name__ == '__main__':
    main()
