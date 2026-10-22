"""Test DeepSeek API connectivity (used only for baselines / distillation)."""
import json
import os
import sys

import requests

key = os.environ.get("DEEPSEEK_API_KEY", "")
if not key:
    print("NO_KEY: set DEEPSEEK_API_KEY before running")
    sys.exit(0)

resp = requests.post(
    os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [{"role": "user", "content": "只回复 OK 两个字母"}],
        "max_tokens": 10,
        "temperature": 0,
    },
    timeout=60,
)
print("status:", resp.status_code)
try:
    print(json.dumps(resp.json(), ensure_ascii=False)[:500])
except Exception:
    print(resp.text[:500])
