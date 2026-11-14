# 作者：vick 邮箱：ykun@yk9811.com

"""控制信息的只读查询：裁决、问题、事项与事件。

读路径与写路径同源（`state.json` / `events.jsonl`），这里只做过滤、
相似度排名与格式化，**不改任何文件**。两种出口：
- 文本（markdown 表/清单）给人读；
- `--json`（纯 JSON 单对象）给智能体——约定与 `status --json` 一致：
  stdout 只有一份 JSON，提示与错误走 stderr、退出码非 0。

规则口径见 `rules/decision.md` 与 `rules/documents.md`：agent 取控制
信息一律走命令，不以读信息为目的打开 `state.json` 与渲染物。
"""

import json
import os
import re

from framework.engine.decisions import _content_grams, content_overlaps
from framework.engine.runtime import EngineError, _find_decision
from framework.state import EVENTS_FILE, state_path, sys_dir


def _table(headers, rows):
    lines = ["| %s |" % " | ".join(headers), "|%s|" % "|".join("---" for _ in headers)]
    for row in rows:
        lines.append("| %s |" % " | ".join("" if cell is None else str(cell) for cell in row))
    return lines


def _stage_titles():
    from framework import flow
    return {str(stage): flow.stage_title(stage) for stage in flow.stages()}


def _text_match(pattern, *texts):
    """正文匹配：pattern 可编译成正则就按正则（忽略大小写），否则退回子串。"""
    hay = "\n".join(str(item or "") for item in texts)
    try:
        return bool(re.compile(str(pattern), re.I).search(hay))
    except re.error:
        return str(pattern).lower() in hay.lower()


def _plain(text):
    """多行正文压成单行，避免打断 markdown 表格/清单。"""
    return " ".join(str(text or "").split())


# ------------------------------------------------------------------ 裁决


def decision_rows(state):
    """`state["decisions"]` 的扁平化视图（按阶段、入库顺序）。

    行字段：id / kind / stage / stage_title / stop / content / note /
    source / time / withdrawn / revisions（override 次数）。
    返回新字典，调用方改不到 state。
    """
    titles = _stage_titles()
    rows = []
    for step in sorted(state.get("decisions") or {}, key=int):
        for row in state["decisions"].get(step) or []:
            rows.append({
                "id": row["id"],
                "kind": row.get("kind", ""),
                "stage": str(step),
                "stage_title": titles.get(str(step), str(step)),
                "stop": row.get("stop"),
                "content": row.get("content", ""),
                "note": row.get("note", ""),
                "source": row.get("source", ""),
                "time": row.get("time", ""),
                "withdrawn": bool(row.get("withdrawn")),
                "revisions": len(row.get("history") or []),
            })
    return rows


def problem_sections(state):
    """待裁决与已推迟两组未关闭问题（副本，互斥）。

    与状态文档渲染同一口径：已推迟的问题不再进"待裁决"组——推迟的
    问题保持打开，但等条件满足后才重新回到点选队列（rules/decision.md）。
    """
    pending = [dict(item) for item in state.get("problems") or []
               if item.get("open", True) and item.get("kind") == "待裁决"
               and not item.get("deferred")]
    deferred = [dict(item) for item in state.get("problems") or []
                if item.get("open", True) and item.get("deferred")]
    return pending, deferred


