"""Driver return acknowledgement precedes H8 administrative disposition."""
from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
spec=importlib.util.spec_from_file_location("history_bench",BENCH/"bench.py")
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
from engine import fixtures,identity,project,receipts,workspace


class HistoryDriver(unittest.TestCase):
    def test_failed_parity_returns_nonzero_with_retained_case_summary(self):
        class Failure(ValueError):
            result={'family':'dedup_branch_history','status':'FAIL','cases':[{'case':'missing','status':'FAIL'}]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);error=Failure('prepared input absent');error.output=root/'parity'
            output=io.StringIO()
            with patch.object(project,'ParityFailure',Failure,create=True), \
                    patch.object(project,'parity_workspace',side_effect=error),redirect_stdout(output):
                returned=bench.main(['parity','dedup_branch_history','--prepared',str(root/'prepared'),
                                     '--out',str(error.output)])
            self.assertEqual(returned,1)
            result=json.loads(output.getvalue())
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['cases'],1)
            self.assertEqual(result['evidence'],str(error.output))

    def drive(self,root,case,result,ack_failure=False):
        here=root/"bench";family=here/"families/dedup_branch_history";family.mkdir(parents=True)
        (family/"family.json").write_text(json.dumps({"family":"dedup_branch_history","cases":[case]}))
        output=root/"benchmark-results/fs-bench-pro/run";calls=[]
        def attempted(*args):calls.append("attempt");return result
        def acknowledged(*args):
            calls.append("ack")
            if ack_failure:raise OSError("outer acknowledgement unavailable")
        def disposed(*args):calls.append("dispose")
        with ExitStack() as stack:
            for module,name,value in ((bench,"HERE",here),(identity,"ROOT",root),
                                      (fixtures,"WORKSPACE_FAMILIES",("dedup_branch_history",))):
                stack.enter_context(patch.object(module,name,value))
            stack.enter_context(patch.object(identity,"source_identity",return_value={"source_commit":"a"*40,"source_tree":"b"*40,"product_tree":"c"*40}))
            stack.enter_context(patch.object(workspace,"one_family_case",side_effect=attempted))
            stack.enter_context(patch.object(receipts,"acknowledge_guarded",side_effect=acknowledged))
            stack.enter_context(patch.object(workspace,"dispose_family_resources",side_effect=disposed))
            with redirect_stdout(io.StringIO()):
                if ack_failure:
                    with self.assertRaisesRegex(OSError,"acknowledgement"):
                        bench.main(["run","dedup_branch_history","--case",case["id"],"--build",str(root/"build"),
                                    "--prepared",str(root/"prepared"),"--out",str(output)])
                    returned=None
                else:
                    returned=bench.main(["run","dedup_branch_history","--case",case["id"],"--build",str(root/"build"),
                                        "--prepared",str(root/"prepared"),"--out",str(output)])
        return returned,calls

    def test_non_git_guard_is_acknowledged_before_administrative_disposition(self):
        case={"id":"case","v016_case":"case","status":"ported","fixture":{"recipe":"case"}}
        result={"case":"case","status":"INELIGIBLE","publication_guard":{"scope":receipts.HISTORY_PUBLICATION_SCOPE}}
        with tempfile.TemporaryDirectory() as temporary:
            returned,calls=self.drive(Path(temporary).resolve(),case,result)
            self.assertEqual(returned,1)
            self.assertEqual(calls,["attempt","ack","dispose"])

    def test_missing_outer_ack_never_reaches_disposal(self):
        case={"id":"case","v016_case":"case","status":"ported","fixture":{"recipe":"case"}}
        result={"case":"case","status":"PASS","publication_guard":{"scope":receipts.HISTORY_PUBLICATION_SCOPE}}
        with tempfile.TemporaryDirectory() as temporary:
            _,calls=self.drive(Path(temporary).resolve(),case,result,ack_failure=True)
            self.assertEqual(calls,["attempt","ack"])

    def test_verification_only_driver_uses_real_proof_and_never_performance_eligibility(self):
        case={"id":"case","v016_case":"case","status":"ported","fixture":{"recipe":"case"},"proof_only":True}
        result={"case":"case","status":"INELIGIBLE","functional_status":"PASS","proof_status":"PASS",
                "proof_only":True,"performance_mode":"verification-only","sample_count":0,"verification_attempt_count":1,
                "publication_guard":{"scope":receipts.HISTORY_PUBLICATION_SCOPE}}
        with tempfile.TemporaryDirectory() as temporary:
            returned,calls=self.drive(Path(temporary).resolve(),case,result)
            self.assertEqual(returned,0)
            self.assertEqual(calls,["attempt","ack","dispose"])
        with tempfile.TemporaryDirectory() as temporary:
            returned,_=self.drive(Path(temporary).resolve(),case,{**result,"proof_status":"FAIL","status":"FAIL"})
            self.assertEqual(returned,1)

    def test_verification_only_cannot_claim_a_performance_sample(self):
        case={"id":"case","v016_case":"case","status":"ported","fixture":{"recipe":"case"},"proof_only":True}
        result={"case":"case","status":"PASS","proof_only":True,"performance_mode":"verification-only","sample_count":1,"verification_attempt_count":1}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,"no performance sample"):
                self.drive(Path(temporary).resolve(),case,result)


if __name__=="__main__":unittest.main()
