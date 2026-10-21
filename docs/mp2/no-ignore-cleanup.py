#!/usr/bin/env python3
"""Dispose only this campaign's cxn- resources after retaining its evidence."""
import json
import os
import pathlib
import subprocess
import time

R=pathlib.Path(__file__).resolve().parent/'receipts/noignore01/attempt2'
rows=[]

def cmd(args):
    start=time.monotonic_ns();p=subprocess.run(args,capture_output=True,text=True,timeout=40)
    rows.append(dict(command=args,exit=p.returncode,wall_ns=time.monotonic_ns()-start,output=p.stdout+p.stderr))
    return p


def names(args):return subprocess.check_output(args,text=True).splitlines()

v=os.statvfs('.');before=v.f_bavail*v.f_frsize
# The failed S8b workspace has never been committed. Discard it explicitly.
s=json.loads((R/'v2-maven-b-state.json').read_text())
p=cmd(['docker','exec',s['daemon'],'timeout','25','/bins/off/layerfs-remote','/state/daemon.setup','unmount',s['workspace'],s['namespace'],'discard'])
assert p.returncode==0
for c in names(['docker','ps','-a','--filter','name=^/cxn-','--format','{{.Names}}']):
    assert c.startswith('cxn-v2-maven-'),c
    for f in ['daemon.log','server.log','proxy.log']:
        dest=R/(c+'-final-'+f)
        p=subprocess.run(['docker','cp',c+':/state/'+f,str(dest)],capture_output=True,text=True)
        if p.returncode==0:rows.append({'retained':dest.name,'container':c})
    assert cmd(['docker','rm','-f',c]).returncode==0
for n in names(['docker','volume','ls','--format','{{.Name}}']):
    if n.startswith('cxn-'):
        assert n.startswith('cxn-v2-maven-'),n
        assert cmd(['docker','volume','rm',n]).returncode==0
for n in names(['docker','network','ls','--format','{{.Name}}']):
    if n.startswith('cxn-'):
        assert n.startswith('cxn-v2-maven-'),n
        assert cmd(['docker','network','rm',n]).returncode==0
for tag in ['cxn-tools:noignore02-node20','cxn-tools:noignore02-pnpm','cxn-tools:noignore02']:
    assert cmd(['docker','image','rm',tag]).returncode==0
assert cmd(['docker','volume','inspect','cxi-target','--format','{{.Name}}']).returncode==0
remaining={
 'containers':names(['docker','ps','-a','--filter','name=^/cxn-','--format','{{.Names}}']),
 'networks':[n for n in names(['docker','network','ls','--format','{{.Name}}']) if n.startswith('cxn-')],
 'volumes':[n for n in names(['docker','volume','ls','--format','{{.Name}}']) if n.startswith('cxn-')]}
assert not any(remaining.values())
v=os.statvfs('.');after=v.f_bavail*v.f_frsize
with (R/'cleanup-final.json').open('x') as f:json.dump({'operations':rows,'remaining':remaining,'host_free_before':before,'host_free_after':after,'net_host_free_change':after-before,'kept':'cxi-target','failed_store_payloads':'deleted after receipt capture; not available for proof reuse'},f,indent=2);f.write('\n')
print(json.dumps({'remaining':remaining,'kept':'cxi-target','net_host_free_change':after-before}))
