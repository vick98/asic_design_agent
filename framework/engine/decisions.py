# 作者：vick 邮箱：ykun@yk9811.com

"""裁决入库、改写、撤回与重合度守卫。"""

import os, re
from framework.flow import (
    load as load,
)
from framework.state import record_event, state_txn, sys_dir
from framework.engine.runtime import current_time as now
from framework.engine.runtime import (
    DEFER_PICK,
    EngineError,
    KINDS,
    _find_decision,
    _require_action,
    stage_of_stop,
)
from framework.engine.stops import (
    _cascade_decision,
)


_GRAM_STRIP = re.compile(r"[\s，。、；：（）()\[\]【】`*<>《》\"'\-—→＝=/|]")


def _content_grams(text):
    """把裁决正文压成字符三元组集合，用于判"是不是同一条内容"。"""
    flat = _GRAM_STRIP.sub("", text or "")
    if len(flat) < 3:
        return {flat} if flat else set()
    return {flat[i:i + 3] for i in range(len(flat) - 2)}


def content_overlaps(state, content, threshold=0.6, limit=3):
    """返回与已有裁决正文高度重合的条目 [(重合度, D 号, 正文)]。

    一个内容只保留一条裁决（见 rules/decision.md）；修订型条目应该用
    `decision override` 改写在原编号下，而不是取新号。自动判定只看字符
    三元组重合度，故只做"拦一下并要求写明理由"，不做终审。
    """
    grams = _content_grams(content)
    if len(grams) < 6:
        return []
    hits = []
    for step in sorted(state.get("decisions") or {}):
        for row in state["decisions"][step] or []:
            other = _content_grams(row.get("content", ""))
            if not other:
                continue
            score = len(grams & other) / float(min(len(grams), len(other)))
            if score >= threshold:
                hits.append((score, row["id"], row.get("content", "")))
    hits.sort(key=lambda item: (-item[0], item[1]))
    return hits[:limit]


def _overlap_guard(state, content, force, reason, what):
    """同一内容只保留一条裁决：重合度达到阈值时拦下，要求改走 override。

    返回命中的重合条目，供调用方在放行时把理由记进备注。
    """
    hits = content_overlaps(state, content)
    if not hits or (force and reason):
        return hits
    listed = "；".join(
        "%s（重合 %.0f%%：%s…）" % (did, score * 100.0, body[:36])
        for score, did, body in hits
    )
    raise EngineError(
        "%s的正文与已有裁决高度重合：%s。一个内容只保留一条裁决——"
        "修订型条目请改用 decision %s override --id <D号> --content \"...\" "
        "在原编号下改写（旧正文进 history）；确属新内容才用 --force --reason 放行"
        % (what, listed, state["sys_name"])
    )


def commit_decision(root, name, content="", kind="", from_problem="", pick="", source="",
                    stop=None, note="", force=False, reason=""):
    """两步链路的第二步：点选即入库。

    - `--kind 记录`：直接入库，不经问题与队列；
    - `--kind 方向|数值`：必须有点选来源——`--from <待裁决问题号> --pick <选项>`
      （来自开发者点选），或来自 mark 的收割（`source="mark:<文件>:<行>"`，开发者亲笔）；
      入库后**自动关闭**该问题、按 `--stop`（缺省取问题的停点）级联；
    - 阶段号由停点的 stage 字段推导（stage_of_stop）；命令只认 `--stop`。
    """
    with state_txn(root, name, cmd="commit_decision") as state:
        return _commit_decision_txn(root, name, state, content, kind, from_problem, pick,
                                    source, stop, note, force, reason)


_FMT_HINT_RE = re.compile(r"<\s*\d+\s*,\s*\d+\s*,\s*[A-Za-z]\s*>")


_UNIT_HINT_RE = re.compile(r"\d\s*(位|bit|MHz|kHz|GHz|Hz|ns|us|ms|拍|级|字|样点)", re.I)


def _spec_module_names(root, name):
    """spec_doc/ 下的模块名清单（<模块>_spec.md）；目录缺失或为空返回空表。"""
    base = os.path.join(sys_dir(root, name), "spec_doc")
    if not os.path.isdir(base):
        return []
    return sorted(fn[:-len("_spec.md")] for fn in os.listdir(base)
                  if fn.endswith("_spec.md") and len(fn) > len("_spec.md"))


