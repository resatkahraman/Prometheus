from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "desktop" / "src-tauri" / "binaries"
NAME = "prometheus-core-x86_64-pc-windows-msvc"


def python_with_pyinstaller() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT.parent / "Prometheus" / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.is_file():
            probe = subprocess.run(
                [str(candidate), "-c", "import PyInstaller"],
                cwd=ROOT,
                capture_output=True,
            )
            if probe.returncode == 0:
                return str(candidate)
    pyinstaller = shutil.which("pyinstaller")
    if pyinstaller:
        return pyinstaller
    raise RuntimeError("PyInstaller is required to build the Core sidecar.")

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    python = python_with_pyinstaller()
    command = [python, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole", "--name", NAME, "--paths", str(ROOT), "--add-data", f"{ROOT / 'config' / 'skill_manifests.json'};config", "--distpath", str(OUTPUT_DIR), "--workpath", str(ROOT / "build" / "desktop-core-sidecar"), "--specpath", str(ROOT / "build" / "desktop-core-sidecar"), str(ROOT / "app" / "desktop_server.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    artifact = OUTPUT_DIR / f"{NAME}.exe"
    if not artifact.is_file() or artifact.stat().st_size == 0:
        raise RuntimeError("Core sidecar was not generated.")
    print(f"Core sidecar ready: {artifact.name} ({artifact.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
