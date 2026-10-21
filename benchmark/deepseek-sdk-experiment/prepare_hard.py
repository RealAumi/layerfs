import sys
from pathlib import Path
import hashlib,json
root=Path.cwd();base=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/checkpoints-1';base.mkdir(parents=True,exist_ok=True);src=root/'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input';small='packages/util/brand/src/index.ts';original=(src/small).read_bytes()
def sha(b):return hashlib.sha256(b).hexdigest()
def setup(name):
 case=base/name;case.mkdir();work=case/'workloads';work.mkdir();return case,work
def script(work,name,body,limit=9):
 (work/(name+'.sh')).write_text(f"set -eu\ntimeout {limit}s python3 - <<'WORKLOAD_PY'\n"+body+'WORKLOAD_PY\n')
def seal(case,work,plan):
 plan.update({'case':case.name,'outer_limit_s':120,'workload_limit_s':15,'verifier_limit_s':9,'cache':'natural/setup warmth; functional only','workloads':{p.name:sha(p.read_bytes()) for p in work.iterdir()}});(case/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
case,work=setup('H02');payload=b''.join(hashlib.sha256(i.to_bytes(8,'little')).digest() for i in range(524288));later=payload[:8192]+b'B'*4096+payload[12288:]
script(work,'mutate',"from pathlib import Path\nimport hashlib\np=Path('.issue323-capture');p.mkdir()\nwith (p/'payload').open('wb') as f:\n for i in range(524288):f.write(hashlib.sha256(i.to_bytes(8,'little')).digest())\nprint('initial 16MiB payload published')\n",15)
(work/'writer.py').write_text("from pathlib import Path\nimport os,sys\nassert sys.stdin.readline()=='write-later\\n'\nfd=os.open('.issue323-capture/payload',os.O_WRONLY)\ntry:assert os.pwrite(fd,b'B'*4096,8192)==4096\nfinally:os.close(fd)\nPath('.issue323-capture/late').write_bytes(b'late\\n')\nprint('later4096B write and marker published',flush=True)\n")
for name,expected,haslate in [('verify-captured',payload,False),('verify-later',later,True),('verify-later-installed',later,True),('verify-later-fresh',later,True)]:
 body=f"from pathlib import Path\nimport hashlib\np=Path('.issue323-capture/payload');assert p.stat().st_size==16777216\nwith p.open('rb') as f:\n h=hashlib.sha256()\n while b:=f.read(131072):h.update(b)\nassert h.hexdigest()=={sha(expected)!r}\nassert Path('.issue323-capture/late').exists()=={haslate}\n"
 if haslate:body+="assert Path('.issue323-capture/late').read_bytes()==b'late\\n'\n"
 body+="print('PASS exact frontier bytes, length and late-marker membership')\n";script(work,name,body)
seal(case,work,{'payload_bytes':len(payload),'captured_sha256':sha(payload),'later_sha256':sha(later),'later_write':{'offset':8192,'bytes':4096},'synchronization':'SDK stdin released 100ms after driver begins first Commit call; require writer actual exit observed before first Commit reply and independently verify first captured root excludes later bytes. No product hooks.','qualification':'No exact kernel capture/install timestamp claim; saved-frontier and returned-operation interleaving are checked.'})
case,work=setup('H03');expect={}
for letter in ['a','b']:
 marker=f'\n// Issue 323 isolated Branch {letter}\n'.encode();token=f'branch-{letter}\n'.encode();expect[letter]={'source_sha256':sha(original+marker),'token':token.decode()}
 body=f'''from pathlib import Path
import time,os
start=time.monotonic_ns()
time.sleep(1)
p=Path('.issue323-isolation');p.mkdir()
(p/'token').write_bytes({token!r})
os.link(p/'token',p/'alias')
os.symlink('token',p/'link')
src=Path({small!r});tmp=src.with_suffix('.issue323-tmp');tmp.write_bytes(src.read_bytes()+{marker!r});os.chmod(tmp,0o644);os.replace(tmp,src)
end=time.monotonic_ns();print(start,end)
''';script(work,'mutate-'+letter,body,15)
 verify=f'''from pathlib import Path
import os,hashlib
p=Path('.issue323-isolation');assert {{x.name for x in p.iterdir()}}=={{'token','alias','link'}}
assert (p/'token').read_bytes()=={token!r};assert (p/'alias').read_bytes()=={token!r};assert (p/'link').read_bytes()=={token!r}
assert os.readlink(p/'link')=='token';assert (p/'token').stat().st_ino==(p/'alias').stat().st_ino;assert (p/'token').stat().st_nlink==2
assert hashlib.sha256(Path({small!r}).read_bytes()).hexdigest()=={sha(original+marker)!r}
assert not Path({small!r}).with_suffix('.issue323-tmp').exists()
print('PASS isolated source, exact names/bytes, hardlink identity and symlink')
'''
 for label in ['verify-'+letter,'verify-'+letter+'-fresh']:script(work,label,verify)
seal(case,work,{'branches':2,'workspaces':2,'sandboxes':1,'expected':expect,'overlap':'Both command monotonic lifetime intervals from same Linux kernel must overlap; this does not claim simultaneous SQL writes or Commit overlap.'})
case,work=setup('H04');expect={}
for n in range(6):
 marker=f'\n// Issue 323 sustained cycle {n}\n'.encode();want=original+marker;expect[str(n)]=sha(want)
 body=f'''from pathlib import Path
import os,sys
p=Path('.issue323-cycles')
if {n}==0:
 p.mkdir();(p/'shared').write_bytes(b'initial');os.link(p/'shared',p/'alias')
else:
 for old in list(p.iterdir()):
  if old.name not in ('shared','alias'):old.unlink()
(p/'shared').write_bytes(bytes([{n}])*4096)
for i in range(16):(p/f'{n}-{{i}}').write_bytes(bytes([({n}*17+i)%251])*1024)
for i in range(5):(p/f'{n}-{{i}}').unlink()
src=Path({small!r});tmp=src.with_suffix('.issue323-tmp');tmp.write_bytes({want!r});os.chmod(tmp,0o644);os.replace(tmp,src)
print('cycle {n} filesystem changes published')
if {n}==2:
 print('intentional command failure after filesystem publication',file=sys.stderr);sys.exit(23)
''';script(work,'mutate-'+str(n),body,15)
 verify=f'''from pathlib import Path
import hashlib
p=Path('.issue323-cycles');assert {{x.name for x in p.iterdir()}}=={{'shared','alias'}}|{{f'{n}-{{i}}' for i in range(5,16)}}
assert (p/'shared').read_bytes()==bytes([{n}])*4096;assert (p/'alias').read_bytes()==bytes([{n}])*4096
assert (p/'shared').stat().st_ino==(p/'alias').stat().st_ino;assert (p/'shared').stat().st_nlink==2
for i in range(5,16):assert (p/f'{n}-{{i}}').read_bytes()==bytes([({n}*17+i)%251])*1024
assert hashlib.sha256(Path({small!r}).read_bytes()).hexdigest()=={sha(want)!r};assert not Path({small!r}).with_suffix('.issue323-tmp').exists()
print('PASS cycle {n} exact names, source bytes, file bytes and hardlink aliases')
''';script(work,'verify-'+str(n),verify)
 if n==5:script(work,'verify-final',verify)
seal(case,work,{'cycles':6,'source_sha256_by_cycle':expect,'expected_command_exit':{'mutate-2':23,'all_other_commands':0},'operations':'per cycle create16/delete5, remove previous generation11 names, in-place shared hardlink write, editor temp/rename source save, one Commit, full selected frontier verifier/status; fresh mount final13 entries and exact6-Commit ancestry','resource_scope':'Public status snapshots only; no continuous peak, incremental-work, global storage, or continuous reclamation-bound claim.'})
print('H02/H03/H04 independently frozen, not executed')
