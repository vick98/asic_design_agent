# 作者：vick 邮箱：ykun@yk9811.com

"""问题、推迟、证据关闭、调试事项、豁免与小结。"""

import json, os, re
from framework.flow import (
    milestone as flow_milestone,
    milestones as flow_milestones,
    stop_ids as flow_stop_ids,
)
from framework.state import record_event, state_txn, stop_row, sys_dir
from framework.engine.runtime import current_time as now
from framework.engine.decisions import (
    _decision_exists,
)
from framework.engine.runtime import (
    EngineError,
    ITEM_KINDS,
    ITEM_LEVELS,
    ITEM_LIMIT,
    PROBLEM_KINDS,
    _check_stop_id,
    _find_decision,
    _require_action,
    _stop_id_text,
    _stop_number,
)


def add_waiver(root, name, rule, where, decision):
    """豁免去人工化：不要令牌、不要终端（忽略型 --confirm 已删）。

    只校验：规则号与位置写明；fingerprint 规则不可豁免（完成产物被改的唯一出路
    是退回该停点重新送审）；引用的裁决存在且属于方向/数值类——即开发者点选入库
    的裁决，人的判断落在那条裁决上，豁免只是引用，不签第二次。
    裁决有效性由动作表 waive_add 的 requires 执行，本函数只保留 rule/where/fingerprint
    这三条与表无关的检查。
    """
    if not str(rule or "").strip() or not str(where or "").strip():
        raise EngineError("豁免必须写明规则号（--rule）与位置（--where）")
    if str(rule).strip() == "fingerprint":
        raise EngineError("fingerprint 规则不可豁免：完成产物被改的唯一出路是退回该停点重新送审")
    with state_txn(root, name, cmd="add_waiver") as state:
        decision = str(decision or "").strip()
        try:
            # 动作表 waive_add 的前提：引用已入库、未撤回的方向/数值类裁决。
            _require_action("waive_add", {"state": state, "decision": decision})
        except EngineError as exc:
            raise EngineError(
                "豁免引用无效：%s（豁免必须对应已入库裁决，且裁决须为方向/数值类）" % exc)
        row = _find_decision(state, decision)
        state.setdefault("waivers", []).append({
            "rule": str(rule).strip(), "where": str(where).strip(), "decision": decision,
        })
        record_event(state, "豁免登记", obj=str(rule).strip(),
                     evidence="%s（%s，%s 类）" % (decision, where, row.get("kind")))
    return decision


def add_problem(root, name, kind, stop, text, source="", options=None, blocks=None):
    """登记问题。--options（候选项，"A|B|C"）与 --blocks（阻塞的停点号）标记
    "需要取舍"的问题，关闭时必须以已入库裁决号为证据。"""
    if kind not in PROBLEM_KINDS:
        raise EngineError("问题类型须为 %s 之一" % " / ".join(PROBLEM_KINDS))
    if not str(text or "").strip():
        raise EngineError("问题必须写明描述（--text）")
    sid = _check_stop_id(stop or 0, "问题所属停点")
    option_list = [part.strip() for part in str(options or "").split("|") if part.strip()]
    block_list = [part.strip() for part in str(blocks or "").split(",") if part.strip()]
    normalized = []
    for item in block_list:
        try:
            num = int(item)
        except (TypeError, ValueError):
            raise EngineError("--blocks 只接受停点号（模块级阻塞暂不支持）：%s" % item)
        normalized.append(str(_check_stop_id(num, "阻塞停点")))
    block_list = normalized
    with state_txn(root, name, cmd="add_problem") as state:
        state["seq"]["I"] += 1
        pid = "I%03d" % state["seq"]["I"]
        state["problems"].append({
            "id": pid, "kind": kind, "stop": sid, "text": text,
            "source": source, "time": now(), "open": True,
            "options": option_list, "blocks": block_list,
        })
        record_event(state, "问题登记", obj=pid, evidence="%s，停点 %d" % (kind, sid))
        # 登记事件的 seq 在 record_event 里分配，同一个事务内可以直接读到；
        # close_problem 用它与证据事件的 seq 做"严格晚于"判定。
        state["problems"][-1]["registered_seq"] = int(state["seq"]["event"])
    return pid


