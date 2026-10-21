import sys
from pathlib import Path
import hashlib,json
root=Path.cwd();base=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'benchmark-results/fs-bench-pro/deepseek-sdk-20261014/checkpoints-1';base.mkdir(parents=True,exist_ok=True);source=root/'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input';path='node_modules/typescript/lib/typescript.js';b=(source/path).read_bytes()
for shape in ['append','truncate-regrow','scattered']:
 case=base/('M05-'+shape);case.mkdir();work=case/'workloads';work.mkdir();body='from pathlib import Path\nimport os\np=Path('+repr(path)+')\n'
 if shape=='append':
  patch=bytes((i*19+7)%256 for i in range(8192));want=b+patch;body+='with p.open("ab") as f:assert f.write(bytes((i*19+7)%256 for i in range(8192)))==8192\n'
 elif shape=='truncate-regrow':
  cut=len(b)-65536;length=len(b)+32768;patch=bytes((i*23+11)%256 for i in range(4096));want=b[:cut]+bytes(length-cut-4096)+patch;body+=f'with p.open("r+b") as f:\n f.truncate({cut})\n f.truncate({length})\n f.seek({length-4096})\n assert f.write(bytes((i*23+11)%256 for i in range(4096)))==4096\n'
 else:
  offsets=[1,65530,len(b)//2,len(b)-4097];want=bytearray(b);body+='fd=os.open(p,os.O_WRONLY)\ntry:\n'
  for n,off in enumerate(offsets):
   patch=bytes((i*29+n*31)%256 for i in range(4096));want[off:off+4096]=patch;body+=f' assert os.pwrite(fd,bytes((i*29+{n}*31)%256 for i in range(4096)),{off})==4096\n'
  body+='finally:os.close(fd)\n'
 body+=f'print("complete {shape}")\n';digest=hashlib.sha256(want).hexdigest()
 verify=f'from pathlib import Path\nimport hashlib\np=Path({path!r});assert p.stat().st_size=={len(want)}\nwith p.open("rb") as f:\n h=hashlib.sha256()\n while data:=f.read(131072):h.update(data)\nassert h.hexdigest()=={digest!r}\nprint("PASS exact full file hash/length, including all unchanged and zero ranges")\n'
 for name,data,limit in [('mutate',body,15),('verify',verify,9),('verify-fresh',verify,9)]:
  (work/(name+'.sh')).write_text(f"set -eu\ntimeout {limit}s python3 - <<'WORKLOAD_PY'\n"+data+'WORKLOAD_PY\n')
 plan={'case':'M05-'+shape,'shape':shape,'path':path,'input_bytes':len(b),'input_sha256':hashlib.sha256(b).hexdigest(),'expected_bytes':len(want),'expected_sha256':digest,'workload_limit_s':15,'verifier_limit_s':9,'outer_limit_s':120,'one_case_per_shape':True,'workloads':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in work.iterdir()}}
 (case/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print('three distinct prospective shapes prepared; none executed')
