# 作者：vick 邮箱：ykun@yk9811.com

"""独立审查记录与审查报告解析计数。"""

import hashlib, os, re
from framework.flow import (
    load as load,
    product_path as product_path,
    stop_review as flow_stop_review,
)
from framework.state import record_event, state_txn, stop_row, sys_dir
from framework.engine.runtime import current_time as now
from framework.engine.runs import (
    run_inputs_digest,
)
from framework.engine.runtime import (
    EngineError,
    _check_stop_id,
    _product_digest,
    _require_action,
    _top_product_digest,
    module_digest,
)


def _newest_mtime(path):
    """路径（文件或目录）下最后一次修改的时间；不存在返回 0。"""
    if os.path.isfile(path):
        return os.path.getmtime(path)
    if not os.path.isdir(path):
        return 0.0
    newest = 0.0
    for dirpath, dirnames, files in os.walk(path):
        dirnames[:] = [item for item in dirnames if item != "__pycache__"]
        for fn in files:
            newest = max(newest, os.path.getmtime(os.path.join(dirpath, fn)))
    return newest


def _review_product(base, sid, module):
    """审查记录要对照的产物路径（报告必须晚于它的最后一次修改）。"""
    stop_obj = load()["by_id"][sid]
    if flow_stop_review(sid) == "rtl_review_per_module" and module:
        for suffix in (".sv", ".v"):
            path = os.path.join(base, "rtl", module + suffix)
            if os.path.isfile(path):
                return path
        return os.path.join(base, "rtl", module + ".sv")
    return os.path.join(base, product_path(stop_obj, os.path.basename(base)))


REVIEW_COLUMNS = ("发现编号", "级别", "位置", "建议", "处置")


_ACCEPT_RISK_RE = re.compile(r"^接受风险\s*[（(]\s*([A-Za-z]+\d*-\d+)\s*[）)]")


def _table_cells(line):
    """Markdown 表格行 → 单元格列表；不是表格行返回 None。"""
    text = line.strip()
    if not (text.startswith("|") and text.endswith("|")):
        return None
    return [cell.strip() for cell in text.strip("|").split("|")]


def _parse_review_report(text):
    """解析审查报告第一张发现表，返回 {findings, blocking, accept_risks, unresolved}。

    表的列名必须原样为"发现编号 / 级别 / 位置 / 建议 / 处置"；找不到这张表时
    正文必须写明"无发现"，否则拒收。findings 取数据行数；blocking 取级别为
    "阻断"且处置既不是"已改…"也不是"接受风险（D号）"的行数。
    """
    lines = text.splitlines()
    header_at = None
    for index, line in enumerate(lines):
        if _table_cells(line) == list(REVIEW_COLUMNS):
            header_at = index
            break
    if header_at is None:
        if not any("无发现" in line for line in lines):
            raise EngineError(
                "审查报告没有发现表（应为五列：%s），也没有写明“无发现”；"
                "无发现也要明确写出来" % " / ".join(REVIEW_COLUMNS))
        return {"findings": 0, "blocking": 0, "accept_risks": [], "unresolved": []}
    findings = 0
    blocking = 0
    accept_risks = []
    unresolved = []
    for line in lines[header_at + 1:]:
        cells = _table_cells(line)
        if cells is None:
            if line.strip():
                break
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        if len(cells) != len(REVIEW_COLUMNS):
            raise EngineError("审查报告发现表的数据行不是 %d 列：%s"
                              % (len(REVIEW_COLUMNS), line.strip()[:80]))
        findings += 1
        level = cells[1]
        action = cells[4]
        risk = _ACCEPT_RISK_RE.match(action)
        if risk:
            accept_risks.append(risk.group(1))
            continue
        if action.startswith("接受风险"):
            raise EngineError(
                "审查报告“处置”写接受风险时必须引用裁决号（形如 接受风险（D1-001））：%s"
                % action[:40])
        if level == "阻断" and not action.startswith("已改"):
            blocking += 1
            unresolved.append("%s（%s）" % (cells[0], action[:40]))
    return {"findings": findings, "blocking": blocking,
            "accept_risks": accept_risks, "unresolved": unresolved}


