# 作者：vick 邮箱：ykun@yk9811.com

"""把仓库复制到临时目录并指向 ADF_ROOT，测试读写都落在副本上。

红线动作的人按只有"点选来源"一种——方向/数值裁决必须带
`--from<待裁决问题号> --pick<选项>`（或 mark 收割），M1/M2 要 `--pick 通过`；
只有 M3 还保留"交互终端照抄"这一道 TTY 检查（用 fake_terminal 假装一个）。
每个测试类仍在进程内把引擎的家目录换成副本里的 home（审阅包等要读它）。

tick 四相位自动化：停点的**启动、普通送审、完成**都由 `tick_report()` 自动做——
① 指纹失效退回并级联；② 依赖定稿且未被里程碑阻塞的未开始停点自动置进行中；
③ 判据齐备的进行中停点直接完成（自动归属）或置送审态（里程碑归属，显示"待里程碑"）；
④ 复核恢复。所以测试的推进口径是"补独立审查记录（`review()`）→ 跑 `tick_report()`"，
**不再用 advance 启动/送审/完成**；`advance` 只剩"退回进行中（主动重做）"与
"带违例送审（--allow-violation）"两种真用法，其余调用不改状态。
停点审查要求读 `flow_model.yaml` 的 `review:` 字段（行 1–6 spec_review、行 7 逐模块、
行 8 顶层、行 9 tb_review、行 10–12 none），用 `review()` 一步补齐；行 6/11/12 由里程碑覆盖完成，
用 `force_done()` 可直接构造"已完成"前置状态。

里程碑确认：M1/M2 要 `--pick 通过`（点选），M3 要终端照抄（`confirm_milestone()`）。
里程碑阻塞：停点 4 启动前要确认 M1、停点 7 启动前要确认 M2——此时这表现为
`tick` 不会自动启动它们（而不是 advance 抛错）。
"""

import os
import shutil
import tempfile
import unittest

_SKIP_DIRS = {".git", "work", "dc", "pt", "lint", "__pycache__"}

# 审查记录的作者与审查者派工号（框架只能校验两者不同）。
AUTHOR = "author-01"
REVIEWER = "reviewer-02"


