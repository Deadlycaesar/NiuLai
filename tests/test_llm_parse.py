"""第三层防线(LLM 兜底解析)单测——全部 mock,零网络零 key。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dialog import parser  # noqa: E402
from src.dialog.state import DialogState  # noqa: E402


def _fresh(monkeypatch, reply):
    """开 LLM_PARSE、mock chat_json、清熔断计数。返回 (state, calls) 。"""
    calls = []

    def fake_chat_json(system, user, max_tokens=200):
        calls.append(user)
        return reply(user) if callable(reply) else reply

    monkeypatch.setattr(parser.config, "LLM_PARSE", True)
    monkeypatch.setattr(parser.llm_client, "chat_json", fake_chat_json)
    monkeypatch.setattr(parser, "_llm_parse_failures", 0)
    return DialogState(session_id="t", profile={}), calls


# 一句不含冒号、不匹配任何模板/salvage 规则的改写消息(会走到 LLM 层)
_MSG = "Hey so the thing is 100% Ring Spun Cotton matters a lot to me here"


def test_extracts_verbatim_constraints(monkeypatch):
    state, calls = _fresh(monkeypatch, {
        "category": None, "override": False,
        "constraints": ["100% Ring Spun Cotton"],
    })
    parser.update_state(state, _MSG, 1)
    assert calls, "应触发 LLM"
    assert [s.value for s in state.slots] == ["100% Ring Spun Cotton"]
    assert not state.slots[0].hard and state.slots[0].terms


def test_rejects_paraphrased_output(monkeypatch):
    # LLM 擅自改写(ring-spun 加了连字符)→ verbatim 校验拒绝 → 退回整句切分
    state, _ = _fresh(monkeypatch, {
        "category": None, "override": False,
        "constraints": ["100% ring-spun cotton fabric"],
    })
    parser.update_state(state, _MSG, 1)
    assert "100% ring-spun cotton fabric" not in [s.value for s in state.slots]


def test_override_promotes(monkeypatch):
    state, _ = _fresh(monkeypatch, {
        "category": None, "override": True,
        "constraints": ["Water Resistant"],
    })
    parser.update_state(state, "For that, what matters is: Water Resistant; Steel Band.", 1)
    parser.update_state(state, "Hmm scrap all that -- Water Resistant is the only thing", 2)
    assert state.scenario == "override"
    hard = [s.value for s in state.slots if s.hard]
    assert hard == ["Water Resistant"]


def test_circuit_breaker(monkeypatch):
    state, calls = _fresh(monkeypatch, lambda user: None)
    for turn in (1, 2, 3, 4):
        parser.update_state(state, _MSG, turn)
    assert len(calls) == 2, "连续两次失败后熔断,不再调用"


def test_off_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(parser.llm_client, "chat_json",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(parser.config, "LLM_PARSE", False)
    state = DialogState(session_id="t", profile={})
    parser.update_state(state, _MSG, 1)
    assert not calls


def test_strict_template_never_reaches_llm(monkeypatch):
    state, calls = _fresh(monkeypatch, {"category": None, "override": False, "constraints": []})
    parser.update_state(state, "I'm looking for Socks. A key requirement is: 100% Cotton.", 1)
    parser.update_state(state, "For that, what matters is: Machine Wash.", 2)
    assert not calls, "严格模板命中时 LLM 层零触发(公开集零影响的构造保证)"
