"""D-5's four kept selections; owner E-1 separately names one large proof."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('issue319_invoke', ROOT/'core/docs/issues/319/tools/invoke_case.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class DriverPolicy(unittest.TestCase):
    def test_two_kept_runs_and_two_preparations_get_300_seconds(self):
        self.assertEqual(len(driver.EXTENDED),4)
        self.assertEqual(sum(kind=='prepare' for kind,_ in driver.EXTENDED),2)
        for kind,item in driver.EXTENDED:
            with self.subTest(kind=kind,item=item):
                policy = driver.call_policy(kind,item)
                self.assertEqual(policy['outer_seconds'],300)
                self.assertLess(policy['driver_seconds'],300)
                self.assertIn('D-5',policy['reason'])
                self.assertIn('unchanged',policy['reason'])

    def test_other_phase_and_nearby_sizes_do_not_inherit_the_exception(self):
        for kind,item in driver.EXTENDED:
            for altered in ((('prepare' if kind=='run' else 'run'),item),
                            (kind,item+'-extra'),(kind,item.replace('500','100'))):
                if altered in driver.EXTENDED or altered in driver.EXTREME or altered in driver.LARGE_ROOT_RUNS:
                    continue
                self.assertEqual(driver.call_policy(*altered)['outer_seconds'],118)
        for kind in ('clean','report','rows'):
            for _,item in driver.EXTENDED:
                self.assertEqual(driver.call_policy(kind,item)['outer_seconds'],118)

    def test_three_large_root_runs_get_300_seconds_and_nothing_near_them_does(self):
        self.assertEqual(driver.LARGE_ROOT_RUNS, frozenset([
            ('run','multi_workspace_development:v016-workspace-mixed-500mb-30000-k100-v1'),
            ('run','branch_development:v016-branch-mixed-500mb-30000-k10-v1'),
            ('run','branch_development:v016-branch-mixed-500mb-30000-k100-v1')]))
        for kind,item in driver.LARGE_ROOT_RUNS:
            with self.subTest(item=item):
                policy = driver.call_policy(kind,item)
                self.assertEqual((policy['outer_seconds'],policy['driver_seconds']),(300,288))
                self.assertIn('unchanged',policy['reason'])
                for altered in ((kind,item+'-extra'),(kind,item.replace('500mb-30000','100mb-5000')),
                                ('clean',item),('report',item),('rows',item)):
                    self.assertEqual(driver.call_policy(*altered)['outer_seconds'],118)
        for item in ('multi_workspace_development:v016-workspace-mixed-500mb-30000-k10-v1',
                     'mixed_load_bearing:v016-mixed-development-500mb-30000-k10-v1',
                     'mixed_load_bearing:v016-mixed-development-500mb-30000-k100-v1'):
            self.assertEqual(driver.call_policy('run',item)['outer_seconds'],118)


if __name__ == '__main__':
    unittest.main()
