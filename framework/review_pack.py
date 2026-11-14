# 作者：vick 邮箱：ykun@yk9811.com

"""把停点审核材料收成一份给主持者的文本；里程碑审阅包也在这里生成。"""

import json
import os
import random
import re

from framework.flow import load, milestone as flow_milestone, product_path
from framework.gates.run import run_gates
from framework.paths import project_root
from framework.state import load_state, stop_row, sys_dir


def review_text(root, name, stop_id):
    state = load_state(root, name)
    model = load()
    stop = model["by_id"][int(stop_id)]
    lines = ["# 停点 %s 审核" % stop_id, ""]
    review_name = "spec.md" if int(stop_id) <= 6 else "rtl.md"
    review_path = os.path.join(project_root(), "rules", "review", review_name)
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as fh:
            lines.append(fh.read().strip())
            lines.append("")
    findings = [item for item in run_gates(root, name, stop_id, state) if item.get("level") != "hint"]
    lines.append("闸门：%s" % ("通过" if not findings else "失败 %d" % len(findings)))
    for item in findings[:20]:
        lines.append("- [%s] %s" % (item.get("rule"), item.get("detail")))
    lines.append("")
    lines.append("最近运行：")
    runs = state.get("runs") or []
    if not runs:
        lines.append("- （无）")
    for run in runs[-5:]:
        arts = "、".join(run.get("artifacts") or []) or "（无产物路径）"
        lines.append("- %s %s %s %s" % (run.get("id"), run.get("capability"), run.get("status"), arts))
    lines.append("")
    lines.append("产出：%s" % product_path(stop, name))
    return "\n".join(lines) + "\n"


def _read_doc(root, name, rel):
    path = os.path.join(root, name, rel)
    if not os.path.isfile(path):
        return "（缺 %s）" % rel
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip() or "（空）"


def _doc_section(root, name, rel, keyword, fallback_lines=60):
    """取文档里标题含 keyword 的章节正文（同关键词的兄弟节合并取全）。"""
    text = _read_doc(root, name, rel)
    lines = text.splitlines()
    start = None
    level = 0
    for index, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        hlevel = len(line) - len(line.lstrip("#"))
        if start is None:
            if keyword in line:
                start = index + 1
                level = hlevel
            continue
        if hlevel <= level:
            if keyword in line and hlevel == level:
                continue
            return "\n".join(lines[start:index]).strip() or "（空）"
    if start is not None:
        return "\n".join(lines[start:]).strip() or "（空）"
    return "（未找到「%s」章节：本阶段未写）" % keyword


def _module_specs(root, name):
    """spec_doc/ 下的模块规格书（<模块>_spec.md，除子系统规格书本身），按名字排序。"""
    base = os.path.join(root, name, "spec_doc")
    if not os.path.isdir(base):
        return []
    return sorted(fn for fn in os.listdir(base)
                  if fn.endswith("_spec.md") and fn != "%s_spec.md" % name)


