"""One registered diagnostic invocation; no resampling or speed ratios."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
root=Path.cwd();case=Path(sys.argv[1]).resolve();volume=sys.argv[2]
plan=json.loads((case/'plan.json').read_text());assert not (case/'run-1').exists()
(root/'docs/general/benchmark_agent_report.md').read_text()
binary=root/'core/target/issue323-checkpoints-host/release/deepseek-sdk-measure';daemon=root/'core/target/deepseek-sdk/layerfs-daemon';source=Path(plan['fixture'])
files=[Path(__file__).resolve(),binary,daemon,root/'benchmark/deepseek-sdk-experiment/src/measure.rs',root/'benchmark/deepseek-sdk-experiment/Cargo.toml',root/'benchmark/deepseek-sdk-experiment/Cargo.lock',root/'.cargo/config.toml',case/'plan.json',case/'oracle.json']+list((case/'workloads').iterdir())
command=['perl','core/target/r4-locked.pl','120',str(binary),str(case),str(source),volume,str(daemon)]
identity={'command':command,'source':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'product_tree':subprocess.check_output(['git','rev-parse','HEAD:core/crates'],text=True).strip(),'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'image':plan['image'],'volume':volume,'cache_eligibility':'INCOMPLETE/INELIGIBLE; diagnostic values only','native_analogue_missing':['Init/install/mount/Commit/history/unmount'],'profile':'Disposable/WAL/OFF','workers':1,'sample_count_per_case_arm':1}
with (case/'invocation.json').open('x') as f:json.dump(identity,f,indent=2);f.write('\n')
env=os.environ.copy();env['LAYERFS_CONSTRUCTION_WORKERS']='1';env['ISSUE323_IMAGE']=plan['image'];clock=time.monotonic_ns()
with (case/'driver.stdout').open('xb') as out,(case/'driver.stderr').open('xb') as err:result=subprocess.run(command,stdout=out,stderr=err,env=env)
ns=time.monotonic_ns()-clock
receipt={'exit':result.returncode,'complete_driver_wall_ns':ns,'diagnostic_test_wall_limit_s':120,'default_performance_command_budget_s':15,'complete_performance_budget':'EXCEEDED' if ns>15_000_000_000 else 'WITHIN','functional':'PASS' if result.returncode==0 else 'FAIL','numeric_eligibility':'INCOMPLETE/INELIGIBLE','no_resampling':True,'custody':'original SDK call/failure receipts; no automatic cleanup on failure'}
with (case/'result.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt));sys.exit(result.returncode)
