import unittest
from unittest.mock import Mock, patch

import services.github as github


def repository(name, description="", **overrides):
    data = {
        "name": name,
        "html_url": f"https://github.com/yeschan119/{name}",
        "description": description,
        "topics": [],
        "language": "Python",
        "stargazers_count": 0,
        "updated_at": "2026-09-01T00:00:00Z",
        "archived": False,
        "fork": False,
    }
    data.update(overrides)
    return data


class GitHubServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_token = github.GITHUB_TOKEN
        github.clear_cache()

    def tearDown(self):
        github.GITHUB_TOKEN = self.original_token
        github.clear_cache()

    def test_headers_omit_invalid_authorization_when_token_is_missing(self):
        github.GITHUB_TOKEN = None

        headers = github._headers()

        self.assertNotIn("Authorization", headers)

    def test_repository_selection_uses_query_intent(self):
        repositories = [
            repository("portfolio", "Portfolio website"),
            repository("erp-database-design-migration", "ERP PostgreSQL migration"),
            repository("real-time-messaging-service", "SignalR messaging system"),
        ]

        selected = github.select_repositories("ERP 재고와 발주 구조를 알려줘", repositories, limit=1)

        self.assertEqual(selected[0]["name"], "erp-database-design-migration")

    @patch("services.github.requests.get")
    def test_repository_list_requests_all_public_repositories(self, get):
        response = Mock()
        response.json.return_value = [repository("portfolio")]
        response.raise_for_status.return_value = None
        get.return_value = response

        repositories = github.get_repos()

        self.assertEqual([repo["name"] for repo in repositories], ["portfolio"])
        self.assertEqual(get.call_args.kwargs["params"]["per_page"], 100)
        self.assertEqual(get.call_args.kwargs["params"]["type"], "owner")

    @patch("services.github.requests.post")
    def test_graphql_profile_returns_pinned_and_contributions(self, post):
        github.GITHUB_TOKEN = "test-token"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {
                "user": {
                    "pinnedItems": {
                        "nodes": [
                            {
                                "name": "portfolio",
                                "description": "Portfolio",
                                "url": "https://github.com/yeschan119/portfolio",
                                "stargazerCount": 3,
                                "forkCount": 1,
                                "updatedAt": "2026-09-01T00:00:00Z",
                                "pushedAt": "2026-09-01T00:00:00Z",
                                "primaryLanguage": {"name": "HTML"},
                                "repositoryTopics": {"nodes": []},
                            }
                        ]
                    },
                    "contributionsCollection": {
                        "contributionCalendar": {"totalContributions": 321},
                        "totalCommitContributions": 250,
                        "totalIssueContributions": 5,
                        "totalPullRequestContributions": 20,
                        "totalPullRequestReviewContributions": 30,
                        "totalRepositoryContributions": 2,
                        "commitContributionsByRepository": [
                            {
                                "repository": {
                                    "name": "portfolio",
                                    "url": "https://github.com/yeschan119/portfolio",
                                },
                                "contributions": {"totalCount": 80},
                            }
                        ],
                    },
                }
            }
        }
        post.return_value = response

        profile = github.get_graphql_profile()

        self.assertTrue(profile["available"])
        self.assertEqual(profile["pinned_repositories"][0]["name"], "portfolio")
        self.assertEqual(profile["contributions"]["total"], 321)
        self.assertEqual(profile["contributions"]["commits_by_repository"][0]["commits"], 80)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    @patch("services.github.get_readme", return_value="# ERP\nPostgreSQL migration")
    @patch("services.github.get_graphql_profile")
    @patch("services.github.get_public_profile")
    @patch("services.github.get_repos")
    def test_context_contains_profile_catalog_pinned_and_readme(
        self,
        get_repos,
        get_public_profile,
        get_graphql_profile,
        _get_readme,
    ):
        get_repos.return_value = [repository("erp-database-design-migration", "ERP migration")]
        get_public_profile.return_value = {
            "login": "yeschan119",
            "name": "Eungchan Kang",
            "bio": "AI Platform Engineer",
            "company": None,
            "location": None,
            "followers": 10,
            "following": 2,
            "public_repos": 1,
            "url": "https://github.com/yeschan119",
        }
        get_graphql_profile.return_value = {
            "available": True,
            "period": {"from": "2025-09-01", "to": "2026-09-01"},
            "pinned_repositories": [
                {
                    "name": "erp-database-design-migration",
                    "description": "ERP migration",
                    "url": "https://github.com/yeschan119/erp-database-design-migration",
                    "stargazerCount": 1,
                    "forkCount": 0,
                    "primaryLanguage": {"name": "Python"},
                    "repositoryTopics": {"nodes": []},
                }
            ],
            "contributions": {
                "total": 100,
                "commits": 90,
                "issues": 1,
                "pull_requests": 4,
                "pull_request_reviews": 3,
                "repositories_created": 2,
                "commits_by_repository": [],
            },
        }

        context = github.get_github_context("ERP를 설명해줘")

        self.assertIn("Pinned repositories", context["text"])
        self.assertIn("Total contributions: 100", context["text"])
        self.assertIn("Public repository catalog", context["text"])
        self.assertIn("README excerpt", context["text"])
        self.assertTrue(context["profile_capabilities"]["pinned_repositories"])


if __name__ == "__main__":
    unittest.main()