def _module_type(root, name, fn):
    with open(os.path.join(root, name, "spec_doc", fn), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("模块类型"):
                return line.split("：", 1)[1].strip() or "（未写）"
    return "（未写）"


def _decisions_lines(root, name, state, record_only=False, human_only=False):
    """裁决清单；记录类条目用 engine.record_kind_hints 高亮疑似方向/数值。

    human_only：只要方向/数值类——M1 包只放这类裁决，记录类另有高亮表。
    """
    from framework.engine import record_kind_hints
    lines = ["| 编号 | 类别 | 裁决内容 | 备注 |", "|------|------|----------|------|"]
    any_row = False
    for step, rows in sorted((state.get("decisions") or {}).items()):
        for row in rows:
            if record_only and row.get("kind") != "记录":
                continue
            if human_only and row.get("kind") not in ("方向", "数值"):
                continue
            any_row = True
            content = row.get("content", "")
            note = row.get("note", "")
            if row.get("kind") == "记录":
                hints = record_kind_hints(root, name, content)
                if hints:
                    note = "；".join(filter(None, ["【疑似方向/数值：%s】" % "；".join(hints), note]))
            lines.append("| %s | %s | %s | %s |" % (
                row.get("id", ""), row.get("kind", ""),
                content.replace("\n", " ").replace("|", "\\|"),
                note.replace("\n", " ").replace("|", "\\|")))
    if not any_row:
        label = "记录类条目" if record_only else ("方向/数值裁决" if human_only else "裁决")
        lines.append("| — | — | （无%s） | — |" % label)
    return lines


def _report_table(root, name, rel, limit=4):
    """按审查记录取报告原文的"发现与处置"表（抽样展示，不整份内嵌）。

    报告不存在时返回一行提示（记录里挂着路径但文件被删，审阅包要看得出来）。
    """
    path = os.path.join(sys_dir(root, name), rel)
    if not os.path.isfile(path):
        return ["  - 报告 %s：文件不存在（记录里有、盘上没了）" % rel]
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip().startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line.strip()):
                rows.append(line.strip())
    if not rows:
        return ["  - 报告 %s：没有表格行" % rel]
    head = rows[0]
    body = [row for row in rows[1:] if "发现编号" not in row]
    return ["  - 报告 %s（抽样 %d 行）" % (rel, min(limit, len(body))), "    " + head] + \
           ["    " + row for row in body[:limit]]


def _reviews_lines(root, name, state):
    """独立审查发现及处置：审查记录（含报告原文抽样）+ 阻断发现的关闭证据。"""
    lines = []
    for row in state.get("stops") or []:
        for rev in row.get("reviews") or []:
            lines.append("- 停点 %s：%s，作者 %s、审查者 %s，发现 %s，阻断 0（%s）"
                         % (row["id"], rev.get("kind", ""), rev.get("author", ""),
                            rev.get("reviewer", ""), rev.get("findings", 0), rev.get("time", "")))
            if rev.get("report"):
                lines += _report_table(root, name, rev["report"])
    for row_id, mods in sorted((state.get("modules") or {}).items()):
        for mod in mods:
            if mod.get("kind") == "rtl_review":
                lines.append("- 行 %s 模块 %s：rtl_review，作者 %s、审查者 %s，发现 %s（%s）"
                             % (row_id, mod.get("name"), mod.get("author", ""),
                                mod.get("reviewer", ""), mod.get("findings", 0), mod.get("time", "")))
                if mod.get("report"):
                    lines += _report_table(root, name, mod["report"])
    closed = [p for p in state.get("problems") or [] if not p.get("open", True)]
    for p in closed:
        lines.append("- 问题 %s 已关闭（证据 %s）：%s" % (p["id"], p.get("evidence", ""), p["text"]))
    return lines or ["- （无审查记录）"]


def _open_problems_lines(state):
    lines = []
    for p in state.get("problems") or []:
        if not p.get("open", True):
            continue
        parts = ["%s %s（停点 %s）：%s" % (
            p["id"], p.get("kind", ""), p.get("stop"), p["text"])]
        if p.get("options"):
            parts.append("候选：%s" % " | ".join(p["options"]))
        if p.get("blocks"):
            parts.append("阻塞：%s" % "、".join(str(b) for b in p["blocks"]))
        deferred = p.get("deferred") or {}
        if deferred:
            parts.append("推迟至 %s（%s）" % (
                deferred.get("until") or "—", deferred.get("reason") or "—"))
        lines.append("- " + "；".join(parts))
    return lines or ["- （无未决问题）"]


def _runs_lines(state, capabilities=None, limit=10):
    lines = []
    for run in reversed(state.get("runs") or []):
        if capabilities and run.get("capability") not in capabilities:
            continue
        checks = run.get("checks") or {}
        lines.append("- %s %s %s %s（%s）：%s" % (
            run.get("id"), run.get("capability"), run.get("status"), run.get("time", ""),
            run.get("profile_id") or "无剖面", run.get("summary") or ""))
        if len(lines) >= limit:
            break
    return lines or ["- （无%s运行记录）" % "/".join(capabilities) if capabilities else "- （无运行记录）"]


