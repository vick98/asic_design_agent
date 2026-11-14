# 作者：vick 邮箱：ykun@yk9811.com

"""tick/status 的清单结构、机器可读输出与文本渲染。"""

from framework.flow import (
    DONE as DONE,
    NOT_STARTED as NOT_STARTED,
    PENDING as PENDING,
    RUNNING as RUNNING,
    load as load,
    milestone as flow_milestone,
    milestone_of_stop as flow_milestone_of_stop,
    milestones as flow_milestones,
)
from framework.state import state_read, stop_row, sys_dir, verify_state
from framework.engine.milestones import (
    _deferred_due,
    _milestone_readiness,
)
from framework.engine.reviews import (
    stale_module_count,
)
from framework.engine.runtime import (
    _milestone_blocking,
    _milestone_done_stops,
    _product_digest,
    _stop_number,
    _upstream_milestones,
    _next_command,
    _tick_command,
    _milestone_command,
    _decision_command,
    decision_blockers as _decision_blockers,
    deferred_still_blocks as _deferred_still_blocks,
    milestone_valid,
)
from framework.engine.stops import (
    _previous_done,
    _tick_auto_complete,
    auto_complete_check,
    stale_message,
    stale_stops,
)


ITEM_ROUND_THRESHOLD = 5


CASCADE_RECOVER_MARKER = "变更待重推"


TICK_TODO_TITLE = "可推进的工作："


TICK_HUMAN_TITLE = "需要开发者："


def _item_round_threshold(state):
    """升级上报轮数阈值，默认 ITEM_ROUND_THRESHOLD，state 可配置。"""
    try:
        return int((state.get("thresholds") or {}).get("item_rounds") or ITEM_ROUND_THRESHOLD)
    except (TypeError, ValueError):
        return ITEM_ROUND_THRESHOLD


def _recover_note(root, name, state, sid, row):
    """tick 清单里被级联退回停点的一句说明：为什么没（还没）被复核恢复。"""
    remark = (row.get("remark") or "").strip("；")
    if int(sid) in _milestone_done_stops():
        return "%s；本停点由里程碑覆盖完成，不走复核恢复，判据齐备后 tick 自动置待里程碑，再 milestone confirm" % remark
    marker = row.get("cascaded_fingerprint") or ""
    if not marker:
        return "%s；退回前没有产物指纹可比对，不能自动复核恢复，重跑闸门与审查后跑 tick 自动完成" % remark
    if _product_digest(root, name, load()["by_id"][int(sid)]) != marker:
        return "%s；产物已改动（指纹与退回前不一致），不能自动复核恢复，重跑闸门与审查后跑 tick 自动完成" % remark
    check = auto_complete_check(root, name, state, int(sid))
    if check["reasons"]:
        return "%s；产物指纹未变但复核判据未满足（%s）" % (remark, "；".join(check["reasons"]))
    return "%s；产物指纹未变且复核判据齐备，跑 tick 即自动复核恢复" % remark


def _todo_item(kind, text, command, stop=None, reasons=None, ident=None):
    """todo 清单的结构项：机器可读字段 + 渲染用 text（文本里加 "- " 前缀即可）。"""
    return {"stop": stop, "kind": kind, "reasons": list(reasons or []),
            "command": command, "id": ident, "text": text}


def _human_item(kind, text, command, ident=None, stop=None, reasons=None):
    """human 清单的结构项：等开发者处理的事项（kind 见 CLI --json 口径）。"""
    return {"kind": kind, "id": ident, "stop": stop, "text": text,
            "command": command, "reasons": list(reasons or [])}


