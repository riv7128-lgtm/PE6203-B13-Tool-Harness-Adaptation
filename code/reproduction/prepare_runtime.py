"""Rebase the frozen live pilot into a chosen root; no servers/models are launched.

Use --runtime-archive for the optional separately distributed archive. Without it,
--download reconstructs the pinned bundled dependency closure by public ZIP ranges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
COMMIT = "888c779a0fe735f612ca62bdd1fdd7c9e6bf8701"
DATASET_REVISION = "162e3ffbea1717ac8a20fe9b26465e29117229e4"
REPOSITORY = "https://github.com/Octobrist/MCPEvol-Bench.git"
ENTRIES = {
    "math-mcp": "math-mcp/dist/index.js",
    "mcp-ai-agent-guidelines": "mcp-ai-agent-guidelines/dist/index.js",
    "time-mcp": "time-mcp/dist/index.js",
    "@umengfe/mcp-server-chart": "@umengfe/mcp-server-chart/build/index.js",
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def runtime_fingerprints(extracted):
    result = {}
    for version in ("original", "iter3", "iter5"):
        base = extracted / version
        if not base.is_dir():
            raise FileNotFoundError(base)
        files = []
        # Match the published POSIX manifest order on case-insensitive Windows.
        for path in sorted(base.rglob("*"), key=lambda p: p.relative_to(base).parts):
            if path.is_symlink():
                raise ValueError("Runtime symlinks are not accepted: " + str(path))
            if path.is_file():
                files.append([path.relative_to(base).as_posix(), path.stat().st_size,
                              hashlib.sha256(path.read_bytes()).hexdigest()])
        result[version] = {
            "file_count": len(files), "total_bytes": sum(row[1] for row in files),
            "tree_sha256": hashlib.sha256(json.dumps(files, ensure_ascii=False,
                                                      separators=(",", ":")).encode()).hexdigest(),
        }
    return result


def extract_runtime(archive, destination):
    """Accept only regular files/dirs below extracted/<pinned-version>/... ."""
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive path: " + member.name)
            # macOS BSD tar adds AppleDouble resource-fork metadata, which is
            # outside the frozen official file tree and is never materialized.
            if path.name.startswith("._"):
                continue
            parts = path.parts
            if not parts or parts[0] != "extracted":
                raise ValueError("Expected extracted/ archive prefix: " + member.name)
            if len(parts) == 1 and member.isdir():
                continue
            if len(parts) < 2 or parts[1] not in ("original", "iter3", "iter5"):
                raise ValueError("Unexpected runtime version: " + member.name)
            target = destination.joinpath(*parts[1:])
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or any(p.is_symlink() for p in target.parents):
                    raise ValueError("Symlink destination is not accepted")
                stream = bundle.extractfile(member)
                if stream is None:
                    raise ValueError("Unreadable archive member")
                with stream, target.open("wb") as out:
                    shutil.copyfileobj(stream, out)
            else:
                raise ValueError("Archive links/devices are not accepted: " + member.name)


def verify_repo(repo, clone=False):
    if not repo.exists():
        if not clone:
            raise FileNotFoundError("Pinned benchmark missing; pass --clone-official: " + str(repo))
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", REPOSITORY, str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "--detach", COMMIT], check=True)
    actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise ValueError("Benchmark checkout does not match the frozen commit")
    subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--"], check=True)
    untracked = subprocess.check_output(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"], text=True)
    if any("__pycache__" not in Path(path).parts and not path.endswith(".pyc")
           for path in untracked.splitlines()):
        raise ValueError("Benchmark checkout contains untracked source files")


def prepare(root, node, python, repo):
    servers = root / "work/live_servers"
    runtime = root / "work/live_runtime"
    layers = [repo / "src/custom/data/mutation" / Path(*(["HYBRID"] * depth)) / "evolution.json"
              for depth in range(1, 5)]
    for path in layers:
        if not path.is_file():
            raise FileNotFoundError(path)
    for stage, version in (("early", "original"), ("middle", "iter3"), ("late", "iter5")):
        sandbox = runtime / stage / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        entries = {}
        for name, relative in ENTRIES.items():
            entrypoint = servers / "extracted" / version / "node_modules" / relative
            if not entrypoint.is_file():
                raise FileNotFoundError(entrypoint)
            entries[name] = {"command": str(node), "args": [str(entrypoint)],
                             "cwd": str(sandbox), "env": {"NO_COLOR": "1"},
                             "official_server_id": name,
                             "source_provenance": {"dataset": "anonymous2233/evol-servers",
                                 "dataset_revision": DATASET_REVISION,
                                 "archive": version + "_servers.zip",
                                 "entrypoint": "node_modules/" + relative,
                                 "entrypoint_sha256": hashlib.sha256(entrypoint.read_bytes()).hexdigest()}}
        time_exe = python.parent / ("mcp-server-time.exe" if os.name == "nt" else "mcp-server-time")
        if not time_exe.is_file():
            raise FileNotFoundError("Install requirements-live.lock.txt into the specified Python environment: " + str(time_exe))
        entries["time"] = {"command": str(time_exe), "args": ["--local-timezone=America/New_York"],
                           "cwd": str(sandbox), "env": {}, "official_server_id": "time",
                           "source_provenance": {"distribution": "mcp-server-time", "frozen_version": "2026.1.26"}}
        write_json(runtime / (stage + "_proxy.json"), {
            "version": stage, "stage": stage.title(), "archive_version": version,
            "task_ids": [133, 144, 235], "servers": entries,
            "official_evolution_files": [str(p) for p in layers],
            "dataset_revision": DATASET_REVISION})
    template = json.loads((HERE / "experiment_template.json").read_text())
    template.update({"workspace": str(runtime),
                     "codex_cli_log_dir": str(root / "results/live_reproduction_model_calls"),
                     "reset_command": [str(python), str(CODE / "scripts/reset_live_environment.py"),
                                       "--endpoint", "{endpoint}"]})
    write_json(runtime / "experiment_config.json", template)
    manifest = {"status": "PREPARED_NOT_LAUNCHED", "root": str(root), "code": str(CODE),
                "repo": str(repo), "python": str(python), "node": str(node),
                "benchmark_commit": COMMIT, "dataset_revision": DATASET_REVISION,
                "runtime_tree_fingerprints": runtime_fingerprints(servers / "extracted"),
                "config": str(runtime / "experiment_config.json"),
                "prepared_tasks": str(CODE / "prepared_live"),
                "snapshots": str(runtime / "snapshots"),
                "results": str(root / "results/live_reproduction"),
                "note": "Paths are rebased to this root; original archived evidence is not overwritten. Rebased config paths change the protocol fingerprint."}
    write_json(runtime / "reproduction_manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--node", default=shutil.which("node"), type=Path)
    parser.add_argument("--python", default=Path(sys.executable), type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--clone-official", action="store_true")
    parser.add_argument("--runtime-archive", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--no-launch", action="store_true", help="Explicit confirmation of default: this script never launches servers or models")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.node is None:
        parser.error("Node executable missing; pass --node")
    node, python = args.node.expanduser().resolve(), args.python.expanduser().absolute()
    if not node.is_file() or not python.is_file():
        parser.error("Node and Python executables must exist")
    repo = (args.repo or root / "work/official/MCPEvol-Bench").resolve()
    verify_repo(repo, args.clone_official)
    servers = root / "work/live_servers"
    servers.mkdir(parents=True, exist_ok=True)
    if args.runtime_archive and args.download:
        parser.error("Choose either --runtime-archive or --download")
    if args.runtime_archive:
        extract_runtime(args.runtime_archive.resolve(), servers / "extracted")
    elif args.download:
        env = dict(os.environ, MCPEVOL_SERVER_ROOT=str(servers))
        for filename in ("index_remote_zips.py", "extract_runtime_closure.py"):
            subprocess.run([str(python), str(HERE / filename)], check=True, env=env)
    actual = runtime_fingerprints(servers / "extracted")
    expected = json.loads((HERE / "runtime_tree_fingerprints.json").read_text())["versions"]
    write_json(root / "results/runtime_fingerprint_check.json", {"actual": actual, "expected": expected, "match": actual == expected})
    if actual != expected:
        raise ValueError("Runtime content differs from the frozen pilot tree; no configuration emitted")
    result = prepare(root, node, python, repo)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
