"""Freeze diagnostic native/FUSE workloads and exact independent state oracle."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/performance-1'
base.mkdir(parents=True, exist_ok=True)
work = base / 'workloads'
work.mkdir()
fixture = root / 'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input'
compiled_plan = json.loads((root / 'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/M03-build-2/plan.json').read_text())

def sha(data):
    return hashlib.sha256(data).hexdigest()

input_hashes = compiled_plan['input_hashes']
input_bytes = {p: (fixture / p).stat().st_size for p in input_hashes}
outputs = compiled_plan['expected_outputs']
read_digest = hashlib.sha256()
for p, h in sorted(input_hashes.items()):
    read_digest.update(p.encode() + b'\0' + bytes.fromhex(h))
read_expected = read_digest.hexdigest()

# The oracle constructs final bytes independently, before any measured operation.
mutation_files = {}
for i in range(128):
    data = bytes([i]) * 1024
    if 32 <= i < 64:
        continue
    name = f'renamed-{i:03d}' if i < 32 else f'file-{i:03d}'
    mutation_files[name] = {'bytes': len(data), 'sha256': sha(data)}
payload = bytes((i * 17 + 3) % 256 for i in range(65536))
payload = payload[:32768] + bytes((i * 29 + 5) % 256 for i in range(4096)) + payload[36864:] + bytes((i * 19 + 7) % 256 for i in range(8192))
payload = payload[:49152] + bytes(81920 - 49152)
mutation_files['payload'] = {'bytes': len(payload), 'sha256': sha(payload)}
mutation_files['editor'] = {'bytes': len(b'issue323-perf-editor\n'), 'sha256': sha(b'issue323-perf-editor\n')}

read = f'''import hashlib,json,os,time
from pathlib import Path
paths={sorted(input_hashes)!r}
start=time.monotonic_ns()
aggregate=hashlib.sha256();byte_count=0
for path in paths:
 p=Path(path);before=p.stat();h=hashlib.sha256()
 with p.open('rb') as stream:
  while chunk:=stream.read(131072):
   byte_count+=len(chunk);h.update(chunk)
 assert p.stat().st_size==before.st_size,path
 aggregate.update(path.encode()+b'\\0'+h.digest())
end=time.monotonic_ns()
print(json.dumps({{'operation':'read','elapsed_ns':end-start,'files':len(paths),'bytes':byte_count,'read_window_bytes':131072,'aggregate_sha256':aggregate.hexdigest()}}),flush=True)
'''
mutation = '''import json,os,time
from pathlib import Path
start=time.monotonic_ns()
p=Path('.issue323-perf');p.mkdir()
for i in range(128):
 (p/f'file-{i:03d}').write_bytes(bytes([i])*1024)
for i in range(32):
 os.rename(p/f'file-{i:03d}',p/f'renamed-{i:03d}')
for i in range(32,64):
 (p/f'file-{i:03d}').unlink()
with (p/'payload').open('wb') as f:
 f.write(bytes((i*17+3)%256 for i in range(65536)))
with (p/'payload').open('r+b') as f:
 f.seek(32768);f.write(bytes((i*29+5)%256 for i in range(4096)))
with (p/'payload').open('ab') as f:f.write(bytes((i*19+7)%256 for i in range(8192)))
with (p/'payload').open('r+b') as f:
 f.truncate(49152);f.truncate(81920)
(p/'editor.tmp').write_bytes(b'issue323-perf-editor\\n')
os.replace(p/'editor.tmp',p/'editor')
end=time.monotonic_ns()
print(json.dumps({'operation':'mutation','elapsed_ns':end-start,'created_small_files':128,'renamed_small_files':32,'deleted_small_files':32,'final_regular_files':98,'payload_bytes':81920,'logical_write_bytes':208917,'final_logical_bytes':180245,'truncate_bytes':49152,'regrow_bytes':81920}),flush=True)
'''
compile_body = f'''import json,subprocess,time
from pathlib import Path
outputs={list(outputs)!r}
start=time.monotonic_ns()
for name in outputs:
 p=Path(name);assert p.is_file() and not p.is_symlink(),name
for name in outputs:Path(name).unlink()
argv=['node','./node_modules/typescript/bin/tsc','-b','packages/util/brand/tsconfig.json','--force','--pretty','false']
# stdout/stderr flow directly through the original SDK streams, never captured.
result=subprocess.run(argv,check=False)
end=time.monotonic_ns()
print(json.dumps({{'operation':'compile','elapsed_ns':end-start,'exit_code':result.returncode,'removed_generated_outputs':len(outputs),'argv':argv}}),flush=True)
raise SystemExit(result.returncode)
'''

# Starting cwd is always the acknowledged mount. Native arm changes only its
# ordinary process cwd to the explicit plain-volume prepared root.
def emit(name, body, limit):
    (work / (name + '.sh')).write_text(f'''set -eu
cd "${{ISSUE323_FS_ROOT:-.}}"
timeout {limit}s python3 - <<'ISSUE323_WORKLOAD'
{body}ISSUE323_WORKLOAD
''')

emit('read', read, 15)
emit('mutation', mutation, 15)
emit('compile', compile_body, 15)

verify = f'''from pathlib import Path
import hashlib,json,os
inputs={input_hashes!r}
outputs={outputs!r}
mutation={mutation_files!r}
for name,h in inputs.items():
 assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
for name,facts in outputs.items():
 p=Path(name);assert p.is_file() and not p.is_symlink(),name
 b=p.read_bytes();assert len(b)==facts['bytes'],name
 assert hashlib.sha256(b).hexdigest()==facts['sha256'],name
p=Path('.issue323-perf');assert {{x.name for x in p.iterdir()}}==set(mutation)
logical=allocated=0
for name,facts in mutation.items():
 f=p/name;assert f.is_file() and not f.is_symlink(),name
 b=f.read_bytes();assert len(b)==facts['bytes'],name
 assert hashlib.sha256(b).hexdigest()==facts['sha256'],name
 s=f.stat();logical+=s.st_size;allocated+=s.st_blocks*512
for path,target in {compiled_plan['symlinks']!r}.items():assert os.readlink(path)==target,path
assert Path('node_modules/typescript').resolve()==Path('node_modules/.pnpm/typescript@6.0.3/node_modules/typescript').resolve()
assert Path('packages/util/brand/node_modules/@deepseek-ai/cordis').resolve()==Path('vendor/cordis').resolve()
assert {{x.name for x in Path('packages/util/brand/lib/types').iterdir()}}=={{'index.js','index.js.map','index.d.ts','index.d.ts.map'}}
print(json.dumps({{'verification':'PASS','selected_input_files':len(inputs),'compiler_outputs':len(outputs),'mutation_regular_files':len(mutation),'mutation_logical_bytes':logical,'mutation_observed_st_blocks_bytes':allocated,'allocation_scope':'selected mutation files only; st_blocks implementation/platform dependent; global Store unavailable'}}),flush=True)
'''
emit('verify', verify, 9)
emit('verify-fresh', verify, 9)

# Source tree comes from the image's independent complete master, not a mounted
# Workspace. The measured scripts are not run during preparation.
clone = '''set -eu
timeout 40s bash -eu -o pipefail <<'NATIVE_CLONE'
test -d /native-master
test -d /layerfs-store/native-run
test -z "$(find /layerfs-store/native-run -mindepth 1 -maxdepth 1 -print -quit)"
cp -a /native-master/. /layerfs-store/native-run/
NATIVE_CLONE
'''
(work / 'native-clone.sh').write_text(clone)

# Full native census is setup/storage evidence, never a cold predicate. It reads
# metadata and link text without pre-reading compiler/read workload bytes.
census = '''import json,os,stat,time
root='/layerfs-store/native-run'
start=time.monotonic_ns();regular=directories=symlinks=logical=allocated=0
hardlink_groups={};stack=[root]
while stack:
 directory=stack.pop()
 with os.scandir(directory) as entries:
  for entry in entries:
   s=entry.stat(follow_symlinks=False)
   if stat.S_ISDIR(s.st_mode):directories+=1;stack.append(entry.path)
   elif stat.S_ISLNK(s.st_mode):symlinks+=1;os.readlink(entry.path)
   elif stat.S_ISREG(s.st_mode):
    regular+=1;logical+=s.st_size;allocated+=s.st_blocks*512
    if s.st_nlink>1:hardlink_groups[(s.st_dev,s.st_ino)]=s.st_nlink
   else:raise RuntimeError('unsupported prepared file type: '+entry.path)
end=time.monotonic_ns()
print(json.dumps({'preparation':'native-census','elapsed_ns':end-start,'regular_files':regular,'directories_excluding_root':directories,'symlinks':symlinks,'logical_regular_bytes':logical,'sum_path_st_blocks_bytes':allocated,'hardlink_groups':len(hardlink_groups),'allocation_scope':'sum per-path regular-file st_blocks; hardlink allocation can be counted multiple times; no cold claim; no Store access'}),flush=True)
'''
# Full setup census has its own frozen bound; outside performance comparisons.
emit('native-census', census, 15)

oracle = {'input_hashes':input_hashes,'input_bytes':input_bytes,'read':{'files':len(input_hashes),'bytes':sum(input_bytes.values()),'aggregate_sha256':read_expected},'compiler_outputs':outputs,'mutation_files':mutation_files,'mutation_final_logical_bytes':sum(v['bytes'] for v in mutation_files.values())}
(base/'oracle.json').write_text(json.dumps(oracle,indent=2)+'\n')
fixture_identity = fixture.parent/'fixture.json'
plan = {
 'issue':323,'case':'prospective diagnostic native/FUSE file access and public SDK operation timing',
 'source':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
 'fixture':str(fixture),'fixture_receipt_sha256':sha(fixture_identity.read_bytes()),
 'oracle_sha256':sha((base/'oracle.json').read_bytes()),'oracle_origin':'M03-build-2 independent host TS6.0.3 five-output oracle plus source-derived immutable input hashes and separately constructed mutation bytes',
 'mutation_constants':{'small_files':128,'small_file_bytes':1024,'rename_indices':'0..31','delete_indices':'32..63','payload_initial_bytes':65536,'payload_initial_pattern':'(i*17+3)%256','overwrite_offset':32768,'overwrite_bytes':4096,'overwrite_pattern':'(i*29+5)%256','append_bytes':8192,'append_pattern':'(i*19+7)%256','truncate_bytes':49152,'regrow_bytes':81920,'editor_token':'issue323-perf-editor\n','logical_write_bytes':208917},
 'order':['native read','FUSE read','native mutation','FUSE mutation','native compile','FUSE compile','FUSE Commit once','native verify','FUSE same-mount verify','normal unmount','fresh mount','FUSE fresh verify','history/UpToDate','normal unmount','SDK close'],
 'samples':1,'cache_eligibility':'INCOMPLETE/INELIGIBLE for numeric performance comparison; natural/setup warmth; metadata setup census recorded; no pretouch or pre-run; no ratios or faster/slower verdict',
 'root_selection':{'FUSE':'.','native':'/layerfs-store/native-run','environment':'ISSUE323_FS_ROOT'},
 'native_preparation':'SDK Exec cp -a from independent image /native-master into command-UID501-owned empty native-run on existing plain local Store volume; outside measured work; no protected global Store access',
 'preparation_budgets_s':{'clone':40,'native_census':15},'command_limit_s':15,'verifier_limit_s':9,'driver_outer_limit_s':120,
 'verification':'After all measured commands and known Commit; every selected input and five generated outputs plus exact98 mutation files; selected-state only, not complete mounted byte census',
 'profile':'Disposable/WAL/synchronous=OFF','durable':'NOT_RUN — disabled by owner until explicit reauthorization','construction_workers':1,
 'dependency_preparation':'Locally transported preinstalled dependencies; installation simulated through prepared state.',
 'root_node_engine':compiled_plan['root_engine'],
 'timing_scope':'Host public SDK call spans separately; Linux batch monotonic_ns includes all declared syscall/hash/compiler work; verification separate; no summing nested/overlapping spans; native Commit/mount/install/unmount N/A',
 'storage_scope':'Native complete metadata census sum per-path logical/st_blocks and hardlink-group count separately; selected mutation allocation after timing; global protected Store storage UNAVAILABLE unless publicSDK observer supplies it',
 'workloads':{p.name:sha(p.read_bytes()) for p in sorted(work.iterdir())},
 'image_daemon_harness_identity':'Caller must pin final qualified image/runtime/daemon/build/driver before sample',
}
(base/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({'case':str(base),'read':oracle['read'],'mutation_files':len(mutation_files),'mutation_logical_bytes':oracle['mutation_final_logical_bytes'],'workloads':plan['workloads']}))