def _tick_data_lists(root, name, state):
    """tick 两张清单的结构：todo 是智能体可推进的工作，human 是等开发者的事项。

    每项都带建议命令 command；text 是文本版里那一行的内容（渲染时加 "- "）。
    """
    model = load()
    todo, human = [], []
    blocked_by_ms = {}
    tick_cmd = _tick_command(name)
    # 运行记录里的工具版本与剖面 expect_versions 不一致：智能体的活（核对/重跑），
    # 归 todo——不进"需要开发者"；只看运行记录的 note，不回读原始日志。
    for run in state.get("runs") or []:
        note = str(run.get("note") or "")
        if "工具版本" in note and "不一致" in note:
            capability = str(run.get("capability") or "sim")
            todo.append(_todo_item(
                "fix",
                "运行记录 %s：%s（核对剖面 expect_versions 后重跑）"
                % (run.get("id", ""), note),
                "python3 script/framework.py run %s --sys %s" % (capability, name),
                reasons=[note]))
    # 里程碑：未确认的就绪提示、已确认的有效性复核。
    for m in flow_milestones():
        mid = m["id"]
        blocks = [int(x) for x in m.get("blocks") or []]
        valid = milestone_valid(root, name, state, mid)
        ready, reasons = _milestone_readiness(root, name, state, m)
        if valid["confirmed"]:
            if valid["needs_review"]:
                changed = "、".join(str(s) for s in valid["changed"])
                if not reasons:
                    human.append(_human_item(
                        "milestone",
                        "里程碑 %s 需复核（%s）：变更停点 %s；先 %s 出增量审阅包，"
                        "再 %s 复核"
                        % (mid, m.get("name", ""), changed,
                           _milestone_command(name, mid, "show"),
                           _milestone_command(name, mid, "confirm")),
                        _milestone_command(name, mid, "show"), ident=mid,
                        reasons=["变更停点 %s" % changed]))
                else:
                    todo.append(_todo_item(
                        "milestone",
                        "里程碑 %s 需复核（%s，覆盖停点未就绪：%s）：变更停点 %s；"
                        "%s 出增量审阅包"
                        % (mid, m.get("name", ""), "；".join(reasons), changed,
                           _milestone_command(name, mid, "show")),
                        _milestone_command(name, mid, "show"), ident=mid, reasons=reasons))
                # 需复核的里程碑视同未确认：只阻塞未启动的下游停点（默认口径）。
                for b in blocks:
                    blocked_by_ms[b] = mid
            else:
                pending_ready = [s for s in ready if stop_row(state, s)["state"] == PENDING]
                if pending_ready:
                    human.append(_human_item(
                        "milestone",
                        "里程碑 %s %s 已确认；覆盖停点 %s 还停在送审态（产物指纹未变）："
                        "%s 收尾置完成"
                        % (mid, m.get("name", ""),
                           "、".join(str(s) for s in pending_ready),
                           _milestone_command(name, mid, "confirm")),
                        _milestone_command(name, mid, "confirm"), ident=mid,
                        stop=pending_ready[0],
                        reasons=["覆盖停点 %s 停在送审态"
                                 % "、".join(str(s) for s in pending_ready)]))
                elif reasons:
                    # 覆盖停点送审了但判据没齐：不能静默跳过（两个循环都不报）。
                    todo.append(_todo_item(
                        "milestone",
                        "里程碑 %s %s 已确认，覆盖停点未就绪：%s"
                        % (mid, m.get("name", ""), "；".join(reasons)),
                        _milestone_command(name, mid, "show"), ident=mid, reasons=reasons))
            continue
        if not reasons:
            human.append(_human_item(
                "milestone",
                "里程碑 %s %s：覆盖停点 %s 已就绪，先 %s 生成审阅包，再 %s%s"
                % (mid, m.get("name", ""), "、".join(str(s) for s in ready),
                   _milestone_command(name, mid, "show"),
                   _milestone_command(name, mid, "confirm"),
                   ("（确认前停点 %s 不得启动）" % "、".join(str(b) for b in blocks))
                   if blocks else ""),
                _milestone_command(name, mid, "show"), ident=mid, reasons=reasons))
        elif ready or any(stop_row(state, s)["state"] != NOT_STARTED
                          for s in [int(x) for x in m.get("covers") or []]):
            # 里程碑已经开工（有覆盖停点不是"未开始"）但未就绪：说明原因，
            # 否则覆盖停点行会被下面的 _milestone_done_stops 分支静默跳过。
            todo.append(_todo_item(
                "milestone",
                "里程碑 %s %s 未就绪：%s" % (mid, m.get("name", ""), "；".join(reasons)),
                _milestone_command(name, mid, "show"), ident=mid, reasons=reasons))
        for b in blocks:
            blocked_by_ms[b] = mid
    # 逐停点给出智能体下一步（被决策阻塞的与可以继续的分开算）。
    for stop in model["stops"]:
        sid = int(stop["id"])
        row = stop_row(state, sid)
        if row["state"] == DONE:
            continue
        if row["state"] == PENDING:
            if sid in _milestone_done_stops():
                continue  # 已由上面的里程碑行说明
            check = auto_complete_check(root, name, state, sid)
            if check["ok"]:
                todo.append(_todo_item(
                    "finish",
                    "停点 %d %s：已就绪待完成，判据齐备时自动完成" % (sid, stop["name"]),
                    tick_cmd, stop=sid))
            else:
                todo.append(_todo_item(
                    "fix",
                    "停点 %d %s：判据未满足（%s）"
                    % (sid, stop["name"], "；".join(check["reasons"])),
                    tick_cmd, stop=sid, reasons=check["reasons"]))
        elif row["state"] == RUNNING:
            if CASCADE_RECOVER_MARKER in (row.get("remark") or ""):
                note = _recover_note(root, name, state, sid, row)
                todo.append(_todo_item(
                    "fix", "停点 %d %s：%s" % (sid, stop["name"], note),
                    tick_cmd, stop=sid, reasons=[note]))
            else:
                blocked = _decision_blockers(state, sid)
                if blocked:
                    todo.append(_todo_item(
                        "fix",
                        "停点 %d %s：被决策阻塞（%s），先裁决并关闭问题"
                        % (sid, stop["name"], "、".join(blocked)),
                        "python3 script/framework.py problem %s list" % name,
                        stop=sid, reasons=blocked))
                    continue
                open_blocking = [p for p in state.get("problems") or []
                                 if p.get("kind") == "阻断" and p.get("open", True)
                                 and int(p.get("stop") or 0) <= sid]
                if open_blocking:
                    todo.append(_todo_item(
                        "fix",
                        "停点 %d %s：存在未关闭阻断（%s），先清掉"
                        % (sid, stop["name"], "、".join(p["id"] for p in open_blocking)),
                        "python3 script/framework.py problem %s list" % name,
                        stop=sid, reasons=[p["id"] for p in open_blocking]))
                    continue
                check = auto_complete_check(root, name, state, sid)
                text = "停点 %d %s：进行中，判据齐备时 tick 自动完成%s" % (
                    sid, stop["name"],
                    ("（未满足：%s）" % "；".join(check["reasons"])) if check["reasons"] else "")
                todo.append(_todo_item(
                    "finish", text, tick_cmd, stop=sid, reasons=check["reasons"]))
        elif sid in blocked_by_ms:
            continue  # 由里程碑行说明，不列为"可启动"
        else:
            deps = [int(x) for x in stop.get("depends_on") or []]
            if all(stop_row(state, d)["state"] == DONE for d in deps):
                blocked = [p["id"] for p in state.get("problems") or []
                           if p.get("kind") == "阻断" and p.get("open", True)
                           and int(p.get("stop") or 0) <= sid]
                if blocked or _decision_blockers(state, sid):
                    continue
                todo.append(_todo_item(
                    "start",
                    "停点 %d %s：依赖已定稿，跑 tick 即自动启动"
                    % (sid, stop["name"]),
                    tick_cmd, stop=sid))
    # 待裁决问题（决策通道）与被决策阻塞的工作（--blocks）。
    # 已推迟问题在条件满足前不列；但若仍阻塞未完成停点，必须列出（否则静默死锁）。
    for p in state.get("problems") or []:
        if not p.get("open", True):
            continue
        deferred = p.get("deferred") or {}
        due_note = ""
        if deferred:
            due = _deferred_due(root, name, state, deferred.get("until"))
            known = {int(row["id"]) for row in state.get("stops") or []}
            blocks_open = [str(b) for b in p.get("blocks") or []
                           if str(b).isdigit() and int(b) in known
                           and stop_row(state, int(b))["state"] != DONE]
            blockers = blocks_open + _deferred_still_blocks(state, p)
            if not due and not blockers:
                continue
            if due:
                due_note = "（推迟条件已满足：推迟至 %s；原推迟原因：%s）" % (
                    deferred.get("until") or "—", deferred.get("reason") or "—")
            else:
                due_note = "（推迟中，条件未满足：推迟至 %s；原推迟原因：%s；仍阻塞 %s）" % (
                    deferred.get("until") or "—", deferred.get("reason") or "—",
                    "、".join(dict.fromkeys(blockers)))
        kind = "deferred" if deferred else "decision"
        if p.get("kind") == "阻断":
            tradeoff = bool(p.get("blocks") or p.get("options"))
            if tradeoff:
                text = ("未关闭阻断 %s（停点 %s）：%s；先裁决并关闭问题%s"
                        % (p["id"], p.get("stop"), p.get("text") or "", due_note))
                command = _decision_command(name, p["id"])
            else:
                text = ("未关闭阻断 %s（停点 %s）：%s；先关闭再推进%s"
                        % (p["id"], p.get("stop"), p.get("text") or "", due_note))
                command = ("python3 script/framework.py problem %s close --id %s "
                           "--evidence <R号|review:<停点>[/模块]|D号>"
                           % (name, p["id"]))
            human.append(_human_item(
                "escalation", text, command, ident=p["id"],
                stop=_stop_number(p.get("stop")),
                reasons=[p.get("text") or ""] + ([due_note] if due_note else [])))
        if p.get("kind") == "待裁决":
            parts = ["待裁决问题 %s（停点 %s）：%s" % (p["id"], p.get("stop"), p["text"])]
            if p.get("options"):
                parts.append("候选项：%s" % " | ".join(p["options"]))
            if p.get("blocks"):
                parts.append("阻塞：%s" % "、".join(str(b) for b in p["blocks"]))
            if p.get("options") or p.get("blocks"):
                parts.append("先裁决并关闭问题")
            if due_note:
                parts.append(due_note)
            human.append(_human_item(
                kind, "；".join(parts), _decision_command(name, p["id"]),
                ident=p["id"], stop=_stop_number(p.get("stop")),
                reasons=list(p.get("options") or []) + ([due_note] if due_note else [])))
        if p.get("blocks") and p.get("kind") != "阻断":
            human.append(_human_item(
                kind,
                "被决策阻塞：%s 由 %s 阻塞（%s）%s"
                % ("、".join(str(b) for b in p["blocks"]), p["id"], p["text"][:80],
                   due_note),
                _decision_command(name, p["id"]), ident=p["id"],
                stop=_stop_number((p.get("blocks") or [None])[0]),
                reasons=[str(b) for b in p.get("blocks") or []]))
    # 升级上报。本包覆盖：调试事项轮数、state verify 失败；
    # 外部资源不可达由后续 dbg/doctor 判定，规则自相矛盾类在此追加。
    threshold = _item_round_threshold(state)
    for item in state.get("items") or []:
        rounds = int(item.get("rounds") or 0)
        if rounds >= threshold:
            human.append(_human_item(
                "escalation",
                "升级上报：%s事项 %s 已迭代 %d 轮未收敛（阈值 %d）：%s"
                % (item.get("kind") or "", item["id"], rounds, threshold,
                   item.get("approach") or item.get("text", "")),
                "python3 script/framework.py item %s list" % name,
                ident=item["id"],
                reasons=[item.get("approach") or item.get("text", "")]))
    ok, message = verify_state(root, name)
    if not ok:
        human.append(_human_item(
            "escalation", "升级上报：state verify 失败（证据异常）：%s" % message,
            "python3 script/framework.py state verify %s" % name, reasons=[message]))
    return todo, human


