import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from oss_launchbot.campaign import campaign, merge_schedule, prepare, schedule
from oss_launchbot.cli import refresh


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "dashboard").mkdir()
        (self.root / "launch").mkdir()
        (self.root / "sample").mkdir()
        (self.root / "dashboard" / "status.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "sample",
                            "stage": "pushed",
                            "repo": "https://github.com/Arthur031221/sample",
                        },
                        {"name": "unfinished", "stage": "building", "repo": ""},
                    ]
                }
            )
        )
        (self.root / "sample" / "README.md").write_text("# Sample\n\nChecks a sample.\n")
        (self.root / "launch" / "sample.md").write_text(
            "# Launch\n\n## Show HN draft\n\nTitle: Show HN: sample\n\n"
            "First comment:\n\n> It checks a sample.\n\nPosting note: Do not paste this.\n\n"
            "## Reddit drafts\n\n### r/examplecommunity\n\nTitle: Sample check\n\n"
            "Body: A useful example. Repo: https://github.com/Arthur031221/sample\n"
        )

    def test_prepare_extracts_only_published_projects(self):
        result = prepare(self.root)
        self.assertEqual(result["published_projects"], 1)
        item = result["campaigns"][0]
        self.assertEqual(item["show_hn"]["first_comment"], "It checks a sample.")
        self.assertEqual(item["reddit"][0]["subreddit"], "examplecommunity")
        self.assertEqual(item["product_hunt"]["tagline"], "Checks a sample.")

    def test_schedule_is_spaced_and_persistent(self):
        item = campaign(
            self.root,
            {
                "project": "sample",
                "repo": "https://github.com/Arthur031221/sample",
                "kit": str(self.root / "launch" / "sample.md"),
            },
        )
        start = datetime(2026, 9, 29, 9, tzinfo=ZoneInfo("America/New_York"))
        jobs = schedule([item], start)
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["status"], "manual_submission")
        self.assertEqual(jobs[2]["status"], "awaiting_access_and_rules")
        self.assertEqual(merge_schedule([item], jobs, start), jobs)
        summary = refresh(self.root, self.root / "out")
        self.assertEqual(summary["queue_jobs"], 3)
        first = json.loads((self.root / "out" / "queue.json").read_text())
        refresh(self.root, self.root / "out")
        second = json.loads((self.root / "out" / "queue.json").read_text())
        self.assertEqual(first["jobs"], second["jobs"])
        self.assertTrue((self.root / "out" / "packs" / "sample.md").exists())


if __name__ == "__main__":
    unittest.main()