def _test_points_lines(root, name, specs):
    """测试要点总数与覆盖关系：各模块规格书"测试要点"章节的条目数。"""
    from framework.trace import _parse_test_points
    points, _ = _parse_test_points(os.path.join(root, name))
    counts = {}
    for point in points:
        counts[point["module"]] = counts.get(point["module"], 0) + 1
    total = 0
    lines = []
    for fn in specs:
        module = fn[:-len("_spec.md")]
        count = counts.get(module, 0)
        total += count
        lines.append("- %s：%d 条测试要点" % (module, count))
    lines.append("- 测试要点总数：%d 条（逐模块列于上，编码时按模块覆盖）" % total)
    return lines


def _rtl_names(root, name):
    rtl = os.path.join(root, name, "rtl")
    if not os.path.isdir(rtl):
        return []
    return sorted(fn.rsplit(".", 1)[0] for fn in os.listdir(rtl)
                  if fn.endswith((".sv", ".v")) and not fn.startswith(name + "_top"))


def _milestone_head(root, name, m, gate_section=True):
    from framework.engine import _milestone_command
    head = [
        "# 里程碑 %s %s（审阅包）" % (m["id"], m.get("name", "")),
        "",
        "覆盖停点：%s；阻塞：%s；终端照抄：%s" % (
            "、".join(str(x) for x in m.get("covers") or []),
            "、".join(str(x) for x in m.get("blocks") or []) or "无",
            "是（confirm 要 --confirm 原话并在终端照抄）" if m.get("terminal") else "否（点选确认）"),
        "",
        "本文件由 `%s` 生成。开发者读后用 `%s` 或 `%s` 回答。"
        % (_milestone_command(name, m["id"], "show"),
           _milestone_command(name, m["id"], "confirm"),
           "python3 script/framework.py milestone %s reject --id %s --reason ..."
           % (name, m["id"])),
        "",
    ]
    if gate_section:
        head += ["## 闸门摘要", ""]
    return head


def _gate_lines(root, name, state, covered):
    lines = []
    for sid in covered:
        findings = [item for item in run_gates(root, name, sid, state)
                    if item.get("level") != "hint"]
        lines.append("- 停点 %d 闸门：%s" % (sid, "通过" if not findings else "失败 %d" % len(findings)))
        for item in findings[:5]:
            lines.append("  - [%s] %s" % (item.get("rule", "?"), item.get("detail", "")))
    return lines


def _sdc_section(root, name, state):
    """SDC 全文：取最近一次综合/时序运行记录携带的 SDC 路径。"""
    paths = []
    for run in reversed(state.get("runs") or []):
        if run.get("capability") in ("synth", "sta") and run.get("sdc_paths"):
            paths = list(run["sdc_paths"])
            break
    if not paths:
        return ["（无 SDC 运行记录：综合/时序运行时用 run --sdc 携带约束文件）"]
    lines = []
    for rel in paths:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.isfile(path):
            path = os.path.join(root, name, rel)
        lines.append("来源：%s" % rel)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines.append("```sdc")
                lines.append(fh.read().rstrip())
                lines.append("```")
        else:
            lines.append("（文件不存在：%s）" % path)
    return lines


def _events_lines(root, name, action, prefix=()):
    path = os.path.join(root, name, "events.jsonl")
    import json
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln.startswith("{"):
                    continue
                try:
                    event = json.loads(ln)
                except Exception:
                    continue
                if event.get("action") != action:
                    continue
                evidence = str(event.get("evidence") or "")
                if prefix and not any(evidence.startswith(p) for p in prefix):
                    continue
                lines.append("- %s %s：%s" % (event.get("time", ""), event.get("object", ""), evidence))
    return lines or ["- （无%s记录）" % action]


