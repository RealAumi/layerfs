#!/usr/bin/env python3
"""Pin the receive-cost correction without rewriting earlier provenance."""
import pathlib,hashlib,json,subprocess,re
base='524862598';root=pathlib.Path('core/vendor/fuser-0.18.0');record=pathlib.Path('docs/mp2/fuser-receive-exclusive')
files=['Cargo.toml','src/session.rs','src/session/lifecycle.rs','src/session/receive_stop.rs']
patch=subprocess.check_output(['git','diff',base,'--',*[str(root/f) for f in files]])
sha=lambda b:hashlib.sha256(b).hexdigest()
(record/'receive-exclusive.patch').write_bytes(patch)
meta=dict(base_commit=base,receive_stop_provenance_sha256=sha(pathlib.Path('docs/mp2/fuser-receive-stop/provenance.json').read_bytes()),patch_sha256=sha(patch),files={f:sha((root/f).read_bytes()) for f in files})
raw=(json.dumps(meta,indent=2)+'\n').encode();(record/'provenance.json').write_bytes(raw)
p=pathlib.Path('core/tools/check_fuser_integrity.py');s=p.read_text();s=re.sub(r'EXCLUSIVE_PROVENANCE_CHECKSUM = "[^"]*"','EXCLUSIVE_PROVENANCE_CHECKSUM = "'+sha(raw)+'"',s);s=re.sub(r'EXCLUSIVE_PATCH_CHECKSUM = "[^"]*"','EXCLUSIVE_PATCH_CHECKSUM = "'+sha(patch)+'"',s);p.write_text(s)
