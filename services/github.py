"""GitHub profile and repository context for the portfolio assistant."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import os
import re
import time
from typing import Any, Callable

import requests
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "yeschan119")
GITHUB_TOKEN = (
    (os.getenv("GITHUB_TOKEN") or os.getenv("github_token") or "")
    .strip()
    .strip("\"'")
    or None
)
GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = f"{GITHUB_API_URL}/graphql"
GITHUB_CACHE_TTL_SECONDS = int(os.getenv("GITHUB_CACHE_TTL_SECONDS", "900"))
MAX_SELECTED_REPOSITORIES = 4
MAX_README_CHARACTERS = 8000

_CACHE: dict[str, tuple[float, Any]] = {}

_GENERIC_TERMS = {
    "about",
    "github",
    "project",
    "projects",
    "repo",
    "repository",
    "tell",
    "what",
    "which",
    "관련",
    "내용",
    "알려줘",
    "있는",
    "저장소",
    "프로젝트",
}

_INTENT_GROUPS = (
    (
        ("erp", "재고", "발주", "정산", "마이그레이션"),
        ("erp", "database", "migration", "postgresql", "inventory", "order"),
    ),
    (
        ("database", "db", "sql", "rdbms", "데이터베이스", "튜닝", "옵티마이저"),
        ("database", "sql", "rdbms", "optimizer", "tuning"),
    ),
    (
        ("ai", "agent", "인공지능", "에이전트", "yolo"),
        ("ai", "agent", "native", "yolo", "segmentation"),
    ),
    (
        ("cloud", "aws", "azure", "클라우드"),
        ("cloud", "aws", "azure", "migration", "saas"),
    ),
    (
        ("message", "messaging", "chat", "채팅", "메시지"),
        ("messaging", "chat", "signalr", "realtime", "real time"),
    ),
    (
        ("career", "experience", "profile", "경력", "소개", "응찬", "eungchan"),
        ("portfolio", "profile", "yeschan119"),
    ),
)


class GitHubDataError(RuntimeError):
    """Raised when required public GitHub data cannot be loaded."""


def _headers(
    accept: str = "application/vnd.github+json",
    *,
    include_authorization: bool = True,
) -> dict[str, str]:
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if include_authorization and GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _cached(key: str, loader: Callable[[], Any]) -> Any:
    cached = _CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < GITHUB_CACHE_TTL_SECONDS:
        return cached[1]

    value = loader()
    _CACHE[key] = (now, value)
    return value


def clear_cache() -> None:
    """Clear in-memory GitHub data. Intended for tests and manual refreshes."""
    _CACHE.clear()


def _get_public_response(
    url: str,
    *,
    accept: str = "application/vnd.github+json",
    params: dict[str, Any] | None = None,
    timeout: int = 10,
) -> requests.Response:
    response = requests.get(
        url,
        headers=_headers(accept),
        params=params,
        timeout=timeout,
    )

    if GITHUB_TOKEN and response.status_code in {401, 403}:
        LOGGER.warning(
            "Authenticated GitHub REST request returned %s; retrying public request without a token",
            response.status_code,
        )
        response = requests.get(
            url,
            headers=_headers(accept, include_authorization=False),
            params=params,
            timeout=timeout,
        )

    return response


def _get_json(url: str, *, params: dict[str, Any] | None = None) -> Any:
    try:
        response = _get_public_response(url, params=params)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GitHubDataError(f"GitHub request failed for {url}") from exc


def get_repos() -> list[dict[str, Any]]:
    """Return every public repository owned by the configured GitHub user."""

    def load() -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        page = 1

        while True:
            batch = _get_json(
                f"{GITHUB_API_URL}/users/{GITHUB_USERNAME}/repos",
                params={
                    "type": "owner",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(batch, list):
                raise GitHubDataError("GitHub repository response was not a list")

            repositories.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        return repositories

    return _cached("repositories", load)


def get_public_profile() -> dict[str, Any]:
    """Return public profile metadata available from the REST API."""

    def load() -> dict[str, Any]:
        profile = _get_json(f"{GITHUB_API_URL}/users/{GITHUB_USERNAME}")
        return {
            "login": profile.get("login"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "location": profile.get("location"),
            "followers": profile.get("followers"),
            "following": profile.get("following"),
            "public_repos": profile.get("public_repos"),
            "url": profile.get("html_url"),
        }

    return _cached("public_profile", load)


def get_graphql_profile() -> dict[str, Any]:
    """Return pinned repositories and the last year's contribution summary."""
    if not GITHUB_TOKEN:
        return {
            "available": False,
            "reason": "GITHUB_TOKEN is not configured",
            "pinned_repositories": [],
            "contributions": None,
        }

    def load() -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        variables = {
            "login": GITHUB_USERNAME,
            "from": (now - timedelta(days=365)).isoformat(),
            "to": now.isoformat(),
        }
        query = """
        query PortfolioProfile($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            pinnedItems(first: 6, types: [REPOSITORY]) {
              nodes {
                ... on Repository {
                  name
                  description
                  url
                  stargazerCount
                  forkCount
                  updatedAt
                  pushedAt
                  primaryLanguage { name }
                  repositoryTopics(first: 10) {
                    nodes { topic { name } }
                  }
                }
              }
            }
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { totalContributions }
              totalCommitContributions
              totalIssueContributions
              totalPullRequestContributions
              totalPullRequestReviewContributions
              totalRepositoryContributions
              commitContributionsByRepository(maxRepositories: 20) {
                repository { name url }
                contributions(first: 100) { totalCount }
              }
            }
          }
        }
        """

        try:
            response = requests.post(
                GITHUB_GRAPHQL_URL,
                headers=_headers(),
                json={"query": query, "variables": variables},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GitHubDataError("GitHub GraphQL request failed") from exc

        if payload.get("errors"):
            messages = "; ".join(error.get("message", "Unknown error") for error in payload["errors"])
            raise GitHubDataError(f"GitHub GraphQL returned errors: {messages}")

        user = payload.get("data", {}).get("user")
        if not user:
            raise GitHubDataError(f"GitHub user '{GITHUB_USERNAME}' was not found")

        pinned = [item for item in user["pinnedItems"]["nodes"] if item]
        contributions = user["contributionsCollection"]
        contribution_repositories = [
            {
                "name": item["repository"]["name"],
                "url": item["repository"]["url"],
                "commits": item["contributions"]["totalCount"],
            }
            for item in contributions.get("commitContributionsByRepository", [])
        ]

        return {
            "available": True,
            "period": {"from": variables["from"], "to": variables["to"]},
            "pinned_repositories": pinned,
            "contributions": {
                "total": contributions["contributionCalendar"]["totalContributions"],
                "commits": contributions["totalCommitContributions"],
                "issues": contributions["totalIssueContributions"],
                "pull_requests": contributions["totalPullRequestContributions"],
                "pull_request_reviews": contributions["totalPullRequestReviewContributions"],
                "repositories_created": contributions["totalRepositoryContributions"],
                "commits_by_repository": contribution_repositories,
            },
        }

    return _cached("graphql_profile", load)


def _normalize(value: Any) -> str:
    normalized = str(value or "").lower().replace("-", " ").replace("_", " ").replace("/", " ")
    return re.sub(r"[^a-z0-9가-힣+#. ]+", " ", normalized).strip()


def _query_terms(query: str) -> set[str]:
    normalized_query = _normalize(query)
    terms = {
        term
        for term in normalized_query.split()
        if len(term) > 1 and term not in _GENERIC_TERMS
    }

    for triggers, expansions in _INTENT_GROUPS:
        if any(trigger in normalized_query for trigger in triggers):
            terms.update(expansions)

    return {_normalize(term) for term in terms if _normalize(term)}


def _repository_score(repo: dict[str, Any], terms: set[str]) -> int:
    name = _normalize(repo.get("name"))
    description = _normalize(repo.get("description"))
    topics = _normalize(" ".join(repo.get("topics") or []))
    score = 0

    for term in terms:
        if name == term:
            score += 16
        elif term in name:
            score += 8
        if term in description:
            score += 4
        if term in topics:
            score += 3

    if repo.get("archived"):
        score -= 10
    if repo.get("fork"):
        score -= 2
    return score


def select_repositories(
    query: str,
    repositories: list[dict[str, Any]],
    limit: int = MAX_SELECTED_REPOSITORIES,
) -> list[dict[str, Any]]:
    """Select repositories deterministically from names, descriptions, and topics."""
    terms = _query_terms(query)
    ranked = sorted(
        (
            (_repository_score(repo, terms), repo)
            for repo in repositories
            if _repository_score(repo, terms) > 0
        ),
        key=lambda item: (item[0], item[1].get("updated_at") or ""),
        reverse=True,
    )
    if ranked:
        return [repo for _, repo in ranked[:limit]]

    fallback_names = (
        "yeschan119",
        "portfolio",
        "agent-native-development-platform",
        "erp-database-design-migration",
    )
    by_name = {repo.get("name"): repo for repo in repositories}
    return [by_name[name] for name in fallback_names if name in by_name][:limit]


def get_readme(repo_name: str) -> str:
    """Return a repository README as raw Markdown."""

    def load() -> str:
        url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo_name}/readme"
        try:
            response = _get_public_response(
                url,
                accept="application/vnd.github.raw+json",
                timeout=10,
            )
            if response.status_code == 404:
                return ""
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as exc:
            LOGGER.warning("README request failed for %s: %s", repo_name, exc)
            return ""

    return _cached(f"readme:{repo_name}", load)


