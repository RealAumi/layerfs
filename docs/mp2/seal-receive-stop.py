#!/usr/bin/env python3
"""Pin the additive receive-stop patch against the accepted Phase 6 tree."""
import hashlib,json,pathlib,subprocess,re
base='6394865a4';root=pathlib.Path('core/vendor/fuser-0.18.0');record=pathlib.Path('docs/mp2/fuser-receive-stop')
files=['src/session.rs','src/session/lifecycle.rs','src/session/receive_stop.rs']
patch=subprocess.check_output(['git','diff',base,'--',str(root/'src/session.rs'),str(root/'src/session/lifecycle.rs')])
patch+=subprocess.run(['git','diff','--no-index','--','/dev/null',str(root/'src/session/receive_stop.rs')],capture_output=True).stdout
(record/'receive-stop.patch').write_bytes(patch)
sha=lambda b:hashlib.sha256(b).hexdigest()
meta=dict(base_commit=base,receive_buffer_provenance_sha256='f3c129457d4eadaf41574c2c1b8da40fb80724e5f42602d3766ab140fdd6d39a',patch_sha256=sha(patch),files={f:sha((root/f).read_bytes()) for f in files})
raw=(json.dumps(meta,indent=2)+'\n').encode();(record/'provenance.json').write_bytes(raw)
p=pathlib.Path('core/tools/check_fuser_integrity.py');s=p.read_text();s=re.sub(r'STOP_PROVENANCE_CHECKSUM = "[^"]*"','STOP_PROVENANCE_CHECKSUM = "'+sha(raw)+'"',s);s=re.sub(r'STOP_PATCH_CHECKSUM = "[^"]*"','STOP_PATCH_CHECKSUM = "'+sha(patch)+'"',s);p.write_text(s)
