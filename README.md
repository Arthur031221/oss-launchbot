# oss-launchbot

Prepare, schedule, and track open-source launch posts from a workspace of public repositories.

On September 30, 2026, one local run prepared **18 public projects and 107 queue jobs** from 18 launch kits.[^measure] The queue keeps existing dates when more projects are published. Live Reddit posting stays gated until approved API access, account eligibility, and a current community rule review are present.

[![CI](https://github.com/Arthur031221/oss-launchbot/actions/workflows/ci.yml/badge.svg)](https://github.com/Arthur031221/oss-launchbot/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Version](https://img.shields.io/badge/version-0.1.2-blue.svg)](CHANGELOG.md)

![Launch queue demonstration](demo/demo.gif)

## Why

Launch kits are easy to lose across repositories. Copying the same draft into every community risks duplicate promotion and local rule violations. A scheduled queue makes the work visible while preserving the difference between a prepared post and a confirmed publication.

## Install

```sh
python3 -m pip install git+https://github.com/Arthur031221/oss-launchbot.git
```

Python 3.11 or newer is required. The package has no runtime dependencies. A workspace must have `dashboard/status.json`, project READMEs, and `launch/<project>.md` files. Only projects marked `pushed` with a repository URL are imported.

## Quick start

```sh
oss-launchbot --workspace /path/to/workspace refresh
oss-launchbot --workspace /path/to/workspace --json run-due
```

The first command writes `.launchbot/campaigns.json`, `.launchbot/queue.json`, and one Markdown pack per project. Packs include Show HN, X, LinkedIn, Reddit, and Product Hunt material when the source kit provides it. The second checks due Reddit jobs without submitting. It reports held jobs when policy approval is absent. Generated files live outside this repository's tracked source.

## How it works

The parser extracts Show HN, X, LinkedIn, and Reddit drafts from existing launch kits. A README pitch becomes a Product Hunt description candidate. Short taglines can be curated in `launch/product-hunt-taglines.json`. The queue gives time-sensitive projects from the workspace launch plan priority, spaces project windows by two weekdays at 10:00 US Eastern, and preserves old due dates across refreshes. Hacker News and Product Hunt jobs are marked `manual_submission` because their public APIs do not provide a general self-service post creation path. X and LinkedIn are also marked manual because no accounts are connected. Reddit uses its approved OAuth API only when all local gates pass.

| Workflow | What it does | What it leaves to the owner |
| --- | --- | --- |
| oss-launchbot | Imports kits, schedules jobs, blocks known incompatible communities, and records Reddit attempts | Supplies legitimate platform access and reviews current community rules |
| A spreadsheet | Tracks dates and links | Copies drafts, applies rules, and records outcomes by hand |
| Buffer or similar schedulers | Schedules supported social accounts | Does not replace Hacker News and Product Hunt submission rules or Reddit API approval |

## Commands

`refresh` regenerates campaigns and packs, then merges new projects into the existing queue. `run-due` checks due Reddit jobs. Add `--live` only after Reddit has approved Data API access and the account is eligible. Both commands accept global `--workspace`, `--output`, and `--json` options before the subcommand. The default output directory is `<workspace>/.launchbot`.

For live Reddit submission, create `<workspace>/.launchbot/policy.json` from `policy.example.json`. Set `allows_project_post` only after checking the current subreddit rules. Set `original_content_ok` only when the post satisfies the community's original-content requirements. The review date must be within seven days. Then provide `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_REFRESH_TOKEN`, `REDDIT_USERNAME`, `REDDIT_API_APPROVED=1`, and `REDDIT_ACCOUNT_ELIGIBLE=1` to the scheduled process. Do not put tokens in the policy file, launchd plist, or repository. A confirmed or uncertain Reddit attempt is never retried automatically. The ledger also enforces seven days between project promotions.

On macOS, clone this repository and run `python3 scripts/install_launchd.py --workspace /path/to/workspace` from the clone. It installs a 15-minute launchd cycle. Each cycle refreshes the queue and checks due Reddit jobs. macOS may deny launchd access to a workspace on Desktop, so the installer copies published launch materials to `~/Library/Application Support/oss-launchbot/workspace`. A detached `screen` session syncs new public projects into that mirror every 15 minutes while the Mac remains on. The mirror keeps the posting ledger and queue. Without approved access or policy entries the cycle only prepares materials and records held status. If approved Reddit credentials become available, put the six environment exports in `~/.config/oss-launchbot/reddit.env` with permission mode `600`. This private file is read by the cycle script and is never committed.

## Limits and FAQ

**Does this create social accounts?** No. Reddit, Hacker News, and Product Hunt require a real account and their own access or onboarding steps. This tool does not bypass them.

**Does this publish to Hacker News, Product Hunt, X, or LinkedIn?** No. It prepares title, URL, and text in `.launchbot/packs/`. Submit those through the platforms' web interfaces when the maintainer can answer comments or connect an approved account workflow.

**Can it post to any subreddit?** No. `r/programming` and `r/opensource` are blocked due to current rules affecting these drafts. Other communities require a recent explicit review and approved Reddit API access. The rule file is deliberately not auto-approved.

**Does it optimize for votes?** No. It does not request votes, cross-post the same text, or create accounts. Good timing and clear technical detail can help readers evaluate a project, but stars and front-page placement cannot be guaranteed.

Platform references: [Reddit Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy), [Reddit API](https://www.reddit.com/dev/api/), [Show HN guidelines](https://news.ycombinator.com/showhn.html), [Hacker News API](https://github.com/HackerNews/API), [Product Hunt API](https://api.producthunt.com/v2/docs), and [Product Hunt posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product).

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under MIT. Copyright 2026 Arthur.

[^measure]: Run `python3 -m oss_launchbot.cli --workspace /Users/arthur/Desktop/oss-localmac --json refresh` against the local workspace snapshot on September 30, 2026. Count the `campaigns` array and `jobs` array in `.launchbot/campaigns.json` and `.launchbot/queue.json`. The count changes as repositories are published.