def _repository_catalog(repositories: list[dict[str, Any]]) -> str:
    lines = []
    for repo in repositories:
        topics = ", ".join(repo.get("topics") or []) or "none"
        lines.append(
            "- {name} | {url} | language={language} | stars={stars} | "
            "updated={updated} | topics={topics} | description={description}".format(
                name=repo.get("name"),
                url=repo.get("html_url"),
                language=repo.get("language") or "unknown",
                stars=repo.get("stargazers_count", 0),
                updated=repo.get("updated_at") or "unknown",
                topics=topics,
                description=repo.get("description") or "none",
            )
        )
    return "\n".join(lines)


def _profile_context(public_profile: dict[str, Any], graphql_profile: dict[str, Any]) -> str:
    lines = [
        "GitHub public profile:",
        f"- Login: {public_profile.get('login')}",
        f"- Name: {public_profile.get('name')}",
        f"- Bio: {public_profile.get('bio') or 'not provided'}",
        f"- Company: {public_profile.get('company') or 'not provided'}",
        f"- Location: {public_profile.get('location') or 'not provided'}",
        f"- Followers: {public_profile.get('followers')}",
        f"- Public repositories: {public_profile.get('public_repos')}",
        f"- URL: {public_profile.get('url')}",
    ]

    if not graphql_profile["available"]:
        lines.append(
            "- Pinned repositories and contribution details are unavailable "
            "because GITHUB_TOKEN is not configured."
        )
        return "\n".join(lines)

    lines.append("Pinned repositories:")
    for repo in graphql_profile["pinned_repositories"]:
        language = (repo.get("primaryLanguage") or {}).get("name") or "unknown"
        topics = ", ".join(
            node["topic"]["name"]
            for node in repo.get("repositoryTopics", {}).get("nodes", [])
        ) or "none"
        lines.append(
            f"- {repo['name']} | {repo['url']} | language={language} | "
            f"stars={repo['stargazerCount']} | forks={repo['forkCount']} | "
            f"topics={topics} | description={repo.get('description') or 'none'}"
        )

    contributions = graphql_profile["contributions"]
    period = graphql_profile["period"]
    lines.extend(
        [
            f"Contributions from {period['from']} to {period['to']}:",
            f"- Total contributions: {contributions['total']}",
            f"- Commits: {contributions['commits']}",
            f"- Pull requests: {contributions['pull_requests']}",
            f"- Pull request reviews: {contributions['pull_request_reviews']}",
            f"- Issues: {contributions['issues']}",
            f"- Repositories created: {contributions['repositories_created']}",
            "Commit contributions by repository:",
        ]
    )
    lines.extend(
        f"- {item['name']} | {item['url']} | commits={item['commits']}"
        for item in contributions["commits_by_repository"]
    )
    return "\n".join(lines)


