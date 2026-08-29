"""M3 LLM 客户端（C 的地盘）——DeepSeek v4-flash，纯 stdlib 实现（零第三方依赖）。

要点（依据 team/调研报告.md §1.1）：
  - thinking 默认开启，必须显式关闭，否则为思维链付费+等延迟；
  - JSON 模式官方承认偶尔返回空内容 → 一次重试 + 上层规则兜底；
  - prompt 按缓存友好排布：system 稳定在前，逐轮变化的内容在后；
  - usage 逐 token 累计，evaluator 要求上报（Feasibility 披露项）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src import config

_usage = {"prompt_tokens": 0, "completion_tokens": 0}


def pop_usage() -> dict:
    """取走并清零本轮累计的 token 用量（agent 每轮上报用）。"""
    global _usage
    current, _usage = _usage, {"prompt_tokens": 0, "completion_tokens": 0}
    return current


def chat_json(system: str, user: str, max_tokens: int = 200) -> dict | None:
    """一次 JSON 模式调用。失败/超时/空内容 → 重试一次 → 仍失败返回 None（上层走规则兜底）。"""
    if not config.LLM_API_KEY:
        return None
    body = json.dumps({
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "temperature": 0,   # 排序任务要可复现；不固定温度时同一会话两次重排结果会不同
        "max_tokens": max_tokens,
    }).encode()
    request = urllib.request.Request(
        f"{config.LLM_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.LLM_API_KEY}",
        },
    )
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT) as response:
                data = json.loads(response.read())
            usage = data.get("usage") or {}
            _usage["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            _usage["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            content = (data["choices"][0]["message"]["content"] or "").strip()
            if content:
                return json.loads(content)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return None
