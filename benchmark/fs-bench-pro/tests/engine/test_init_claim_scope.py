"""H30 claim regression; pure source identities, no sample/Store/daemon."""
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import project

OLD_SCOPE=("benchmark/fs-bench-pro/engine/project.py","benchmark/fs-bench-pro/engine/fixtures.py",
           "benchmark/fs-bench-pro/engine/identity.py","benchmark/fs-bench-pro/engine/recipes/namespace.rs")
SHARED=("benchmark/fs-bench-pro/engine/workspace.py","benchmark/fs-bench-pro/engine/receipts.py")

def current():
    return {"product_tree":"a"*40,"source_commit":"b"*40,
            "files":{**{p:str(i)*64 for i,p in enumerate(OLD_SCOPE,1)},SHARED[0]:"c"*64,SHARED[1]:"d"*64}}

def treatment(family,identity):
    selected={"id":"synthetic-claim-contract","fixture":{"recipe":"synthetic-claim-contract"}}
    prepared={"fixture":{"recipe":"synthetic-claim-contract","seed":1}}
    build={"binaries":{"runtime":{"sha256":"e"*64}}}
    with patch.object(project.identity,"sha256",return_value="f"*64):
        if hasattr(project,"init_treatment"):
            return project.init_treatment(family,selected,prepared,build,identity)
        # Red executes the parent's actual treatment expression, not a copied
        # whitelist. Green calls the extracted function used by one_init.
        body=ast.parse(inspect.getsource(project.one_init))
        assigned=next(node.value for node in ast.walk(body) if isinstance(node,ast.Assign)
                      and any(isinstance(target,ast.Name) and target.id=='treatment' for target in node.targets))
        return eval(compile(ast.Expression(assigned),'<parent actual treatment>','eval'),project.__dict__,
                    {'family':family,'case':selected,'prepared':prepared,'build':build,'current':identity})

def key(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

class InitClaimScope(unittest.TestCase):
    def test_import_shared_verifier_and_guard_changes_make_distinct_treatments(self):
        for family in ('dedup_cdc_locality','dedup_cross_file'):
            original=current();base=treatment(family,original)
            for path in SHARED:
                changed=copy.deepcopy(original);changed['files'][path]='9'*64
                with self.subTest(family=family,path=path):
                    self.assertNotEqual(key(base),key(treatment(family,changed)))
                    self.assertEqual(treatment(family,changed)['execution_files'][path],'9'*64)

    def test_namespace_legacy_key_exact_and_ignores_unused_import_shared_files(self):
        original=current();base=treatment('init_namespace',original)
        changed=copy.deepcopy(original)
        for path in SHARED:changed['files'][path]='9'*64
        self.assertEqual(key(base),key(treatment('init_namespace',changed)))
        self.assertEqual(set(base['execution_files']),set(OLD_SCOPE))
        self.assertEqual(key(base),'a17e6445f3d0af521ad5fbdd70c48251d32623beb2c4b876a3aa99f06638bd09')

    def test_source_commit_only_does_not_authorize_an_import_replay(self):
        original=current();changed=copy.deepcopy(original);changed['source_commit']='8'*40
        self.assertEqual(key(treatment('dedup_cdc_locality',original)),key(treatment('dedup_cdc_locality',changed)))

if __name__=='__main__':unittest.main()