def record_kind_hints(root, name, content):
    """记录类正文疑似方向/数值类的提示，返回原因列表（空列表=无提示）。

    命中口径：位宽格式 <w,f,t>；裸数字加单位（16 位、32MHz…）；模块名
    （取 spec_doc/ 的模块清单，取不到就只用前两条启发式）。由命令输出提示，
    里程碑审阅包据此高亮。
    """
    text = content or ""
    hints = []
    if _FMT_HINT_RE.search(text):
        hints.append("含位宽格式 <w,f,t>")
    if _UNIT_HINT_RE.search(text):
        hints.append("含裸数字加单位")
    modules = _spec_module_names(root, name)
    if modules:
        hit = [m for m in modules if re.search(r"\b%s\b" % re.escape(m), text)]
        if hit:
            hints.append("含模块名 %s" % "、".join(hit[:3]))
    return hints


def _commit_decision_txn(root, name, state, content="", kind="", from_problem="", pick="",
                         source="", stop=None, note="", force=False, reason=""):
    """两步链路的第二步（事务体）：点选来源 → 领 D 号 → 关问题 → 级联。

    防线都在这里：方向/数值类必须有点选来源（`--from/--pick` 或 mark 收割），
    `--force` 不放行"无来源"这一条；`_overlap_guard`（一个内容一条裁决）与
    `record_kind_hints`（记录类防夹带）原样保留在新路径上。
    """
    if kind not in KINDS:
        raise EngineError("裁决类别必填，须为 %s 之一（--kind）" % " / ".join(KINDS))
    human = kind in ("方向", "数值")
    what = "方向或数值类裁决入库" if human else "记录类裁决入库"
    content = str(content or "").strip()
    source = str(source or "").strip()
    from_problem = str(from_problem or "").strip()
    pick = str(pick or "").strip()
    if pick == DEFER_PICK:
        raise EngineError(
            "“%s”不是裁决：问题保持打开，改用 problem %s defer --id <问题号> "
            "--until <停点号|M1|M2|M3> [--reason \"…\"] 标推迟，条件满足后再点选入库"
            % (DEFER_PICK, name))
    problem = None
    if from_problem:
        problem = next((p for p in state["problems"] if p["id"] == from_problem), None)
        if problem is None:
            raise EngineError("没有待裁决问题 %s" % from_problem)
        if not problem.get("open", True):
            raise EngineError("问题 %s 已关闭：一条问题只对应一次点选入库" % from_problem)
        options = [str(x) for x in (problem.get("options") or [])]
        if not pick:
            raise EngineError(
                "从问题 %s 入库必须带 --pick 写明开发者点选的选项%s"
                % (from_problem, "（%s）" % "、".join(options) if options else ""))
        if options and pick not in options:
            raise EngineError("--pick %s 不在问题 %s 的候选里（%s）"
                              % (pick, from_problem, "、".join(options)))
        if not content:
            # 缺省正文带上问题原文：只留选项标签时看不出这是哪件问题的选择。
            problem_text = str(problem.get("text") or "")
            content = "%s：%s" % (problem_text, pick) if problem_text else pick
        source = "%s/%s" % (from_problem, pick)
    elif source.startswith("mark"):
        if not pick:
            # mark 是开发者亲笔，正文本身就是被点选的内容；pick 记原文来源。
            pick = "mark"
    if human:
        # 红线动作的前提由动作策略表执行。这个动作的"点选来源"只有两种：从待裁决
        # 问题点选（--from/--pick）或 mark 收割（开发者亲笔）；裸 --pick 不构成来源，
        # 所以不把它塞进 ctx['pick']——由表的 class:redline 规则拒绝。
        source_ctx = {"state": state, "from_problem": from_problem}
        if from_problem or source.startswith("mark"):
            source_ctx["pick"] = pick
        _require_action("decision_directional", source_ctx)
    if content == DEFER_PICK:
        raise EngineError(
            "“%s”不是裁决正文：改用 problem %s defer --id <问题号> "
            "--until <停点号|M1|M2|M3> 标推迟，条件满足后再点选入库"
            % (DEFER_PICK, name))
    if not content:
        raise EngineError("入库正文为空：请带 --content 写明裁决正文")
    # 一个内容只保留一条裁决：新号只给新内容，修订型走 override（rules/decision.md）。
    overlaps = _overlap_guard(state, content, force, reason, what)
    target = int(stop) if stop else int((problem or {}).get("stop") or 0)
    if not target:
        raise EngineError("入库必须写明停点（--stop）：它决定阶段号与级联起点")
    step = stage_of_stop(target)
    state["seq"]["D"][step] += 1
    did = "D%s-%03d" % (step, state["seq"]["D"][step])
    note2 = note
    if force and reason and overlaps:
        note2 = (note2 + "；重合放行理由：" + reason).strip("；")
    state["decisions"][step].append({
        "id": did, "content": content, "note": note2, "kind": kind,
        "time": now(),          # 关闭问题要用证据序号晚于问题登记
        "stop": target,         # override 的级联起点（入库时记下的停点）
        "source": source,       # 点选来源：I00x/选项 或 mark:<文件>:<行>
    })
    if problem is not None:
        # 入库即关闭该问题，证据就是这条裁决（同一事务里登记 seq 更小，天然"晚于"）。
        problem["open"] = False
        problem["closed_at"] = now()
        problem["evidence"] = did
        record_event(state, "问题关闭", obj=problem["id"], evidence="%s（%s）" % (did, source))
    if kind != "记录":
        # 记录类不承载变更语义，不级联；"产物偷改"由指纹提示与 tick/advance 的
        # pending_digest 校验独立兜底。方向/数值类照旧级联。
        _cascade_decision(state, target, did, load())
    record_event(state, "裁决入库", obj=did,
                 evidence="类别 %s；阶段 %s；停点 %d；来源 %s；问题原文 %s；点选 %s"
                          % (kind, step, target, source or "（无）",
                             (problem or {}).get("text", "—"), pick or "—"))
    return did


