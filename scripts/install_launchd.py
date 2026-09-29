"""Install a local launchd agent for campaign refresh and gated Reddit submission."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import signal
import subprocess
import time
from pathlib import Path

from sync_workspace import copy_file, sync

LABEL = "com.arthur.oss-launchbot"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the oss-launchbot launchd agent")
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not (workspace / "dashboard" / "status.json").is_file():
        parser.error("workspace must contain dashboard/status.json")
    project = Path(__file__).resolve().parents[1]
    base = Path.home() / "Library" / "Application Support" / "oss-launchbot"
    runtime = base / "runtime"
    mirror = base / "workspace"
    package = runtime / "oss_launchbot"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(
        project / "oss_launchbot", package, ignore=shutil.ignore_patterns("__pycache__")
    )
    script = runtime / "scripts" / "launchbot-cycle.sh"
    copy_file(project / "scripts" / "launchbot-cycle.sh", script)
    sync(workspace, mirror)
    for filename in ("campaigns.json", "queue.json", "last_run.json", "policy.json", "posts.json"):
        copy_file(workspace / ".launchbot" / filename, mirror / ".launchbot" / filename)
    directory = Path.home() / "Library" / "LaunchAgents"
    directory.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / ".local" / "state" / "oss-launchbot"
    logs.mkdir(parents=True, exist_ok=True)
    target = directory / f"{LABEL}.plist"
    agent = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", str(script), str(mirror)],
        "RunAtLoad": True,
        "StartInterval": 900,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    target.write_bytes(plistlib.dumps(agent))
    domain = f"gui/{subprocess.check_output(['/usr/bin/id', '-u'], text=True).strip()}"
    subprocess.run(["/bin/launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(target)], check=True)
    screen = shutil.which("screen")
    if screen:
        match = str(project / "scripts" / "sync_workspace.py")
        processes = subprocess.run(
            ["/usr/bin/pgrep", "-f", match], capture_output=True, text=True
        ).stdout
        for line in processes.splitlines():
            pid = int(line)
            if pid != os.getpid():
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        time.sleep(0.2)
        subprocess.run([screen, "-wipe"], capture_output=True)
        subprocess.run(
            [
                screen,
                "-dmS",
                "oss-launchbot-sync",
                shutil.which("python3") or "/usr/bin/python3",
                str(project / "scripts" / "sync_workspace.py"),
                "--workspace",
                str(workspace),
                "--mirror",
                str(mirror),
                "--loop",
            ],
            check=True,
        )
    print(f"Installed {target}")
    print(f"Workspace mirror: {mirror}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