def _render_tick_items(items):
    """结构项 → 文本行（" - <text>"）。"""
    return ["- %s" % item["text"] for item in items]


def _render_tick_lists(todo, human):
    """两张清单的文本行（标题 + 条目 / 空清单提示）。"""
    lines = [TICK_TODO_TITLE] + (_render_tick_items(todo) or ["- （无可推进的工作）"])
    lines += [TICK_HUMAN_TITLE] + (_render_tick_items(human) or ["- （无：不等你裁决）"])
    return lines


def _tick_lists(root, name, state):
    """tick 的两张清单（文本版）：返回 (可推进的工作, 需要开发者)。

    与 `tick_data`/`status_data` 里的 todo/human 同源，只做渲染。
    """
    todo, human = _tick_data_lists(root, name, state)
    return _render_tick_items(todo), _render_tick_items(human)


def tick_data(root, name):
    """tick 的机器可读结果：先在事务里把四相位推进到不动点，再读回两张清单结构。

    返回：
      sys        子系统名
      rounds     本次 tick 实际执行的相位数（轮数）
      actions    {done, started, sent, recovered, retreated}：各相位动作的停点号
      refused    [{stop, reason}]：送审后产物已改动、暂不能完成的停点
      todo/human 两张清单的结构项（字段见 _todo_item / _human_item，每项带 command）
    文本版 `tick_report` 只对这份结构做渲染。
    """
    result = _tick_auto_complete(root, name)
    state = state_read(root, name)
    todo, human = _tick_data_lists(root, name, state)
    refused = [{"stop": int(sid), "reason": reason}
               for sid, reason in result.get("refused") or []]
    for row in refused:
        todo.insert(0, _todo_item(
            "fix", "停点 %d：%s" % (row["stop"], row["reason"]),
            _tick_command(name), stop=row["stop"], reasons=[row["reason"]]))
    return {
        "sys": name,
        "rounds": result.get("rounds", 1),
        "actions": {key: list(result.get(key) or [])
                    for key in ("done", "started", "sent", "recovered", "retreated")},
        "refused": refused,
        "todo": todo,
        "human": human,
    }


