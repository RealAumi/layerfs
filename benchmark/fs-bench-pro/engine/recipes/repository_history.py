"""Authenticated original repository transitions and full observed-tree oracles.

This is native input recipe machinery. It performs no Store, SDK or measurement
operation. Corpus paths are read only; output must be fresh and outside the corpus.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

MANIFEST_SHA = "03f21acfb415907f521217e7a972ed512265c8d0c2da0f8034e2ff3014334271"
SOURCE_TIP = "b0a7d2ce3b4c19d7452e364b2d7acbfa87e707ed"
SELECTIONS = {"deepseek-full": tuple(range(1, 158)),
              "deepseek-stride3": tuple(range(1, 158, 3)),
              "deepseek-stride10": tuple(sorted(set(range(1, 158, 10)) | {157}))}


def remaining(deadline, operation):
    value = deadline.require(operation) if hasattr(deadline, "require") else float(deadline) - time.monotonic()
    if not math.isfinite(value) or value <= 0:
        raise TimeoutError(operation + " reached the explicit preparation deadline")
    return value


def sha256(path, deadline):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            remaining(deadline, "source/recipe hashing")
            chunk = source.read(65536)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def regular(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("exact regular input file required: " + str(path))


def read_manifest(data):
    path = Path(data) / "checkpoint-manifest.json"
    regular(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError("original checkpoint manifest identity")
    manifest = json.loads(raw)
    rows = manifest["checkpoints"]
    if manifest["tip"] != SOURCE_TIP or len(rows) != 157 or [r["index"] for r in rows] != list(range(1, 158)):
        raise ValueError("original source tip/checkpoint order")
    return raw, manifest


def entries(raw):
    result = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid, size = meta.split()
        if (kind != b"blob" or mode not in (b"100644", b"100755", b"120000")
                or len(oid) != 40 or any(c not in b"0123456789abcdef" for c in oid)
                or not path or b"\0" in path or path.hex() in result
                or any(p in (b"", b".", b"..") for p in path.split(b"/"))):
            raise ValueError("unsupported/unsafe/duplicate original Git tree entry")
        length = int(size)
        if length < 0:
            raise ValueError("negative original blob length")
        result[path.hex()] = (mode.decode(), oid.decode(), length)
    names = {bytes.fromhex(path) for path in result}
    if any(b"/".join(path.split(b"/")[:n]) in names
           for path in names for n in range(1, len(path.split(b"/")))):
        raise ValueError("file is an original path ancestor")
    return result


def encode(tree):
    return "".join(f"{mode}\t{oid}\t{size}\t{path}\n" for path, (mode, oid, size) in sorted(tree.items()))


def git_tree(data, row, deadline):
    result = subprocess.run(["git", "--git-dir=" + str(Path(data) / "source.git"),
                             "ls-tree", "-rlz", "--full-tree", row["sha"]],
                            capture_output=True, timeout=remaining(deadline, "original Git tree authentication"), check=True)
    raw = result.stdout
    if hashlib.sha256(raw).hexdigest() != row["manifest_sha256"]:
        raise ValueError("original raw Git tree manifest identity")
    tree = entries(raw)
    if len(tree) != row["files"] or sum(value[2] for value in tree.values()) != row["logical_bytes"]:
        raise ValueError("original checkpoint file/logical census")
    return raw, tree


class GitBlobs:
    """One exact cat-file batch, bounded streaming reads and no object retry."""
    def __init__(self, data, stderr):
        self.log = Path(stderr).open("xb")
        self.process = subprocess.Popen(["git", "--git-dir=" + str(Path(data) / "source.git"), "cat-file", "--batch"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = bytearray()

    def read(self, length, deadline):
        while len(self.buffer) < length:
            if not self.selector.select(remaining(deadline, "original Git blob read")):
                raise TimeoutError("original Git blob read deadline")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise ValueError("original Git blob stream ended early")
            self.buffer.extend(chunk)
        result = bytes(self.buffer[:length])
        del self.buffer[:length]
        return result

    def copy(self, oid, size, output, deadline):
        remaining(deadline, "original Git blob request")
        self.process.stdin.write((oid + "\n").encode())
        self.process.stdin.flush()
        header = bytearray()
        while not header.endswith(b"\n"):
            header.extend(self.read(1, deadline))
            if len(header) > 128:
                raise ValueError("original Git blob header is malformed")
        if header.split() != [oid.encode(), b"blob", str(size).encode()]:
            raise ValueError("original Git blob header identity")
        git_digest = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        raw_digest = hashlib.sha256()
        with Path(output).open("xb") as dest:
            left = size
            while left:
                raw = self.read(min(left, 65536), deadline)
                dest.write(raw)
                git_digest.update(raw)
                raw_digest.update(raw)
                left -= len(raw)
        if self.read(1, deadline) != b"\n" or git_digest.hexdigest() != oid:
            raise ValueError("original Git blob body identity")
        return raw_digest.hexdigest()

    def finish(self, deadline):
        self.process.stdin.close()
        if self.buffer or self.process.wait(timeout=remaining(deadline, "original Git blob process exit")):
            raise ValueError("original Git blob process did not close successfully")

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.stdout.close()
        self.selector.close()
        self.log.close()


def membership(root, deadline):
    """Complete owned recipe member list, never a whole corpus traversal."""
    files = {}
    directories = ["."]
    for base, dirs, names in os.walk(root, followlinks=False):
        remaining(deadline, "owned recipe membership")
        for name in sorted(dirs):
            path = Path(base) / name
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError("recipe directory is not exact directory")
            directories.append(str(path.relative_to(root)))
        for name in sorted(names):
            path = Path(base) / name
            regular(path)
            files[str(path.relative_to(root))] = sha256(path, deadline)
    return {"files": dict(sorted(files.items())), "directories": sorted(directories)}


def parse_observed(path):
    actual = {}
    for line in Path(path).read_text().splitlines():
        mode, size, digest, name = line.split("\t")
        raw = bytes.fromhex(name)
        length = int(size)
        if (name != raw.hex() or not raw or any(p in (b"", b".", b"..") for p in raw.split(b"/"))
                or mode not in ("100644", "100755", "120000", "40755") or length < 0 or name in actual
                or mode == "40755" and (length != 0 or digest != "-")
                or mode != "40755" and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest))):
            raise ValueError("malformed/duplicate original observed tree row")
        actual[name] = [mode, length, digest]
    return actual


def verify_observed(observed, oracle):
    actual = parse_observed(observed)
    regular(oracle)
    expected = json.loads(Path(oracle).read_text())
    if actual != expected:
        raise ValueError("complete original historical tree oracle mismatch")
    return {"status": "PASS", "verified_entries": len(actual),
            "verified_bytes": sum(value[1] for value in actual.values()),
            "scope": "all original observed paths/kinds/modes/lengths/SHA256 and symlink target bytes; no mtime assertion added"}


def copy_cached_blob(path, oid, size, output, deadline):
    regular(path)
    git_digest = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
    raw_digest = hashlib.sha256()
    count = 0
    with Path(path).open("rb") as source, Path(output).open("xb") as dest:
        while True:
            remaining(deadline, "original cached blob byte copy")
            chunk = source.read(65536)
            if not chunk:
                break
            dest.write(chunk)
            git_digest.update(chunk)
            raw_digest.update(chunk)
            count += len(chunk)
    if count != size or git_digest.hexdigest() != oid:
        raise ValueError("original cached blob Git identity")
    return raw_digest.hexdigest()


def authenticate_and_prepare(data, case, output, deadline):
    if case not in SELECTIONS:
        raise ValueError("exact original repository-history selection required")
    if remaining(deadline, "repository preparation start") > 120:
        raise ValueError("repository preparation deadline exceeds owner120s ceiling")
    data, output = Path(data).resolve(), Path(output).resolve()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(data):
        raise ValueError("fresh owned recipe output outside source corpus required")
    raw_manifest, manifest = read_manifest(data)
    selected = [manifest["checkpoints"][i-1] for i in SELECTIONS[case]]
    output.mkdir(parents=True)
    previous, digests, states = {}, {}, []
    blobs = GitBlobs(data, output / "git-cat-file.stderr")
    try:
        for ordinal, row in enumerate(selected, 1):
            raw_tree, tree = git_tree(data, row, deadline)
            folder = output / str(ordinal)
            (folder / "blobs").mkdir(parents=True)
            (folder / "manifest.tsv").write_text(encode(tree))
            (folder / "previous.tsv").write_text(encode(previous))
            cached = None
            if case == "deepseek-full":
                cached = data / "inputs" / row["sha"]
                if cached.is_symlink() or not cached.is_dir():
                    raise ValueError("original immutable full157 transition is absent")
                cached_receipt = cached.with_suffix(".receipt.json")
                regular(cached_receipt)
                saved = json.loads(cached_receipt.read_text())
                key = hashlib.sha256(encode(previous).encode() + b"\0" + raw_tree).hexdigest()
                if (saved["key"] != key or membership(cached, deadline)["files"] != saved["files"]
                        or (cached / "manifest.tsv").read_text() != encode(tree)
                        or (cached / "previous.tsv").read_text() != encode(previous)):
                    raise ValueError("original cached full157 transition receipt/manifests")
            for path, value in sorted(tree.items()):
                remaining(deadline, "original selected transition")
                if previous.get(path) == value:
                    continue
                mode, oid, size = value
                dest = folder / "blobs" / oid
                if not dest.exists():
                    digests[oid] = (copy_cached_blob(cached / "blobs" / oid, oid, size, dest, deadline)
                                    if cached is not None else blobs.copy(oid, size, dest, deadline))
            expected = {}
            for path, (mode, oid, size) in tree.items():
                expected[path] = [mode, size, digests[oid]]
                parts = bytes.fromhex(path).split(b"/")
                for n in range(1, len(parts)):
                    expected[b"/".join(parts[:n]).hex()] = ["40755", 0, "-"]
            oracle = data / "oracles" / (row["sha"] + ".json")
            regular(oracle)
            if json.loads(oracle.read_text()) != expected:
                raise ValueError("selected original full-byte oracle differs from authenticated Git blobs")
            oracle_copy = folder / "oracle.json"
            with oracle.open("rb") as source, oracle_copy.open("xb") as dest:
                while True:
                    remaining(deadline, "original oracle byte copy")
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    dest.write(chunk)
            input_seal = membership(folder, deadline)
            oracle_sha = sha256(oracle, deadline)
            if input_seal["files"]["oracle.json"] != oracle_sha:
                raise ValueError("original oracle changed during recipe copy")
            states.append({**row, "index": ordinal, "full157_index": row["index"],
                           "input": str(folder), "oracle": str(oracle_copy), "source_oracle": str(oracle),
                           "oracle_sha256": oracle_sha, "input_seal": input_seal,
                           "full_entries": len(expected), "logical_bytes": row["logical_bytes"],
                           "raw_tree_sha256": hashlib.sha256(raw_tree).hexdigest(),
                           "previous_full157_index": None if ordinal == 1 else selected[ordinal-2]["index"]})
            previous = tree
        blobs.finish(deadline)
    finally:
        blobs.close()
    if (data / "checkpoint-manifest.json").read_bytes() != raw_manifest:
        raise ValueError("original corpus manifest changed during preparation")
    result = {"schema": "fs-bench-pro-repository-input-v1", "status": "PASS", "case": case,
              "source_tip": SOURCE_TIP, "manifest_sha256": MANIFEST_SHA,
              "full157_indices": list(SELECTIONS[case]), "state_count": len(states), "states": states,
              "source_corpus": str(data), "profile": "native transitions only; no Store/SDK operation",
              "input_identity": hashlib.sha256(raw_manifest + repr(SELECTIONS[case]).encode()
                                                + Path(__file__).read_bytes()).hexdigest(),
              "scope": "exact selected direct transitions and original complete tree oracles; no skipped state replay"}
    with (output / "fixture.json").open("x") as dest:
        json.dump(result, dest, indent=2, sort_keys=True)
        dest.write("\n")
    sealed = membership(output, deadline)
    for path in sealed["files"]:
        (output / path).chmod(0o444)
    for path in reversed(sealed["directories"]):
        (output / path).chmod(0o555)
    result["sealed_membership"] = sealed
    return result
