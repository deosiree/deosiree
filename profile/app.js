const PAGE_SIZE = 10;
const PULL_REQUESTS_URL =
  "https://github.com/search?q=is%3Apr+is%3Amerged+author%3Adeosiree&type=pullrequests";

let profileData = null;
let currentPrPage = 0;

const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const tablist = document.querySelector('[role="tablist"]');

/**
 * Create a link constrained to GitHub's HTTPS origin.
 * @param {string} value Candidate URL from public GitHub data.
 * @returns {string} A validated GitHub URL or the profile fallback.
 */
function safeGitHubUrl(value) {
  if (typeof value !== "string" || !value) {
    return "https://github.com/deosiree";
  }
  try {
    const url = new URL(value, "https://github.com");
    if (url.protocol === "https:" && url.hostname === "github.com") {
      return url.href;
    }
  } catch {
    return "https://github.com/deosiree";
  }
  return "https://github.com/deosiree";
}

/**
 * Create an external GitHub link using text content rather than HTML.
 * @param {string} url Destination URL.
 * @param {string} label Visible link text.
 * @param {string} className Optional CSS class.
 * @returns {HTMLAnchorElement} A safe external anchor element.
 */
function createGitHubLink(url, label, className) {
  const link = document.createElement("a");
  link.href = safeGitHubUrl(url);
  link.textContent = label;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  if (className) {
    link.className = className;
  }
  return link;
}

/**
 * Format a count using the user's browser locale.
 * @param {number} value Count from the generated JSON file.
 * @returns {string} Formatted non-negative count.
 */
function formatCount(value) {
  const count = Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
  return new Intl.NumberFormat("zh-CN").format(count);
}

/**
 * Format an ISO timestamp as a Chinese calendar date.
 * @param {string} value ISO timestamp from GitHub.
 * @returns {string} Localized date or a fallback label.
 */
