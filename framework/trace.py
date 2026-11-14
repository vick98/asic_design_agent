# 作者：vick 邮箱：ykun@yk9811.com

"""需求追溯矩阵：输入要点 → 节点 → 模块 → 测试要点 → 用例 → 最近全量回归。

追溯锚点是各表最后一列「来源」：节点表、模块清单/分组表写输入编号（A001…），
测试要点写上游模块名或输入编号。矩阵按输入要点逐行汇总，缺口说明写清断在哪一环。
最近结果只取最近一次全量回归（sys 场景、不带 --tc）记录里的逐用例结果；
记录里没有逐用例结果时标「未回归」，不拿整次 pass 冒充逐用例结论。
"""

import os
import re

INPUT_ID = re.compile(r"^([A-F])[-_]?(\d{3})$")
SECTION_NUM = re.compile(r"^§?\s*\d+\s*[\.、]?\s*")
TOKEN_SPLIT = re.compile(r"[\s、,，;；/|]+")
RESULT_KEYS = ("case_results", "per_case_results", "cases", "results")
STRONG = "强约束"
TIERS = ("强约束", "权威", "参考")


# ------------------------------------------------------------------ 表格解析


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells):
    return (bool(cells) and any("-" in cell for cell in cells)
            and all(set(cell) <= set("-: ") for cell in cells))


def _tables(body):
    """章节正文里的表：[(表头, [数据行…])]，表头取每张表第一行，分隔行丢掉。"""
    lines = body.split("\n")
    tables = []
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        block = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            block.append(lines[index])
            index += 1
        rows = [_cells(line) for line in block]
        rows = [row for row in rows if not _is_separator(row)]
        if not rows:
            continue
        tables.append((rows[0], rows[1:]))
    return tables


def _column(headers, *names):
    """表头里第一个包含任一名字的列号；找不到返回 -1。"""
    for position, head in enumerate(headers):
        for name in names:
            if name in head:
                return position
    return -1


def _cell(cells, position):
    return cells[position] if 0 <= position < len(cells) else ""


def _section(text, keyword):
    """取 `##` 标题含 keyword 的章节正文；没有返回空串。"""
    parts = re.split(r"(?m)^##\s+", text)
    for part in parts[1:]:
        lines = part.split("\n")
        title = SECTION_NUM.sub("", lines[0].strip())
        if keyword in title:
            return "\n".join(lines[1:])
    return ""


def _tokens(raw):
    """来源单元格 → 记号列表（输入编号归一成 A001 形式，去掉括号注记）。"""
    out = []
    for chunk in TOKEN_SPLIT.split(raw or ""):
        token = chunk.strip().strip("`*（）()[]【】 ")
        token = re.split(r"[（(]", token)[0].strip().strip("`* ")
        if not token or token in ("—", "-", "无", "（无）"):
            continue
        matched = INPUT_ID.match(token)
        if matched:
            token = matched.group(1) + matched.group(2)
        if token not in out:
            out.append(token)
    return out


def _canonical_id(token):
    matched = INPUT_ID.match((token or "").strip())
    return matched.group(1) + matched.group(2) if matched else ""


def _tier(raw):
    for tier in TIERS:
        if tier in (raw or ""):
            return tier
    return ""


def _sys_name(sys_root):
    return os.path.basename(os.path.abspath(sys_root).rstrip(os.sep))


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ------------------------------------------------------------------ 各层解析


def _assign_ids(raw_ids):
    """优先用显式编号（A001 形式）；缺失的按行序补稳定编号并避开已用号。"""
    used = set()
    explicit = []
    for raw in raw_ids:
        canonical = _canonical_id((raw or "").strip().strip("`"))
        if canonical:
            used.add(canonical)
        explicit.append(canonical)
    assigned = []
    counter = 1
    for canonical in explicit:
        if canonical:
            assigned.append(canonical)
            continue
        while "A%03d" % counter in used:
            counter += 1
        assigned.append("A%03d" % counter)
        used.add("A%03d" % counter)
        counter += 1
    return assigned