def _render_tick(name, data):
    """把 tick_data 渲染成文本（动作摘要一行 + 两张清单）。"""
    lines = []
    labels = (("retreated", "指纹失效退回停点"), ("started", "自动启动停点"),
              ("sent", "自动送审停点"), ("done", "自动完成停点"),
              ("recovered", "复核恢复停点"))
    parts = ["%s %s" % (label, "、".join(str(s) for s in data["actions"][key]))
             for key, label in labels if data["actions"][key]]
    if parts:
        lines.append("tick %s：%s（见事件日志）" % (name, "；".join(parts)))
    lines += _render_tick_lists(data["todo"], data["human"])
    return "\n".join(lines)


def tick_report(root, name):
    """主持者每个工作包后跑一次 `framework.py tick <sys>`（文本版，结构见 tick_data）。

    自动推进到不动点后输出两张清单——「可推进的工作：」与「需要开发者：」。退出码恒 0。
    """
    return _render_tick(name, tick_data(root, name))


STATUS_FOOTER = "数值用 toolbox fx 计算。EDA 用 run。长文见 rules/methodology.md。"


def _status_current_notes(root, name, state, stop, row, shown):
    """当前位置下的一段说明：当前停点为什么还不能自动完成/启动。"""
    notes = []
    decision_blocked = _decision_blockers(state, stop["id"])
    if decision_blocked:
        pid = decision_blocked[0]
        return ["被决策阻塞（%s）：先裁决并关闭问题，`tick` 不会启动或完成本停点。"
                "下一步见“需要开发者”清单：%s"
                % ("、".join(decision_blocked), _decision_command(name, pid))]
    open_blocking = [p for p in state.get("problems") or []
                     if p.get("kind") == "阻断" and p.get("open", True)
                     and int(p.get("stop") or 0) <= int(stop["id"])]
    if open_blocking:
        pid = open_blocking[0]["id"]
        tradeoff = any(p.get("options") or p.get("blocks") for p in open_blocking)
        if tradeoff:
            return ["有未关闭阻断 %s：先裁决并关闭问题：%s"
                    % ("、".join(p["id"] for p in open_blocking),
                       _decision_command(name, pid))]
        return ["有未关闭阻断 %s：先用 `problem %s list` 查看，再按“需要开发者”清单关闭："
                "python3 script/framework.py problem %s close --id %s --evidence <R号|review:<停点>[/模块]|D号>"
                % ("、".join(p["id"] for p in open_blocking), name, name, pid)]
    if row["state"] == PENDING:
        if int(stop["id"]) in _milestone_done_stops():
            check = auto_complete_check(root, name, state, stop["id"])
            extra = "" if not check["reasons"] else "判据未满足：%s；" % "；".join(check["reasons"])
            notes.append("本停点由里程碑覆盖完成（%s）：%s判据齐备时 `tick` 自动置待里程碑，"
                         "审阅包齐备后 milestone confirm。" % (shown, extra))
        else:
            notes.append("本停点自动完成：闸门通过、无未关闭阻断、无在途调试事项、"
                         "且有对应当前产物指纹的独立审查记录后，`tick` 即置完成，不需确认语句。")
    if row["state"] == NOT_STARTED:
        blocking = [p for p in state.get("problems") or []
                    if p.get("kind") == "阻断" and p.get("open", True)
                    and int(p.get("stop") or 0) <= int(stop["id"])]
        if blocking:
            notes.append("有未关闭阻断 %s，先清掉；`tick` 不会自动启动本停点。"
                         % "、".join(str(p["id"]) for p in blocking))
        mid = _milestone_blocking(root, name, state, stop["id"])
        if mid:
            notes.append("本停点被里程碑 %s 阻塞：先 %s 出审阅包并 confirm，"
                         "再由 `tick` 自动启动。"
                         % (mid, _milestone_command(name, mid, "show")))
        elif not _previous_done(state, stop["id"]) and not blocking:
            notes.append("本停点依赖已定稿：跑 `tick` 即自动置进行中。")
    return notes