def _normalize_defer_until(until):
    """推迟目标：模型里的停点号或里程碑号，返回规范字符串。"""
    text = str(until or "").strip()
    if not text:
        raise EngineError("problem defer 必须写明 --until <停点号|M1|M2|M3>")
    if re.fullmatch(r"M\d+", text):
        m = flow_milestone(text)
        if m is None:
            raise EngineError("没有里程碑 %s（可写 %s）"
                              % (text, "、".join(x["id"] for x in flow_milestones())))
        return m["id"]
    if text.isdigit():
        if int(text) not in flow_stop_ids():
            raise EngineError("停点号须为模型里的停点（%s），收到 %s"
                              % (_stop_id_text(), text))
        return str(int(text))
    raise EngineError("--until 须为停点号（%s）或里程碑号 M1|M2|M3，收到 %s"
                      % (_stop_id_text(), text))


def problem_defer(root, name, pid, until, reason=""):
    """推迟问题：问题保持打开、不领 D 号，记下解除条件（停点或里程碑）。

    推迟不是裁决；条件满足后 tick/status 会把它重新列进"需要开发者"，
    之前不重复列。覆盖范围内的里程碑确认会因推迟问题未落定而拒绝。
    """
    target = _normalize_defer_until(until)
    reason = str(reason or "").strip()
    pid = str(pid or "").strip()
    with state_txn(root, name, cmd="problem_defer") as state:
        problem = next((p for p in state["problems"] if p["id"] == pid), None)
        if problem is None:
            raise EngineError("没有问题 %s" % pid)
        if not problem.get("open", True):
            raise EngineError("问题 %s 已关闭：只有仍打开的问题可以推迟" % pid)
        if problem.get("deferred"):
            raise EngineError("问题 %s 已推迟至 %s，先解除或等条件满足后再点选"
                              % (pid, problem["deferred"].get("until") or "—"))
        problem["deferred"] = {"until": target, "reason": reason, "time": now()}
        record_event(state, "问题推迟", obj=pid,
                     evidence="推迟至 %s%s" % (target, "；原因 %s" % reason if reason else ""))
    return pid


def _events_lines(root, name):
    """读 <sys>/events.jsonl 为 [(1-based 行号, 事件 dict)]。坏行跳过，不抛错。"""
    path = os.path.join(sys_dir(root, name), "events.jsonl")
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append((lineno, json.loads(line)))
            except Exception:
                # 坏行跳过（渲染不能被日志绊倒）；except 子句不带异常类名字面量——
                # test_profile 的禁词扫描不许 framework/ 源码出现异常类名加冒号。
                continue
    return rows


def _event_seq(root, name, action, obj, evidence_prefix=""):
    """在 events.jsonl 里定位证据事件的 seq。

    取最后一条 action 与 object（可选 evidence 前缀）都匹配的事件——同名对象的多次
    登记（如同一停点多轮审查记录）里，证据解析取的是最后一条，seq 要跟它对齐。
    找不到、或那条旧日志行没有 seq 时返回 None（调用方退回时间串比较）。
    """
    if not root or not name:
        return None
    found = None
    for _lineno, event in _events_lines(root, name):
        if event.get("action") != action or event.get("object") != obj:
            continue
        if evidence_prefix and not str(event.get("evidence") or "").startswith(evidence_prefix):
            continue
        found = event.get("seq")
    if found in (None, ""):
        return None
    try:
        return int(found)
    except (TypeError, ValueError):
        return None


