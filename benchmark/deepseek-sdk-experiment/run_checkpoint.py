"""One explicit SDK checkpoint invocation, fresh receipt files; no replay."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
root=Path.cwd();case=Path(sys.argv[1]).resolve();volume=sys.argv[2]
assert (case/'plan.json').is_file();plan=json.loads((case/'plan.json').read_text());run=case/'run-1';assert not run.exists()
(root/'docs/general/benchmark_agent_report.md').read_text()
binary=root/'core/target/issue323-checkpoints-host/release/deepseek-sdk-checkpoint'
daemon=root/'core/target/deepseek-sdk/layerfs-daemon'
source=root/'benchmark-results/fs-bench-pro/deepseek-probe-20261014/full-input'
cmd=['perl','core/target/r4-locked.pl','120',str(binary),str(run),str(source),volume,str(daemon)]
files=[Path(__file__).resolve(),binary,daemon,root/'benchmark/deepseek-sdk-experiment/src/checkpoint.rs',root/'benchmark/deepseek-sdk-experiment/Cargo.toml',root/'benchmark/deepseek-sdk-experiment/Cargo.lock',root/'.cargo/config.toml',case/'plan.json']+list((case/'workloads').iterdir())
identity={'command':cmd,'source':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'profile':'Disposable/WAL/OFF','workers':1,'cache':'natural/setup warmth; no performance claim','volume':volume,'installation':'SDK SandboxApi.create; empty volume is operator prerequisite only','image':plan.get('image','sha256:378b799ef43343fc64008b6a5ef456dd6bf0cb8f6ea4cec72e7b42dfc17d2cd6')}
with (case/'invocation.json').open('x') as f:json.dump(identity,f,indent=2);f.write('\n')
env=os.environ.copy();env['LAYERFS_CONSTRUCTION_WORKERS']='1'
if 'image' in plan:env['ISSUE323_IMAGE']=plan['image']
start=time.monotonic_ns()
with (case/'driver.stdout').open('xb') as out,(case/'driver.stderr').open('xb') as err:r=subprocess.run(cmd,stdout=out,stderr=err,env=env)
result={'exit':r.returncode,'complete_driver_wall_ns':time.monotonic_ns()-start,'wall_limit_s':120,'functional':'PASS' if r.returncode==0 else 'FAIL','performance_samples':0,'custody':'see original sdk-calls.tsv; no automatic cleanup after failure'}
with (case/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result));sys.exit(r.returncode)
