"""Immediate sample cleanup tied to this run's declared volumes and verified manifest."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

SAMPLE_VOLUME = re.compile(r"layerfs-fsb-sample-[0-9a-f]{16}")
PAYLOAD_FOLDERS = ("graph-store", "census-store")
PAYLOAD_FILES = ("store.sqlite", "pristine-store.sqlite", "closed-overlay.sqlite", "footprint-typed.sqlite")
RULE = "sample-owned writable copies/containers/exported Stores removed after retained proof; closed fixture masters kept"


def say(**fields):
    print(json.dumps(fields), flush=True)


def docker_command(socket, protected, *arguments):
    if arguments[:2] == ("volume", "rm") and protected.intersection(arguments[2:]):
        raise ValueError("pre-existing protected volume; cleanup refused")
    result = subprocess.run(["docker", "--host", "unix://" + socket, *arguments],
                            capture_output=True, text=True, timeout=15)
    return result.returncode, result.stdout.strip(), result.stderr.strip()[-400:]


def tree_bytes(path):
    total = 0
    for folder, _, names in os.walk(path):
        for name in names:
            entry = Path(folder) / name
            if not entry.is_symlink():
                total += entry.stat().st_size
    return total


def remove_tree(path):
    for folder, names, _ in os.walk(path):
        os.chmod(folder, 0o700)
        for name in names:
            if not (Path(folder) / name).is_symlink():
                os.chmod(Path(folder) / name, 0o700)
    size = tree_bytes(path)
    shutil.rmtree(path)
    return size


def file_sha256(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def sample_volumes(sample):
    """Only explicit resources created by this sample, never referenced producer resources."""
    found = set()
    for claim in Path(sample).rglob("resource-claim.json"):
        value = json.loads(claim.read_text())
        volume = value.get("volume")
        if value.get("created_by_this_run") is True and isinstance(volume, str) and SAMPLE_VOLUME.fullmatch(volume):
            found.add(volume)
    return sorted(found)


def drop_test_copy(sample, socket, protected):
    """Check the sealed manifest, then remove the sample's volumes, their containers and exported Stores."""
    record = sample / "payload-cleanup.json"
    if record.exists() or not sample.is_dir():
        return None
    docker = lambda *args: docker_command(socket, protected, *args)
    removed = {"rule": RULE, "volumes": [], "containers": [], "manifest_check_before_removal": None,
               "removed_manifest_entries": {}, "bytes": {}}
    failures = []
    sealed = {}
    manifest = sample / "manifest.json"
    if manifest.exists():
        sealed = json.loads(manifest.read_text())["files"]
        wrong = [name for name, wanted in sealed.items()
                 if not (sample / name).is_file() or file_sha256(sample / name) != wanted]
        removed["manifest_check_before_removal"] = "PASS" if not wrong else "FAIL: " + ", ".join(wrong[:5])
    for volume in sample_volumes(sample):
        code, listed, error = docker("ps", "--all", "--quiet", "--no-trunc", "--filter", "volume=" + volume)
        if code:
            failures.append("list: " + error)
        for container in listed.split():
            docker("stop", "--time", "2", container)
            code, _, error = docker("rm", "--force", container)
            (failures if code else removed["containers"]).append(container + (": " + error if code else ""))
        code, known, _ = docker("volume", "ls", "--quiet", "--filter", "name=" + volume)
        if not code and volume in known.split():
            code, _, error = docker("volume", "rm", volume)
            if code:
                failures.append("volume " + volume + ": " + error)
            else:
                removed["volumes"].append(volume)
    for folder, names, _ in os.walk(sample):
        for name in [name for name in names if name in PAYLOAD_FOLDERS]:
            exported = Path(folder) / name
            relative = str(exported.relative_to(sample))
            for entry, wanted in sealed.items():
                if entry == relative or entry.startswith(relative + "/"):
                    removed["removed_manifest_entries"][entry] = wanted
            removed["bytes"][relative] = remove_tree(exported)
            names.remove(name)
    # The Store a sample itself built or exported (Init families keep it beside the receipt).
    for entry in sorted(sample.rglob("*")):
        if entry.is_file() and not entry.is_symlink() and entry.name.startswith(PAYLOAD_FILES):
            relative = str(entry.relative_to(sample))
            if relative in sealed:
                removed["removed_manifest_entries"][relative] = sealed[relative]
            removed["bytes"][relative] = entry.stat().st_size
            os.chmod(entry.parent, 0o700)
            entry.unlink()
    if failures:
        say(cleanup=sample.name, failed=failures)
        return None
    left = tree_bytes(sample)
    large = sorted(((entry.stat().st_size, str(entry.relative_to(sample))) for entry in sample.rglob("*")
                    if entry.is_file() and not entry.is_symlink() and entry.stat().st_size > 16 << 20), reverse=True)[:4]
    removed["left_bytes"], removed["left_large_files"] = left, large
    record.write_text(json.dumps(removed, indent=2) + "\n")
    return {"volumes": len(removed["volumes"]), "containers": len(removed["containers"]),
            "manifest": removed["manifest_check_before_removal"],
            "removed_mb": round(sum(removed["bytes"].values()) / 1e6, 1), "left_mb": round(left / 1e6, 1),
            **({"left_large": large} if large else {})}

