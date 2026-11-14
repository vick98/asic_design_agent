# 作者：vick 邮箱：ykun@yk9811.com

"""签核记录渲染与送审闸门：闸门、裁决、覆盖率与门禁证据。"""

import hashlib, json, os
from framework.flow import (
    load as load,
)
from framework.state import stop_row, sys_dir
from framework.engine.reviews import (
    module_state,
)
from framework.engine.runs import (
    _digest_folder,
)
from framework.engine.runtime import (
    EngineError,
    SIGNOFF_FOLDER,
    _top_product_digest,
    milestone_valid,
    module_digest,
)


def _folder_digest(base, folder):
    """目录指纹（相对路径 + 内容，排序遍历）；目录不存在返回空串。"""
    digest = hashlib.sha256()
    _digest_folder(digest, base, folder)
    return digest.hexdigest()[:12] if os.path.isdir(os.path.join(base, folder)) else ""


def _violation_sends(root, name):
    """带违例送审的留痕：`{停点号: 裁决号}`（读事件日志，不新加 state 字段）。"""
    sent = {}
    path = os.path.join(sys_dir(root, name), "events.jsonl")
    if not os.path.isfile(path):
        return sent
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "带违例送审" not in line:
                continue
            try:
                event = json.loads(line)
            except (ValueError,):
                continue
            if event.get("action") == "带违例送审":
                sent[str(event.get("object") or "")] = str(event.get("evidence") or "")
    return sent


def _lint_runs_by_module(state):
    """行 7 每个模块的最后一次 lint 记录号：{模块: (R号, 摘要)}。"""
    out = {}
    for run in state.get("runs") or []:
        if run.get("capability") != "lint" or run.get("status") != "pass":
            continue
        scope = run.get("scope") or {}
        modules = scope.get("modules") or (run.get("checks") or {}).get("modules") or []
        digests = scope.get("module_digests") or {}
        for module in modules:
            out[module] = (run.get("id", ""), str(digests.get(module) or "")[:12] or "（记录未带摘要）")
    return out


def _latest_run(state, cap):
    for run in reversed(state.get("runs") or []):
        if run.get("capability") == cap:
            return run
    return None


