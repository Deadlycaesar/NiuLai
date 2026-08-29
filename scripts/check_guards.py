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
    # 指纹前把 CRLF 归一化为 LF：Windows 队友 core.autocrlf=true 时工作区是 CRLF，
    # 而基线指纹在 LF 机器上生成——不归一化会对未改动的官方文件误报红线（git 索引里仍是 LF）。
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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
    # 只扫 git 跟踪的文件：推得出去的才可能泄漏。未跟踪的 .env 是 key 的合法居所
    # （gitignored、永不入库），对它报"入库"是误报——狼来了会让人对 FAIL 麻木。
    # ".env 被意外跟踪"由 check_env_not_tracked 专门守着，两道闸互补。
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT)
    for name in result.stdout.splitlines():
        if not name:
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        if any(part in SECRET_SKIP_DIRS for part in Path(name).parts):
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


# ---------- 测试收集完整性：写了却没被跑到的用例 ----------
def check_tests_collected() -> None:
    """比对 tests/ 里定义的用例数 vs `unittest discover` 实际收集到的数量。

    起因（2026-08-30）：tests/test_stability.py 用 pytest 风格写（模块级 `def test_*(tmp_path)`），
    但本项目零第三方依赖、用 stdlib unittest，discover 只收集 TestCase 子类——
    结果 5 个稳定性用例一次都没被执行过，而且没有任何报错。
    这条护栏让同类问题当场暴露，而不是等到正式评测时才发现"测过"的东西其实没测。
    """
    import unittest

    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        return

    defined = 0
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # TestCase 子类里的 test_* 方法，或模块级 test_* 函数（pytest 风格）
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                defined += 1

    suite = unittest.defaultTestLoader.discover(str(tests_dir), top_level_dir=str(ROOT))
    collected = suite.countTestCases()

    if collected < defined:
        fail(
            "有测试用例写了但没被执行",
            f"tests/ 里定义了 {defined} 个 test_* 用例，unittest discover 只收集到 {collected} 个",
            "多半是 pytest 风格（模块级 def test_*(fixture)）——本项目零第三方依赖，"
            "用例必须写成 unittest.TestCase 的方法才会被跑到",
        )
    else:
        ok("测试用例全部可被收集", f"定义 {defined} / 收集 {collected}")


# ---------- 留言板：把待回复的帖子推到人眼前 ----------
# git 身份 → 留言板上的称呼。同一个人可能有多个 git 配置（不同机器/邮箱）。
_BOARD_IDENTITY = {
    "chen zhilong": "陈智龙", "project-dragon7": "陈智龙", "2668767311@qq.com": "陈智龙",
    "bestbucky": "BestBucky", "biyongqi@outlook.com": "BestBucky",
    "lin xiaoxiao": "C", "lyx": "C",
    "89674854@qq.com": "周峻恺", "unknown": "周峻恺",
}


def _whoami() -> str | None:
    """从 git 配置猜当前是谁，用来高亮"在等你回复"的帖子。猜不到就不高亮。"""
    for key in ("user.name", "user.email"):
        value = subprocess.run(["git", "config", key], capture_output=True, text=True, cwd=ROOT)
        name = _BOARD_IDENTITY.get((value.stdout or "").strip().lower())
        if name:
            return name
    return None


def check_board() -> None:
    """列出留言板上 🟡 待回复的帖子。**永远不会让自检失败**——只是把它推到眼前。

    起因：留言板建起来了但没人回，而大家不会主动去 git pull 之后翻文件。
    这条挂在推代码前必跑的自检里，就不需要谁记得。
    """
    board = ROOT / "team" / "留言板.md"
    if not board.exists():
        return
    me = _whoami()
    open_threads: list[tuple[str, str]] = []
    for line in board.read_text(encoding="utf-8").splitlines():
        # 排除"帖子格式"示例里的 T-00X 占位
        if line.startswith("### [T-") and "🟡" in line and "[T-00X]" not in line:
            title = line[4:].split(" · 🟡")[0].strip()
            # 帖子标题下一行才是收件人，这里直接从标题里找不到，退而扫全文的 @ 提及
            open_threads.append((title, line))
    if not open_threads:
        ok("留言板无待回复帖子")
        return

    # 找出每个 🟡 帖子的收件人（帖子标题后第一行的 **发起** X → **@Y**）
    text = board.read_text(encoding="utf-8")
    detail: list[str] = []
    mine = 0
    for title, _ in open_threads:
        block = text.split("### [" + title.split("]")[0][1:] + "]", 1)
        header = ""
        idx = text.find("### [" + title[1:].split("]")[0] + "]")
        if idx != -1:
            header = text[idx: idx + 400].split("\n")[1] if "\n" in text[idx:] else ""
        to = header.split("**@")[1].split("**")[0] if "**@" in header else "全体"
        flag = ""
        if me and (me in to or "全体" in to):
            flag = "  ← 在等你"
            mine += 1
        detail.append(f"{title}  → @{to}{flag}")

    notes.append("留言板有 %d 个 🟡 待回复%s：" % (len(open_threads), f"（其中 {mine} 个在等你）" if mine else ""))
    for line in detail:
        notes.append("         " + line)
    notes.append("         → 打开 team/留言板.md，在对应帖子下加一行 `- **回复 @你**：…`")


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
    check_tests_collected()
    check_board()
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