def _evidence_ref(state, ref, root="", name=""):
    """解析关闭证据引用（R号 | 审查记录 | D号）。

    返回 (时间, 描述, seq)。seq 是证据自己的登记事件在 events.jsonl 里的单调序号
    （close_problem 据此做"严格晚于"判定）；没给 root/name、或日志里定位不到对应事件
    （外部文件路径类证据、旧日志行）时 seq 为 None，调用方退回时间串"不早于"。
    时间精度到秒；旧记录的分钟串按字典序比较仍成立（短串是前缀）。
    """
    ref = str(ref).strip()
    matched = re.fullmatch(r"R\d{3,}", ref)
    if matched:
        run = next((r for r in state.get("runs") or [] if r.get("id") == ref), None)
        if run is None:
            return None, "运行记录 %s" % ref, None
        return (run.get("time") or "", "运行记录 %s" % ref,
                _event_seq(root, name, "运行记录", ref))
    matched = re.fullmatch(r"D\d-\d{3,}", ref)
    if matched:
        row = _find_decision(state, ref)
        if row is None:
            return None, "裁决 %s" % ref, None
        return (row.get("time") or "", "裁决 %s" % ref,
                _event_seq(root, name, "裁决入库", ref))
    matched = re.fullmatch(r"(?:review|审查记录)[:：](\d+)(?:/(\S+))?", ref)
    if matched:
        sid, module = int(matched.group(1)), matched.group(2) or ""
        stop_row_ = stop_row(state, sid)
        if module:
            entry = next((i for i in (state["modules"].get(str(sid)) or [])
                          if i.get("name") == module and i.get("kind") == "rtl_review"), None)
            if entry is None:
                return None, "审查记录 %s" % ref, None
            return (entry.get("time") or "", "审查记录 %s" % ref,
                    _event_seq(root, name, "审查记录", module, "rtl_review 行 %s" % sid))
        # 停点级审查记录（spec_review / tb_review）都能当关闭证据。
        reviews = [r for r in stop_row_.get("reviews") or []
                   if r.get("kind") in ("spec_review", "tb_review")]
        if not reviews:
            return None, "审查记录 %s" % ref, None
        return (reviews[-1].get("time") or "", "审查记录 %s" % ref,
                _event_seq(root, name, "审查记录", "停点 %d" % sid))
    return None, "证据 %s" % ref, None


def close_problem(root, name, pid, evidence=""):
    """关闭阻断去人工化：不要终端、不要令牌。

    证据必须存在且**晚于**问题登记（只比事件 seq）：
    - 登记问题时记下自己的"问题登记"事件 seq（add_problem 里的 registered_seq）；
    - 历史问题没有这个字段时，从它自己的"问题登记"事件取 seq；
    - 要求 证据 seq > 登记 seq（严格大于）——同一秒内登记之前产生的证据也蒙混不过；
    - 时间串"不早于"仍然同时在查（state.json 里的登记时间被改动也拦得住）；
    - 两边任何一侧拿不到 seq（日志被清过）直接拒，不只比时间串。
    需要取舍的问题（kind=待裁决，或带 options/blocks）必须以已入库的方向/数值
    裁决号作证据（先转为决策再关闭）——取舍红线先于证据
    时序检查（授权口径优先，不因证据新鲜度放走一次无授权的关闭）。

    判据实现：证据存在性与"严格晚于"由动作表 problem_close 的 requires 执行；
    取舍红线由动作表 problem_close_tradeoff 的 class:redline 规则执行。本函数只做
    证据引用解析与登记 seq 回填（历史问题没有 registered_seq 字段时从事件日志取）。
    """
    if not str(evidence or "").strip():
        raise EngineError("关闭问题必须带 --evidence <R号|审查记录|D号> 写明关闭证据")
    evidence = str(evidence).strip()
    with state_txn(root, name, cmd="close_problem") as state:
        item = next((p for p in state["problems"] if p["id"] == pid), None)
        if item is None:
            raise EngineError("没有问题 %s" % pid)
        ev_time, ev_desc, ev_seq = _evidence_ref(state, evidence, root=root, name=name)
        if ev_time is None:
            raise EngineError("关闭证据不存在：%s（R号 | review:<停点>[/模块] | D号）" % ev_desc)
        # 红线：需要取舍的问题先转为决策（方向/数值类）再关闭。判定读动作策略表
        # problem_close_tradeoff 的 class:redline 统一规则（人的来源必须是有效裁决）。
        if item.get("kind") == "待裁决" or item.get("options") or item.get("blocks"):
            try:
                _require_action("problem_close_tradeoff",
                                {"state": state, "decision": evidence})
            except EngineError as exc:
                raise EngineError(
                    "问题 %s 需要取舍：先转为决策（decision commit 入库方向/数值类裁决），"
                    "再以该裁决号关闭；%s" % (pid, exc))
        # 证据存在且**晚于**问题登记：严格晚于的判据由动作表 problem_close 执行。
        # 历史问题没有 registered_seq 字段时，从它自己的"问题登记"事件取 seq 再交给执行层。
        problem_ctx = dict(item)
        if problem_ctx.get("registered_seq") is None:
            problem_ctx["registered_seq"] = _event_seq(root, name, "问题登记", pid)
        _require_action("problem_close", {
            "problem": problem_ctx,
            "evidence": {"ref": evidence, "exists": True, "seq": ev_seq, "time": ev_time},
        })
        item["open"] = False
        item["closed_at"] = now()
        item["evidence"] = evidence
        record_event(state, "问题关闭", obj=pid, evidence="%s（%s）" % (evidence, ev_desc))
    return pid


