# 作者：vick 邮箱：ykun@yk9811.com

"""里程碑就绪、确认、拒绝与推迟/待确认标注检查。"""

import os, re
from framework.flow import (
    DONE as DONE,
    NOT_STARTED as NOT_STARTED,
    PENDING as PENDING,
    RUNNING as RUNNING,
    load as load,
    milestone as flow_milestone,
    milestones as flow_milestones,
    product_path as product_path,
)
from framework.state import record_event, state_txn, stop_row, sys_dir
from framework.engine.runtime import current_time as now
from framework.engine.problems import (
    _deferred_problem_reasons,
)
from framework.engine.runtime import (
    EngineError,
    _product_digest,
    _require_action,
    _upstream_milestones,
    decision_blockers,
    milestone_valid,
    refresh_position,
    require_confirm_arg,
    require_human,
)
from framework.engine.signoff import (
    render_signoff,
)
from framework.engine.stops import (
    _cascade,
    _clear_confirmation,
    _finish_stop,
    _pending_digest,
    auto_complete_check,
    stale_stops,
)


def _deferred_due(root, name, state, until):
    """推迟条件是否满足。

    - until 是停点号：该停点已启动（状态不是"未开始"）；
    - until 是里程碑号：里程碑已确认，或覆盖停点已就绪（_milestone_readiness
      返回就绪停点且无未就绪原因）。
    """
    text = str(until or "").strip()
    if text.startswith("M"):
        m = flow_milestone(text)
        if m is None:
            return False
        if milestone_valid(root, name, state, m["id"])["confirmed"]:
            return True
        ready, reasons = _milestone_readiness(root, name, state, m)
        return bool(ready) and not reasons
    try:
        sid = int(text)
    except (TypeError, ValueError):
        return False
    try:
        return stop_row(state, sid)["state"] != NOT_STARTED
    except (KeyError,):
        return False


def _milestone_readiness(root, name, state, m):
    """里程碑是否就绪：覆盖停点全部完成，或停在"已送审"且判据齐、送审摘要
    一致。返回 (就绪停点号列表, 未就绪原因列表)。

    M1 还要求结论摘要（<sys>/milestone_notes/M1.md）按模板写 3–6 条——审阅包
    只放摘要，原文留链接。
    """
    ready, reasons = [], []
    reasons += _milestone_notes_reasons(root, name, m)
    if not (state.get("milestones") or {}).get(m["id"]):
        reasons += _deferred_problem_reasons(state, m)
    for sid in [int(x) for x in m.get("covers") or []]:
        stop = load()["by_id"][sid]
        row = stop_row(state, sid)
        blocked = decision_blockers(state, sid)
        if blocked:
            reasons.append("停点 %d 被决策阻塞（%s）：先裁决并关闭问题"
                           % (sid, "、".join(blocked)))
            continue
        open_blocking = [p for p in state.get("problems") or []
                         if p.get("kind") == "阻断" and p.get("open", True)
                         and int(p.get("stop") or 0) <= sid]
        if open_blocking:
            reasons.append("停点 %d 存在未关闭阻断（%s）：先关闭再确认"
                           % (sid, "、".join(p["id"] for p in open_blocking)))
            continue
        if row["state"] == DONE:
            ready.append(sid)
            continue
        if row["state"] != PENDING:
            reasons.append("停点 %d %s（%s）" % (sid, stop["name"], row["state"]))
            continue
        check = auto_complete_check(root, name, state, sid)
        pending = row.get("pending_digest") or ""
        if pending and _pending_digest(root, name, stop) != pending:
            reasons.append("停点 %d 产物与送审时不一致，重跑闸门后退回重新送审" % sid)
        elif check["reasons"]:
            reasons.append("停点 %d：%s" % (sid, "；".join(check["reasons"])))
        else:
            ready.append(sid)
    return ready, reasons


def milestone_notes_path(root, name, mid):
    """里程碑结论摘要的位置（<sys>/milestone_notes/<mid>.md，主持者手写）。"""
    return os.path.join(sys_dir(root, name), "milestone_notes", "%s.md" % mid)


def milestone_note_lines(root, name, mid):
    """读结论摘要的条目（`- ` 或 `1. ` 开头的行）；文件缺失返回空列表。"""
    path = milestone_notes_path(root, name, mid)
    if not os.path.isfile(path):
        return []
    lines = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if text.startswith(("- ", "* ")) or re.match(r"^\d+[.、)]\s*\S", text):
                lines.append(text)
    return lines


