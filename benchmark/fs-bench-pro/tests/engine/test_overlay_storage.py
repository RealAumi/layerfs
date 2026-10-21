"""Synthetic closed source-schema accounting/custody admission guards.

No Docker is invoked. Resource and runtime receipts are explicitly synthetic
protocol fixtures, never evidence of an actual case, Stop, mount or source stat.
The exported fixture's own stat is actual and is never relabeled source allocation.
"""
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
import test_census as store_support
import test_closed_store as closed_support
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('overlay_oracle', BENCH / 'engine/oracle.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class OverlayFixture:
    """A closed template, the archive of its directory and one mounted owner.

    `left` names the namespaces whose Workspace file the synthetic stopped
    directory still holds; the measured owner is namespace 1.
    """
    def __init__(self, home, left=()):
        self.home = home.resolve()
        self.path = self.home / 'overlay.sqlite'
        self.source, _, _, _ = oracle._overlay_storage_source()
        database = sqlite3.connect(self.path, isolation_level=None, timeout=0)
        database.execute('PRAGMA page_size=4096')
        database.execute('PRAGMA journal_mode=MEMORY')
        database.execute('PRAGMA synchronous=OFF')
        database.executescript(self.source)
        database.close()
        self.owner = {'key': 'measured', 'namespace': 1, 'incarnation': '01' * 32}
        self.events = self.home / 'runtime.events.jsonl'
        self.export = self.home / 'export.completion.json'
        self.archive = self.home / 'directory.stdout'
        self.listed = self.home / 'directory.completion.json'
        self.container = 'a' * 64
        self.volume = 'layerfs-fsb-sample-synthetic-only'
        self.write_events([
            {'event': 'sandbox_create_attempt', 'sequence': 1, 'value': 'volume=' + self.volume},
            {'event': 'daemon_setup', 'sequence': 2, 'fields': {'container': self.container}},
            {'event': 'mount', 'sequence': 3, 'fields': {'key': self.owner['key'], 'workspace_incarnation': self.owner['incarnation'],
                         'workspace_namespace': self.owner['namespace']}},
            {'event': 'container_stopped', 'sequence': 4, 'value': self.container},
            {'event': 'finished', 'sequence': 5}])
        self.export.write_text(json.dumps({'status': 'PASS', 'exit_code': 0, 'attempts': 1,
            'argv': ['docker', '--host', 'unix:///synthetic-only.sock', 'cp',
                     self.container + ':/layerfs-local/overlay/overlay.sqlite', str(self.path)]}))
        self.listed.write_text(json.dumps({'status': 'PASS', 'exit_code': 0, 'attempts': 1, 'stdout': str(self.archive),
            'argv': ['docker', '--host', 'unix:///synthetic-only.sock', 'cp',
                     self.container + ':/layerfs-local/overlay', '-']}))
        self.custody = dict(custody='KNOWN_STOP', container=self.container, volume=self.volume,
                            remote_source='/layerfs-local/overlay/overlay.sqlite', local_source=str(self.path),
                            runtime_events=str(self.events), export_completion=str(self.export))
        self.left = {namespace: b'workspace file ' + bytes([namespace]) for namespace in left}
        self.extra = {}
        self.rebind()

    def write_archive(self):
        """The directory as `docker cp <container>:/layerfs-local/overlay -` writes it."""
        with tarfile.open(self.archive, mode='w') as archive:
            folder = tarfile.TarInfo('overlay/'); folder.type = tarfile.DIRTYPE
            archive.addfile(folder)
            members = {'overlay/overlay.sqlite': self.path.read_bytes(),
                       **{f'overlay/{namespace}.sqlite': body for namespace, body in self.left.items()}, **self.extra}
            for name, body in members.items():
                member = tarfile.TarInfo(name); member.size = len(body)
                archive.addfile(member, io.BytesIO(body))

    def rebind(self):
        self.write_archive()
        self.custody.update(source_sha256=oracle.file_sha(self.path), source_size=self.path.stat().st_size,
                            runtime_events_sha256=oracle.file_sha(self.events), export_completion_sha256=oracle.file_sha(self.export),
                            directory={'completion': str(self.listed), 'completion_sha256': oracle.file_sha(self.listed),
                                       'stdout': str(self.archive), 'stdout_sha256': oracle.file_sha(self.archive)})

    def write_events(self, events):
        self.events.write_text(''.join(json.dumps(event) + '\n' for event in events))

    def mutate(self, sql, params=()):
        with oracle.closing(sqlite3.connect(self.path, isolation_level=None, timeout=0)) as database:
            database.execute('PRAGMA journal_mode=MEMORY')
            database.execute('PRAGMA synchronous=OFF')
            database.execute(sql, params)
        self.rebind()

    def run(self):
        return oracle.observe_closed_storage(self.path, self.custody, kind='overlay', owners=[self.owner])


class ClosedOverlayStorage(unittest.TestCase):
    def test_gone_is_the_absent_workspace_file_beside_an_empty_template(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            before = fixture.path.read_bytes()
            result = fixture.run()
            owner = result['owners'][0]
            self.assertEqual(result['schema'], 'fs-bench-pro-closed-storage-observation-v2')
            self.assertEqual(result['schema_version'], 37)
            self.assertEqual(owner['state'], 'GONE')
            self.assertEqual(owner['workspace_file'], '/layerfs-local/overlay/1.sqlite')
            self.assertIsNone(owner['workspace_file_bytes_after_stop'])
            self.assertEqual(result['namespace_cleanup_status'], 'PASS')
            self.assertEqual(result['owned_files_after_cleanup_status'], 'PASS')
            self.assertEqual(result['observation_status'], 'PASS')
            listing = result['overlay_directory']
            self.assertEqual(listing['workspace_files_after_stop'], 0)
            self.assertFalse(any(listing['template_rows'].values()))
            self.assertEqual(listing['archive']['template']['sha256'], result['export_copy']['sha256'])
            # No physical byte of a Workspace is credited from closed storage.
            for key in ('legacy_physical_equation_status', 'legacy_physical_resource_status',
                        'owned_spool_2gib_status', 'source_main_store_4gib_status'):
                self.assertEqual(result[key], 'UNAVAILABLE')
            for key in ('workspace_physical_live_bytes', 'workspace_physical_allocated_bytes', 'workspace_physical_peak_bytes'):
                self.assertTrue(result['metric_availability'][key].startswith('UNAVAILABLE'))
            self.assertEqual(result['export_copy']['export_allocated_bytes'], fixture.path.stat().st_blocks * 512)
            self.assertEqual(fixture.path.read_bytes(), before)
            self.assertEqual(result['original_limits_bytes'], {'main_store': 4 * 1024**3, 'owned_spool': 2 * 1024**3})

    def test_a_workspace_file_left_after_stop_fails_cleanup_and_is_counted(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp), left=(1,))
            result = fixture.run()
            owner = result['owners'][0]
            self.assertEqual(owner['state'], 'HELD')
            self.assertEqual(owner['workspace_file_bytes_after_stop'], len(fixture.left[1]))
            self.assertEqual(result['namespace_cleanup_status'], 'FAIL')
            self.assertEqual(result['owned_files_after_cleanup_status'], 'FAIL')
            self.assertEqual(result['observation_status'], 'PASS')
        # Another Workspace's file is not the measured owner's, and still fails the directory.
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp), left=(2,))
            result = fixture.run()
            self.assertEqual(result['owners'][0]['state'], 'GONE')
            self.assertEqual(result['namespace_cleanup_status'], 'PASS')
            self.assertEqual(result['overlay_directory']['workspace_files_after_stop'], 1)
            self.assertEqual(result['owned_files_after_cleanup_status'], 'FAIL')

    def test_a_template_that_holds_a_row_is_refused(self):
        for sql, params in (
                ('INSERT INTO fs_truncate(inode,generation,depth,cell_offset,epoch) VALUES(1,1,1,0,1)', ()),
                ('INSERT INTO cleanup_task(kind,resource,target) VALUES(1,0,1)', ())):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
                fixture = OverlayFixture(Path(temp)); fixture.mutate(sql, params)
                with self.assertRaisesRegex(ValueError, 'template holds rows'):
                    fixture.run()

    def test_directory_archive_members_command_and_template_identity_are_exact(self):
        for change in ('sidecar', 'unknown', 'nested', 'zero', 'padded', 'template', 'command', 'hash', 'missing'):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
                fixture = OverlayFixture(Path(temp))
                if change == 'sidecar': fixture.extra = {'overlay/overlay.sqlite-journal': b''}
                if change == 'unknown': fixture.extra = {'overlay/notes.txt': b'x'}
                if change == 'nested': fixture.extra = {'overlay/1/2.sqlite': b'x'}
                if change == 'zero': fixture.extra = {'overlay/0.sqlite': b'x'}
                if change == 'padded': fixture.extra = {'overlay/01.sqlite': b'x'}
                fixture.rebind()
                if change == 'template':
                    with tarfile.open(fixture.archive, mode='w') as archive:
                        member = tarfile.TarInfo('overlay/overlay.sqlite'); member.size = 3
                        archive.addfile(member, io.BytesIO(b'abc'))
                    fixture.custody['directory']['stdout_sha256'] = oracle.file_sha(fixture.archive)
                if change == 'command':
                    command = json.loads(fixture.listed.read_text()); command['argv'][4] = fixture.container + ':/layerfs-local'
                    fixture.listed.write_text(json.dumps(command))
                    fixture.custody['directory']['completion_sha256'] = oracle.file_sha(fixture.listed)
                if change == 'hash': fixture.custody['directory']['stdout_sha256'] = '00' * 32
                if change == 'missing': del fixture.custody['directory']
                with self.assertRaisesRegex(ValueError, 'closed overlay directory'):
                    fixture.run()

    def test_exact_incarnation_domain_and_owner_membership_are_required(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            for owner in ({**fixture.owner, 'namespace': 0}, {**fixture.owner, 'namespace': True},
                          {**fixture.owner, 'incarnation': '00' * 32}, {**fixture.owner, 'incarnation': 'ff' * 31},
                          'invalid-owner'):
                with self.subTest(owner=owner), self.assertRaises(ValueError):
                    oracle._observe_closed_storage_read_only(fixture.path, 'overlay', [owner], {})
            with self.assertRaisesRegex(ValueError, 'unique explicit'):
                oracle._observe_closed_storage_read_only(fixture.path, 'overlay', [], {})
            with self.assertRaisesRegex(ValueError, 'unique explicit'):
                oracle._observe_closed_storage_read_only(fixture.path, 'overlay', [fixture.owner, fixture.owner], {})
            # An overlay observation needs the directory; a mount token of another incarnation is refused by custody.
            with self.assertRaisesRegex(ValueError, 'directory membership'):
                oracle._observe_closed_storage_read_only(fixture.path, 'overlay', [fixture.owner])
            with self.assertRaisesRegex(ValueError, 'mount token'):
                oracle.observe_closed_storage(fixture.path, fixture.custody, kind='overlay',
                                              owners=[{**fixture.owner, 'incarnation': 'ff' * 32}])

    def test_canonical_schema_trigger_membership_version_and_source_pins(self):
        for sql in ('CREATE TABLE extra(a INTEGER)', 'CREATE TRIGGER extra AFTER INSERT ON fs_truncate BEGIN SELECT 1; END', 'PRAGMA user_version=33'):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
                fixture = OverlayFixture(Path(temp)); fixture.mutate(sql)
                with self.assertRaisesRegex(ValueError, 'schema'):
                    fixture.run()
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            actual_sha = oracle.file_sha
            with patch.object(oracle, 'file_sha', side_effect=lambda path: 'bad' if str(path).endswith('/layerfs-overlay/sql/schema.sql') else actual_sha(path)):
                with self.assertRaisesRegex(ValueError, 'source pin'):
                    fixture.run()

    def test_knownstop_export_hash_command_and_explicit_mount_token_guards(self):
        for change in ('not_stopped', 'wrong_mount', 'missing_mount_numeric', 'wrong_sequence', 'wrong_export', 'wrong_hash'):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
                fixture = OverlayFixture(Path(temp))
                events = [json.loads(line) for line in fixture.events.read_text().splitlines()]
                if change == 'not_stopped': events[3]['event'] = 'attempted_stop'
                if change == 'wrong_mount': events[2]['fields']['workspace_incarnation'] = 'ff' * 32
                if change == 'missing_mount_numeric': del events[2]['fields']['workspace_namespace']
                if change == 'wrong_sequence': events[3]['sequence'] = 3
                fixture.write_events(events)
                if change == 'wrong_export':
                    command = json.loads(fixture.export.read_text()); command['argv'][4] = fixture.container + ':/wrong/file'
                    fixture.export.write_text(json.dumps(command))
                fixture.rebind()
                if change == 'wrong_hash': fixture.custody['source_sha256'] = '00' * 32
                with self.assertRaises(ValueError): fixture.run()

    def test_sidecars_hardlinks_and_change_during_read_are_refused(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            Path(str(fixture.path) + '-journal').touch()
            with self.assertRaisesRegex(ValueError, 'sidecar'): fixture.run()
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            (Path(temp) / 'hardlink').hardlink_to(fixture.path)
            with self.assertRaisesRegex(ValueError, 'one regular copy'): fixture.run()
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            observe = oracle._overlay_owner_state
            def mutate_after_observation(*args):
                result = observe(*args)
                with fixture.path.open('ab') as stream: stream.write(b'changed')
                return result
            with patch.object(oracle, '_overlay_owner_state', side_effect=mutate_after_observation):
                with self.assertRaisesRegex(ValueError, 'changed'): fixture.run()

    def test_actual_current_store_schema_and_source_stat_guard_have_distinct_scopes(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = store_support.StoreFixture(Path(temp))
            result = oracle.observe_closed_storage(fixture.path, fixture.custody, kind='store')
            self.assertEqual(result['schema_version'], 7)
            self.assertEqual(result['source_main_store_4gib_status'], 'UNAVAILABLE')
            self.assertEqual(result['namespace_cleanup_status'], 'UNAVAILABLE')
            stdout, completion = Path(temp) / 'source-stat.stdout', Path(temp) / 'source-stat.completion.json'
            row = {'schema': 'fs-bench-pro-source-storage-stat-v1', 'path': '/layerfs-store/global/store.sqlite',
                   'logical_bytes': fixture.path.stat().st_size, 'allocated_bytes': 4 * 1024**3 + 512,
                   'device': 1, 'inode': 2, 'links': 1}
            stdout.write_text(json.dumps(row))
            command = {'status': 'PASS', 'exit_code': 0, 'attempts': 1, 'stdout': str(stdout),
                       'argv': ['docker', '--host', 'unix:///synthetic-only.sock', 'exec', '--user', '0:0',
                                fixture.container, 'python3', '-B', '-c', oracle.storage_source_stat_body('store')]}
            completion.write_text(json.dumps(command))
            def bind():
                fixture.custody['source_stat'] = {'completion': str(completion), 'completion_sha256': oracle.file_sha(completion),
                                                 'stdout': str(stdout), 'stdout_sha256': oracle.file_sha(stdout)}
            bind()
            result = oracle.observe_closed_storage(fixture.path, fixture.custody, kind='store')
            self.assertEqual(result['source_main_store_4gib_status'], 'FAIL')
            self.assertNotEqual(result['source_stat']['allocated_bytes'], result['export_copy']['export_allocated_bytes'])
            row['allocated_bytes'] = 4 * 1024**3
            stdout.write_text(json.dumps(row)); bind()
            self.assertEqual(oracle.observe_closed_storage(fixture.path, fixture.custody, kind='store')['source_main_store_4gib_status'], 'PASS')
            command['argv'][-1] += '# changed observer'
            completion.write_text(json.dumps(command)); bind()
            with self.assertRaisesRegex(ValueError, 'exact acknowledged command'):
                oracle.observe_closed_storage(fixture.path, fixture.custody, kind='store')

    def test_normalized_wal_store_observation_binds_full_raw_set_without_modifying_it(self):
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            home = Path(temp).resolve()
            fixture = closed_support.WalFixture(home)
            normalized = fixture.normalize(home)
            custody = dict(fixture.fixture.custody)
            custody['normalization'] = {'receipt': normalized['receipt'], 'receipt_sha256': normalized['receipt_sha256']}
            result = oracle.observe_closed_storage(normalized['path'], custody, kind='store')
            self.assertEqual(result['observation_status'], 'PASS')
            self.assertEqual(result['normalization'], custody['normalization'])
            self.assertEqual(fixture.identities(), fixture.before)
            self.assertEqual(result['export_copy']['sha256'], normalized['normalized_identity']['sha256'])
            self.assertEqual(result['source_main_store_4gib_status'], 'UNAVAILABLE')
            with (fixture.raw / 'store.sqlite-wal').open('ab') as stream:
                stream.write(b'changed raw WAL')
            with self.assertRaisesRegex(ValueError, 'raw SQLite set changed'):
                oracle.observe_closed_storage(normalized['path'], custody, kind='store')

    def test_source_stat_binding_preserves_original_main_store_limit_and_copy_distinction(self):
        # Synthetic Store-stat receipt tests exercise admission/threshold arithmetic,
        # not actual source telemetry. The public path always authenticates this
        # separately from the exported copy's physical observation.
        with tempfile.TemporaryDirectory(prefix='fsb-overlay-test-') as temp:
            fixture = OverlayFixture(Path(temp))
            stdout, completion = Path(temp) / 'stat.stdout', Path(temp) / 'stat.completion.json'
            body = oracle.storage_source_stat_body('store')
            row = {'schema': 'fs-bench-pro-source-storage-stat-v1', 'path': '/layerfs-store/global/store.sqlite',
                   'logical_bytes': 1024, 'allocated_bytes': 4 * 1024**3 + 512, 'device': 1, 'inode': 2, 'links': 1}
            stdout.write_text(json.dumps(row))
            completion.write_text(json.dumps({'status': 'PASS', 'exit_code': 0, 'attempts': 1, 'stdout': str(stdout),
                'argv': ['docker', '--host', 'unix:///synthetic-only.sock', 'exec', '--user', '0:0',
                         fixture.container, 'python3', '-B', '-c', body]}))
            fixture.custody['source_stat'] = {'completion': str(completion), 'completion_sha256': oracle.file_sha(completion),
                                             'stdout': str(stdout), 'stdout_sha256': oracle.file_sha(stdout)}
            result = oracle._storage_source_stat(fixture.custody, 'store')
            self.assertEqual(result['allocated_bytes'], row['allocated_bytes'])
            self.assertNotEqual(result['allocated_bytes'], fixture.path.stat().st_blocks * 512)
            stdout.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash'): oracle._storage_source_stat(fixture.custody, 'store')


if __name__ == '__main__':
    unittest.main()