def status_data(root, name):
    """status 的机器可读结构（纯只读）：当前位置、告警、小结与两张清单。

    字段：sys / where / next / updated / rule_version / fingerprint；
    done（十二条停点是否全部完成）；current（None 或当前停点结构，含 stop、name、
    state（显示态）、raw_state、role、product、rule、command、notes、card、rule_file）；
    stale（None 或 {stops, message}）；cascaded、stale_modules、blocking、waivers；
    summaries（最近 5 条，{time, text}）；todo / human（两张清单的结构项，见
    _todo_item / _human_item）。文本版 `status_report` 只对这份结构做渲染。
    """
    state = state_read(root, name)
    model = load()
    current = None
    for stop in model["stops"]:
        row = stop_row(state, stop["id"])
        if row["state"] != DONE:
            current = stop
            break
    data = {
        "sys": name,
        "where": state["position"]["where"],
        "next": state["position"]["next"],
        "updated": state["position"]["updated"],
        "rule_version": state["position"]["rule_version"],
        "fingerprint": state["position"]["fingerprint"],
        "done": current is None,
        "current": None,
        "stale": None,
        "cascaded": [],
        "stale_modules": 0,
        "blocking": [],
        "waivers": [],
        "summaries": [{"time": item.get("time", ""), "text": item.get("text", "")}
                      for item in (state.get("summary") or [])[-5:]],
    }
    if current is not None:
        row = stop_row(state, current["id"])
        shown = display_state(root, name, state, current["id"], row)
        data["current"] = {
            "stop": int(current["id"]),
            "name": current["name"],
            "state": shown,
            "raw_state": row["state"],
            "role": current["role"],
            "product": current["product"].replace("{sys}", name),
            "rule": "rules/roles/%s.md" % current["role"],
            "command": _next_command(root, name, state, current, row),
            "notes": _status_current_notes(root, name, state, current, row, shown),
            "card": "rules/host/design.md" if int(current["id"]) <= 6 else "rules/host/code.md",
            "rule_file": "rules/roles/%s.md" % current["role"],
        }
    stale = stale_stops(root, name, state)
    if stale:
        data["stale"] = {"stops": list(stale), "message": stale_message(name, stale)}
    data["cascaded"] = [
        {"stop": int(row["id"]), "remark": row["remark"]}
        for row in state["stops"] if "变更待重推" in (row.get("remark") or "")
    ]
    data["stale_modules"] = stale_module_count(state, sys_dir(root, name))
    data["blocking"] = [
        {"id": p["id"], "stop": p.get("stop", ""), "text": p.get("text", "")}
        for p in state.get("problems") or []
        if p.get("kind") == "阻断" and p.get("open", True)
    ]
    data["waivers"] = [
        {"rule": item.get("rule", ""), "where": item.get("where", ""),
         "decision": item.get("decision", "")}
        for item in state.get("waivers") or []
    ]
    data["todo"], data["human"] = _tick_data_lists(root, name, state)
    return data


