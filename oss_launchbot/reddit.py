"""Approved Reddit API posting with conservative idempotency rules."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import __version__
from .campaign import BLOCKED_SUBREDDITS


class PostingError(RuntimeError):
    """Posting could not be completed or verified."""


def _user_agent() -> str:
    return f"macos:oss-launchbot:{__version__} (by /u/{os.environ['REDDIT_USERNAME']})"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PostingError(f"Expected a JSON object in {path}")
    return value


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=".launchbot-"
    ) as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def check_policy(
    subreddit: str,
    policy: dict[str, Any],
    *,
    today: date | None = None,
) -> None:
    """Require a recent, explicit owner review of the target community."""
    target = subreddit.lower().removeprefix("r/")
    if target in BLOCKED_SUBREDDITS:
        raise PostingError(f"r/{target} is blocked: {BLOCKED_SUBREDDITS[target]}")
    entry = policy.get("subreddits", {}).get(target)
    if not isinstance(entry, dict) or entry.get("allows_project_post") is not True:
        raise PostingError(f"r/{target} needs an explicit allow decision in the policy file")
    try:
        checked = date.fromisoformat(entry["rules_checked_on"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PostingError(f"r/{target} needs a rules_checked_on date") from exc
    current = today or date.today()
    if checked > current or current - checked > timedelta(days=7):
        raise PostingError(f"r/{target} rules review is older than 7 days")
    if entry.get("original_content_ok") is not True:
        raise PostingError(f"r/{target} draft source has not been cleared for local rules")


def _request(url: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except (urllib.error.URLError, ValueError) as exc:
        raise PostingError(f"Reddit request failed: {type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise PostingError("Reddit returned a non-object response")
    return result


def _access_token() -> str:
    required = (
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_REFRESH_TOKEN",
        "REDDIT_USERNAME",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise PostingError("Missing environment variables: " + ", ".join(missing))
    credentials = f"{os.environ['REDDIT_CLIENT_ID']}:{os.environ['REDDIT_CLIENT_SECRET']}"
    basic = base64.b64encode(credentials.encode()).decode()
    result = _request(
        "https://www.reddit.com/api/v1/access_token",
        urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": os.environ["REDDIT_REFRESH_TOKEN"]}
        ).encode(),
        {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _user_agent(),
        },
    )
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        raise PostingError("Reddit did not issue an access token")
    return token


def _submit(subreddit: str, title: str, body: str, token: str) -> str:
    result = _request(
        "https://oauth.reddit.com/api/submit",
        urllib.parse.urlencode(
            {
                "api_type": "json",
                "kind": "self",
                "sr": subreddit.removeprefix("r/"),
                "title": title,
                "text": body,
                "resubmit": "false",
                "send_replies": "true",
                "raw_json": "1",
            }
        ).encode(),
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _user_agent(),
        },
    )
    response = result.get("json", {})
    errors = response.get("errors", []) if isinstance(response, dict) else []
    if errors:
        raise PostingError(f"Reddit rejected the post: {errors}")
    data = response.get("data", {}) if isinstance(response, dict) else {}
    url = data.get("url") if isinstance(data, dict) else None
    if not isinstance(url, str) or not url.startswith("https://www.reddit.com/"):
        raise PostingError("Reddit response did not confirm a post URL")
    return url


def publish(
    project: str,
    subreddit: str,
    title: str,
    body: str,
    *,
    policy_path: Path,
    state_path: Path,
    live: bool = False,
) -> dict[str, str]:
    """Dry-run by default. A live attempt is never retried automatically."""
    policy = _read_json(policy_path, {})
    check_policy(subreddit, policy)
    if not title or not body:
        raise PostingError("A title and body are required")
    if not live:
        return {"status": "dry_run", "project": project, "subreddit": subreddit}
    if os.environ.get("REDDIT_API_APPROVED") != "1":
        raise PostingError("Reddit API approval is required")
    if os.environ.get("REDDIT_ACCOUNT_ELIGIBLE") != "1":
        raise PostingError("Account participation and promotion ratio must be verified")
    state = _read_json(state_path, {"posts": {}})
    posts = state.setdefault("posts", {})
    if any(key.startswith(f"{project}:") for key in posts):
        raise PostingError("This project already has a Reddit attempt. Reconcile it manually")
    for previous in posts.values():
        if previous.get("status") != "sent":
            continue
        posted = date.fromisoformat(previous["date"])
        if date.today() - posted < timedelta(days=7):
            raise PostingError("Wait at least 7 days between project promotions")
    key = f"{project}:{subreddit.lower().removeprefix('r/')}"
    token = _access_token()
    posts[key] = {"status": "attempting", "date": date.today().isoformat()}
    _atomic_json(state_path, state)
    try:
        url = _submit(subreddit, title, body, token)
    except PostingError:
        posts[key]["status"] = "unknown"
        _atomic_json(state_path, state)
        raise
    posts[key] = {"status": "sent", "date": date.today().isoformat(), "url": url}
    _atomic_json(state_path, state)
    return {"status": "sent", "url": url, "project": project, "subreddit": subreddit}
