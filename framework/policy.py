# 作者：vick 邮箱：ykun@yk9811.com

"""动作策略表的前提校验层：把 flow_model.yaml 的 actions 表变成可执行判据。

动作策略表（framework/flow_model.yaml 的 `actions:`）是唯一事实源。本模块做两件事：
按动作号读表项，再按表里声明的 `requires:` 逐条调用校验函数。表里出现本模块不认识的
标识、调用方要求表里不存在的动作号、或强制动作的 `requires:` 在表里缺失，一律报错——
绝不因为"没有判据可跑"而静默放行。

不 import framework.engine：引擎之后 import 本模块，反过来会成环。涉及动作表的事实仍
从 framework.flow 读（class、requires、停点是否被在途事项挡）；其余判据只读调用方填好
的 ctx。ctx 是普通 dict，缺少某条判据要用的键同样报错（fail closed）。

ctx 契约（键 → 类型 → 读它的 requires 标识 / 含义）
---------------------------------------------------
root            str              保留（调用方统一带上；判据本身不访问磁盘）
name            str              保留
state           dict             state.json 内容；decision_exists_directional、decision_id
                                 与红线来源校验从 state["decisions"]、state["problems"] 查
stop            int              停点号；no_blocking（阻断范围）、no_open_item（挡不挡）
findings        list[dict]       闸门 findings；gate_pass（level 非 "hint" 即阻断）
gate_pass       bool             gate_pass 的另一种填法：调用方已有闸门结论时用，
                                 与 findings 二选一
problems        list[dict]       state["problems"]；no_blocking
items           list[dict]       state["items"]；no_open_item
review          dict|bool        {"ok","reason","ref"} 或布尔；review_record
author          str              审查记录作者（派工号）；author_ne_reviewer
reviewer        str              审查记录审查者（派工号）；author_ne_reviewer
findings_count  int              审查发现总数；blocking_zero（非负、类型合法）
blocking        int              阻断发现数；blocking_zero（必须为 0）
decision        str              裁决号（D…）；decision_exists_directional、decision_id、
                                 红线来源
pick            str              开发者点选内容；红线来源（可与 from_problem 组合）
from_problem    str              待裁决问题号；红线来源（须同时给 pick，且问题还开着；
                                 在 problems（缺省回退 state["problems"]）里查）
confirm         str              终端照抄原话；红线来源（签核类里程碑）
evidence        dict             {"ref","exists","seq","time"} 已解析的关闭证据；
                                 evidence_exists_later
problem         dict             被关闭的问题（time、registered_seq）；
                                 evidence_exists_later（也可用 problems + problem_id）
problem_id      str              配合 problems 定位被关闭的问题

requires 标识 → 判据
---------------------
gate_pass                   闸门 findings 里没有 level != "hint" 的项（或 gate_pass 为真）。
no_blocking                 stop 及更早停点没有仍 open 的"阻断"问题。
no_open_item                该停点在动作表里被在途调试事项挡（flow.stop_blocked_by_items）
                            时，items 必须为空；不被挡的停点不看 items。
review_record               独立审查记录判据已满足（review.ok 为真 / review 为真）。
author_ne_reviewer          作者与审查者都写明（派工号）且不相同。
blocking_zero               阻断发现数为 0；findings_count 若给出须为非负整数。
decision_exists_directional 引用的裁决已入库、未撤回、类别为方向或数值。
decision_id                 与 decision_exists_directional 同一有效口径：必须带已入库的
                            方向/数值裁决号。
evidence_exists_later       关闭证据已解析，证据事件 seq 严格大于问题登记 seq，且证据
                            时间串不早于登记时间。

红线统一规则（class: redline，不属于 requires 表）
--------------------------------------------------
红线动作在表里列出的 requires 之外，还必须有人的来源：pick / from_problem+pick /
decision（有效裁决号）/ confirm（终端照抄原话）之一。记录类动作不追这条。

公开面：REQUIRE_CHECKS（标识 → 校验函数）、MANDATORY_ACTIONS（必须有非空 requires 的
动作号；表里缺失即报错，防止"删掉 requires 就一路放行"）、require()、PolicyError。
"""

from framework import flow

# 这些动作的前提就是它的全部语义：表里把 requires 删空时必须报错，不能静默放行。
# 新增这类动作先改动作策略表，再把动作号登记到这里。
MANDATORY_ACTIONS = frozenset({
    "stop_done_auto",
    "review_record",
    "waive_add",
    "problem_close",
    "allow_violation",
    "cov_threshold_down",
})