def _m1_sections(root, name, state, covered):
    """M1 包（减负）：结论摘要为唯一入口，原文只留链接。

    rules/host/design.md 早就要求 M1 出 3–6 条结论摘要，实现却一直整份内嵌三份文档；
    现在摘要由主持者写进 <sys>/milestone_notes/M1.md，条数由闸门检查
    （engine._milestone_notes_reasons），审阅包只放摘要 + 链接。
    """
    from framework.engine import milestone_note_lines
    products = ("info_input/%s_info_overview.md" % name,
                "flow_doc/%s_flow.md" % name,
                "plan_doc/%s_plan.md" % name)
    notes = milestone_note_lines(root, name, "M1")
    summary = "\n".join(notes) if notes else (
        "（缺结论摘要：按 rules/host/design.md 的模板写 milestone_notes/M1.md，3–6 条）")
    return [
        ("结论摘要（milestone_notes/M1.md，原文只留链接）", summary),
        ("原文链接", "\n".join("- %s" % rel for rel in products)),
        ("全部方向/数值裁决", "\n".join(_decisions_lines(root, name, state, human_only=True))),
        ("冲突与红线五问的处置",
         "\n\n".join([_doc_section(root, name, products[0], "冲突"),
                      _doc_section(root, name, products[0], "红线五问")])),
        ("独立审查发现及处置", "\n".join(_reviews_lines(root, name, state))),
        ("未决问题", "\n".join(_open_problems_lines(state))),
    ]


def _trace_result(root, name, state):
    from framework.trace import trace_matrix
    return trace_matrix(sys_dir(root, name), state)


def _trace_coverage_lines(root, name, state):
    """M2 的「输入要点→测试要点覆盖率」：只算输入要点到测试要点这一层。"""
    result = _trace_result(root, name, state)
    summary = result["summary"]
    lines = [
        "- 矩阵口径：输入要点一行，沿各表「来源」列追溯到测试要点；覆盖率只算输入要点→测试要点这一层。",
        "- 输入要点 %d 条，已追溯到测试要点 %d 条，覆盖率 %d%%（%s）"
        % (summary["input_points"], summary["traced_points"],
           summary["coverage_percent"], summary["coverage"]),
        "- 强约束输入要点 %d 条，未追溯 %d 条"
        % (summary["strong_input_points"], summary["strong_uncovered"]),
    ]
    if result["uncovered"]:
        lines.append("- 未追溯：" + "、".join(
            "%s（%s）" % (item["input"], item["credibility"] or "未定级")
            for item in result["uncovered"]))
    else:
        lines.append("- 未追溯：无")
    regression = result.get("regression")
    lines.append("- 最近全量回归：%s" % (
        "%s %s" % (regression["id"], regression["status"]) if regression else "（无）"))
    return lines


def _demote_markdown(text, by=2):
    """把内嵌文档的标题整体降到 H3 起步，避免同级或跳级。"""
    lines = str(text or "").splitlines()
    levels = [len(line) - len(line.lstrip("#"))
              for line in lines if line.startswith("#")]
    shift = (3 - min(levels)) if levels else 0
    out = []
    for line in lines:
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            level = max(1, min(6, level + shift))
            line = "#" * level + line[level - shift:]
        out.append(line)
    return "\n".join(out)


def _trace_matrix_lines(root, name, state):
    """M3 的「需求追溯矩阵统计」：统计、未覆盖清单与完整矩阵。"""
    from framework.trace import render_markdown
    result = _trace_result(root, name, state)
    summary = result["summary"]
    lines = [
        "- 输入要点 %d 条，已追溯到测试要点 %d 条，覆盖率 %d%%（%s）"
        % (summary["input_points"], summary["traced_points"],
           summary["coverage_percent"], summary["coverage"]),
        "- 强约束输入要点 %d 条，未覆盖 %d 条；测试要点 %d 条；用例 %d 条"
        % (summary["strong_input_points"], summary["strong_uncovered"],
           summary["test_points"], summary["cases"]),
    ]
    if result["uncovered"]:
        lines.append("- 未覆盖：" + "、".join(
            "%s（%s）" % (item["input"], item["credibility"] or "未定级")
            for item in result["uncovered"]))
    else:
        lines.append("- 未覆盖：无")
    regression = result.get("regression")
    lines.append("- 最近全量回归：%s" % (
        "%s %s" % (regression["id"], regression["status"]) if regression else "（无）"))
    lines.append("")
    lines.append(_demote_markdown(render_markdown(result).rstrip()))
    return lines


