"""Synthetic schema/FK/BLOB guards on isolated current-schema WAL/OFF files.

IDs, roots and provider observation fields here are synthetic. Canonical public
Store/Commit/provider qualification is a separate external integration test.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("census_oracle", BENCH/"engine/oracle.py")
oracle = importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)


def ident(tag, length, ordinal=1):
    return bytes([tag])+ordinal.to_bytes(length-1,"big")


class StoreFixture:
    def __init__(self, home, version=7, commits=3):
        home=home.resolve()
        self.path=home/"store.sqlite"; self.manifest=home/"installed.manifest"; self.transcript=home/"ack.tsv"
        self.runtime=home/"runtime.events.jsonl"; self.export=home/"export.completion.json"
        self.stack=ident(0x31,17); self.branch=ident(0x11,17); self.base=ident(0x32,33)
        self.initial=bytes([3])*32; self.binding=b"private-test-catalog-binding"; self.catalog=bytes([8])*32
        self.container="a"*64; self.volume="layerfs-fsb-sample-0123456789abcdef"
        self.expected=[]
        source,definition,_=oracle._schema_source(version)
        database=sqlite3.connect(self.path,isolation_level=None,timeout=0)
        database.execute("PRAGMA journal_mode=WAL"); database.execute("PRAGMA synchronous=OFF")
        database.executescript(source)
        database.execute("PRAGMA application_id=1279677264"); database.execute(f"PRAGMA user_version={version}")
        database.execute("INSERT INTO store_policy(id,schema_version,format_profile,small_file_threshold_bytes,whole_file_delta_max_depth,chunk_delta_max_depth,metadata_delta_max_depth) VALUES(1,?,1,131072,1,1,1)",(version,))
        database.execute("INSERT INTO history_meta VALUES(1,?,1,?,1,?,?,?,1)",(self.catalog,self.binding,version,source,definition))
        database.execute("INSERT INTO layer_stack VALUES(?,?,?,?,?)",(self.stack,"project",bytes([4])*32,bytes([5])*32,self.base))
        database.execute("INSERT INTO layer VALUES(?,?,?,?,?,?)",(self.base,self.stack,None,self.initial,None,None))
        previous=None
        for index in range(commits):
            commit=ident(0x12,33,index+1); root=bytes([16+index])*32
            values=(commit,self.stack,root,previous,self.base)
            database.execute('INSERT INTO "commit" VALUES(?,?,?,?,?)',values)
            self.expected.append(dict(zip(oracle.CENSUS_COLUMNS,[v.hex() if v is not None else None for v in values])))
            previous=commit
        database.execute("INSERT INTO branch VALUES(?,?,?,?,?)",(self.branch,self.stack,"main",self.base,previous))
        database.execute("PRAGMA foreign_keys=ON")
        assert not list(database.execute("PRAGMA foreign_key_check"))
        database.close()
        def blob(value):return len(value).to_bytes(2,"big")+value
        self.manifest.write_bytes(b"LFSI\x01\x01\x02"+blob(b"/layerfs-store/global/store.sqlite")+blob(self.binding)+bytes([6])*32+self.stack+self.branch+self.initial+self.path.stat().st_size.to_bytes(8,"big")+blob(b"3.53.2")+blob(b"3.53.2"))
        rows=[f"0\t-\t-\t{self.initial.hex()}\tinitial.tsv"]
        rows += [f"{i}\t{r['commit_id']}\t{r['parent_commit_id'] or '-'}\t{r['root_id']}\t-" for i,r in enumerate(self.expected,1)]
        self.transcript.write_text("\n".join(rows)+"\n")
        events=[{"event":"sandbox_create_attempt","sequence":1,"value":"volume="+self.volume+" image=pinned"},
                {"event":"daemon_setup","sequence":2,"fields":{"container":self.container}},
                {"event":"container_stopped","sequence":3,"value":self.container},
                {"event":"finished","sequence":4}]
        self.runtime.write_text("".join(json.dumps(row)+"\n" for row in events))
        self.export.write_text(json.dumps({"status":"PASS","exit_code":0,"attempts":1,
            "argv":["docker","--host","unix:///private-test.sock","cp",self.container+":/layerfs-store/global",str(home)]}))
        self.provider={"provider_validation":"current-public-schema-source-binding-validated","catalog_id":self.catalog.hex(),
            "catalog_incarnation":1,"binding_sha256":hashlib.sha256(self.binding).hexdigest(),"stack_id":self.stack.hex(),
            "branch_id":self.branch.hex(),"base_layer_id":self.base.hex(),"initial_root":self.initial.hex(),
            "final_head_commit_id":previous.hex(),"final_head_root":self.expected[-1]["root_id"],
            "acknowledged_transcript_sha256":oracle.file_sha(self.transcript),"provider_store_after_size":self.path.stat().st_size,
            "provider_store_unchanged":1}
        self.custody={"custody":"KNOWN_STOP","container":self.container,"volume":self.volume,
            "remote_source":"/layerfs-store/global/store.sqlite","local_source":str(self.path),
            "prepared_manifest":str(self.manifest),"prepared_manifest_sha256":oracle.file_sha(self.manifest),
            "transcript":str(self.transcript),"transcript_sha256":oracle.file_sha(self.transcript),
            "runtime_events":str(self.runtime),"runtime_events_sha256":oracle.file_sha(self.runtime),
            "export_completion":str(self.export),"export_completion_sha256":oracle.file_sha(self.export)}
        self.rebind()

    def rebind(self):
        digest=oracle.file_sha(self.path); size=self.path.stat().st_size
        self.provider.update(provider_store_sha256=digest,provider_store_size=size,
                             provider_store_after_sha256=digest,provider_store_after_size=size)
        self.custody.update(source_sha256=digest,source_size=size)

    def mutate(self, sql, parameters=(), corrupt=False):
        database=sqlite3.connect(self.path,isolation_level=None,timeout=0)
        try:
            database.execute("PRAGMA journal_mode=WAL");database.execute("PRAGMA synchronous=OFF")
            if corrupt:database.execute("PRAGMA ignore_check_constraints=ON")
            database.execute(sql,parameters)
        finally:
            database.close()
        self.rebind()

    def run(self):return oracle.commit_census(self.path,self.expected,self.provider,self.custody)


class CommitCensus(unittest.TestCase):
    def test_all_six_current_schemas_and_streaming_eof_preserve_source(self):
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            for version in (7, 8, 9, 13, 14, 15):
                home=Path(temporary)/str(version);home.mkdir()
                fixture=StoreFixture(home,version,commits=130 if version==9 else 3)
                before=oracle.file_sha(fixture.path)
                result=fixture.run()
                self.assertEqual(result["status"],"PASS");self.assertEqual(result["schema_version"],version)
                self.assertEqual(result["commit_count"],len(fixture.expected))
                self.assertEqual(result["fetch_batches_including_eof"],3 if version==9 else 2)
                self.assertEqual(oracle.file_sha(fixture.path),before)
                self.assertEqual(result["query"],oracle.CENSUS_SQL)
                self.assertNotIn(fixture.binding.decode(),json.dumps(result))
                self.assertFalse(any(Path(str(fixture.path)+s).exists() for s in ("-wal","-shm","-journal")))

    def test_extra_unreachable_synthetic_row_is_not_hidden_by_ancestry(self):
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            fixture=StoreFixture(Path(temporary))
            # Synthetic tagged/FK-bound SQL row outside the expected ancestry.
            # This is not a canonical public Commit or authenticated root.
            fixture.mutate('INSERT INTO "commit" VALUES(?,?,?,?,?)',
                (ident(0x12,33,999),fixture.stack,bytes.fromhex(fixture.expected[0]["root_id"]),None,fixture.base))
            with oracle.closing(sqlite3.connect(fixture.path)) as check:
                self.assertEqual(list(check.execute("PRAGMA foreign_key_check")),[])
            with self.assertRaisesRegex(ValueError,"global Commit membership"):
                fixture.run()

    def test_equal_count_substitution_missing_and_wrong_tuple_fail(self):
        changes=[('UPDATE "commit" SET commit_id=? WHERE commit_id=?',(ident(0x12,33,77),ident(0x12,33,2))),
                 ('DELETE FROM "commit" WHERE commit_id=?',(ident(0x12,33,2),)),
                 ('UPDATE "commit" SET root_id=? WHERE commit_id=?',(bytes([99])*32,ident(0x12,33,2)))]
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            for index,(sql,args) in enumerate(changes):
                home=Path(temporary)/str(index);home.mkdir();fixture=StoreFixture(home)
                fixture.mutate(sql,args)
                with self.assertRaisesRegex(ValueError,"global Commit membership"):
                    fixture.run()

    def test_raw_blob_tag_type_length_and_nullable_parent_guards(self):
        changes=[('UPDATE "commit" SET root_id=? WHERE commit_id=?',("x"*32,ident(0x12,33,2))),
                 ('UPDATE "commit" SET commit_id=? WHERE commit_id=?',(ident(0x13,33,2),ident(0x12,33,2))),
                 ('UPDATE "commit" SET root_id=? WHERE commit_id=?',(bytes(31),ident(0x12,33,2))),
                 ('UPDATE "commit" SET parent_commit_id=NULL WHERE commit_id=?',(ident(0x12,33,2),))]
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            for index,(sql,args) in enumerate(changes):
                home=Path(temporary)/str(index);home.mkdir();fixture=StoreFixture(home)
                if index==0:
                    # STRICT blocks TEXT even when CHECK constraints are fault
                    # injected off; prove the raw guard directly as well.
                    with self.assertRaises(ValueError):oracle._blob("x"*32,32)
                    with self.assertRaises(ValueError):oracle._blob(None,32)
                    with self.assertRaises(sqlite3.IntegrityError):fixture.mutate(sql,args,True)
                    continue
                fixture.mutate(sql,args,True)
                with self.assertRaises(ValueError):fixture.run()

    def test_schema_source_definition_app_catalog_binding_and_provider_are_mandatory(self):
        mutations=[("PRAGMA application_id=1",()),("PRAGMA user_version=13",()),("PRAGMA user_version=6",()),
                   ("PRAGMA user_version=1",()),("PRAGMA user_version=8",()),("DROP TABLE inode_value",()),
                   ("CREATE TABLE metadata_value_group(first_ordinal INTEGER PRIMARY KEY,value_count INTEGER)",()),
                   ("UPDATE history_meta SET schema_source='forged'",()),
                   ("UPDATE history_meta SET schema_definition='forged'",()),
                   ("UPDATE history_meta SET binding_key=?",(b"different",)),
                   ("UPDATE history_meta SET catalog_id=?",(bytes([9])*32,)),
                   ("CREATE TABLE extra_table(value TEXT)",())]
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            for index,(sql,args) in enumerate(mutations):
                home=Path(temporary)/str(index);home.mkdir();fixture=StoreFixture(home)
                fixture.mutate(sql,args)
                with self.assertRaises(ValueError):fixture.run()
            home=Path(temporary)/"provider";home.mkdir();fixture=StoreFixture(home)
            fixture.provider.pop("provider_validation")
            with self.assertRaisesRegex(ValueError,"mandatory public provider"):
                fixture.run()

    def test_provider_writable_copy_change_is_observed_without_touching_census_export(self):
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            fixture=StoreFixture(Path(temporary))
            original=oracle.file_sha(fixture.path)
            fixture.provider.update(provider_store_after_sha256="f"*64,
                                    provider_store_after_size=fixture.path.stat().st_size+4096,
                                    provider_store_unchanged=0)
            proof=fixture.run()
            self.assertEqual(proof["public_provider"]["provider_store_unchanged"],0)
            self.assertEqual(oracle.file_sha(fixture.path),original)
            fixture.provider["provider_store_unchanged"]=1
            with self.assertRaisesRegex(ValueError,"after-seal"):
                fixture.run()

    def test_exact_known_stop_export_manifest_transcript_and_sidecars(self):
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            fixture=StoreFixture(Path(temporary))
            for suffix in ("-wal","-shm","-journal"):
                side=Path(str(fixture.path)+suffix);side.touch()
                with self.assertRaisesRegex(ValueError,"sidecar"):fixture.run()
                side.unlink()
            for key,value in (("custody","UNKNOWN"),("container","b"*64),("volume","layerfs-fsb-sample-other"),
                              ("source_sha256","0"*64),("prepared_manifest_sha256","0"*64),("transcript_sha256","0"*64)):
                original=fixture.custody[key];fixture.custody[key]=value
                with self.assertRaises(ValueError):fixture.run()
                fixture.custody[key]=original
            fixture.expected[0]["parent_commit_id"]=fixture.expected[-1]["commit_id"]
            with self.assertRaisesRegex(ValueError,"first-parent"):fixture.run()

    def test_changed_source_during_read_only_query_cannot_pass(self):
        with tempfile.TemporaryDirectory(prefix="fsb-census-test-") as temporary:
            fixture=StoreFixture(Path(temporary))
            original=oracle._schema_source
            def changed(version):
                result=original(version)
                with fixture.path.open("ab") as output:output.write(b"changed after entry hash")
                return result
            with patch.object(oracle,"_schema_source",side_effect=changed):
                with self.assertRaisesRegex(ValueError,"SHA/size changed"):
                    fixture.run()


if __name__=="__main__":unittest.main()
