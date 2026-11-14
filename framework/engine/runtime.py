# 作者：vick 邮箱：ykun@yk9811.com

"""运行时基础：常量、状态机原语、里程碑动作表读取、摘要原语。"""

import hashlib, os, pwd, re, sys
from framework import policy
from framework.flow import (
    DONE as DONE,
    NOT_STARTED as NOT_STARTED,
    PENDING as PENDING,
    RUNNING as RUNNING,
    action as flow_action,
    depends_on as flow_depends_on,
    load as load,
    milestone as flow_milestone,
    milestone_of_stop as flow_milestone_of_stop,
    milestones as flow_milestones,
    product_path as product_path,
    stage_of_stop as flow_stage_of_stop,
    stop_ids as flow_stop_ids,
)
from framework.state import now as _state_now, stop_row, sys_dir


KINDS = ("方向", "数值", "记录")


PROBLEM_KINDS = ("阻断", "待裁决")


DEFER_PICK = "推迟决定"


ITEM_KINDS = ("调试", "综合优化")


ITEM_LEVELS = ("L0", "L1", "L2", "L3")


ITEM_LIMIT = 4


SIGNOFF_FOLDER = "signoff"


def stage_of_stop(sid):
    """停点 → 阶段号（D 号前缀）：读 flow_model.yaml 的 `stage:` 字段。

    阶段号不再由命令行传入，也不在本文件里写死映射；模型缺字段/取值非法时
    报错（阶段号是 D 号与分阶段分桶的输入，不能静默退化）。
    """
    try:
        return flow_stage_of_stop(sid)
    except (KeyError,):
        raise EngineError("没有停点 %s（--stop）" % sid)
    except ValueError as exc:
        raise EngineError(str(exc))


def _stop_id_text():
    """模型停点号的展示串（错误消息用，不写死 1..12）。"""
    ids = sorted(flow_stop_ids())
    return "%d..%d" % (ids[0], ids[-1]) if ids else "（空）"


def _check_stop_id(sid, what="停点"):
    """停点号必须在模型停点集合里；返回 int。"""
    try:
        value = int(sid)
    except (TypeError, ValueError):
        raise EngineError("%s须为停点号（%s），收到 %r" % (what, _stop_id_text(), sid))
    if value not in flow_stop_ids():
        raise EngineError("%s须为模型里的停点号（%s），收到 %s"
                          % (what, _stop_id_text(), value))
    return value


class EngineError(Exception):
    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = list(findings or [])


def _require_action(action_id, ctx):
    """执行动作策略表里该动作的前提（唯一实现见 framework/policy.py）。

    policy.PolicyError 在引擎边界一律转 EngineError：命令行与调用方只认一种错误类型，
    消息里已带动作号与触发的 requires 标识，不必解析异常类型。
    """
    try:
        policy.require(action_id, ctx)
    except policy.PolicyError as exc:
        raise EngineError(str(exc))


def _stop_done_ctx(state, sid, findings, review_ok, review_reason, review_ref):
    """auto_complete_check 的动作前提上下文（键义见 framework/policy.py 的 docstring）。"""
    return {
        "state": state,
        "stop": int(sid),
        "findings": findings,
        "problems": state.get("problems") or [],
        "items": state.get("items") or [],
        "review": {"ok": review_ok, "reason": review_reason, "ref": review_ref},
    }


def _stdin_is_tty():
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def _read_line(prompt=""):
    return input(prompt)


def real_home():
    """账户数据库里的家目录（审阅包等按它定位）。"""
    return pwd.getpwuid(os.geteuid()).pw_dir


_home_dir = real_home


def _pkg():
    """本包（framework.engine）：可变钩子经包级属性查，patch 包属性即生效。"""
    import framework.engine as package
    return package


def state_now():
    """当前时间的原始实现；包级 `now` 初始指向它，测试可整体替换。"""
    return _state_now()


def current_time():
    """内部取当前时间：经包级属性查，patch `framework.engine.now` 生效。"""
    return _pkg().now()