def _risk_score(root, name, state, candidate):
    """风险分：关联裁决数 + 审查发现数 + 回修次数 + 端口数（抽样排序用）。

    四个分量都从既有记录里数，不新增字段：裁决看正文/来源是否点到该对象；审查发现
    看模块条目/停点审查记录；回修看事件日志里"事项收尾"的证据是否点到它；端口数从
    规格书端口表的数据行数来。
    """
    hits = 0
    for rows in (state.get("decisions") or {}).values():
        for row in rows:
            body = "%s %s" % (row.get("content") or "", row.get("source") or "")
            if candidate in body:
                hits += 1
    findings = 0
    for _row_id, mods in (state.get("modules") or {}).items():
        for mod in mods:
            if mod.get("name") == candidate:
                findings += int(mod.get("findings") or 0)
    reworks = len([line for line in _events_lines(root, name, "事项收尾")
                   if candidate in line])
    ports = 0
    for rel in ("spec_doc/%s_spec.md" % candidate, "spec_doc/%s_spec.md" % name):
        text = _doc_section(root, name, rel, "端口表")
        if text and candidate in rel:
            ports = len([line for line in text.splitlines()
                         if line.strip().startswith("|") and "---" not in line])
            break
    return (hits, findings, reworks, ports)


def _risk_sample(root, name, state, candidates, mid):
    """风险优先抽样——按四分量排序取前二，再随机取一个；种子写进包、可复现。

    种子由"子系统名/里程碑"决定（同一子系统两次出包同一抽样），随机只用于第三项；
    排序键与种子都会渲染进审阅包，便于复核。
    """
    if not candidates:
        return [], ""
    scored = sorted(candidates, key=lambda item: (-sum(_risk_score(root, name, state, item)), item))
    top = scored[:2]
    rest = scored[2:]
    picked = []
    if rest:
        rng = random.Random("%s/%s" % (name, mid))
        picked = [rng.choice(rest)]
    sampled = top + picked
    note = ("抽样口径：风险优先（关联裁决数 + 审查发现数 + 回修次数 + 端口数）排序取前二"
            "（%s），再从其余 %d 个里随机取一（%s）；种子 %s/%s（同子系统同里程碑可复现）"
            % ("、".join(top) or "—", len(rest), "、".join(picked) or "—", name, mid))
    return sampled, note


def _m2_sections(root, name, state, covered):
    specs = _module_specs(root, name)
    names = [fn[:-len("_spec.md")] for fn in specs]
    sampled, sample_note = _risk_sample(root, name, state, names, "M2")
    sections = [
        ("抽样口径（可复现）", sample_note or "（没有模块规格书可抽样）"),
        ("子系统规格书端口表（spec_doc/%s_spec.md）" % name,
         _doc_section(root, name, "spec_doc/%s_spec.md" % name, "端口表")),
        ("模块清单与类型",
         "\n".join("- %s：类型 %s" % (fn[:-len("_spec.md")], _module_type(root, name, fn))
                   for fn in specs) or "- （无模块规格书）"),
    ]
    for mod in sampled:
        sections.append((
            "抽样模块规格书：%s（结构 + 逻辑块）" % mod,
            "【模块实现结构】\n%s\n\n【模块逻辑块描述】\n%s" % (
                _demote_markdown(_doc_section(
                    root, name, "spec_doc/%s_spec.md" % mod, "实现结构")),
                _demote_markdown(_doc_section(
                    root, name, "spec_doc/%s_spec.md" % mod, "逻辑块")))))
    sections += [
        ("测试要点总数与覆盖关系", "\n".join(_test_points_lines(root, name, specs))),
        ("输入要点→测试要点覆盖率", "\n".join(_trace_coverage_lines(root, name, state))),
        ("审查发现处置表", "\n".join(_reviews_lines(root, name, state))),
        ("记录类条目（疑似方向/数值高亮）",
         "\n".join(_decisions_lines(root, name, state, record_only=True))),
        ("未决问题", "\n".join(_open_problems_lines(state))),
    ]
    return sections