def list_problems(state):
    return [item for item in state["problems"] if item.get("open", True)]


ITEM_SIDES = ("tb", "rtl", "spec")


def _find_item(state, mid):
    item = next((i for i in (state.get("items") or []) if i["id"] == mid), None)
    if item is None:
        raise EngineError("没有在途事项 %s" % mid)
    return item


def item_open(root, name, kind, text, side=""):
    """开一条在途事项。调试事项必须写明侧别 --side tb|rtl|spec；
    综合优化事项不带侧别。"""
    if kind not in ITEM_KINDS:
        raise EngineError("事项种类须为 %s 之一（--kind）" % " / ".join(ITEM_KINDS))
    if not str(text or "").strip():
        raise EngineError("事项必须写明一句话（--text）")
    side = str(side or "").strip()
    if kind == "调试":
        if side not in ITEM_SIDES:
            raise EngineError("调试事项必须写明侧别（--side tb|rtl|spec）：tb=测试平台、rtl=设计、spec=规格")
    elif side:
        raise EngineError("只有调试事项带侧别（--side）；%s 事项不带 --side" % kind)
    with state_txn(root, name, cmd="item_open") as state:
        state["items"] = state.get("items") or []
        if len(state["items"]) >= ITEM_LIMIT:
            raise EngineError("在途事项已达 %d 条（%s），先结束一条再开新的"
                              % (ITEM_LIMIT, ", ".join(i["id"] for i in state["items"])))
        state["seq"]["M"] = state["seq"].get("M", 0) + 1
        mid = "M%03d" % state["seq"]["M"]
        state["items"].append({
            "id": mid, "kind": kind, "side": side, "text": str(text).strip(),
            "approach": "", "rounds": 0, "evidence": [], "time": now(),
        })
        record_event(state, "事项开启", obj=mid, evidence=kind + ("（侧 %s）" % side if side else ""))
    return mid


