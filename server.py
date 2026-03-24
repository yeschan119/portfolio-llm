from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
import json

from services.github import get_repos, get_selected_context

# -------------------------
# 환경 설정
# -------------------------
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -------------------------
# 요청 모델
# -------------------------
class ChatRequest(BaseModel):
    message: str


# -------------------------
# LLM으로 repo 선택
# -------------------------
def select_repos_with_llm(query, repos):
    repo_names = [r["name"] for r in repos]

    prompt = f"""
            User question:
            {query}

            Available repositories:
            {repo_names}

            Select up to 4 repositories that are most relevant.

            Return ONLY JSON array.
            Example:
            ["repo1", "repo2"]
            """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Select relevant GitHub repositories."},
            {"role": "user", "content": prompt}
        ]
    )

    text = response.choices[0].message.content.strip()

    try:
        selected = json.loads(text)
    except:
        selected = []

    return selected


# -------------------------
# API
# -------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        # 1. repo 가져오기
        repos = get_repos()
        # print('repos', repos)

        # 2. LLM으로 repo 선택
        selected = select_repos_with_llm(req.message, repos)
        # print('selected', selected)

        # 3. fallback
        if not selected:
            selected = [r["name"] for r in repos[:4]]

        # 4. context 생성
        context_texts = get_selected_context(selected)
        context = "\n\n".join(context_texts)
        # print('context', context)

        # 5. 최종 LLM 답변
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
                    You are a GitHub assistant.

                    Rules:
                    - Answer in the same language as the user
                    - Organize the answer clearly using bullet points
                    - Make it easy to read
                    - Use the context as reference, but you can summarize freely
                    """
                        },
                        {
                            "role": "user",
                            "content": f"""
                    Question:
                    {req.message}

                    Context:
                    {context}
                    Answer clearly using bullet points.
                    """
                }
            ]
        )

        return {"reply": response.choices[0].message.content}

    except Exception as e:
        return {"error": str(e)}