function formatDate(value) {
  if (!value) {
    return "日期未提供";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "日期未提供";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

/**
 * Create a list row for an empty dataset.
 * @param {string} message Empty state message.
 * @returns {HTMLLIElement} An accessible empty-state row.
 */
function createEmptyRow(message) {
  const row = document.createElement("li");
  row.className = "empty-state";
  row.textContent = message;
  return row;
}

/**
 * Render merged pull requests with ten records per page.
 * @param {void} None.
 * @returns {void}
 */
function renderMergedPullRequests() {
  const list = document.getElementById("merged-list");
  const records = profileData.merged_prs;
  list.replaceChildren();

  if (records.length === 0) {
    list.append(createEmptyRow("暂无公开的已合并 PR。"));
  } else {
    const firstIndex = currentPrPage * PAGE_SIZE;
    const pageRecords = records.slice(firstIndex, firstIndex + PAGE_SIZE);
    for (const record of pageRecords) {
      const row = document.createElement("li");
      row.className = "record";

      const main = document.createElement("div");
      main.className = "record-main";
      main.append(
        createGitHubLink(record.repository_url, record.repository, "repo"),
        createGitHubLink(
          record.html_url,
          "#" + record.number + " " + record.title + " ↗",
          "record-title"
        )
      );

      const meta = document.createElement("time");
      meta.className = "record-meta";
      meta.dateTime = record.merged_at || "";
      meta.textContent = formatDate(record.merged_at);
      row.append(main, meta);
      list.append(row);
    }
  }

  renderPullRequestPagination(records.length);
}

/**
 * Update merged PR pagination controls for the current page.
 * @param {number} totalCount Number of loaded PR records.
 * @returns {void}
 */
function renderPullRequestPagination(totalCount) {
  const pagination = document.getElementById("merged-pagination");
  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  pagination.hidden = totalPages <= 1;
  if (pagination.hidden) {
    return;
  }

  document.getElementById("page-label").textContent =
    "第 " + (currentPrPage + 1) + " / " + totalPages + " 页";
  document.getElementById("previous-page").disabled = currentPrPage === 0;
  document.getElementById("next-page").disabled = currentPrPage >= totalPages - 1;
}

/**
 * Render owned, public, non-fork repositories and their individual star counts.
 * @param {void} None.
 * @returns {void}
 */
function renderOwnedRepositories() {
  const list = document.getElementById("projects-list");
  list.replaceChildren();

  if (profileData.owned_repositories.length === 0) {
    list.append(createEmptyRow("暂无符合条件的公开项目。"));
    return;
  }

  for (const repository of profileData.owned_repositories) {
    const row = document.createElement("li");
    row.className = "project-row";

    const main = document.createElement("div");
    main.className = "project-main";
    main.append(
      createGitHubLink(repository.html_url, repository.full_name + " ↗", "project-name")
    );

    const details = [];
    if (repository.description) {
      details.push(repository.description);
    }
    if (repository.language) {
      details.push(repository.language);
    }
    const description = document.createElement("span");
    description.className = "project-description";
    description.textContent = details.join(" · ") || "暂无项目描述";
    main.append(description);

    const meta = document.createElement("span");
    meta.className = "project-meta";
    const label = document.createElement("span");
    label.textContent = "该仓库获 Star";
    const count = document.createElement("strong");
    count.textContent = formatCount(repository.stars);
    meta.append(label, count);

    row.append(main, meta);
    list.append(row);
  }
}

/**
 * Render external repositories with merged PR counts and their latest PR.
 * @param {void} None.
 * @returns {void}
 */
function renderExternalContributions() {
  const list = document.getElementById("external-list");
  list.replaceChildren();

  if (profileData.external_contributions.length === 0) {
    list.append(createEmptyRow("暂无合并到其他账号仓库的公开 PR。"));
    return;
  }

  for (const contribution of profileData.external_contributions) {
    const row = document.createElement("li");
    row.className = "contribution-row";

    const main = document.createElement("div");
    main.className = "contribution-main";
    main.append(
      createGitHubLink(
        contribution.html_url,
        contribution.full_name + " ↗",
        "contribution-name"
      )
    );

    if (contribution.latest_pr) {
      main.append(
        createGitHubLink(
          contribution.latest_pr.html_url,
          "最近合并：#" +
            contribution.latest_pr.number +
            " " +
            contribution.latest_pr.title +
            " ↗",
          "latest-pr"
        )
      );
    }

    const meta = document.createElement("span");
    meta.className = "contribution-meta";
    const count = document.createElement("strong");
    count.className = "contribution-count";
    count.textContent = formatCount(contribution.merged_pr_count) + " 个 PR";
    meta.append(count);

    row.append(main, meta);
    list.append(row);
  }
}

/**
 * Activate one tab and reveal its corresponding panel.
 * @param {HTMLButtonElement} selectedTab Tab button to activate.
 * @param {boolean} focusTab Whether to move keyboard focus to the tab.
 * @returns {void}
 */
function activateTab(selectedTab, focusTab) {
  for (const tab of tabs) {
    const isSelected = tab === selectedTab;
    tab.setAttribute("aria-selected", String(isSelected));
    tab.tabIndex = isSelected ? 0 : -1;

    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    panel.hidden = !isSelected;
  }

  if (focusTab) {
    selectedTab.focus();
  }
}

/**
 * Handle pointer activation in the statistics tablist.
 * @param {MouseEvent} event Click event from the tablist.
 * @returns {void}
 */
function handleTabClick(event) {
  if (!(event.target instanceof Element)) {
    return;
  }
  const selectedTab = event.target.closest('[role="tab"]');
  if (selectedTab) {
    activateTab(selectedTab, false);
  }
}

/**
 * Support arrow, Home, and End keyboard navigation between tabs.
 * @param {KeyboardEvent} event Keyboard event from the tablist.
 * @returns {void}
 */
function handleTabKeydown(event) {
  const currentIndex = tabs.indexOf(document.activeElement);
  if (currentIndex < 0) {
    return;
  }

  let nextIndex = currentIndex;
  if (event.key === "ArrowRight") {
    nextIndex = (currentIndex + 1) % tabs.length;
  } else if (event.key === "ArrowLeft") {
    nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = tabs.length - 1;
  } else {
    return;
  }

  event.preventDefault();
  activateTab(tabs[nextIndex], true);
}

/**
 * Handle previous and next page controls for merged PR results.
 * @param {MouseEvent} event Click event from the pagination region.
 * @returns {void}
 */
function handlePaginationClick(event) {
  if (!(event.target instanceof Element)) {
    return;
  }
  const button = event.target.closest("[data-page-action]");
  if (!button || button.disabled) {
    return;
  }

  if (button.dataset.pageAction === "previous") {
    currentPrPage = Math.max(0, currentPrPage - 1);
  } else if (button.dataset.pageAction === "next") {
    currentPrPage += 1;
  }
  renderMergedPullRequests();
}

/**
 * Validate loaded data and populate the profile page.
 * @param {object} data Parsed statistics document.
 * @returns {void}
 */
function renderProfile(data) {
  if (
    !data ||
    !data.summary ||
    !Array.isArray(data.merged_prs) ||
    !Array.isArray(data.owned_repositories) ||
    !Array.isArray(data.external_contributions)
  ) {
    throw new Error("Profile statistics have an unexpected shape.");
  }

  profileData = data;
  currentPrPage = 0;
  document.getElementById("merged-count").textContent = formatCount(
    data.summary.merged_prs
  );
  document.getElementById("count-merged").textContent = formatCount(
    data.summary.merged_prs
  );
  document.getElementById("count-projects").textContent = formatCount(
    data.owned_repositories.length
  );
  document.getElementById("count-external").textContent = formatCount(
    data.external_contributions.length
  );

  const mergedSummary = document.getElementById("merged-summary");
  mergedSummary.textContent = data.merged_prs_truncated
    ? "按合并时间倒序展示，当前列表最多包含 1,000 条；可通过 GitHub 搜索查看完整结果。"
    : "按合并时间倒序展示公开 PR。";
  if (data.merged_prs_truncated) {
    mergedSummary.append(
      document.createTextNode(" "),
      createGitHubLink(PULL_REQUESTS_URL, "查看完整结果 ↗", "inline-link")
    );
  }

  document.getElementById("updated-at").textContent = data.updated_at || "未知";
  renderMergedPullRequests();
  renderOwnedRepositories();
  renderExternalContributions();

  const status = document.getElementById("load-state");
  status.hidden = true;
}

/**
 * Display a recoverable message when profile data cannot be loaded.
 * @param {Error} error Loading or validation error.
 * @returns {void}
 */
function showLoadError(error) {
  const status = document.getElementById("load-state");
  status.replaceChildren(
    document.createTextNode("统计数据暂时无法加载。"),
    document.createTextNode(" "),
    createGitHubLink(PULL_REQUESTS_URL, "直接查看已合并 PR ↗", "inline-link")
  );
  status.hidden = false;
  console.error(error);
}

/**
 * Fetch the generated public statistics JSON and render the profile.
 * @param {void} None.
 * @returns {Promise<void>} Resolves after loading or displaying an error.
 */
async function loadProfileData() {
  try {
    const response = await fetch("./stats.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Statistics request failed with status " + response.status);
    }
    renderProfile(await response.json());
  } catch (error) {
    showLoadError(error);
  }
}

tablist.addEventListener("click", handleTabClick);
tablist.addEventListener("keydown", handleTabKeydown);
document
  .getElementById("merged-pagination")
  .addEventListener("click", handlePaginationClick);
loadProfileData();