def _decision_exists(state, did):
    """裁决存在且未被撤回——撤回的裁决不再是有效证据。"""
    row = _find_decision(state, did)
    return bool(row) and not row.get("withdrawn")


def _guard_kind_change(state, row, kind):
    """方向或数值类裁决不许降级成记录。人确认不在这里做，见 require_human 的说明。"""
    del state
    target = kind or row.get("kind") or ""
    if target not in KINDS:
        raise EngineError("裁决类别须为 %s 之一" % " / ".join(KINDS))
    if row.get("kind") in ("方向", "数值") and target != row.get("kind"):
        raise EngineError("%s 是%s类裁决，不能改成%s" % (row["id"], row["kind"], target))
    return target


def withdraw_decision(root, name, did):
    """撤回：只标"已撤回"并保留历史（不删条目、不领新号）。

    撤回后这条裁决不再是有效证据：`_decision_exists`/`--allow-violation` 都会拒它。
    """
    with state_txn(root, name, cmd="withdraw_decision") as state:
        row = _find_decision(state, did)
        if row is None:
            raise EngineError("没有裁决 %s" % did)
        if row.get("withdrawn"):
            raise EngineError("裁决 %s 已经撤回" % did)
        row["withdrawn"] = True
        row["withdrawn_at"] = now()
        record_event(state, "裁决撤回", obj=did,
                     evidence="只标注已撤回、保留历史；节点 %s" % (row.get("stop") or "—"))
    return did


def override_decision(root, name, did, content, note="", kind=""):
    """修订链：在原编号下改写，旧正文进 history。

    方向/数值类的改动仍触发级联——级联起点读该裁决自己的 `stop`（入库时记下）。
    """
    with state_txn(root, name, cmd="override_decision") as state:
        row = _find_decision(state, did)
        if row is None:
            raise EngineError("没有裁决 %s" % did)
        if row.get("withdrawn"):
            raise EngineError("裁决 %s 已撤回：撤回的裁决不再改写，请用新问题点选入库" % did)
        target = _guard_kind_change(state, row, kind)
        row.setdefault("history", []).append({
            "content": row["content"], "note": row.get("note", ""), "kind": row.get("kind", ""),
        })
        row["content"] = content
        row["kind"] = target
        if note:
            row["note"] = note
        if target != "记录":
            # override 与 commit 同口径——方向/数值类改动触发级联，
            # `_cascade` 按依赖闭包级联：只把该裁决所打停点的下游
            # （depends_on 传递闭包）内、已启动（进行中/已送审/完成）的停点
            # **退回进行中**（标"上游裁决变更待重推"、清确认痕迹、留复核恢复
            # 标记），未启动的不动；不是"只标不退回"。被级联停点产物未变的，
            # tick 依 recover_cascaded 自动复核恢复。
            target_stop = int(row.get("stop") or 0)
            if target_stop:
                _cascade_decision(state, target_stop, did, load())
        record_event(state, "裁决改写", obj=did, evidence="类别 %s；旧正文进 history" % target)
    return did