def _review_report(base, report, product):
    """审查报告校验——必填、在 report/ 下、存在、晚于产物最后一次修改，并按发现表计数。

    返回 (相对路径, 内容摘要, 解析结果)：审阅包按记录取报告原文；
    发现数与阻断数以报告第一张五列表为准，不接受自报数字。
    """
    rel = str(report or "").strip()
    if not rel:
        raise EngineError(
            "审查记录必须带 --report report/<文件>.md：审阅包按记录取报告原文（发现与处置）")
    if not rel.startswith("report/"):
        raise EngineError("审查报告要放在 report/ 下（--report report/<文件>.md），收到 %s" % rel)
    path = os.path.join(base, rel)
    if not os.path.isfile(path):
        raise EngineError("审查报告不存在：%s" % rel)
    if product and os.path.exists(product):
        if os.path.getmtime(path) < _newest_mtime(product):
            raise EngineError(
                "审查报告 %s 早于产物 %s 的最后一次修改：报告必须是这一版产物审出来的"
                % (rel, os.path.relpath(product, base)))
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    parsed = _parse_review_report(text)
    return rel, hashlib.sha256(raw).hexdigest()[:12], parsed


def review_record(root, name, stop, module="", author="", reviewer="", findings=None,
                  blocking=None, report=""):
    """审查记录去人工化：不要终端、不要令牌；作者与审查者必须不同（两者都是
    派工号，由主持者登记，框架只能校验不同，身份靠事件日志与里程碑抽查兜底）。

    发现数与阻断数**以报告里的发现表为准**：`report/<文件>.md` 的第一张五列表
    （发现编号/级别/位置/建议/处置）的数据行数即 findings；级别"阻断"且处置不是
    "已改…"也不是"接受风险（D号）"的行数即 blocking，必须为 0。`--findings`/
    `--blocking` 可选，给了就与解析结果比对，不一致直接拒。无发现表的报告正文必须
    写明"无发现"。审查要求与绑定口径读 flow_model.yaml 的 `review:` 字段
    （flow.stop_review，唯一事实源），不按停点号写死：

    - spec_review：spec_review 记录绑停点产物指纹（_product_digest），记在停点行 reviews；
    - tb_review：TB 构建的停点级审查，口径与 spec_review 相同，只换 kind；
    - rtl_review_per_module：rtl_review 绑该模块摘要（module_digest，含 include 链），记在模块条目；
    - rtl_review：rtl_review 绑顶层产物指纹，记在模块条目（模块名缺省 `<sys>_top`）；
    - none：不登记审查记录（审查就是闸门与运行记录本身）。

    `--report` **必填**——审查报告必须存在且晚于产物最后一次修改；记录里挂报告
    路径与内容摘要，审阅包按记录取原文。

    作者≠审查者、阻断发现为 0 两条前提由动作表 review_record 的 requires 执行；
    本函数保留报告解析与 --findings/--blocking 的一致性比对（解析口径）。
    """
    sid = _check_stop_id(stop, "审查记录的停点号")
    kind = flow_stop_review(sid)
    if kind == "none":
        raise EngineError(
            "行 %d 的 review 要求是 none：以闸门与运行记录为审查依据，不需要 review record" % sid)
    author = str(author or "").strip()
    reviewer = str(reviewer or "").strip()
    base = sys_dir(root, name)
    module = str(module or "").strip()
    report_rel, report_digest, parsed = _review_report(
        base, report, _review_product(base, sid, module))
    # 动作表 review_record 的前提：作者≠审查者、阻断发现为 0。发现数与阻断数以报告
    # 解析结果为准（--findings/--blocking 只在下面做一致性比对，不参与判定）。
    _require_action("review_record", {
        "author": author, "reviewer": reviewer,
        "findings_count": parsed["findings"], "blocking": parsed["blocking"],
    })
    if findings is not None:
        given = int(findings)
        if given < 0:
            raise EngineError("发现数不能为负（--findings）")
        if given != parsed["findings"]:
            raise EngineError(
                "--findings %d 与报告发现表解析出的 %d 条不一致：框架按报告表计数，"
                "删掉 --findings 或改成解析值" % (given, parsed["findings"]))
    if blocking is not None:
        given = int(blocking)
        if given != parsed["blocking"]:
            raise EngineError(
                "--blocking %d 与报告发现表解析出的 %d 条阻断不一致：框架按报告表计数，"
                "删掉 --blocking 或改成解析值" % (given, parsed["blocking"]))
    findings = parsed["findings"]
    with state_txn(root, name, cmd="review_record") as state:
        # "接受风险（D号）"引用的裁决必须有效：读动作表 problem_close_tradeoff 的
        # class:redline 统一规则（人的来源必须是已入库、未撤回的方向/数值类裁决）。
        for did in parsed["accept_risks"]:
            _require_action("problem_close_tradeoff", {"state": state, "decision": did})
        stop_obj = load()["by_id"][sid]
        if kind in ("spec_review", "tb_review"):
            # tb_review 复用 spec_review 的停点级口径——作者≠审查者、阻断发现为 0、
            # 必带 --report、记录绑停点产物指纹；只换 kind 与展示文案，不另造一套语义。
            stop_row(state, sid).setdefault("reviews", []).append({
                "kind": kind, "author": author, "reviewer": reviewer,
                "findings": findings, "digest": _product_digest(root, name, stop_obj),
                "report": report_rel, "report_digest": report_digest,
                "time": now(),
            })
            record_event(state, "审查记录", obj="停点 %d" % sid,
                         evidence="%s 作者 %s 审查者 %s 发现 %d；报告 %s"
                                  % (kind, author, reviewer, findings, report_rel))
            return "停点 %d 审查记录已登记（%s，报告 %s）" % (sid, kind, report_rel)
        row_id = str(sid)
        if kind == "rtl_review_per_module":
            if not module:
                raise EngineError("行 %d 的审查记录要写明模块（--module）" % sid)
            if not _lint_ok(state, module, base):
                raise EngineError("%s 没有针对当前文件的通过 lint 记录，审查通过之前先跑 run lint" % module)
            digest = module_digest(base, module)
        else:
            module = module or (name + "_top")
            digest = _product_digest(root, name, stop_obj)
        # 只写证据（kind/digest/author/...），状态由 module_state 推导；新审查记录
        # 同时清掉该模块的显式"退回"覆盖——重新审查 = 退回指令已执行完。
        items = state["modules"].setdefault(row_id, [])
        if not any(item.get("name") == module for item in items):
            items.append({"name": module})
        for item in items:
            if item["name"] == module:
                item.pop("state", None)
                item["kind"] = "rtl_review"
                item["author"] = author
                item["reviewer"] = reviewer
                item["findings"] = findings
                item["digest"] = digest
                item["report"] = report_rel
                item["report_digest"] = report_digest
                item["time"] = now()
        record_event(state, "审查记录", obj=module,
                     evidence="rtl_review 行 %s 作者 %s 审查者 %s 发现 %d；报告 %s"
                              % (row_id, author, reviewer, findings, report_rel))
    return "%s 审查通过（rtl_review，行 %s，报告 %s）" % (module, row_id, report_rel)


