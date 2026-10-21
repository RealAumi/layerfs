"""Tier selection is one case, append-only, bounded and sample-resource scoped."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location("tier_driver", BENCH / "tier.py")
tier = importlib.util.module_from_spec(spec); spec.loader.exec_module(tier)


class TierDriver(unittest.TestCase):
    def test_named_outer_limits_are_exact_and_other_cases_keep_two_minutes(self):
        self.assertEqual(len(tier.EXTENDED_RUNS), 6)
        self.assertEqual(len(tier.EXTENDED_PREPARATIONS), 2)
        for case in tier.EXTENDED_RUNS:
            self.assertEqual(tier.policy("run", case), 300)
        for case in ["git-tool-1-compact-v2", "local-snapshot-create-25000-onebyte-v1", "dedup-history-hotset-100"]:
            self.assertEqual(tier.policy("run", case), 118)
            self.assertEqual(tier.policy("prepare", case), 118)

    def test_next_requires_closed_preparation_without_starting_a_sample(self):
        case = tier.bench.catalogue("everyday")[0]
        with tempfile.TemporaryDirectory() as temporary, patch.object(tier, "invoke") as invoked:
            result = tier.ensure_prepared(case, Path(temporary) / "missing", {}, Path("sealed"),
                                           Path(temporary), False)
            self.assertIsNone(result); invoked.assert_not_called()

    def test_no_existing_case_output_can_be_replayed(self):
        case = tier.bench.catalogue("everyday")[0]
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            (campaign / ("run-" + case["family"]) / case["id"]).mkdir(parents=True)
            with patch.object(tier, "invoke") as invoked, self.assertRaises(ValueError):
                tier.run_case(case, None, campaign, {}, {}, set(), False)
            invoked.assert_not_called()

    def test_cleanup_recognizes_only_explicit_new_sample_volume_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); own = "layerfs-fsb-sample-" + "a" * 16
            other = "layerfs-fsb-sample-" + "b" * 16
            (root / "resource-claim.json").write_text(json.dumps({"created_by_this_run": True, "volume": own}))
            (root / "old-receipt.json").write_text(json.dumps({"referenced_volume": other}))
            child = root / "producer"; child.mkdir()
            (child / "resource-claim.json").write_text(json.dumps({"created_by_this_run": False, "volume": other}))
            self.assertEqual(tier.sample_cleanup.sample_volumes(root), [own])
            with self.assertRaises(ValueError):
                tier.sample_cleanup.docker_command("unused", {own}, "volume", "rm", own)