def _milestone_notes_reasons(root, name, m):
    """M1 的结论摘要必须按模板写 3–6 条（规则与实现对齐：原文不再内嵌）。"""
    if m.get("id") != "M1":
        return []
    lines = milestone_note_lines(root, name, m["id"])
    if not lines:
        return ["M1 缺结论摘要 %s：按模板写 3–6 条要点（每份产物一段，原文只留链接）"
                % os.path.relpath(milestone_notes_path(root, name, m["id"]), sys_dir(root, name))]
    if not 3 <= len(lines) <= 6:
        return ["M1 结论摘要是 %d 条：按模板写 3–6 条（当前 %s）"
                % (len(lines), os.path.relpath(milestone_notes_path(root, name, m["id"]),
                                               sys_dir(root, name)))]
    return []


def milestone_confirm(root, name, mid, confirm="", pick=""):
    """里程碑确认（红线动作"里程碑确认"的人按：M1/M2 点选即确认；M3 终端照抄）。

    非终端里程碑要求 `--pick 通过`（来自主持者的点选工具）并记进里程碑记录；
    M3 保留"交互终端照抄"这一道 TTY 检查。

    把覆盖停点里处于"待里程碑"（以及"已送审"且判据
    已满足）的停点一起置为完成，记录确认语句、时间与覆盖停点的产物指纹。

    允许对已确认的里程碑再次确认（复核过期上游变更）：旧记录进 history，不删。
    终端照抄在全部机器检查（上游里程碑有效、覆盖停点就绪、判据、
    送审摘要一致）之后才发生；产物与送审时不一致则拒绝。terminal 读
    milestones: 表，不硬编码 M3。点选/照抄来源由动作表 milestone_confirm 的
    class:redline 规则执行（在机器检查之后、终端照抄提示之前）。
    """
    m = flow_milestone(str(mid or "").strip())
    if m is None:
        raise EngineError("没有里程碑 %s（milestones: 表里声明的是 %s）"
                          % (mid, "、".join(x["id"] for x in flow_milestones())))
    mid = m["id"]
    with state_txn(root, name, cmd="milestone_confirm") as state:
        reasons = _milestone_confirm_reasons(root, name, state, m)
        if reasons:
            raise EngineError("里程碑 %s 不能确认：%s" % (mid, "；".join(reasons)))
        terminal = bool(m.get("terminal"))
        what = "里程碑 %s %s 签核" % (mid, m.get("name", ""))
        pick = str(pick or "").strip()
        if terminal:
            # 缺 --confirm 的文案先给（动作表只描述"有点选/照抄来源"，不描述参数写法）。
            require_confirm_arg(confirm, what)
        elif pick != "通过":
            raise EngineError(
                "里程碑 %s 需要点选来源：--pick 通过（来自主持者的点选工具；"
                "M1/M2 不再用终端照抄）" % mid)
        # 动作表 milestone_confirm 的 class:redline 统一规则：必须有点选来源或终端照抄
        # 原话。位置在全部机器检查之后、终端照抄提示之前。
        _require_action("milestone_confirm",
                        {"state": state, "pick": pick, "confirm": confirm})
        if terminal:
            require_human(confirm, what)
            quote = confirm
        else:
            # 点选是授权（--pick 通过，记进里程碑记录）；confirm 是开发者自己的
            # 备注原话，写了就一起记进确认语句。
            quote = (confirm or "").strip() or "点选通过"
        covered = [int(x) for x in m.get("covers") or []]
        records = state.setdefault("milestones", {})
        previous = records.get(mid)
        fingerprints = {}
        record = {
            "id": mid, "name": m.get("name", ""), "time": now(), "quote": quote,
            "terminal": terminal, "pick": "" if terminal else "通过",
            "covered": covered, "fingerprints": fingerprints,
        }
        if previous:
            # 再次确认（复核）：旧记录进 history，原确认不删（审计要留）。
            history = [entry for entry in (previous.get("history") or [])]
            history.append({key: value for key, value in previous.items() if key != "history"})
            record["history"] = history
        # 先落里程碑记录，再渲染签核文件：签核里要读到"里程碑 M3 已确认"。
        records[mid] = record
        for sid in covered:
            stop = load()["by_id"][sid]
            row = stop_row(state, sid)
            if row["state"] == PENDING:
                if "signoff" in (stop.get("gates") or []):
                    # 放行：签核文件是最终交付物，先用确认原话重渲染，再由
                    # _finish_stop 算指纹——指纹覆盖的就是这一版签核文件。行 12 的
                    # 送审基线走 _pending_digest 的 inputs: 分支（不含 signoff/），
                    # 重渲染不会触发"送审后产物改动"。
                    render_signoff(root, name, state, confirm=quote)
                _finish_stop(root, name, state, sid, quote=quote)
                row["state"] = DONE
                record_event(state, "里程碑完成", obj="停点 %d" % sid,
                             evidence="里程碑 %s 确认；确认语句：%s；指纹 %s"
                                      % (mid, quote, row["fingerprint"]))
            fingerprints[str(sid)] = row.get("fingerprint") or _product_digest(root, name, stop)
        state["position"]["where"] = "里程碑 %s %s 已确认" % (mid, m.get("name", ""))
        refresh_position(state, load())
        record_event(state, "里程碑确认", obj=mid,
                     evidence="确认语句：%s；覆盖停点 %s；产物指纹 %s"
                              % (quote, "、".join(str(s) for s in covered), fingerprints))
    return "里程碑 %s %s 已确认（覆盖停点 %s）" % (
        mid, m.get("name", ""), "、".join(str(s) for s in covered))