# 开发者点选入库的裁决类别；"记录"类不作为执行授权，也不级联。
DIRECTIONAL_KINDS = ("方向", "数值")


class PolicyError(Exception):
    """动作前提不满足，或动作/前提标识不在动作策略表里。

    action 是动作号，require 是触发的 requires 标识（红线统一规则用 "redline_source"）；
    引擎接线时把本异常转成自己的错误类型即可，不需要解析消息正文。
    """

    def __init__(self, message, action="", require=""):
        super().__init__(message)
        self.action = action
        self.require = require


def require(action_id, ctx):
    """执行动作策略表里 `action_id` 声明的全部前提；不满足抛 PolicyError。

    表项不存在、表里 requires 含未知标识、强制动作的 requires 缺失，都抛 PolicyError。
    成功返回 None；表里没有 requires 且不是红线动作时，等于无事可查。
    """
    aid = str(action_id or "").strip()
    act = flow.action(aid)
    if act is None:
        raise PolicyError(
            "动作 %r 不在动作策略表（flow_model.yaml 的 actions:）里：表里没有的动作号"
            "不许在代码里 require" % (aid or "（空）"))
    if ctx is None:
        ctx = {}
    if not isinstance(ctx, dict):
        raise PolicyError("动作 %s 的 ctx 必须是 dict，收到 %r" % (aid, type(ctx).__name__))

    requires = flow.requires_of(aid)
    if aid in MANDATORY_ACTIONS and not requires:
        raise PolicyError(
            "动作 %s 在动作策略表里缺 requires（或为空）：动作表是唯一事实源，"
            "缺表不允许静默放行" % aid, action=aid)
    for ident in requires:
        check = REQUIRE_CHECKS.get(ident)
        if check is None:
            raise PolicyError(
                "动作 %s 的 requires 含未知标识 %r：动作表与实现必须双向锁定"
                % (aid, ident), action=aid, require=ident)
        try:
            check(aid, ctx)
        except PolicyError as exc:
            if not exc.action:
                exc.action = aid
            if not exc.require:
                exc.require = ident
            raise
    if act.get("class") == "redline":
        try:
            _check_redline_source(aid, ctx)
        except PolicyError as exc:
            if not exc.action:
                exc.action = aid
            if not exc.require:
                exc.require = "redline_source"
            raise


# ---------- ctx 取值助手：缺键/类型不对一律报错 ----------

def _value(ctx, key, aid, what):
    if key not in ctx:
        raise PolicyError("动作 %s 的%s判据缺 ctx 键 %r" % (aid, what, key))
    return ctx[key]


def _stop_id(ctx, aid):
    raw = _value(ctx, "stop", aid, "停点范围")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise PolicyError("动作 %s 的 ctx['stop'] 不是停点号：%r" % (aid, raw))


def _as_int(value, aid, what):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PolicyError("动作 %s 的%s不是整数：%r" % (aid, what, value))


def _decision_invalid_reason(state, did):
    """裁决无效的原因；有效返回空串（与引擎的"存在且未撤回、方向/数值类"同口径）。"""
    if not isinstance(state, dict):
        return "缺 ctx 键 'state'，无法核对裁决"
    buckets = state.get("decisions") or {}
    if not isinstance(buckets, dict):
        return "ctx['state']['decisions'] 不是阶段号字典"
    found = None
    for bucket in buckets.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            if row.get("id") == did:
                found = row
    if found is None:
        return "裁决 %s 不存在" % did
    if found.get("withdrawn"):
        return "裁决 %s 已撤回，不再是有效授权" % did
    kind = found.get("kind") or "（未标类别）"
    if found.get("kind") not in DIRECTIONAL_KINDS:
        return "裁决 %s 是 %s 类：只有方向/数值类可作执行授权" % (did, kind)
    return ""


def _valid_decision(ctx, aid, what):
    did = str(ctx.get("decision") or "").strip()
    if not did:
        raise PolicyError("动作 %s 缺有效裁决号（ctx['decision']）：%s" % (aid, what))
    reason = _decision_invalid_reason(ctx.get("state"), did)
    if reason:
        raise PolicyError("动作 %s：%s" % (aid, reason))
    return did


# ---------- requires 标识的实现 ----------

