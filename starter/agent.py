"""入口壳：官方评测器硬编码 `from starter.agent import Agent`，此文件只做转发。

业务实现全部在 src/ 下（见 AGENTS.md 目录归属）。不要在这里写任何逻辑。
"""

from src.dialog.agent import ShoppingAgent as Agent

__all__ = ["Agent"]
