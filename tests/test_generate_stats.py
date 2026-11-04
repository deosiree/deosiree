import io
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts import generate_stats


def repo(full_name):
    return {"full_name": full_name}


def merged_pr(full_name, number):
    return {
        "repository_url": f"https://api.github.com/repos/{full_name}",
        "number": number,
        "title": f"Change {number}",
        "html_url": f"https://github.com/{full_name}/pull/{number}",
        "closed_at": "2026-11-04T10:31:01Z",
    }


class GenerateStatsTests(unittest.TestCase):
    def test_search_excludes_every_owned_target_repository(self):
        response = {"total_count": 1, "items": [merged_pr("upstream/repo", 7)]}
        with patch.object(
            generate_stats,
            "request_json",
            side_effect=[response, {"private": False}],
        ) as request:
            pull_requests, total = generate_stats.load_merged_pull_requests(
                [repo("deosiree/cursor-config"), repo("deosiree/deosiree")]
            )

        self.assertEqual(total, 1)
        self.assertEqual(pull_requests, response["items"])
        query = next(
            call.args[0]
            for call in request.call_args_list
            if "/search/issues?" in call.args[0]
        )
        self.assertIn("-repo%3Adeosiree%2Fcursor-config", query)
        self.assertIn("-repo%3Adeosiree%2Fdeosiree", query)

    def test_private_repositories_are_not_included_in_public_stats(self):
        response = {"total_count": 1, "items": [merged_pr("private-org/repo", 7)]}
        with patch.object(
            generate_stats,
            "request_json",
            side_effect=[response, {"private": True}],
        ):
            pull_requests, total = generate_stats.load_merged_pull_requests([])

        self.assertEqual(pull_requests, [])
        self.assertEqual(total, 0)

        stats = generate_stats.summarize(
            [{"name": "private", "full_name": "deosiree/private", "private": True}],
            [],
            0,
        )
        self.assertEqual(stats["owned_repositories"], [])

    def test_search_limit_fails_instead_of_reporting_partial_public_total(self):
        with patch.object(
            generate_stats,
            "request_json",
            return_value={"total_count": 1001, "items": []},
        ), self.assertRaisesRegex(RuntimeError, "1,000-result limit"):
            generate_stats.load_merged_pull_requests([])

    def test_incomplete_merged_pr_search_does_not_publish_a_partial_total(self):
        with patch.object(
            generate_stats,
            "request_json",
            side_effect=[
                {"total_count": 101, "items": [merged_pr("upstream/repo", 7)] * 100},
                {"total_count": 101, "items": []},
            ],
        ), self.assertRaisesRegex(RuntimeError, "search incomplete"):
            generate_stats.load_merged_pull_requests([])

    def test_request_json_uses_environment_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), patch.object(
            generate_stats, "urlopen", return_value=io.BytesIO(b"{}")
        ) as urlopen:
            self.assertEqual(generate_stats.request_json("/user"), {})

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_owned_repository_prs_are_filtered_from_count_and_lists(self):
        stats = generate_stats.summarize(
            [],
            [
                merged_pr("deosiree/cursor-config", 1),
                merged_pr("career-ops-hq/career-ops", 6469),
                merged_pr("career-ops-hq/career-ops", 6470),
            ],
            2,
        )

        self.assertEqual(stats["summary"]["merged_prs"], 2)
        self.assertEqual(
            [pr["number"] for pr in stats["merged_prs"]], [6470, 6469]
        )
        self.assertEqual(len(stats["external_contributions"]), 1)
        self.assertEqual(
            stats["external_contributions"][0]["merged_pr_count"], 2
        )
        self.assertIn("02 MERGED PRs", generate_stats.render_overview_svg(stats))

    def test_readme_uses_the_same_generated_timestamp_as_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "before\n"
                f"{generate_stats.README_START}\nold stats\n{generate_stats.README_END}\n"
                f"{generate_stats.README_UPDATE_START}\nold update\n{generate_stats.README_UPDATE_END}\n"
                "after\n",
                encoding="utf-8",
            )
            with patch.object(generate_stats, "ROOT", root):
                generate_stats.update_readme(
                    {"summary": {"merged_prs": 2}, "updated_at": "2026-11-04 14:30 UTC+8"}
                )

            readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("最近数据生成（北京时间）：2026-11-04 14:30", readme)
        self.assertIn("已合并 PR：2", readme)
        self.assertNotIn("old update", readme)

    def test_each_summary_uses_a_fresh_beijing_timestamp(self):
        instants = [
            datetime(2026, 11, 4, 14, 30, tzinfo=generate_stats.UTC_PLUS_EIGHT),
            datetime(2026, 11, 4, 14, 31, tzinfo=generate_stats.UTC_PLUS_EIGHT),
        ]
        with patch.object(generate_stats, "datetime") as mocked_datetime:
            mocked_datetime.now.side_effect = instants
            first = generate_stats.summarize([], [], 0)
            second = generate_stats.summarize([], [], 0)

        self.assertEqual(first["updated_at"], "2026-11-04 14:30 UTC+8")
        self.assertEqual(second["updated_at"], "2026-11-04 14:31 UTC+8")

    def test_readme_requires_both_unique_marker_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("no markers", encoding="utf-8")
            with patch.object(generate_stats, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "profile stats marker pair"):
                    generate_stats.update_readme(
                        {"summary": {"merged_prs": 0}, "updated_at": "2026-11-04 14:30 UTC+8"}
                    )


if __name__ == "__main__":
    unittest.main()