def _parse_input_points(sys_root):
    name = _sys_name(sys_root)
    rel = "info_input/%s_info_overview.md" % name
    path = os.path.join(sys_root, rel)
    notices = []
    if not os.path.isfile(path):
        return [], notices
    text = _read(path)
    body = _section(text, "输入文档") or text
    tables = _tables(body)
    if not tables:
        return [], ["输入文档章没有输入表，无法采集输入要点"]
    headers, rows = tables[0]
    for candidate in tables:
        if _column(candidate[0], "要点") >= 0:
            headers, rows = candidate
            break
    index_id = _column(headers, "编号")
    index_text = _column(headers, "要点")
    index_tier = _column(headers, "可信度")
    raw_ids = [_cell(row, index_id) if index_id >= 0 else "" for row in rows]
    ids = _assign_ids(raw_ids)
    points = []
    generated = 0
    for row, point_id, raw_id in zip(rows, ids, raw_ids):
        if not any(cell.strip() for cell in row):
            continue
        if not raw_id.strip() or not _canonical_id(raw_id.strip().strip("`")):
            generated += 1
        points.append({
            "id": point_id,
            "text": _cell(row, index_text),
            "credibility": _tier(_cell(row, index_tier)),
            "source_file": rel,
        })
    if generated:
        notices.append(
            "输入文档表有 %d 行没有 A001 形式的编号，已按行序生成 %s…；"
            "请在「编号」列写显式编号以便全流程引用"
            % (generated, ids[0] if ids else "A001"))
    return points, notices


def _parse_nodes(sys_root):
    name = _sys_name(sys_root)
    rel = "flow_doc/%s_flow.md" % name
    path = os.path.join(sys_root, rel)
    notices = []
    if not os.path.isfile(path):
        return [], notices
    body = _section(_read(path), "节点表")
    if not body:
        return [], notices
    nodes = []
    for headers, rows in _tables(body):
        index_node = _column(headers, "数据节点", "节点")
        if index_node < 0:
            continue
        index_steps = _column(headers, "对应步骤", "步骤")
        index_source = _column(headers, "来源")
        if index_source < 0:
            notices.append("节点表没有「来源」列，节点不参与向上追溯")
        for row in rows:
            node = _cell(row, index_node).strip().strip("`")
            if not node or node in ("数据节点", "节点"):
                continue
            nodes.append({
                "node": node,
                "steps": _cell(row, index_steps),
                "source": _tokens(_cell(row, index_source)),
            })
        break
    return nodes, notices


def _parse_modules(sys_root):
    name = _sys_name(sys_root)
    rel = "plan_doc/%s_plan.md" % name
    path = os.path.join(sys_root, rel)
    notices = []
    if not os.path.isfile(path):
        return [], notices
    text = _read(path)
    body = _section(text, "模块划分") or text
    modules = []
    by_name = {}
    for headers, rows in _tables(body):
        index_group = _column(headers, "大子模块名")
        index_module = _column(headers, "模块名")
        if index_group < 0 and index_module < 0:
            continue
        index_kind = _column(headers, "模块类型")
        index_source = _column(headers, "来源")
        if index_source < 0:
            notices.append("模块划分表没有「来源」列，模块不参与向上追溯")
        for row in rows:
            module = ""
            if index_module >= 0:
                module = _cell(row, index_module).strip().strip("`")
            if not module and index_group >= 0:
                module = _cell(row, index_group).strip().strip("`")
            if not module or module in ("—", "-", "模块名", "大子模块名"):
                continue
            record = by_name.get(module)
            if record is None:
                record = {"module": module, "kind": _cell(row, index_kind), "source": []}
                by_name[module] = record
                modules.append(record)
            # 分组表与模块清单各写一行时，来源列取并集（同一模块的追溯锚点不丢）。
            for token in _tokens(_cell(row, index_source)):
                if token not in record["source"]:
                    record["source"].append(token)
    return modules, notices


def _point_number(raw, fallback):
    matched = re.search(r"\d+", raw or "")
    return int(matched.group(0)) if matched else fallback