def _review_record_ok(root, name, state, sid):
    """审查记录判据。返回 (ok, 原因, 引用描述)。

    审查要求读 flow_model.yaml 的 `review:` 字段（flow.stop_review，唯一事实源），
    不按停点号写死：
      spec_review            停点级 spec_review，绑停点产物指纹；
      tb_review              停点级 tb_review，绑停点产物指纹；
      rtl_review_per_module  逐模块 rtl_review，绑模块摘要；
      rtl_review             顶层 rtl_review，绑停点产物指纹；
      none                   不另要求审查记录（审查就是闸门与运行记录本身）。
    """
    sid = int(sid)
    stop = load()["by_id"].get(sid)
    kind = flow_stop_review(sid)
    if kind == "none":
        return True, "", ""
    if kind in ("spec_review", "tb_review"):
        digest = _product_digest(root, name, stop)
        for rev in stop_row(state, sid).get("reviews") or []:
            if rev.get("kind") == kind and rev.get("digest") == digest:
                return True, "", "%s 停点 %d（指纹 %s）" % (kind, sid, digest)
        return False, ("缺对应当前产物指纹的 %s 审查记录："
                       "python3 script/framework.py review %s record --stop %d "
                       "--author <派工号> --reviewer <派工号> "
                       "--report report/<文件>.md" % (kind, name, sid)), ""
    base = sys_dir(root, name)
    if kind == "rtl_review_per_module":
        from framework.gates.run import _rtl_names
        names = _rtl_names(base)
        if not names:
            return False, "行 %d 没有可审查的模块（rtl/ 下没有非顶层 HDL 文件）" % sid, ""
        missing = [mod for mod in names if not _module_review_current(state, sid, mod, base)]
        if missing:
            return False, ("以下模块缺对应当前文件的 rtl_review 审查记录：%s"
                           % "、".join(missing)), ""
        return True, "", "rtl_review 行 %d（%d 个模块，绑模块摘要）" % (sid, len(names))
    digest = _product_digest(root, name, stop)
    for item in state["modules"].get(str(sid), []) or []:
        if (item.get("kind") == "rtl_review" and item.get("digest") == digest):
            return True, "", "rtl_review 行 %d（指纹 %s）" % (sid, digest)
    return False, ("行 %d 缺对应当前顶层产物指纹的 rtl_review 审查记录："
                   "python3 script/framework.py review %s record --stop %d "
                   "--author <派工号> --reviewer <派工号> --report report/<文件>.md"
                   % (sid, name, sid)), ""


