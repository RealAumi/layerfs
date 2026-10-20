#!/usr/bin/env python3
"""Seal local executable custody and remove only resources owned by Phase 7."""
import pathlib,subprocess,json,hashlib
repo=pathlib.Path(__file__).resolve().parents[2];out=repo/'docs/mp2/receipts/run07/setup';work=repo/'target/cx7'
identity={arm:{p.name:dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (work/('bin-'+arm)).iterdir()} for arm in ['before','after']}
(out/'binary-custody.json').write_text(json.dumps(identity,indent=2)+'\n')
files=list((repo/'docs/mp2').glob('phase7*'))+[repo/'docs/mp2/seal-receive-stop.py']
(out/'harness-custody.json').write_text(json.dumps({str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()},indent=2)+'\n')
commands=[['ps','-a','--filter','name=cx7-','--format','{{.Names}}'],['network','ls','--filter','name=cx7-','--format','{{.Name}}'],['run','--rm','--name','cx7-seal','-v','cx7-seed:/state:ro','cx7-tools','sha256sum','/state/store/store.sqlite'],['volume','rm','cx7-seed'],['image','rm','cx7-tools'],['ps','-a','--filter','name=cx7-','--format','{{.Names}}'],['network','ls','--filter','name=cx7-','--format','{{.Name}}'],['volume','ls','--filter','name=cx7-','--format','{{.Name}}']]
with (out/'cleanup.jsonl').open('x') as f:
    for args in commands:
        p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=30);f.write(json.dumps(dict(command=['docker',*args],exit=p.returncode,output=p.stdout+p.stderr))+'\n');f.flush();assert p.returncode==0
        if args[0]=='ps' or args[:2]==['network','ls']:assert not p.stdout.strip()
        if args[:2]==['volume','ls']:assert p.stdout.strip()=='cx7-target'
