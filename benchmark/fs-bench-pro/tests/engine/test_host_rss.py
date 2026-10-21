"""Current RSS observations never substitute a lifetime peak or missing sample."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from engine import receipts


class HostRss(unittest.TestCase):
    def child(self):
        child = mock.Mock(pid=12345,returncode=0)
        child.poll.side_effect = [None,None,0]
        return child

    def test_current_ps_sample_is_recorded_in_bytes_at_actual_elapsed_boundary(self):
        child = self.child()
        ps = subprocess.CompletedProcess([],0,"1024\n","")
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(receipts.subprocess,"Popen",return_value=child), \
             mock.patch.object(receipts.subprocess,"run",return_value=ps) as sampled:
            row = receipts.command(["/test/child"],temporary,"rss",1,host_rss_limit_bytes=2*1024**3)
            self.assertEqual(row["status"],"PASS")
            self.assertEqual(row["host_rss"]["samples"][0]["rss_bytes"],1048576)
            self.assertGreater(row["host_rss"]["samples"][0]["elapsed_ns"],0)
            self.assertIn("no descendant or lifetime-peak substitution",row["host_rss"]["scope"])
            self.assertEqual(sampled.call_args.args[0],["/bin/ps","-o","rss=","-p","12345"])

    def test_real_limit_violation_keeps_failed_guard_and_exact_host_custody(self):
        child = self.child()
        ps = subprocess.CompletedProcess([],0,"2097153\n","")
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(receipts.subprocess,"Popen",return_value=child), \
             mock.patch.object(receipts.subprocess,"run",return_value=ps), \
             mock.patch.object(receipts.os,"killpg") as fenced:
            with self.assertRaisesRegex(RuntimeError,"RSS exceeds"):
                receipts.command(["/test/child"],temporary,"rss",1,host_rss_limit_bytes=2*1024**3)
            row = __import__("json").loads((Path(temporary)/"rss.completion.json").read_text())
            self.assertEqual(row["status"],"FAIL")
            self.assertEqual(row["host_rss"]["samples"][0]["rss_bytes"],2097153*1024)
            self.assertIn("NOT_ESTABLISHED",row["remote_cancellation"])
            fenced.assert_called_once()

    def test_missing_live_sample_fails_without_inventing_a_zero_peak(self):
        child = mock.Mock(pid=12345,returncode=0)
        child.poll.side_effect = [None,None,None]
        ps = subprocess.CompletedProcess([],1,"","")
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(receipts.subprocess,"Popen",return_value=child), \
             mock.patch.object(receipts.subprocess,"run",return_value=ps), \
             mock.patch.object(receipts.os,"killpg"):
            with self.assertRaisesRegex(ValueError,"RSS observation missing"):
                receipts.command(["/test/child"],temporary,"rss",1,host_rss_limit_bytes=2*1024**3)


if __name__=="__main__": unittest.main()