def _check_gate_pass(aid, ctx):
    if "findings" in ctx:
        findings = ctx["findings"]
        if not isinstance(findings, list):
            raise PolicyError("动作 %s 的 ctx['findings'] 必须是闸门 findings 列表，收到 %r"
                              % (aid, type(findings).__name__))
        # 形状不对的 finding 也算阻断（fail closed），不跳过。
        blocking = [item for item in findings
                    if not isinstance(item, dict) or item.get("level") != "hint"]
        if blocking:
            first = blocking[0]
            raise PolicyError("动作 %s：闸门未过：[%s] %s" % (
                aid, first.get("rule", "?"), first.get("detail") or first))
        return
    if "gate_pass" in ctx:
        if not ctx["gate_pass"]:
            raise PolicyError("动作 %s：闸门未过（ctx['gate_pass'] 为假）" % aid)
        return
    raise PolicyError("动作 %s 的闸门判据缺 ctx 键 'findings'（或 'gate_pass'）" % aid)


def _check_no_blocking(aid, ctx):
    problems = _value(ctx, "problems", aid, "未关闭阻断")
    if not isinstance(problems, list):
        raise PolicyError("动作 %s 的 ctx['problems'] 必须是列表" % aid)
    sid = _stop_id(ctx, aid)
    open_blocking = []
    for row in problems:
        if row.get("kind") != "阻断" or not row.get("open", True):
            continue
        try:
            row_stop = int(row.get("stop") or 0)
        except (TypeError, ValueError):
            row_stop = 0
        if row_stop <= sid:
            open_blocking.append(str(row.get("id") or "?"))
    if open_blocking:
        raise PolicyError("动作 %s：存在未关闭阻断（%s，覆盖停点 %d 及更早）"
                          % (aid, "、".join(open_blocking), sid))


def _check_no_open_item(aid, ctx):
    items = _value(ctx, "items", aid, "在途事项")
    if not isinstance(items, list):
        raise PolicyError("动作 %s 的 ctx['items'] 必须是列表" % aid)
    sid = _stop_id(ctx, aid)
    try:
        blocked = flow.stop_blocked_by_items(sid)
    except (KeyError, ValueError):
        raise PolicyError("动作 %s 的 ctx['stop'] 不是动作表里的停点：%r" % (aid, sid))
    if blocked and items:
        raise PolicyError("动作 %s：停点 %d 存在在途调试事项（%s）"
                          % (aid, sid, "、".join(str(row.get("id") or "?") for row in items)))


def _check_review_record(aid, ctx):
    if "review" not in ctx:
        raise PolicyError("动作 %s 的独立审查判据缺 ctx 键 'review'" % aid)
    review = ctx["review"]
    if isinstance(review, bool):
        ok, detail = review, ""
    elif isinstance(review, dict):
        ok = bool(review.get("ok"))
        detail = str(review.get("reason") or "").strip()
    else:
        raise PolicyError("动作 %s 的 ctx['review'] 须为 dict 或布尔，收到 %r"
                          % (aid, type(review).__name__))
    if not ok:
        raise PolicyError("动作 %s：缺独立审查记录%s"
                          % (aid, ("：" + detail) if detail else ""))


def _check_author_ne_reviewer(aid, ctx):
    author = str(ctx.get("author") or "").strip()
    reviewer = str(ctx.get("reviewer") or "").strip()
    if "author" not in ctx or "reviewer" not in ctx or not author or not reviewer:
        raise PolicyError("动作 %s：审查记录要写明作者与审查者（ctx['author']/"
                          "ctx['reviewer']，派工号）" % aid)
    if author == reviewer:
        raise PolicyError("动作 %s：作者与审查者必须不同（作者自审不算独立审查）" % aid)


def _check_blocking_zero(aid, ctx):
    blocking = _as_int(_value(ctx, "blocking", aid, "阻断发现数"), aid, "阻断发现数")
    if blocking != 0:
        raise PolicyError("动作 %s：存在 %d 条阻断发现，先解决阻断再记审查通过"
                          % (aid, blocking))
    if "findings_count" in ctx:
        total = _as_int(ctx["findings_count"], aid, "审查发现总数")
        if total < 0:
            raise PolicyError("动作 %s：审查发现总数不能为负（%d）" % (aid, total))
        if blocking > total:
            raise PolicyError("动作 %s：阻断发现数（%d）大于发现总数（%d）"
                              % (aid, blocking, total))


