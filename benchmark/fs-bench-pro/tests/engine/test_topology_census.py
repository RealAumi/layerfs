"""Synthetic current-schema topology guards; no public/runtime qualification."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("old_census_fixture", Path(__file__).with_name("test_census.py"))
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
oracle = fixture_module.oracle
ident = fixture_module.ident


class GraphFixture(fixture_module.StoreFixture):
    def __init__(self, home, version=7):
        super().__init__(home, version)
        self.mutate('UPDATE "commit" SET parent_commit_id=? WHERE commit_id=?',
                    (ident(0x12,33,1), ident(0x12,33,3)))
        self.expected[2]["parent_commit_id"] = self.expected[0]["commit_id"]
        self.expected.append(dict(self.expected[2]))
        self.mutate("UPDATE branch SET head_commit_id=NULL WHERE branch_id=?", (self.branch,))
        self.branch_records = [("initial", self.branch, "main", None, self.initial, None, self.initial, "-", 0),
                               ("trunk", ident(0x11,17,2), "trunk", None, self.initial,
                                ident(0x12,33,2), bytes([17])*32, "-", 0),
                               ("a", ident(0x11,17,3), "a", ident(0x12,33,1), bytes([16])*32,
                                ident(0x12,33,3), bytes([18])*32, "trunk", 1),
                               ("b", ident(0x11,17,4), "b", ident(0x12,33,1), bytes([16])*32,
                                ident(0x12,33,3), bytes([18])*32, "trunk", 1)]
        for _, branch, name, _, _, head, _, _, _ in self.branch_records[1:]:
            self.mutate("INSERT INTO branch VALUES(?,?,?,?,?)", (branch,self.stack,name,self.base,head))
        self.provider.update(topology_case="synthetic-convergent", topology_acknowledgements=4,
                             topology_distinct_commits=3, topology_branches=4,
                             final_head_commit_id="-", final_head_root=self.initial.hex())
        self.write_transcript()

    def write_transcript(self):
        rows = ["topology-v1\tsynthetic-convergent"]
        for role, branch, name, parent, initial, head, final, source, local in self.branch_records:
            rows.append("\t".join(["branch",role,branch.hex(),name,self.stack.hex(),self.base.hex(),
                                   parent.hex() if parent else "-",initial.hex(),head.hex() if head else "-",
                                   final.hex(),source,str(local)]))
        for (role,local), values in zip([( "trunk",1),("trunk",2),("a",1),("b",1)],self.expected):
            rows.append("\t".join(["commit",role,str(local),values["commit_id"],values["layer_stack_id"],
                                   values["root_id"],values["parent_commit_id"] or "-",values["base_layer_id"],"-","-"]))
        self.transcript.write_text("\n".join(rows)+"\n")
        self.provider["acknowledged_transcript_sha256"] = oracle.file_sha(self.transcript)
        self.custody["transcript_sha256"] = oracle.file_sha(self.transcript)

    def run(self):
        return oracle.graph_commit_census(self.path,self.expected,self.provider,self.custody)


class TopologyCensus(unittest.TestCase):
    def test_identical_acknowledgements_collapse_only_full_tuples_and_keep_unused_initial_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            for version in (7, 8, 9, 13, 14, 15):
                home=Path(temporary)/str(version); home.mkdir()
                fixture=GraphFixture(home,version)
                before=oracle.file_sha(fixture.path)
                proof=fixture.run()
                self.assertEqual((proof["commit_count"],proof["acknowledged_commit_count"],
                                  proof["retained_root_references"],proof["identical_duplicate_acknowledgements"],
                                  proof["branch_count"]), (3,4,5,1,4))
                self.assertEqual(proof["query"],oracle.CENSUS_SQL)
                self.assertEqual(proof["fetch_batches_including_eof"],2)
                self.assertEqual(oracle.file_sha(fixture.path),before)

    def test_same_id_conflicting_tuple_missing_ack_and_wrong_fork_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mutation in ("conflict","missing","fork"):
                home=Path(temporary)/mutation;home.mkdir();fixture=GraphFixture(home)
                if mutation=="conflict":
                    fixture.expected[-1]["root_id"] = "ee"*32
                    fixture.write_transcript()
                    expected="conflicting full tuple"
                elif mutation=="missing":
                    fixture.expected.pop();fixture.write_transcript()
                    expected="final Branch head/root"
                else:
                    record=list(fixture.branch_records[-1]);record[-1]=2
                    fixture.branch_records[-1]=tuple(record);fixture.write_transcript()
                    expected="historical fork parent/root"
                with self.assertRaisesRegex(ValueError,expected):fixture.run()

    def test_global_extra_commit_branch_and_equal_count_head_substitution_are_never_filtered(self):
        changes=[('INSERT INTO "commit" VALUES(?,?,?,?,?)',
                  (ident(0x12,33,9),ident(0x31,17),bytes([19])*32,None,ident(0x32,33)),"global Commit membership"),
                 ('INSERT INTO branch VALUES(?,?,?,?,?)',
                  (ident(0x11,17,9),ident(0x31,17),"extra",ident(0x32,33),None),"global Branch membership"),
                 ('UPDATE branch SET head_commit_id=? WHERE name=\'a\'',
                  (ident(0x12,33,2),),"global Branch membership")]
        with tempfile.TemporaryDirectory() as temporary:
            for index,(sql,args,error) in enumerate(changes):
                home=Path(temporary)/str(index);home.mkdir();fixture=GraphFixture(home)
                fixture.mutate(sql,args)
                with self.assertRaisesRegex(ValueError,error):fixture.run()

    def test_original_custody_and_provider_bindings_remain_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mutation in ("profile","manifest","stop","transcript","counts"):
                home=Path(temporary)/mutation;home.mkdir();fixture=GraphFixture(home)
                if mutation=="profile":fixture.provider["provider_validation"]="unknown"
                elif mutation=="manifest":fixture.custody["prepared_manifest_sha256"]="0"*64
                elif mutation=="stop":fixture.custody["custody"]="UNKNOWN"
                elif mutation=="transcript":fixture.provider["acknowledged_transcript_sha256"]="0"*64
                else:fixture.provider["topology_acknowledgements"]=True
                with self.assertRaises(ValueError):fixture.run()


class AccessPasses(unittest.TestCase):
    def source(self, alias=True):
        import hashlib
        payload=b"independent exact bytes"
        paths=["tiny-moved/t4.dat", "tiny-moved/a4.dat"] if alias else ["tiny-moved/t4.dat"]
        case={"id":"v016-access-inode-before-v1" if alias else "v016-access-inode-after-v1",
              "historical_access":{"reads":[{"path":path,"bytes":len(payload)} for path in paths],
                  "absent":[] if alias else ["tiny-moved/a4.dat"], "read_plan":"InodePair" if alias else "InodeTarget",
                  "reader_profile":"fresh-session-application-cold;uncontrolled-os-cache;no-pre-read"}}
        events=[{"event":"access_expected_read","fields":{"path":path,"bytes":len(payload),
                 "payload_hex":payload.hex(),"sha256":hashlib.sha256(payload).hexdigest()}} for path in paths]
        if not alias:events.append({"event":"access_expected_absent","fields":{"path":"tiny-moved/a4.dat"}})
        def receipt(phase):
            rows=["access_case="+case["id"],"access_phase="+phase,
                  "access_reader_profile="+case["historical_access"]["reader_profile"],"access_pre_read=0","access_commits=0"]
            for event in events:
                value=event["fields"]
                if event["event"]=="access_expected_absent":rows.append("access_absent="+value["path"]);continue
                rows.extend(["access_target="+value["path"],"access_declared_bytes="+str(value["bytes"]),
                             "access_bytes="+str(value["bytes"]),"access_sha256="+value["sha256"],
                             "access_ino=42","access_dev=9","access_nlink="+str(2 if alias else 1),
                             "access_payload_hex="+value["payload_hex"]])
            return "\n".join(rows+["access_status=pass"])+"\n"
        return case,events,receipt("reader"),receipt("verifier")

    def test_both_original_passes_require_independent_bytes_aliases_and_absence(self):
        for alias in (True,False):
            case,events,reader,verifier=self.source(alias)
            proof=oracle.verify_access_passes(case,reader,verifier,events)
            self.assertEqual(proof["status"],"PASS")
            self.assertEqual(proof["read_passes"],2)
            self.assertEqual(proof["commits_created"],0)
            self.assertEqual(proof["full_read_bytes"],2*sum(event["fields"].get("bytes",0) for event in events))

    def test_self_consistent_corruption_inode_mismatch_nlink_and_profile_fail(self):
        import hashlib
        case,events,reader,verifier=self.source()
        changed=b"self consistent wrong!"
        substitutions=[(events[0]["fields"]["payload_hex"],changed.hex()),
                       (events[0]["fields"]["sha256"],hashlib.sha256(changed).hexdigest())]
        corrupt=verifier
        for old,new in substitutions:corrupt=corrupt.replace(old,new)
        for bad in (corrupt,verifier.replace("access_ino=42","access_ino=43"),
                    verifier.replace("access_nlink=2","access_nlink=1"),
                    verifier.replace("uncontrolled-os-cache","warm")):
            with self.assertRaises(ValueError):oracle.verify_access_passes(case,reader,bad,events)
        case,events,reader,verifier=self.source(False)
        with self.assertRaisesRegex(ValueError,"ENOENT"):
            oracle.verify_access_passes(case,reader,verifier.replace("access_absent=tiny-moved/a4.dat\n",""),events)


if __name__ == "__main__":
    unittest.main()