def _module_review_current(state, row, mod, base):
    """模块条目上有对当前文件有效的 rtl_review 审查记录（状态不再落库，只比摘要）。"""
    for item in state["modules"].get(str(row), []) or []:
        if (item.get("name") == mod and item.get("kind") == "rtl_review"
                and item.get("digest") == module_digest(base, mod)):
            return True
    return False


def _lint_ok(state, module, base):
    """行 7 的 lint 通过来自逐模块的运行记录，且记录对应当前文件。"""
    for run in reversed(state.get("runs") or []):
        if run.get("capability") != "lint":
            continue
        scope = run.get("scope") or {}
        modules = scope.get("modules") or (run.get("checks") or {}).get("modules") or []
        if module not in modules:
            continue
        if run.get("status") != "pass":
            return False
        digests = scope.get("module_digests") or {}
        if module in digests:
            return digests[module] == module_digest(base, module)
        root, name = os.path.split(base.rstrip(os.sep))
        return run.get("inputs_digest") == run_inputs_digest(root, name, run)
    return False


def review_current(item, base):
    """审查通过只对审查时的那一版文件有效（状态由证据推导，这里只比摘要）。"""
    return item.get("kind") == "rtl_review" and item.get("digest") == module_digest(base, item.get("name", ""))


def module_stale_note(state, base, row, mod):
    """模块证据是否仍对当前文件有效；失效返回说明，供状态文档与 status 使用。

    只标注，不改判定——闸门仍按 `_lint_ok`/`review_current` 的口径否决。状态由
    `module_state` 推导，这里的"失效"指：曾经有 lint/审查证据，但对不上当前文件。
    """
    if str(row) != "7":
        return ""
    name = mod.get("name", "")
    if mod.get("kind") == "rtl_review":
        return "" if review_current(mod, base) else "文件已改，需重审"
    if _lint_ok(state, name, base):
        return ""
    return "文件已改，需重跑 lint" if mod.get("digest") or mod.get("kind") else ""


def stale_module_count(state, base):
    """行 7 里已失效的 lint/审查证据条数。"""
    return sum(1 for mod in state["modules"].get("7", [])
               if module_stale_note(state, base, "7", mod))


def _module_entry(state, row, mod):
    """取模块条目（证据记录：rtl_review 的 digest/author/... 或显式"退回"覆盖）。"""
    for item in state.get("modules", {}).get(str(row), []) or []:
        if item.get("name") == mod:
            return item
    return None


def _module_override(state, row, mod):
    """显式 `module --state 退回` 的覆盖值（没有则 ""）。"""
    entry = _module_entry(state, row, mod)
    return str((entry or {}).get("state") or "")


def module_state(state, base, row, mod):
    """模块状态由文件与证据推导（取消手工登记）。

    - 显式"退回"覆盖优先（`module --state 退回`），直到该模块重新登记审查记录；
    - 行 7：rtl_review 记录对得上当前文件 → "审查通过"；有对当前文件的 lint 通过记录 →
      "lint 通过"；模块文件在 → "已生成"；
    - 行 8：顶层文件的 rtl_review 记录对得上当前产物指纹 → "连接通过"；否则"已生成"；
    - 行 9：平台状态由用例核对推导（gates.tc.platform_state）。
    返回 "未开始" 表示该模块/平台还没有任何证据。
    """
    row = str(row)
    override = _module_override(state, row, mod)
    if override == "退回":
        return "退回"
    if row == "7":
        entry = _module_entry(state, row, mod)
        if (entry and entry.get("kind") == "rtl_review"
                and entry.get("digest") == module_digest(base, mod)):
            return "审查通过"
        if _lint_ok(state, mod, base):
            return "lint 通过"
        return "已生成"
    if row == "8":
        entry = _module_entry(state, row, mod)
        digest = _top_product_digest(base)
        if entry and entry.get("kind") == "rtl_review" and digest and entry.get("digest") == digest:
            return "连接通过"
        return "已生成"
    if row == "9":
        from framework.gates.tc import platform_state
        return platform_state(base, mod)
    return "未开始"


def _clear_module_override(state, row):
    """清掉该行所有模块的显式"退回"覆盖：该行重新过闸门 = 退回指令已执行完。"""
    for item in state.get("modules", {}).get(str(row), []) or []:
        if item.get("state") == "退回":
            item.pop("state", None)