def refresh_position(state, model):
    """tick 收尾把当前位置对齐到第一个未完成停点。"""
    for stop in model["stops"]:
        row = stop_row(state, stop["id"])
        if row["state"] != DONE:
            state["position"]["where"] = "停点 %d %s（%s）" % (
                stop["id"], stop["name"], row["state"])
            state["position"]["next"] = "按 tick/status 清单推进停点 %d" % stop["id"]
            state["position"]["updated"] = current_time()
            return
    state["position"]["where"] = "全部停点已完成"
    state["position"]["next"] = (
        "流程已签核放行"
        if (state.get("milestones") or {}).get("M3")
        else "按里程碑 M3 审阅包确认（若尚未确认）")
    state["position"]["updated"] = current_time()


def decision_blockers(state, sid):
    """仍打开的、以 --blocks 指向该停点的问题号（决策通道的阻塞）。"""
    key = str(int(sid))
    return [p.get("id") for p in state.get("problems") or []
            if p.get("open", True)
            and key in [str(b) for b in p.get("blocks") or []]]


def _hook(name, *args):
    """按包级属性调用可变钩子（patch `_stdin_is_tty`/`_read_line` 等即生效）。"""
    return getattr(_pkg(), name)(*args)

def require_human(confirm, what):
    """终端照抄：收缩后只用于 terminal: true 的里程碑（M3），由 milestone confirm 调用。

    其余动作一律不要终端。调用前必须已经做完闸门、送审摘要、裁决存在性等全部检查，
    否则开发者会先照抄一遍原话、再被告知前面就过不了。
    """
    if not confirm:
        raise EngineError("%s需要 --confirm 写下开发者原话" % what)
    if not _hook("_stdin_is_tty"):
        raise EngineError("%s需要交互终端（stdin 不是 TTY），请在终端里亲自执行" % what)
    try:
        typed = _hook("_read_line", "%s：请照抄确认原话：" % what)
    except (EOFError, KeyboardInterrupt):
        raise EngineError("没有读到确认原话，%s被拒" % what)
    if (typed or "").strip() != confirm:
        raise EngineError("现场输入的原话与 --confirm 不一致，%s被拒" % what)


def require_confirm_arg(confirm, what):
    """只查 --confirm 写没写；照抄原话留到所有检查之后。

    收缩后只剩 M3（terminal: true 的里程碑）确认走这里。
    """
    if not confirm:
        raise EngineError("%s需要 --confirm 写下开发者原话" % what)


def _auto_done_stops():
    """动作表 stop_done_auto 的 stops：判据齐备即自动完成的停点（唯一起源是这张表）。"""
    act = flow_action("stop_done_auto") or {}
    return {int(x) for x in act.get("stops") or []}


def _milestone_done_stops():
    """动作表 stop_done_milestone 的 stops：由里程碑确认完成、advance 不置完成的停点。"""
    act = flow_action("stop_done_milestone") or {}
    return {int(x) for x in act.get("stops") or []}


def _terminal_milestone(mid):
    """里程碑 mid 是否要终端照抄：读 milestones: 表的 terminal 字段（不硬编码 M3）。"""
    m = flow_milestone(mid)
    return bool(m and m.get("terminal"))