def _render_status(data):
    """把 status_data 渲染成文本（逐行口径与结构字段一一对应）。"""
    lines = ["子系统 %s" % data["sys"], "所处：%s" % data["where"]]
    current = data["current"]
    if current is None:
        lines.append("十二条停点均已完成。")
    else:
        lines.append("下一停点：%s（行 %d，%s，角色 %s）" % (
            current["name"], current["stop"], current["state"], current["role"]))
        lines.append("产出：%s" % current["product"])
        lines.append("规则：%s" % current["rule"])
        hint = ("（tick 自动启动/送审/完成）"
                if current["command"].rstrip().endswith("tick %s" % data["sys"]) else "")
        lines.append("下一条命令：")
        lines.append(current["command"])
        if hint:
            lines.append(hint)
        lines.extend(current["notes"])
        lines.append("主持卡：%s" % current["card"])
        lines.append("角色文件：%s" % current["rule_file"])
    if data["stale"]:
        lines.append("阻断：%s" % data["stale"]["message"])
    for row in data["cascaded"]:
        lines.append("级联：停点 %d %s" % (row["stop"], row["remark"]))
    if data["stale_modules"]:
        lines.append("标记失效：%d 个模块的 lint/审查标记已因文件改动失效，先重跑 run lint 与 review record"
                     % data["stale_modules"])
    if data["blocking"]:
        lines.append("阻断：%s" % "；".join("%s %s" % (p["id"], p["text"])
                                           for p in data["blocking"]))
    if data["waivers"]:
        lines.append("豁免：%s" % "；".join("%s %s %s" % (item["rule"], item["where"],
                                                          item["decision"])
                                           for item in data["waivers"]))
    if data["summaries"]:
        lines.append("最近小结：")
        for item in data["summaries"]:
            lines.append("  - %s %s" % (item["time"], item["text"]))
    lines += _render_tick_lists(data["todo"], data["human"])
    lines.append(STATUS_FOOTER)
    return "\n".join(lines)


def status_report(root, name):
    """status 文本版：只对 `status_data` 的结构做渲染（清单与 tick 同源）。"""
    return _render_status(status_data(root, name))


def display_state(root, name, state, sid, row):
    """派生显示态：停点内部仍只有四个状态，"待里程碑（Mn）"只出现在
    status/简报等显示层——该停点停在"已送审"、属于动作表 stop_done_milestone
    的停点，且其余自动完成判据（闸门、阻断、事项、审查记录、送审摘要）都已满足，
    只差里程碑确认。
    """
    if row["state"] != PENDING or int(sid) not in _milestone_done_stops():
        return row["state"]
    check = auto_complete_check(root, name, state, sid)
    if check["waiting_milestone"] and not check["reasons"]:
        return "待里程碑（%s）" % check["milestone"]
    return row["state"]
