#!/usr/bin/env python3
"""Generate light and dark SVG cards from public GitHub activity."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGIN = "deosiree"
API_ROOT = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
CARD_WIDTH = 1000
CARD_HEIGHT = 560


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


def load_merged_pull_requests() -> list[dict]:
    """Load public merged pull requests authored by the profile account.

    @returns: Public search result records, up to GitHub's 1,000-result limit.
    """
    query_text = f"is:pr is:merged author:{LOGIN}"
    pull_requests = []
    page = 1
    total_count = 0
    while page <= 10:
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
        if len(items) < 100 or len(pull_requests) >= min(total_count, 1000):
            break
        page += 1
    return pull_requests


def summarize(repositories: list[dict], pull_requests: list[dict]) -> dict:
    """Aggregate public repository and merged pull request counts.

    @param repositories: Public repositories owned by the profile account.
    @param pull_requests: Public merged pull requests authored by the account.
    @returns: Values used to render both theme variants of the stats card.
    """
    original_repositories = [
        repo
        for repo in repositories
        if not repo.get("fork") and repo.get("name", "").casefold() != LOGIN
    ]
    repo_by_name = {
        repo.get("full_name", "").casefold(): repo for repo in repositories
    }
    groups: dict[str, dict] = {}
    owned_pr_count = 0
    upstream_pr_count = 0
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_count = 0

    for pull_request in pull_requests:
        repository_url = pull_request.get("repository_url", "")
        repository = repository_url.rsplit("/repos/", 1)[-1]
        if not repository or "/" not in repository:
            continue
        owner = repository.split("/", 1)[0]
        is_owned = owner.casefold() == LOGIN
        if is_owned:
            owned_pr_count += 1
        else:
            upstream_pr_count += 1
        group = groups.setdefault(repository, {"count": 0, "owned": is_owned})
        group["count"] += 1
        group["stars"] = repo_by_name.get(repository.casefold(), {}).get(
            "stargazers_count", 0
        )
        closed_at = pull_request.get("closed_at")
        if closed_at:
            merged_at = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            if merged_at >= thirty_days_ago:
                recent_count += 1

    ranked_repositories = [
        {"name": name, **values}
        for name, values in sorted(
            groups.items(), key=lambda item: (-item[1]["count"], item[0].casefold())
        )
    ]
    return {
        "merged_prs": len(pull_requests),
        "owned_prs": owned_pr_count,
        "upstream_prs": upstream_pr_count,
        "recent_prs": recent_count,
        "original_repositories": len(original_repositories),
        "stars": sum(int(repo.get("stargazers_count", 0)) for repo in original_repositories),
        "repositories": ranked_repositories[:5],
        "updated_at": datetime.now(
            timezone(timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M UTC+8"),
    }


def render_card(stats: dict, theme: str) -> str:
    """Render one theme-specific SVG profile card.

    @param stats: Aggregated public activity statistics.
    @param theme: Either light or dark.
    @returns: Complete SVG document as a string.
    """
    repository_rows = stats["repositories"][:5]
    card_height = CARD_HEIGHT + max(0, len(repository_rows) - 3) * 36
    palettes = {
        "light": {
            "background": "#ffffff",
            "text": "#20232a",
            "muted": "#687386",
            "line": "#e4e8f0",
            "accent": "#8055e8",
            "surface": "#fbfcff",
        },
        "dark": {
            "background": "#0d1117",
            "text": "#f0f3f8",
            "muted": "#9aa4b2",
            "line": "#303846",
            "accent": "#a887ff",
            "surface": "#111720",
        },
    }
    colors = palettes[theme]
    text_nodes = []

    def add_text(x: int, y: int, value: str, size: int, color: str, weight: int = 400) -> None:
        """Append safely escaped SVG text.

        @param x: Horizontal text position.
        @param y: Baseline position.
        @param value: Text content to escape and render.
        @param size: Font size in pixels.
        @param color: SVG fill color.
        @param weight: CSS font weight.
        @returns: None.
        """
        text_nodes.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            'font-family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" '
            f'font-weight="{weight}">{escape(value)}</text>'
        )

    add_text(44, 55, "■  OPEN SOURCE / CONTRIBUTIONS", 13, colors["accent"], 700)
    add_text(778, 55, "GITHUB / PUBLIC DATA", 12, colors["muted"])
    add_text(44, 112, LOGIN, 39, colors["text"], 700)
    add_text(44, 143, "公开仓库与开源协作记录", 15, colors["muted"])
    add_text(750, 143, f"近 30 天  +{stats['recent_prs']}", 13, colors["accent"], 600)

    metrics = [
        ("MERGED PRs", stats["merged_prs"]),
        ("UPSTREAM PRs", stats["upstream_prs"]),
        ("ORIGINAL REPOS", stats["original_repositories"]),
        ("STARS", stats["stars"]),
    ]
    for index, (label, value) in enumerate(metrics):
        x = 44 + index * 235
        add_text(x, 197, label, 11, colors["accent"], 700)
        add_text(x, 246, str(value), 34, colors["text"], 700)
    add_text(44, 273, "公开已合并", 12, colors["muted"])
    add_text(279, 273, "合并到其他账号仓库", 12, colors["muted"])
    add_text(514, 273, "排除 fork 与资料仓库", 12, colors["muted"])
    add_text(749, 273, "原创仓库累计", 12, colors["muted"])

    rows = [
        f'<rect x="24" y="24" width="{CARD_WIDTH - 48}" height="{card_height - 48}" '
        f'rx="8" fill="{colors["background"]}" stroke="{colors["line"]}"/>',
        f'<rect x="24" y="24" width="4" height="{card_height - 48}" fill="{colors["accent"]}"/>',
        f'<line x1="44" y1="296" x2="956" y2="296" stroke="{colors["line"]}"/>',
    ]
    add_text(44, 333, "MERGED PULL REQUESTS", 12, colors["accent"], 700)
    add_text(
        677,
        333,
        f"{stats['owned_prs']} OWN REPO  ·  {stats['upstream_prs']} UPSTREAM",
        11,
        colors["muted"],
    )

    if repository_rows:
        for index, repository in enumerate(repository_rows):
            y = 378 + index * 36
            add_text(44, y, f"{index + 1:02d}", 12, colors["accent"], 600)
            add_text(88, y, repository["name"], 15, colors["text"], 600)
            kind = "OWN REPOSITORY" if repository["owned"] else "UPSTREAM"
            add_text(704, y, kind, 10, colors["muted"], 500)
            add_text(846, y, f"{repository['count']} PR", 13, colors["text"], 500)
            add_text(916, y, f"★ {repository['stars']}", 12, colors["muted"])
            rows.append(
                f'<line x1="88" y1="{y + 14}" x2="956" y2="{y + 14}" '
                f'stroke="{colors["line"]}"/>'
            )
    else:
        add_text(44, 382, "暂无公开合并 PR", 14, colors["muted"])

    footer_y = card_height - 46
    add_text(44, footer_y, "GitHub REST API · 公开数据 · 每日更新", 11, colors["muted"])
    add_text(728, footer_y, stats["updated_at"], 11, colors["muted"])
    rows.extend(text_nodes)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" '
        f'height="{card_height}" viewBox="0 0 {CARD_WIDTH} {card_height}" '
        f'role="img" aria-label="deosiree public GitHub contribution statistics">'
        f'<rect width="100%" height="100%" fill="{colors["surface"]}"/>'
        f'{"".join(rows)}</svg>\n'
    )


def main() -> None:
    """Fetch current public profile data and write both SVG themes.

    @param: None.
    @returns: None.
    """
    stats = summarize(load_repositories(), load_merged_pull_requests())
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        path = assets / f"open-source-{theme}.svg"
        path.write_text(render_card(stats, theme), encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")
    print(
        "Stats: "
        f"{stats['merged_prs']} merged PRs, "
        f"{stats['upstream_prs']} upstream PRs, "
        f"{stats['original_repositories']} original repositories, "
        f"{stats['stars']} stars"
    )


if __name__ == "__main__":
    main()
