# portfolio-llm

GitHub-grounded LLM server for the AI chat on yeschan119.com.

## GitHub context

Each answer is grounded with:

- the complete public repository list and repository metadata;
- pinned repositories from the GitHub GraphQL API;
- the last 365 days of contribution totals and repository-level commit counts;
- README excerpts from up to four repositories selected for the question.

The API refuses to generate an answer if it cannot load verified repository
context. Responses include the exact GitHub sources used.

## Environment

Copy `.env.example` to `.env` and configure:

- `OPENAI_API_KEY`: required to generate answers;
- `GITHUB_TOKEN`: required for pinned repositories and contribution data
  (`github_token` is also accepted for the existing Render configuration);
- `GITHUB_USERNAME`: defaults to `yeschan119`;
- `GITHUB_CACHE_TTL_SECONDS`: GitHub profile cache duration, default `900`;
- `OPENAI_CHAT_MODEL`: defaults to `gpt-4o-mini`.

Use a read-only GitHub token and keep it on the backend. Public repository
metadata and README retrieval still work without a token, but pinned and
contribution fields are reported as unavailable.

## Run

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```