def _milestone_product_docs(root, name, m):
    """里程碑覆盖停点的产品文档：文件产物本身 + 目录产物下的 .md（去重排序）。

    只扫 Markdown：里程碑冻结/签核要管的是规格与方案文档里的未决标注，
    日志与二进制产物不参与这条检查。
    """
    base = sys_dir(root, name)
    docs = []
    for sid in [int(x) for x in m.get("covers") or []]:
        stop = load()["by_id"].get(sid)
        if not stop:
            continue
        path = os.path.join(base, product_path(stop, name))
        if os.path.isdir(path):
            for dirpath, dirnames, files in os.walk(path):
                dirnames[:] = sorted(item for item in dirnames if not item.startswith("."))
                for fn in sorted(files):
                    if fn.endswith(".md"):
                        docs.append(os.path.join(dirpath, fn))
        elif os.path.isfile(path) and path.endswith(".md"):
            docs.append(path)
    seen, out = set(), []
    for path in docs:
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            out.append(path)
    return out


def _pending_confirmation_reasons(root, name, m):
    """覆盖范围内产品文档还留着"待确认"标注时拒绝里程碑确认。

    口径比 U1 闸门更强：标注即使引用了仍打开的问题号也不放行——里程碑冻结/签核
    不带着未决标注过线；问题已关闭而标注还在，说明该处要按结论改写后再确认。
    原因列出文件与标注行文本。
    """
    from framework.gates.docs import pending_confirmations
    base = sys_dir(root, name)
    reasons = []
    for path in _milestone_product_docs(root, name, m):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = pending_confirmations(fh.read())
        except (OSError,):
            continue
        rel = os.path.relpath(path, base)
        for line in lines:
            reasons.append("产物 %s 仍有待确认标注：%s" % (rel, line.strip()[:120]))
    return reasons


def _confirm_command(name, mid):
    """生成可直接照抄的里程碑确认命令（M1/M2 点选，M3 终端原话）。"""
    item = flow_milestone(mid) or {}
    if item.get("terminal"):
        suffix = '--confirm "确认 %s 签核放行（%s）通过"' % (name, item.get("id", mid))
    else:
        suffix = "--pick 通过"
    return "python3 script/framework.py milestone %s confirm --id %s %s" % (name, mid, suffix)


