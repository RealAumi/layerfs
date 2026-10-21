import sys
from pathlib import Path
import subprocess,hashlib,json
root=Path.cwd();base=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/checkpoints-1';base.mkdir(parents=True,exist_ok=True);case=base/'M04';case.mkdir();work=case/'workloads';work.mkdir()
source=root/'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input';small='packages/util/brand/src/index.ts';marker=b'\n// Issue 323 M04 ordinary Git workflow\n';data=(source/small).read_bytes()+marker
cmd=['git','--no-optional-locks','-C',str(source)]
def git(*a):return subprocess.check_output(cmd+list(a))
def obj(kind,v):return hashlib.sha1(kind.encode()+b' '+str(len(v)).encode()+b'\0'+v).hexdigest()
parent=git('rev-parse','HEAD').decode().strip();blob=obj('blob',data)
def tree_update(tree,parts):
 raw=git('cat-file','tree',tree);rows=[]
 while raw:
  namepart,raw=raw.split(b'\0',1);mode,name=namepart.split(b' ',1);oid,raw=raw[:20],raw[20:]
  if name.decode()==parts[0]:oid=bytes.fromhex(blob if len(parts)==1 else tree_update(oid.hex(),parts[1:]))
  rows.append(mode+b' '+name+b'\0'+oid)
 return obj('tree',b''.join(rows))
tree=tree_update(git('rev-parse','HEAD^{tree}').decode().strip(),small.split('/'))
message='Issue 323 M04 saved Git state';date='1791979200 +0000';ident='LayerFS Experiment <issue323@example.invalid>'
commitbytes=f'tree {tree}\nparent {parent}\nauthor {ident} {date}\ncommitter {ident} {date}\n\n{message}\n'.encode();commit=obj('commit',commitbytes)
expect={'case':'M04','parent':parent,'tree':tree,'git_commit':commit,'blob':blob,'small':small,'small_sha256':hashlib.sha256(data).hexdigest(),'small_bytes':len(data),'marker':marker.decode(),'workload_limit_s':15,'verifier_limit_s':9,'outer_limit_s':120}
mutate=f'''set -eu
timeout 15s bash -eu -o pipefail -c '\nexport GIT_AUTHOR_NAME="LayerFS Experiment" GIT_AUTHOR_EMAIL="issue323@example.invalid" GIT_COMMITTER_NAME="LayerFS Experiment" GIT_COMMITTER_EMAIL="issue323@example.invalid" GIT_AUTHOR_DATE="{date}" GIT_COMMITTER_DATE="{date}"
git --no-optional-locks status --porcelain=v1 --untracked-files=no -- {small}
printf "\\n// Issue 323 M04 ordinary Git workflow\\n" >> {small}
git --no-optional-locks diff -- {small}
git add -- {small}
git -c core.hooksPath=/dev/null -c commit.gpgsign=false commit --no-verify -m "{message}"
git --no-optional-locks status --porcelain=v1 --untracked-files=no -- {small}
'
'''
verify=f'''from pathlib import Path
import hashlib,subprocess,os,json
def git(*a):return subprocess.check_output(['git','--no-optional-locks']+list(a)).decode().strip()
assert git('rev-parse','HEAD')=={commit!r}
assert git('rev-parse','HEAD^')=={parent!r}
assert git('rev-parse','HEAD^{{tree}}')=={tree!r}
assert git('rev-parse','HEAD:{small}')=={blob!r}
assert git('ls-files','--stage','--',{small!r}).split()[1]=={blob!r}
assert git('status','--porcelain=v1','--untracked-files=no','--',{small!r})==''
p=Path({small!r});assert p.stat().st_size=={len(data)};assert hashlib.sha256(p.read_bytes()).hexdigest()=={expect['small_sha256']!r}
'''
fixture=json.loads((source.parent/'fixture.json').read_text())
for p in ['package.json','pnpm-lock.yaml','node_modules/typescript/lib/typescript.js']:verify+=f'assert hashlib.sha256(Path({p!r}).read_bytes()).hexdigest()=={fixture["selected"][p]["sha256"]!r}\n'
verify+="assert Path('node_modules/typescript').is_symlink()\nprint('PASS independently derived Git Commit/tree/parent/index blob, source and selected dependency bytes')\n"
(work/'mutate.sh').write_text(mutate)
for name in ['verify','verify-fresh']:(work/(name+'.sh')).write_text("set -eu\ntimeout 9s python3 - <<'PY_VERIFY'\n"+verify+'PY_VERIFY\n')
expect['workloads']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in work.iterdir()};(case/'plan.json').write_text(json.dumps(expect,indent=2)+'\n');print(json.dumps(expect))