def _parse_test_points(sys_root):
    """spec_doc/<模块>_spec.md 的「测试要点」章：表格数据行或列表项都算一条。"""
    name = _sys_name(sys_root)
    spec_dir = os.path.join(sys_root, "spec_doc")
    notices = []
    points = []
    if not os.path.isdir(spec_dir):
        return points, notices
    for filename in sorted(os.listdir(spec_dir)):
        if not filename.endswith("_spec.md") or filename == name + "_spec.md":
            continue
        module = filename[:-len("_spec.md")]
        body = _section(_read(os.path.join(spec_dir, filename)), "测试要点")
        if not body:
            continue
        sequence = 0
        table_found = False
        for headers, rows in _tables(body):
            index_number = _column(headers, "编号")
            index_scene = _column(headers, "场景")
            if index_number < 0 and index_scene < 0:
                continue
            table_found = True
            index_source = _column(headers, "来源")
            if index_source < 0:
                notices.append("%s 的测试要点表没有「来源」列，测试要点不参与追溯"
                               % filename)
            for row in rows:
                if not any(cell.strip() for cell in row):
                    continue
                if _cell(row, 0).strip() in ("编号", "名字", "序号"):
                    continue
                sequence += 1
                points.append({
                    "module": module,
                    "number": _point_number(_cell(row, index_number), sequence),
                    "scene": _cell(row, index_scene),
                    "source": _tokens(_cell(row, index_source)),
                })
        if table_found:
            continue
        for line in body.splitlines():
            if not re.match(r"^\s*-\s+\S", line):
                continue
            sequence += 1
            scene = re.sub(r"^\s*-\s+", "", line).strip()
            matched = re.search(r"来源[:：]\s*([^。；;\n]+)", scene)
            points.append({
                "module": module,
                "number": sequence,
                "scene": scene,
                "source": _tokens(matched.group(1) if matched else ""),
            })
    return points, notices


def _parse_cases(sys_root):
    """(dut, 测试要点号) → 用例文件名；声明途径与 tc 闸门一致。

    用例名 `<dut>_tc_tp<N>.sv` 直接算覆盖第 N 条；手写用例在文件头注释里
    写 `testpoint: N` 也算。
    """
    base = os.path.join(sys_root, "testbench")
    mapping = {}
    if not os.path.isdir(base):
        return mapping
    platforms = []
    if os.path.isdir(os.path.join(base, "tc")):
        platforms.append(base)
    for entry in sorted(os.listdir(base)):
        folder = os.path.join(base, entry)
        if os.path.isdir(os.path.join(folder, "tc")):
            platforms.append(folder)
    for platform in platforms:
        tc_dir = os.path.join(platform, "tc")
        all_files = sorted(name for name in os.listdir(tc_dir)
                           if name.endswith("_tc_all.sv"))
        if not all_files:
            continue
        dut = all_files[0][:-len("_tc_all.sv")]
        for filename in sorted(os.listdir(tc_dir)):
            if not (filename.startswith(dut + "_tc_") and filename.endswith(".sv")):
                continue
            case = filename[len(dut) + len("_tc_"):-len(".sv")]
            if case in ("base", "all"):
                continue
            numbers = set()
            matched = re.fullmatch(r"tp(\d+)", case)
            if matched:
                numbers.add(int(matched.group(1)))
            path = os.path.join(tc_dir, filename)
            if os.path.isfile(path):
                numbers.update(int(num) for num in
                               re.findall(r"testpoint\s*[:=]\s*(\d+)", _read(path)))
            for number in numbers:
                names = mapping.setdefault((dut, number), [])
                case_name = filename[:-len(".sv")]
                if case_name not in names:
                    names.append(case_name)
    return mapping


# ------------------------------------------------------------------ 回归结果


def _latest_regression(state):
    for run in reversed((state or {}).get("runs") or []):
        if run.get("capability") != "sim":
            continue
        scope = run.get("scope") or {}
        if scope.get("scenario", "sys") != "sys" or scope.get("tc"):
            continue
        return run
    return None


def _normalize_result(value):
    text = str(value or "").strip().upper()
    if text in ("PASS", "PASSED", "OK", "SUCCESS"):
        return "PASS"
    if text in ("FAIL", "FAILED", "ERROR", "TIMEOUT"):
        return "FAIL"
    return text or "未回归"


def _per_case_results(run):
    """运行记录里的逐用例结果：checks 里优先，也接受记录顶层同名字段。"""
    if not isinstance(run, dict):
        return {}
    containers = [run.get("checks") or {}, run]
    for container in containers:
        for key in RESULT_KEYS:
            raw = container.get(key)
            if isinstance(raw, dict):
                return {str(case): _normalize_result(value) for case, value in raw.items()}
            if isinstance(raw, list):
                found = {}
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    case = item.get("case") or item.get("name") or item.get("case_name")
                    result = item.get("result") or item.get("status") or item.get("RESULT")
                    if case:
                        found[str(case)] = _normalize_result(result)
                if found:
                    return found
    return {}


