from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "desktop" / "src-tauri" / "binaries" / "prometheus-core-x86_64-pc-windows-msvc.exe"


def main() -> None:
    with socket.socket() as dummy:
        dummy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        dummy.bind(("127.0.0.1", 8765))
        dummy.listen(1)
        with tempfile.TemporaryDirectory(prefix="prometheus-core-collision-", ignore_cleanup_errors=True) as cwd:
            env = os.environ.copy()
            env["PROMETHEUS_CORE_PORT"] = "18766"
            env["PROMETHEUS_DESKTOP_CORE_PORT"] = "18766"
            process = subprocess.Popen([str(SIDECAR)], cwd=cwd, env=env, creationflags=0x08000000)
            try:
                deadline = time.time() + 15
                while time.time() < deadline:
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:18766/v1/health", timeout=2) as response:
                            if response.status == 200:
                                print("Occupied default port smoke PASS: 8765 occupied, Core READY on 18766")
                                return
                    except Exception:
                        if process.poll() is not None:
                            raise RuntimeError(f"Core sidecar exited early: {process.returncode}")
                        time.sleep(0.25)
                raise RuntimeError("Occupied default port smoke timed out.")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
