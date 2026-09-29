"""Command line interface for launch preparation and guarded posting."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .campaign import merge_schedule, prepare
from .reddit import PostingError, publish


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=".launchbot-"
    ) as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        temporary = Path(stream.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _pack(item: dict[str, Any]) -> str:
    hn = item["show_hn"]
    ph = item["product_hunt"]
    lines = [
        f"# {item['project']} launch pack",
        "",
        f"Repository: {item['repo']}",
        "",
        "## Show HN",
        "",
        f"Title: {hn['title']}",
        f"URL: {item['repo']}",
        "",
        hn["first_comment"],
        "",
        "## Product Hunt",
        "",
        f"Name: {ph['name']}",
        f"Tagline candidate: {ph['tagline']}",
        f"URL: {ph['url']}",
        "",
    ]
    for draft in item["reddit"]:
        status = (
            "blocked by community rules"
            if draft["blocked"]
            else "requires approved API access and current community review"
        )
        lines.extend(
            [
                f"## Reddit r/{draft['subreddit']}",
                "",
                f"Status: {status}",
                f"Title: {draft['title']}",
                "",
                draft["body"],
                "",
            ]
        )
    lines.extend(
        [
            "## Submission status",
            "",
            "Show HN and Product Hunt require submission through their own web interfaces.",
            "Reddit API submission requires approved access, account eligibility, "
            "and current community review.",
            "",
        ]
    )
    return "\n".join(lines)


def refresh(workspace: Path, output: Path) -> dict[str, Any]:
    """Create launch packs and preserve existing queue dates."""
    result = prepare(workspace)
    existing = _read_json(output / "queue.json", {"jobs": []})
    jobs = merge_schedule(
        result["campaigns"], existing.get("jobs", []), datetime.now().astimezone()
    )
    _write_json(output / "campaigns.json", result)
    _write_json(
        output / "queue.json",
        {"schema_version": 1, "generated_at": result["generated_at"], "jobs": jobs},
    )
    packs = output / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    for item in result["campaigns"]:
        (packs / f"{item['project']}.md").write_text(_pack(item), encoding="utf-8")
    return {
        "published_projects": result["published_projects"],
        "prepared_projects": result["prepared_projects"],
        "missing_kits": result["missing_kits"],
        "queue_jobs": len(jobs),
        "output": str(output),
    }


def run_due(output: Path, *, live: bool) -> dict[str, Any]:
    """Attempt due Reddit jobs. No other platform is submitted by this command."""
    campaigns = _read_json(output / "campaigns.json", {}).get("campaigns", [])
    queue = _read_json(output / "queue.json", {}).get("jobs", [])
    by_project = {item["project"]: item for item in campaigns}
    now = datetime.now().astimezone()
    results = []
    for job in queue:
        if job["platform"] != "reddit" or job["status"] == "blocked":
            continue
        if datetime.fromisoformat(job["due_at"]) > now:
            continue
        item = by_project.get(job["project"])
        if item is None:
            continue
        draft = next(
            (
                draft
                for draft in item["reddit"]
                if draft["subreddit"].lower() == job["target"].lower()
            ),
            None,
        )
        if draft is None:
            continue
        try:
            outcome = publish(
                item["project"],
                draft["subreddit"],
                draft["title"],
                draft["body"],
                policy_path=output / "policy.json",
                state_path=output / "posts.json",
                live=live,
            )
        except PostingError as exc:
            results.append({"id": job["id"], "status": "held", "reason": str(exc)})
            continue
        results.append({"id": job["id"], **outcome})
        if live and outcome["status"] == "sent":
            job["status"] = "sent"
            job["url"] = outcome["url"]
            _write_json(output / "queue.json", {"schema_version": 1, "jobs": queue})
    result = {
        "checked_at": now.isoformat(timespec="seconds"),
        "live": live,
        "due_reddit_jobs": len(results),
        "results": results,
    }
    _write_json(output / "last_run.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and schedule open-source launch campaigns"
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("refresh", help="Prepare launch packs and update the persistent queue")
    due = subparsers.add_parser("run-due", help="Check due Reddit jobs and their safety gates")
    due.add_argument(
        "--live", action="store_true", help="Submit through approved Reddit API access"
    )
    args = parser.parse_args(argv)
    output = args.output or args.workspace / ".launchbot"
    try:
        if args.command == "refresh":
            result = refresh(args.workspace, output)
        else:
            result = run_due(output, live=args.live)
    except (OSError, ValueError, KeyError, PostingError) as exc:
        print(f"oss-launchbot: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if args.command == "refresh":
            count = result["prepared_projects"]
            total = result["published_projects"]
            print(f"Prepared {count} of {total} published projects")
            print(f"Queue: {result['queue_jobs']} jobs at {result['output']}")
        else:
            print(f"Checked {result['due_reddit_jobs']} due Reddit jobs")
            for item in result["results"]:
                print(f"{item['id']}: {item['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