def get_github_context(query: str) -> dict[str, Any]:
    """Build verified profile, repository, contribution, and README context."""
    repositories = get_repos()
    if not repositories:
        raise GitHubDataError("No GitHub repositories were returned")

    public_profile = get_public_profile()
    try:
        graphql_profile = get_graphql_profile()
    except GitHubDataError as exc:
        LOGGER.warning("GraphQL profile data is unavailable: %s", exc)
        graphql_profile = {
            "available": False,
            "reason": str(exc),
            "pinned_repositories": [],
            "contributions": None,
        }

    selected = select_repositories(query, repositories)

    def read_repository(repo: dict[str, Any]) -> dict[str, Any] | None:
        readme = get_readme(repo["name"])
        if not readme:
            return None
        return {
            "name": repo["name"],
            "url": repo["html_url"],
            "description": repo.get("description") or "",
            "readme": readme[:MAX_README_CHARACTERS],
        }

    with ThreadPoolExecutor(max_workers=MAX_SELECTED_REPOSITORIES) as executor:
        readme_contexts = [item for item in executor.map(read_repository, selected) if item]

    if not readme_contexts:
        raise GitHubDataError("No README context was available for the selected repositories")

    sections = [
        _profile_context(public_profile, graphql_profile),
        "Public repository catalog:\n" + _repository_catalog(repositories),
    ]
    sections.extend(
        (
            f"Selected repository: {repo['name']}\n"
            f"URL: {repo['url']}\n"
            f"Description: {repo['description'] or 'none'}\n"
            f"README excerpt:\n{repo['readme']}"
        )
        for repo in readme_contexts
    )

    sources = [{"name": "GitHub profile", "url": public_profile["url"]}]
    sources.extend({"name": repo["name"], "url": repo["url"]} for repo in readme_contexts)

    return {
        "text": "\n\n---\n\n".join(sections),
        "sources": sources,
        "selected_repositories": [repo["name"] for repo in readme_contexts],
        "profile_capabilities": {
            "repository_list": True,
            "pinned_repositories": graphql_profile["available"],
            "contributions": graphql_profile["available"],
        },
    }
