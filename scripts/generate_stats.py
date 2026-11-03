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
OVERVIEW_IMAGE = ROOT / "profile" / "overview.svg"
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


def render_overview_svg(stats: dict) -> str:
    """Render the linked static cover image shown in the profile README.

    @param stats: Aggregated public profile statistics.
    @returns: Standalone SVG markup for the GitHub profile overview.
    """
    merged_count = int(stats["summary"]["merged_prs"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="420" viewBox="0 0 1200 420" role="img" aria-labelledby="title description">
  <title id="title">惠岩 · @deosiree | Coding Agent Builder</title>
  <desc id="description">AI systems engineering focused on agent harnesses, security, and memory. Click through to the interactive contribution dashboard.</desc>
  <rect width="1200" height="420" fill="#101216"/>
  <rect width="8" height="420" fill="#d4ff70"/>
  <rect x="8" y="0" width="1192" height="72" fill="#15181d"/>
  <text x="48" y="45" fill="#d4ff70" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="13" font-weight="700">HY / ENGINEERING PROFILE</text>
  <text x="1152" y="45" text-anchor="end" fill="#aeb5bf" font-family="Segoe UI, sans-serif" font-size="12">AI SYSTEMS · OPEN SOURCE</text>
  <line x1="48" y1="72" x2="1152" y2="72" stroke="#30353d"/>

  <text x="48" y="151" fill="#f3f4f6" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="58" font-weight="700">惠岩</text>
  <text x="207" y="147" fill="#aeb5bf" font-family="Segoe UI, sans-serif" font-size="20">@deosiree</text>
  <text x="48" y="194" fill="#d4ff70" font-family="Segoe UI, sans-serif" font-size="15" font-weight="700">BUILDING CODING AGENTS</text>
  <text x="48" y="231" fill="#e5e7eb" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="18">构建 Coding Agent，持续参与一线 AI 开源项目。</text>
  <text x="48" y="260" fill="#aeb5bf" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="15">从 Harness、安全边界到记忆系统，让 Agent 更可靠。</text>

  <line x1="48" y1="294" x2="666" y2="294" stroke="#30353d"/>
  <text x="48" y="321" fill="#818995" font-family="Segoe UI, sans-serif" font-size="11" font-weight="700">ENGINEERING FOCUS</text>
  <rect x="48" y="339" width="184" height="34" rx="3" fill="#1a1e24" stroke="#3a414a"/>
  <rect x="48" y="339" width="3" height="34" fill="#d4ff70"/>
  <text x="64" y="361" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="12" font-weight="600">AGENT HARNESS</text>
  <rect x="244" y="339" width="158" height="34" rx="3" fill="#1a1e24" stroke="#3a414a"/>
  <rect x="244" y="339" width="3" height="34" fill="#ff8068"/>
  <text x="260" y="361" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="12" font-weight="600">SECURITY</text>
  <rect x="414" y="339" width="188" height="34" rx="3" fill="#1a1e24" stroke="#3a414a"/>
  <rect x="414" y="339" width="3" height="34" fill="#78c7ff"/>
  <text x="430" y="361" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="12" font-weight="600">MEMORY SYSTEMS</text>

  <rect x="708" y="103" width="444" height="270" rx="4" fill="#14171c" stroke="#343a43"/>
  <text x="738" y="137" fill="#818995" font-family="Segoe UI, sans-serif" font-size="11" font-weight="700">SYSTEMS I WORK ON</text>
  <line x1="738" y1="155" x2="1122" y2="155" stroke="#30353d"/>
  <text x="738" y="190" fill="#d4ff70" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700">01</text>
  <text x="778" y="190" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="15" font-weight="600">Agent Harness</text>
  <text x="778" y="211" fill="#8b929d" font-family="Segoe UI, sans-serif" font-size="12">Runtime · orchestration · evaluation</text>
  <line x1="738" y1="226" x2="1122" y2="226" stroke="#30353d"/>
  <text x="738" y="261" fill="#ff8068" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700">02</text>
  <text x="778" y="261" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="15" font-weight="600">Security</text>
  <text x="778" y="282" fill="#8b929d" font-family="Segoe UI, sans-serif" font-size="12">Policy · permissions · safe execution</text>
  <line x1="738" y1="297" x2="1122" y2="297" stroke="#30353d"/>
  <text x="738" y="332" fill="#78c7ff" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700">03</text>
  <text x="778" y="332" fill="#f3f4f6" font-family="Segoe UI, sans-serif" font-size="15" font-weight="600">Memory Systems</text>

  <rect x="8" y="389" width="1192" height="31" fill="#d4ff70"/>
  <text x="48" y="410" fill="#101216" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700">{merged_count:02d} MERGED PRs · PUBLIC GITHUB DATA</text>
  <text x="1152" y="410" text-anchor="end" fill="#101216" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700">OPEN INTERACTIVE DASHBOARD ↗</text>
</svg>
'''


def write_overview_svg(stats: dict) -> None:
    """Write the generated profile cover image used by the README.

    @param stats: Aggregated public profile statistics.
    @returns: None.
    """
    OVERVIEW_IMAGE.write_text(render_overview_svg(stats), encoding="utf-8")


def main() -> None:
    """Fetch public GitHub data and update the README and Pages data file.

    @param: None.
    @returns: None.
    """
    repositories = load_repositories()
    pull_requests, total_pr_count = load_merged_pull_requests()
    stats = summarize(repositories, pull_requests, total_pr_count)
    write_stats(stats)
    write_overview_svg(stats)
    update_readme(stats)
    print(
        "Updated profile stats: "
        f"{total_pr_count} merged PRs, "
        f"{len(stats['owned_repositories'])} projects, "
        f"{len(stats['external_contributions'])} external repositories"
    )


if __name__ == "__main__":
    main()
