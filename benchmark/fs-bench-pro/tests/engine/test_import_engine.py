"""Fresh imports retain native-only preparation, storage proof and mounted oracle."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, receipts, workspace


def rows(name):
    return json.loads((BENCH/"families"/name/"family.json").read_text())


def qualification(case, chunks):
    digest = hashlib.sha256()
    for path, parts in sorted(chunks.items()):
        digest.update(path.encode()+b"\0")
        for part in parts:
            digest.update(part["logical_start"].to_bytes(8,"little"))
            digest.update(part["len"].to_bytes(8,"little"))
            digest.update(part["raw_sha256"].encode())
    return {"schema":"fs-bench-pro-independent-dedup-input-v1","status":"PASS",
        "case":case,"step":0,"regular_files":len(chunks),
        "logical_bytes":sum(p["len"] for parts in chunks.values() for p in parts),
        "transcript_sha256":digest.hexdigest(),"receipt":{},"transcripts":chunks}


class Imports(unittest.TestCase):
    def test_all_original_directory_imports_have_complete_census_and_one_fresh_operation(self):
        total = 0
        for name in fixtures.IMPORT_FAMILIES:
            family = rows(name)
            for case in family["cases"]:
                plan = fixtures.import_plan(family,case)
                self.assertEqual(plan["entries"],plan["files"]+plan["directories"])
                self.assertEqual(plan["state"],0)
                self.assertIn("fresh FUSE mount",case["oracle"]["mounted_verification"])
                total += 1
        self.assertEqual(total,10)

    def test_import_admission_refuses_prepared_store_and_mutation_substitutions(self):
        family = rows("dedup_cross_file")
        original = family["cases"][0]
        for change in ({"commit":True},{"mount":True},{"run":"workload.sh apply"},{"fresh_store":False}):
            case = copy.deepcopy(original); case["steps"][0].update(change)
            with self.assertRaises(ValueError): fixtures.import_plan(family,case)
        for change in ({"status":"pending"},{"v016_case":"another"}):
            case = copy.deepcopy(original); case.update(change)
            with self.assertRaises(ValueError): fixtures.import_plan(family,case)
        case = copy.deepcopy(original); case["fixture"]["paths"] += 1
        with self.assertRaises(ValueError): fixtures.import_plan(family,case)

    def test_transcript_seal_requires_complete_contiguous_independent_raw_chunks(self):
        case = rows("dedup_cross_file")["cases"][0]
        parts = [{"logical_start":i*16384,"len":16384,"raw_sha256":f"{i:064x}"} for i in range(64)]
        value = qualification(case["id"],{"files/f0000.dat":parts})
        plan = fixtures.import_plan(rows("dedup_cross_file"),case)
        self.assertIs(fixtures.validate_import_qualification(case,plan,value),value)
        for change in ("digest","gap","oversized","raw","case","step","files","logical"):
            bad = copy.deepcopy(value)
            if change=="digest": bad["transcript_sha256"]="0"*64
            elif change=="gap": bad["transcripts"]["files/f0000.dat"][1]["logical_start"] += 1
            elif change=="oversized": bad["transcripts"]["files/f0000.dat"][0]["len"] = 32769
            elif change=="raw": bad["transcripts"]["files/f0000.dat"][0]["raw_sha256"] = "g"*64
            elif change=="case": bad["case"]="other"
            elif change=="step": bad["step"]=1
            elif change=="files": bad["regular_files"]=2
            else: bad["logical_bytes"] -= 1
            with self.assertRaises(ValueError,msg=change): fixtures.validate_import_qualification(case,plan,bad)

    def test_preparation_invokes_only_native_recipe_full_check_and_independent_scanner(self):
        family = rows("dedup_cross_file"); case = family["cases"][0]
        parts = [{"logical_start":i*16384,"len":16384,"raw_sha256":f"{i:064x}"} for i in range(64)]
        q = qualification(case["id"],{"files/f0000.dat":parts})
        called = []
        build = {"binaries":{name:{"path":"/sealed/"+name,"sha256":"a"*64} for name in
                    ("namespace-writer","workspace-writer","workload-host","edit-host")}, "flags":"mock tools", "explicit_rustflags":None}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)/"fresh"
            cache = mock.patch.object(fixtures.prepared_inputs, "CACHE", Path(temporary)/"inputs")
            cache.start(); self.addCleanup(cache.stop)
            def command(argv, out, label, seconds, **options):
                called.append(argv)
                source = Path(argv[-1]); source.mkdir(parents=True, exist_ok=True)
                value = q if argv[1]=="import-qualified" else {"files":1,"entries":3,"logical_bytes":1048576,
                    "fixture_digest":"b"*64,"verification_status":"pass"}
                path = Path(out)/(label+".stdout"); path.write_text(json.dumps(value))
                return {"argv":argv,"stdout":str(path),"exit_code":0}
            with mock.patch.object(fixtures.identity,"load_build",return_value=build), \
                 mock.patch.object(fixtures.identity,"source_identity",return_value={"source_commit":"sealed","files":{}}), \
                 mock.patch.object(fixtures.receipts,"command",side_effect=command), \
                 mock.patch.object(fixtures.project,"provision",side_effect=AssertionError("setup Init forbidden")):
                result = fixtures.prepare_import(family,case,folder,Path(temporary)/"build")
            self.assertEqual([argv[1] for argv in called],["fixture","verify-step","import-qualified"])
            self.assertIsNone(result["master_volume"])
            self.assertNotIn("provision",result)
            self.assertEqual(result["source_qualification"],q)
            receipts.verify_manifest(folder)
            self.assertEqual(fixtures.load(folder)["schema"],"fs-bench-pro-prepared-native-import-v1")

    def test_original_proof_reserve_and_publication_guard_are_separate(self):
        case = rows("dedup_cross_file")["cases"][0]
        with mock.patch.object(workspace.time,"monotonic",return_value=100):
            stops = workspace.import_proof_deadlines(case,2_000_000_000)
        self.assertEqual(stops,{"work":139,"cleanup":143,"publication":157})
        bad = copy.deepcopy(case); bad["budget"]["verifier_ms"]=46000
        with self.assertRaises(ValueError): workspace.import_proof_deadlines(bad)
        with self.assertRaises(ValueError): workspace.import_proof_deadlines(case,-1)

    def test_reuse_has_exact_original_single_commit_and_cumulative_proof_budget(self):
        cases = rows("dedup_workspace_reuse")["cases"]
        self.assertIn("dedup_workspace_reuse",fixtures.WORKSPACE_FAMILIES)
        with mock.patch.object(workspace.time,"monotonic",return_value=100):
            for case in cases:
                self.assertEqual(workspace.family_proof_deadlines(case,2_000_000_000),
                                 ({"work":169,"cleanup":173,"publication":187} if case["id"] in workspace.LARGE_CHECK_CASES else {"work":139,"cleanup":143,"publication":157}))
                self.assertEqual(case["reuse_schedule"]["verification_states"],[0,1])
                self.assertIn("no warmup",case["cache_contract"]["scope"])


@unittest.skipUnless(os.environ.get("FSBP_NATIVE_CLI"),"explicit compiler-only native CLI required")
class NativeQualifiedCLI(unittest.TestCase):
    def test_complete_original_boundary_record_and_native_tamper_refusal(self):
        binary = os.environ["FSBP_NATIVE_CLI"]
        family = rows("dedup_cdc_locality")
        case = next(case for case in family["cases"] if case["id"]=="dedup-cdc-boundaries-proof")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"source"
            fixture = subprocess.run([binary,"fixture",case["id"],str(root)],text=True,
                                     capture_output=True,check=True,timeout=5)
            fixture = json.loads(fixture.stdout)
            observed = subprocess.run([binary,"import-qualified",case["id"],"0",str(root)],
                                      text=True,capture_output=True,check=True,timeout=5)
            q = json.loads(observed.stdout)
            fixtures.validate_import_qualification(case,fixtures.import_plan(family,case),q)
            self.assertEqual((fixture["files"],q["regular_files"],q["logical_bytes"]),(60,60,884745))
            self.assertEqual(sum(not chunks for chunks in q["transcripts"].values()),6)
            self.assertEqual(q["receipt"]["dedup_transcript_status"],"pass")
            self.assertEqual(q["receipt"]["input_transcript_sha256"],q["transcript_sha256"])
            path = next(root/path for path,chunks in q["transcripts"].items() if chunks)
            with path.open("r+b") as stream:
                byte = stream.read(1); stream.seek(0); stream.write(bytes([byte[0]^1]))
            refused = subprocess.run([binary,"import-qualified",case["id"],"0",str(root)],
                                     text=True,capture_output=True,timeout=5)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(refused.stdout,"")


if __name__=="__main__":
    unittest.main()