def query_decisions(state, kind="", stop=0, stage=None, grep="",
                    threshold=0.25, limit=None):
    """按条件过滤裁决；grep 命中的排前，正文相近（重合度）的排后并带分数。

    - kind / stop / stage 是精确过滤；grep 对正文、备注、编号、来源做
      子串或正则匹配，未命中的再按字符三元组重合度（`content_overlaps`，
      阈值 threshold）给相近条目，重合度标进 `match` 字段——这就是
      "比较裁决"的只读出口（rules/decision.md「一个内容一条裁决」）。
    """
    rows = decision_rows(state)
    if kind:
        rows = [row for row in rows if row["kind"] == kind]
    if stop:
        rows = [row for row in rows if int(row["stop"] or 0) == int(stop)]
    if stage is not None:
        rows = [row for row in rows if int(row["stage"]) == int(stage)]
    if grep:
        for row in rows:
            if _text_match(grep, row["content"], row["note"], row["id"], row["source"]):
                row["match"] = "命中"
        exact = [row for row in rows if row.get("match")]
        near_ids = {row["id"] for row in exact}
        near = []
        for score, did, _body in content_overlaps(state, grep, threshold=threshold,
                                                  limit=None):
            if did in near_ids:
                continue
            hit = next((row for row in rows if row["id"] == did), None)
            if hit is not None:
                hit["match"] = "相近 %.0f%%" % (score * 100)
                near.append((score, hit))
        near.sort(key=lambda item: (-item[0], item[1]["id"]))
        rows = exact + [hit for _score, hit in near]
    if limit:
        rows = rows[:int(limit)]
    return rows


def decision_detail(state, did):
    """单条全档：行字段 + 修订历史 + 点选来源问题（证据即该裁决的那条）。"""
    did = str(did or "").strip()
    row = _find_decision(state, did)
    if row is None:
        raise EngineError("没有裁决 %s" % did)
    step = ""
    for key, rows_ in (state.get("decisions") or {}).items():
        if any(item["id"] == did for item in rows_ or []):
            step = str(key)
            break
    titles = _stage_titles()
    detail = {
        "id": row["id"],
        "kind": row.get("kind", ""),
        "stage": step,
        "stage_title": titles.get(step, step),
        "stop": row.get("stop"),
        "content": row.get("content", ""),
        "note": row.get("note", ""),
        "source": row.get("source", ""),
        "time": row.get("time", ""),
        "withdrawn": bool(row.get("withdrawn")),
        "withdrawn_at": row.get("withdrawn_at", ""),
        "history": [dict(old) for old in row.get("history") or []],
    }
    problem = next((item for item in state.get("problems") or []
                    if item.get("evidence") == did), None)
    if problem is not None:
        detail["closing_problem"] = {
            key: problem.get(key)
            for key in ("id", "kind", "stop", "text", "options", "source", "time")
        }
    return detail


def similar_decisions(state, content, threshold=0.25, limit=8):
    """给定正文与既有裁决的重合度排名：入库前判"是不是同一条"的比对出口。

    正文压掉标点后不足 6 个字符三元组时没法做重合度比对，直接报错并
    指向 `decision list --grep` 的子串查询。
    """
    if len(_content_grams(content or "")) < 6:
        raise EngineError(
            "比对正文太短：压掉标点后不足 6 个字符三元组，"
            "改用 decision %s list --grep 做子串查询" % state.get("sys_name"))
    by_id = {row["id"]: row for row in decision_rows(state)}
    rows = []
    for score, did, _body in content_overlaps(state, content, threshold=threshold,
                                              limit=None):
        row = by_id.get(did)
        if row is not None:
            item = dict(row)
            item["score"] = round(score, 3)
            rows.append(item)
        if len(rows) >= int(limit):
            break
    return rows


# ------------------------------------------------------------------ 问题 / 事项 / 事件


def query_problems(state, open_only=True, kind="", stop=None, grep="", limit=None):
    """问题清单过滤；缺省只看打开的问题，`open_only=False` 连已关闭一起给。"""
    rows = [dict(item) for item in state.get("problems") or []]
    if open_only:
        rows = [item for item in rows if item.get("open", True)]
    if kind:
        rows = [item for item in rows if item.get("kind") == kind]
    if stop:
        rows = [item for item in rows if int(item.get("stop") or 0) == int(stop)]
    if grep:
        rows = [item for item in rows
                if _text_match(grep, item.get("text"), item.get("id"), item.get("source"),
                               "|".join(item.get("options") or []))]
    if limit:
        rows = rows[:int(limit)]
    return rows


