"""Launch the prepared localhost proxies and execute a new 27-cell pilot.

This explicitly invokes the configured logged-in Codex CLI for real inference and
judging. It does not access credentials or overwrite the archived delivery logs.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    manifest = json.loads((root / "work/live_runtime/reproduction_manifest.json").read_text())
    code, python, repo = (Path(manifest[k]) for k in ("code", "python", "repo"))
    runtime = root / "work/live_runtime"
    snapshots = Path(manifest["snapshots"])
    processes, logs = [], []
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def run(arguments):
        subprocess.run([str(python), "-m", "harness_adapt"] + arguments, cwd=code, check=True)

    try:
        for offset, stage in enumerate(("early", "middle", "late")):
            port = 3050 + offset
            # An occupied endpoint must not be silently reused from another run.
            import socket
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(f"Port {port} is already occupied; stop the existing service") from exc
            log = (runtime / (stage + "_proxy.log")).open("w")
            logs.append(log)
            processes.append(subprocess.Popen([str(python), str(code / "scripts/stdio_http_proxy.py"),
                                               "--config", str(runtime / (stage + "_proxy.json")),
                                               "--port", str(port)], cwd=code, stdout=log, stderr=log))
        for offset, stage in enumerate(("early", "middle", "late")):
            port = 3050 + offset
            deadline = time.monotonic() + 150
            while True:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Proxy exited; inspect the stage proxy logs")
                try:
                    with local_http.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        if json.loads(response.read())["status"] == "ready":
                            break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Proxy readiness timed out")
                    time.sleep(1)
            run(["capture", "--url", f"http://127.0.0.1:{port}/mcp/", "--out", str(snapshots / (stage + ".json"))])
        config = str(runtime / "experiment_config.json")
        run(["preflight", "--config", config, "--repo", str(repo), "--snapshots", str(snapshots),
             "--out", str(runtime / "preflight.json")])
        run(["run-official", "--config", config, "--repo", str(repo),
             "--prepared", manifest["prepared_tasks"], "--snapshots", str(snapshots), "--out", manifest["results"]])
        output = Path(manifest["results"])
        subprocess.run([str(python), str(code / "scripts/analyze_results.py"), "official",
                        "--manifest", str(output / "run_manifest.json"), "--records", str(output / "records.json"),
                        "--output", str(output / "summary")], cwd=code, check=True)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