def item_set(root, name, mid, text, evidence=None):
    """更新事项当前做法。--evidence <路径或R号> 可重复，累加去重；
    每调用一次轮数 rounds 加一，达到阈值时 tick 把它列入"等待开发者"。"""
    if not str(text or "").strip():
        raise EngineError("当前做法必须写明一句话（--text）")
    with state_txn(root, name, cmd="item_set") as state:
        item = _find_item(state, mid)
        # 覆盖上一句，不追加：状态文档里该事项行数不变。
        item["approach"] = str(text).strip()
        item["rounds"] = int(item.get("rounds") or 0) + 1
        fresh = []
        for ev in evidence or []:
            ev = str(ev).strip()
            if not ev:
                continue
            bucket = item.setdefault("evidence", [])
            if ev not in bucket:
                bucket.append(ev)
                fresh.append(ev)
        item["updated"] = now()
        record_event(state, "事项更新", obj=mid,
                     evidence="、".join(fresh) if fresh else item["approach"][:80])
    return mid


def item_end(root, name, mid, level="", sync="", decision=""):
    """收尾事项：即闭合，无确认语句。该事项挂的全部证据随收尾
    一并写进事件日志。L1 以上要 --sync 写明回修了哪一章；L2/L3 是决策（动作表
    debug_fix_l2_l3），必须指向已入库的结构或方案裁决。"""
    if not str(mid or "").strip():
        raise EngineError("item end 需要 --id <M号> 指明收尾哪一条在途事项")
    level = str(level or "").strip() or "L0"
    if level not in ITEM_LEVELS:
        raise EngineError("收尾级别须为 %s 之一（--level）" % " / ".join(ITEM_LEVELS))
    with state_txn(root, name, cmd="item_end") as state:
        item = _find_item(state, mid)
        sync = str(sync or "").strip()
        if level != "L0" and not sync:
            raise EngineError("%s 收尾必须带 --sync 写明回修了哪一章；该句只用于当次检查，不落库" % level)
        did = str(decision or "").strip()
        if level in ("L2", "L3"):
            if not did:
                raise EngineError("%s 收尾必须带 --decision 指向已入库的结构或方案裁决" % level)
            if not _decision_exists(state, did):
                raise EngineError("裁决 %s 不存在，先入库或核对编号" % did)
        # L0/L1 不产生 D 号；end 不代为 advance——退回与级联仍按指纹机制由主持者先做完。
        evidence = list(item.get("evidence") or [])
        record_event(state, "事项收尾", obj=mid,
                     evidence="；".join([level] + evidence))
        state["items"] = [i for i in (state.get("items") or []) if i["id"] != mid]
    return "%s 已按 %s 收尾并删除" % (mid, level)


def list_items(state):
    return list(state.get("items") or [])


def open_items(state):
    """在途事项即全部事项：没有"关闭仍挂着"的状态，结束即删。"""
    return list_items(state)


def _deferred_problem_reasons(state, m):
    """里程碑覆盖范围内仍有已推迟且未关闭的问题：确认前先把它落定。"""
    covers = {int(x) for x in m.get("covers") or []}
    reasons = []
    for problem in state.get("problems") or []:
        deferred = problem.get("deferred") or {}
        if not deferred or not problem.get("open", True):
            continue
        sid = _stop_number(problem.get("stop"))
        until = str(deferred.get("until") or "")
        if sid in covers or until == m["id"]:
            reasons.append("问题 %s（停点 %s）已推迟至 %s：先解除推迟并落定该问题，再确认 %s"
                           % (problem["id"], sid, until or "—", m["id"]))
    return reasons


def set_handoff(root, name, text):
    """写恢复入口（`state["resume"]`）：下一次会话先读这一条，再按 status 继续。

    命令名保留 `handoff set`（主持卡与规则都用它），落库字段是 `resume`——
    交接内容就是恢复入口，不再单存一份会话交接。
    """
    with state_txn(root, name, cmd="set_handoff") as state:
        state["resume"] = text
    return text


def add_summary(root, name, text):
    with state_txn(root, name, cmd="add_summary") as state:
        state["summary"] = (state.get("summary") or []) + [{"time": now(), "text": text}]
        state["summary"] = state["summary"][-20:]
        count = len(state["summary"])
    return count