def items_view(state):
    """调试/综合优化事项（副本）。"""
    return [dict(item) for item in state.get("items") or []]


def load_events(root, name):
    """读 events.jsonl 为事件列表；子系统不存在报 FileNotFoundError。

    半截行（崩溃残留）跳过，不让日志查询被一条坏行卡死。
    """
    if not os.path.isfile(state_path(root, name)):
        raise FileNotFoundError("没有 %s，先执行 init" % name)
    events = []
    with open(os.path.join(sys_dir(root, name), EVENTS_FILE), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except (ValueError,):
                continue
    return events


def query_events(events, grep="", limit=None):
    """事件过滤：grep 匹配动作/对象/证据/命令/操作者；limit 取最后 N 条。"""
    rows = list(events)
    if grep:
        rows = [item for item in rows
                if _text_match(grep, item.get("action"), item.get("object"),
                               item.get("evidence"), item.get("cmd"), item.get("actor"))]
    if limit:
        rows = rows[-int(limit):]
    return rows


# ------------------------------------------------------------------ 文本渲染


def render_problem_line(item):
    """一条问题的人读行（与 `problem list` 历史格式一致）。"""
    extra = []
    if item.get("options"):
        extra.append("候选=%s" % "|".join(item["options"]))
    if item.get("blocks"):
        extra.append("阻塞=%s" % ",".join(str(b) for b in item["blocks"]))
    deferred = item.get("deferred") or {}
    if deferred:
        extra.append("推迟至=%s" % (deferred.get("until") or "—"))
    closed = "" if item.get("open", True) else \
        "（已关闭，证据 %s）" % (item.get("evidence") or "—")
    return "%s %s 停点%s %s%s%s" % (
        item["id"], item["kind"], item["stop"], item["text"],
        ("（%s）" % "；".join(extra)) if extra else "", closed)


def render_decision_list(rows, pending, deferred, show_problems=True,
                         show_decisions=True, filter_desc=""):
    """`decision list` 的文本视图：待裁决问题 + 分阶段裁决两张表。

    pending/deferred 恒给（历史格式里两段标题常在）；rows 为空时给占位行。
    """
    lines = []
    if show_problems:
        lines += ["## 待裁决问题", ""]
        if not pending:
            lines.append("（无待裁决问题）")
        else:
            lines.extend(_table(
                ["问题号", "停点", "问题原文", "候选"],
                [[item["id"], item.get("stop", ""), item.get("text", ""),
                  "|".join(item.get("options") or []) or "—"] for item in pending]))
        if deferred:
            lines += ["", "## 已推迟问题", ""]
            lines.extend(_table(
                ["问题号", "停点", "推迟至", "原因", "问题原文"],
                [[item["id"], item.get("stop", ""),
                  (item.get("deferred") or {}).get("until") or "—",
                  _plain((item.get("deferred") or {}).get("reason")),
                  item.get("text", "")] for item in deferred]))
    if show_decisions:
        lines += ["", "## 分阶段裁决", ""]
        if filter_desc:
            lines.append("过滤条件：%s" % filter_desc)
            lines.append("")
        if not rows:
            lines.append("（暂无裁决）")
        else:
            headers = ["阶段", "编号", "类别", "裁决内容", "来源/备注"]
            has_match = any("match" in row for row in rows)
            if has_match:
                headers.append("匹配")
            body = []
            for row in rows:
                extra = "已撤回" if row["withdrawn"] \
                    else (row.get("source") or row.get("note", ""))
                if row.get("revisions"):
                    tag = "已修订 %d 次" % row["revisions"]
                    extra = ("%s；%s" % (extra, tag)) if extra else tag
                cells = [row["stage_title"], row["id"], row["kind"],
                         row["content"], extra]
                if has_match:
                    cells.append(row.get("match", ""))
                body.append(cells)
            lines.extend(_table(headers, body))
    return "\n".join(lines)


def render_decision_detail(detail):
    """单条裁决全档：字段行 + 修订历史 + 关闭问题，多行正文压成单行。"""
    lines = [
        "%s（阶段 %s %s，停点 %s）" % (detail["id"], detail["stage"] or "—",
                                      detail["stage_title"] or "—",
                                      detail["stop"] if detail["stop"] is not None else "—"),
        "类别：%s" % (detail["kind"] or "—"),
        "入库：%s" % (detail["time"] or "—"),
        "来源：%s" % (detail["source"] or "（无）"),
        "状态：%s" % ("已撤回（%s）" % detail["withdrawn_at"] if detail["withdrawn"]
                      else "有效"),
        "正文：%s" % _plain(detail["content"]),
    ]
    if detail.get("note"):
        lines.append("备注：%s" % _plain(detail["note"]))
    for index, old in enumerate(detail.get("history") or [], 1):
        lines.append("修订历史[%d]（%s）：%s"
                     % (index, old.get("kind", "") or "—", _plain(old.get("content"))))
    problem = detail.get("closing_problem")
    if problem:
        lines.append("关闭问题：%s（%s，停点 %s）候选：%s"
                     % (problem.get("id"), problem.get("kind") or "—",
                        problem.get("stop", "—"),
                        "|".join(problem.get("options") or []) or "—"))
    return "\n".join(lines)


def render_similar(rows):
    """重合度比对结果：提醒"同一内容请用 override"，与入库守卫同一口径。"""
    lines = ["与给定正文相近的裁决（同一内容请用 override 在原编号下改写，不要开新号）：", ""]
    if not rows:
        lines.append("（无相近条目）")
    else:
        lines.extend(_table(
            ["编号", "重合", "类别", "阶段", "裁决内容"],
            [[row["id"], "%.0f%%" % (row["score"] * 100), row["kind"],
              row["stage_title"], row["content"]] for row in rows]))
    return "\n".join(lines)


def render_problems(rows):
    """`problem list` 文本视图：逐行，与历史格式一致。"""
    return "\n".join(render_problem_line(item) for item in rows) or "（无问题）"


def render_items(items):
    """`item list` 文本视图：逐行，与历史格式一致。"""
    lines = []
    for item in items:
        side = "，侧 %s" % item["side"] if item.get("side") else ""
        evidence = ("；证据：%s" % "、".join(item.get("evidence") or [])
                    if item.get("evidence") else "")
        lines.append("%s %s%s %s；当前做法：%s；第 %d 轮%s"
                     % (item["id"], item["kind"], side, item["text"],
                        item.get("approach") or "（未写）",
                        int(item.get("rounds") or 0), evidence))
    return "\n".join(lines)


def render_events(rows):
    """`events` 文本视图：一张表，序号、时间、命令、动作、对象、操作者、证据。"""
    if not rows:
        return "（无匹配事件）"
    return "\n".join(_table(
        ["序号", "时间", "命令", "动作", "对象", "操作者", "证据"],
        [[item.get("seq", ""), item.get("time", ""), item.get("cmd", ""),
          item.get("action", ""), item.get("object") or "—", item.get("actor", ""),
          item.get("evidence") or "—"] for item in rows]))


# ------------------------------------------------------------------ JSON 载荷


def decision_list_payload(state, rows, pending, deferred):
    """`decision list --json`：一份对象装下裁决与未关闭问题。"""
    return {
        "sys": state.get("sys_name"),
        "stages": _stage_titles(),
        "decisions": rows,
        "open_problems": pending,
        "deferred_problems": deferred,
    }


def problems_payload(state, rows):
    return {"sys": state.get("sys_name"), "problems": rows}


def items_payload(state, rows):
    return {"sys": state.get("sys_name"), "items": rows}


def events_payload(name, rows):
    return {"sys": name, "count": len(rows), "events": rows}


def similar_payload(state, content, rows):
    return {"sys": state.get("sys_name"), "query": content, "similar": rows}