def _check_decision_exists_directional(aid, ctx):
    _valid_decision(ctx, aid, "这个动作必须引用开发者点选入库的方向/数值类裁决")


def _check_decision_id(aid, ctx):
    _valid_decision(ctx, aid, "这个动作必须带已入库的方向/数值裁决号")


def _check_evidence_exists_later(aid, ctx):
    problem = ctx.get("problem")
    if not isinstance(problem, dict):
        pid = str(ctx.get("problem_id") or "").strip()
        problems = ctx.get("problems")
        if pid and isinstance(problems, list):
            problem = next((row for row in problems if row.get("id") == pid), None)
    if not isinstance(problem, dict):
        raise PolicyError("动作 %s 的关闭证据判据缺 ctx 键 'problem'（或 problems+problem_id）"
                          % aid)
    evidence = ctx.get("evidence")
    if not isinstance(evidence, dict):
        raise PolicyError("动作 %s：关闭证据要用已解析的 dict（ctx['evidence'] 含 "
                          "ref/exists/seq/time）" % aid)
    ref = str(evidence.get("ref") or "?")
    if not evidence.get("exists", False):
        raise PolicyError("动作 %s：关闭证据不存在：%s" % (aid, ref))
    ev_seq = evidence.get("seq")
    if ev_seq is None:
        raise PolicyError("动作 %s：关闭证据 %s 的时序无法判定（缺事件 seq）" % (aid, ref))
    reg_seq = problem.get("registered_seq")
    if reg_seq is None:
        raise PolicyError("动作 %s：问题 %s 的登记事件缺 seq，时序无法判定"
                          % (aid, problem.get("id") or "?"))
    ev_seq = _as_int(ev_seq, aid, "关闭证据的事件 seq")
    reg_seq = _as_int(reg_seq, aid, "问题登记的事件 seq")
    if ev_seq <= reg_seq:
        raise PolicyError("动作 %s：关闭证据 %s 不晚于问题登记（严格晚于）：证据 seq %d，"
                          "登记 seq %d" % (aid, ref, ev_seq, reg_seq))
    ev_time = str(evidence.get("time") or "")
    reg_time = str(problem.get("time") or "")
    if ev_time < reg_time:
        raise PolicyError("动作 %s：关闭证据 %s 的时间（%s）早于问题登记时间（%s）"
                          % (aid, ref, ev_time, reg_time))


def _find_problem(ctx, pid):
    """先在 ctx["problems"]（调用方通常填 state["problems"]）里查，再回退 state。"""
    candidates = []
    if isinstance(ctx.get("problems"), list):
        candidates.extend(ctx["problems"])
    state = ctx.get("state")
    if isinstance(state, dict) and isinstance(state.get("problems"), list):
        candidates.extend(state["problems"])
    return next((row for row in candidates if row.get("id") == pid), None)


def _check_redline_source(aid, ctx):
    """红线统一规则：人的来源之一。记录类动作不走这里（它们不是红线）。"""
    decision = str(ctx.get("decision") or "").strip()
    pick = str(ctx.get("pick") or "").strip()
    from_problem = str(ctx.get("from_problem") or "").strip()
    confirm = str(ctx.get("confirm") or "").strip()
    if decision and not _decision_invalid_reason(ctx.get("state"), decision):
        return
    if from_problem:
        problem = _find_problem(ctx, from_problem)
        if problem is not None and problem.get("open", True) and pick:
            return
        raise PolicyError(
            "动作 %s 是红线：问题 %s 的点选来源无效（问题须存在且还开着，并同时给 pick）"
            % (aid, from_problem))
    if pick or confirm:
        return
    if decision:
        raise PolicyError("动作 %s 是红线：裁决 %s 无效（%s）"
                          % (aid, decision, _decision_invalid_reason(ctx.get("state"), decision)))
    raise PolicyError(
        "动作 %s 是红线：必须有点选来源或已入库裁决号（ctx 给出 pick / from_problem+pick / "
        "decision / confirm 之一）" % aid)


REQUIRE_CHECKS = {
    "gate_pass": _check_gate_pass,
    "no_blocking": _check_no_blocking,
    "no_open_item": _check_no_open_item,
    "review_record": _check_review_record,
    "author_ne_reviewer": _check_author_ne_reviewer,
    "blocking_zero": _check_blocking_zero,
    "decision_exists_directional": _check_decision_exists_directional,
    "evidence_exists_later": _check_evidence_exists_later,
    "decision_id": _check_decision_id,
}