def milestone_valid(root, name, state, mid):
    """里程碑有效性判定：已确认的里程碑是否仍然作数。

    有效 = 覆盖停点当前都为"完成"或"已送审（已送审）"，且每个覆盖停点的
    产物指纹（_product_digest，与确认时记的同一口径）与确认时记下的
    fingerprints 一致。不一致时派生状态为"需复核"：原确认记录保留不删
    （审计要留），由 `milestone show` 出增量审阅包、`milestone confirm` 再确认。

    返回 dict：
      status       "未确认" / "有效" / "需复核"（派生状态，不进 states）；
      confirmed    state["milestones"] 里有没有确认记录；
      valid        status == "有效"；
      needs_review status == "需复核"；
      changed      指纹变化、或当前已不在"完成/已送审"的覆盖停点号（升序）；
      details      每个 changed 停点的一句说明（进 tick 清单与增量审阅包）；
      record       确认记录本身（未确认时是 {}）。
    """
    m = flow_milestone(str(mid or "").strip())
    record = ((state.get("milestones") or {}).get((m or {}).get("id") or str(mid)) or {})
    blank = {"status": "未确认", "confirmed": False, "valid": False,
             "needs_review": False, "changed": [], "details": [], "record": {}}
    if m is None or not record:
        return blank
    recorded = record.get("fingerprints") or {}
    changed, details = [], []
    for sid in [int(x) for x in m.get("covers") or []]:
        stop = load()["by_id"].get(sid)
        row = stop_row(state, sid)
        label = "停点 %d %s" % (sid, (stop or {}).get("name", ""))
        baseline = str(recorded.get(str(sid)) or "")
        if stop is None:
            changed.append(sid)
            details.append("%s：flow_model 里没有这个停点，确认基线无法核对" % label)
            continue
        if row["state"] not in (DONE, PENDING):
            changed.append(sid)
            details.append("%s：已不在完成/送审态（当前 %s）" % (label, row["state"]))
            continue
        if not baseline:
            changed.append(sid)
            details.append("%s：确认时没有记下产物指纹，无法核对" % label)
            continue
        current = _product_digest(root, name, stop)
        if current != baseline:
            changed.append(sid)
            details.append("%s：产物指纹 %s → %s" % (label, baseline, current))
    return {"status": "需复核" if changed else "有效", "confirmed": True,
            "valid": not changed, "needs_review": bool(changed),
            "changed": changed, "details": details, "record": record}


def _milestone_blocking(root, name, state, sid):
    """被里程碑阻塞的启动：sid 在某个当前不作数的里程碑的 blocks 里时返回其 id。

    "不作数"= 未确认，或已确认但"需复核"（milestone_valid）。调用点都在停点的
    "未开始"分支，所以这自然满足默认口径：需复核只阻塞**未启动**的停点，
    不重新阻塞已启动的停点（已启动的由级联退回与复核恢复机制处理）。
    """
    for m in flow_milestones():
        if int(sid) not in [int(x) for x in m.get("blocks") or []]:
            continue
        if milestone_valid(root, name, state, m["id"])["valid"]:
            continue
        return m["id"]
    return ""


def _upstream_milestones(mid):
    """里程碑 mid 的上游里程碑：覆盖停点出现在 mid 覆盖停点的依赖闭包里。

    由 flow_model.yaml 的 covers/depends_on 推导（不硬编码 M1/M2/M3）：M3 覆盖
    行 7–12，其依赖闭包含行 1–6，故 M1（覆盖 1–3）与 M2（覆盖 4–6）都是它的上游；
    M2 的上游只有 M1。
    """
    m = flow_milestone(str(mid or "").strip())
    if m is None:
        return []
    seen = {int(x) for x in m.get("covers") or []}
    pending = list(seen)
    upstream_stops = set()
    while pending:
        for dep in flow_depends_on(pending.pop()) or []:
            dep = int(dep)
            if dep in seen:
                continue
            seen.add(dep)
            upstream_stops.add(dep)
            pending.append(dep)
    out = []
    for other in flow_milestones():
        if other["id"] == m["id"]:
            continue
        if upstream_stops & {int(x) for x in other.get("covers") or []}:
            out.append(other)
    return out


def _find_decision(state, did):
    for rows in state["decisions"].values():
        for row in rows:
            if row["id"] == did:
                return row
    return None


