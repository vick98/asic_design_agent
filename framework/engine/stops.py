# 作者：vick 邮箱：ykun@yk9811.com

"""停点推进：advance、送审、完成、级联、指纹、模块状态与 tick 自动相位。"""
from framework import policy
from framework.flow import (
    DONE as DONE, NOT_STARTED as NOT_STARTED,
    PENDING as PENDING, RUNNING as RUNNING,
    depends_on as flow_depends_on,
    dependents as flow_dependents,
    load as load,
    milestone_of_stop as flow_milestone_of_stop,
    module_rows as flow_module_rows,
    product_path as product_path,
    stop_blocked_by_items as flow_stop_blocked_by_items,
)
from framework.state import record_event, state_txn, stop_row
from framework.engine.runtime import current_time as now
from framework.engine.reviews import (
    _clear_module_override, _review_record_ok,
)
from framework.engine.runs import (
    inputs_digest,
)
from framework.engine.runtime import (
    EngineError, SIGNOFF_FOLDER,
    _covers, _milestone_blocking, decision_blockers as _decision_blockers,
    _milestone_done_stops, _product_digest,
    _require_action, _stop_done_ctx, refresh_position as _refresh_position,
)
from framework.engine.signoff import _require_gates

ADVANCE_NARROWED = ("已由 tick 自动处理：停点的启动、普通送审与完成由 "
                    "`python3 script/framework.py tick <sys>` 负责；advance 只保留"
                    "退回进行中（--to 进行中）与带违例送审（--to 已送审 --allow-violation）")

def _previous_done(state, sid):
    """启动停点前的依赖检查：depends_on 全部"定稿"才允许启动。

    "定稿"= 已完成（审核通过），或该依赖停点**由里程碑完成**（动作表
    stop_done_milestone 的 stops）且已送审（已送审/待里程碑）。
    后者是必需的：动作表里由里程碑完成归属的停点只能由里程碑确认置完成，而 M3
    覆盖的停点又要求先送审；若坚持依赖停点必须"已完成"，行 12（依赖行 11）与 M3
    会互相等待成死锁（行 12 起不来 → M3 确认不了 → 行 11 完不成 → 行 12 起不来）。

    返回未定稿的依赖停点号列表（空列表 = 全部定稿，可以启动）；拒绝消息据此
    点名缺失依赖（depends_on 不再是"上一行"，消息不能写死 sid-1）。
    """
    if sid <= 1:
        return []
    deps = flow_depends_on(sid) or [sid - 1]
    milestone_done = _milestone_done_stops()
    missing = []
    for dep in deps:
        row = stop_row(state, dep)
        if row["state"] == DONE:
            continue
        if row["state"] == PENDING and dep in milestone_done:
            continue
        missing.append(dep)
    return missing


def advance(root, name, sid, to_state, allow_violation=False, decision=""):
    """停点推进（命令行瘦身后只剩两种真用法）：

    - `--to 进行中`：主动重做——从"已送审/完成"退回进行中，清确认痕迹并按依赖级联；
    - `--to 已送审 --allow-violation`：带违例送审（红线，要裁决号），
      送审后仍由 `tick` 在判据齐备时置完成。

    其余调用（启动、普通送审、置完成）归 `tick`：不改任何状态，打印一句说明并按成功退出。
    `--confirm`/`--enter-structure`/`--loop-side` 不是本命令的参数。
    """
    model = load()
    if to_state not in model["states"]:
        raise EngineError("状态须为：%s" % " / ".join(model["states"]))
    stop = model["by_id"].get(sid)
    if stop is None:
        raise EngineError("没有停点 %s" % sid)
    with state_txn(root, name, cmd="advance") as state:
        return _advance_txn(root, name, model, state, sid, to_state, stop,
                            allow_violation, decision)


def _send_stop(root, name, state, stop, allow_violation=False):
    """把停点置为送审态：跑闸门、记送审摘要、清该行的模块"退回"覆盖。

    `advance`（带违例送审）与 `tick`（里程碑归属停点的送审相位）共用这一处，不要另写一套。
    模块通过态由证据推导（module_state），这里不再按闸门名写模块状态——只把该行模块的
    显式"退回"覆盖清掉（闸门过了 = 退回指令已执行完）。带违例送审在行上留
    `allow_violation` 标记：完成时 tick 按同一授权重跑闸门。
    """
    sid = int(stop["id"])
    row = stop_row(state, sid)
    _require_gates(root, name, state, stop, allow_violation)
    # 通过闸门后记下送审摘要；完成时摘要必须一致。
    row["pending_digest"] = _pending_digest(root, name, stop)
    if allow_violation:
        row["allow_violation"] = True
    _clear_module_override(state, sid)


