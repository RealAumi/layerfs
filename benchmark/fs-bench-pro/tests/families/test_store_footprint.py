"""Six original fresh-import/edit controls and the intentionally clipped oracle."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH/"families/store_footprint"


class Footprint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family = json.loads((FAMILY/"family.json").read_text())
        cls.cases = cls.family["cases"]

    def test_five_kept_control_geometries_and_seed_are_exact(self):
        expected = [("unique-100000",100000,1001,500000000,100000),
            ("metadata-cardinality-100000",100000,1001,500000000,100000),
            ("large-object-500m",100,2,500000000,100000),
            ("unique-100-low-v1",100,2,5000000,100),
            ("metadata-cardinality-100-low-v1",100,2,5000000,100)]
        self.assertEqual(len(self.cases),5)
        for c,(suffix,files,dirs,logical,tier) in zip(self.cases,expected):
            ident = "store-footprint-"+suffix
            self.assertEqual((c["id"],c["v016_case"],c["status"]),(ident,ident,"ported"))
            f=c["fixture"]
            self.assertEqual((f["regular_files"],f["directories_including_root"],f["entries"],f["logical_bytes"],f["infrastructure_tier"],f["seed"]),
                             (files,dirs,files+dirs,logical,tier,1))
            self.assertTrue(f["source_only_preparation"])
            self.assertEqual(c["reference"]["release"],"0.1.5")

    def test_original_initialization_is_measured_and_not_hidden_in_a_master(self):
        for c in self.cases:
            self.assertEqual(c["steps"][0],{"init":c["id"],"public_api":"ProjectApi::init","fresh_store":True,"measured":True})
            self.assertEqual(c["steps"][1]["expected_commit"],"Committed")
            schedule=c["store_footprint_schedule"]
            self.assertEqual((schedule["initializations"],schedule["ordinary_edits"],schedule["commits"]),(1,1,1))
            self.assertTrue(schedule["fresh_verifier"])
            self.assertEqual(c["cache_class"],"A")
            self.assertIn("INELIGIBLE","\n".join(c["differences"]))

    def test_final_original_boundary_scope_and_equations_are_not_full_tree_claims(self):
        for c in self.cases:
            oracle=c["oracle"]
            self.assertEqual((oracle["boundary_before_bytes"],oracle["boundary_after_bytes"],oracle["marker"]),(65536,65536,"E000000001"))
            self.assertTrue(oracle["file_length_required"])
            self.assertIn("full_namespace_verified=false",oracle["omissions"])
            self.assertFalse(c["store_footprint_schedule"]["full_namespace_verified"])
            self.assertFalse(c["store_footprint_schedule"]["full_file_bytes_verified"])
            self.assertIn("allocated = live + superseded",oracle["spool_equation"])
            self.assertIn("peak >= allocated",oracle["spool_equation"])
            self.assertIn("sqlite_database_bytes + other_store_bytes",oracle["store_equation"])

    def test_original_watchdogs_and_resources_have_no_new_ratio_gate(self):
        for c in self.cases:
            self.assertEqual(c["budget"],{"command_ms":15000,"operation_watchdog_ms":120000,
                "performance_hard_watchdog_ms":120000,"verifier_ms":75000 if c["id"].endswith("-100000") else 45000,"verification_hard_watchdog_ms":89000 if c["id"].endswith("-100000") else 59000,
                "cleanup_reserve_ms":4000,"publication_guard_ms":250,"wall_stop_ms":120000})
            p=c["resource_profile"]
            self.assertEqual((p["container_cpus"],p["container_memory_bytes"],p["container_memory_swap_bytes"],p["container_pids_limit"]),(2,2*1024**3,2*1024**3,256))
            self.assertEqual(p["main_store_logical_bytes_max"],4*1024**3)
            self.assertEqual(p["owned_workspace_spool_allocated_bytes_max"],2*1024**3)
            self.assertEqual(p["owned_workspace_spool_cleanup_files"],0)
            self.assertEqual((p["host_swaps_allowed"],p["container_swap_allowed"],p["container_oom_delta_allowed"]),(0,0,0))

    def test_frozen_source_seals_and_only_ordinary_exact_native_dispatch(self):
        for path,digest in self.cases[0]["port_review"]["files"].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
            self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(["git","show",self.cases[0]["port_review"]["source_commit"]+":"+path],cwd=ROOT))
        with tempfile.TemporaryDirectory() as temporary:
            fake=Path(temporary)/"writer"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); fake.chmod(0o755)
            env={**os.environ,"WORKLOAD_WRITER":str(fake)}
            for c in self.cases:
                ident=c["id"];tier=str(c["fixture"]["infrastructure_tier"])
                for args,wanted in [(["fixture",ident,"/native"],["store-footprint-fixture","/native",ident,tier]),
                    (["verify-source",ident,"/native"],["store-footprint-digest","/native"]),
                    (["apply",ident,"d0000/file"],["namespace-edit","d0000/file"]),
                    (["verify",ident,"d0000/file","0","100"],["digest-range-inode","d0000/file","0","100"])]:
                    r=subprocess.run(["/bin/bash",str(FAMILY/"workload.sh"),*args],env=env,text=True,capture_output=True,timeout=2,check=True)
                    self.assertEqual(r.stdout.splitlines(),wanted)
            for args in (["apply","unknown","f"],["apply",self.cases[0]["id"]],["verify",self.cases[0]["id"],"f","0"],["init",self.cases[0]["id"]]):
                r=subprocess.run(["/bin/bash",str(FAMILY/"workload.sh"),*args],env=env,capture_output=True,timeout=2)
                self.assertEqual(r.returncode,2)


if __name__=="__main__": unittest.main()