def _m3_sections(root, name, state, covered):
    # 签核文件按当前 state 重渲染：避免 M3 包里的“未关闭阻断：0”是加问题前的快照。
    from framework.engine.signoff import render_signoff
    m3 = (state.get("milestones") or {}).get("M3") or {}
    render_signoff(root, name, state, confirm=m3.get("quote") or "")
    signoff_text = _read_doc(root, name, "signoff/%s_signoff.md" % name)
    # 内嵌到“## 签核记录”下：标题整体降到 H3 起步。
    signoff_text = _demote_markdown(signoff_text)
    autodone = []
    for sid in covered:
        row = stop_row(state, sid)
        autodone.append("- 停点 %d：%s，完成时间 %s，指纹 %s"
                        % (sid, row["state"], row.get("done_at") or "—", row.get("fingerprint") or "—"))
    walkthrough = []
    state_mods = {item.get("name"): item for item in state.get("modules", {}).get("7") or []}
    from framework.engine import module_state
    from framework.state import sys_dir
    base = sys_dir(root, name)
    sampled, sample_note = _risk_sample(root, name, state, _rtl_names(root, name), "M3")
    for mod in sampled:
        item = state_mods.get(mod) or {}
        walkthrough.append("- 模块 %s：状态 %s，作者 %s、审查者 %s，摘要 %s"
                           % (mod, module_state(state, base, "7", mod), item.get("author", ""),
                              item.get("reviewer", ""), (item.get("digest") or "")[:16] or "—"))
    return [
        ("自动完成清单", "\n".join(autodone)),
        ("回修清单（L0/L1）", "\n".join(_events_lines(root, name, "事项收尾", prefix=("L0", "L1")))),
        ("综合与时序运行记录", "\n".join(_runs_lines(state, capabilities=("synth", "sta")))),
        ("SDC 全文", "\n".join(_sdc_section(root, name, state))),
        ("覆盖率", "\n".join(_runs_lines(state, capabilities=("coverage",), limit=3))),
        ("需求追溯矩阵统计", "\n".join(_trace_matrix_lines(root, name, state))),
        ("抽样口径（可复现）", sample_note or "（rtl/ 下没有模块可抽样）"),
        ("抽样模块的 RTL 走查", "\n".join(walkthrough) or "- （rtl/ 下没有模块）"),
        ("未决问题", "\n".join(_open_problems_lines(state))),
        ("签核记录", signoff_text),
    ]


# 审阅包内容结构固定；里程碑的 id/覆盖/terminal 等事实仍从
# flow_model.yaml 的 milestones: 读，这里不复制对应关系。
_SECTIONS_BY_MILESTONE = {"M1": _m1_sections, "M2": _m2_sections, "M3": _m3_sections}


def _events_after_last_confirm(root, name, mid):
    """events.jsonl 里里程碑 mid 上次"里程碑确认"事件之后的全部事件。

    界取事件行（上次确认那条之后的每一行），与简报"自上一个里程碑以来"同款
    口径——时间只有分钟粒度，靠时间比较会把确认前同一分钟的事务也算进来。
    日志里找不到该确认行时退回全部事件：增量包宁可多列，不漏列。
    """
    path = os.path.join(root, name, "events.jsonl")
    events = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    events.append(json.loads(line))
                except (ValueError,):
                    continue
    boundary = [i for i, ev in enumerate(events)
                if ev.get("action") == "里程碑确认"
                and str(ev.get("object") or "") == str(mid)]
    return events[boundary[-1] + 1:] if boundary else events