def _advance_txn(root, name, model, state, sid, to_state, stop,
                 allow_violation, decision):
    row = stop_row(state, sid)
    previous = row["state"]
    # 退回进行中永远允许，否则阻断项会把人锁死在坏状态里；带违例送审是第二条保留用法。
    retreat = to_state == RUNNING and row["state"] in (PENDING, DONE)
    violation_send = to_state == PENDING and allow_violation
    if not retreat and not violation_send:
        return "停点 %d：%s" % (sid, ADVANCE_NARROWED)
    allowed = (model.get("transitions") or {}).get(row["state"]) or []
    if to_state not in allowed:
        raise EngineError("不允许从 %s 转到 %s" % (row["state"], to_state))
    if not retreat and any(p.get("kind") == "阻断" and p.get("open", True)
                           and int(p.get("stop") or 0) <= sid for p in state["problems"]):
        raise EngineError("停点 %d 或更早存在阻断项，先清掉再推进" % sid)
    if not retreat:
        stale = stale_stops(root, name, state, skip=sid)
        if stale:
            raise EngineError(stale_message(name, stale))

    # 红线：带违例送审要裁决号（人的判断落在裁决的点选来源上）；
    # 闸门与摘要检查在裁决号检查之前做完。
    if allow_violation and to_state in (PENDING, DONE):
        _require_violation_decision(state, decision)

    # 常驻判据：存在在途调试事项时被 blocked_by_items 覆盖的停点不得置已送审
    # （替代"行 10 回路侧未闭合不得送审"）；退回进行中不受这条限制（否则 L1/L2
    # 无法在事项还开着时退回）。范围读 flow_model.yaml 的 blocked_by_items: 字段。
    if (to_state == PENDING and flow_stop_blocked_by_items(sid)
            and (state.get("items") or [])):
        raise EngineError(
            "存在在途调试事项（%s）：先按级别收尾（item end），再置已送审"
            % ", ".join(i["id"] for i in state["items"]))

    if row["state"] == NOT_STARTED and to_state != NOT_STARTED:
        missing = _previous_done(state, sid)
        if missing:
            raise EngineError(
                "依赖停点 %s 尚未完成（已完成，或里程碑覆盖停点已送审），不能启动停点 %d"
                % ("、".join(str(dep) for dep in missing), sid))
        # 被当前不作数的里程碑（未确认或需复核）阻塞的停点在其确认前不得启动。
        mid = _milestone_blocking(root, name, state, sid)
        if mid:
            raise EngineError(
                "停点 %d 被里程碑 %s 阻塞：先 python3 script/framework.py milestone %s show --id %s "
                "出审阅包并 confirm，再启动"
                % (sid, mid, name, mid))

    if to_state == PENDING:
        _send_stop(root, name, state, stop, allow_violation)
        if allow_violation:
            # 签核记录要写"带违例送审的裁决号"——事件日志是这条留痕的落点
            # （不新加 state 字段，避免隐式键与 schema 变更）。
            record_event(state, "带违例送审", obj="停点 %d" % sid,
                         evidence="裁决 %s" % decision)

    if to_state == RUNNING:
        # 退回进行中后，上一次"完成"的确认痕迹不再代表这一版（现场发现：
        # status 文档会照抄 done_at，state.json 会留着 confirm_quote）。
        _clear_confirmation(row)
    row["state"] = to_state
    if previous == DONE and to_state == RUNNING:
        _cascade(state, sid, "停点 %d" % sid)
    state["position"]["where"] = "停点 %d %s（%s）" % (sid, stop["name"], to_state)
    state["position"]["next"] = "完成停点 %d 的产出或审核" % sid
    record_event(state, "停点状态", obj="停点 %d" % sid, evidence="%s → %s" % (previous, to_state))
    return "停点 %d → %s" % (sid, to_state)


