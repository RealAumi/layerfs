#!/usr/bin/env python3
"""Maven full comparison and three cache placements, public offline unit test."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sc',HERE/'no-ignore-scenarios.py');sc=importlib.util.module_from_spec(spec);spec.loader.exec_module(sc)
v,h=sc.v,sc.h


def mvn(s,offline=False):
    cache=' -Dmaven.repo.local="$PWD/.m2"' if s['variant']=='b' else ''
    return 'mvn -B -ntp'+(' -o' if offline else '')+cache


def bind_cache(s,label,branch):
    cache=sc.mount(s,label+'-cache',branch)
    h.docker(label+'-cache-bind','exec',s['daemon'],'bash','-c',
      'mkdir -p /home/runner/.m2; chown 1000:1000 /home/runner/.m2; mount --bind '+cache['path']+' /home/runner/.m2')
    h.record('multi_workspace',label=label,daemon=s['daemon'],repo_workspace=s['workspace'],cache_workspace=cache['workspace'],repo_namespace=s['namespace'],cache_namespace=cache['namespace'],result='one daemon, two mounts, writable cache bind at /home/runner/.m2')
    s['cache_workspace']=cache


def end(s,label,discard=False):
    if 'cache_workspace' in s:
        h.docker(label+'-cache-unbind','exec',s['daemon'],'umount','/home/runner/.m2')
        sc.unmount(s['cache_workspace'],label+'-cache-unmount',discard)
    sc.unmount(s,label+'-repo-unmount',discard)


def commit_both(s,label):
    if 'cache_workspace' in s:v.commit(s['cache_workspace'],label+'-cache-commit')
    v.commit(s,label+'-repo-commit')


def prepare_base(variant):
    name='v2-maven-'+variant;h.NETWORK='cxn-'+name+'-net'
    s=h.start(name);s.update(network=h.NETWORK,kind='maven',variant=variant)
    if variant=='a':
        sc.unmount(s,name+'-empty-unmount')
        cache='cxn-'+name+'-shared-cache';s['shared_cache']=cache
        h.docker(name+'-cache-volume','volume','create',cache)
        h.docker(name+'-cache-owner','run','--rm','--name','cxn-cache-owner','--network',h.NETWORK,'-v',cache+':/cache',h.IMAGE,'chown','1000:1000','/cache')
        s=sc.client(s,name+'-builder',[cache+':/home/runner/.m2']);s=sc.mount(s,name+'-builder','base')
    elif variant=='c':
        sc.fork(s,name+'-cache-branch','cache-base','main');bind_cache(s,name+'-builder','cache-base')
    v.save(s)
    return s


def populate_base(variant):
    name='v2-maven-'+variant; s=v.load(name)
    before=v.snapshot(s,name+'-base-start')
    v.clone(s,'https://github.com/spring-projects/spring-petclinic.git',v.PETCLINIC)
    if variant=='b':
        sc.work(s,name+'-cache-rules','printf "\\n/.m2/\\n" >> .git/info/exclude; printf ".m2/\\n" >> .lww',10)
    sc.work(s,name+'-install',mvn(s)+' dependency:go-offline',600)
    sc.work(s,name+'-build',mvn(s)+' -Dtest=ValidatorTests package',110)
    commit_both(s,name+'-base')
    inventory=v.shape(s,name+'-shape')
    cache_inventory=v.shape(s['cache_workspace'],name+'-cache-shape') if 'cache_workspace' in s else None
    h.record('warm_base',label=name,before=before,after=v.snapshot(s,name+'-base-end'),inventory=inventory,cache_inventory=cache_inventory,variant=variant,sample_count=1)
    end(s,name+'-seal');h.docker(name+'-server-stop','stop','-t','10',s['server'])
    s['closed_base']=True;s.pop('cache_workspace',None);v.save(s)


def base(variant):
    prepare_base(variant)
    populate_base(variant)


def add_dependency(s,label):
    jar=('.m2' if s['variant']=='b' else '/home/runner/.m2/repository')+'/com/google/zxing/core/3.5.3/core-3.5.3.jar'
    sc.work(s,label+'-jar-absent','test ! -e '+jar,10)
    code='from pathlib import Path; p=Path("pom.xml"); t=p.read_text(); t=t.replace("</dependencies>", "  <dependency>\\n      <groupId>com.google.zxing</groupId>\\n      <artifactId>core</artifactId>\\n      <version>3.5.3</version>\\n    </dependency>\\n  </dependencies>", 1); p.write_text(t)'
    sc.work(s,label+'-pom','python3 -c '+v.quote(code),10)
    sc.work(s,label+'-download-build',mvn(s)+' -DskipTests package',300)
    sc.work(s,label+'-jar-proof','sha256sum '+jar,10)
    commit_both(s,label)


def fresh_client(s,label,repo_branch='thread',cache_branch='cache-thread'):
    mounts=[s['shared_cache']+':/home/runner/.m2'] if s['variant']=='a' else []
    s=sc.client(s,label,mounts)
    before={'store':v.store(s),'transport':h.proxy(s)};start=time.monotonic_ns()
    s=sc.mount(s,label,repo_branch)
    if s['variant']=='c':bind_cache(s,label,cache_branch)
    return s,before,start


def arm(variant,mode):
    name='v2-maven-'+variant+'-'+mode;base_state=v.load('v2-maven-'+variant)
    s=sc.start_server(base_state,name,mode);s['variant']=variant
    if variant=='a':
        cache='cxn-'+name+'-shared-cache'
        h.docker(name+'-cache-volume','volume','create',cache)
        h.docker(name+'-cache-clone','run','--rm','--name','cxn-cache-clone','--network',s['network'],
          '-v',base_state['shared_cache']+':/source:ro','-v',cache+':/cache',h.IMAGE,'bash','-c','cp -a /source/. /cache/',limit=60)
        s['shared_cache']=cache
    sc.fork(s,name+'-repo-fork','thread')
    if variant=='c':sc.fork(s,name+'-cache-fork','cache-thread','cache-base')
    s,before,start=fresh_client(s,name+'-cold');v.save(s)
    row,_=sc.work(s,name+'-S2-offline-test',mvn(s,True)+' -Dtest=ValidatorTests test',110,False)
    h.record('fresh_test',label=name+'-S2',variant=variant,wall_ns=time.monotonic_ns()-start,before=before,after={'store':v.store(s),'transport':h.proxy(s)},exit=row['exit'],sample_count=1)
    if row['exit']!=0:raise RuntimeError('Maven offline workload failed: '+name)
    if variant=='a':
        for iteration in range(1,11):
            label=name+f'-S3-{iteration:02}'
            code = r"""from pathlib import Path
