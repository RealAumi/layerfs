"""Original selections, direct selected transitions and complete tree oracles."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/repository_history"
spec = importlib.util.spec_from_file_location("repository_recipe", BENCH / "engine/recipes/repository_history.py")
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class RepositoryHistory(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FAMILY / "family.json").read_text())

    def test_exact_selected_indices_outcomes_original_limits_and_resource_scopes(self):
        self.assertEqual([c["id"] for c in self.document["cases"]], list(recipe.SELECTIONS))
        for row in self.document["cases"]:
            case = row["id"]
            indices = list(recipe.SELECTIONS[case])
            count = len(indices)
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["fixture"]["selection"], indices)
            self.assertEqual([s["full157_index"] for s in row["steps"]], indices)
            self.assertEqual([s["index"] for s in row["steps"]], list(range(1, count+1)))
            self.assertEqual([s["previous_full157_index"] for s in row["steps"]], [None]+indices[:-1])
            self.assertEqual(row["repository_schedule"]["verification_indices"], list(range(1, count+1)))
            self.assertEqual(row["repository_schedule"]["require_created"], case != "deepseek-full")
            self.assertFalse(row["repository_schedule"]["skipped_states_replayed"])
            self.assertTrue(row["repository_schedule"]["no_component_history_substitution"])
            self.assertTrue(row["repository_schedule"]["freeze_storage_before_verification"])
            self.assertEqual(row["repository_schedule"]["performance_mounts"], 1)
            self.assertEqual(row["budget"]["original_performance_phase_ms"], 14400000)
            self.assertEqual(row["budget"]["original_operation_watchdog_ms"], 300000)
            self.assertEqual(row["budget"]["original_verification_phase_ms"], 14400000)
            self.assertEqual(row["budget"]["original_verifier_operation_ms"], 300000)
            for key in ("performance_hard_watchdog_ms", "operation_watchdog_ms", "verifier_ms",
                        "verification_hard_watchdog_ms", "wall_stop_ms"):
                self.assertEqual(row["budget"][key], 120000)
            resources = row["resource_profile"]
            self.assertEqual([resources[k] for k in ("store_and_sidecar_limit_bytes", "spool_plus_staging_limit_bytes",
                              "owned_output_limit_bytes", "host_free_reserve_bytes", "host_sampled_rss_limit_bytes")],
                             [n*1024**3 for n in (16, 16, 32, 50, 8)])
            self.assertEqual((resources["cpus"], resources["memory_bytes"], resources["memory_swap_bytes"], resources["pids_limit"]),
                             (2, 2*1024**3, 2*1024**3, 256))
            self.assertIn("does not assert mtime", row["oracle"]["omissions"])
            self.assertIn("INELIGIBLE", row["cache_contract"]["iteration"])

    def test_frozen_operation_sources_and_read_only_real_manifest_identity(self):
        review = self.document["cases"][0]["port_review"]
        for path, digest in review["files"].items():
            actual = (ROOT / path).read_bytes()
            frozen = subprocess.check_output(["git", "show", review["source_commit"]+":"+path], cwd=ROOT)
            self.assertEqual(actual, frozen, path)
            self.assertEqual(hashlib.sha256(actual).hexdigest(), digest)
        data = Path(self.document["cases"][0]["fixture"]["source_corpus"])
        raw, manifest = recipe.read_manifest(data)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), recipe.MANIFEST_SHA)
        self.assertEqual(manifest["tip"], recipe.SOURCE_TIP)
        for row in self.document["cases"]:
            selected = [manifest["checkpoints"][i-1] for i in recipe.SELECTIONS[row["id"]]]
            self.assertEqual(row["fixture"]["selected_logical_bytes_sum"], sum(s["logical_bytes"] for s in selected))
            self.assertEqual(row["fixture"]["selected_file_occurrence_sum"], sum(s["files"] for s in selected))

    def test_wrapper_preserves_exact_mounted_helper_dispatch_and_refuses_other_cases(self):
        with tempfile.TemporaryDirectory(prefix="repository-wrapper-") as temporary:
            helper = Path(temporary) / "helper"
            helper.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            helper.chmod(0o755)
            env = dict(os.environ, WORKLOAD_WRITER=str(helper), LAYERFS_WORKSPACE_ROOT="/actual/mount")
            def invoke(*args):
                return subprocess.run(["bash", str(FAMILY/"workload.sh"), *args], env=env,
                                      capture_output=True, text=True, timeout=3)
            for case, indices in recipe.SELECTIONS.items():
                for index in (1, len(indices)):
                    result = invoke("apply", case, str(index), "/sealed/checkpoint")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), ["storage-smoke-import", "/sealed/checkpoint", "/actual/mount"])
                    result = invoke("verify", case, str(index), "/input/observed.tsv")
                    self.assertEqual(json.loads(result.stdout), ["storage-smoke-observe", "/actual/mount", "/input/observed.tsv"])
            for args in [("apply", "deepseek-full", "0", "/input"), ("apply", "deepseek-full", "0157", "/input"),
                         ("apply", "deepseek-stride3", "54", "/input"), ("verify", "deepseek-stride10", "18", "/out"),
                         ("apply", "deepseek-ten", "1", "/input"), ("fixture", "deepseek-full", "1", "/input"),
                         ("apply", "deepseek-full", "1", ""), ("apply", "deepseek-full", "1", "/input", "extra")]:
                result = invoke(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""), args)

    def corpus(self, root):
        data = root / "corpus"
        (data/"oracles").mkdir(parents=True)
        (data/"inputs").mkdir()
        (data/"source.git").mkdir()
        path = b"dir/file.txt".hex()
        blobs, trees, rows, previous = {}, {}, [], {}
        for index in range(1, 158):
            body = b"initial" if index == 1 else b"changed-at-skipped-two" if index < 12 else b"changed-at-twelve"
            oid = hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()
            blobs[oid] = body
            raw = b"100644 blob "+oid.encode()+b" "+str(len(body)).encode()+b"\t"+bytes.fromhex(path)+b"\0"
            sha = f"{index:040x}"
            row = {"index":index,"sha":sha,"tree":f"{index+1000:040x}","files":1,"logical_bytes":len(body),
                   "manifest_sha256":hashlib.sha256(raw).hexdigest()}
            rows.append(row)
            trees[sha] = raw
            tree = recipe.entries(raw)
            source = data/"inputs"/sha
            (source/"blobs").mkdir(parents=True)
            (source/"manifest.tsv").write_text(recipe.encode(tree))
            (source/"previous.tsv").write_text(recipe.encode(previous))
            if tree != previous:
                (source/"blobs"/oid).write_bytes(body)
            saved = {"key":hashlib.sha256(recipe.encode(previous).encode()+b"\0"+raw).hexdigest(),
                     "files":recipe.membership(source,time.monotonic()+10)["files"]}
            source.with_suffix(".receipt.json").write_text(json.dumps(saved))
            oracle = {path:["100644",len(body),hashlib.sha256(body).hexdigest()], b"dir".hex():["40755",0,"-"]}
            (data/"oracles"/(sha+".json")).write_text(json.dumps(oracle))
            previous = tree
        manifest = {"tip":recipe.SOURCE_TIP,"checkpoints":rows}
        raw = json.dumps(manifest).encode()
        (data/"checkpoint-manifest.json").write_bytes(raw)
        return data, hashlib.sha256(raw).hexdigest(), blobs, trees

    def patches(self, digest, blobs, trees):
        class SourceBlobs:
            def __init__(self, data, stderr):
                self.data = Path(data)
                Path(stderr).write_bytes(b"")
            def copy(self, oid, size, output, deadline):
                source = self.data/"test-blobs"/oid
                return recipe.copy_cached_blob(source, oid, size, output, deadline)
            def finish(self, deadline):
                recipe.remaining(deadline, "synthetic source batch completion")
            def close(self):
                pass
        def git_tree(data, row, deadline):
            recipe.remaining(deadline, "synthetic tree")
            raw = trees[row["sha"]]
            if hashlib.sha256(raw).hexdigest() != row["manifest_sha256"]:
                raise ValueError("original raw Git tree manifest identity")
            return raw, recipe.entries(raw)
        return patch.object(recipe,"MANIFEST_SHA",digest), patch.object(recipe,"GitBlobs",SourceBlobs), patch.object(recipe,"git_tree",git_tree)

    def test_exact_three_transition_recipes_and_stride_skipped_change_do_not_replay_states(self):
        with tempfile.TemporaryDirectory(prefix="repository-recipes-") as temporary:
            root = Path(temporary)
            data,digest,blobs,trees = self.corpus(root)
            (data/"test-blobs").mkdir()
            for oid,body in blobs.items(): (data/"test-blobs"/oid).write_bytes(body)
            before = recipe.membership(data,time.monotonic()+10)
            a,b,c = self.patches(digest,blobs,trees)
            with a,b,c:
                for case,indices in recipe.SELECTIONS.items():
                    prepared = recipe.authenticate_and_prepare(data,case,root/case,time.monotonic()+20)
                    self.assertEqual(prepared["full157_indices"],list(indices))
                    self.assertEqual(prepared["state_count"],len(indices))
                    self.assertEqual([s["previous_full157_index"] for s in prepared["states"]],[None]+list(indices[:-1]))
                    second = prepared["states"][1]
                    expected_previous = prepared["states"][0]
                    self.assertEqual((Path(second["input"])/"previous.tsv").read_text(),
                                     (Path(expected_previous["input"])/"manifest.tsv").read_text())
                    if case != "deepseek-full":
                        # Both selected transitions change relative to state1 even
                        # though adjacent full157 input state4 has no changed blobs.
                        self.assertEqual(len(list((Path(second["input"])/"blobs").iterdir())),1)
                    self.assertEqual(prepared["sealed_membership"],recipe.membership(root/case,time.monotonic()+10))
                    self.assertEqual((root/case).stat().st_mode&0o777,0o555)
                    self.assertTrue(all((root/case/n).stat().st_mode&0o777 == 0o444 for n in prepared["sealed_membership"]["files"]))
            self.assertEqual(before,recipe.membership(data,time.monotonic()+10))

    def test_append_only_deadline_blob_and_observed_oracle_guards(self):
        with tempfile.TemporaryDirectory(prefix="repository-negative-") as temporary:
            root = Path(temporary)
            for case,deadline in [("deepseek-ten",time.monotonic()+10), ("deepseek-full",time.monotonic()-1),
                                  ("deepseek-full",time.monotonic()+121)]:
                with self.assertRaises((ValueError,TimeoutError)):
                    recipe.authenticate_and_prepare(root,case,root/"out",deadline)
            source = root/"blob"
            source.write_bytes(b"actual source")
            with self.assertRaisesRegex(ValueError,"Git identity"):
                recipe.copy_cached_blob(source,"0"*40,len(source.read_bytes()),root/"copy",time.monotonic()+5)
            good = {b"dir".hex():["40755",0,"-"], b"dir/link".hex():["120000",3,hashlib.sha256(b"../").hexdigest()]}
            oracle = root/"oracle.json"
            oracle.write_text(json.dumps(good))
            observed = root/"observed.tsv"
            observed.write_text("".join(f"{mode}\t{size}\t{sha}\t{path}\n" for path,(mode,size,sha) in good.items()))
            self.assertEqual(recipe.verify_observed(observed,oracle)["verified_entries"],2)
            observed.write_text(observed.read_text().replace("40755","40700"))
            with self.assertRaises(ValueError): recipe.verify_observed(observed,oracle)
            observed.write_text("120000\t3\t"+"0"*64+"\t"+b"dir/link".hex()+"\n")
            with self.assertRaisesRegex(ValueError,"oracle mismatch"): recipe.verify_observed(observed,oracle)
            observed.write_text("40755\t0\t-\t"+b"dir".hex()+"\n")
            observed.write_text(observed.read_text()*2)
            with self.assertRaisesRegex(ValueError,"duplicate"): recipe.parse_observed(observed)
            for raw in [b"100644 blob "+b"0"*40+b" 1\t../escape\0", b"160000 commit "+b"0"*40+b" 1\tgitlink\0"]:
                with self.assertRaises(ValueError): recipe.entries(raw)


if __name__ == "__main__":
    unittest.main()