def _finish_stop(root, name, state, sid, quote=""):
    """把判据已满足、停在"已送审"的停点置为完成落库（advance、tick、
    里程碑确认三处共用；调用方负责 row["state"] = DONE 与记事件）。

    - 送审摘要：产物与送审时不一致则拒绝；
    - 自动完成不写确认语句；里程碑确认传入开发者原话（quote）；
    - 指纹只在判据通过后写入；级联退回标记随重推完成清掉。
    """
    stop = load()["by_id"][int(sid)]
    row = stop_row(state, sid)
    pending = row.get("pending_digest") or ""
    if pending and _pending_digest(root, name, stop) != pending:
        raise EngineError("送审后产物已改动（停点 %d），退回进行中后重新送审" % sid)
    row["done_at"] = now()
    row["confirmed_at"] = row["done_at"]
    if quote:
        row["confirm_quote"] = quote
    if "变更待重推" in (row.get("remark") or ""):
        # 级联重推已完成：清掉退回标记，status 不再显示过期级联行。
        row["remark"] = ""
    # 级联退回的复核恢复标记随重推完成一并清掉——这一版是重推后的新完成，
    # 不再是被级联退回的那一版，recover_cascaded 不应再看到它。
    for key in ("cascaded_at", "cascaded_from", "cascaded_fingerprint"):
        row[key] = ""
    # 指纹只在闸门通过后写入。
    row["fingerprint"] = _product_digest(root, name, stop)
    state["position"]["fingerprint"] = row["fingerprint"]
    state["position"]["where"] = "停点 %d %s（%s）" % (sid, stop["name"], DONE)
    state["position"]["next"] = "继续下一未完成停点"
    return row["fingerprint"]


def _require_violation_decision(state, decision):
    """红线：带违例送审必须带已入库的方向/数值裁决号（有效性读动作策略表）。

    "--decision 没写"这条缺参文案留在引擎（表只描述前提，不描述命令行参数写法）；
    裁决存在/未撤回/方向数值类由 allow_violation 的 requires 执行。
    """
    did = str(decision or "").strip()
    if not did:
        raise EngineError("带违例送审是红线动作：--allow-violation 必须带 --decision <D号>")
    _require_action("allow_violation", {"state": state, "decision": did})


def auto_complete_check(root, name, state, sid, allow_violation=False):
    """自动完成判据，advance、tick 与 milestone confirm 共用（不要另写一套）。

    返回 dict：
      ok                 bool，全部判据通过、可以置完成；
      waiting_milestone  bool，停点由里程碑覆盖完成（动作表 stop_done_milestone 的
                         stops），不自动完成、标记"待里程碑"，由 milestone
                         confirm 处理；
      milestone          覆盖里程碑 id（waiting_milestone 时非空，否则 ""）；
      reasons            未通过原因列表（每条一句，可直接进事件日志或输出）。
                         waiting_milestone 时也照常给出其余判据的检查结果：
                         reasons 为空即"只差里程碑确认"（显示层据此标"待里程碑"）；
      review             判据引用的独立审查记录描述（供事件日志引用；`review:` 取 none 的停点以
                         闸门与运行记录为审查依据，此时为空串）。

    判据：闸门通过（run_gates，allow_violation 透传）；无未关闭阻断（stop<=sid）；
    `blocked_by_items:` 为真的停点无在途调试事项；有对得上当前产物指纹的独立审查
    记录——审查要求读停点的 `review:` 字段（flow.stop_review）：spec_review / tb_review 绑
    _product_digest，rtl_review_per_module 绑模块摘要，rtl_review 绑顶层产物指纹，
    none 不另要求审查记录。范围与要求都只来自 flow_model.yaml，本函数不写死停点号。
    送审摘要（pending_digest）的一致性不在这里查，由完成落库（_finish_stop）把关。
    执行层：reasons 聚合之后，动作表 stop_done_auto 的 requires 由 policy.require 统一
    过一遍；表里新增前提而展示层还不会表达时，拒绝原因并入 reasons（ok 随之变假）。
    """
    reasons = []
    ms = flow_milestone_of_stop(sid) if int(sid) in _milestone_done_stops() else None
    # 闸门（复用唯一入口；allow_violation 的红线校验由 advance 在之前做完）。
    from framework.gates.run import run_gates
    findings = run_gates(root, name, sid, state, allow_violation=allow_violation)
    blocking = [item for item in findings if item.get("level") != "hint"]
    if blocking:
        item = blocking[0]
        reasons.append("闸门未过：[%s] %s" % (item.get("rule", "?"), item.get("detail") or item))
    # 未关闭阻断（与 advance 的推进检查同口径）。
    open_blocking = [p for p in state.get("problems") or []
                     if p.get("kind") == "阻断" and p.get("open", True)
                     and int(p.get("stop") or 0) <= int(sid)]
    if open_blocking:
        reasons.append("存在未关闭阻断（%s）" % "、".join(p["id"] for p in open_blocking))
    decision_blocked = _decision_blockers(state, sid)
    if decision_blocked:
        reasons.append("被决策阻塞（%s）：先裁决并关闭问题" % "、".join(decision_blocked))
    # 在途调试事项挡被 blocked_by_items 覆盖的停点（常驻判据，范围读字段）。
    items = state.get("items") or []
    if flow_stop_blocked_by_items(sid) and items:
        reasons.append("存在在途调试事项（%s）" % ", ".join(i["id"] for i in items))
    # 独立审查记录对得上当前产物指纹。
    review_ok, review_reason, review_ref = _review_record_ok(root, name, state, sid)
    if not review_ok:
        reasons.append(review_reason)
    # 执行层：动作表 stop_done_auto 的前提逐条过一遍。reasons 是给 tick/status 展示的
    # 聚合结果，这里不抛异常打断只读路径；表里新增前提而展示层还不会表达时，把它补进
    # reasons（ok 随之变假），保证"表变了引擎行为就变"。
    try:
        policy.require("stop_done_auto",
                       _stop_done_ctx(state, sid, findings, review_ok, review_reason, review_ref))
    except policy.PolicyError as exc:
        if not reasons:
            reasons.append(str(exc))
    return {"ok": not reasons, "waiting_milestone": ms is not None,
            "milestone": (ms or {}).get("id", ""), "reasons": reasons,
            "review": review_ref}


