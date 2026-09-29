"""Install a local launchd agent for campaign refresh and gated Reddit submission."""

from __future__ import annotations

import argparse
import plistlib
import subprocess
from pathlib import Path

LABEL = "com.arthur.oss-launchbot"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the oss-launchbot launchd agent")
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not (workspace / "dashboard" / "status.json").is_file():
        parser.error("workspace must contain dashboard/status.json")
    script = Path(__file__).resolve().with_name("launchbot-cycle.sh")
    directory = Path.home() / "Library" / "LaunchAgents"
    directory.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / ".local" / "state" / "oss-launchbot"
    logs.mkdir(parents=True, exist_ok=True)
    target = directory / f"{LABEL}.plist"
    agent = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", str(script), str(workspace)],
        "RunAtLoad": True,
        "StartInterval": 21600,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    target.write_bytes(plistlib.dumps(agent))
    domain = f"gui/{subprocess.check_output(['/usr/bin/id', '-u'], text=True).strip()}"
    subprocess.run(["/bin/launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(target)], check=True)
    print(f"Installed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
