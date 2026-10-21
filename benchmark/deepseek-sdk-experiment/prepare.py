"""Independent source oracle and immutable workloads; no product/database/runtime calls."""
import hashlib,json,sys
from pathlib import Path
source=Path(sys.argv[1]);campaign=Path(sys.argv[2]);work=campaign/'workloads';work.mkdir()
small='packages/util/brand/src/index.ts';big='node_modules/typescript/lib/typescript.js'
a=(source/small).read_bytes();b=(source/big).read_bytes()
marker1=b'\n// SDK-only experiment: source edit\n';marker2=b'// SDK-only experiment: later edit\n'
offset=(len(b)//2//4096)*4096;patch=bytes((i*17+3)%256 for i in range(4096));newb=b[:offset]+patch+b[offset+4096:]
def sha(v):return hashlib.sha256(v).hexdigest()
original={rel:sha((source/rel).read_bytes()) for rel in [small,big,'package.json','pnpm-lock.yaml']}
expected={'source':str(source),'small':small,'big':big,'initial_sha256':original,'source_after_edit':sha(a+marker1),'source_final':sha(a+marker1+marker2),'big_bytes':len(b),'patch_offset':offset,'patch_bytes':4096,'big_after_sha256':sha(newb),'created':256,'renamed':64,'deleted':64,'remaining':192}
(campaign/'expected.json').write_text(json.dumps(expected,indent=2)+'\n')
header='from pathlib import Path\nimport hashlib,json,os,time\n'
def verify(paths):
 body=header
 for rel,h in paths.items():body+=f'assert hashlib.sha256(Path({rel!r}).read_bytes()).hexdigest()=={h!r}, {rel!r}\n'
 return body
initial=verify(original)+"assert Path('node_modules/typescript').is_symlink()\nprint('PASS initial selected complete-file hashes and pnpm symlink')\n"
smallverify=verify({small:sha(a+marker1)})+"assert Path('.sdk-probe/token').read_bytes()==b'sdk-only-token\\n'\nprint('PASS source edit and new token')\n"
burstverify=header+'''d=Path('.sdk-probe/burst')
want={f'r-{i:04d}' for i in range(64)}|{f'f-{i:04d}' for i in range(128,256)}
assert {p.name for p in d.iterdir()}==want
for i in list(range(64))+list(range(128,256)):
 name=f'r-{i:04d}' if i<64 else f'f-{i:04d}'
 assert (d/name).read_bytes()==bytes([i%251])*1024,name
print('PASS exact192 small files and membership')
'''
largeverify=verify({big:sha(newb)})+f"assert Path({big!r}).stat().st_size=={len(b)}\nprint('PASS complete large-file SHA256, all unchanged bytes included')\n"
finalverify=verify({small:sha(a+marker1+marker2),big:sha(newb),'package.json':original['package.json'],'pnpm-lock.yaml':original['pnpm-lock.yaml']})+burstverify+"assert Path('node_modules/typescript').is_symlink()\nprint('PASS final saved state after SDK remount/reopen')\n"
bodies={
 'verify-initial':(initial,9),
 'edit-source':(header+f"Path('.sdk-probe').mkdir()\nwith Path({small!r}).open('ab') as f:f.write({marker1!r})\nPath('.sdk-probe/token').write_bytes(b'sdk-only-token\\n')\nprint('source mutation complete')\n",15),
 'verify-source':(smallverify,9),'verify-source-fresh':(smallverify,9),
 'small-files':(header+'''d=Path('.sdk-probe/burst');d.mkdir()
for i in range(256):(d/f'f-{i:04d}').write_bytes(bytes([i%251])*1024)
for i in range(64):(d/f'f-{i:04d}').rename(d/f'r-{i:04d}')
for i in range(64,128):(d/f'f-{i:04d}').unlink()
print('small-file mutation complete')
''',15),
 'verify-small-fresh':(burstverify,9),
 'large-patch':(header+f"fd=os.open({big!r},os.O_WRONLY)\ntry:assert os.pwrite(fd,bytes((i*17+3)%256 for i in range(4096)),{offset})==4096\nfinally:os.close(fd)\nprint('4096B patch complete')\n",15),
 'verify-large':(largeverify,9),
 'later-edit':(header+f"with Path({small!r}).open('ab') as f:f.write({marker2!r})\nprint('later active mutation complete')\n",15),
 'verify-final-fresh':(finalverify,9),'verify-reopen':(finalverify,9),
 'holder':(header+"Path('.sdk-probe/holder-ready').write_bytes(b'ready')\nwhile not Path('.sdk-probe/holder-release').exists():time.sleep(.02)\nprint('holder explicitly released')\n",5),
 'holder-ready':(header+"end=time.monotonic()+2\nwhile not Path('.sdk-probe/holder-ready').exists():\n assert time.monotonic()<end,'holder readiness deadline'\n time.sleep(.02)\nprint('holder ready')\n",3),
 'holder-release':(header+"Path('.sdk-probe/holder-release').write_bytes(b'release')\nprint('holder release signalled')\n",3),
}
for name,(body,limit) in bodies.items():
 (work/(name+'.sh')).write_text(f"set -eu\ntimeout {limit}s python3 - <<'WORKLOAD_PY'\n"+body+'WORKLOAD_PY\n')
(campaign/'workloads.json').write_text(json.dumps({p.name:sha(p.read_bytes()) for p in work.iterdir()},indent=2)+'\n')
print(json.dumps({'workloads':len(bodies),'source_immutable':str(source),'large_bytes':len(b),'sha256_independent':True}))
