#!/usr/bin/env python3
"""Inside the owned input volume: pinned Dubbo, metadata-shape and I/O fixtures."""
import pathlib,shutil,json,gzip,hashlib,os,collections
root=pathlib.Path('/input');dubbo=root/'dubbo'
with (dubbo/'.git/info/exclude').open('a') as f:f.write('\nnode_modules/\n')
for variant in ['plain','large']:
    shutil.copytree(dubbo,root/variant,symlinks=True)
rows=json.load(gzip.open('/manifest.json.gz','rt'))
for r in rows:
    p=root/'large'/r['path'];p.parent.mkdir(parents=True,exist_ok=True)
    chunk=hashlib.shake_256(r['sha256'].encode()).digest(min(r['size'],65536))
    with p.open('wb') as f:
        left=r['size']
        while left:
            n=min(left,len(chunk));f.write(chunk[:n]);left-=n
hot=root/'hot';hot.mkdir();shutil.copytree(dubbo,hot/'dubbo',symlinks=True)
(hot/'small').mkdir()
for i in range(5000):(hot/'small'/f'f{i:05}').write_bytes(hashlib.shake_256(f'small-{i}'.encode()).digest(1024))
with (hot/'large.bin').open('wb') as f:
    for i in range(256):f.write(hashlib.shake_256(f'large-{i}'.encode()).digest(1024*1024))
for uid in [0,1000]:
    p=root/f'copies-{uid}';p.mkdir();(p/'file.txt').write_text('ownership copy oracle\n');(p/'nested').mkdir();(p/'nested/other.txt').write_text('second copy oracle\n')
    for q in [p,*p.rglob('*')]:os.chown(q,uid,uid)
print(json.dumps(dict(node_files=len(rows),node_bytes=sum(r['size'] for r in rows),node_directories=len({str(p.parent) for p in (root/'large/node_modules').rglob('*')}),small_files=5000,small_bytes=5000*1024,large_bytes=(hot/'large.bin').stat().st_size,source='Dubbo cb05763298f081ed17171d704408b6478cf8fd83; node names/sizes from retained Phase4 full manifest; synthetic payloads')))