# ------------------------------------------------------------------ 追溯解析


def _resolve(points, nodes, modules, test_points):
    """把每一层来源解析成"这条记录能追溯到哪些输入要点"。"""
    input_ids = {point["id"] for point in points}
    node_by = {node["node"]: node for node in nodes}
    module_by = {module["module"]: module for module in modules}

    def node_inputs(node, seen):
        if node in seen:
            return set()
        seen.add(node)
        record = node_by.get(node)
        if not record:
            return set()
        found = set()
        for token in record.get("source") or []:
            canonical = _canonical_id(token)
            if canonical in input_ids:
                found.add(canonical)
            elif token in node_by:
                found |= node_inputs(token, seen)
        return found

    def module_inputs(module, seen):
        if module in seen:
            return set()
        seen.add(module)
        record = module_by.get(module)
        if not record:
            return set()
        found = set()
        for token in record.get("source") or []:
            canonical = _canonical_id(token)
            if canonical in input_ids:
                found.add(canonical)
            elif token in module_by:
                found |= module_inputs(token, seen)
            elif token in node_by:
                found |= node_inputs(token, set())
        return found

    def point_inputs(point):
        found = set()
        for token in point.get("source") or []:
            canonical = _canonical_id(token)
            if canonical in input_ids:
                found.add(canonical)
            elif token in module_by:
                found |= module_inputs(token, set())
            elif token in node_by:
                found |= node_inputs(token, set())
        return found

    node_links = {node["node"]: node_inputs(node["node"], set()) for node in nodes}
    module_links = {module["module"]: module_inputs(module["module"], set())
                    for module in modules}
    point_links = {id(point): point_inputs(point) for point in test_points}
    return node_links, module_links, point_links


def trace_matrix(sys_root, state=None):
    """需求追溯矩阵：返回行、统计、未覆盖清单与提示（Markdown 由 render_markdown 出）。

    state 缺省时从 sys_root 的父目录按子系统名加载。
    """
    name = _sys_name(sys_root)
    if state is None:
        from framework.state import load_state
        state = load_state(os.path.dirname(os.path.abspath(sys_root)), name)
    points, input_notices = _parse_input_points(sys_root)
    nodes, node_notices = _parse_nodes(sys_root)
    modules, module_notices = _parse_modules(sys_root)
    test_points, point_notices = _parse_test_points(sys_root)
    cases = _parse_cases(sys_root)
    notices = input_notices + node_notices + module_notices + point_notices
    node_links, module_links, point_links = _resolve(
        points, nodes, modules, test_points)
    regression = _latest_regression(state)
    case_results = _per_case_results(regression)

    rows = []
    for point in points:
        linked_nodes = [node["node"] for node in nodes
                        if point["id"] in node_links.get(node["node"], set())]
        linked_modules = [module["module"] for module in modules
                          if point["id"] in module_links.get(module["module"], set())]
        linked_points = [item for item in test_points
                         if point["id"] in point_links.get(id(item), set())]
        row_cases = []
        for item in linked_points:
            for case in cases.get((item["module"], item["number"]), []):
                if case not in row_cases:
                    row_cases.append(case)
        if not row_cases:
            result = "未回归"
        else:
            values = []
            for case in row_cases:
                value = case_results.get(case, "未回归")
                if value not in values:
                    values.append(value)
            result = "/".join(values)
        gaps = []
        if not linked_nodes:
            gaps.append("节点表没有该输入要点")
        if not linked_modules:
            gaps.append("模块划分没有该输入要点")
        if not linked_points:
            gaps.append("无测试要点追溯")
        for item in linked_points:
            if not cases.get((item["module"], item["number"])):
                gaps.append("测试要点 %s#%d 无对应用例"
                            % (item["module"], item["number"]))
        if row_cases and result == "未回归":
            gaps.append("最近全量回归没有逐用例结果")
        rows.append({
            "input": point["id"],
            "input_text": point["text"],
            "credibility": point["credibility"],
            "strong": point["credibility"] == STRONG,
            "nodes": linked_nodes,
            "modules": linked_modules,
            "test_points": [
                {"module": item["module"], "number": item["number"],
                 "scene": item["scene"]} for item in linked_points],
            "cases": row_cases,
            "result": result,
            "run": (regression or {}).get("id") or "",
            "gap": "；".join(gaps),
        })

    input_count = len(rows)
    traced = [row for row in rows if row["test_points"]]
    uncovered = [row for row in rows if not row["test_points"]]
    strong_rows = [row for row in rows if row["strong"]]
    strong_uncovered = [row for row in uncovered if row["strong"]]
    all_cases = sorted({case for names in cases.values() for case in names})
    summary = {
        "input_points": input_count,
        "traced_points": len(traced),
        "uncovered_points": len(uncovered),
        "strong_input_points": len(strong_rows),
        "strong_uncovered": len(strong_uncovered),
        "test_points": len(test_points),
        "cases": len(all_cases),
        "coverage": "%d/%d" % (len(traced), input_count),
        "coverage_percent": int(round(100.0 * len(traced) / input_count)) if input_count else 0,
    }
    return {
        "sys": name,
        "rows": rows,
        "summary": summary,
        "uncovered": [
            {"input": row["input"], "credibility": row["credibility"],
             "strong": row["strong"], "text": row["input_text"]}
            for row in uncovered],
        "notices": notices,
        "regression": (
            {"id": regression.get("id") or "", "status": regression.get("status") or "",
             "time": regression.get("time") or ""} if regression else None),
        "sources": {
            "info_overview": "info_input/%s_info_overview.md" % name,
            "flow": "flow_doc/%s_flow.md" % name,
            "plan": "plan_doc/%s_plan.md" % name,
            "spec_doc": sorted(filename for filename in os.listdir(
                os.path.join(sys_root, "spec_doc"))
                if filename.endswith("_spec.md") and filename != name + "_spec.md")
            if os.path.isdir(os.path.join(sys_root, "spec_doc")) else [],
        },
    }