def _milestone_confirm_reasons(root, name, state, m):
    """里程碑确认前的全部机器检查：上游里程碑当前有效、覆盖停点就绪、
    判据齐、送审摘要一致、已完成停点的指纹未变、覆盖范围内没有"待确认"标注。
    返回原因列表，空列表即可确认。

    上游里程碑由 flow_model.yaml 的 covers/depends_on 推导（_upstream_milestones）：
    确认 M3 前 M1、M2 必须当前有效（"需复核"不算有效），签核只能建立在有效的
    上游里程碑之上。
    """
    reasons = _milestone_notes_reasons(root, name, m)
    reasons += _pending_confirmation_reasons(root, name, m)
    if not (state.get("milestones") or {}).get(m["id"]):
        reasons += _deferred_problem_reasons(state, m)
    for other in _upstream_milestones(m["id"]):
        valid = milestone_valid(root, name, state, other["id"])
        if valid["valid"]:
            continue
        if valid["needs_review"]:
            reasons.append(
                "上游里程碑 %s 当前需复核（变更停点 %s）：先 "
                "python3 script/framework.py milestone %s show --id %s 出增量审阅包、"
                "%s 复核，再确认 %s"
                % (other["id"], "、".join(str(s) for s in valid["changed"]),
                   name, other["id"], _confirm_command(name, other["id"]), m["id"]))
        else:
            reasons.append("上游里程碑 %s 尚未确认：先 "
                           "python3 script/framework.py milestone %s show --id %s 出审阅包、"
                           "%s，再确认 %s"
                           % (other["id"], name, other["id"],
                              _confirm_command(name, other["id"]), m["id"]))
    stale = set(stale_stops(root, name, state))
    for sid in [int(x) for x in m.get("covers") or []]:
        stop = load()["by_id"][sid]
        row = stop_row(state, sid)
        blocked = decision_blockers(state, sid)
        if blocked:
            reasons.append("停点 %d 被决策阻塞（%s）：先裁决并关闭问题"
                           % (sid, "、".join(blocked)))
            continue
        open_blocking = [p for p in state.get("problems") or []
                         if p.get("kind") == "阻断" and p.get("open", True)
                         and int(p.get("stop") or 0) <= sid]
        if open_blocking:
            reasons.append("停点 %d 存在未关闭阻断（%s）：先关闭再确认"
                           % (sid, "、".join(p["id"] for p in open_blocking)))
            continue
        if row["state"] == DONE:
            if sid in stale:
                reasons.append("停点 %d 的产物在完成后有改动，先退回该停点重新送审" % sid)
            continue
        if row["state"] != PENDING:
            reasons.append("停点 %d %s（%s），未送审" % (sid, stop["name"], row["state"]))
            continue
        check = auto_complete_check(root, name, state, sid)
        if check["reasons"]:
            reasons.append("停点 %d 判据未满足：%s" % (sid, "；".join(check["reasons"])))
        pending = row.get("pending_digest") or ""
        if pending and _pending_digest(root, name, stop) != pending:
            reasons.append("停点 %d 的产物与送审时不一致：重跑闸门后退回进行中重新送审" % sid)
    return reasons


def milestone_reject(root, name, mid, reason, stop=None):
    """里程碑拒绝：把最早一个有问题的覆盖停点退回进行中（--stop N 可指定），
    按依赖闭包级联（只退回下游已启动的停点）；理由转成
    问题登记；该里程碑覆盖的其它停点状态按级联结果处理。"""
    m = flow_milestone(str(mid or "").strip())
    if m is None:
        raise EngineError("没有里程碑 %s" % mid)
    mid = m["id"]
    reason = str(reason or "").strip()
    if not reason:
        raise EngineError("milestone reject 必须写明 --reason，说明不通过的理由")
    covered = [int(x) for x in m.get("covers") or []]
    with state_txn(root, name, cmd="milestone_reject") as state:
        if stop:
            sid = int(stop)
            if sid not in covered:
                raise EngineError("停点 %d 不在里程碑 %s 的覆盖范围（%s）"
                                  % (sid, mid, "、".join(str(s) for s in covered)))
        else:
            stale = set(stale_stops(root, name, state))
            bad = [s for s in covered
                   if stop_row(state, s)["state"] != DONE or s in stale]
            sid = min(bad or covered)
        row = stop_row(state, sid)
        previous = row["state"]
        _clear_confirmation(row)
        row["state"] = RUNNING
        row["remark"] = "里程碑 %s 拒绝，退回重做" % mid
        cascaded = _cascade(state, sid, "里程碑 %s 拒绝" % mid)
        state["seq"]["I"] += 1
        pid = "I%03d" % state["seq"]["I"]
        state["problems"].append({
            "id": pid, "kind": "待裁决", "stop": sid, "text": reason,
            "source": "milestone reject %s" % mid, "time": now(), "open": True,
            "options": [], "blocks": [str(sid)] + [str(c) for c in cascaded],
        })
        state["position"]["where"] = "停点 %d %s（里程碑 %s 拒绝）" % (
            sid, load()["by_id"][sid]["name"], mid)
        state["position"]["next"] = "按问题 %s 重做停点 %d 的产出后重新送审" % (pid, sid)
        record_event(state, "里程碑拒绝", obj=mid,
                     evidence="退回停点 %d（%s → %s）；级联 %s；理由转问题 %s"
                              % (sid, previous, RUNNING, "、".join(str(c) for c in cascaded) or "无", pid))
    return "里程碑 %s 拒绝：停点 %d 退回进行中，级联 %s；理由已登记为问题 %s" % (
        mid, sid, "、".join(str(c) for c in cascaded) or "无", pid)
