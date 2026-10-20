#!/usr/bin/env python3
"""Verify retained binary custody and remove only Phase 5 Docker resources."""
import hashlib,json,pathlib,subprocess
root=pathlib.Path.home()/'lfs-remote/mp2-remote-store';campaign=root/'phase5';d='/usr/local/bin/docker'
prior=json.loads((root/'phase4/receipts/binary-custody.json').read_text());identity={}
for p in (campaign/'bin').iterdir():
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if p.name in prior:
        assert digest==prior[p.name]['sha256'];assert pathlib.Path(prior[p.name]['path']).exists()
        identity[p.name]=prior[p.name]
    else:identity[p.name]=dict(sha256=digest,path=str(p))
(campaign/'receipts/binary-custody.json').write_text(json.dumps(identity,indent=2)+'\n')
scripts=list((root/'source/docs/mp2').glob('phase5-*'))+[root/'source/docs/mp2/phase3-diagnostics.py']
(campaign/'receipts/harness-custody.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts},indent=2)+'\n')
commands=[['run','--rm','--name','mp2-p5-seal','-v','mp2-p5-seed:/seed:ro','mp2-p5-tools','bash','-c','uname -a; git --version; sha256sum /seed/store/store.sqlite'],['volume','rm','mp2-p5-seed','mp2-p5-input'],['image','rm','mp2-p5-tools'],['ps','-a','--filter','name=mp2-p5','--format','{{.Names}}'],['network','ls','--filter','name=mp2-p5','--format','{{.Name}}'],['volume','ls','--filter','name=mp2-p5','--format','{{.Name}}']]
with (campaign/'receipts/cleanup.log').open('x') as f:
    for args in commands:
        p=subprocess.run([d,*args],capture_output=True,text=True,timeout=30)
        f.write(json.dumps(dict(command=args,exit=p.returncode,output=p.stdout+p.stderr))+'\n');f.flush();assert p.returncode==0
        if 'ls' in args or args[0]=='ps':assert not p.stdout.strip()