def _dependent_closure(sid):
    """停点 sid 的传递下游闭包（不含 sid 自身）。

    flow_model.yaml 的 depends_on 是唯一事实源：沿 flow.dependents（直接下游）
    逐层展开到闭包。行 8 的依赖含 4 与 7，所以退回 3 会覆盖 4..12 全部、
    退回 9 只覆盖 10 与 12（11 只依赖 7、8）。
    """
    source = int(sid)
    out, pending = set(), [source]
    while pending:
        cur = pending.pop()
        for dep in flow_dependents(cur):
            if dep != source and dep not in out:
                out.add(dep)
                pending.append(dep)
    return out


def _cascade(state, sid, reason):
    """按依赖级联：停点 sid 退回进行中时，只把**依赖闭包内（下游）且已启动**
    （进行中/已送审/完成）的停点退回进行中；未开始的不动。返回被退回的停点号。

    每个被级联停点：
    - 记复核恢复标记 cascaded_at / cascaded_from / cascaded_fingerprint（退回前的
      产物指纹——_clear_confirmation 会清掉行上的 fingerprint，恢复判定
      （recover_cascaded）要拿"退回前指纹"与当前产物重算值比对，故先另存；
      行上已有标记时保留最早那份基线，避免二次级联把可比对基线抹成空）；
    - 沿用 _clear_confirmation 清掉"完成"的确认痕迹（不变量：退回与级联清确认痕迹）；
    - 记事件：谁级联了谁、原因。
    不变量：退回进行中永远允许；未关闭阻断挡推进（退回不受限）。
    """
    closure = _dependent_closure(sid)
    cascaded = []
    for row in state["stops"]:
        target = int(row["id"])
        if target not in closure or row["state"] == NOT_STARTED:
            continue
        previous = row["state"]
        if not row.get("cascaded_fingerprint"):
            row["cascaded_fingerprint"] = row.get("fingerprint") or ""
        row["cascaded_at"] = now()
        row["cascaded_from"] = int(sid)
        _clear_confirmation(row)
        row["state"] = RUNNING
        row["remark"] = "上游 %s 变更待重推" % reason
        cascaded.append(target)
        record_event(state, "级联退回", obj="停点 %d" % target,
                     evidence="由 %s 按依赖闭包级联，原因 %s；%s → %s"
                              % (sid, reason, previous, RUNNING))
    return cascaded