def _stop_number(value):
    """停点号转 int；不是数字（模块名等）时给 None。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _covers(outer, inner):
    """产物路径 outer 是否覆盖 inner：同一路径，或 inner 在目录 outer 之下。"""
    outer, inner = outer.rstrip("/"), inner.rstrip("/")
    return outer == inner or inner.startswith(outer + "/")


def _path_digest(root, name, rel, stop_id=0):
    import hashlib
    base = os.path.join(sys_dir(root, name), rel)
    # 后续停点独占的子路径（行 8 的顶层文件在行 7 的 rtl/ 之下）不进本停点指纹，
    # 否则后续停点的正常产出会被当成本停点完成后的改动而阻断。
    owned = []
    for later in load()["stops"]:
        sub = product_path(later, name)
        if later["id"] > int(stop_id) and _covers(rel, sub) and not _covers(sub, rel):
            owned.append(os.path.join(sys_dir(root, name), sub).rstrip("/"))
    digest = hashlib.sha256()
    paths = []
    if os.path.isdir(base):
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = sorted(dirnames)
            for fn in sorted(files):
                paths.append(os.path.join(dirpath, fn))
    elif os.path.isfile(base):
        paths.append(base)
    paths = [path for path in paths
             if not any(path == own or path.startswith(own + os.sep) for own in owned)]
    for path in paths:
        # 悬挂符号链接（EDA 回拉产物被后续运行覆盖/清理后常见）不参与摘要：
        # os.path.isfile 对其返回 False，否则 open 抛 FileNotFoundError 炸掉状态机。
        if not os.path.isfile(path):
            continue
        digest.update(os.path.relpath(path, sys_dir(root, name)).encode())
        with open(path, "rb") as fh:
            digest.update(fh.read())
    return digest.hexdigest()[:16]


def _product_digest(root, name, stop):
    rel = product_path(stop, name)
    if rel.rstrip("/") == "rtl":
        # 行 7 不再对整个 rtl/ 目录算一个指纹，改按模块证聚合——
        # 见 _rtl_module_digest。某个模块改动只让该模块的 lint/审查标记失效
        # （module_stale_note 标它），行级指纹据此提示退回（stale_stops），
        # 级联与复核恢复接住下游；行的"就绪"= 每个模块都有对得上
        # 当前摘要（含 include 链）的 lint 通过记录与审查记录，由行 7 的
        # lint/rtl 闸门（_lint_ok/_rtl_module_findings）与 _review_record_ok 按模块判。
        return _rtl_module_digest(root, name, stop)
    return _path_digest(root, name, rel, stop_id=stop["id"])


def _top_product_digest(base):
    """行 8 顶层产物的指纹：`rtl/<sys>_top.sv` 的路径摘要（与 _product_digest 同口径）。"""
    root, name = os.path.split(base.rstrip(os.sep))
    stop = load()["by_id"].get(8)
    if stop is None or not os.path.isfile(os.path.join(base, "rtl", name + "_top.sv")):
        return ""
    return _path_digest(root, name, product_path(stop, name), stop_id=8)


def _rtl_module_digest(root, name, stop):
    """行 7 的停点指纹 = rtl/ 下每个模块（顶层除外）module_digest 的聚合。

    module_digest 覆盖 include 链与 `// digest-extra:` 附属文件；顶层文件
    （<sys>_top.sv）属行 8，不进行 7 的模块清单（_rtl_names 按 _top 后缀排除，
    行 8 口径不变）。rtl/ 下没有模块文件时退回目录口径（仍排除行 8 独占的
    顶层文件），避免空清单给恒定指纹。
    """
    base = sys_dir(root, name)
    from framework.gates.run import _rtl_names
    names = _rtl_names(base)
    if not names:
        return _path_digest(root, name, "rtl/", stop_id=stop["id"])
    digest = hashlib.sha256()
    for mod in names:
        digest.update(("%s:%s\n" % (mod, module_digest(base, mod))).encode("utf-8"))
    return digest.hexdigest()[:16]


_INCLUDE_RE = re.compile(r"^\s*`?include\s+[\"<]([^\">]+)[\">]", re.M)


_DIGEST_EXTRA_RE = re.compile(r"//\s*digest-extra:\s*(.+)")


def _file_digest(path):
    if not os.path.isfile(path):
        return "MISSING"  # 缺失也要参与摘要，文件出现/消失必须改变摘要
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _module_files(path, seen=None, depth=0):
    """(名字, 摘要) 列表：模块文件本身 + include 链 + `// digest-extra:` 附属文件。

    改前 `module_digest` 只哈希 `rtl/<module>.sv`：本轮 `rx_cfo` 改了被 `include` 的
    1.2 MB 旋转因子表，模块摘要却不变、审查记录仍算通过。附属文件用文件里的
    `// digest-extra: <相对路径>[,<相对路径>]` 声明（生成脚本等）。
    """
    out = []
    if seen is None:
        seen = set()
    if depth > 8:
        return out
    real = os.path.realpath(path)
    if real in seen:
        return out
    seen.add(real)
    out.append((os.path.basename(path), _file_digest(path)))
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    here = os.path.dirname(path)
    for inc in _INCLUDE_RE.findall(text):
        out += _module_files(os.path.join(here, inc), seen, depth + 1)
    for line in _DIGEST_EXTRA_RE.findall(text):
        for extra in line.split(","):
            extra = extra.strip()
            if extra:
                out.append((extra, _file_digest(os.path.join(here, extra))))
    return out


def module_digest(base, module):
    """rtl/<module>.sv|.v 与其 include 链/附属文件的内容摘要；行 7 的 lint 与审查只对这一版有效。"""
    for ext in (".sv", ".v"):
        path = os.path.join(base, "rtl", module + ext)
        if os.path.isfile(path):
            parts = sorted(_module_files(path))
            if len(parts) == 1:
                # 没有 include/附属文件时保持历史算法（文件字节摘要），
                # 免得存量 lint/审查记录因为换算法而无故全部失效。
                return parts[0][1]
            blob = "\n".join("%s:%s" % item for item in parts)
            return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return ""


def _tick_command(name):
    """建议命令：停点的启动、送审与完成都归 tick。"""
    return "python3 script/framework.py tick %s" % name


def _milestone_command(name, mid, action="show"):
    """里程碑的建议命令：先出审阅包，再确认（M3 仍要终端照抄原话）。"""
    prefix = "python3 script/framework.py milestone %s %s" % (name, action)
    if action == "confirm":
        m = flow_milestone(mid) or {}
        if m.get("terminal"):
            return ('%s --id %s --confirm "确认 %s 签核放行（%s）通过"'
                    % (prefix, mid, name, m.get("id", mid)))
        return "%s --id %s --pick 通过" % (prefix, mid)
    return "%s --id %s" % (prefix, mid)


def _decision_command(name, pid):
    """点选入库的建议命令（类别由开发者按问题性质取方向或数值）。"""
    return ("python3 script/framework.py decision %s commit --from %s --pick <选项> "
            "--kind <方向|数值>" % (name, pid))

def _next_command(root, name, state, stop, row):
    """按当前真正阻塞项给出下一条可执行命令。"""
    sid = int(stop["id"])
    if row["state"] == DONE:
        return "python3 script/framework.py advance %s --stop %d --to %s" % (
            name, sid, RUNNING)
    if decision_blockers(state, sid):
        return "python3 script/framework.py problem %s list" % name
    blocking = [p for p in state.get("problems") or []
                if p.get("kind") == "阻断" and p.get("open", True)
                and int(p.get("stop") or 0) <= sid]
    if blocking:
        return "python3 script/framework.py problem %s list" % name
    if row["state"] == PENDING and sid in _milestone_done_stops():
        m = flow_milestone_of_stop(sid)
        if m:
            for other in _upstream_milestones(m["id"]):
                if not milestone_valid(root, name, state, other["id"])["valid"]:
                    return _milestone_command(name, other["id"], "show")
            return _milestone_command(name, m["id"], "show")
        return "python3 script/framework.py milestone %s show --id <M号>" % name
    if row["state"] == NOT_STARTED:
        mid = _milestone_blocking(root, name, state, sid)
        if mid:
            return _milestone_command(name, mid, "show")
    return "python3 script/framework.py tick %s" % name


def deferred_still_blocks(state, p):
    """推迟中的问题仍挡住的对象（里程碑号 / 未完成停点号）。"""
    sid = _stop_number(p.get("stop"))
    blockers = []
    if p.get("kind") == "阻断":
        blockers += ["未完成停点 %d" % int(row["id"])
                     for row in state.get("stops") or []
                     if int(row["id"]) >= sid and row["state"] != DONE]
    until = str((p.get("deferred") or {}).get("until") or "")
    for m in flow_milestones():
        if (state.get("milestones") or {}).get(m["id"]):
            continue
        if sid in [int(x) for x in m.get("covers") or []] or until == m["id"]:
            blockers.append("里程碑 %s" % m["id"])
    return blockers