# 作者：vick 邮箱：ykun@yk9811.com

"""子系统 state.json 与人读 Markdown 的渲染。"""

import contextlib
import datetime
import fcntl
import json
import os
import re
import shutil
import tempfile

from framework.flow import (
    DONE, NOT_STARTED, load, module_row_label, module_rows, product_path, stages,
)
from framework.paths import project_root

SYS_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
RESERVED = {"work", "dc", "pt", "lint", "framework", "toolchain", "rules", "script"}
TRACKED_DIRS = ("info_input", "flow_doc", "plan_doc", "spec_doc", "rtl", "testbench", "signoff")
TOOL_DIRS = ("work", "dc", "pt", "lint")
# 写前滚动备份，保留最近 3 版；目录落在子系统内，便于随产物一起审计。
STATE_BACKUP_DIR = ".state_backups"
STATE_BACKUP_KEEP = 3
# 跨进程事务锁；事件日志；schema 版本与迁移步骤表。
LOCK_FILE = ".state.lock"
EVENTS_FILE = "events.jsonl"
SCHEMA_VERSION = 4
# 事件在事务内先暂存到这个私有键下，提交前剥离，不进 state.json。
EVENT_STAGING_KEY = "_pending_events"
# load 时迁移确实改了内容就打上这个私有标记，提交前据此多留一份备份。
MIGRATION_MARKER_KEY = "_pre_migration_backup"
_DEFAULT_ACTOR = "主持者"


class StateEncodingError(ValueError):
    """state 里有无法编码为 UTF-8 的字符（如 lone surrogate），写盘前拒绝。"""


