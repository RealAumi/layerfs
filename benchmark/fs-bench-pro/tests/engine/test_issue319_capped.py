"""A three-second command cannot spend the capped Commit's two seconds."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import workspace


class CappedCommit(unittest.TestCase):
    def test_command_and_commit_have_separate_deadlines(self):
        case = json.loads((BENCH / 'families/edit_length_changing_capped/family.json').read_text())['cases'][0]
        now = [100.0]
        calls = []
        class Runtime:
            container = 'container'
            selector = raw = stderr = None
            process = None
            rows = []
            def event(self, *args):
                return None
            def send(self, operation, key='', *args, **options):
                calls.append((operation, options.get('deadline')))
                if operation == 'command':
                    now[0] += 3
                if operation == 'commit':
                    raise ValueError('explicit Commit refusal after deadline observation')
                return {'sequence':len(calls), 'event':operation,
                        'span':{'duration_ns':3_000_000_000 if operation == 'command' else 1},
                        'fields':{'state':'Gone'}}
            def retain(self, error):
                return {'cause':str(error), 'remote_stop':'NOT_ESTABLISHED'}
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            current = {'source_commit':'source', 'product_tree':'product', 'files':{}}
            build = {'socket':'/socket', 'binaries':{n:{'sha256':n,'path':'/'+n} for n in ('runtime','daemon')}}
            prepared = {'fixture':{'fixture_sha256':'fixture'},'helpers':{'files':{}},
                        'provision':{'manifest':'/manifest'},'source_uid':1,'source_gid':1}
            for module, name, value in ((workspace.identity,'ROOT',root),
                    (workspace.identity,'source_identity',lambda:current),
                    (workspace.identity,'load_build',lambda *args:build),
                    (workspace.fixtures,'load',lambda *args:prepared),
                    (workspace.fixtures,'validate_runtime_helpers',lambda *args:{}),
                    (workspace.fixtures,'clone',lambda *args:{'volume':'volume'}),
                    (workspace.fixtures,'stage',lambda *args:{}),
                    (workspace.cell_runner,'EventProcess',lambda *args:Runtime()),
                    (workspace.time,'monotonic',lambda:now[0])):
                stack.enter_context(patch.object(module,name,value))
            result = workspace.one_family_case('edit_length_changing_capped',case,'prepared','build',root/'case')
            commands = [deadline for operation,deadline in calls if operation == 'command']
            commits = [deadline for operation,deadline in calls if operation == 'commit']
            self.assertEqual(commands, [220.0, 223.0])
            self.assertEqual(commits, [108.0])
            self.assertEqual(result['original_failure'], 'explicit Commit refusal after deadline observation')
            self.assertEqual(result['sample_count'], 1)


if __name__ == '__main__':
    unittest.main()
