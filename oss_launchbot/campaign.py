"""Read published repositories and their existing launch kits."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BLOCKED_SUBREDDITS = {
    "programming": "Rules prohibit LLM-written content and simple project promotion",
    "opensource": "Rules prohibit AI-generated posts",
}
EASTERN = ZoneInfo("America/New_York")
PRIORITY_PROJECTS = (
    "modelshift",
    "cliffhanger",
    "agentleaks",
    "slopblock",
    "songforge",
    "snipmd",
    "llm-doctor",
    "inference-visually",
    "shiftgear",
)


def inventory(workspace: Path) -> list[dict[str, Any]]:
    """Return published projects and launch-kit availability from the dashboard."""
    data = json.loads((workspace / "dashboard" / "status.json").read_text())
    projects = []
    for item in data["projects"]:
        if item.get("stage") != "pushed" or not item.get("repo"):
            continue
        kit = workspace / "launch" / f"{item['name']}.md"
        projects.append(
            {
                "project": item["name"],
                "repo": item["repo"],
                "kit": str(kit),
                "kit_exists": kit.is_file(),
            }
        )
    return sorted(projects, key=lambda item: item["project"])


def _section(text: str, heading: str) -> str:
    match = re.search(rf"(?im)^##\s+{heading}[^\n]*\n", text)
    if match is None:
        return ""
    following = re.search(r"(?m)^##\s+", text[match.end() :])
    end = match.end() + following.start() if following else len(text)
    return text[match.end() : end].strip()


def _field(block: str, label: str) -> str:
    match = re.search(rf"(?im)^{label}[^:\n]*:\s*([^\n]*)", block)
    if match is None:
        return ""
    inline = match.group(1).strip()
    if inline:
        return inline
    rest = block[match.end() :].lstrip("\n")
    return rest.splitlines()[0].strip() if rest else ""


def _first_comment(block: str) -> str:
    match = re.search(r"(?im)^First comment[^:\n]*:\s*", block)
    if match is None:
        return ""
    remainder = block[match.end() :]
    if remainder.startswith("\n"):
        remainder = remainder.lstrip("\n")
    stop = re.search(r"(?m)^###?\s+|^Posting note:|^Check \[Show HN", remainder)
    if stop:
        remainder = remainder[: stop.start()]
    return "\n".join(line.removeprefix("> ") for line in remainder.strip().splitlines()).strip()


def _reddit_drafts(block: str) -> list[dict[str, str]]:
    drafts: list[dict[str, str]] = []
    matches = list(re.finditer(r"(?im)^###\s+r/([A-Za-z0-9_]+)[^\n]*\n", block))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        content = block[match.end() : end].strip()
        title = _field(content, "Title")
        body_match = re.search(r"(?im)^Body[^:\n]*:\s*", content)
        body = content[body_match.end() :].strip() if body_match else ""
        body = re.sub(r"(?m)^Posting note:.*$", "", body).strip()
        subreddit = match.group(1)
        if title and body:
            drafts.append(
                {
                    "subreddit": subreddit,
                    "title": title,
                    "body": body,
                    "blocked": BLOCKED_SUBREDDITS.get(subreddit.lower(), ""),
                }
            )
    return drafts


def _readme_pitch(workspace: Path, project: str) -> str:
    readme = workspace / project / "README.md"
    if not readme.is_file():
        return ""
    lines = readme.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "[", "!", "<")):
            return re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", stripped)[:260]
    return ""


def _tagline(text: str, pitch: str) -> str:
    match = re.search(r"(?im)^One-liner:\s*(.+)$", text)
    candidate = match.group(1) if match else pitch
    candidate = re.sub(r"`([^`]+)`|\*\*([^*]+)\*\*", lambda m: m.group(1) or m.group(2), candidate)
    candidate = candidate.split(". ", 1)[0].strip().rstrip(".")
    if len(candidate) <= 60:
        return candidate
    return candidate[:61].rsplit(" ", 1)[0].rstrip(" ,:;-")


def campaign(workspace: Path, item: dict[str, Any]) -> dict[str, Any]:
    """Extract platform-specific drafts without generating new claims."""
    text = Path(item["kit"]).read_text(encoding="utf-8")
    show_hn = _section(text, "Show HN")
    reddit = _section(text, "Reddit")
    pitch = _readme_pitch(workspace, item["project"])
    override_file = workspace / "launch" / "product-hunt-taglines.json"
    overrides = (
        json.loads(override_file.read_text(encoding="utf-8")) if override_file.exists() else {}
    )
    override = overrides.get(item["project"], "")
    tagline = (
        override if isinstance(override, str) and 0 < len(override) <= 60 else _tagline(text, pitch)
    )
    return {
        "project": item["project"],
        "repo": item["repo"],
        "show_hn": {"title": _field(show_hn, "Title"), "first_comment": _first_comment(show_hn)},
        "reddit": _reddit_drafts(reddit),
        "product_hunt": {
            "name": item["project"],
            "tagline": tagline,
            "description": pitch,
            "url": item["repo"],
        },
    }


def prepare(workspace: Path) -> dict[str, Any]:
    found = inventory(workspace)
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "published_projects": len(found),
        "prepared_projects": sum(item["kit_exists"] for item in found),
        "missing_kits": [item["project"] for item in found if not item["kit_exists"]],
        "campaigns": [campaign(workspace, item) for item in found if item["kit_exists"]],
    }


def schedule(campaigns: list[dict[str, Any]], start: datetime) -> list[dict[str, Any]]:
    """Space projects by two weekdays, never auto-submit manual platforms."""
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    local = start.astimezone(EASTERN).replace(hour=10, minute=0, second=0, microsecond=0)
    if local <= start.astimezone(EASTERN):
        local += timedelta(days=1)
    jobs: list[dict[str, Any]] = []
    ordered = sorted(
        campaigns,
        key=lambda item: (
            PRIORITY_PROJECTS.index(item["project"])
            if item["project"] in PRIORITY_PROJECTS
            else len(PRIORITY_PROJECTS),
            item["project"],
        ),
    )
    for item in ordered:
        while local.weekday() >= 5:
            local += timedelta(days=1)
        jobs.append(
            {
                "id": f"{item['project']}:show_hn",
                "project": item["project"],
                "platform": "show_hn",
                "due_at": local.isoformat(),
                "status": "manual_submission",
            }
        )
        jobs.append(
            {
                "id": f"{item['project']}:product_hunt",
                "project": item["project"],
                "platform": "product_hunt",
                "due_at": local.isoformat(),
                "status": "manual_submission",
            }
        )
        for draft in item["reddit"]:
            jobs.append(
                {
                    "id": f"{item['project']}:reddit:{draft['subreddit'].lower()}",
                    "project": item["project"],
                    "platform": "reddit",
                    "target": draft["subreddit"],
                    "due_at": local.isoformat(),
                    "status": "blocked" if draft["blocked"] else "awaiting_access_and_rules",
                    "reason": draft["blocked"],
                }
            )
        local += timedelta(days=2)
    return jobs


def merge_schedule(
    campaigns: list[dict[str, Any]], existing: list[dict[str, Any]], start: datetime
) -> list[dict[str, Any]]:
    """Keep previous due dates and add newly published projects at the end."""
    known = {job["id"] for job in existing}
    projects = {job["project"] for job in existing}
    new_campaigns = [item for item in campaigns if item["project"] not in projects]
    if not new_campaigns:
        return existing
    last = max((datetime.fromisoformat(job["due_at"]) for job in existing), default=start)
    additions = schedule(new_campaigns, max(start, last))
    return existing + [job for job in additions if job["id"] not in known]
