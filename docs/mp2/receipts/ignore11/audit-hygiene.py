"""Audit only this campaign's receipts; never inventory another job's resources."""
import json
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parent
# Literal grep of the actual home, without recording that private search term.
grep = subprocess.run(['rg', '-l', '-F', str(pathlib.Path.home()), str(root)], capture_output=True, text=True)
assert grep.returncode in (0, 1)
home_files = grep.stdout.splitlines()
resources = []

def resource(kind, name):
    resources.append((kind, name))

rows = [json.loads(line) for line in (root / 'e2e-receipts.jsonl').read_text().splitlines()]
for path in root.rglob('*.command.json'):
    row = json.loads(path.read_text())
    row['output'] = path.with_name(path.name.removesuffix('.command.json')).read_text()
    rows.append(row)
for row in rows:
    args = row['command']
    if not args or args[0] != 'docker':
        continue
    a = args[1:]
    if a[:1] == ['--context']:
        a = a[2:]
    if a[0] == 'ps' or a[:2] in (['network', 'ls'], ['volume', 'ls']):
        assert '--filter' in a and a[a.index('--filter') + 1] == 'name=cxi-'
        for name in row['output'].split():
            resource('listed', name)
    elif a[0] == 'run':
        resource('container', a[a.index('--name') + 1])
        if '--network' in a and a[a.index('--network') + 1] != 'none':
            resource('network', a[a.index('--network') + 1])
        for i, arg in enumerate(a[:-1]):
            if arg == '-v':
                source = a[i + 1].split(':')[0]
                if not source.startswith(('/', '~')):
                    resource('volume', source)
    elif a[0] == 'exec':
        i = 1
        while a[i] in ('-e', '-w'):
            i += 2
        resource('container', a[i])
    elif a[0] == 'network':
        if a[1] in ('create', 'rm'):
            resource('network', a[-1])
        elif a[1] == 'connect':
            resource('network', a[-2])
            resource('container', a[-1])
        else:
            raise AssertionError(a)
    elif a[0] == 'volume':
        assert a[1] in ('create', 'rm')
        resource('volume', a[-1])
    elif a[0] == 'cp':
        resource('container', a[1].split(':')[0])
    elif a[0] in ('rm', 'kill', 'start'):
        resource('container', a[-1])
    else:
        raise AssertionError(a)
for kind in ('containers', 'networks', 'volumes'):
    for name in (root / f'cleanup-{kind}.log').read_text().split():
        resource(kind, name)
for line in (root / 'mount-control-samples.jsonl').read_text().splitlines():
    resource('container', json.loads(line)['container'])
# Also literal-grep each observed resource token: every recorded resource must
# begin with the job's prefix. Filesystem fixture paths and image names are not
# container/network/volume identities.
bad = sorted(set(name for _, name in resources if not re.fullmatch(r'cxi-[A-Za-z0-9_.-]+', name)))
for name in bad:
    subprocess.run(['rg', '-l', '-F', name, str(root)], capture_output=True, text=True, check=False)
result = dict(home_path_files=len(home_files), non_cxi_resource_names=len(bad),
              resource_references_checked=len(resources), unique_resources=sorted(set(name for _, name in resources)),
              scope='all new receipt files for home grep; all Docker command/listing and mount-control resource identities')
print(json.dumps(result, indent=2))
assert not home_files and not bad, 'receipt hygiene failed'
