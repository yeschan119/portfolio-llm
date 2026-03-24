import requests
import os
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

GITHUB_USERNAME = "yeschan119"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO_CACHE = None
README_CACHE = {}

# 공통 headers
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.raw"
}


# -------------------------
# Repo 가져오기 (캐싱)
# -------------------------
def get_repos():
    global REPO_CACHE

    if REPO_CACHE:
        return REPO_CACHE

    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos"

    try:
        res = requests.get(url, headers=HEADERS, timeout=5)

        if res.status_code != 200:
            print("get_repos error:", res.status_code, res.text)
            return []

        REPO_CACHE = res.json()
        return REPO_CACHE

    except Exception as e:
        print("get_repos exception:", e)
        return []


# -------------------------
# README 가져오기 (캐싱)
# -------------------------
def get_readme(repo_name):
    if repo_name in README_CACHE:
        return README_CACHE[repo_name]

    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/readme"

    try:
        res = requests.get(url, headers=HEADERS, timeout=5)

        if res.status_code != 200:
            # README 없는 경우 조용히 처리
            return ""

        text = res.text
        README_CACHE[repo_name] = text
        return text

    except Exception as e:
        print(f"get_readme error ({repo_name}):", e)
        return ""


# -------------------------
# 병렬로 README 가져오기
# -------------------------
def get_selected_context(selected_repos):
    def fetch(name):
        readme = get_readme(name)

        if readme:
            return f"Repo: {name}\n{readme[:1000]}"

        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch, selected_repos))

    return [r for r in results if r]