def _delta_event_lines(events, actions, levels=None, index=None):
    """增量包的一节：指定事件动作（事项收尾再按 L0–L3 级别过滤）。

    事件的 evidence 只带编号与类别（裁决正文、问题正文在 state.json 里），
    增量审阅包是给开发者读的，index 命中时把正文补在括号里。
    """
    lines = []
    for ev in events:
        action = ev.get("action", "")
        if action not in actions:
            continue
        evidence = str(ev.get("evidence") or "")
        if levels is not None and evidence.split("；")[0].strip() not in levels:
            continue
        text = "- %s %s：%s" % (ev.get("time") or "—", ev.get("object") or "—", evidence)
        row = (index or {}).get(str(ev.get("object") or "")) or {}
        summary = str(row.get("content") or row.get("text") or "").strip().replace("\n", " ")
        if summary:
            text += "（%s%s）" % (summary[:80], "…" if len(summary) > 80 else "")
        lines.append(text)
    return lines or ["- （无）"]


def _records_index(state):
    """裁决号 / 问题号 → 记录，供增量包把事件里的编号补成正文。"""
    decisions = {}
    for rows in (state.get("decisions") or {}).values():
        for row in rows or []:
            decisions[str(row.get("id") or "")] = row
    problems = {str(row.get("id") or ""): row for row in state.get("problems") or []}
    return decisions, problems


def _milestone_delta_sections(root, name, state, m, valid):
    """需复核里程碑的增量审阅包内容：只列"自上次确认以来"的变化。

    - 指纹变化的覆盖停点（milestone_valid 的 changed）；
    - 上次确认以来入库/改写的裁决（裁决入库/改写/撤回事件）；
    - 上次确认以来的 L0–L3 回修（事项收尾，级别写在 evidence 首段）；
    - 上次确认以来关闭的问题（问题关闭事件）。
    """
    events = _events_after_last_confirm(root, name, m["id"])
    decisions, problems = _records_index(state)
    return [
        ("自上次确认以来指纹变化的停点",
         ["- %s" % item for item in valid.get("details") or []] or ["- （无）"]),
        ("自上次确认以来入库/改写的裁决",
         _delta_event_lines(events, ("裁决入库", "裁决改写", "裁决撤回"), index=decisions)),
        ("自上次确认以来的 L0–L3 回修",
         _delta_event_lines(events, ("事项收尾",), levels=("L0", "L1", "L2", "L3"))),
        ("自上次确认以来关闭的问题",
         _delta_event_lines(events, ("问题关闭",), index=problems)),
    ]


def milestone_report(root, name, mid):
    """里程碑审阅包：复用 review_text 的闸门与运行记录摘要，按里程碑分档
    出内容；记录类条目按疑似方向/数值高亮。返回文本（调用方落 <sys>/milestone_<id>.md）。

    已确认但"需复核"的里程碑（覆盖停点或产物在上次确认后变了）只出增量审阅包：
    自上次"里程碑确认"以来的指纹变化、裁决、L0–L3 回修与关闭的问题。
    """
    m = flow_milestone(str(mid or "").strip())
    if m is None:
        raise ValueError("没有里程碑 %s" % mid)
    covered = [int(x) for x in m.get("covers") or []]
    state = load_state(root, name)
    from framework.engine import milestone_valid, _milestone_command
    valid = milestone_valid(root, name, state, m["id"])
    lines = _milestone_head(root, name, m, gate_section=not valid["needs_review"])
    if valid["needs_review"]:
        lines += [
            "## 需复核（增量审阅包）",
            "",
            "本里程碑已确认，但覆盖停点或产物在上次确认后有变化（变更停点 %s）。"
            "以下只列自上次「里程碑确认」以来的变化；复核无误后用 "
            "`%s` 再次确认（旧记录进 history，不删）。"
            % ("、".join(str(x) for x in valid["changed"]),
               _milestone_command(name, m["id"], "confirm")),
            "",
        ]
        for title, body in _milestone_delta_sections(root, name, state, m, valid):
            lines += ["## %s" % title, ""]
            lines += body
            lines.append("")
        return "\n".join(lines) + "\n"
    lines += _gate_lines(root, name, state, covered)
    lines += ["", "## 最近运行", ""]
    lines += _runs_lines(state, limit=8)
    builder = _SECTIONS_BY_MILESTONE.get(m["id"])
    for title, body in (builder(root, name, state, covered) if builder else []):
        lines += ["", "## %s" % title, "", body if body.strip() else "（空）"]
    return "\n".join(lines) + "\n"