def checkout_root():
    """正在执行的这份代码所在仓库，不受 ADF_ROOT 影响。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ignore(directory, names):
    skipped = []
    # 仓库根下的子系统目录（含 state.json）不进测试副本：否则用户正常
    # `init <sys>` 之后跑 selftest，多子系统类用例会把真实子系统算进来而假失败。
    at_repo_root = os.path.abspath(directory) == checkout_root()
    for name in names:
        path = os.path.join(directory, name)
        if name in _SKIP_DIRS and os.path.isdir(path):
            skipped.append(name)
        elif at_repo_root and os.path.isfile(os.path.join(path, "state.json")):
            skipped.append(name)
        elif name.endswith(".pyc"):
            skipped.append(name)
    return skipped


def copy_repo():
    parent = tempfile.mkdtemp(prefix="adf-test-")
    dest = os.path.join(parent, "repo")
    shutil.copytree(checkout_root(), dest, ignore=_ignore)
    # 测试断言绑定出厂剖面（example）的脚本内容与 expect_versions 占位，
    # 钉住副本的 active，不随开发机 toolchain/active 的指向漂移；
    # 需要别的剖面的用例自行覆盖副本里的这一行。
    with open(os.path.join(dest, "toolchain", "active"), "w", encoding="utf-8") as fh:
        fh.write("example\n")
    return parent, dest


REVIEW_REPORT_TABLE = (
    "## 发现与处置\n\n"
    "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
    "|---|---|---|---|---|\n"
    "| F1 | 提示 | 全文 | 无 | 已确认并记录 |\n"
)


def write_report(root, name, sid, module="", report=""):
    """按停点（行 7 带模块）在 `<sys>/report/` 下写一份审查报告，返回相对路径。

    报告修改时间顶到产物最后一次修改之后——"报告必须是这一版产物审出来的"。
    内容缺省用固定格式的发现与处置表（REVIEW_REPORT_TABLE），可用 `report=` 覆盖。
    CLI 用例给 `review record --report` 备料，也复用给进程内 `review()`。
    """
    import framework.engine as engine
    from framework.state import sys_dir
    base = sys_dir(root, name)
    rel = "report/%s_row%d%s_review.md" % (name, int(sid), ("_" + module) if module else "")
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report or ("# 行 %s%s 独立审查报告\n\n%s"
                            % (sid, ("（%s）" % module) if module else "", REVIEW_REPORT_TABLE)))
    product = engine._review_product(base, int(sid), module)
    newest = engine._newest_mtime(product)
    if newest and os.path.getmtime(path) <= newest:
        os.utime(path, (newest + 1, newest + 1))
    return rel


def review(root, name, sid, module="", report="", findings=None):
    """给停点 sid 补一条对当前产物的独立审查记录（作者≠审查者）。

    行 1–6 记 spec_review；行 7 要 module（绑模块摘要）；行 8 缺省审顶层；
    行 9 记 tb_review；行 10–12 不需要审查记录（闸门与运行记录就是审查）。

    审查记录必须带 `--report report/<文件>.md`，这里先用 `write_report()` 写一份
    固定格式的报告（发现与处置表；内容可用 report= 覆盖）再调 `review_record()`。
    `findings` 缺省 None：引擎按报告表解析计数；显式给时只作一致性校验（与解析不符即拒）。
    """
    import framework.engine as engine
    rel = write_report(root, name, int(sid), module=module, report=report)
    kwargs = {}
    if findings is not None:
        kwargs["findings"] = findings
    return engine.review_record(root, name, int(sid), module=module, author=AUTHOR, reviewer=REVIEWER,
                                report=rel, **kwargs)


def cli(root, *args):
    """在副本仓库里跑 `script/framework.py`（ADF_ROOT 指向副本），返回 CompletedProcess。

    用真进程验命令行面（argparse 的退出码与 stderr 是真结论，不能靠 import 猜）；
    stdin 给 DEVNULL，免得任何终端提示挂住用例。
    """
    import subprocess
    import sys
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run(
        [sys.executable, os.path.join(checkout_root(), "script", "framework.py"), *args],
        env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


def force_done(root, name, sid):
    """把停点直接置为完成并按当前产物写指纹。

    构造"该行已完成"的前置状态：既用于行 6/11/12（它们的完成由里程碑确认写入，
    动作表 stop_done_milestone），也用于在流程中段直接造出"前面若干行已完成"的起点。
    绕过闸门与审查判据，只做状态与指纹——不要用它替代对判据本身的断言。
    """
    from framework.engine import _product_digest
    from framework.flow import DONE, load
    from framework.state import load_state, now, save, stop_row
    state = load_state(root, name)
    stop = load()["by_id"][int(sid)]
    row = stop_row(state, int(sid))
    row["state"] = DONE
    row["done_at"] = now()
    row["confirmed_at"] = row["done_at"]
    row["fingerprint"] = _product_digest(root, name, stop)
    save(root, name, state)
    return row


def write_milestone_notes(root, name, mid, count=4, extra=""):
    """写 M1 的结论摘要（<sys>/milestone_notes/M1.md，固定 3–6 条）。

    闸门检查条数，所以夹具推进 M1 前必须先有它——这正是"摘要为唯一入口"的口径。
    """
    from framework.state import sys_dir
    path = os.path.join(sys_dir(root, name), "milestone_notes", "%s.md" % mid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# %s 结论摘要（%s）" % (mid, name), ""]
    for index in range(1, int(count) + 1):
        lines.append("%d. 第 %d 条结论：口径与依据见原文对应章节。" % (index, index))
    if extra:
        lines.append(extra)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def confirm_milestone(root, name, mid, confirm="", pick="通过"):
    """里程碑确认。M1/M2 要 `--pick 通过`（点选，无终端、无令牌）；
    M3 要交互终端照抄（配合 fake_terminal 使用）。

    M1 确认前必须有 3–6 条结论摘要，夹具按需自动补一份。
    前提：覆盖停点全部完成或已送审且判据齐备，否则 milestone_confirm 会拒绝。"""
    import framework.engine as engine
    if str(mid) == "M1":
        notes = engine.milestone_notes_path(root, name, "M1")
        if not os.path.isfile(notes):
            write_milestone_notes(root, name, "M1")
    return engine.milestone_confirm(root, name, mid, confirm=confirm, pick=pick)


def decide(root, name, content, kind, stop, pick="通过", options="通过|其他"):
    """登记一条裁决（两步链路的测试口径）。

    记录类：`decision commit --kind 记录 --content …` 直接入库；
    方向/数值类：先 `problem add --kind 待裁决 --options …`，再按开发者点选
    `commit --from <问题号> --pick <选项>` 入库——走的正是红线动作的真实路径。
    返回 D 号。
    """
    from framework.engine import add_problem, commit_decision
    if kind == "记录":
        return commit_decision(root, name, content=content, kind=kind, stop=int(stop))
    pid = add_problem(root, name, "待裁决", int(stop), content, "测试夹具", options=options)
    chosen = options.split("|")[0] if pick not in options.split("|") else pick
    return commit_decision(root, name, content=content, kind=kind,
                           from_problem=pid, pick=chosen)


def plant_sample(root, name):
    """把 fixtures/sample 的停点 1-6 产物与 fixtures/mini 的 rtl/testbench
    放到 <name>/ 下，文件名与正文里的 sample 改成子系统名。"""
    base = os.path.join(root, name)
    for src, dest in (
        (os.path.join(checkout_root(), "framework", "fixtures", "sample"), base),
        (os.path.join(checkout_root(), "framework", "fixtures", "mini", "rtl"),
         os.path.join(base, "rtl")),
        (os.path.join(checkout_root(), "framework", "fixtures", "mini", "testbench"),
         os.path.join(base, "testbench")),
    ):
        for dirpath, _dirs, files in os.walk(src):
            rel = os.path.relpath(dirpath, src)
            target = dest if rel == "." else os.path.join(dest, rel)
            os.makedirs(target, exist_ok=True)
            for fn in files:
                if fn == ".gitkeep":
                    continue
                out = fn.replace("sample", name).replace("mini_top", name + "_top")
                with open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                    text = fh.read()
                with open(os.path.join(target, out), "w", encoding="utf-8") as fh:
                    fh.write(text.replace("sample", name))
    return base


class fake_terminal:
    """假装交互终端：在 TTY 下现场输入 quote。`calls` 记被问了几个照抄（T4 先查后问）。"""

    def __init__(self, quote):
        self.quote = quote
        self.calls = 0
        self._saved = None

    def __enter__(self):
        from framework import engine
        self._saved = (engine._stdin_is_tty, engine._read_line)
        engine._stdin_is_tty = lambda: True

        def _line(prompt=""):
            self.calls += 1
            return self.quote

        engine._read_line = _line
        return self

    def __exit__(self, *exc):
        from framework import engine
        engine._stdin_is_tty, engine._read_line = self._saved
        return False


class RepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.root = copy_repo()
        cls.addClassCleanup(shutil.rmtree, cls._tmp, True)
        cls._prev = {key: os.environ.get(key) for key in ("ADF_ROOT", "HOME", "ADF_RELEASE_TOKEN")}
        cls.home = os.path.join(cls.root, "home")
        os.makedirs(cls.home, exist_ok=True)
        os.environ["ADF_ROOT"] = cls.root
        os.environ["HOME"] = cls.home
        os.environ.pop("ADF_RELEASE_TOKEN", None)
        cls.addClassCleanup(cls._restore_env)
        from framework import engine
        saved_home = engine._home_dir
        engine._home_dir = lambda: cls.home
        cls.addClassCleanup(setattr, engine, "_home_dir", saved_home)
        # 默认假装"没有交互终端"：开发者可能就在真终端里跑 selftest，
        # 不挡这一下的话，关键停点的照抄提示会一直等输入。要 TTY 的用例用 fake_terminal。
        saved_tty = engine._stdin_is_tty
        engine._stdin_is_tty = lambda: False
        cls.addClassCleanup(setattr, engine, "_stdin_is_tty", saved_tty)

    @classmethod
    def _restore_env(cls):
        for key, value in cls._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
