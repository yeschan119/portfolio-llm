import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

import server


class ServerTests(unittest.TestCase):
    @patch("server.get_openai_client")
    @patch("server.get_github_context")
    def test_chat_returns_grounded_sources_and_capabilities(self, get_context, get_client):
        get_context.return_value = {
            "text": "Verified repository context",
            "sources": [
                {
                    "name": "portfolio",
                    "url": "https://github.com/yeschan119/portfolio",
                }
            ],
            "selected_repositories": ["portfolio"],
            "profile_capabilities": {
                "repository_list": True,
                "pinned_repositories": True,
                "contributions": True,
            },
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Grounded answer"))]
        )
        client = Mock()
        client.chat.completions.create.return_value = completion
        get_client.return_value = client

        result = server.chat(server.ChatRequest(message="What did Eungchan build?"))

        self.assertEqual(result.reply, "Grounded answer")
        self.assertEqual(result.sources[0].name, "portfolio")
        self.assertTrue(result.profile_capabilities["contributions"])
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call["temperature"], 0.1)
        self.assertIn("Never invent repositories", call["messages"][0]["content"])

    @patch("server.get_github_context")
    def test_chat_refuses_to_answer_when_github_fails(self, get_context):
        get_context.side_effect = server.GitHubDataError("GitHub unavailable")

        with self.assertLogs(server.LOGGER, level="ERROR"):
            with self.assertRaises(HTTPException) as caught:
                server.chat(server.ChatRequest(message="Tell me about a repository"))

        self.assertEqual(caught.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
