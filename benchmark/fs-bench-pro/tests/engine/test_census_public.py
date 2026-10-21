"""Actual public Store/Commit/provider qualification; no Docker custody claim."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest

BENCH=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("public_census_oracle",BENCH/"engine/oracle.py")
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)


def provider_fields(path):
    events=[json.loads(line) for line in path.read_text().splitlines()]
    providers=[event for event in events if event.get("event")=="workspace_verified"]
    if len(providers)!=1 or events[-1].get("event")!="finished":
        raise ValueError("actual public typed proof did not finish exactly once")
    return providers[0]["fields"]


class PublicCanonicalCensus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get("LAYERFS_BATCH4_CENSUS_FIXTURE")
        if not value:
            raise unittest.SkipTest("explicit genuine public fixture output required")
        cls.fixture=Path(value).resolve()
        if not (cls.fixture/"extra-commit.json").is_file():
            raise FileNotFoundError("explicit public Rust canonical fixture is missing")

    def test_actual_anchored_public_proof_passes_but_unfiltered_extra_commit_fails(self):
        fixture=self.fixture;extra=json.loads((fixture/"extra-commit.json").read_text())
        runtime=Path(os.environ.get("LAYERFS_BATCH4_CENSUS_RUNTIME",extra["runtime"]))
        runtime_sha=oracle.file_sha(runtime)
        output=fixture/"python-canonical-check";output.mkdir(exist_ok=False)
        baseline=fixture/"baseline/store.sqlite";manifest=fixture/"manifest";transcript=fixture/"history.tsv"
        original=provider_fields(fixture/"provider.jsonl")
        self.assertEqual(original.get("status"),"PASS")
        expected=[]
        for line in transcript.read_text().splitlines()[1:]:
            _,commit,parent,root,_=line.split("\t")
            expected.append({"commit_id":commit,"layer_stack_id":original["stack_id"],"root_id":root,
                             "parent_commit_id":None if parent=="-" else parent,"base_layer_id":original["base_layer_id"]})
        baseline_result=oracle._commit_census_read_only(baseline,expected,original,manifest,transcript)
        self.assertEqual(baseline_result["commit_count"],2)
        self.assertEqual(extra["original_head"],expected[-1]["commit_id"])
        self.assertEqual(extra["parent_commit_id"],expected[-1]["commit_id"])
        self.assertEqual(extra["root_id"],expected[0]["root_id"])
        self.assertNotEqual(extra["root_id"],expected[-1]["root_id"])
        self.assertEqual(extra["layer_stack_id"],original["stack_id"])
        self.assertEqual(extra["base_layer_id"],original["base_layer_id"])
        self.assertNotIn(extra["commit_id"],{row["commit_id"] for row in expected})
        reset=output/"reset/store.sqlite";reset.parent.mkdir()
        shutil.copy2(fixture/"extra/store.sqlite",reset)
        connection=sqlite3.connect(reset,isolation_level=None,timeout=0)
        try:
            connection.execute("PRAGMA journal_mode=WAL");connection.execute("PRAGMA synchronous=OFF")
            before=list(connection.execute(oracle.CENSUS_SQL))
            self.assertIn(tuple(bytes.fromhex(extra[key]) for key in oracle.CENSUS_COLUMNS),before)
            branch=bytes.fromhex(original["branch_id"])
            self.assertEqual(connection.execute("SELECT head_commit_id FROM branch WHERE branch_id=?",(branch,)).fetchone(),
                             (bytes.fromhex(extra["commit_id"]),))
            restored=connection.execute("UPDATE branch SET head_commit_id=? WHERE branch_id=?",
                                        (bytes.fromhex(extra["original_head"]),branch))
            self.assertEqual(restored.rowcount,1)
            self.assertEqual(list(connection.execute(oracle.CENSUS_SQL)),before)
            self.assertEqual(len(before),3)
            self.assertEqual(list(connection.execute("PRAGMA foreign_key_check")),[])
        finally:
            connection.close()
        reset_identity=oracle._sealed_identity(reset)
        proof_copy=output/"typed-copy/store.sqlite";proof_copy.parent.mkdir();shutil.copy2(reset,proof_copy)
        self.assertEqual(oracle._sealed_identity(proof_copy),reset_identity)
        events=output/"anchored-provider.jsonl"
        argv=[str(runtime),"verify-history","--socket","/unused","--volume","unused","--daemon","/unused",
              "--case",extra["case"],"--uid","1","--gid","1","--manifest",str(manifest),
              "--sealed",str(proof_copy),"--history-file",str(transcript),"--receipt",str(events)]
        oracle.write_new(output/"typed-proof-attempt.json",{"argv":argv,"attempts":1,"wall_stop_seconds":25,
            "runtime_sha256":runtime_sha,"input_identity":reset_identity,"profile":"Disposable/WAL/OFF",
            "construction_workers":1,"scope":"offline public typed proof on independent native copy; no Docker/mount/sample"})
        with (output/"typed-proof.stdout").open("xb") as stdout,(output/"typed-proof.stderr").open("xb") as stderr:
            child=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                 env={**os.environ,"LAYERFS_CONSTRUCTION_WORKERS":"1"},timeout=25)
        oracle.write_new(output/"typed-proof-completion.json",{"exit_code":child.returncode,"runtime_sha256":oracle.file_sha(runtime)})
        self.assertEqual(child.returncode,0,(output/"typed-proof.stderr").read_text())
        actual=provider_fields(events)
        self.assertEqual(actual.get("status"),"PASS")
        self.assertEqual(actual["provider_validation"],"current-public-schema-source-binding-validated")
        self.assertEqual(actual["final_head_commit_id"],expected[-1]["commit_id"])
        self.assertEqual(actual["commits"],2)
        self.assertEqual(actual["provider_store_sha256"],reset_identity["sha256"])
        self.assertEqual(oracle.file_sha(runtime),runtime_sha)
        with self.assertRaisesRegex(ValueError,"global Commit membership or five-field tuples differ") as rejected:
            oracle._commit_census_read_only(reset,expected,actual,manifest,transcript)
        self.assertEqual(oracle._sealed_identity(reset),reset_identity)
        oracle.write_new(output/"qualification.json",{"schema":"fs-bench-pro-public-canonical-census-regression-v1",
            "status":"PASS","baseline_census":baseline_result,"actual_anchored_public_provider":actual,
            "unfiltered_census":"EXPECTED_FAIL","reason":str(rejected.exception),"extra_canonical_public_commit":extra,
            "unchanged_immutable_source":reset_identity,"runtime_sha256":runtime_sha,
            "docker_custody":"NOT_APPLICABLE: native public Handles::seal fixture, no daemon/container/volume or mounted case",
            "scope":"publicly saved canonical filesystem objects and public HistoryCatalog Commit; only isolated branch-head restoration; anchored originalK2 actual typed proof stillPASS; same global read-only census rejects unreachableC3"})


if __name__=="__main__":unittest.main()
