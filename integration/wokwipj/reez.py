"""Run the Rust monitor alongside the existing C monitor.

Usage: uv run --locked python tools/reez.py build|run|demo|test [arguments]
The Rust workspace and Cargo cache live in ../reez.
"""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
reez = Path(os.environ.get("REEZ_ROOT", root.parent / "reez"))
action = sys.argv[1] if len(sys.argv) > 1 else "run"
extra = sys.argv[2:]
env = dict(os.environ)
env.pop("VIRTUAL_ENV", None)
env["WOKWI_PROJECT"] = str(root)
binary = reez / "target/debug/reez-monitor"
if action == "build":
    project = Path(env.get("EEZ_PROJECT", "/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project"))
    generated = project.parent / "rust-src"
    if (generated / ".reez-manifest.json").exists():
        env["EEZ_RUST_SRC"] = str(generated)
    command = ["uv", "run", "--locked", "cargo", "build", "--locked", "--workspace", *extra]
    cwd = reez
elif action == "test":
    env["MONITOR_PC"] = str(binary)
    env["MONITOR_CORE"] = "rust"
    command = ["uv", "run", "--locked", "pytest", *extra]
    cwd = root
elif action == "demo":
    command = [str(reez / "target/debug/reez-firmware-host"), *extra]
    cwd = root
elif action == "run":
    command = [str(binary), *extra]
    cwd = root
else:
    raise SystemExit("expected build, run, demo, or test")
raise SystemExit(subprocess.run(command, cwd=cwd, env=env).returncode)
