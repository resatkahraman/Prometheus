from __future__ import annotations

import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "desktop" / "src-tauri" / "binaries" / "prometheus-core-x86_64-pc-windows-msvc.exe"

def main() -> None:
    if not SIDECAR.is_file():
        raise SystemExit("Core sidecar is missing.")
    with tempfile.TemporaryDirectory(prefix="prometheus-core-smoke-") as cwd:
        environment = os.environ.copy()
        environment["PROMETHEUS_DESKTOP_CORE_PORT"] = "18765"
        process = subprocess.Popen([str(SIDECAR)], cwd=cwd, env=environment, creationflags=0x08000000)
        try:
            deadline = time.time() + 15
            body = b""
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18765/v1/health", timeout=2) as response:
                        body = response.read(256)
                    break
                except Exception:
                    if process.poll() is not None:
                        raise RuntimeError(f"Core sidecar exited early: {process.returncode}")
                    time.sleep(0.25)
            if not body:
                raise RuntimeError("Core sidecar readiness timeout.")
            print(f"Core sidecar smoke PASS: {body.decode('utf-8', 'replace')}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

if __name__ == "__main__":
    main()