import re,sys
p=Path("src/main/java/org/springframework/samples/petclinic/PetClinicApplication.java")
t=p.read_text()
t=re.sub(r'\t\tSystem.setProperty\("cxn.iteration", "[0-9]+"\);\n', "", t)
t=t.replace("\t\tSpringApplication.run", '\t\tSystem.setProperty("cxn.iteration", "'+sys.argv[1]+'");\n\t\tSpringApplication.run')
p.write_text(t)
"""
            command='python3 -c '+v.quote(code)+' '+str(iteration)
            sc.work(s,label+'-edit',command,10)
            sc.work(s,label+'-incremental',mvn(s,True)+' -DskipTests package',110)
            commit_both(s,label)
        sc.work(s,name+'-S4-clean-build','rm -rf target && '+mvn(s,True)+' -DskipTests package',110)
        commit_both(s,name+'-S4')
    add_dependency(s,name+'-S5');v.save(s)
    if variant=='c':
        jar='/repository/com/google/zxing/core/3.5.3/core-3.5.3.jar'
        h.call(s,name+'-cache-fork-jar','fs.stat','branch=cache-thread','path='+jar)
        row,text=h.docker(name+'-cache-base-no-jar','exec',s['server'],'timeout','25','/bins/cxn-noignore-driver','call','fs.stat','branch=cache-base','path='+jar,check=False)
        h.record('cache_fork_isolation',label=name,base_lookup_exit=row['exit'],reply=text,merged_back=False)
        if row['exit']==0:raise RuntimeError('cache base unexpectedly acquired new jar')
    if variant=='a':
        end(s,name+'-reclaim')
        fresh,before,start=fresh_client(s,name+'-resume')
        if mode=='on':sc.work(fresh,name+'-S6-reinstall-rebuild',mvn(fresh)+' -DskipTests package',300)
        row,_=sc.work(fresh,name+'-S6-offline-test',mvn(fresh,True)+' -Dtest=ValidatorTests test',110,False)
        h.record('resume',label=name+'-S6',wall_ns=time.monotonic_ns()-start,before=before,after={'store':v.store(fresh),'transport':h.proxy(fresh)},exit=row['exit'],sample_count=1)
        end(fresh,name+'-resume',True)
    else:end(s,name+'-finish',True)
    s.pop('cache_workspace',None);s.pop('workspace',None);s.pop('namespace',None);s.pop('path',None);v.save(s)


if __name__=='__main__':
    try:
        if sys.argv[1]=='prepare':prepare_base(sys.argv[2])
        elif sys.argv[1]=='populate':populate_base(sys.argv[2])
        elif sys.argv[1]=='base':base(sys.argv[2])
        elif sys.argv[1]=='arm':arm(sys.argv[2],sys.argv[3])
        else:raise ValueError('selection')
    except BaseException as error:
        h.record('selection_failure',selection=sys.argv[1:],error=str(error));raise