def _clear_confirmation(row):
    """清掉行上的"完成"痕迹：确认原话、完成时间、产物指纹与带违例送审授权。

    退回进行中或由上游级联退回后，这些值只属于过去的那一版；
    留着会让 `state.json` 与 `*_status.md` 看着像"这一版已经确认过"。
    历史仍在 `state.json` 的 git 记录里。
    """
    for key in ("done_at", "confirmed_at", "confirm_quote", "fingerprint"):
        row[key] = ""
    # 带违例送审的授权只对这一版有效：退回后要重新送审、重新授权。
    row["allow_violation"] = False


def _cascade_decision(state, target, did, model):
    """裁决级联：受影响停点是映射后的停点号，不是阶段号。"""
    row = stop_row(state, target)
    base = row["remark"].split("；")[0].strip()
    row["remark"] = ("%s；裁决 %s 已入库" % (base, did)) if base else "裁决 %s 已入库" % did
    cascaded = _cascade(state, target, did)
    if cascaded:
        first = min(cascaded)
        name = (model["by_id"].get(first) or {}).get("name", "")
        state["position"]["where"] = "停点 %d %s（%s，上游裁决 %s 变更）" % (first, name, RUNNING, did)
        _refresh_position(state, model)
    return cascaded


def _pending_digest(root, name, stop):
    """送审基线。签核产物本身随确认原话变化，用输入摘要当基线。"""
    if str(stop.get("product") or "").startswith(SIGNOFF_FOLDER + "/"):
        return "inputs:" + inputs_digest(root, name)
    return _product_digest(root, name, stop)


def stale_stops(root, name, state, skip=None):
    """已完成、但产物在完成后有改动的停点号；不一致即阻断推进。

    对称回滚（2026-10-18 开发者裁决）：凡已完成且行上指纹与当前产物不一致的停点
    全部列出——同一批产物被相邻停点共同覆盖（行 5/6 共用 spec_doc/，行 4 的子系统
    规格书在其下）时，只退"负责送审的那个停点"会让被豁免一侧的指纹永久陈旧，毒化
    里程碑复核。行 8 顶层文件在行 7 目录之下的子路径豁免由 _product_digest 的
    后继产物摘要排除承担，不在本函数重复。改动落在行 5/6 完成之后的行为是
    5、6 一起退回重推；落在行 4 完成之后则是 4、5、6 一起退回。
    """
    model = load()
    stale = []
    for stop in model["stops"]:
        sid = stop["id"]
        row = stop_row(state, sid)
        if sid == skip or row["state"] != DONE or not row.get("fingerprint"):
            continue
        if _product_digest(root, name, stop) == row["fingerprint"]:
            continue
        stale.append(sid)
    return stale


def stale_message(name, sids):
    first = min(sids)
    return ("停点 %s 的产物在完成后有改动，先退回停点 %d 重新送审"
            "（其依赖闭包下游已启动的行会按依赖级联退回）："
            "python3 script/framework.py advance %s --stop %d --to 进行中") % (
        "、".join(str(sid) for sid in sids), first, name, first)


TICK_MAX_ROUNDS = 12


def recover_cascaded(root, name, state):
    """复核恢复的候选停点：被级联退回过（cascaded_at 标记，见 _cascade）
    且当前停在"进行中"的停点号列表。

    标记方案：_cascade 在停点行写 cascaded_at / cascaded_from / cascaded_fingerprint
    （退回前的产物指纹），重推完成（_finish_stop）或复核恢复时清掉。选停点行标记
    而不是回溯事件日志：恢复判定要的是"退回前指纹"这个值本身，行上读一个键即可，
    不必解析 events.jsonl。

    这里只给候选；"指纹未变、闸门重跑通过、审查记录仍对得上当前产物"的核对在
    _tick_auto_complete 的事务内做（auto_complete_check 覆盖后两条）。里程碑覆盖
    完成的停点（动作表 stop_done_milestone，行 6/11/12）不进候选——它们按原规则
    走送审与 milestone confirm，不被 tick 误恢复成完成。
    """
    skip = _milestone_done_stops()
    out = []
    for row in state["stops"]:
        sid = int(row["id"])
        if row["state"] == RUNNING and row.get("cascaded_at") and sid not in skip:
            out.append(sid)
    return out


