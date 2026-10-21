#!/usr/bin/env python3
"""One non-performance native-filesystem control for test fixture persistence."""
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sc',HERE/'no-ignore-scenarios.py');sc=importlib.util.module_from_spec(spec);spec.loader.exec_module(sc)
v,h=sc.v,sc.h
s=v.load('v2-vite-off3');s['daemon']='cxn-v2-vite-off3-resume'
s=sc.mount(s,'native-diagnostic-input','base')
target='/home/runner/cxn-native-control'
h.docker('native-diagnostic-copy','exec','--user','1000:1000',s['daemon'],'timeout','110','bash','-c','mkdir '+target+' && cp -a '+s['path']+'/. '+target+'/',limit=115)
sc.unmount(s,'native-diagnostic-input-unmount',True)
fixture=target+'/packages/vite/src/node/ssr/runtime/__tests__/fixtures/throws-error-method.ts'
h.docker('native-diagnostic-before','exec',s['daemon'],'nl','-ba',fixture)
row,text=h.docker('native-diagnostic-tests','exec','--user','1000:1000','-e','HOME=/home/runner','-w',target,s['daemon'],'timeout','110','pnpm','test-unit',limit=115,check=False)
h.docker('native-diagnostic-after','exec',s['daemon'],'nl','-ba',fixture)
h.record('native_cause_diagnostic',exit=row['exit'],sample_count=1,performance_comparison=False,scope='full unit suite on container local filesystem, copied immutable base, no measured-arm replay')
