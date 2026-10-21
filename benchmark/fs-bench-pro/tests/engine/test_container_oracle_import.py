"""Copied native oracle CLI imports without weakening host schema-source pins."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import oracle


class ContainerOracleImport(unittest.TestCase):
    def test_shallow_copied_module_imports_and_offline_census_refuses_missing_sources(self):
        body = (BENCH / 'engine/oracle.py').read_text()
        scope = {'__file__': '/code/engine/oracle.py', '__name__': 'copied_native_oracle'}
        exec(compile(body, scope['__file__'], 'exec'), scope)
        self.assertTrue(callable(scope['prepare']))
        with patch.object(scope['sqlite3'], 'connect') as opened:
            with self.assertRaisesRegex(ValueError, 'authoritative repository schema sources unavailable'):
                scope['_schema_source'](7)
        opened.assert_not_called()

    def test_host_schema_pin_checker_remains_exact(self):
        self.assertEqual(oracle.ROOT, BENCH.parents[1])
        source, definition, tables = oracle._schema_source(7)
        self.assertIn('branch', tables)
        self.assertIn('inode_value', tables)
        self.assertNotIn('metadata_value_group', tables)
        self.assertIn('CREATE TABLE', source)
        self.assertTrue(definition)
        with patch.dict(oracle.SCHEMA_PINS, {next(iter(oracle.SCHEMA_PINS)): '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'authoritative schema/wire source pin changed'):
                oracle._schema_source(7)


if __name__ == '__main__':
    unittest.main()
