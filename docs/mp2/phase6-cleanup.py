#!/usr/bin/env python3
"""Retain both executable arms and remove only Phase 6 Docker resources."""
import hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path.home()/'lfs-remote/mp2-remote-store';campaign=root/'phase6';d='/usr/local/bin/docker';identity={}
for arm in ['before-bin','bin']:
    identity[arm]={}
    for p in (campaign/arm).iterdir():
        digest=hashlib.sha256(p.read_bytes()).hexdigest();dst=campaign/'artifacts'/digest/p.name
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists():shutil.copy2(p,dst)
        assert hashlib.sha256(dst.read_bytes()).hexdigest()==digest
        identity[arm][p.name]=dict(sha256=digest,path=str(dst))
(campaign/'receipts/binary-custody.json').write_text(json.dumps(identity,indent=2)+'\n')
src=root/'source';paths=list((src/'docs/mp2').glob('phase6-*'))+[src/'docs/mp2/phase3-diagnostics.py']+list((src/'core/crates/layerfs-remote-store').rglob('*.rs'))
(campaign/'receipts/source-custody.json').write_text(json.dumps({str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2)+'\n')
commands=[['run','--rm','--name','mp2-p6-seal','-v','mp2-p6-seed:/seed:ro','-v','mp2-p6-warm:/warm:ro','mp2-p6-tools','bash','-c','uname -a; git --version; sha256sum /seed/store/store.sqlite /warm/store/store.sqlite'],['image','inspect','mp2-p6-tools','--format','{{.Id}}'],['volume','rm','mp2-p6-seed','mp2-p6-warm','mp2-p6-input'],['image','rm','mp2-p6-tools'],['ps','-a','--filter','name=mp2-p6','--format','{{.Names}}'],['network','ls','--filter','name=mp2-p6','--format','{{.Name}}'],['volume','ls','--filter','name=mp2-p6','--format','{{.Name}}']]
with (campaign/'receipts/cleanup.log').open('x') as f:
    for args in commands:
        p=subprocess.run([d,*args],capture_output=True,text=True,timeout=30)
        f.write(json.dumps(dict(command=args,exit=p.returncode,output=p.stdout+p.stderr))+'\n');f.flush();assert p.returncode==0
        if 'ls' in args or args[0]=='ps':assert not p.stdout.strip()
