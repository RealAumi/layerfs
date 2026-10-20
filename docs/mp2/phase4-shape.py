#!/usr/bin/env python3
"""Read-only sampling of an existing install; materialize only in campaign work."""
import pathlib, hashlib, json, shutil, collections, statistics
root=pathlib.Path.home()/'work/mp2/node_modules'
out=pathlib.Path.home()/'lfs-remote/mp2-remote-store/phase4/work/shape';out.mkdir()
added=root/'.bun/zod@4.6.5/node_modules/zod'
files=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and added not in p.parents]
files.sort(key=lambda p:hashlib.sha256(str(p.relative_to(root)).encode()).digest())
assert len(files)>=30000 and added.is_dir()
summary={}
for kind,selected in [('full',files[:30000]),('delta',[p for p in added.rglob('*') if p.is_file() and not p.is_symlink()])]:
    rows=[]
    for p in selected:
        rel=pathlib.Path('node_modules')/(p.relative_to(root) if kind=='full' else pathlib.Path('added-zod')/p.relative_to(added))
        target=out/kind/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);target.chmod(0o644)
        rows.append(dict(path=str(rel),source=str(p.relative_to(root)),size=p.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (out/(kind+'-manifest.json')).write_text(json.dumps(rows))
    sizes=sorted(r['size'] for r in rows)
    summary[kind]=dict(files=len(rows),bytes=sum(sizes),size_min=sizes[0],size_median=statistics.median(sizes),size_p90=sizes[int(len(sizes)*.9)],size_p99=sizes[int(len(sizes)*.99)],size_max=sizes[-1],depth=dict(collections.Counter(str(len(pathlib.Path(r['path']).parts)-1) for r in rows)))
summary['source']=dict(path=str(root),regular_files=len(files),selection='lowest SHA256(relative path), exclude added zod; preserve bytes and relative path, no symlinks; not an executable install',added_version=json.loads((added/'package.json').read_text())['version'])
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
