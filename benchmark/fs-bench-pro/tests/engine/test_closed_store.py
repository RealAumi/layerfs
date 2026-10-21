"""Real SQLite WAL copies with synthetic identities; public canonical proof is separate."""
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import test_census as support

oracle = support.oracle


class WalFixture:
    def __init__(self, home, extra=False):
        work = home / "work"
        work.mkdir()
        self.fixture = support.StoreFixture(work, commits=1)
        self.raw = home / "raw"
        self.raw.mkdir()
        fixture = self.fixture
        writer = sqlite3.connect(fixture.path, isolation_level=None, timeout=0)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA synchronous=OFF")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        previous = bytes.fromhex(fixture.expected[-1]["commit_id"])
        for index in (2, 3):
            values = (support.ident(0x12, 33, index), fixture.stack, bytes([15 + index]) * 32, previous, fixture.base)
            writer.execute('INSERT INTO "commit" VALUES(?,?,?,?,?)', values)
            fixture.expected.append(dict(zip(oracle.CENSUS_COLUMNS, [value.hex() if value is not None else None for value in values])))
            previous = values[0]
        writer.execute("UPDATE branch SET head_commit_id=? WHERE branch_id=?", (previous, fixture.branch))
        if extra:
            writer.execute('INSERT INTO "commit" VALUES(?,?,?,?,?)',
                           (support.ident(0x12, 33, 99), fixture.stack, bytes([17]) * 32, None, fixture.base))
        # Copy the full closed snapshot set while its sole writer is idle and
        # alive. Closing the original afterwards cannot checkpoint these copies.
        for name in ("store.sqlite", "store.sqlite-wal", "store.sqlite-shm"):
            shutil.copy2(work / name, self.raw / name)
        writer.close()
        self.before = self.identities()
        self.asserted_wal_bytes = (self.raw / "store.sqlite-wal").stat().st_size
        fixture.provider.update(final_head_commit_id=previous.hex(), final_head_root=fixture.expected[-1]["root_id"])
        rows = [f"0\t-\t-\t{fixture.initial.hex()}\tinitial.tsv"]
        rows += [f"{i}\t{row['commit_id']}\t{row['parent_commit_id'] or '-'}\t{row['root_id']}\t-" for i, row in enumerate(fixture.expected, 1)]
        fixture.transcript.write_text("\n".join(rows) + "\n")
        fixture.provider["acknowledged_transcript_sha256"] = oracle.file_sha(fixture.transcript)
        fixture.custody.update(local_source=str(self.raw / "store.sqlite"),
                               source_sha256=oracle.file_sha(self.raw / "store.sqlite"),
                               source_size=(self.raw / "store.sqlite").stat().st_size,
                               transcript_sha256=oracle.file_sha(fixture.transcript))
        exported = json.loads(fixture.export.read_text())
        exported["argv"][-1] = str(self.raw)
        fixture.export.write_text(json.dumps(exported))
        fixture.custody["export_completion_sha256"] = oracle.file_sha(fixture.export)

    def identities(self):
        return {item.name: {"size": item.stat().st_size, "sha256": oracle.file_sha(item)} for item in self.raw.iterdir()}

    def normalize(self, home):
        return oracle.prepare_closed_store(self.raw, home / "normalized/store.sqlite", time.monotonic() + 10)

    def census(self, result):
        path = Path(result["path"])
        identity = oracle._sealed_identity(path)
        provider = {**self.fixture.provider, "provider_store_sha256": identity["sha256"], "provider_store_size": identity["size"],
                    "provider_store_after_sha256": identity["sha256"], "provider_store_after_size": identity["size"], "provider_store_unchanged": 1}
        custody = {**self.fixture.custody, "normalization": {key: result[key] for key in ("receipt", "receipt_sha256")}}
        return oracle.commit_census(path, self.fixture.expected, provider, custody)


