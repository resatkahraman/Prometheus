import subprocess
raise SystemExit(subprocess.run('node --version', shell=True, check=False).returncode)