def _signoff_blocks(root, name, state, quote):
    """签核记录的正文（逐项、只引用记录号，不抄日志）。"""
    from framework.gates.run import _rtl_names
    base = sys_dir(root, name)
    synth = _latest_run(state, "synth")
    sta = _latest_run(state, "sta")
    sim = _latest_run(state, "sim")
    cov = _latest_run(state, "coverage")
    lines = []

    def run_head(run):
        return "%s %s" % (run.get("id", "（无）"), run.get("status", "无"))

    def tool_versions(run):
        versions = ((run or {}).get("checks") or {}).get("tool_versions") or {}
        return "；".join("%s %s" % (k, v) for k, v in sorted(versions.items())) or "（未记录）"

    lines += ["## 1. 剖面与工具", ""]
    lines.append("- 剖面：%s（综合 %s / 时序 %s）"
                 % ((synth or {}).get("profile_id") or (sta or {}).get("profile_id") or "（无）",
                    run_head(synth or {}), run_head(sta or {})))
    lines.append("- 工具版本：综合 %s；时序 %s；仿真 %s；覆盖率 %s"
                 % (tool_versions(synth), tool_versions(sta), tool_versions(sim), tool_versions(cov)))

    lines += ["", "## 2. 模块、回归与覆盖率", ""]
    lint_runs = _lint_runs_by_module(state)
    modules = _rtl_names(base)
    for module in modules:
        rid, digest = lint_runs.get(module, ("（无 lint 记录）", ""))
        lines.append("- 行 7 模块 %s：lint %s，模块摘要 %s，状态 %s"
                     % (module, rid, digest or module_digest(base, module)[:12],
                        module_state(state, base, "7", module)))
    top = name + "_top"
    lines.append("- 行 8 顶层 %s：状态 %s，产物摘要 %s"
                 % (top, module_state(state, base, "8", top), _top_product_digest(base)[:12] or "（无）"))
    if sim is None:
        lines.append("- 全量回归：R（无）")
    else:
        checks = sim.get("checks") or {}
        cases = int(checks.get("result_pass") or 0) + int(checks.get("result_fail") or 0)
        seeds = ((sim.get("scope") or {}).get("seeds") or [])
        lines.append("- 全量回归：%s（用例 %d × seed %d；结果 通过 %s 失败 %s%s）"
                     % (run_head(sim), cases, len(seeds),
                        checks.get("result_pass", "—"), checks.get("result_fail", "—"),
                        "；全量" if checks.get("full_regression") else ""))
    if cov is None:
        lines.append("- 覆盖率：R（无）")
    else:
        checks = cov.get("checks") or {}
        sources = ["剖面缺省"]
        for item in state.get("waivers") or []:
            if item.get("rule") == "COV":
                sources.append("豁免 %s ← %s" % (item.get("where", ""), item.get("decision", "")))
        lines.append("- 覆盖率：%s（line %s / cond %s / fsm %s / tgl %s；阈值来源：%s）"
                     % (run_head(cov), checks.get("line", "—"), checks.get("cond", "—"),
                        checks.get("fsm", "—"), checks.get("tgl", "—"), " + ".join(sources)))

    lines += ["", "## 3. 综合与时序", ""]
    if synth is None:
        lines.append("- 综合：R（无）")
    else:
        checks = synth.get("checks") or {}
        lines.append("- 综合：%s（面积 %s，latch %s，错误 %s）"
                     % (run_head(synth), checks.get("area", "—"),
                        checks.get("latches", "—"), checks.get("errors", "—")))
    if sta is None:
        lines.append("- 时序：R（无）")
    else:
        checks = sta.get("checks") or {}
        corners = checks.get("corners") or []
        detail = "；".join(
            "%s：setup WNS %s，hold WNS %s，违例 %s/%s"
            % (corner.get("name") or corner.get("corner") or ("角 %d" % (index + 1)),
               corner.get("setup_wns", "—"), corner.get("hold_wns", "—"),
               corner.get("setup_violations", "—"), corner.get("hold_violations", "—"))
            for index, corner in enumerate(corners)) or "（记录未带分角明细）"
        lines.append("- 时序：%s（%s；未约束端点 %s）"
                     % (run_head(sta), detail, checks.get("unconstrained_endpoints", "—")))

    lines += ["", "## 4. 红线留痕", ""]
    waivers = state.get("waivers") or []
    lines.append("- 豁免：%s" % ("；".join("%s %s ← %s" % (item.get("rule", ""), item.get("where", ""),
                                                            item.get("decision", ""))
                                          for item in waivers) or "（无）"))
    violations = _violation_sends(root, name)
    lines.append("- 带违例送审：%s" % ("；".join("%s ← %s" % (stop, evidence)
                                                for stop, evidence in sorted(violations.items()))
                                       or "（无）"))
    # 审查记录（行 9 的 tb_review 也在其中）：只引用记录种类、报告路径与派工号，不抄报告正文。
    reviews = []
    for row in state.get("stops") or []:
        for rev in row.get("reviews") or []:
            reviews.append("停点 %s %s ← %s（%s/%s）"
                           % (row["id"], rev.get("kind", ""), rev.get("report") or "（无报告）",
                              rev.get("author", ""), rev.get("reviewer", "")))
    for row_id, mods in sorted((state.get("modules") or {}).items()):
        for mod in mods:
            if mod.get("kind"):
                reviews.append("行 %s %s %s ← %s（%s/%s）"
                               % (row_id, mod.get("kind"), mod.get("name"),
                                  mod.get("report") or "（无报告）",
                                  mod.get("author", ""), mod.get("reviewer", "")))
    lines.append("- 审查记录：%s" % ("；".join(reviews) or "（无）"))
    milestones = state.get("milestones") or {}
    for mid in ("M1", "M2", "M3"):
        record = milestones.get(mid)
        if not record:
            lines.append("- 里程碑 %s：未确认" % mid)
            continue
        validity = ""
        if mid in ("M1", "M2"):
            validity = "，当前%s" % ("有效" if milestone_valid(root, name, state, mid)["valid"] else "已失效")
        lines.append("- 里程碑 %s：%s 确认（%s）%s"
                     % (mid, record.get("time", ""), record.get("quote", ""), validity))

    lines += ["", "## 5. 收尾核对", ""]
    lines.append("- 在途调试事项：%d（必须为 0）" % len(state.get("items") or []))
    blocking = [p for p in state.get("problems") or []
                if p.get("kind") == "阻断" and p.get("open", True)]
    lines.append("- 未关闭阻断：%d（必须为 0）" % len(blocking))
    lines.append("- RTL 目录指纹：%s；SDC 摘要：%s"
                 % (_folder_digest(base, "rtl") or "（无）", _folder_digest(base, "sdc") or "（无）"))
    lines.append("- 放行：%s" % (quote or "（未记录：以 M3 确认记录为准）"))
    return lines


def _signoff_stop_id():
    """签核停点号：gates 含 signoff 的停点（读模型，不写死行 12）。"""
    for stop in load()["stops"]:
        if "signoff" in (stop.get("gates") or []):
            return int(stop["id"])
    return 0


def _require_gates(root, name, state, stop, allow_violation):
    from framework.gates.run import run_gates
    findings = run_gates(root, name, stop["id"], state, allow_violation=allow_violation)
    blocking = [item for item in findings if item.get("level") != "hint"]
    if blocking:
        item = blocking[0]
        raise EngineError("闸门未过：[%s] %s" % (item.get("rule", "?"), item.get("detail") or item),
                          findings)
    if "signoff" in (stop.get("gates") or []):
        render_signoff(root, name, state)


def render_signoff(root, name, state, confirm=""):
    """渲染中端签核记录：逐项引用记录号与摘要，不抄日志。

    覆盖模块 lint/摘要、全量回归、覆盖率与阈值来源、综合与时序明细、剖面与工具版本、
    豁免与带违例送审留痕、三个里程碑的确认时间/语句与 M1/M2 当前有效性、收尾核对
    （在途事项 0、未关闭阻断 0）、RTL 目录指纹与 SDC 摘要。
    """
    from framework.gates.run import _rtl_names as _names
    del _names
    signoff_sid = _signoff_stop_id()
    quote = confirm or (
        stop_row(state, signoff_sid).get("confirm_quote")
        if state and signoff_sid else "") or ""
    text = "\n".join(
        ["# %s 中端签核" % name, "",
         "本文件由引擎按 state.json 与运行记录渲染；只引用记录号与摘要，不抄日志。", ""]
        + _signoff_blocks(root, name, state, quote) + [""])
    path = os.path.join(sys_dir(root, name), SIGNOFF_FOLDER, "%s_signoff.md" % name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
