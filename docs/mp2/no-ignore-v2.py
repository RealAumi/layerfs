#!/usr/bin/env python3
"""Attempt 2: immutable attempt-1 receipts; per-command append-only observations."""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('h', HERE/'no-ignore-run.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
h.OUT = HERE/'receipts/noignore01/attempt2'
h.IMAGE = 'cxn-tools:noignore02-pnpm'
VITE = '051370a332df99d107365ed6beab418ef017eff6'
PETCLINIC = '500158f732419217507c7656904b8e6aa1bcc0d6'
INC = 'pnpm exec tsc --incremental --tsBuildInfoFile packages/vite/temp/.tsbuildinfo --emitDeclarationOnly --outDir packages/vite/temp -p packages/vite/src/node/tsconfig.build.json'
NODE_BUILD = 'pnpm --filter vite run build-bundle && '+INC
NODE_TEST = 'pnpm test-unit'


def save(s):
    (h.OUT/(s['repo']+'-state.json')).write_text(json.dumps(s,indent=2)+'\n')


def load(name):
    return json.loads((h.OUT/(name+'-state.json')).read_text())


def store(s):
    code='import sqlite3,pathlib,json; p=pathlib.Path("/state/store/store.sqlite"); c=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True); print(json.dumps({"logical_database_bytes":c.execute("pragma page_count").fetchone()[0]*c.execute("pragma page_size").fetchone()[0],"physical_files":{x.name:{"logical":x.stat().st_size,"allocated":x.stat().st_blocks*512} for x in p.parent.iterdir() if x.is_file()}})); c.close()'
    return json.loads(subprocess.check_output(['docker','exec',s['server'],'python3','-c',code],text=True))


def snapshot(s,label):
    return {'store':store(s),'transport':h.proxy(s),'stats':h.stats(s,label+'-stats')}


def commit(s,label):
    before=snapshot(s,label+'-before')
    row,text=h.ctl(s,label,'commit',s['workspace'],s['namespace'])
    after=snapshot(s,label+'-after')
    if not any(x in text for x in ['Committed','UpToDate']):
        h.record('layerfs_failure',label=label,reply=text)
        raise RuntimeError('LayerFS Commit failed: '+label)
    h.record('measured_commit',label=label,before=before,after=after,
             product_wall_ns=int(re.search(r'wall_ns=(\d+)',text)[1]),command_wall_ns=row['wall_ns'],
             uploaded_bytes=after['stats']['uploadedBytes']-before['stats']['uploadedBytes'],
             fetched_wire_bytes=after['transport']['from_store_bytes']-before['transport']['from_store_bytes'],
             store_growth_bytes=after['store']['logical_database_bytes']-before['store']['logical_database_bytes'],sample_count=1)


def shape(s,label):
    code='import os,json; n=b=nm=nb=0\nfor r,ds,fs in os.walk("."):\n for f in fs:\n  p=os.path.join(r,f)\n  if not os.path.islink(p):\n   z=os.stat(p).st_size;n+=1;b+=z\n   if p.startswith("./node_modules/"):nm+=1;nb+=z\nprint(json.dumps({"files":n,"bytes":b,"node_modules_files":nm,"node_modules_bytes":nb}))'
    return json.loads(h.workload(s,label,'python3 -c '+quote(code),limit=60))


def quote(s):
    import shlex
    return shlex.quote(s)


def clone(s,url,sha):
    h.workload(s,s['repo']+'-clone',f'git init . && git remote add origin {url} && git fetch --depth=1 origin {sha} && git checkout --detach FETCH_HEAD',limit=120)
    h.workload(s,s['repo']+'-lww','printf "%%include .gitignore\\n" > .lww; printf "\\n/.lww\\n" >> .git/info/exclude',limit=10)


def node_base():
    name='v2-vite';h.NETWORK='cxn-'+name+'-net'
    s=h.start(name);s['network']=h.NETWORK;s['kind']='node';save(s)
    before=snapshot(s,name+'-base-start')
    clone(s,'https://github.com/vitejs/vite.git',VITE)
    h.workload(s,name+'-install','pnpm install --frozen-lockfile --registry=https://registry.npmjs.org',limit=600)
    h.workload(s,name+'-build',NODE_BUILD,limit=300)
    commit(s,name+'-base-commit')
    inventory=shape(s,name+'-shape')
    h.record('warm_base',label=name,before=before,after=snapshot(s,name+'-base-end'),inventory=inventory,sample_count=1)
    if not 30000<=inventory['node_modules_files']<=150000:
        h.record('workload_rejected',label=name,reason='file count outside requested range',inventory=inventory)
        raise RuntimeError('candidate size outside range')
    s['qualified']=True;save(s)


if __name__=='__main__':
    try:
        {'node-base':node_base}[sys.argv[1]]()
    except BaseException as error:
        h.record('attempt_failure',operation=sys.argv[1],error=str(error))
        raise
