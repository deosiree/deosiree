#!/usr/bin/env python3
"""Generate public profile statistics for the README and GitHub Pages site."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGIN = "deosiree"
API_ROOT = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
PROFILE_DATA = ROOT / "profile" / "stats.json"
PAGES_URL = "https://deosiree.github.io/deosiree/"
PULL_REQUESTS_URL = (
    "https://github.com/search?q=is%3Apr+is%3Amerged+author%3Adeosiree"
    "&type=pullrequests"
)
WORKFLOW_URL = (
    "https://github.com/deosiree/deosiree/actions/workflows/update-profile.yml"
)
README_START = "<!-- profile-stats:start -->"
README_END = "<!-- profile-stats:end -->"
SEARCH_RESULT_LIMIT = 1000
UTC_PLUS_EIGHT = timezone(timedelta(hours=8))


def request_json(path: str) -> dict | list:
    """Fetch one public GitHub REST API response as JSON.

    @param path: API path including its query string.
    @returns: Decoded JSON response.
    """
    request = Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "deosiree-profile-readme",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"GitHub API request failed: {path}: {error}") from error


def load_repositories() -> list[dict]:
    """Load public repositories owned by the profile account.

    @param: None.
    @returns: Public repository records returned by the GitHub REST API.
    """
    repositories = []
    page = 1
    while True:
        query = urlencode({"type": "owner", "per_page": 100, "page": page})
        result = request_json(f"/users/{LOGIN}/repos?{query}")
        if not isinstance(result, list):
            raise RuntimeError("Unexpected response while loading repositories")
        repositories.extend(result)
        if len(result) < 100:
            return repositories
        page += 1


def load_merged_pull_requests() -> tuple[list[dict], int]:
    """Load public merged pull requests authored by the profile account.

    @returns: Search result records and GitHub's total matching count.
    """
    query_text = f"is:pr is:merged author:{LOGIN}"
    pull_requests = []
    page = 1
    total_count = 0
    while page <= SEARCH_RESULT_LIMIT // 100:
        query = urlencode(
            {"q": query_text, "per_page": 100, "page": page, "sort": "updated"}
        )
        result = request_json(f"/search/issues?{query}")
        if not isinstance(result, dict):
            raise RuntimeError("Unexpected response while searching pull requests")
        if page == 1:
            total_count = int(result.get("total_count", 0))
        items = result.get("items", [])
        pull_requests.extend(items)
        if len(items) < 100 or len(pull_requests) >= min(total_count, SEARCH_RESULT_LIMIT):
            break
        page += 1
    return pull_requests, total_count


def pull_request_sort_key(pull_request: dict) -> tuple[str, str, int]:
    """Return a deterministic key that orders pull requests by merge time.

    @param pull_request: Normalized pull request record.
    @returns: Merge timestamp, repository name, and pull request number.
    """
    return (
        pull_request["merged_at"],
        pull_request["repository"].casefold(),
        pull_request["number"],
    )


def repository_sort_key(repository: dict) -> tuple[int, str]:
    """Return a key that orders owned repositories by stars and name.

    @param repository: Normalized repository record.
    @returns: Negative star count followed by a stable repository name.
    """
    return (-repository["stars"], repository["full_name"].casefold())


def contribution_sort_key(contribution: dict) -> tuple[int, str]:
    """Return a key that orders external repositories by contribution count.

    @param contribution: Grouped external contribution record.
    @returns: Negative pull request count followed by a stable repository name.
    """
    return (-contribution["merged_pr_count"], contribution["full_name"].casefold())


def normalize_pull_requests(pull_requests: list[dict]) -> list[dict]:
    """Normalize public search results into records for display.

    @param pull_requests: Raw issue-search records for merged pull requests.
    @returns: Pull requests with repository, URL, title, number, and merge date.
    """
    normalized = []
    for pull_request in pull_requests:
        repository_url = pull_request.get("repository_url", "")
        full_name = repository_url.rsplit("/repos/", 1)[-1]
        if full_name.count("/") != 1:
            continue
        try:
            number = int(pull_request["number"])
        except (KeyError, TypeError, ValueError):
            continue
        normalized.append(
            {
                "title": pull_request.get("title") or "Untitled pull request",
                "number": number,
                "repository": full_name,
                "repository_url": f"https://github.com/{full_name}",
                "html_url": pull_request.get("html_url")
                or f"https://github.com/{full_name}/pull/{number}",
                "merged_at": pull_request.get("closed_at") or "",
            }
        )
    normalized.sort(key=pull_request_sort_key, reverse=True)
    return normalized


def summarize(
    repositories: list[dict], pull_requests: list[dict], total_pr_count: int
) -> dict:
    """Build profile project, merged PR, and external contribution datasets.

    @param repositories: Public repositories owned by the account.
    @param pull_requests: Raw public merged pull request search results.
    @param total_pr_count: Total result count reported by GitHub Search.
    @returns: JSON-serializable statistics for the profile page.
    """
    owned_repositories = []
    for repository in repositories:
        if repository.get("fork") or repository.get("name", "").casefold() == LOGIN:
            continue
        owned_repositories.append(
            {
                "name": repository.get("name", ""),
                "full_name": repository.get("full_name", ""),
                "html_url": repository.get("html_url", ""),
                "description": repository.get("description") or "",
                "language": repository.get("language") or "",
                "stars": int(repository.get("stargazers_count", 0)),
                "updated_at": repository.get("updated_at") or "",
            }
        )
    owned_repositories.sort(key=repository_sort_key)

    normalized_prs = normalize_pull_requests(pull_requests)
    external_contributions = {}
    for pull_request in normalized_prs:
        full_name = pull_request["repository"]
        owner = full_name.split("/", 1)[0]
        if owner.casefold() == LOGIN:
            continue
        contribution = external_contributions.setdefault(
            full_name,
            {
                "full_name": full_name,
                "html_url": pull_request["repository_url"],
                "merged_pr_count": 0,
                "latest_pr": None,
            },
        )
        contribution["merged_pr_count"] += 1
        if contribution["latest_pr"] is None:
            contribution["latest_pr"] = {
                "title": pull_request["title"],
                "number": pull_request["number"],
                "html_url": pull_request["html_url"],
                "merged_at": pull_request["merged_at"],
            }

    contributions = sorted(
        external_contributions.values(), key=contribution_sort_key
    )
    return {
        "updated_at": datetime.now(UTC_PLUS_EIGHT).strftime(
            "%Y-%m-%d %H:%M UTC+8"
        ),
        "summary": {"merged_prs": total_pr_count},
        "merged_prs_truncated": total_pr_count > len(normalized_prs),
        "merged_prs": normalized_prs,
        "owned_repositories": owned_repositories,
        "external_contributions": contributions,
    }


def update_readme(stats: dict) -> None:
    """Replace the marked README summary with the current merged PR count.

    @param stats: Aggregated public profile statistics.
    @returns: None.
    """
    readme_path = ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    if content.count(README_START) != 1 or content.count(README_END) != 1:
        raise RuntimeError("README must contain exactly one profile stats marker pair")
    start = content.index(README_START) + len(README_START)
    end = content.index(README_END)
    if start > end:
        raise RuntimeError("README profile stats markers are out of order")

    merged_count = stats["summary"]["merged_prs"]
    block = (
        f"\n\n**已合并 PR：{merged_count}** · "
        f"[打开交互统计页 ↗]({PAGES_URL}) · "
        f"[查看已合并 PR ↗]({PULL_REQUESTS_URL}) · "
        f"[更新记录 ↗]({WORKFLOW_URL})\n"
    )
    readme_path.write_text(content[:start] + block + content[end:], encoding="utf-8")


def write_stats(stats: dict) -> None:
    """Write the generated profile data for GitHub Pages.

    @param stats: Aggregated public profile statistics.
    @returns: None.
    """
    PROFILE_DATA.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_DATA.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Fetch public GitHub data and update the README and Pages data file.

    @param: None.
    @returns: None.
    """
    repositories = load_repositories()
    pull_requests, total_pr_count = load_merged_pull_requests()
    stats = summarize(repositories, pull_requests, total_pr_count)
    write_stats(stats)
    update_readme(stats)
    print(
        "Updated profile stats: "
        f"{total_pr_count} merged PRs, "
        f"{len(stats['owned_repositories'])} projects, "
        f"{len(stats['external_contributions'])} external repositories"
    )


if __name__ == "__main__":
    main()