def now():
    """当前时间，精确到秒。

    旧记录是分钟粒度（`YYYY-MM-DD HH:MM`），与秒级串按字典序比较仍然成立
    （短串是长串的前缀），所以不需要改写历史数据。
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def root_of(start=None):
    if start:
        return os.path.abspath(start)
    return project_root()


def sys_dir(root, name):
    return os.path.join(root, name)


def state_path(root, name):
    return os.path.join(sys_dir(root, name), "state.json")


# 停点行的声明字段（blank() 的叶子；verify_state 用它做字段校验）。
STOP_FIELDS = ("id", "state", "done_at", "remark", "confirm_quote", "confirmed_at",
               "pending_digest", "fingerprint", "allow_violation")


def blank(name):
    model = load()
    stages_keys = [str(stage) for stage in stages()]
    stops = []
    for stop in model["stops"]:
        stops.append({
            "id": stop["id"],
            "state": NOT_STARTED,
            "done_at": "",
            "remark": "",
            "confirm_quote": "",
            "confirmed_at": "",
            "pending_digest": "",
            "fingerprint": "",
            # 带违例送审在行上留下的授权标记（tick 完成时按同一授权重跑闸门）。
            "allow_violation": False,
        })
    return {
        "sys_name": name,
        "position": {
            "where": "未开始",
            "next": "向 info_input/ 放入前置输入后启动停点 1",
            "updated": now(),
            "rule_version": "",
            "fingerprint": "",
        },
        "stops": stops,
        # 模块行集合由模型 review: 推导（rtl_review_per_module / rtl_review / tb_review）。
        "modules": {row: [] for row in module_rows()},
        "runs": [],
        # 分阶段分桶由模型 stages: 生成（D 号前缀与分阶段裁决表同源）。
        "decisions": {stage: [] for stage in stages_keys},
        "problems": [],
        "items": [],
        "summary": [],
        "resume": "目录已初始化。恢复入口：放入前置输入后执行 status。",
        "waivers": [],
        # 参考数据登记段：{id, data, gen, inputs[], digest, time}（见 golden_add）。
        "golden": [],
        # 可配置阈值段（如 marks_cap）；缺省即按框架口径（不限）。
        "thresholds": {},
        # 没有"修改队列"与 T 序号：收成两步（problem add → decision commit --from/--pick）。
        "seq": {"I": 0, "M": 0, "G": 0, "event": 0,
                "D": {stage: 0 for stage in stages_keys}},
    }


def _migrate_v1_to_v2(state):
    """v1 → v2 完整迁移。只对 schema < 2 的存量文件执行，幂等、可叠加：

    - 停点行剥 human/completed_once（迭代降级删除）；
    - loop_side 未闭合（tb|rtl|spec）→ 转成一条调试事项（kind=调试、side=loop_side、
      text 说明"由旧回路侧迁移"、领事项自己的 seq.M 号）；已闭合（closed）的丢弃；
    - 删 position.delegate（代判删除）与 enter_structure；
    - 模块条目补 author/reviewer 空字段（审查记录字段齐备）。

    迁移是否真的改了内容由 _read_state 比对，改了就在写盘前多留一份备份。
    """
    for row in state.get("stops") or []:
        row.pop("human", None)
        row.pop("completed_once", None)
    loop_side = state.pop("loop_side", "") or ""
    state.pop("loop_closed_at", None)
    state.pop("enter_structure", None)
    if isinstance(state.get("position"), dict):
        state["position"].pop("delegate", None)
    modules = state.get("modules") or {}
    for key in ("7", "8", "9"):
        for item in modules.get(key) or []:
            item.setdefault("author", "")
            item.setdefault("reviewer", "")
    if loop_side not in ("", "closed"):
        seq = state.setdefault("seq", {})
        seq["M"] = int(seq.get("M", 0)) + 1
        state["items"] = (state.get("items") or []) + [{
            "id": "M%03d" % seq["M"], "kind": "调试", "side": loop_side,
            "text": "由旧回路侧 %s 迁移" % loop_side,
            "approach": "", "rounds": 0, "evidence": [], "time": now(),
        }]


def _migrate_v2_to_v3(state):
    """v2 → v3：状态名改"已送审"、秒级时间戳与事件 seq、模块状态降级为证据、
    golden 登记段、停点行的 allow_violation 字段。

    - 停点状态 `待人工审核` → `已送审`（本迁移函数与规则正文里的旧名是唯一允许的历史引用）；
    - `problems` 删 `registered_line`：**保留这步的理由**是"兼容 v2 文件本身"——
      v2 的问题记录里带着这个字段，不在这里 pop 掉就会永远留在迁移后的 state.json 里
      变成死字段；证据时序只有一套口径（比事件 `seq`，见 _backfill_events）；
    - 模块条目只保留证据字段（rtl_review 的 digest/author/...）与显式"退回"覆盖，
      派生的 state 值删掉——状态改由文件与证据推导（engine.module_state）；
    - `seq` 增加 `event` 计数器（事件日志新行带单调递增 seq）、`G`（golden 序号）；
    - 停点行补 `allow_violation`；补 `golden: []`；
    - 历史事件回填由 `migrate()` 在拿到 events.jsonl 路径时调 `_backfill_events`。
    """
    for row in state.get("stops") or []:
        if row.get("state") == "待人工审核":
            row["state"] = "已送审"
        row.setdefault("allow_violation", False)
    for problem in state.get("problems") or []:
        problem.pop("registered_line", None)
    modules = state.get("modules") or {}
    for key in list(modules):
        for item in modules.get(key) or []:
            if item.get("state") != "退回":
                item.pop("state", None)
    seq = state.setdefault("seq", {})
    seq.setdefault("event", 0)
    seq.setdefault("G", 0)
    state.setdefault("golden", [])


def _migrate_v3_to_v4(state):
    """v3 → v4：问题类型"提示"退场、thresholds 段就位。

    - 存量 `kind="提示"` 的问题置 `open=False`（**不删数据**：kind 原样保留供审计），
      每条补一条"问题关闭"事件说明这是迁移动作；已关闭的不重复处理；
    - 补 `thresholds: {}`（可配置阈值的挂点，如 marks_cap）；
    - 旧 `handoff` → `resume` 的字段退场由 `migrate()` 的收尾钩子 `_retire_handoff`
      统一处理（不升版本号的字段退场，对 v4 文件也生效）。
    """
    closed = []
    for problem in state.get("problems") or []:
        if problem.get("kind") == "提示" and problem.get("open", True):
            problem["open"] = False
            problem["closed_at"] = now()
            problem["evidence"] = "v3→v4 迁移"
            closed.append(str(problem.get("id") or ""))
    state.setdefault("thresholds", {})
    for pid in [item for item in closed if item]:
        record_event(state, "问题关闭", obj=pid,
                     evidence="v3→v4 迁移：问题类型“提示”退场，置关闭（数据保留）")


def _retire_handoff(state):
    """旧 `handoff` 字段退场：文本搬进 `resume`（v4 起只有一个恢复入口）。

    不升版本号的字段退场，对任何版本的文件都生效；两侧都有时以 `resume` 为准。
    """
    old = state.pop("handoff", None)
    if old is not None and not state.get("resume"):
        state["resume"] = old
    state.setdefault("resume", "")


# 迁移步骤表：后续版本往里加一步并抬 SCHEMA_VERSION。
_MIGRATIONS = {1: _migrate_v1_to_v2, 2: _migrate_v2_to_v3, 3: _migrate_v3_to_v4}


def _retire_queue(state):
    """修改队列退场——存量队列条目转成"待裁决"问题。

    队列条目没有停点（旧模型里阶段由 `--step` 决定），所以迁成问题时一律挂停点 1，
    并在 source 里写明来源，由主持者按需重新登记到正确停点后点选入库；
    `dequeued`（已移出的条目）随队列一起退场——移出理由已在 events.jsonl 留痕。
    不做版本号变更：v3 文件若仍带队列，由 migrate() 的收尾钩子一并收敛。
    """
    queue = state.pop("queue", None)
    state.pop("dequeued", None)
    seq = state.setdefault("seq", {})
    for item in queue or []:
        seq["I"] = int(seq.get("I", 0)) + 1
        state.setdefault("problems", []).append({
            "id": "I%03d" % seq["I"], "kind": "待裁决", "stop": 1,
            "text": item.get("content", ""),
            "source": "由旧修改队列 %s 迁移（原条目没有停点，请核对所属停点）"
                      % item.get("id", ""),
            "time": item.get("time") or now(), "open": True, "options": [], "blocks": [],
        })
    state.get("seq", {}).pop("T", None)


def _backup_events(path, keep=STATE_BACKUP_KEEP):
    """回填前的事件日志备份：`<sys>/.state_backups/events_<时间戳>.jsonl`。

    与 state.json 的滚动备份同目录（`state_*` 前缀），便于一起审计。
    """
    if not os.path.isfile(path):
        return ""
    backup_dir = os.path.join(os.path.dirname(path), STATE_BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = os.path.join(backup_dir, "events_%s.jsonl" % stamp)
    shutil.copy2(path, target)
    names = sorted(fn for fn in os.listdir(backup_dir)
                   if fn.startswith("events_") and fn.endswith(".jsonl"))
    for old in names[:-keep]:
        os.remove(os.path.join(backup_dir, old))
    return target


def _backfill_events(events_path, state=None):
    """给历史事件行回填 `seq`（证据时序只有"比 seq"一套口径）。

    events.jsonl 是 append-only 日志：**按文件行序**依次赋单调递增 seq 是忠实的。
    已有 seq 的行原样保留（幂等——第二次加载一条都不缺，直接返回 0、不碰文件），
    只补缺失的行；`state["seq"]["event"]` 抬到回填后的最大值，新事件接着往下排。
    写入前先备份，再走同目录 mkstemp + os.replace 原子替换。
    返回回填条数（0 = 没缺、没动文件）。
    """
    if not events_path or not os.path.isfile(events_path):
        return 0
    with open(events_path, encoding="utf-8") as fh:
        raw = fh.read().splitlines()
    counter = 0
    assigned = 0
    out = []
    for line in raw:
        if not line.strip():
            out.append(line)
            continue
        try:
            event = json.loads(line)
        except (ValueError,):
            # 坏行原样保留（日志只追加不改写；坏行不该让迁移整体失败）。
            out.append(line)
            continue
        seq = event.get("seq")
        if isinstance(seq, int) and seq > counter:
            counter = seq
            out.append(line)
            continue
        counter += 1
        event["seq"] = counter
        out.append(json.dumps(event, ensure_ascii=False))
        assigned += 1
    # 计数器与日志对账：即使这次没有缺 seq 的行，也要把 state["seq"]["event"] 抬到
    # 日志里的最大值——否则"回填后新事件接着排"会从 0 重新开始（seq 就会撞号）。
    if state is not None:
        seq_map = state.setdefault("seq", {})
        seq_map["event"] = max(int(seq_map.get("event", 0)), counter)
    if not assigned:
        return 0
    _backup_events(events_path)
    _atomic_write(events_path, "\n".join(out) + "\n")
    return assigned


def migrate(state, events_path="", backfill=True):
    """按 schema 版本叠加迁移；每次 load 都走，对已是最新版的文件是空操作。

    收尾钩子处理"不升版本号的字段退场"：修改队列删掉后，老 v3 文件里可能
    还留着 `queue`/`seq.T`，见到就按 _retire_queue 收敛；`handoff` 退场后，
    任何版本的文件里见到旧字段都按 `_retire_handoff` 把文本搬进 `resume`。

    历史事件 seq 回填：拿到 `events_path` 时给历史事件行回填 `seq`（作者授权的
    红线动作，以代码里的迁移落地，不靠脚本手工改文件）；`backfill=False` 给只读
    路径用——`status` 这类命令不得写任何文件（含事件日志）。
    """
    version = int(state.get("schema") or 1)
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step:
            step(state)
        version += 1
        state["schema"] = version
    if "queue" in state or "T" in (state.get("seq") or {}):
        _retire_queue(state)
    _retire_handoff(state)
    if backfill:
        _backfill_events(events_path, state)
    return state


def _rule_version(root):
    import hashlib
    digest = hashlib.sha256()
    for base in ("rules", "framework"):
        start = os.path.join(root, base)
        if not os.path.isdir(start):
            continue
        for dirpath, dirnames, files in os.walk(start):
            dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
            for fn in sorted(files):
                if not fn.endswith((".py", ".md", ".yaml")):
                    continue
                path = os.path.join(dirpath, fn)
                digest.update(os.path.relpath(path, root).encode())
                with open(path, "rb") as fh:
                    digest.update(fh.read())
    return digest.hexdigest()[:12]


def load_state(root, name):
    """读盘并迁移（含历史事件 seq 回填）；文件缺失时抛 FileNotFoundError。"""
    path = state_path(root, name)
    if not os.path.isfile(path):
        raise FileNotFoundError("没有 %s，先执行 init" % name)
    with open(path, encoding="utf-8") as fh:
        return migrate(json.load(fh), os.path.join(sys_dir(root, name), EVENTS_FILE))


def _read_state(root, name, create=False, backfill=True):
    """锁内读盘：已迁移的 state；文件缺失时仅在 create（init_sys）下给空白版。

    schema 版本键由这里盖章而不进 blank()：blank() 的每个叶子都被
    test_stop_completion 的"无死字段"口径当作必须有独立写入路径的活字段，
    而 schema 只应随版本迁移与首建落盘，不随业务写入变化。
    迁移确实改动了内容时打上私有标记，_commit_state 在写盘前据此对
    迁移前的旧版多留一份备份。

    写路径（state_txn）顺带回填历史事件 seq；只读路径（state_read）
    传 backfill=False——`status` 这类命令不得写任何文件。
    """
    path = state_path(root, name)
    if not os.path.isfile(path):
        if create:
            state = blank(name)
            state["schema"] = SCHEMA_VERSION
            return state
        raise FileNotFoundError("没有 %s，先执行 init" % name)
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    before = json.dumps(state, sort_keys=True, ensure_ascii=False)
    migrate(state, os.path.join(sys_dir(root, name), EVENTS_FILE), backfill=backfill)
    if json.dumps(state, sort_keys=True, ensure_ascii=False) != before:
        state[MIGRATION_MARKER_KEY] = True
    return state


def _actor():
    """操作者取 ADF_ACTOR；主持者代执行时不传就是"主持者"。"""
    return os.environ.get("ADF_ACTOR") or _DEFAULT_ACTOR


def record_event(state, action, obj="", evidence=""):
    """在事务内暂存一条事件（动作、对象、证据引用），并领一个单调递增的事件序号。

    序号在**暂存时**就分配（记进 state["seq"]["event"]，随事务落盘），
    所以"问题登记"这类需要在同一次事务里拿到自己序号的调用方可以直接读
    `state["seq"]["event"]`。事件随事务提交追加到 <sys>/events.jsonl；暂存在私有键下，
    序列化前剥离，不进 state.json。evidence 可以是字符串（如 R 号、D 号、指纹）或列表。
    """
    seq = state.setdefault("seq", {})
    seq["event"] = int(seq.get("event", 0)) + 1
    state.setdefault(EVENT_STAGING_KEY, []).append({
        "action": action, "object": obj, "evidence": evidence, "seq": seq["event"],
    })


def _append_events(root, name, cmd, actor, events):
    """只追加不改写。没有显式事件的琐碎写入也落一行，保住"一次事务一行"的口径。

    每行带 seq：证据时序比 seq，不再靠事件行号或时间粒度的补丁。
    """
    if not events:
        events = [{"action": "状态写入", "object": "", "evidence": ""}]
    path = os.path.join(sys_dir(root, name), EVENTS_FILE)
    lines = []
    for event in events:
        lines.append(json.dumps({
            "time": now(),
            "seq": int(event.get("seq") or 0),
            "cmd": cmd or "save",
            "actor": actor or _actor(),
            "action": event.get("action", ""),
            "object": event.get("object", ""),
            "evidence": event.get("evidence", ""),
        }, ensure_ascii=False))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _commit_state(root, name, state, cmd="", actor=""):
    """统一提交路径：剥离事件暂存 → 迁移备份 → 刷新 position → 编码预校验
    → 滚动备份 → 原子替换 → 渲染 → 事件日志。编码失败在落盘前抛出，不碰任何文件。"""
    events = state.pop(EVENT_STAGING_KEY, [])
    if state.pop(MIGRATION_MARKER_KEY, False):
        # 本次写入来自一次真迁移，写盘前对迁移前的旧版多留一份备份
        #（此刻盘上还是迁移前的文件，_backup_state 拿到的正是它）。
        _backup_state(state_path(root, name))
    state["position"]["updated"] = now()
    state["position"]["rule_version"] = _rule_version(root)
    path = state_path(root, name)
    text = _encode_state(state)
    _backup_state(path)
    _atomic_write(path, text)
    # 事件先落 events.jsonl 再渲染——简报只从事件日志与 state 渲染，
    # 顺序换过来后本事务刚记的事件就能进同一次渲染出的简报。
    _append_events(root, name, cmd, actor, events)
    render(root, name, state)


@contextlib.contextmanager
def state_txn(root, name, cmd="", actor="", create=False):
    """事务写入（排他锁）：读（并迁移）→ 改 → 校验编码 → 备份 → 原子替换
    → 渲染 → 事件日志 → 释放锁。

    异常退出时不写任何文件；锁在 finally 里释放。cmd 是命令名（进事件日志），
    actor 缺省取 ADF_ACTOR。只有 init_sys 用 create=True 在文件缺失时建空白版。
    """
    base = sys_dir(root, name)
    if create:
        os.makedirs(base, exist_ok=True)
    fh = open(os.path.join(base, LOCK_FILE), "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        state = _read_state(root, name, create=create)
        yield state
        _commit_state(root, name, state, cmd=cmd, actor=actor)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def state_read(root, name):
    """只读助手（共享锁）：读盘并迁移，返回快照后立即释放；不写任何文件。

    status 等只读命令用它。不要在 state_txn 事务体内调用——同进程对同一把锁
    再加共享锁会自等死锁。事件 seq 回填会写日志，所以这里
    `backfill=False`——只读命令一个字都不写（历史回填交给下一次写命令）。
    """
    base = sys_dir(root, name)
    fh = open(os.path.join(base, LOCK_FILE), "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_SH)
        return _read_state(root, name, backfill=False)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _encode_state(state):
    """写前编码预校验，失败即拒绝写。

    2026-10-14 事故：`--confirm` 里的中文经 shell 变量展开在 `LC_ALL=C` 下变成
    lone surrogate，`json.dump` 写到一半抛 `UnicodeEncodeError`，而 save 是原地
    截断写，于是 `state.json` 只剩 857 字节。现在序列化与编码校验都在落盘之前完成，
    异常不会再破坏既有文件。
    """
    text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StateEncodingError(
            "state 含无法编码为 UTF-8 的字符（%s）：多为 --confirm 里的中文经 shell "
            "变量或命令替换展开成了代理对。请改用单引号字面量重试；本次未写入任何文件。"
            % exc
        ) from exc
    return text


def _backup_state(path, keep=STATE_BACKUP_KEEP):
    """写前把上一版留到 <sys>/.state_backups/，只保留最近 keep 份。"""
    if not os.path.isfile(path):
        return
    backup_dir = os.path.join(os.path.dirname(path), STATE_BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    shutil.copy2(path, os.path.join(backup_dir, "state_%s.json" % stamp))
    names = sorted(fn for fn in os.listdir(backup_dir)
                   if fn.startswith("state_") and fn.endswith(".json"))
    for old in names[:-keep]:
        os.remove(os.path.join(backup_dir, old))


def _atomic_write(path, text):
    """同目录唯一临时文件（mkstemp）→ fsync → os.replace。

    旧的固定 `state.json.tmp` 让并发进程互相踩踏（FileNotFoundError / 互相截断）；
    临时名唯一后，并发下各写各的，替换仍由锁串行化。
    """
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def save(root, name, state):
    """兼容入口（init_sys 与存量测试在用）：与 state_txn 走同一套编码/备份/原子写路径。

    不加锁：调用方是"读改写"里的写半步，事务语义由 state_txn 提供。
    """
    _commit_state(root, name, state, cmd="save")


# ---------- 参考数据登记段（golden 的持久化半边） ----------
# 记录形状：{id, data, gen, inputs[], digest, time}
#   data   产物相对路径（如 testbench/<dut>/data/x.txt）
#   gen    生成脚本相对路径
#   inputs 输入路径列表（脚本、规格、裁决等；生成脚本或输入改了即"需重新生成"）
#   digest 产物摘要（登记时算）
# 后续接上两处挂点：`golden <sys> register` CLI（调 golden_add）与行 10 新鲜度
# 闸门（用 golden_find/golden_records 判"生成脚本或输入改了"并要求被 TB 引用的数据都已登记）。


def golden_records(state):
    """已登记的参考数据记录（副本，调用方改不到 state）。"""
    return [dict(item) for item in state.get("golden") or []]


def golden_add(state, data, gen, inputs, digest):
    """登记一条参考数据；返回领到的 G 号。字段空值直接拒绝（登记才可追溯）。"""
    data = str(data or "").strip()
    gen = str(gen or "").strip()
    digest = str(digest or "").strip()
    inputs = [str(item).strip() for item in (inputs or []) if str(item).strip()]
    if not data or not gen or not digest:
        raise ValueError("参考数据登记要写明产物路径、生成脚本与产物摘要")
    if not inputs:
        raise ValueError("参考数据登记要写明至少一个输入路径（否则判不了新鲜度）")
    seq = state.setdefault("seq", {})
    seq["G"] = int(seq.get("G", 0)) + 1
    record = {"id": "G%03d" % seq["G"], "data": data, "gen": gen,
              "inputs": inputs, "digest": digest, "time": now()}
    state["golden"] = (state.get("golden") or []) + [record]
    return record["id"]


def golden_find(state, data):
    """按产物路径取登记记录（副本）；没有返回 None。"""
    target = str(data or "").strip()
    for record in state.get("golden") or []:
        if record.get("data") == target:
            return dict(record)
    return None


def verify_state(root, name):
    """只读校验 state.json —— JSON 可读、必需键齐全、裁决表能渲染。

    返回 (ok, message)；不写任何文件（渲染用纯函数 `_decision_md`）。
    """
    path = state_path(root, name)
    if not os.path.isfile(path):
        return False, "没有 %s" % path
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        return False, "state.json 不是合法 JSON：%s" % exc
    missing = [key for key in blank(name) if key not in state]
    if missing:
        return False, "缺必需键：%s" % ", ".join(missing)
    # 停点行的声明字段（blank() 的叶子）：少字段说明这份 state 还没走最新迁移，
    # 尤其 allow_violation——它是显式声明，不该留成隐式键。
    for row in state.get("stops") or []:
        absent = [key for key in STOP_FIELDS if key not in row]
        if absent:
            return False, "停点 %s 缺字段：%s（跑一次写命令触发迁移即可）" % (
                row.get("id"), ", ".join(absent))
    try:
        _decision_md(name, state)
    except Exception as exc:  # 渲染是唯一能证明结构可用的只读检查
        return False, "裁决表渲染失败：%s" % exc
    return True, "OK：%s（停点 %d 条，裁决 %d 条，runs %d 条）" % (
        name, len(state.get("stops") or []),
        sum(len(v) for v in (state.get("decisions") or {}).values()),
        len(state.get("runs") or []))


def stop_row(state, sid):
    for row in state["stops"]:
        if int(row["id"]) == int(sid):
            return row
    raise KeyError(sid)


def _cell(value, summary=False):
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if summary:
        text = text.split("\n", 1)[0]
    else:
        text = text.replace("\n", "<br>")
    return text.replace("|", "\\|")


def _md_row(cells, summary_at=None):
    rendered = []
    for index, cell in enumerate(cells):
        rendered.append(_cell(cell, summary=(summary_at is not None and index == summary_at)))
    return "| %s |" % " | ".join(rendered)


def _module_stale_note(root, name, state, row, mod):
    """行 7 模块标记对当前文件是否仍有效；判定逻辑在 engine，这里只取文案。

    延迟导入避免 state↔engine 循环依赖（engine 顶层导入 state）。
    """
    if str(row) != "7":
        return ""
    from framework import engine
    return engine.module_stale_note(state, sys_dir(root, name), row, mod)


# ---------- 开发者简报（<sys>/<sys>_brief.md） ----------

# 针对"开发者失去对进展的感知"的补偿：简报在每次事务提交后随状态文档一并重渲染，
# 固定四节、第一行就是"需要你做的：…"。只从 events.jsonl 与 state.json 渲染，
# 不手写、不写设计内容。
BRIEF_RUN_COUNT = 5
# "自上一个里程碑以来"收录的事件动作：
#   自动完成=tick 自动完成的停点；裁决入库=入库的裁决；事项收尾=L0/L1 回修
#   （L2/L3 是决策，不在此列）；问题关闭=关闭的阻断；复核恢复=级联复核恢复。
BRIEF_EVENT_ACTIONS = ("自动完成", "裁决入库", "事项收尾", "问题关闭", "复核恢复")
_BRIEF_ACTION_LABELS = {
    "自动完成": "自动完成",
    "裁决入库": "裁决入库",
    "事项收尾": "L0/L1 回修收尾",
    "问题关闭": "阻断关闭",
    "复核恢复": "复核恢复",
}
# 状态文档与简报里"最近小结"显示的条数（state["summary"] 只追加，按时间顺序）。
SUMMARY_SHOWN = 5


def _summary_lines(state, limit=SUMMARY_SHOWN):
    """最近 limit 条小结，一条一行带时间；文本压成单行，避免打断 Markdown 列表。"""
    lines = []
    for item in (state.get("summary") or [])[-limit:]:
        text = " ".join(str(item.get("text") or "").split())
        if text:
            lines.append("- %s %s" % (item.get("time") or "—", text))
    return lines


def _brief_todo(root, name, state):
    """第一节："需要你做的"。

    判定不另写一套：复用 tick 两张清单里的"需要开发者"（就绪待确认的里程碑、
    待裁决问题、被决策阻塞的工作、升级上报）。延迟导入避免 state↔engine
    循环依赖（engine 顶层导入 state，同 _module_stale_note 的注释）。
    """
    from framework import engine
    _, human = engine._tick_lists(root, name, state)
    out = []
    for entry in human:
        text = " ".join(str(entry).split())
        if text.startswith("- "):
            text = text[2:]
        if text and text not in out:
            out.append(text)
    return out


def _brief_since(state):
    """"自上一个里程碑以来"的时间基准：state["milestones"] 里最近一次确认的
    时间和 id；从未确认过则以"开始"为界。时间是分钟粒度字符串，直接比字典序。"""
    best = None
    for mid, row in (state.get("milestones") or {}).items():
        row = row or {}
        t = str(row.get("time") or "")
        if best is None or t >= best[0]:
            best = (t, mid, row)
    if best is None:
        return "", "开始", ""
    return best[0], "里程碑 %s %s · %s 之后" % (best[1], best[2].get("name") or "", best[0]), best[1]


def _brief_load_events(root, name):
    """读 events.jsonl（只追加日志）。坏行跳过，不抛错——渲染不能被日志绊倒。"""
    path = os.path.join(sys_dir(root, name), EVENTS_FILE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:  # 与 coverage.py 同款：坏行跳过，渲染不被日志绊倒
                del exc
                continue
            if isinstance(row, dict):
                events.append(row)
    return events


def _brief_since_lines(root, name, state):
    """第二节：自上一个里程碑以来的自动完成、入库裁决、L0/L1 回修、
    关闭的阻断与复核恢复，各自一行；无则"（无）"。

    时间基准是最近一次里程碑确认。时间只有分钟粒度，单靠 >= 会把确认前同一
    分钟的事务也算进来，所以有确认 id 时以事件日志里那条"里程碑确认"行为界，
    只收录其后的行；日志里找不到该行时才退回按时间比较（确认时刻之后，不含
    同分钟的旧行）。"""
    since, label, base_mid = _brief_since(state)
    lines = ["## 自上一个里程碑以来", "", "（基准：%s）" % label, ""]
    events = _brief_load_events(root, name)
    if base_mid:
        boundary = [i for i, ev in enumerate(events)
                    if ev.get("action") == "里程碑确认"
                    and str(ev.get("object") or "") == base_mid]
        candidates = events[boundary[-1] + 1:] if boundary else \
            [ev for ev in events if str(ev.get("time") or "") > since]
    else:
        candidates = events
    shown = []
    for event in candidates:
        action = event.get("action", "")
        if action not in BRIEF_EVENT_ACTIONS:
            continue
        if action == "事项收尾" and str(event.get("evidence") or "").split("；")[0].strip() not in ("L0", "L1"):
            continue  # L2/L3 收尾是决策，不属于"L0/L1 回修"
        text = "- %s %s：%s" % (event.get("time") or "—",
                                _BRIEF_ACTION_LABELS.get(action, action),
                                event.get("object") or "—")
        evidence = str(event.get("evidence") or "")
        if evidence:
            text += "；%s" % (evidence if len(evidence) <= 80 else evidence[:79] + "…")
        if text not in shown:
            shown.append(text)
    lines += shown or ["（无）"]
    summaries = _summary_lines(state)
    if summaries:
        lines += ["", "### 最近小结", ""] + summaries
    return lines


def _brief_risk_lines(root, name, state, model=None):
    """第三节：风险与在途事项，每条一句——在途调试事项（含 side/轮数）、
    未关闭阻断、被决策阻塞的工作、升级上报、待里程碑。"""
    from framework import engine
    lines = []
    threshold = engine._item_round_threshold(state)
    for item in state.get("items") or []:
        rounds = int(item.get("rounds") or 0)
        side = "，侧 %s" % item["side"] if item.get("side") else ""
        text = "- 在途%s %s%s：第 %d 轮；%s" % (
            item.get("kind") or "事项", item.get("id") or "—", side, rounds,
            item.get("text") or "")
        if rounds >= threshold:
            text += "（升级上报：已 %d 轮未收敛，阈值 %d）" % (rounds, threshold)
        lines.append(text)
    for p in state.get("problems") or []:
        if not p.get("open", True):
            continue
        if p.get("kind") == "阻断":
            lines.append("- 未关闭阻断 %s（停点 %s）：%s"
                         % (p.get("id"), p.get("stop"), p.get("text") or ""))
        if p.get("blocks"):
            lines.append("- 停点 %s 被 %s 阻塞：%s"
                         % ("、".join(str(b) for b in p["blocks"]), p.get("id"),
                            (p.get("text") or "")[:80]))
    # 待里程碑（派生显示态）：判定在 engine.display_state，这里只取文案。
    model = model if model is not None else load()
    for stop in model["stops"]:
        row = stop_row(state, stop["id"])
        if row["state"] == DONE:
            continue
        shown = engine.display_state(root, name, state, stop["id"], row)
        if shown.startswith("待里程碑"):
            matched = re.search(r"（(.+)）", shown)
            lines.append("- 停点 %d %s：%s（待里程碑，确认后置完成）"
                         % (stop["id"], stop["name"], shown))
            lines.append("  " + engine._milestone_command(
                name, matched.group(1) if matched else "", "confirm"))
    return lines


def _brief_run_lines(state):
    """第四节：最近 %d 条运行记录，每条一句结论（时间、能力、状态、摘要首行）。"""
    lines = []
    for run in (state.get("runs") or [])[-BRIEF_RUN_COUNT:]:
        summary = (run.get("summary") or "").split("\n", 1)[0]
        lines.append("- %s %s %s：%s" % (run.get("time") or "—",
                                         run.get("capability") or "—",
                                         run.get("status") or "—",
                                         summary or "（无摘要）"))
    return lines or ["（无）"]


def brief_sections(root, name, state, model=None):
    """简报四节，标题与顺序固定，返回 [第一节, 第二节, 第三节, 第四节]。

    1 "需要你做的：…"（一行，无则"需要你做的：无"）；
    2 自上一个里程碑以来；3 风险与在途事项；4 最近 5 条运行记录。
    只从 events.jsonl 与 state.json 渲染，不写设计内容。
    """
    todo = _brief_todo(root, name, state)
    first = "需要你做的：%s" % ("；".join(todo) if todo else "无")
    risk = ["## 风险与在途事项", ""] + (_brief_risk_lines(root, name, state, model) or ["（无）"])
    runs = ["## 最近 %d 条运行记录" % BRIEF_RUN_COUNT, ""] + _brief_run_lines(state)
    return [first, "\n".join(_brief_since_lines(root, name, state)),
            "\n".join(risk), "\n".join(runs)]


def brief_md(root, name, state, model=None):
    return "\n\n".join(brief_sections(root, name, state, model))


def brief_report(root, name):
    """status --brief——只打印前两节（"需要你做的"+"自上一个里程碑以来"），
    供主持者在会话里引用，不复述长文。只读，不写任何文件。"""
    state = state_read(root, name)
    return "\n\n".join(brief_sections(root, name, state)[:2])


def render(root, name, state):
    model = load()
    lines = [
        "# %s 开发状态" % name,
        "",
        "此文件由 state.json 渲染。改状态用 `python3 script/framework.py`，不要手改表。",
        "",
        "## 1. 当前位置",
        "",
        "- **所处环节**：%s" % state["position"]["where"],
        "- **下一步**：%s" % state["position"]["next"],
        "- **最近更新**：%s" % state["position"]["updated"],
        "- **框架规则版本**：%s" % (state["position"]["rule_version"] or "（未记录）"),
        "- **基线产出物指纹**：%s" % (state["position"]["fingerprint"] or "（未记录）"),
        "",
        "## 2. 流程状态",
        "",
        "| # | STEP | 停点 | 状态 | 产出物 | 完成时间 | 备注 |",
        "|---|------|------|------|--------|----------|------|",
    ]
    for stop in model["stops"]:
        row = stop_row(state, stop["id"])
        lines.append(_md_row([
            stop["id"], stop["step"], stop["name"], row["state"],
            product_path(stop, name), row["done_at"] or "—", row["remark"],
        ]))
    lines += [
        "",
        "## 3. 模块进度与在途事项",
        "",
    ]
    # 按模块分行，摘要不符时标注失效；不再把含 digest/confirm_quote 的原始 JSON 打进状态文档。
    stale_count = 0
    for row_id in module_rows():
        label = module_row_label(row_id)
        mods = state["modules"].get(row_id, [])
        if not mods:
            lines.append("- %s：（无）" % label)
            continue
        lines.append("- %s：" % label)
        from framework import engine
        base = sys_dir(root, name)
        for mod in mods:
            line = "  - %s：%s" % (mod.get("name"),
                                   engine.module_state(state, base, row_id, mod.get("name")))
            note = _module_stale_note(root, name, state, row_id, mod)
            if note:
                stale_count += 1
                line += "（%s）" % note
            lines.append(line)
    if stale_count:
        lines.append("- 标记失效：%d 个模块的 lint/审查标记已因文件改动失效，先重跑 run lint / review record" % stale_count)
    # 退回侧并进调试事项（side）；审查记录字段在模块条目上。
    # 在途调试/综合优化事项，一条一行，带侧别与轮数；end 即从清单消失。
    items = state.get("items") or []
    if items:
        lines.append("- 在途事项：")
        for item in items:
            side = "，侧 %s" % item["side"] if item.get("side") else ""
            rounds = int(item.get("rounds") or 0)
            lines.append("  - %s %s%s：%s；当前做法：%s；第 %d 轮"
                         % (item["id"], item["kind"], side, item["text"],
                            item.get("approach") or "（未写）", rounds))
    else:
        lines.append("- 在途事项：（无）")
    lines += [
        "",
        "## 4. 工具运行",
        "",
        "| 时间 | 能力 | 状态 | 摘要 |",
        "|------|------|------|------|",
    ]
    runs = state.get("runs") or []
    if not runs:
        lines.append(_md_row(["—", "—", "—", "（无）"]))
    for run in runs[-20:]:
        lines.append(_md_row([
            run.get("time", ""), run.get("capability", ""), run.get("status", ""),
            run.get("summary") or "",
        ], summary_at=3))
    lines += ["", "## 5. 待解决问题", "", "| 编号 | 类型 | 停点 | 描述 |", "|------|------|------|------|"]
    pending = []
    deferred = []
    for problem in state.get("problems") or []:
        if not problem.get("open", True):
            continue
        if problem.get("deferred"):
            deferred.append(problem)
        else:
            pending.append(problem)
    if not pending:
        lines.append(_md_row(["—", "—", "—", "（无）"]))
    for problem in pending:
        lines.append(_md_row([problem["id"], problem["kind"], problem["stop"], problem["text"]]))
    if deferred:
        lines += ["", "已推迟问题（条件满足后由 tick/status 重新列入需要开发者；"
                     "覆盖范围内的里程碑确认会拒绝）：", ""]
        for problem in deferred:
            info = problem.get("deferred") or {}
            lines.append("- %s（停点 %s，推迟至 %s）：%s（原因：%s）"
                         % (problem["id"], problem.get("stop", ""),
                            info.get("until") or "—", problem.get("text", ""),
                            info.get("reason") or "—"))
    lines += ["", "## 6. 恢复入口", "", state.get("resume") or "（无）", "",
              "### 最近小结", ""]
    lines += _summary_lines(state) or ["（无）"]
    lines.append("")
    _write(os.path.join(sys_dir(root, name), "%s_status.md" % name), "\n".join(lines))
    _write(os.path.join(sys_dir(root, name), "%s_decision.md" % name), _decision_md(name, state))
    # 开发者简报随每次事务一并重渲染（与状态文档、裁决表同一处）。
    _write(os.path.join(sys_dir(root, name), "%s_brief.md" % name),
           brief_md(root, name, state, model))


def _decision_note(row):
    """被 `override` 过的裁决在备注列标出修订次数。"""
    note = row.get("note", "")
    history = row.get("history") or []
    if not history:
        return note
    tag = "已修订 %d 次" % len(history)
    return "%s；%s" % (note, tag) if note else tag


def _decision_history_lines(rows):
    """列出 `override` 前的旧正文摘要，让"改了什么"在渲染物里看得见。"""
    out = []
    for row in rows:
        for index, old in enumerate(row.get("history") or [], 1):
            first = (old.get("content") or "").split("\n", 1)[0].strip()
            if len(first) > 80:
                first = first[:80] + "…"
            out.append("- `%s` 第 %d 次修订前（%s）：%s"
                       % (row.get("id", ""), index, old.get("kind") or "—", first))
    return out


def _decision_md(name, state):
    lines = [
        "# %s 裁决" % name,
        "",
        "此文件由 state.json 渲染。效力：裁决高于输入文档的强约束、权威、参考。",
        "",
        "## 1. 待裁决问题（点选后用 `python3 script/framework.py decision %s commit --from <问题号> --pick <选项> --kind <方向|数值>` 入库）"
        % name,
        "",
        "| 问题号 | 停点 | 问题原文 | 候选 |",
        "|--------|------|----------|------|",
    ]
    pending = [item for item in state.get("problems") or []
               if item.get("open", True) and item.get("kind") == "待裁决"
               and not item.get("deferred")]
    if not pending:
        lines.append(_md_row(["—", "—", "（无待裁决问题）", "—"]))
    for item in pending:
        lines.append(_md_row([item["id"], item.get("stop", ""), item.get("text", ""),
                              "|".join(item.get("options") or []) or "—"]))
    deferred = [item for item in state.get("problems") or []
                if item.get("open", True) and item.get("deferred")]
    lines += ["", "## 2. 已推迟问题", "",
              "| 问题号 | 停点 | 推迟至 | 原因 | 问题原文 |",
              "|--------|------|--------|------|----------|"]
    if not deferred:
        lines.append(_md_row(["—", "—", "—", "—", "（无已推迟问题）"]))
    for item in deferred:
        info = item.get("deferred") or {}
        lines.append(_md_row([item["id"], item.get("stop", ""),
                              info.get("until") or "—", info.get("reason") or "—",
                              item.get("text", "")]))
    # 分阶段裁决表：阶段集合与标题读模型 stages:（不写死阶段号）。
    from framework.flow import stage_title
    titles = {str(stage): stage_title(stage) for stage in stages()}
    lines += ["", "## 3. 分阶段裁决表", ""]
    for key, title in titles.items():
        lines += ["### %s" % title, "", "| 编号 | 类别 | 裁决内容 | 备注 |",
                  "|------|------|----------|------|"]
        rows = state["decisions"].get(key) or []
        if not rows:
            lines.append(_md_row(["—", "—", "（暂无裁决）", "—"]))
        for row in rows:
            lines.append(_md_row([row["id"], row.get("kind", ""), row["content"],
                                  _decision_note(row)]))
        history = _decision_history_lines(rows)
        if history:
            lines += ["", "修订链（`override` 前的旧正文）：", ""] + history
        lines.append("")
    return "\n".join(lines)


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def init_sys(root, name):
    if not SYS_NAME_RE.match(name) or name.lower() in RESERVED:
        raise ValueError("子系统名须字母开头，且不能占用保留目录名")
    base = sys_dir(root, name)
    os.makedirs(base, exist_ok=True)
    for d in TRACKED_DIRS:
        path = os.path.join(base, d)
        os.makedirs(path, exist_ok=True)
        keep = os.path.join(path, ".gitkeep")
        if not os.path.exists(keep):
            _write(keep, "")
    for d in TOOL_DIRS:
        os.makedirs(os.path.join(base, d), exist_ok=True)
    existed = os.path.isfile(state_path(root, name))
    with state_txn(root, name, cmd="init_sys", create=True) as state:
        if not existed:
            record_event(state, "初始化", obj=name)
    return state