class ClosedStoreNormalization(unittest.TestCase):
    def test_initial_raw_digest_uses_the_scratch_copy_read(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-copy-count-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            scratch = home / "normalized/scratch"
            real_open = Path.open
            counts = {"raw": {}, "scratch": {}}
            sizes = []

            class Counted:
                def __init__(self, stream, kind, name):
                    self.stream, self.kind, self.name = stream, kind, name

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def read(self, size):
                    chunk = self.stream.read(size)
                    totals = counts[self.kind]
                    totals[self.name] = totals.get(self.name, 0) + len(chunk)
                    sizes.append(size)
                    return chunk

            def opened(path, mode="r", *args, **kwargs):
                stream = real_open(path, mode, *args, **kwargs)
                parent = path.resolve().parent
                kind = "raw" if parent == fixture.raw else "scratch" if parent == scratch else None
                return Counted(stream, kind, path.name) if mode == "rb" and kind else stream

            with patch.object(Path, "open", opened):
                result = fixture.normalize(home)
            record = json.loads(Path(result["receipt"]).read_text())
            self.assertEqual(record["raw_files"], fixture.before)
            self.assertEqual(record["copied_files"], fixture.before)
            self.assertEqual(record["raw_files_after"], fixture.before)
            self.assertEqual(fixture.identities(), fixture.before)
            self.assertEqual(oracle._sealed_identity(result["path"]), result["normalized_identity"])
            self.assertEqual(fixture.census(result)["commit_count"], 3)
            raw_stat = (fixture.raw / "store.sqlite").stat()
            copied_stat = (scratch / "store.sqlite").stat()
            self.assertNotEqual((raw_stat.st_dev, raw_stat.st_ino), (copied_stat.st_dev, copied_stat.st_ino))
            expected = {name: value["size"] for name, value in fixture.before.items()}
            print(json.dumps({"scope": "Python normalization stream bytes; SQLite C VFS excluded",
                              "source_sizes": expected, "observed": counts}), flush=True)
            self.assertTrue(sizes)
            self.assertTrue(all(size == 65536 for size in sizes))
            self.assertEqual(counts["scratch"], expected)
            self.assertEqual(counts["raw"], {name: 2 * size for name, size in expected.items()})

    def test_target_selects_off_before_wal_can_initialize_file(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-initial-profile-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            real_connect = sqlite3.connect
            observed = []
            owner = self
            class Target(sqlite3.Connection):
                def execute(self, sql, *args):
                    if sql == "PRAGMA journal_mode=WAL":
                        profile = super().execute("PRAGMA synchronous").fetchone()
                        observed.append(profile)
                        owner.assertEqual(profile, (0,), "WAL initialization must never inherit default FULL synchronization")
                    return super().execute(sql, *args)
            def connect(*args, **kwargs):
                if not kwargs.get("uri"):
                    kwargs["factory"] = Target
                return real_connect(*args, **kwargs)
            with patch.object(oracle.sqlite3, "connect", side_effect=connect):
                result = fixture.normalize(home)
            self.assertEqual(observed, [(0,)])
            self.assertEqual(fixture.identities(), fixture.before)
            self.assertEqual(oracle._sealed_identity(result["path"]), result["normalized_identity"])

    def test_wal_rows_survive_normalization_and_strict_census(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-wal-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            self.assertGreater(fixture.asserted_wal_bytes, 0)
            legacy = home / "legacy.sqlite"
            shutil.copy2(fixture.raw / "store.sqlite", legacy)
            with oracle.closing(sqlite3.connect(legacy.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM "commit"').fetchone(), (1,))
            result = fixture.normalize(home)
            self.assertEqual(Path(result["path"]).read_bytes()[18:20], bytes([2,2]))
            self.assertEqual(fixture.census(result)["commit_count"], 3)
            self.assertEqual(fixture.identities(), fixture.before)
            self.assertEqual(oracle._sealed_identity(result["path"]), result["normalized_identity"])

    def test_delete_header_is_not_a_disposable_store_normalization(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-delete-") as temporary:
            home = Path(temporary).resolve()
            raw = home / "raw"
            raw.mkdir()
            with oracle.closing(sqlite3.connect(raw / "store.sqlite", isolation_level=None, timeout=0)) as connection:
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("CREATE TABLE recorded(value)")
            before = oracle.file_sha(raw / "store.sqlite")
            with self.assertRaises((ValueError, sqlite3.OperationalError)):
                oracle.prepare_closed_store(raw, home / "normalized/store.sqlite", time.monotonic() + 10)
            self.assertEqual(oracle.file_sha(raw / "store.sqlite"), before)

    def test_sidecar_free_input_is_also_qualified(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-main-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            raw = home / "sealed"
            raw.mkdir()
            shutil.copy2(fixture.fixture.path, raw / "store.sqlite")
            before = oracle.file_sha(raw / "store.sqlite")
            result = oracle.prepare_closed_store(raw, home / "normalized/store.sqlite", time.monotonic() + 10)
            with oracle.closing(sqlite3.connect(Path(result["path"]).as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM "commit"').fetchone(), (3,))
            self.assertEqual(oracle.file_sha(raw / "store.sqlite"), before)

    def test_unfiltered_extra_row_is_still_rejected(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-extra-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home, extra=True)
            result = fixture.normalize(home)
            with self.assertRaisesRegex(ValueError, "global Commit membership"):
                fixture.census(result)

    def test_raw_receipt_output_and_sidecar_tampering_are_rejected(self):
        for kind in ("raw", "receipt", "output", "sidecar", "export"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="fsb-closed-tamper-") as temporary:
                home = Path(temporary).resolve()
                fixture = WalFixture(home)
                result = fixture.normalize(home)
                if kind == "raw":
                    with (fixture.raw / "store.sqlite-wal").open("ab") as stream:
                        stream.write(b"changed")
                elif kind == "receipt":
                    with Path(result["receipt"]).open("a") as stream:
                        stream.write(" ")
                elif kind == "output":
                    with Path(result["path"]).open("ab") as stream:
                        stream.write(b"changed")
                elif kind == "sidecar":
                    Path(result["path"] + "-wal").touch()
                else:
                    fixture.fixture.custody["source_sha256"] = "0" * 64
                with self.assertRaises(ValueError):
                    fixture.census(result)

    def test_deadline_and_unsafe_raw_set_refuse_without_mutation(self):
        for kind in ("expired", "symlink", "extra", "journal"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="fsb-closed-refuse-") as temporary:
                home = Path(temporary).resolve()
                fixture = WalFixture(home)
                deadline = time.monotonic() + 10
                if kind == "expired":
                    deadline = time.monotonic() - 1
                elif kind == "symlink":
                    (fixture.raw / "store.sqlite-shm").unlink()
                    (fixture.raw / "store.sqlite-shm").symlink_to(fixture.fixture.path)
                else:
                    (fixture.raw / ("unexpected" if kind == "extra" else "store.sqlite-journal")).touch()
                before = {item.name: oracle.file_sha(item) for item in fixture.raw.iterdir()}
                with self.assertRaises((ValueError, TimeoutError)):
                    oracle.prepare_closed_store(fixture.raw, home / "normalized/store.sqlite", deadline)
                self.assertEqual({item.name: oracle.file_sha(item) for item in fixture.raw.iterdir()}, before)

    def test_rebound_receipt_cannot_change_profile_deadline_or_retry_contract(self):
        mutations = [("backup_attempts", 2), ("source_query_only", True), ("target_journal_mode", "delete"),
                     ("completed_monotonic", float("inf")), ("receipt_scope", "unbounded"), ("copied_files", {})]
        for key, value in mutations:
            with self.subTest(key=key), tempfile.TemporaryDirectory(prefix="fsb-closed-contract-") as temporary:
                home = Path(temporary).resolve()
                fixture = WalFixture(home)
                result = fixture.normalize(home)
                path = Path(result["receipt"])
                record = json.loads(path.read_text())
                record[key] = value
                path.write_text(json.dumps(record))
                result["receipt_sha256"] = oracle.file_sha(path)
                with self.assertRaises(ValueError):
                    fixture.census(result)

    def test_backup_progress_enforces_absolute_deadline(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-deadline-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            real_connect, real_clock = sqlite3.connect, time.monotonic
            deadline, expired = real_clock() + 10, [False]
            class ExpiringSource:
                def __init__(self, connection):
                    self.connection = connection
                def __getattr__(self, name):
                    return getattr(self.connection, name)
                def backup(self, target, *, pages, progress, sleep):
                    def advance(*values):
                        expired[0] = True
                        progress(*values)
                    self.connection.backup(target, pages=pages, progress=advance, sleep=sleep)
            def connect(*args, **kwargs):
                connection = real_connect(*args, **kwargs)
                return ExpiringSource(connection) if kwargs.get("uri") else connection
            with patch.object(oracle.sqlite3, "connect", side_effect=connect), patch.object(oracle.time, "monotonic", side_effect=lambda: deadline + 1 if expired[0] else real_clock()):
                with self.assertRaisesRegex(TimeoutError, "absolute deadline"):
                    oracle.prepare_closed_store(fixture.raw, home / "normalized/store.sqlite", deadline)
            self.assertTrue(expired[0])
            self.assertEqual(fixture.identities(), fixture.before)
            self.assertFalse((home / "normalized/normalization.json").exists())

    def test_backup_busy_aborts_one_attempt_without_retry(self):
        with tempfile.TemporaryDirectory(prefix="fsb-closed-busy-") as temporary:
            home = Path(temporary).resolve()
            fixture = WalFixture(home)
            real = sqlite3.connect
            calls = []
            class BusySource:
                def __init__(self, connection):
                    self.connection = connection
                def __getattr__(self, name):
                    return getattr(self.connection, name)
                def backup(self, target, *, pages, progress, sleep):
                    calls.append((pages, sleep))
                    progress(sqlite3.SQLITE_BUSY, 1, 1)
                    raise AssertionError("BUSY callback returned instead of aborting")
            def connect(*args, **kwargs):
                connection = real(*args, **kwargs)
                return BusySource(connection) if kwargs.get("uri") else connection
            with patch.object(oracle.sqlite3, "connect", side_effect=connect):
                with self.assertRaisesRegex((sqlite3.OperationalError, ValueError), "BUSY|LOCKED"):
                    fixture.normalize(home)
            self.assertEqual(calls, [(128, 0)])
            self.assertEqual(fixture.identities(), fixture.before)


if __name__ == "__main__":
    unittest.main()
