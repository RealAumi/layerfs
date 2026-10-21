"""Prepare M03 immutable workloads and a native compiler oracle; never execute SDK operations."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
source = root / 'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input'
case = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/M03-build-1'
case.mkdir(parents=True)
work = case / 'workloads'
work.mkdir()
oracle = case / 'oracle'
oracle.mkdir()
outputs = [
    'packages/util/brand/lib/types/index.js',
    'packages/util/brand/lib/types/index.js.map',
    'packages/util/brand/lib/types/index.d.ts',
    'packages/util/brand/lib/types/index.d.ts.map',
    'packages/util/brand/lib/tsconfig.tsbuildinfo',
]

def sha(data):
    return hashlib.sha256(data).hexdigest()

# This host-only preparation reads the complete independent input. Every compiler
# write is intercepted into the new oracle directory; no input/output is removed.
oracle_program = r'''
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const source = process.argv[2];
const destination = process.argv[3];
const expected = JSON.parse(process.argv[4]);
process.chdir(source);
const ts = require(path.join(source, 'node_modules/typescript/lib/typescript.js'));
const diagnostics = [];
const host = ts.createSolutionBuilderHost(ts.sys, undefined, d => diagnostics.push(ts.flattenDiagnosticMessageText(d.messageText, '\n')));
const writes = [];
host.writeFile = (file, text, bom) => {
  const relative = path.relative(source, path.resolve(file)).split(path.sep).join('/');
  if (!expected.includes(relative)) throw new Error('Unexpected compiler write: ' + relative);
  const target = path.join(destination, relative);
  fs.mkdirSync(path.dirname(target), {recursive:true});
  fs.writeFileSync(target, (bom ? '\uFEFF' : '') + text);
  writes.push(relative);
};
const exit = ts.createSolutionBuilder(host, ['packages/util/brand/tsconfig.json'], {force:true, pretty:false}).build();
if (exit !== 0 || diagnostics.length || JSON.stringify([...writes].sort()) !== JSON.stringify([...expected].sort())) throw new Error(JSON.stringify({exit, diagnostics, writes}));
console.log(JSON.stringify({node:process.version, platform:process.platform, arch:process.arch, compiler:ts.version, exit, diagnostics, writes}));
'''
(case / 'oracle-prepare.cjs').write_text(oracle_program)
node = os.environ.get('ISSUE323_ORACLE_NODE', '/usr/local/bin/node')
argv = [node, str(case / 'oracle-prepare.cjs'), str(source), str(oracle), json.dumps(outputs)]
receipt = subprocess.run(argv, capture_output=True, timeout=120, check=False)
(case / 'oracle-preparation.stdout').write_bytes(receipt.stdout)
(case / 'oracle-preparation.stderr').write_bytes(receipt.stderr)
if receipt.returncode:
    raise SystemExit(f'Native oracle preparation failed: {receipt.returncode}; retained raw streams')
preparation = json.loads(receipt.stdout)
assert preparation['compiler'] == '6.0.3'

# Campaign-owned focused tests of the actual emitted real package. This is not
# the repository Vitest suite, which needs additional compatible native assets.
test = '''import { test } from 'node:test';
import assert from 'node:assert/strict';
import { brandString, brandNumber } from '../packages/util/brand/lib/types/index.js';
test('source-contract branded strings retain values and JSON behavior', () => {
  for (const value of ['', 'session-1', 'λ/relative']) {
    assert.equal(brandString(value), value);
    assert.equal(JSON.stringify(brandString(value)), JSON.stringify(value));
  }
});
test('source-contract branded numbers retain values and JSON behavior', () => {
  for (const value of [7, 0, -1, 42.5, Number.MAX_SAFE_INTEGER]) {
    assert.equal(brandNumber(value), value);
    assert.equal(JSON.stringify(brandNumber(value)), JSON.stringify(value));
  }
  assert.ok(Object.is(brandNumber(-0), -0));
  assert.ok(Number.isNaN(brandNumber(NaN)));
});
'''
(case / 'runtime.test.mjs').write_text(test)
expected_outputs = {p: {'sha256': sha((oracle / p).read_bytes()), 'bytes': (oracle / p).stat().st_size} for p in outputs}
info = json.loads((oracle / outputs[-1]).read_text())
assert info['version'] == '6.0.3'
info_parent = (source / outputs[-1]).parent
inputs = set(['package.json', 'pnpm-lock.yaml', 'tsconfig.base.json', 'packages/util/brand/tsconfig.json', 'packages/util/brand/package.json', 'packages/util/brand/src/index.ts', 'packages/util/brand/tests/brand.spec.ts', 'packages/util/brand/lib/index.js', 'node_modules/typescript/package.json', 'node_modules/typescript/bin/tsc', 'node_modules/typescript/lib/tsc.js', 'node_modules/typescript/lib/_tsc.js', 'node_modules/typescript/lib/typescript.js'])
for file in info['fileNames']:
    # Preserve symlink-facing pnpm paths as recorded by the compiler.
    inputs.add(os.path.relpath(os.path.normpath(info_parent / file), source))
input_hashes = {p: sha((source / p).read_bytes()) for p in sorted(inputs)}
links = {p: os.readlink(source / p) for p in ['node_modules/typescript', 'packages/util/brand/node_modules/@deepseek-ai/cordis']}

# All destination writes occur in the mounted project's SDK-launched command.
encoded = base64.b64encode(test.encode()).decode()
mutation = f'''set -eu
# Explicit experiment watchdog; ordinary product Exec has no runtime timeout.
timeout 15s bash -eu -o pipefail <<'BUILD_M03'
python3 - <<'PREPARE_MOUNT'
from pathlib import Path
import base64
outputs={outputs!r}
for name in outputs:
 p=Path(name)
 assert p.is_file() and not p.is_symlink(), name
p=Path(".issue323-build")
p.mkdir()
(p/"runtime.test.mjs").write_bytes(base64.b64decode({encoded!r}))
for name in outputs:Path(name).unlink()
print("Removed exactly five selected preexisting generated outputs; source/dependencies preserved", flush=True)
PREPARE_MOUNT
node ./node_modules/typescript/bin/tsc -b packages/util/brand/tsconfig.json --force --pretty false
BUILD_M03
'''
(work / 'mutate.sh').write_text(mutation)
(work / 'test.sh').write_text('set -eu\ntimeout 15s node --test .issue323-build/runtime.test.mjs\n')

verify = f'''from pathlib import Path
import hashlib,json,os
expected={expected_outputs!r}
inputs={input_hashes!r}
links={links!r}
for path, facts in expected.items():
 p=Path(path);assert p.is_file() and not p.is_symlink(),path
 data=p.read_bytes();assert len(data)==facts['bytes'],path
 assert hashlib.sha256(data).hexdigest()==facts['sha256'],path
for path, expected_hash in inputs.items():
 assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected_hash,path
for path,target in links.items():
 assert Path(path).is_symlink(),path
 assert os.readlink(path)==target,path
assert Path('node_modules/typescript').resolve()==Path('node_modules/.pnpm/typescript@6.0.3/node_modules/typescript').resolve()
assert Path('packages/util/brand/node_modules/@deepseek-ai/cordis').resolve()==Path('vendor/cordis').resolve()
assert {{p.name for p in Path('packages/util/brand/lib/types').iterdir()}}=={{'index.js','index.js.map','index.d.ts','index.d.ts.map'}}
assert {{p.name for p in Path('.issue323-build').iterdir()}}=={{'runtime.test.mjs'}}
assert hashlib.sha256(Path('.issue323-build/runtime.test.mjs').read_bytes()).hexdigest()=={sha(test.encode())!r}
info=json.loads(Path('packages/util/brand/lib/tsconfig.tsbuildinfo').read_text())
assert info['version']=='6.0.3'
assert info['options']=={info['options']!r}
assert info['fileNames']=={info['fileNames']!r}
assert info['root']=={info['root']!r}
assert not info.get('errors')
assert not info.get('affectedFilesPendingEmit')
for mapping in ['index.js.map','index.d.ts.map']:
 m=json.loads(Path('packages/util/brand/lib/types',mapping).read_text())
 assert m['sources']==['../../core/src/index.ts']
print('PASS independent native-compiler exact five-output hashes, metadata, unchanged source/config/compiler/type inputs, pnpm/workspace links and saved campaign test')
'''
for label in ['verify-before', 'verify', 'verify-fresh']:
    (work / (label + '.sh')).write_text("set -eu\ntimeout 9s python3 - <<'VERIFY_M03'\n" + verify + 'VERIFY_M03\n')
plan = {
    'case': 'M03', 'scope': 'Actual TypeScript package compilation plus campaign-owned Node built-in tests; existing Vitest suite NOT_RUN',
    'source': subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
    'input': str(source), 'root_engine': json.loads((source/'package.json').read_text())['engines']['node'],
    'cache': 'Natural/setup warmth; functional only; no performance sample',
    'profile': 'Disposable/WAL/synchronous=OFF', 'durable': 'NOT_RUN — disabled by owner until explicit reauthorization',
    'construction_workers': 1, 'outer_limit_s':120,'workload_limit_s':15,'verifier_limit_s':9,
    'dependency_preparation': 'Locally transported preinstalled dependencies; installation simulated through prepared state.',
    'compile_argv':['node','./node_modules/typescript/bin/tsc','-b','packages/util/brand/tsconfig.json','--force','--pretty','false'],
    'test_argv':['node','--test','.issue323-build/runtime.test.mjs'],
    'oracle_preparation': {'argv':argv,'host_result':preparation,'boundary':'Read-only compiler inputs; intercepted writeFile to fresh host oracle only; native host oracle is preparation and not mounted workload execution.'},
    'expected_outputs': expected_outputs, 'input_hashes': input_hashes, 'symlinks':links,
    'runtime_test_sha256':sha(test.encode()),
    'workloads': {p.name:sha(p.read_bytes()) for p in sorted(work.iterdir())},
    'call_sequence':'Project init/create or exactly matching sealed Project reuse; mount; mutate Exec; test Exec; verify-before Exec; Commit once; verify Exec; unmount; fresh mount; verify-fresh Exec; history; UpToDate; normal unmount; close',
    'publication':'Original known Committed or failure retained; stop dependent operations on failure; no replay',
}
(case/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({'case':str(case),'output_count':len(outputs),'input_pin_count':len(input_hashes),'workloads':plan['workloads']}))
