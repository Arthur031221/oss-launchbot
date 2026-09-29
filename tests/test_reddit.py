import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from oss_launchbot.reddit import PostingError, check_policy, publish


class RedditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = self.root / "policy.json"
        self.state = self.root / "posts.json"
        self.policy.write_text(
            json.dumps(
                {
                    "subreddits": {
                        "examplecommunity": {
                            "allows_project_post": True,
                            "original_content_ok": True,
                            "rules_checked_on": date.today().isoformat(),
                        }
                    }
                }
            )
        )

    def test_blocks_prohibited_and_stale_communities(self):
        with self.assertRaisesRegex(PostingError, "blocked"):
            check_policy("r/programming", {})
        with self.assertRaisesRegex(PostingError, "older than 7 days"):
            check_policy(
                "examplecommunity",
                {
                    "subreddits": {
                        "examplecommunity": {
                            "allows_project_post": True,
                            "original_content_ok": True,
                            "rules_checked_on": (date.today() - timedelta(days=8)).isoformat(),
                        }
                    }
                },
            )

    def test_dry_run_does_not_write_state(self):
        with patch.dict(os.environ, {}, clear=True):
            result = publish(
                "sample",
                "examplecommunity",
                "A sample",
                "Body",
                policy_path=self.policy,
                state_path=self.state,
            )
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(self.state.exists())

    def test_live_requires_approved_access(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PostingError, "API approval"):
                publish(
                    "sample",
                    "examplecommunity",
                    "A sample",
                    "Body",
                    policy_path=self.policy,
                    state_path=self.state,
                    live=True,
                )

    @patch(
        "oss_launchbot.reddit._submit", return_value="https://www.reddit.com/r/examplecommunity/x"
    )
    @patch("oss_launchbot.reddit._access_token", return_value="fake-token")
    def test_success_is_recorded_and_cannot_repeat(self, _token, _submit):
        flags = {"REDDIT_API_APPROVED": "1", "REDDIT_ACCOUNT_ELIGIBLE": "1"}
        with patch.dict(os.environ, flags, clear=True):
            result = publish(
                "sample",
                "examplecommunity",
                "A sample",
                "Body",
                policy_path=self.policy,
                state_path=self.state,
                live=True,
            )
            self.assertEqual(result["status"], "sent")
            self.assertEqual(
                json.loads(self.state.read_text())["posts"]["sample:examplecommunity"]["status"],
                "sent",
            )
            with self.assertRaisesRegex(PostingError, "already has a Reddit attempt"):
                publish(
                    "sample",
                    "examplecommunity",
                    "A sample",
                    "Body",
                    policy_path=self.policy,
                    state_path=self.state,
                    live=True,
                )


if __name__ == "__main__":
    unittest.main()
