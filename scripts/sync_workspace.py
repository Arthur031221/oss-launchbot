"""Mirror published launch materials outside macOS protected Desktop folders."""

from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import time
from datetime import datetime
from pathlib import Path


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.sync")
    shutil.copy2(source, temporary)
    temporary.replace(target)


def sync(workspace: Path, mirror: Path) -> int:
    status = workspace / "dashboard" / "status.json"
    data = json.loads(status.read_text(encoding="utf-8"))
    copy_file(status, mirror / "dashboard" / "status.json")
    copy_file(
        workspace / "launch" / "product-hunt-taglines.json",
        mirror / "launch" / "product-hunt-taglines.json",
    )
    count = 0
    for item in data["projects"]:
        if item.get("stage") != "pushed" or not item.get("repo"):
            continue
        name = item["name"]
        if not isinstance(name, str) or Path(name).name != name:
            continue
        copy_file(workspace / "launch" / f"{name}.md", mirror / "launch" / f"{name}.md")
        copy_file(workspace / name / "README.md", mirror / name / "README.md")
        count += 1
    source_state = workspace / ".launchbot"
    mirror_state = mirror / ".launchbot"
    copy_file(source_state / "policy.json", mirror_state / "policy.json")
    for filename in ("campaigns.json", "queue.json", "last_run.json", "posts.json"):
        copy_file(mirror_state / filename, source_state / filename)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync published launch materials")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--mirror", type=Path, required=True)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    args.mirror.mkdir(parents=True, exist_ok=True)
    lock = (args.mirror / ".sync.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another workspace sync is already running", flush=True)
        return 1
    while True:
        try:
            count = sync(args.workspace, args.mirror)
            print(
                f"{datetime.now().isoformat(timespec='seconds')} synced {count} projects",
                flush=True,
            )
        except (OSError, ValueError, KeyError) as exc:
            print(f"{datetime.now().isoformat(timespec='seconds')} sync failed: {exc}", flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(900)


if __name__ == "__main__":
    raise SystemExit(main())