def _tick_auto_complete(root, name):
    """tick 的写半步：一个事务里循环四相位，直到某一轮没有任何动作为止。

    四相位按轮执行（上限 TICK_MAX_ROUNDS 轮）：
    ① 指纹失效退回：最早一个"已完成但产物已变"的停点退回进行中，并按依赖级联，记事件
       "指纹失效退回"（每轮最多退一个，级联已覆盖下游）；
    ② 自动启动：依赖定稿、未被里程碑阻塞、无未关闭阻断的未开始停点置进行中，记"自动启动"；
    ③ 完成/送审：进行中（或已送审）且判据齐备的停点——自动归属的直接完成（记"自动完成"），
       里程碑归属的置送审态（显示"待里程碑"，记"自动送审"）；
    ④ 复核恢复：本 tick 开始前就被级联退回、且自身指纹未变的停点恢复完成（记"复核恢复"）。

    前一行在同一 tick 里完成后，后一行在下一轮自动启动、判据齐备即完成。
    返回 dict：各相位动作的停点号列表（汇总所有轮次）、未收敛的 (停点号, 原因) 与轮数。
    """
    actions = {"done": [], "recovered": [], "started": [],
               "sent": [], "retreated": [], "refused": []}
    rounds = 0
    with state_txn(root, name, cmd="tick") as state:
        model = load()
        # 恢复候选按本 tick 开始时的状态算。本 tick 新级联出来的停点既不在相位③里直接
        # 完成、也不在同一 tick 里恢复——留到重推后再由下一次 tick 复核。
        recovering = set(recover_cascaded(root, name, state))
        deferred = set()
        refused_seen = set()
        for _round in range(TICK_MAX_ROUNDS):
            rounds += 1
            moved = False

            # ① 指纹失效退回。
            stale = stale_stops(root, name, state)
            if stale:
                sid = min(stale)
                row = stop_row(state, sid)
                _clear_confirmation(row)
                row["state"] = RUNNING
                row["remark"] = "产物在完成后有改动，指纹失效退回"
                cascaded = _cascade(state, sid, "停点 %d 指纹失效" % sid)
                deferred.update(int(x) for x in cascaded)
                record_event(state, "指纹失效退回", obj="停点 %d" % sid,
                             evidence="产物与完成时指纹不一致，退回重做；级联退回 %s"
                                      % ("、".join(str(x) for x in cascaded) or "无"))
                actions["retreated"].append(sid)
                moved = True

            # ② 自动启动。
            for stop in model["stops"]:
                sid = int(stop["id"])
                row = stop_row(state, sid)
                if row["state"] != NOT_STARTED:
                    continue
                if _previous_done(state, sid):
                    continue
                if _milestone_blocking(root, name, state, sid):
                    continue
                if _decision_blockers(state, sid):
                    continue
                if any(p.get("kind") == "阻断" and p.get("open", True)
                       and int(p.get("stop") or 0) <= sid for p in state.get("problems") or []):
                    continue
                row["state"] = RUNNING
                state["position"]["where"] = "停点 %d %s（%s）" % (sid, stop["name"], RUNNING)
                state["position"]["next"] = "完成停点 %d 的产出后跑 tick" % sid
                record_event(state, "自动启动", obj="停点 %d" % sid,
                             evidence="依赖已定稿、未被里程碑阻塞，由 tick 置进行中")
                actions["started"].append(sid)
                moved = True

            # ③ 完成 / 送审。
            for stop in model["stops"]:
                sid = int(stop["id"])
                row = stop_row(state, sid)
                if row["state"] not in (RUNNING, PENDING) or sid in deferred:
                    continue
                if _decision_blockers(state, sid):
                    continue
                if sid in recovering:
                    # 级联候选里"自身产物未变"的交给相位④按"复核恢复"处理（事件语义不变）；
                    # 产物已改的必须走正常完成路径，否则重做完也永远出不去。
                    marker = row.get("cascaded_fingerprint") or ""
                    if marker and _product_digest(root, name, stop) == marker:
                        continue
                allow = bool(row.get("allow_violation"))
                check = auto_complete_check(root, name, state, sid, allow_violation=allow)
                if check["reasons"]:
                    continue
                if check["waiting_milestone"]:
                    if row["state"] == RUNNING:
                        _send_stop(root, name, state, stop, allow_violation=allow)
                        row["state"] = PENDING
                        record_event(state, "自动送审", obj="停点 %d" % sid,
                                     evidence="判据齐备；由里程碑 %s 收口，置待里程碑"
                                              % check["milestone"])
                        actions["sent"].append(sid)
                        moved = True
                    continue
                if row["state"] == PENDING:
                    pending = row.get("pending_digest") or ""
                    if pending and _pending_digest(root, name, stop) != pending:
                        key = (sid, "送审后产物已改动，先退回进行中重做")
                        if key not in refused_seen:
                            refused_seen.add(key)
                            actions["refused"].append(key)
                        continue
                else:
                    # 进行中的停点以完成时的判据为准，旧的送审基线作废。
                    row["pending_digest"] = _pending_digest(root, name, stop)
                _finish_stop(root, name, state, sid)
                row["state"] = DONE
                record_event(state, "自动完成", obj="停点 %d" % sid,
                             evidence="闸门通过；审查记录 %s；指纹 %s"
                                      % (check.get("review") or "（以闸门与运行记录为准）",
                                         row["fingerprint"]))
                actions["done"].append(sid)
                moved = True

            # ④ 复核恢复：被级联退回的停点若自身产物指纹未变（当前产物重算摘要与退回前
            #    记录的 cascaded_fingerprint 一致）、闸门重跑通过、审查记录仍对得上当前产物
            #    （auto_complete_check 覆盖后两条），自动置完成并记"复核恢复"事件，不需要
            #    开发者重新确认；产物改过或判据不齐的保持进行中，由清单说明原因。
            for sid in sorted(recovering):
                sid = int(sid)
                row = stop_row(state, sid)
                if row["state"] != RUNNING:
                    continue
                stop = model["by_id"][sid]
                marker = row.get("cascaded_fingerprint") or ""
                digest = _product_digest(root, name, stop)
                if not marker or digest != marker:
                    continue
                check = auto_complete_check(root, name, state, sid)
                if check["waiting_milestone"] or check["reasons"]:
                    continue
                row["state"] = DONE
                row["fingerprint"] = digest
                row["done_at"] = now()
                row["confirmed_at"] = row["done_at"]
                row["remark"] = ""
                for key in ("cascaded_at", "cascaded_from", "cascaded_fingerprint"):
                    row[key] = ""
                record_event(state, "复核恢复", obj="停点 %d" % sid,
                             evidence="指纹未变（%s）；闸门重跑通过；审查记录 %s 对得上当前产物"
                                      % (digest, check.get("review") or "（以闸门与运行记录为准）"))
                actions["recovered"].append(sid)
                moved = True

            if not moved:
                break
        _refresh_position(state, model)
    actions["rounds"] = rounds
    return actions


