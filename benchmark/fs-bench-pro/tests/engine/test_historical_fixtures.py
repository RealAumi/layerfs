"""Historical setup admission with mocked callbacks/tools; no real Store or Docker."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, workspace


def declared(position=0):
    return json.loads((BENCH / "families/historical_access/family.json").read_text())["cases"][position]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class HistoricalFixtures(unittest.TestCase):
    def test_paired_access_automatically_reuses_closed_producer_and_installed_master(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "kept-fixtures"
            first = cache / "first-key"; first.mkdir(parents=True)
            prior, build, current, genesis, _, _ = self.prepared(first, declared(0))
            second = cache / "second-key"; second.mkdir()
            calls = []
            holder = {"closed": prior["closed_producer"]}
            with patch.object(fixtures.identity, "load_build", return_value=build), \
                 patch.object(fixtures.identity, "source_identity", return_value=current), \
                 patch.object(fixtures, "validate_runtime_helpers", return_value={"status": "PASS"}) as helper_check, \
                 patch.object(workspace, "prepare_history_producer") as replay, \
                 patch.object(fixtures, "install_closed_history_store") as install, \
                 patch.object(fixtures.receipts, "command", side_effect=self.tools(declared(1), calls, holder)):
                result = fixtures.prepare_historical_workspace({"family": "historical_access"},
                    declared(1), second / "access", "mock-build")
            replay.assert_not_called(); install.assert_not_called()
            helper_check.assert_called_once()
            self.assertEqual(result["closed_producer"], prior["closed_producer"])
            self.assertEqual(result["master_volume"], prior["master_volume"])
            self.assertEqual(result["provision"], prior["provision"])
            self.assertEqual(result["historical_selection"]["local"], 49)
            self.assertEqual(result["closed_master_reuse"]["store_sha256"], prior["closed_producer"]["store_sha256"])

    def inputs(self, folder, case):
        tools = {"socket": "mock-socket", "binaries": {}}
        for name in ("workspace-writer", "workload-linux"):
            path = folder / name; path.write_text("mock sealed binary " + name)
            tools["binaries"][name] = {"path": str(path), "sha256": fixtures.identity.sha256(path)}
        current = {"source_commit": "mock-source", "source_tree": "mock-tree", "product_tree": "mock-product",
                   "source_clean": True, "files": {path: fixtures.identity.sha256(fixtures.identity.ROOT / path) for path in fixtures.CONTEXT_SOURCE_FILES}}
        plan = fixtures.historical_plan(case)
        genesis_folder = folder / "immutable-genesis"; genesis_folder.mkdir()
        store = genesis_folder / "initial.sqlite"; store.write_bytes(b"mocked genesis bytes, not SQLite")
        manifest = genesis_folder / "installed.manifest"; manifest.write_text("mocked immutable initial manifest\n")
        genesis = {"schema": fixtures.CONTEXT_PREPARED_SCHEMA if plan["producer_family"] == "branch_development" else "fs-bench-pro-prepared-workspace-v1",
                   "status": "PASS", "family": plan["producer_family"], "case": plan["producer_case"], "recipe": plan["producer_case"],
                   "identity": current, "global_profile": "Disposable/WAL/OFF", "source_uid": 501, "source_gid": 20,
                   "fixture": {"fixture_sha256": digest("pristine fixture"), "logical_bytes": 0, "files": 0},
                   "helpers": {"root": "mocked genesis code", "files": {}}, "master_volume": "mock-immutable-genesis",
                   "native_verification": {"initial": {"verification_status": "pass"}},
                   "provision": {"sealed_store": str(store), "store_sha256": fixtures.identity.sha256(store),
                                 "manifest": str(manifest), "manifest_sha256": fixtures.identity.sha256(manifest)},
                   "prepared_folder": str(genesis_folder)}
        fixtures.receipts.write_new(genesis_folder / "prepared.json", genesis)
        fixtures.receipts.manifest(genesis_folder)
        return tools, current, genesis

    def closed(self, case, genesis, current, output, *, duplicate=False):
        output = Path(output); output.mkdir()
        plan = fixtures.historical_plan(case)
        graph = {"branches": {}}; by_role = {}; acks = []; rows = ["topology-v1\t" + plan["producer_case"]]
        for role in plan["graph_roles"]:
            source = plan["fork_sources"].get(role, {"role": None, "local": 0})
            parent = by_role[source["role"]][source["local"]]["commit_id"] if source["role"] else "-"
            root = by_role[source["role"]][source["local"]]["root_id"] if source["role"] else digest("initial root")
            branch = {"branch_id": digest("branch " + role), "name": "original-" + role, "stack": digest("stack"),
                      "base_layer": digest("base"), "initial_parent": parent, "initial_root": root,
                      "source_role": source["role"], "source_local": source["local"], "commits": []}
            by_role[role] = {}
            for local in range(1, plan["local_commits"].get(role, 0) + 1):
                salt = "shared" if duplicate and role in ("a", "b") else role
                next_root = digest("root " + salt + str(local)); identifier = digest(parent + next_root)
                fields = {"commit_id": identifier, "stack": branch["stack"], "root": next_root, "parent": parent, "base_layer": branch["base_layer"]}
                record = {"index": local, "commit": {"fields": fields}}; branch["commits"].append(record)
                ack = {"role": role, "local": local, "commit_id": identifier, "layer_stack_id": branch["stack"], "root_id": next_root,
                       "parent_commit_id": None if parent == "-" else parent, "base_layer_id": branch["base_layer"]}
                acks.append(ack); by_role[role][local] = ack
                parent, root = identifier, next_root
            branch.update(final_head=parent, final_root=root); graph["branches"][role] = branch
            rows.append("\t".join(["branch", role, branch["branch_id"], branch["name"], branch["stack"], branch["base_layer"],
                                   branch["initial_parent"], branch["initial_root"], parent, root, source["role"] or "-", str(source["local"])]))
            for record in branch["commits"]:
                fields = record["commit"]["fields"]
                rows.append("\t".join(["commit", role, str(record["index"]), fields["commit_id"], fields["stack"], fields["root"],
                                       fields["parent"], fields["base_layer"], "-", "-"]))
        store = output / "closed.sqlite"
        header = bytearray(100); header[:16] = b"SQLite format 3\0"; header[18:20] = bytes([2,2])
        store.write_bytes(bytes(header) + b"mocked header fixture, never opened as SQLite")
        manifest = output / "installed.manifest"; shutil.copy2(genesis["provision"]["manifest"], manifest)
        transcript = output / "transcript.tsv"; transcript.write_text("\n".join(rows) + "\n")
        events = output / "runtime.events.jsonl"; events.write_text('{"event":"stop"}\n{"event":"finished"}\n')
        exported = output / "export.completion.json"; exported.write_text('{"status":"PASS","exit_code":0}\n')
        raw = output / "raw-export"; raw.mkdir()
        (raw / "store.sqlite").write_bytes(b"mocked raw main bytes")
        (raw / "store.sqlite-wal").write_bytes(b"mocked raw WAL bytes")
        raw_files = {path.name: {"sha256": fixtures.identity.sha256(path), "size": path.stat().st_size} for path in raw.iterdir()}
        normalized_identity = {"sha256": fixtures.identity.sha256(store), "size": store.stat().st_size}
        normalized = {"schema":"fs-bench-pro-closed-store-normalization-v1", "status":"PASS", "profile":"Disposable/WAL/OFF",
                      "raw_directory":str(raw), "path":str(store), "raw_files":raw_files, "raw_files_after":raw_files,
                      "copied_files":raw_files, "raw_unchanged":True, "source_closed":True, "target_closed":True,
                      "normalized_identity":normalized_identity, "source_uri_mode":"ro", "source_query_only":1,
                      "source_synchronous":0, "target_synchronous":0, "source_journal_mode":"wal", "target_journal_mode":"wal",
                      "backup_pages_per_step":128, "backup_sleep_seconds":0, "backup_attempts":1, "checkpoint":[0,0,0],
                      "backup_progress":{"calls":1,"remaining_pages":0,"total_pages":1,"last_status":101},
                      "helper_sha256":fixtures.identity.sha256(fixtures.identity.ROOT / "benchmark/fs-bench-pro/engine/oracle.py")}
        normalization = output / "normalization.json"; normalization.write_text(json.dumps(normalized))
        attempt_folder = output / "mocked-attempt"; attempt_folder.mkdir(); attempt = attempt_folder / "receipt.json"
        attempt.write_text(json.dumps({"setup_only":True, "sample_count":0, "status":"INELIGIBLE", "functional_status":"PASS",
                                      "proof_status":"PASS", "cleanup":"Gone", "custody":"KNOWN_STOP", "case":plan["producer_case"],
                                      "source_commit":current["source_commit"], "product_tree":current["product_tree"], "identity":current}))
        fixtures.receipts.manifest(attempt_folder)
        result = {"schema": "fs-bench-pro-closed-history-producer-v1", "status": "PASS", "producer_case": plan["producer_case"],
                  "producer_family": plan["producer_family"], "source_commit": current["source_commit"], "source_tree": current["source_tree"],
                  "product_tree": current["product_tree"], "seed": 1, "setup_only": True, "sample_count": 0,
                  "initial_prepared": genesis["prepared_folder"], "manifest": str(manifest), "manifest_sha256": fixtures.identity.sha256(manifest),
                  "sealed_store": str(store), "store_sha256": fixtures.identity.sha256(store), "transcript": str(transcript),
                  "transcript_sha256": fixtures.identity.sha256(transcript), "graph": graph, "acknowledgements": acks,
                  "custody": {"state": "KNOWN_STOP", "all_workspaces_gone": True, "active_executions": 0,
                              "runtime_events": str(events), "runtime_events_sha256": fixtures.identity.sha256(events),
                              "export_completion": str(exported), "export_completion_sha256": fixtures.identity.sha256(exported)},
                  "raw_export": str(raw), "helpers": genesis["helpers"],
                  "normalization":{"receipt":str(normalization),"receipt_sha256":fixtures.identity.sha256(normalization),
                                   "path":str(store),"raw_directory":str(raw),"raw_files":raw_files,"normalized_identity":normalized_identity},
                  "attempt_receipt":str(attempt),"attempt_receipt_sha256":fixtures.identity.sha256(attempt),
                  "attempt_manifest":str(attempt_folder/"manifest.json"),"attempt_manifest_sha256":fixtures.identity.sha256(attempt_folder/"manifest.json")}
        self.summary(result, output / "producer-summary.json")
        return result

    def summary(self, record, path=None):
        path = Path(path or record["receipt"])
        path.write_text(json.dumps({key: value for key, value in record.items() if key not in ("receipt", "receipt_sha256")}))
        record.update(receipt=str(path), receipt_sha256=fixtures.identity.sha256(path))

    def tools(self, case, calls, holder, *, wrong_native=False, bad_install=False):
        def command(argv, out, label, seconds, **options):
            calls.append((argv, label, seconds, options)); self.assertLessEqual(seconds, 120)
            output = Path(out) / (label + ".stdout")
            plan = fixtures.historical_plan(case)
            if argv[0] == "docker":
                if label == "historical-master-volume": value = argv[-1] + "\n"
                elif label == "historical-master-install": value = "backing_directory=0:0:700\nbacking_store=0:0:600\n" + ("0" * 64 if bad_install else holder["closed"]["store_sha256"]) + "  /dest/global/store.sqlite\n"
                else: value = "mocked Docker, no actual execution\n"
                output.write_text(value)
            elif argv[1] in ("expected-step", "materialize-context"):
                compact = argv[1] == "materialize-context"; root = Path(argv[-1]); root.mkdir()
                lines = ["workspace-independent-manifest-v1", ".\tdirectory\t0\t755\t1700000000\t0\t-"]
                targets = case["historical_access"]["reads"]
                for index, target in enumerate(targets):
                    path = root / target["path"]; path.parent.mkdir(parents=True, exist_ok=True)
                    if index and case["historical_access"]["required_relations"]["inode_pair_dev_ino_equal_and_nlink2"]:
                        os.link(root / targets[0]["path"], path)
                        lines.append(f"{target['path']}\thardlink\t0\t640\t1700000000\t0\t{targets[0]['path'].encode().hex()}")
                    else:
                        data = bytes([plan["selected_local"]]) * target["bytes"]; path.write_bytes(data)
                        lines.append(f"{target['path']}\tfile\t{len(data)}\t640\t1700000000\t0\t{hashlib.sha256(data).hexdigest()}")
                manifest = root.with_suffix(".manifest.tsv"); manifest.write_text("\n".join(lines) + "\n")
                value = {"case": plan["producer_case"], "seed": 1, "step": 1 if wrong_native else plan["selected_local"], "entries": len(lines)-1,
                         "logical_bytes": sum(row["bytes"] for row in targets), "files": len(targets), "recipe_identity": "a" * 64,
                         "manifest_sha256" if compact else "fixture_digest": fixtures.identity.sha256(manifest)}
                if compact: value["role"] = plan["source_role"]
                output.write_text(json.dumps(value))
            elif argv[1] in ("verify-step", "verify-context"):
                value = {"case": plan["producer_case"], "step": plan["selected_local"], "verification_status": "pass"}
                if argv[1] == "verify-context": value["role"] = plan["source_role"]
                output.write_text(json.dumps(value))
            else: self.fail("unexpected mocked command " + repr(argv))
            return {"stdout": str(output), "status": "PASS", "exit_code": 0}
        return command

    def prepared(self, folder, case, *, supplied=True, wrong_native=False, bad_install=False):
        build, current, genesis = self.inputs(folder, case); calls = []; holder = {}; callbacks = []
        def callback(family, producer, initial, build_folder, output):
            callbacks.append((family, producer, initial, build_folder, str(output)))
            self.assertFalse(Path(output).exists())
            holder["closed"] = self.closed(case, genesis, current, output)
            return holder["closed"]
        with patch.object(fixtures.identity, "load_build", return_value=build), \
             patch.object(fixtures.identity, "source_identity", return_value=current), \
             patch.object(fixtures, "historical_genesis", return_value=genesis), \
             patch.object(workspace, "prepare_history_producer", side_effect=callback, create=True), \
             patch.object(fixtures.receipts, "command", side_effect=self.tools(case, calls, holder, wrong_native=wrong_native, bad_install=bad_install)):
            result = fixtures.prepare_historical_workspace({"family": "historical_access"}, case, folder / "access", "mock-build",
                                                           genesis["prepared_folder"] if supplied else None)
        return result, build, current, genesis, calls, callbacks

    def test_six_original_selections_have_four_complete_producers_and_local_ordinals(self):
        plans = [fixtures.historical_plan(declared(index)) for index in range(6)]
        self.assertEqual(len({plan["producer_case"] for plan in plans}), 4)
        self.assertEqual([(p["source_role"], p["selected_local"]) for p in plans], [("main",48),("main",49),("main",94),("main",95),("trunk",5),("b",10)])
        self.assertEqual([p["acknowledgements"] for p in plans], [100,100,100,100,30,40])
        self.assertEqual(plans[0]["graph_roles"], ["main"])
        self.assertEqual(plans[5]["original_source_role"], "B")
        self.assertEqual(plans[5]["fork_sources"]["c"], {"role":"a","local":5})
        for field in ("producer", "producer_branch_role", "selected_ordinal"):
            case=declared(); case["historical_access"][field]="different"
            with self.subTest(field=field), self.assertRaises(ValueError): fixtures.historical_plan(case)

    def test_complete_closed_producer_accepts_equal_canonical_tuples_and_json_key_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); case=declared(4); _,current,genesis=self.inputs(folder,case)
            closed=self.closed(case,genesis,current,folder/"producer",duplicate=True)
            closed=json.loads(json.dumps(closed,sort_keys=True))
            admitted=fixtures.validate_closed_history_producer(case,closed,genesis,current)
            self.assertEqual(admitted["selected"]["local"],5)
            self.assertLess(admitted["distinct_commit_tuples"],30)

    def test_missing_ack_parent_fork_head_custody_or_changed_store_receipt_is_refused(self):
        for variant in ("ack", "parent", "fork", "head", "custody", "active", "source", "sample", "store", "summary", "transcript", "export", "wal", "sidecar", "normalization", "attempt"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary); case=declared(5); _,current,genesis=self.inputs(folder,case)
                closed=self.closed(case,genesis,current,folder/"producer")
                if variant=="ack": closed["acknowledgements"].pop()
                elif variant=="parent": closed["graph"]["branches"]["b"]["commits"][0]["commit"]["fields"]["parent"]="-"
                elif variant=="fork": closed["graph"]["branches"]["c"]["source_local"]=6
                elif variant=="head": closed["graph"]["branches"]["trunk"]["final_head"]="-"
                elif variant=="custody": closed["custody"]["state"]="UNAVAILABLE"
                elif variant=="active": closed["custody"]["active_executions"]=1
                elif variant=="source": closed["product_tree"]="other-product"
                elif variant=="sample": closed["setup_only"]=False; closed["sample_count"]=1
                elif variant=="store": Path(closed["sealed_store"]).write_bytes(b"mutated measured sample")
                elif variant=="summary": Path(closed["receipt"]).write_text("{}")
                elif variant=="transcript":
                    path=Path(closed["transcript"]); path.write_text(path.read_text().replace("\t5\t","\t6\t",1)); closed["transcript_sha256"]=fixtures.identity.sha256(path)
                elif variant=="export":
                    path=Path(closed["custody"]["export_completion"]); path.write_text('{"status":"FAIL","exit_code":124}')
                    closed["custody"]["export_completion_sha256"]=fixtures.identity.sha256(path)
                elif variant=="wal": Path(closed["raw_export"],"store.sqlite-wal").write_bytes(b"changed WAL")
                elif variant=="sidecar": Path(closed["sealed_store"]+"-wal").write_bytes(b"unclosed")
                elif variant=="normalization":
                    path=Path(closed["normalization"]["receipt"]); value=json.loads(path.read_text()); value["backup_attempts"]=2
                    path.write_text(json.dumps(value)); closed["normalization"]["receipt_sha256"]=fixtures.identity.sha256(path)
                else: Path(closed["attempt_receipt"]).write_text('{"setup_only":false,"sample_count":1}')
                if variant!="summary": self.summary(closed)
                with patch.object(fixtures.receipts,"command") as effect, self.assertRaises(ValueError):
                    fixtures.validate_closed_history_producer(case,closed,genesis,current)
                effect.assert_not_called()

    def test_access_preparation_has_fresh_closed_install_unchanged_reader_and_selected_native_scope(self):
        for index in range(6):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                case=declared(index); result,build,current,genesis,calls,callbacks=self.prepared(Path(temporary),case)
                self.assertEqual(len(callbacks),1); self.assertTrue(callbacks[0][-1].endswith("/access/producer"))
                self.assertEqual(result["schema"],fixtures.HISTORICAL_PREPARED_SCHEMA)
                self.assertNotEqual(result["master_volume"],genesis["master_volume"])
                self.assertEqual(result["provision"]["store_sha256"],result["closed_producer"]["store_sha256"])
                self.assertEqual(result["historical_selection"]["local"],case["historical_access"]["selected_ordinal"])
                self.assertEqual(len([x for x in calls if x[1]=="historical-selected-native"]),1)
                self.assertFalse(any("v016-access-read" in argv or "provision" in argv for argv,_,_,_ in calls))
                before={str(p):fixtures.identity.sha256(p) for p in Path(temporary).rglob("*") if p.is_file()}
                with patch.object(fixtures,"load",return_value=genesis),patch.object(fixtures.receipts,"command") as effect:
                    self.assertEqual(fixtures.validate_runtime_helpers(case,result,build)["status"],"PASS")
                effect.assert_not_called()
                self.assertEqual(before,{str(p):fixtures.identity.sha256(p) for p in Path(temporary).rglob("*") if p.is_file()})

    def test_immutable_genesis_reuse_is_explicit_and_measured_sample_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); case=declared(); build,current,genesis=self.inputs(folder,case); plan=fixtures.historical_plan(case)
            with patch.object(fixtures,"load",return_value=genesis),patch.object(fixtures,"prepare") as prepared,patch.object(fixtures,"validate_runtime_helpers"):
                accepted=fixtures.historical_genesis(plan,folder,"build",build,current,genesis["prepared_folder"])
            prepared.assert_not_called(); self.assertEqual(accepted["master_volume"],genesis["master_volume"])
            measured=copy.deepcopy(genesis); measured["schema"]="fs-bench-pro-workspace-family-v1"
            with patch.object(fixtures,"load",return_value=measured),patch.object(fixtures,"prepare") as prepared, self.assertRaises(ValueError):
                fixtures.historical_genesis(plan,folder,"build",build,current,genesis["prepared_folder"])
            prepared.assert_not_called()
            with patch.object(fixtures,"load",return_value=genesis),patch.object(fixtures,"prepare") as prepared,patch.object(fixtures,"validate_runtime_helpers"):
                fixtures.historical_genesis(plan,folder,"build",build,current)
            prepared.assert_called_once_with(plan["producer_case"],folder/"genesis","build")

    def test_explicit_paired_reuse_preserves_closed_receipts_and_never_replays_producer(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); case = declared(1)
            build, current, genesis = self.inputs(folder, case)
            closed = self.closed(case, genesis, current, folder / "prior-producer")
            before = {str(p): fixtures.identity.sha256(p) for p in (folder / "prior-producer").rglob("*") if p.is_file()}
            calls = []; holder = {"closed": closed}
            with patch.object(fixtures.identity, "load_build", return_value=build), \
                 patch.object(fixtures.identity, "source_identity", return_value=current), \
                 patch.object(fixtures, "load_closed_history_producer", return_value=(closed, genesis)) as reused, \
                 patch.object(workspace, "prepare_history_producer") as replay, \
                 patch.object(fixtures.receipts, "command", side_effect=self.tools(case, calls, holder)):
                result = fixtures.prepare_historical_workspace({"family":"historical_access"}, case, folder / "paired", "mock-build",
                                                               closed_producer_folder=folder / "first-access")
            replay.assert_not_called(); reused.assert_called_once()
            self.assertEqual(result["closed_producer"], closed)
            self.assertEqual(result["historical_selection"]["local"], 49)
            self.assertEqual(result["producer_dependency"]["source_admission"]["status"], "PASS")
            self.assertEqual(result["producer_dependency"]["reused_closed_producer"], str((folder / "first-access").resolve()))
            self.assertEqual(before, {str(p): fixtures.identity.sha256(p) for p in (folder / "prior-producer").rglob("*") if p.is_file()})

    def test_reuse_requires_original_source_identity_and_exact_execution_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); case=declared(); _,current,genesis=self.inputs(folder,case)
            closed=self.closed(case,genesis,current,folder/"producer")
            attempt=json.loads(Path(closed["attempt_receipt"]).read_text())
            changed=copy.deepcopy(current); changed["source_commit"]="new-doc-commit"; changed["source_tree"]="new-doc-tree"
            result=fixtures.historical_source_admission(closed,attempt,changed)
            self.assertEqual(result["original_source_commit"],current["source_commit"])
            self.assertEqual(result["current_source_commit"],changed["source_commit"])
            for variant in ("identity", "model", "membership"):
                bad=copy.deepcopy(changed); old=copy.deepcopy(attempt)
                if variant=="identity": old["identity"]["source_clean"]=False
                elif variant=="model": bad["files"][fixtures.CONTEXT_SOURCE_FILES[0]]="0"*64
                else: bad["files"]["undeclared.py"]="0"*64
                with self.subTest(variant=variant), self.assertRaises(ValueError):
                    fixtures.historical_source_admission(closed,old,bad)

    def test_fixture_scope_excludes_only_reuse_adapters_and_retains_every_producer_function(self):
        source=(BENCH/"engine/fixtures.py").read_text()
        self.assertEqual(fixtures.historical_fixture_scope(source), fixtures.historical_fixture_scope(source.replace('"exact_source_files"', '"same_count"')))
        self.assertNotEqual(fixtures.historical_fixture_scope(source), fixtures.historical_fixture_scope(source.replace('"v016-access-boundary-before-v1"', '"changed-original-case"')))
        self.assertNotEqual(fixtures.historical_fixture_scope(source), fixtures.historical_fixture_scope(source.replace('master_measurement_mounts", 0) != 0', 'master_measurement_mounts", 0) != 1')))

    def test_only_reviewed_non_producer_adapters_can_differ_between_source_snapshots(self):
        for kind,adapter in (("workspace","access_graph_proof"),("receipts","result_rows")):
            before="def producer():\n    return 7\n\ndef "+adapter+"():\n    return 0\n"
            after=before.replace("return 0","return 1")
            self.assertEqual(fixtures.historical_adapter_scope(before,kind),fixtures.historical_adapter_scope(after,kind))
            self.assertNotEqual(fixtures.historical_adapter_scope(before,kind),fixtures.historical_adapter_scope(after.replace("return 7","return 8"),kind))

    def test_stored_preparation_admission_reads_its_committed_snapshot_not_later_files(self):
        path="benchmark/fs-bench-pro/engine/workspace.py"
        before=b"def producer():\n    return 7\n\ndef access_graph_proof():\n    return 0\n"
        after=before.replace(b"return 0",b"return 1")
        original={"source_commit":"producer-source","source_tree":"producer-tree","product_tree":"product", "source_clean":True,
                  "files":{path:hashlib.sha256(before).hexdigest()}}
        current={**original,"source_commit":"prepared-source","source_tree":"prepared-tree","files":{path:hashlib.sha256(after).hexdigest()}}
        closed={name:original[name] for name in ("source_commit","source_tree","product_tree")}
        attempt={"identity":original,"source_commit":original["source_commit"]}
        with patch.object(fixtures.subprocess,"check_output",side_effect=[before,after]) as snapshots:
            admitted=fixtures.historical_source_admission(closed,attempt,current)
        self.assertEqual(admitted["status"],"PASS")
        self.assertEqual(snapshots.call_args_list[1].args[0][2],"prepared-source:"+path)
        with patch.object(fixtures.subprocess,"check_output",side_effect=[before,b"substituted source"]),self.assertRaisesRegex(ValueError,"blob seal differs"):
            fixtures.historical_source_admission(closed,attempt,current)

    def test_historical_install_keeps_private_daemon_backing_separate_from_workspace_uid(self):
        with tempfile.TemporaryDirectory() as temporary:
            _,_,_,genesis,calls,_=self.prepared(Path(temporary),declared())
            self.assertEqual((genesis["source_uid"],genesis["source_gid"]),(501,20))
            create=next(argv for argv,label,_,_ in calls if label=="historical-master-create")
            body=create[-1]
            self.assertIn("chown 0:0 /dest/global /dest/global/store.sqlite",body)
            self.assertIn("chmod 600 /dest/global/store.sqlite",body)
            self.assertNotIn("chown 501:20",body)
            self.assertEqual(create[create.index("--user")+1],"0:0")
            self.assertIn("backing_directory=%u:%g:%a",body)
            self.assertIn("backing_store=%u:%g:%a",body)

    def test_bad_daemon_backing_readback_is_refused_before_passing_removal(self):
        original_tools=self.tools
        for before,after in (("backing_directory=0:0:700","backing_directory=501:20:700"),
                             ("backing_store=0:0:600","backing_store=501:20:600"),
                             ("backing_store=0:0:600","backing_store=0:0:644")):
            calls=[]
            def tools(case, observed, holder, **options):
                command=original_tools(case,observed,holder,**options)
                def invoke(argv,out,label,seconds,**keywords):
                    calls.append(label);result=command(argv,out,label,seconds,**keywords)
                    if label=="historical-master-install":
                        path=Path(result["stdout"]);path.write_text(path.read_text().replace(before,after))
                    return result
                return invoke
            with self.subTest(after=after),tempfile.TemporaryDirectory() as temporary,patch.object(self,"tools",side_effect=tools):
                with self.assertRaisesRegex(ValueError,"Store installation differs"):
                    self.prepared(Path(temporary),declared())
            self.assertNotIn("historical-master-remove-passing",calls)

    def test_bad_selected_native_binding_and_bad_install_are_retained_without_retry(self):
        for variant in ("native","install"):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary,self.assertRaises(ValueError):
                self.prepared(Path(temporary),declared(),wrong_native=variant=="native",bad_install=variant=="install")
                self.fail("bad mocked native/install was admitted")

    def test_resealed_selection_reader_or_extra_asset_is_refused_readonly(self):
        for variant in ("selected","bytes","manifest","source","reader","extra"):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary:
                case=declared(5); result,build,_,genesis,_,_=self.prepared(Path(temporary),case)
                bad=copy.deepcopy(result); root=Path(bad["helpers"]["root"])
                if variant=="selected": bad["historical_selection"]["acknowledged_commit"]["local"]=9
                elif variant=="bytes": bad["historical_selection"]["read_targets"][0]["hex"]="00"*65536
                elif variant=="manifest":
                    path=Path(bad["historical_selection"]["manifest"]); path.write_text(path.read_text().replace("640","600"))
                    bad["historical_selection"]["manifest_sha256"]=fixtures.identity.sha256(path)
                elif variant=="source": bad["producer_dependency"]["source_binding"]["model_files"][fixtures.CONTEXT_SOURCE_FILES[0]]="0"*64
                elif variant=="reader":
                    path=root/"workload.sh"; path.chmod(0o644); path.write_text("pre-read warmup\n")
                    bad["helpers"]["files"]["workload.sh"]=fixtures.identity.sha256(path)
                else:
                    path=root/"warmup.sh"; path.write_text("undeclared read\n"); bad["helpers"]["files"]["warmup.sh"]=fixtures.identity.sha256(path)
                metadata=root/"access/dependency.json"; metadata.chmod(0o644)
                metadata.write_text(json.dumps({"producer_dependency":bad["producer_dependency"],"historical_selection":bad["historical_selection"]}))
                bad["helpers"]["files"]["access/dependency.json"]=fixtures.identity.sha256(metadata)
                with patch.object(fixtures,"load",return_value=genesis),patch.object(fixtures.receipts,"command") as effect,self.assertRaises(ValueError):
                    fixtures.validate_runtime_helpers(case,bad,build)
                effect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
