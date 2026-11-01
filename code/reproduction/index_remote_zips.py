"""Read public ZIP directories and selected files without full archive transfer.

This tool only reads and extracts bytes. It never executes downloaded code.
"""
from pathlib import Path, PurePosixPath
import concurrent.futures
import hashlib
import json
import os
import struct
import time
import urllib.request
import urllib.error
import zlib

ROOT = Path(os.environ.get("MCPEVOL_SERVER_ROOT", str(Path(__file__).resolve().parent / "cache"))).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
METADATA = Path(__file__).resolve().parent
DATASET_REVISION = "162e3ffbea1717ac8a20fe9b26465e29117229e4"
TREE = json.loads((METADATA / "hf_tree_pinned.json").read_text())
PACKAGES = ("@guanxiong/mcp-server-time", "time-mcp", "math-mcp", "mcp-filesystem-server", "@modelcontextprotocol/server-filesystem", "mcp-tasks", "mcp-sequentialthinking-tools")


def read_range(filename, start, length):
    end = start + length - 1
    url = f"https://huggingface.co/datasets/anonymous2233/evol-servers/resolve/{DATASET_REVISION}/{filename}?download=true&range={start}-{end}"
    for attempt in range(5):
        request = urllib.request.Request(url + f"&attempt={attempt}", headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 206:
                    raise RuntimeError(f"Range request returned {response.status}; full body not downloaded")
                expected = f"bytes {start}-{end}/"
                if not response.headers.get("Content-Range", "").startswith(expected):
                    raise RuntimeError("Server returned a different byte range")
                payload = response.read(length + 1)
                if len(payload) != length:
                    raise RuntimeError("Truncated or oversized range response")
            return payload
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 4:
                raise
            time.sleep(min(0.5 * 2**attempt, 4))


def index_zip(item):
    filename, size = item["path"], item["size"]
    version = filename.removesuffix("_servers.zip")
    tail = read_range(filename, size - 131072, 131072)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("ZIP end record missing")
    fields = struct.unpack_from("<4s4H2LH", tail, eocd)
    central_size, central_start = fields[5], fields[6]
    print(json.dumps({"version": version, "archive_bytes": size, "directory_bytes": central_size}), flush=True)
    central = read_range(filename, central_start, central_size)
    provenance = json.loads((METADATA / "pinned_provenance.json").read_text())
    expected = next(x for x in provenance["files"] if x["path"] == filename)
    if size != expected["size"] or hashlib.sha256(central).hexdigest() != expected["central_directory_sha256"]:
        raise ValueError("Pinned archive directory integrity mismatch")
    (ROOT / f"{version}_central.bin").write_bytes(central)
    entries, position = [], 0
    while position < len(central):
        if central[position:position + 4] != b"PK\x01\x02":
            raise ValueError(f"Invalid central entry at {position}")
        f = struct.unpack_from("<4s6H3L5H2L", central, position)
        nlen, xlen, clen = f[10:13]
        raw_name = central[position + 46:position + 46 + nlen]
        name = raw_name.decode("utf-8" if f[3] & 0x800 else "cp437")
        entries.append({"name": name, "compression": f[4], "crc32": f[7], "compressed_size": f[8], "size": f[9], "local_header_offset": f[16], "external_attributes": f[15]})
        position += 46 + nlen + xlen + clen
    (ROOT / f"{version}_index.json").write_text(json.dumps({"filename": filename, "archive_size": size, "central_start": central_start, "central_size": central_size, "entries": entries}, separators=(",", ":")))
    selected = [e for e in entries if any(f"node_modules/{p}/" in e["name"] for p in PACKAGES)]
    summary = {"version": version, "filename": filename, "archive_size": size, "central_start": central_start, "central_size": central_size, "entry_count": len(entries), "directory_sha256": hashlib.sha256(central).hexdigest(), "selected_entries": selected}
    (ROOT / f"{version}_selected_index.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"version": version, "entry_count": len(entries), "selected_count": len(selected), "selected_compressed_bytes": sum(e["compressed_size"] for e in selected)}), flush=True)
    return summary


def extract_entry(version, entry):
    path = PurePosixPath(entry["name"])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe ZIP path")
    if ((entry["external_attributes"] >> 16) & 0o170000) == 0o120000:
        raise ValueError("Symlink extraction is not supported")
    if entry["name"].endswith("/"):
        return None
    filename = f"{version}_servers.zip"
    header = read_range(filename, entry["local_header_offset"], 30)
    if header[:4] != b"PK\x03\x04":
        raise ValueError("Invalid local ZIP header")
    fields = struct.unpack("<4s5H3L2H", header)
    offset = entry["local_header_offset"] + 30 + fields[-2] + fields[-1]
    compressed = read_range(filename, offset, entry["compressed_size"])
    if entry["compression"] == 0:
        data = compressed
    elif entry["compression"] == 8:
        data = zlib.decompress(compressed, -15)
    else:
        raise ValueError("Unsupported compression")
    if len(data) != entry["size"] or zlib.crc32(data) & 0xffffffff != entry["crc32"]:
        raise ValueError("ZIP entry size or CRC mismatch")
    target = ROOT / "extracted" / version / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"source": entry["name"], "path": str(target), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


if __name__ == "__main__":
    items = [x for x in TREE if x.get("path", "").endswith("_servers.zip")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(index_zip, items))
    (ROOT / "archive_summary.json").write_text(json.dumps(results, indent=2))
