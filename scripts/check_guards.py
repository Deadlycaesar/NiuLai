"""提交前护栏自检（M5/E 的活，E 缺席期间由全组共同维护）。

守 AGENTS.md 的四条红线 + 密钥扫描。零依赖，约 10 秒跑完。
CI（.github/workflows/ci.yml）跑的就是这个脚本，本地推之前也该跑一遍：

    python3 scripts/check_guards.py

任一检查失败 → 退出码 1，并打印怎么修。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 官方冻结文件：内容必须与官方 kit 发布时逐字节一致（红线 1、3）。
# 基线指纹存在 team/frozen.sha256，首次运行自动生成并提交，之后每次比对。
FROZEN = (
    "evaluator/local_evaluator.py",
    "evaluator/__init__.py",
    "data/public_set.jsonl",
)
FROZEN_BASELINE = ROOT / "team" / "frozen.sha256"

# 密钥特征（红线 3）：宁可误报也不能漏
SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), "OpenAI/DeepSeek 风格 API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}"), "AWS access key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{16,}['\"]"), "硬编码凭据"),
]
# 这些路径不扫（文档里会出现示例字符串）
SECRET_SKIP_DIRS = {".git", "__pycache__", "data", "node_modules", ".venv", "venv"}
SECRET_EXTS = {".py", ".yml", ".yaml", ".json", ".toml", ".cfg", ".sh", ".env"}

failures: list[str] = []
notes: list[str] = []


def fail(check: str, detail: str, fix: str) -> None:
    failures.append(f"[FAIL] {check}\n       {detail}\n       修复：{fix}")


def ok(check: str, detail: str = "") -> None:
    print(f"  [ok]   {check}{('  — ' + detail) if detail else ''}")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- 红线 1 & 3：官方文件零改动 ----------
def check_frozen(write_baseline: bool) -> None:
    current = {name: sha256_of(ROOT / name) for name in FROZEN if (ROOT / name).exists()}
    missing = [n for n in FROZEN if not (ROOT / n).exists()]
    if missing:
        fail("官方文件缺失", f"找不到 {', '.join(missing)}", "从官方 kit 恢复这些文件")
        return
    if write_baseline or not FROZEN_BASELINE.exists():
        FROZEN_BASELINE.write_text(
            "".join(f"{h}  {n}\n" for n, h in sorted(current.items())), encoding="utf-8"
        )
        notes.append(f"已写入基线指纹 {FROZEN_BASELINE.relative_to(ROOT)}（首次运行）")
        ok("官方文件指纹基线已建立")
        return
    baseline = {}
    for line in FROZEN_BASELINE.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            baseline[parts[1]] = parts[0]
    changed = [n for n, h in current.items() if baseline.get(n) and baseline[n] != h]
    if changed:
        fail(
            "官方文件被修改（红线 1/3）",
            f"以下文件与基线不符：{', '.join(changed)}",
            "git checkout <文件> 还原。改 evaluator 或 public_set = 成绩无效",
        )
    else:
        ok("官方文件未被修改", f"{len(current)} 个文件指纹一致")


# ---------- 红线 4：入口壳形态 ----------
def check_entry_shell() -> None:
    path = ROOT / "starter" / "agent.py"
    if not path.exists():
        fail("入口文件缺失（红线 4）", "starter/agent.py 不存在", "官方评测器硬编码此路径，必须存在")
        return
    tree = ast.parse(path.read_text(encoding="utf-8"))
    heavy = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if heavy:
        fail(
            "入口壳混入业务逻辑（红线 4）",
            f"starter/agent.py 里定义了 {', '.join(n.name for n in heavy)}",
            "业务实现全部放 src/，此文件只做 import 转发",
        )
        return
    ok("starter/agent.py 仍是转发壳")


def check_entry_imports() -> None:
    """真正 import 一次，确保官方评测器的 `from starter.agent import Agent` 不会炸。"""
    code = "import sys; sys.path.insert(0, %r); from starter.agent import Agent; print(Agent.__name__)" % str(ROOT)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        fail(
            "评测器入口 import 失败（红线 4，= 全队零分）",
            (result.stderr or "").strip().splitlines()[-1] if result.stderr else "未知错误",
            "修好 starter/agent.py 及其 import 链",
        )
    else:
        ok("from starter.agent import Agent 可用", result.stdout.strip())


# ---------- 红线 3：密钥扫描 ----------
def iter_scan_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SECRET_SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix in SECRET_EXTS or path.name == ".env":
            yield path


def check_secrets() -> None:
    hits: list[str] = []
    for path in iter_scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}  ({label})")
    if hits:
        fail(
            "疑似密钥入库（红线 3）",
            "\n       ".join(hits[:10]),
            "从代码里删除，改用 os.environ 读取；.env 已在 .gitignore",
        )
    else:
        ok("未发现硬编码密钥", f"扫描 {sum(1 for _ in iter_scan_files())} 个文件")


def check_env_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if result.returncode == 0:
        fail(".env 已被 git 跟踪（红线 3）", ".env 在版本库里",
             "git rm --cached .env，并轮换掉已泄露的 key")
    else:
        ok(".env 未被 git 跟踪")


# ---------- 冒烟：跑 5 个 session 保证不崩 ----------
def check_smoke(n: int) -> None:
    catalog = ROOT / "data" / "catalog.jsonl"
    if not catalog.exists():
        notes.append("跳过冒烟测试：data/catalog.jsonl 不存在（先跑 scripts/prepare_catalog.py）")
        return
    import json
    import tempfile

    samples = []
    with (ROOT / "data" / "public_set.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            samples.append(line)
            if len(samples) >= n:
                break
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        tmp.writelines(samples)
        dataset = tmp.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        output = tmp.name
    result = subprocess.run(
        [sys.executable, "-m", "evaluator.local_evaluator", "--dataset", dataset, "--output", output],
        capture_output=True, text=True, cwd=ROOT,
    )
    if result.returncode != 0:
        fail("冒烟测试崩溃", (result.stderr or "").strip().splitlines()[-1], "修好再推")
        return
    score = json.load(open(output))["recommended_technical_score"]
    ok(f"冒烟 {n} sessions 通过", f"score={score:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="提交前护栏自检")
    parser.add_argument("--write-baseline", action="store_true",
                        help="重新写入官方文件指纹基线（仅在确认官方 kit 升级后使用）")
    parser.add_argument("--smoke", type=int, default=5, help="冒烟测试的 session 数，0 = 跳过")
    args = parser.parse_args()

    print("护栏自检（AGENTS.md 红线）")
    check_frozen(args.write_baseline)
    check_entry_shell()
    check_entry_imports()
    check_secrets()
    check_env_not_tracked()
    if args.smoke:
        check_smoke(args.smoke)

    for note in notes:
        print(f"  [note] {note}")
    if failures:
        print("\n" + "\n\n".join(failures))
        print(f"\n{len(failures)} 项未通过。修复后再推。")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
