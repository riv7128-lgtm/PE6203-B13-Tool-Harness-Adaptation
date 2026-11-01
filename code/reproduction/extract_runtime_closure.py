"""Extract selected official Node packages and their bundled dependency closure.

Downloads coalesced ZIP ranges and verifies every extracted file's ZIP CRC.
Downloaded code is never executed by this script.
"""
from pathlib import Path, PurePosixPath
import concurrent.futures
import hashlib
import json
import shutil
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_remote_zips import ROOT, read_range

PRIMARIES = ["@guanxiong/mcp-server-time", "math-mcp", "mcp-ai-agent-guidelines", "time-mcp", "@umengfe/mcp-server-chart"]
CACHE = {}
RECORDS = ROOT / "package_records"
RECORDS.mkdir(exist_ok=True)
for record_file in RECORDS.glob("*.json"):
    record = json.loads(record_file.read_text())
    CACHE[(record["prefix"], record["signature"])] = ROOT / "extracted" / record["version"] / record["prefix"]


def relative_file(entry, prefix):
    return entry["name"][len(prefix) + 1:]


def extract_package(version, prefix, entries):
    selected = [e for e in entries if e["name"].startswith(prefix + "/") and not e["name"].endswith("/")]
    selected.sort(key=lambda e: e["local_header_offset"])
    signature = hashlib.sha256(json.dumps([(relative_file(e, prefix), e["crc32"], e["size"], e["compressed_size"]) for e in selected], separators=(",", ":")).encode()).hexdigest()
    target = ROOT / "extracted" / version / prefix
    cache_key = (prefix, signature)
    if cache_key in CACHE:
        if CACHE[cache_key] != target:
            shutil.copytree(CACHE[cache_key], target, dirs_exist_ok=True, symlinks=False)
        return {"version": version, "prefix": prefix, "signature": signature, "file_count": len(selected), "copied_identical_archive_records_from": str(CACHE[cache_key]), "downloaded_bytes": 0, "file_hashes": []}
    if not selected:
        raise ValueError(f"No official package {prefix} in {version}")
    start = selected[0]["local_header_offset"]
    last = selected[-1]
    header = read_range(f"{version}_servers.zip", last["local_header_offset"], 30)
    f = struct.unpack("<4s5H3L2H", header)
    end = last["local_header_offset"] + 30 + f[-2] + f[-1] + last["compressed_size"]
    if end - start > 32 * 1024 * 1024:
        raise ValueError(f"Package span exceeds limit: {prefix} {end-start}")
    data = read_range(f"{version}_servers.zip", start, end - start)
    hashes, skipped = [], []
    for entry in selected:
        path = PurePosixPath(entry["name"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive path")
        if ((entry["external_attributes"] >> 16) & 0o170000) == 0o120000:
            skipped.append(entry["name"])
            continue
        position = entry["local_header_offset"] - start
        if data[position:position+4] != b"PK\x03\x04":
            raise ValueError("Bad local header")
        h = struct.unpack_from("<4s5H3L2H", data, position)
        body_start = position + 30 + h[-2] + h[-1]
        compressed = data[body_start:body_start+entry["compressed_size"]]
        if entry["compression"] == 0:
            body = compressed
        elif entry["compression"] == 8:
            body = zlib.decompress(compressed, -15)
        else:
            raise ValueError("Unsupported ZIP compression")
        if len(body) != entry["size"] or (zlib.crc32(body) & 0xffffffff) != entry["crc32"]:
            raise ValueError("CRC or size mismatch")
        out = ROOT / "extracted" / version / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(body)
        hashes.append({"name": entry["name"], "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)})
    return {"version": version, "prefix": prefix, "signature": signature, "file_count": len(selected), "downloaded_bytes": len(data)+30, "file_hashes": hashes, "skipped_symlinks": skipped}


def resolve_dependency(prefix, dependency, names):
    current = PurePosixPath(prefix)
    for folder in [current] + list(current.parents):
        candidate = str(folder / "node_modules" / dependency)
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate + "/package.json" in names:
            return candidate
    raise ValueError(f"Unresolved bundled dependency {dependency} from {prefix}")


def closure(version, label=""):
    entries = json.loads((ROOT / f"{version}_index.json").read_text())["entries"]
    names = {e["name"] for e in entries}
    pending = {"node_modules/" + p for p in PRIMARIES}
    completed, records, missing = set(), [], []
    while pending:
        wave = sorted(pending - completed)
        pending = set()
        if not wave:
            break
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            extracted = list(pool.map(lambda prefix: extract_package(version, prefix, entries), wave))
        for record in extracted:
            prefix = record["prefix"]
            completed.add(prefix)
            records.append(record)
            target = ROOT / "extracted" / version / prefix
            CACHE[(prefix, record["signature"])] = target
            package = json.loads((target / "package.json").read_text())
            record["package_name"] = package.get("name")
            record["package_version"] = package.get("version")
            record["dependencies"] = package.get("dependencies", {})
            (RECORDS / f"{version}_{hashlib.sha256(prefix.encode()).hexdigest()[:20]}.json").write_text(json.dumps(record, indent=2))
            for dependency in package.get("dependencies", {}):
                try:
                    resolved = resolve_dependency(prefix, dependency, names)
                    if resolved not in completed:
                        pending.add(resolved)
                except ValueError as exc:
                    missing.append(str(exc))
            print(json.dumps({"version": version, "package": package.get("name"), "package_version": package.get("version"), "files": record["file_count"], "downloaded_bytes": record["downloaded_bytes"]}), flush=True)
        suffix = "_" + label if label else ""
        (ROOT / f"{version}{suffix}_closure_manifest.json").write_text(json.dumps({"status": "EXTRACTION_IN_PROGRESS", "packages": records, "missing": missing}, indent=2))
    result = {"version": version, "status": "EXTRACTED_NOT_EXECUTED" if not missing else "DEPENDENCIES_MISSING", "primary_packages": PRIMARIES, "packages": records, "missing": missing, "package_count": len(records), "downloaded_bytes": sum(x["downloaded_bytes"] for x in records)}
    suffix = "_" + label if label else ""
    (ROOT / f"{version}{suffix}_closure_manifest.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    summaries = []
    for version in ("original", "iter3", "iter5"):
        summary = closure(version)
        summaries.append({k:v for k,v in summary.items() if k != "packages"})
        print(json.dumps(summaries[-1]), flush=True)
    (ROOT / "closure_summary.json").write_text(json.dumps(summaries, indent=2))