def set_module(root, name, row, mod, status):
    """模块状态去手工登记：只保留显式"退回"。

    模块清单由文件推导、通过态由证据推导（lint 记录、审查记录、连接核对、用例核对），
    所以这里只接受 `--state 退回`：记一条覆盖并把该行退回进行中，等重新登记证据。
    """
    if str(status) != "退回":
        raise EngineError(
            "模块状态只接受 退回（模块清单与通过态由文件与证据推导，不再手工登记；"
            "要给行 %s 的 %s 标 %s 请改证据：lint 记录、review record 或闸门）"
            % (row, mod, status))
    if str(row) not in flow_module_rows():
        raise EngineError("行 %s 不是模块行（模块行集合由模型 review: 推导：%s）"
                          % (row, " / ".join(flow_module_rows())))
    with state_txn(root, name, cmd="set_module") as state:
        items = state["modules"].setdefault(str(row), [])
        found = next((item for item in items if item.get("name") == mod), None)
        if found is None:
            items.append({"name": mod, "state": "退回"})
        else:
            found["state"] = "退回"
        row_state = stop_row(state, int(row))
        _clear_confirmation(row_state)
        row_state["state"] = "进行中"
        state["position"]["where"] = "停点 %s 因 %s 退回" % (row, mod)
        _refresh_position(state, load())
        record_event(state, "模块退回", obj="%s（行 %s）" % (mod, row),
                     evidence="显式退回：通过态改由证据推导，等重新登记 lint/审查/闸门证据")
    return "%s 行 %s → 退回" % (mod, row)
