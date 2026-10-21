"""Public SDK covering proof, never a family sample.

Live use (lead only after final seal/prepared qualification):
  perl core/target/r4-locked.pl 120 python3 -B THIS_FILE \
    --build SEALED_BUILD --prepared CLOSED_EMPTY_FIXTURE --out FRESH_RAW
Source-only checks: python3 -B -m unittest discover ... -p test_public_fork_history.py
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import sys
import time
import unittest
import tempfile
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, identity, oracle, receipts, workspace

TEST_ID = "public-sdk-fork-history"
TUPLE_KEYS = ("commit_id", "stack", "root", "parent", "base_layer")


def one_exchange(fields):
    for direction in ("send", "receive"):
        before, after = fields.get(f"control_{direction}_records_before"), fields.get(f"control_{direction}_records_after")
        if type(before) is not int or type(after) is not int or after != before + 1:
            raise ValueError("one actual original SDK exchange required")


def typed(fields):
    """Exact public five-tuple; no root-only or count-only substitutions."""
    values = {key: fields[key] for key in TUPLE_KEYS}
    oracle._hex(values["commit_id"], 33, 0x12)
    oracle._hex(values["stack"], 17, 0x31)
    oracle._hex(values["root"], 32)
    if values["parent"] != "-":
        oracle._hex(values["parent"], 33, 0x12)
    oracle._hex(values["base_layer"], 33, 0x32)
    return values


def history_records(runtime, label, branch, anchor, wanted, folder, stop):
    request = workspace.script(folder, f"history-{label}-{len(runtime.rows)}.tsv", f"{anchor}\t-\t32\n")
    before = len(runtime.rows)
    final = workspace.context_send(runtime, "history", label, request, deadline=stop)
    rows = [event["fields"] for event in runtime.rows[before:] if event["event"] == "history_record"]
    verify_history_page(rows, final["fields"], label, branch, wanted)
    return {"anchor": anchor, "records": rows, "finished": final}


def verify_history_page(rows, final, label, branch, wanted):
    if (final.get("label") != label or final.get("branch_id") != branch
            or type(final.get("records")) is not int or final["records"] != len(wanted)
            or final.get("cursor_path") != "-" or "cursor_sha256" in final or type(final.get("cursor_bytes")) is not int or final["cursor_bytes"] != 0
            or len(rows) != len(wanted)):
        raise ValueError("exact anchored SDK History cardinality/EOF/binding differs")
    for row, expected in zip(rows, wanted):
        if row.get("label") != label or row.get("branch_id") != branch or typed(row) != expected:
            raise ValueError("public SDK History full typed record differs")
    one_exchange(final)


def fork(runtime, label, name, source, commit, initial, output, stop):
    identifier = "11" + secrets.token_hex(16)
    body = (f"layer\t{identifier}\t{name}\n" if source is None else
            f"commit\t{identifier}\t{name}\t{source}\t{commit['commit_id']}\n")
    request = workspace.script(output, f"fork-{label}.tsv", body)
    result = workspace.context_send(runtime, "fork", label, request, deadline=stop)
    fields = result["fields"]
    parent = "-" if commit is None else commit["commit_id"]
    root = initial["root"] if commit is None else commit["root"]
    wanted = {"label": label, "branch_id": identifier, "name": name, "head": parent, "root": root,
              "base_root": initial["root"], "stack": initial["stack"], "base_layer": initial["base_layer"]}
    if any(fields.get(key) != value for key, value in wanted.items()):
        raise ValueError("public SDK Fork exact ancestor/Branch binding differs")
    one_exchange(fields)
    return {**wanted, "initial_parent": parent, "initial_root": root, "commits": [], "event": result}


def command(runtime, key, body, output, label, stop, expected_stdout=b""):
    before = len(runtime.rows)
    path = workspace.script(output, label + ".sh", "set -euo pipefail\n" + body + "\n")
    result = runtime.send("command", key, path, deadline=stop)
    fields = result["fields"]
    if (fields.get("exit_code") != "0" or fields.get("registered_execs") != "0"
            or fields.get("command_sha256") != identity.sha256(path)
            or Path(fields["stdout"]).read_bytes() != expected_stdout
            or Path(fields["stderr"]).read_bytes() != b""):
        raise ValueError("ordinary Bash exact bytes/known zero exit/stream custody differs")
    selected = runtime.rows[before:]
    if len([event for event in selected if event["event"] == "streams"]) != 1 or len([event for event in selected if event["event"] == "exec_status"]) != 1:
        raise ValueError("one stream EOF and original exit inspection required")
    return result


def commit(runtime, key, parent, initial, stop):
    event = runtime.send("commit", key, deadline=stop)
    fields = event["fields"]
    if fields.get("key") != key or fields.get("commit_kind") != "Committed":
        raise ValueError("small changed public operation must produce Committed")
    result = typed(fields)
    if result["parent"] != parent or result["stack"] != initial["stack"] or result["base_layer"] != initial["base_layer"]:
        raise ValueError("public Commit first-parent/stack/base differs")
    return result


def closed_census(path, initial, branches, acknowledgements, manifest):
    """Post-known-Stop immutable global SQL proof; no live or fake family route."""
    before = oracle._sealed_identity(path)
    if Path(path).read_bytes()[18:20] != b"\x02\x02":
        raise ValueError("toy normalized source must preserve WAL header")
    bound = oracle._manifest_identity(manifest)
    if any(initial[key] != bound[key] for key in ("branch_id", "stack_id", "initial_root")):
        raise ValueError("toy census original manifest identity differs")
    expected = sorted((oracle._hex(row["commit_id"],33,0x12), oracle._hex(row["stack"],17,0x31),
                       oracle._hex(row["root"],32), None if row["parent"] == "-" else oracle._hex(row["parent"],33,0x12),
                       oracle._hex(row["base_layer"],33,0x32)) for row in acknowledgements)
    if len({row[0] for row in expected}) != 3 or len(expected) != 3:
        raise ValueError("toy requires exact three distinct acknowledged Commit tuples")
    wanted_branches = sorted((oracle._hex(row["branch_id"],17,0x11), oracle._hex(row["stack"],17,0x31), row["name"],
                              oracle._hex(row["base_layer"],33,0x32), None if row["head"] == "-" else oracle._hex(row["head"],33,0x12))
                             for row in branches.values())
    connection = None
    try:
        connection = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro&immutable=1", uri=True, isolation_level=None, timeout=0)
        connection.execute("PRAGMA synchronous=OFF"); connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA synchronous").fetchone() != (0,) or connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise ValueError("toy immutable SQLite explicit OFF/read-only profile differs")
        if connection.execute("PRAGMA application_id").fetchone() != (1279677264,):
            raise ValueError("toy current SQLite application identity differs")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        source, definition, tables = oracle._schema_source(version)
        actual = "".join(value+"\n" for row in connection.execute(oracle.DEFINITION_SQL) for value in row)
        if actual != definition or [row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")] != tables:
            raise ValueError("toy full authoritative schema/table contract differs")
        meta = connection.execute("SELECT catalog_id,catalog_incarnation,binding_key,identity_format,schema_version,schema_source,schema_definition,next_stage_token FROM history_meta WHERE id=1").fetchall()
        if (len(meta) != 1 or type(meta[0][1]) is not int or not 0 < meta[0][1] <= 2**63-1
                or hashlib.sha256(meta[0][2]).hexdigest() != bound["binding_sha256"]
                or meta[0][3:7] != (1,version,source,definition)
                or type(meta[0][7]) is not int or meta[0][7] <= 0):
            raise ValueError("toy catalog binding/schema metadata differs")
        catalog = oracle._blob(meta[0][0],32).hex()
        if connection.execute("SELECT schema_version FROM store_policy WHERE id=1").fetchall() != [(version,)]:
            raise ValueError("toy persisted policy schema differs")
        if connection.execute("SELECT branch_id,layer_stack_id,name,base_layer_id,head_commit_id FROM branch ORDER BY branch_id").fetchall() != wanted_branches:
            raise ValueError("toy unfiltered Branch set/head/stack/base differs")
        observed = []; batches = 0
        cursor = connection.execute(oracle.CENSUS_SQL)
        while True:
            rows = cursor.fetchmany(127); batches += 1
            if not rows: break
            observed.extend(rows)
        if observed != expected:
            raise ValueError("toy unfiltered global Commit EOF membership/five-tuples differ")
        base = oracle._hex(initial["base_layer"],33,0x32)
        if connection.execute("SELECT layer_stack_id,root_id,parent_layer_id,source_branch_id,source_commit_id FROM layer WHERE layer_id=?",(base,)).fetchall() != [(oracle._hex(initial["stack"],17,0x31),oracle._hex(initial["root"],32),None,None,None)]:
            raise ValueError("toy original genesis Layer/root/stack differs")
        if connection.execute("SELECT layer_stack_id,head_layer_id FROM layer_stack").fetchall() != [(oracle._hex(initial["stack"],17,0x31),base)]:
            raise ValueError("toy exact LayerStack set/head differs")
    finally:
        if connection is not None: connection.close()
        if oracle._sealed_identity(path) != before:
            raise ValueError("toy immutable normalized Store changed")
    return {"status":"PASS","commits":3,"branches":len(wanted_branches),"fetch_batches_including_eof":batches,"catalog_id":catalog,
            "query":oracle.CENSUS_SQL,"source":before,"scope":"post-known-Stop immutable whole global Commit/Branch tables; exact SDK typed tuples and independent manifest/schema binding; no canonical family case"}


def admit_empty(prepared, current):
    shape, provision = prepared["fixture"], prepared["provision"]
    if (prepared.get("recipe") != "empty" or prepared.get("status") != "PASS"
            or type(shape.get("files")) is not int or shape["files"] != 0
            or type(shape.get("logical_bytes")) is not int or shape["logical_bytes"] != 0
            or prepared.get("identity",{}).get("product_tree") != current["product_tree"]
            or provision.get("status") != "PASS" or type(provision.get("construction_workers")) is not int
            or provision["construction_workers"] != 1
            or provision.get("global_profile") != "Disposable/WAL/OFF"
            or provision.get("overlay_profile") != "MEMORY/OFF/EXCLUSIVE"
            or type(prepared["source_uid"]) is not int or not 0 < prepared["source_uid"] <= 2**32-1):
        raise ValueError("fresh current-product sealed empty Disposable input required before clone")


def run(build_folder, prepared_folder, output):
    begun = time.monotonic(); stop = begun + 60
    output = Path(output).resolve()
    if not output.is_relative_to((identity.ROOT / "benchmark-results/fs-bench-pro").resolve()):
        raise ValueError("fresh proof output must be under benchmark-results/fs-bench-pro")
    output.mkdir(parents=True, exist_ok=False)
    row = {"schema":"fs-bench-pro-public-sdk-covering-proof-v1","test_id":TEST_ID,"status":"FAIL","samples":0,
           "identity":"UNAVAILABLE before source admission","build":str(Path(build_folder).resolve()),"prepared":str(Path(prepared_folder).resolve()),
           "inner_wall_stop_seconds":60,"outer_wall_stop_seconds":120,"timers":"diagnostic only; no performance/cache claim",
           "global_profile":"Disposable/WAL/OFF","overlay_profile":"MEMORY/OFF/EXCLUSIVE","construction_workers":1,
           "durable":"NOT_RUN — disabled by owner until explicit reauthorization","history":[],"mounts":[]}
    runtime = None; active = {}
    try:
        current, build = identity.source_identity(), identity.load_build(build_folder)
        prepared = fixtures.load(prepared_folder,"empty")
        admit_empty(prepared,current)
        if not callable(getattr(workspace,"context_send",None)):
            raise ValueError("reviewed one-write context SDK sender required before clone")
        row["identity"] = current
        row["clone"] = fixtures.clone(prepared, output / "clone", build)
        argv = [build["binaries"]["runtime"]["path"],"serve","--socket",build["socket"],"--volume",row["clone"]["volume"],
                "--daemon",build["binaries"]["daemon"]["path"],"--manifest",prepared["provision"]["manifest"],
                "--receipt",str(output / "runtime.events.jsonl"),"--uid",str(prepared["source_uid"]),"--gid",str(prepared["source_gid"]),
                "--observation-scope",secrets.token_hex(32),"--case",TEST_ID]
        runtime = workspace.cell_runner.EventProcess(argv, output, "runtime")
        runtime.event("protocol_ready",stop)
        row["container"] = runtime.container
        if not runtime.container: raise ValueError("actual runtime container acknowledgement missing")
        initial_events = [event["fields"] for event in runtime.rows if event["event"] == "history_initial_root"]
        if len(initial_events) != 1: raise ValueError("exact original sealed empty-root binding required")
        initial = initial_events[0]
        if initial.get("head") != "-" or initial.get("name") != "main": raise ValueError("fresh empty manifest Branch required")
        branches = {"initial":dict(initial)}; all_commits=[]
        def mount(label):
            key = secrets.token_hex(32)
            event = workspace.context_send(runtime,"mount-branch",key,label,deadline=stop)
            if event["fields"].get("key") != key or event["fields"].get("branch_id") != branches[label]["branch_id"] or event["fields"].get("branch_label") != label:
                raise ValueError("fresh Workspace binding differs")
            if key in active: raise ValueError("fresh Workspace key reused")
            active[key]=label;row["mounts"].append(event);return key
        branches["trunk"] = fork(runtime,"trunk","sdk-proof-trunk",None,None,initial,output,stop)
        trunk = mount("trunk")
        command(runtime,trunk,"printf one > tiny.txt",output,"create-one",stop)
        one = commit(runtime,trunk,"-",initial,stop);all_commits.append(one)
        command(runtime,trunk,"printf two > tiny.txt",output,"overwrite-two",stop)
        two = commit(runtime,trunk,one["commit_id"],initial,stop);all_commits.append(two)
        branches["trunk"].update(head=two["commit_id"],root=two["root"])
        branches["child"] = fork(runtime,"child","sdk-proof-child","trunk",one,initial,output,stop)
        child = mount("child")
        command(runtime,child,"cat tiny.txt",output,"child-one",stop,b"one")
        row["history"].append(history_records(runtime,"child",branches["child"]["branch_id"],one["commit_id"],[one],output,stop))
        command(runtime,child,"printf child > tiny.txt",output,"child-change",stop)
        changed = commit(runtime,child,one["commit_id"],initial,stop);all_commits.append(changed)
        branches["child"].update(head=changed["commit_id"],root=changed["root"])
        branches["ancestor"] = fork(runtime,"ancestor","sdk-proof-ancestor","child",one,initial,output,stop)
        ancestor = mount("ancestor")
        command(runtime,ancestor,"cat tiny.txt",output,"ancestor-one",stop,b"one")
        for label,anchor,wanted in (("trunk",two["commit_id"],[two,one]),("child",changed["commit_id"],[changed,one]),("ancestor",one["commit_id"],[one])):
            row["history"].append(history_records(runtime,label,branches[label]["branch_id"],anchor,wanted,output,stop))
        command(runtime,trunk,"cat tiny.txt",output,"trunk-still-two",stop,b"two")
        command(runtime,child,"cat tiny.txt",output,"child-still-child",stop,b"child")
        for key in list(active):
            ended = runtime.send("unmount",key,deadline=stop)
            gone = workspace.readiness(runtime,key,min(5,max(0,stop-time.monotonic())))
            if ended["fields"].get("key") != key or gone[-1]["fields"].get("state") != "Gone":
                raise ValueError("exact explicit unmount and Gone required")
            row.setdefault("terminal_mounts",[]).append({"key":key,"unmount":ended,"cleanup":gone});del active[key]
        runtime.send("stop",deadline=stop);runtime.event("finished",stop)
        if runtime.process.wait(timeout=max(.001,stop-time.monotonic())) != 0: raise ValueError("original runtime return not zero")
        ended = [event for event in runtime.rows if event["event"] == "control_ended"]
        channels = {event["fields"]["channel"] for event in runtime.rows if event["event"] == "control_origin"}
        if {event["fields"].get("channel") for event in ended} != channels or len(ended) != len(channels):
            raise ValueError("every native control channel EndSession/fence required")
        for event in ended: one_exchange(event["fields"])
        stopped = [event for event in runtime.rows if event["event"] == "container_stopped"]
        if len(stopped)!=1 or stopped[0].get("value") != runtime.container: raise ValueError("actual known Stop missing")
        row["custody"]="KNOWN_STOP"
        docker=["docker","--host","unix://"+build["socket"]]
        export=receipts.command([*docker,"cp",runtime.container+":/layerfs-store/global",str(output/"graph-store")],output,"closed-store-export",max(.001,stop-time.monotonic()))
        normalized=oracle.prepare_closed_store(output/"graph-store",output/"census-store/store.sqlite",stop)
        row["closed_store_normalization"] = normalized
        bound_initial = {**initial,"stack_id":initial["stack"],"initial_root":initial["root"]}
        row["global_census"] = closed_census(Path(normalized["path"]),bound_initial,branches,all_commits,prepared["provision"]["manifest"])
        if time.monotonic()>=stop: raise TimeoutError("inner 60-second complete proof wall reached")
        row.update(status="PASS",commits=all_commits,branches=branches,cleanup="Gone",resource_removal_pending=True,
                   resource_disposition="passing owned sample pair retained until sealed test receipt and known outer return; Root removes separately")
    except BaseException as error:
        row.update(original_failure=str(error),original_failure_type=type(error).__name__,retained_mount_keys=list(active),
                   resource_disposition="retain every original failed/uncertain container/volume; no teardown guess/retry")
        if runtime is None: runtime=getattr(error,"event_process",None)
        if runtime is not None:
            row["container"]=runtime.container;row["retained_host_custody"]=runtime.retain(error)
    finally:
        # Stop live work at60; receipt emission remains under the outer120 stop.
        signal.setitimer(signal.ITIMER_REAL,max(.001,begun+120-time.monotonic()))
        if runtime is not None:
            for value in (runtime.selector,runtime.raw,runtime.stderr,getattr(runtime.process,"stdin",None),getattr(runtime.process,"stdout",None)):
                if value is not None:
                    try: value.close()
                    except BaseException as error:
                        row.setdefault("independent_close_failures",[]).append(str(error));row["status"]="FAIL"
        row["complete_wall_ns"]=int((time.monotonic()-begun)*1_000_000_000)
        receipts.write_new(output/"proof.json",row);receipts.manifest(output)
    return row


class SourceChecks(unittest.TestCase):
    def test_dirty_geometry_stale_product_and_disabled_profile_are_refused_before_resources(self):
        import copy
        prepared={"recipe":"empty","status":"PASS","fixture":{"files":0,"logical_bytes":0},
                  "identity":{"product_tree":"current"},"source_uid":501,"provision":{"status":"PASS","construction_workers":1,
                  "global_profile":"Disposable/WAL/OFF","overlay_profile":"MEMORY/OFF/EXCLUSIVE"}}
        admit_empty(prepared,{"product_tree":"current"})
        for section,key,value in (("fixture","files",1),("fixture","logical_bytes",1),
                                  ("identity","product_tree","old"),("provision","global_profile","Durable/WAL/FULL"),
                                  ("provision","status","UNKNOWN"),("provision","construction_workers",2)):
            wrong=copy.deepcopy(prepared);wrong[section][key]=value
            with self.assertRaises(ValueError):admit_empty(wrong,{"product_tree":"current"})

    def test_full_typed_history_record_and_eof_cannot_be_substituted(self):
        record={"commit_id":"12"+"01"*32,"stack":"31"+"02"*16,"root":"03"*32,"parent":"-","base_layer":"32"+"04"*32}
        branch="11"+"05"*16
        rows=[{**record,"label":"child","branch_id":branch}]
        final={"label":"child","branch_id":branch,"records":1,"cursor_path":"-","cursor_bytes":0,
               "control_send_records_before":4,"control_send_records_after":5,"control_receive_records_before":4,"control_receive_records_after":5}
        verify_history_page(rows,final,"child",branch,[record])
        for altered in ({**rows[0],"root":"99"*32},{**rows[0],"parent":"12"+"06"*32}):
            with self.assertRaises(ValueError):verify_history_page([altered],final,"child",branch,[record])
        with self.assertRaises(ValueError):verify_history_page(rows,{**final,"cursor_path":"partial"},"child",branch,[record])
        with self.assertRaises(ValueError):verify_history_page(rows,{**final,"cursor_sha256":"unexpected"},"child",branch,[record])
        with self.assertRaises(ValueError):verify_history_page(rows,{**final,"cursor_bytes":False},"child",branch,[record])
        with self.assertRaises(ValueError):verify_history_page(rows,{**final,"control_send_records_after":6},"child",branch,[record])

    def test_unknown_original_fork_write_is_one_attempt_without_resend_or_teardown(self):
        initial={"root":"01"*32,"stack":"31"+"02"*16,"base_layer":"32"+"03"*32}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(workspace,"context_send",create=True,
                              side_effect=RuntimeError("short original context write; outcome uncertain; no resend")) as send:
                with self.assertRaisesRegex(RuntimeError,"outcome uncertain"):
                    fork(object(),"trunk","sdk-proof-trunk",None,None,initial,Path(temporary),time.monotonic()+5)
                self.assertEqual(send.call_count,1)
                args,kwargs=send.call_args
                self.assertEqual(args[1:3],("fork","trunk"))
                body=Path(args[3]).read_text().splitlines()
                self.assertEqual(len(body),1)
                columns=body[0].split("\t")
                self.assertEqual((columns[0],columns[2]),("layer","sdk-proof-trunk"))
                oracle._hex(columns[1],17,0x11)

    def test_closed_toy_census_includes_extra_rows_and_branches_instead_of_ancestry_filter(self):
        # Synthetic SQL exercises only this independent census controller.
        # Live public SDK qualification is deliberately not executed here.
        import importlib.util
        spec=importlib.util.spec_from_file_location("p1_synthetic_census",Path(__file__).with_name("test_census.py"))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            fixture=module.StoreFixture(Path(temporary))
            ident=module.ident
            fixture.mutate('UPDATE "commit" SET parent_commit_id=? WHERE commit_id=?',(ident(0x12,33,1),ident(0x12,33,3)))
            fixture.expected[2]["parent_commit_id"]=fixture.expected[0]["commit_id"]
            fixture.mutate("UPDATE branch SET head_commit_id=NULL WHERE branch_id=?",(fixture.branch,))
            initial={"branch_id":fixture.branch.hex(),"stack_id":fixture.stack.hex(),"stack":fixture.stack.hex(),
                     "initial_root":fixture.initial.hex(),"root":fixture.initial.hex(),"base_layer":fixture.base.hex(),"name":"main","head":"-"}
            branches={"initial":initial}
            for index,name,head in ((2,"trunk",2),(3,"child",3),(4,"ancestor",1)):
                fixture.mutate("INSERT INTO branch VALUES(?,?,?,?,?)",(ident(0x11,17,index),fixture.stack,name,fixture.base,ident(0x12,33,head)))
                branches[name]={**initial,"branch_id":ident(0x11,17,index).hex(),"name":name,"head":ident(0x12,33,head).hex()}
            acknowledged=[dict(zip(TUPLE_KEYS,[row["commit_id"],row["layer_stack_id"],row["root_id"],row["parent_commit_id"] or "-",row["base_layer_id"]])) for row in fixture.expected]
            result=closed_census(fixture.path,initial,branches,acknowledged,fixture.manifest)
            self.assertEqual((result["commits"],result["branches"],result["fetch_batches_including_eof"]),(3,4,2))
            fixture.mutate('INSERT INTO "commit" VALUES(?,?,?,?,?)',(ident(0x12,33,99),fixture.stack,fixture.initial,None,fixture.base))
            with self.assertRaisesRegex(ValueError,"global Commit EOF"):
                closed_census(fixture.path,initial,branches,acknowledged,fixture.manifest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",required=True);parser.add_argument("--prepared",required=True);parser.add_argument("--out",required=True)
    args=parser.parse_args()
    def ceiling(signum,frame): raise TimeoutError("covering proof wall reached: live/proof60s; outer receipt120s")
    signal.signal(signal.SIGALRM,ceiling);signal.setitimer(signal.ITIMER_REAL,60)
    os.environ["LAYERFS_CONSTRUCTION_WORKERS"]="1"
    try: row=run(args.build,args.prepared,args.out)
    finally: signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps({"status":row["status"],"evidence":str(Path(args.out).resolve()),"samples":0},indent=2))
    return 0 if row["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