# ------------------------------------------------------------------ Markdown


class TraceMatrix:
    """追溯矩阵对象：`as_dict()` 给 JSON 结构，`markdown()` 给 Markdown 矩阵。"""

    def __init__(self, sys_root, state=None):
        self._data = trace_matrix(sys_root, state)

    def as_dict(self):
        return self._data

    def markdown(self):
        return render_markdown(self._data)


def _md_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_markdown(result):
    """矩阵的 Markdown 版：每条输入要点一行，缺口说明写断点。"""
    lines = ["# %s 需求追溯矩阵" % result["sys"], ""]
    lines.append(
        "矩阵口径：每条输入要点一行；节点/模块/测试要点按各自「来源」列逐级追溯，"
        "用例取 `<dut>_tc_tp<N>.sv` 或文件头 `testpoint: N`，最近结果取最近一次"
        "全量回归（sys 场景、不带 --tc）里的逐用例结果。")
    lines.append("")
    lines.append("| 输入要点 | 节点 | 模块 | 测试要点 | 用例 | 最近结果 | 缺口说明 |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in result["rows"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            _md_cell("%s %s" % (row["input"], row["input_text"])),
            _md_cell("、".join(row["nodes"]) or "—"),
            _md_cell("、".join(row["modules"]) or "—"),
            _md_cell("、".join("%s#%d" % (item["module"], item["number"])
                              for item in row["test_points"]) or "—"),
            _md_cell("、".join(row["cases"]) or "—"),
            _md_cell(row["result"]),
            _md_cell(row["gap"] or "—"),
        ))
    summary = result["summary"]
    lines.append("")
    lines.append("统计：输入要点 %d 条，已追溯到测试要点 %d 条，覆盖率 %d%%（%s）。"
                 % (summary["input_points"], summary["traced_points"],
                    summary["coverage_percent"], summary["coverage"]))
    regression = result.get("regression")
    if regression:
        lines.append("最近全量回归：%s（%s，%s）" % (
            regression["id"] or "—", regression["status"] or "—", regression["time"] or "—"))
    else:
        lines.append("最近全量回归：（无）")
    if result["uncovered"]:
        lines.append("未覆盖：" + "、".join(
            "%s（%s）" % (item["input"], item["credibility"] or "未定级")
            for item in result["uncovered"]))
    else:
        lines.append("未覆盖：无")
    for notice in result.get("notices") or []:
        lines.append("提示：%s" % notice)
    return "\n".join(lines) + "\n"
