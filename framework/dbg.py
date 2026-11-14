# 作者：vick 邮箱：ykun@yk9811.com

"""`dbg` —— EDA MCP 观察面统一封装。

任何宿主都能用：经 SSH 调用远端 `<prefix>/bin/eda-mcp` CLI，并负责
**路径换算**（子系统相对路径 → 镜像绝对路径）、**镜像新鲜度检查**与
**导出文件落地**（`<sys>/work/dbg/`）。

边界（写在本文件里并测试守住）：
- **观察面全开，作业面不开**：只调用 eda-mcp 的观察组子命令
  （info/signals/scopes/query/wave/wave_extract/doctor/npi），绝不拼装
  作业组（sim/lint/syn/sta/job）子命令；入账运行仍只经 `framework.py run`。
- **观察面不写框架状态**：本模块不写 `state.json`，只读运行记录；
  导出文件落 `<sys>/work/dbg/`，由人工/后续命令用
  `item <sys> set --id <M号> --text "<当前做法>" --evidence <路径>` 挂事项。
- **镜像新鲜度**：读波形时找到产生它的运行记录，比对输入摘要与本地当前
  摘要，不一致时输出**第一行**提示"波形来自 R0xx，之后 RTL/TB 已改动"，不阻断。
  运行记录的 `waves` 字段由后续包补，缺失时容错（按最近同场景运行推断）。
- **NPI 复用**：`design_id = <sys>@<RTL 摘要前 8 位>`；查询前核对摘要，
  不一致先重新打开；打开新设计时关闭同一子系统旧的 design_id（daemon 上限
  `max_design_daemons` 默认 2，超出时先关其它子系统最旧的）。

公开 API（CLI 按它接线）：

    run_dbg(root, name, argv, run=None) -> (输出文本, 退出码)
        name 为子系统名，或 "doctor"（配 `dbg doctor`）；
        argv 为 `dbg <name>` 之后的参数；
        run 可注入 subprocess.run 桩（FakeProc 做法）。
    design_id(root, name) -> "<sys>@<RTL 摘要前 8 位>"
    node_names(root, name) -> 行 2 节点表里的节点名（flow_doc/<sys>_flow.md）
"""

import argparse
import json
import os
import re
import shlex

from framework import eda_mcp, eda_mcp_deploy
from framework.engine import _pub_code_used, inputs_digest, run_inputs_digest
from framework.paths import project_root

# tb_define.svh 里 TB_DUMP_TAG 的缺省值（TB_DUMP_TAG=… 变体可在命令行 --tag 覆盖）。
DEFAULT_TAG = "wave"

STALE_NOTE = "波形来自 %s，之后 RTL/TB 已改动（不阻断）"

# eda-mcp daemon.py 的 max_design_daemons 默认值。
MAX_DESIGN_DAEMONS = 2

# dbg 允许的远端 CLI 子命令（全部是观察组；作业组一律不出现）。
OBSERVE_SUBCOMMANDS = ("info", "signals", "scopes", "query", "wave",
                       "wave_extract", "windows", "diff", "trace", "active",
                       "fsm", "doctor", "npi")

# 查询默认值（ctx）对哪些 dbg 子命令生效、继承哪些字段。
# case/signals/clock/valid/start/end 之外的字段不进 ctx（tag/module 随 set 显式给）。
_CTX_WANTED = {
    "signals": ("case",),
    "wave": ("case", "signals", "clock", "start", "end"),
    "value": ("case", "signal"),
    "extract": ("case", "clock", "valid", "start", "end"),
    "windows": ("case", "start", "end"),
    "diff": ("signals", "clock", "start", "end"),
    "trace": ("case", "clock"),
    "active": ("case", "clock"),
    "fsm": ("case", "clock", "start", "end"),
}


class DbgError(Exception):
    """面向用户的 dbg 错误（退出码 2）。"""


# ------------------------------------------------------------------ 公共小件


def _last(text):
    detail = [line for line in (text or "").strip().splitlines() if line.strip()]
    return detail[-1] if detail else "无输出"


def _profile():
    from framework.profile_run import load_profile
    return load_profile()


def _load_state(root, name):
    """只读运行记录；没有台账（还没 init_sys）时按空处理，不崩。"""
    try:
        from framework.state import load_state
        return load_state(root, name)
    except FileNotFoundError as exc:
        del exc
        return {"runs": []}


def _scenario(opts):
    return "module" if getattr(opts, "module", "") else "sys"


def _fsdb_path(profile, name, opts):
    return eda_mcp.fsdb_remote_path(profile, _scenario(opts), name,
                                    getattr(opts, "module", "") or "",
                                    int(opts.case), getattr(opts, "tag", DEFAULT_TAG))


def _freshness(root, name, run):
    """返回 (第一行提示或"", 摘要标记)。运行记录缺失时返回 ("", "无运行记录")。"""
    if not run:
        return "", "无运行记录"
    try:
        current = run_inputs_digest(root, name, run)
    except OSError as exc:
        del exc  # 输入文件被删/读不了：按已改动处理
        current = None
    if current != run.get("inputs_digest"):
        return STALE_NOTE % (run.get("id") or "?"), "输入已变更"
    return "", "输入摘要一致"


def _sim_run_for_wave(state_runs, scenario, module, remote_path):
    """找到产生该波形的运行记录。优先用记录自己的 `waves` 字段（后续包补），
    缺失时退到最近一次同场景同模块的 sim 运行（推断，容错不崩）。"""
    runs = state_runs or []
    for run in reversed(runs):
        if run.get("capability") == "sim" and remote_path in (run.get("waves") or []):
            return run
    for run in reversed(runs):
        if run.get("capability") != "sim":
            continue
        scope = run.get("scope") or {}
        if ((scope.get("scenario") or "sys") == scenario
                and (scope.get("module") or "") == module):
            return run
    return None


def _json_part(text):
    """远端 CLI 的输出里截出 JSON（cmd_wave 会在 JSON 前打印过程信息行）。"""
    text = text or ""
    start = text.find("{")
    if start < 0:
        raise DbgError("远端没有返回 JSON，输出开头：%s" % (text.strip().splitlines() or ["（空）"])[0])
    return text[start:]


def _safe_name(text):
    cleaned = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in str(text or ""))
    return cleaned[:60] or "x"


def _label(signals):
    return _safe_name("_".join(str(s).split(".")[-1] for s in signals))


def _with_stale(stale, body):
    return ("\n".join([stale] + ([body] if body else [])) if stale
            else body).strip("\n")


def _wave_record(root, name, opts, fsdb):
    """波形所属运行记录 + 新鲜度（多命令共用）。"""
    state = _load_state(root, name)
    rec = _sim_run_for_wave(state.get("runs"), _scenario(opts),
                            getattr(opts, "module", "") or "", fsdb)
    stale, mark = _freshness(root, name, rec)
    return rec, stale, mark


# ------------------------------------------------------------------ 调用级 _fp（数据集指纹）
#
# 每次查询的输出都带一个 fp：这答案是**从哪份数据算出来的**（波形、运行记录、
# 输入摘要一致性、远端文件 mtime/size）+ **实际生效的参数**（含 ctx 继承项）。
# 防"证据串源"：agent 把不同波形的答案拼进同一条推理链时，fp 一比即知不同源。

def _remote_stat(profile, run, remote_path):
    """远端波文件指纹（mtime/size）；拿不到就缺省（不阻断）。"""
    proc = eda_mcp.run_ssh(profile, "stat -c '%%Y %%s' %s 2>/dev/null || true"
                           % shlex.quote(remote_path), run=run)
    parts = (proc.stdout or "").split()
    if len(parts) >= 2:
        try:
            return {"mtime": int(parts[0]), "size": int(parts[1])}
        except ValueError as _exc:
            return {}
    return {}


def _fp_of(tool, fsdb, rec, mark, inherited=(), stat=None):
    fp = {
        "tool": "dbg " + tool,
        "wave": fsdb,
        "run": (rec or {}).get("id"),
        "freshness": mark,
        "from_ctx": list(inherited or ()),
    }
    if stat:
        fp["fsdb"] = stat
    return fp


def _fp_line(fp):
    return "fp: " + json.dumps(fp, ensure_ascii=False, sort_keys=True)


# ------------------------------------------------------------------ 查询默认值（ctx）
#
# 一套调试会话里的多个调用共享同一口径（case/信号/时钟/时间窗），省得每步
# 重抄参数——抄错一次，前后结论就错位。显式参数永远优先；用了默认值在输出里
# 声明（from_ctx）；--ctx-rev 钉住版本，被改动即报 ctx_conflict 而不是
# 悄悄换口径。ctx 落 <sys>/work/dbg/ctx.json（工具产物，不进 git）。

_CTX_REL = ("work", "dbg", "ctx.json")


def _ctx_path(root, name):
    return os.path.join(root, name, *_CTX_REL)


def _ctx_load(root, name):
    try:
        with open(_ctx_path(root, name), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"revision": 0}
    if not isinstance(data, dict):
        return {"revision": 0}
    data.setdefault("revision", 0)
    return data


def _ctx_save(root, name, data):
    path = _ctx_path(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _apply_ctx(root, name, opts, wanted):
    """把 ctx 默认值填进 opts 未显式给出的字段；返回继承字段名列表。"""
    ctx = _ctx_load(root, name)
    rev = int(ctx.get("revision") or 0)
    want_rev = getattr(opts, "ctx_rev", None)
    if want_rev is not None and int(want_rev) != rev:
        raise DbgError(
            "ctx_conflict：查询默认值已改动（当前 rev=%d，你钉住的是 rev=%s）；"
            "用 ctx get 看当前值，或去掉 --ctx-rev 重试"
            % (rev, want_rev))
    inherited = []
    if "case" in wanted and getattr(opts, "case", None) is None and ctx.get("case") is not None:
        opts.case = ctx["case"]
        inherited.append("case")
    if "signal" in wanted and getattr(opts, "signal", None) in (None, ""):
        sigs = ctx.get("signals") or []
        if sigs:
            opts.signal = sigs[0]
            inherited.append("signal")
    if "signals" in wanted and not (getattr(opts, "signal", None) or []) and ctx.get("signals"):
        opts.signal = list(ctx["signals"])
        inherited.append("signals")
    if "clock" in wanted and not getattr(opts, "clock", None) and ctx.get("clock"):
        opts.clock = ctx["clock"]
        inherited.append("clock")
    if "valid" in wanted and not getattr(opts, "valid", None) and ctx.get("valid"):
        opts.valid = ctx["valid"]
        inherited.append("valid")
    if "start" in wanted and getattr(opts, "start", None) is None and ctx.get("start") is not None:
        opts.start = ctx["start"]
        inherited.append("start")
    if "end" in wanted and getattr(opts, "end", None) is None and ctx.get("end") is not None:
        opts.end = ctx["end"]
        inherited.append("end")
    return inherited


def cmd_ctx(root, name, opts, profile, run, cfg):
    data = _ctx_load(root, name)
    act = opts.ctx_action
    if act == "get":
        return json.dumps(data, ensure_ascii=False, sort_keys=True), 0
    if act == "clear":
        fields = list(opts.field or [])
        if fields:
            for f in fields:
                data.pop(f, None)
            note = "清除字段 %s" % "、".join(fields)
        else:
            keep = data.get("revision") or 0
            data = {"revision": keep}
            note = "全部清除"
        data["revision"] = int(data.get("revision") or 0) + 1
        _ctx_save(root, name, data)
        return "%s（rev=%d）" % (note, data["revision"]), 0
    # set：只合并显式给出的键
    changed = []
    if opts.case is not None:
        data["case"] = int(opts.case)
        changed.append("case")
    if opts.module is not None:
        data["module"] = opts.module
        changed.append("module")
    if opts.tag is not None:
        data["tag"] = opts.tag
        changed.append("tag")
    if opts.signal:
        data["signals"] = list(opts.signal)
        changed.append("signals")
    if opts.clock:
        data["clock"] = opts.clock
        changed.append("clock")
    if opts.valid:
        data["valid"] = opts.valid
        changed.append("valid")
    if opts.start is not None:
        data["start"] = int(opts.start)
        changed.append("start")
    if opts.end is not None:
        data["end"] = int(opts.end)
        changed.append("end")
    data["revision"] = int(data.get("revision") or 0) + 1
    _ctx_save(root, name, data)
    return ("已写入查询默认值（rev=%d；changed: %s；signals=%s）"
            % (data["revision"], "、".join(changed) or "无",
               data.get("signals") or [])), 0


# ------------------------------------------------------------------ 节点表（行 2）


def node_names(root, name):
    """行 2（处理流程梳理）流程文档的节点表：flow_doc/<sys>_flow.md 的
    「节点表」章节表格第一列（章节集见 framework/templates/chapters.yaml 的 step1）。"""
    path = os.path.join(root, name, "flow_doc", "%s_flow.md" % name)
    if not os.path.isfile(path):
        return []
    names = []
    in_section = False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("## "):
                in_section = "节点表" in line
                continue
            if not in_section:
                continue
            text = line.strip()
            if not text.startswith("|"):
                continue
            cells = [cell.strip() for cell in text.strip("|").split("|")]
            if not cells or set("".join(cells)) <= set("-: "):
                continue  # 分隔行
            if cells[0] in ("", "节点"):
                continue  # 表头
            if cells[0] not in names:
                names.append(cells[0])
    return names


# ------------------------------------------------------------------ waves


def cmd_waves(root, name, opts, profile, run, cfg):
    scenario = _scenario(opts)
    wd = eda_mcp.workdir(profile, scenario, name, getattr(opts, "module", "") or "")
    proc = eda_mcp.run_ssh(profile, "ls -1 %s/*.fsdb 2>/dev/null" % shlex.quote(wd), run=run)
    if proc.returncode != 0:
        raise DbgError("列波形失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    files = sorted(line.strip() for line in (proc.stdout or "").splitlines() if line.strip())
    state = _load_state(root, name)
    stale = ""
    rows = []
    for path in files:
        rec = _sim_run_for_wave(state.get("runs"), scenario,
                                getattr(opts, "module", "") or "", path)
        if getattr(opts, "run", "") and (rec or {}).get("id") != opts.run:
            continue
        note, mark = _freshness(root, name, rec)
        stale = stale or note
        inferred = "" if (rec or {}).get("waves") else ("（推断）" if rec else "")
        rows.append("%s  %s  %s%s" % (path, (rec or {}).get("id") or "无运行记录", mark, inferred))
    if getattr(opts, "run", "") and not rows:
        raise DbgError("运行记录 %s 名下没有匹配的波形（记录可能没有 waves 字段，"
                       "或远端 %s 里没有 *.fsdb）" % (opts.run, wd))
    out = ([stale] if stale else [])
    out.append("远端 %s：共 %d 个 *.fsdb" % (wd, len(files)))
    out.extend(rows or ["（无）"])
    return "\n".join(out), 0


# ------------------------------------------------------------------ signals / wave / value


def cmd_signals(root, name, opts, profile, run, cfg):
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    cmd = "%s/bin/eda-mcp signals %s" % (cfg["prefix"], shlex.quote(fsdb))
    if opts.pattern:
        cmd += " --pattern %s" % shlex.quote(opts.pattern)
    if getattr(opts, "as_args", False):
        cmd += " --as-args"
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 signals 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    fp = _fp_of("signals", fsdb, rec, mark, getattr(opts, "_inherited", []),
                _remote_stat(profile, run, fsdb))
    return _with_stale(stale, (proc.stdout or "").rstrip() + "\n" + _fp_line(fp)), 0


def cmd_wave(root, name, opts, profile, run, cfg):
    signals = list(opts.signal or [])
    if not signals:
        raise DbgError("wave 需要 -s <信号>（可重复）")
    if opts.time and (opts.start is not None or opts.end is not None):
        raise DbgError("-t/-c 与 --start/--end 互斥，只给一种")
    if not opts.time and (opts.start is None or opts.end is None):
        raise DbgError("wave 需要 -t <T> -c <C>，或同时给出 --start 与 --end")
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    cmd = "%s/bin/eda-mcp wave %s" % (cfg["prefix"], shlex.quote(fsdb))
    cmd += "".join(" -s %s" % shlex.quote(sig) for sig in signals)
    if opts.time:
        cmd += " -t %s -c %d" % (shlex.quote(opts.time), int(opts.cycles or 20))
    else:
        cmd += " --start %s --end %s" % (shlex.quote(str(opts.start)), shlex.quote(str(opts.end)))
    if opts.clock:
        cmd += " --clock %s" % shlex.quote(opts.clock)
    summary = getattr(opts, "summary", None)
    if summary:
        # 摘要走 --json：波形图与 segments 都在结果对象里，一次取全
        cmd += " --json --summary %s" % shlex.quote(summary)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 wave 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    payload = _json_part(proc.stdout)
    lines = []
    try:
        parsed = json.loads(payload)
    except ValueError as exc:
        raise DbgError("远端返回的不是合法 WaveDrom JSON：%s" % exc)
    if summary:
        diagram = parsed.get("json")
        if not isinstance(diagram, str) or not diagram.strip():
            raise DbgError("远端 eda-mcp 的 --json 结果里没有波形图（远端版本可能过旧）；"
                           "先跑 python3 script/framework.py eda-mcp install")
        payload = diagram
        segments = parsed.get("segments") or {}
        sidecar = os.path.join(eda_mcp.local_dbg_dir(root, name),
                               "case%d_%s_segments.json" % (int(opts.case), _label(signals)))
        os.makedirs(os.path.dirname(sidecar), exist_ok=True)
        with open(sidecar, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "window": parsed.get("window"),
                    "clock": parsed.get("clock"),
                    "segments": segments,
                    "width_truncated": parsed.get("width_truncated") or [],
                    "signals": parsed.get("signals") or [],
                },
                fh, ensure_ascii=False, indent=2,
            )
            fh.write("\n")
        lines.append("翻转段见 %s" % os.path.relpath(sidecar, root).replace(os.sep, "/"))
        for hier in sorted(segments):
            body = "；".join("[%s, %s] %s" % (seg[0], seg[1], seg[2]) for seg in segments[hier])
            lines.append("  %s: %s" % (hier, body))
        if parsed.get("width_truncated"):
            lines.append("警告: 以下信号超 32 bit，标签只留低 32 bit -> %s"
                         % ", ".join(parsed["width_truncated"]))
    local = os.path.join(eda_mcp.local_dbg_dir(root, name),
                         "case%d_%s.json" % (int(opts.case), _label(signals)))
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "w", encoding="utf-8") as fh:
        fh.write(payload if payload.endswith("\n") else payload + "\n")
    rel = os.path.relpath(local, root).replace(os.sep, "/")
    lines.insert(0, "已写入 %s" % rel)
    fp = _fp_of("wave", fsdb, rec, mark, getattr(opts, "_inherited", []),
                _remote_stat(profile, run, fsdb))
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


def _first_value(entry):
    """WaveDrom 信号对象在窗口里的第一个值：'0'/'1'/'x'/'z' 直接是电平，
    '='/'2'~'5' 是数据槽，取 data 数组第一项；'.'/'|' 延续前值（窗口首槽不会是它）。"""
    wave = str(entry.get("wave") or "")
    data = list(entry.get("data") or [])
    index = 0
    for ch in wave:
        if ch in ".|":
            continue
        if ch in ("=", "2", "3", "4", "5"):
            if index < len(data):
                return str(data[index])
            index += 1
            continue
        return ch
    return None


def _lookup_value(payload, wanted):
    wanted = str(wanted)
    leaf = wanted.split(".")[-1]
    stack = list(payload.get("signal") or [])
    while stack:
        item = stack.pop(0)
        if isinstance(item, list):
            stack = list(item) + stack
            continue
        if not isinstance(item, dict):
            continue
        nm = str(item.get("name") or "")
        if wanted in (nm, nm.split(".")[-1]) or leaf in (nm, nm.split(".")[-1]):
            value = _first_value(item)
            if value is not None:
                return value
    return None


def cmd_value(root, name, opts, profile, run, cfg):
    if not opts.signal:
        raise DbgError("value 需要 -s <信号>（或先 ctx set -s 设置默认信号）")
    if not opts.time:
        raise DbgError("value 需要 --time <时刻>")
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    # 上游 CLI 没有 fsdb_value 子命令：用 wave 的单周期窗口（-t T -c 1）等价取值，
    # 再从 WaveDrom JSON 里读该信号的第一个值。
    cmd = "%s/bin/eda-mcp wave %s -s %s -t %s -c 1" % (
        cfg["prefix"], shlex.quote(fsdb), shlex.quote(opts.signal), shlex.quote(opts.time))
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端取值失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    try:
        payload = json.loads(_json_part(proc.stdout))
    except ValueError as exc:
        raise DbgError("远端返回的不是合法 WaveDrom JSON：%s" % exc)
    value = _lookup_value(payload, opts.signal)
    if value is None:
        raise DbgError("在返回的 WaveDrom JSON 里找不到信号 %s 的值" % opts.signal)
    fp = _fp_of("value", fsdb, rec, mark, getattr(opts, "_inherited", []),
                _remote_stat(profile, run, fsdb))
    return _with_stale(stale, "%s @ %s = %s\n%s"
                       % (opts.signal, opts.time, value, _fp_line(fp))), 0


# ------------------------------------------------------------------ extract


def cmd_extract(root, name, opts, profile, run, cfg):
    known = node_names(root, name)
    if not known:
        raise DbgError("在 flow_doc/%s_flow.md 里取不到节点表（行 2 的「节点表」章节），"
                       "无法校验节点名" % name)
    pairs = []
    for item in (opts.node or []):
        if "=" not in item:
            raise DbgError("--node 需要 节点名=层次路径 形式：%r" % item)
        node, hier = (part.strip() for part in item.split("=", 1))
        if not node or not hier:
            raise DbgError("--node 需要 节点名=层次路径 形式：%r" % item)
        pairs.append((node, hier))
    if not pairs:
        raise DbgError("extract 需要至少一个 --node <节点名>=<层次路径>（可重复）")
    unknown = [node for node, _hier in pairs if node not in known]
    if unknown:
        raise DbgError("节点名不在行 2 节点表里：%s（节点表里有：%s）"
                       % ("、".join(unknown), "、".join(known)))
    if not opts.clock:
        raise DbgError("extract 需要 --clock <时钟>（或先 ctx set --clock 设置默认时钟）")
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    rdir = eda_mcp.remote_dbg_dir(profile, name)
    eda_mcp.run_ssh(profile, "mkdir -p %s" % shlex.quote(rdir), run=run)
    cmd = "%s/bin/eda-mcp wave_extract %s --clock %s" % (
        cfg["prefix"], shlex.quote(fsdb), shlex.quote(opts.clock))
    if opts.edge != "posedge":
        cmd += " --edge %s" % opts.edge
    if opts.valid:
        cmd += " --valid %s" % shlex.quote(opts.valid)
    cmd += "".join(" --node %s" % shlex.quote("%s=%s" % pair) for pair in pairs)
    if (opts.start is None) != (opts.end is None):
        raise DbgError("--start 与 --end 要同时给出（或都不给）")
    if opts.start is not None:
        cmd += " --start %d --end %d" % (int(opts.start), int(opts.end))
    cmd += " --out-dir %s" % shlex.quote(rdir)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 wave_extract 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    try:
        res = json.loads(_json_part(proc.stdout))
    except ValueError as exc:
        raise DbgError("远端 wave_extract 没有返回 JSON：%s" % exc)
    # 拉回远端 <sys>/work/dbg/ → 本地 <sys>/work/dbg/（work/ 不入 git）
    local_dir = eda_mcp.local_dbg_dir(root, name)
    os.makedirs(local_dir, exist_ok=True)
    pull = run(["rsync", "-avz", "%s:%s/" % (profile["ssh_alias"], rdir), local_dir + "/"],
               capture_output=True, text=True, errors="replace")
    if pull.returncode != 0:
        raise DbgError("拉回导出文件失败（退出码 %s）：%s" % (pull.returncode, _last(pull.stderr)))
    case = int(opts.case)
    lines_out = ["导出完成（时钟沿 %s 拍，valid=%s）" % (res.get("beats", "?"), opts.valid or "无")]
    for node in res.get("nodes") or []:
        base = os.path.basename(str(node.get("file") or ""))
        target = os.path.join(local_dir, "case%d_%s.txt" % (case, _safe_name(node.get("name"))))
        src = os.path.join(local_dir, base)
        if base and src != target and os.path.isfile(src):
            os.replace(src, target)
        rel = os.path.relpath(target, root).replace(os.sep, "/")
        lines_out.append("%s（%s 行）" % (rel, node.get("lines", "?")))
    fp = _fp_of("extract", fsdb, rec, mark, getattr(opts, "_inherited", []),
                _remote_stat(profile, run, fsdb))
    lines_out.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines_out)), 0


# ------------------------------------------------------------------ npi


def design_id(root, name):
    """`<sys>@<RTL 摘要前 8 位>`。RTL 摘要取 lint 的输入集（rtl/ + 例化到的
    pub_code，CAPABILITY_INPUTS["lint"]），与 NPI 打开的文件清单一一对应。"""
    return "%s@%s" % (name, inputs_digest(root, name, capability="lint")[:8])


def _npi_files(root, name, profile):
    """打开设计用的文件清单：rtl/ 全量 + 例化到的 pub_code（复用 engine._pub_code_used）。"""
    rtl = os.path.join(root, name, "rtl")
    if not os.path.isdir(rtl):
        raise DbgError("子系统 %s 没有 rtl/ 目录，NPI 无设计可开" % name)
    files = [fn for fn in sorted(os.listdir(rtl)) if fn.endswith((".sv", ".v"))]
    if not files:
        raise DbgError("rtl/ 里没有 .sv/.v 文件，NPI 无设计可开")
    paths = [eda_mcp.mirror_of(profile, "%s/rtl/%s" % (name, fn)) for fn in files]
    for path in _pub_code_used(root, os.path.join(root, name)):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        paths.append(eda_mcp.mirror_of(profile, rel))
    return paths


def _npi_alive(profile, run, cfg):
    proc = eda_mcp.run_ssh(profile, "%s/bin/eda-mcp npi list" % cfg["prefix"], run=run)
    alive = []
    for line in (proc.stdout or "").splitlines():
        matched = re.match(r"^(\S+)\s+alive=(\w+)", line.strip())
        if matched and matched.group(2).lower() == "true":
            alive.append(matched.group(1))
    return alive


def _npi_close(profile, run, cfg, design):
    return eda_mcp.run_ssh(profile, "%s/bin/eda-mcp npi close %s" % (cfg["prefix"], shlex.quote(design)),
                           run=run)


def _npi_open(root, name, profile, run, cfg, top="", alive=None):
    """打开（或复用）当前 RTL 的设计。返回 (design_id, 过程说明)。"""
    did = design_id(root, name)
    alive = _npi_alive(profile, run, cfg) if alive is None else alive
    if did in alive:
        return did, "复用已打开的设计 %s（RTL 摘要一致）" % did
    # NPI 必须对得上当前 RTL——打开前先 rsync 对齐（work/ 在排除表里，
    # 不会碰远端波形与 dbg 导出）。
    sync = run(eda_mcp.rsync_line(profile), shell=True, capture_output=True, text=True,
               errors="replace")
    if sync.returncode != 0:
        raise DbgError("rsync 对齐失败（退出码 %s）：%s" % (sync.returncode, _last(sync.stderr)))
    notes = []
    for other in alive:
        if other.startswith(name + "@"):
            # 打开新设计前关闭同一子系统旧的 design_id，避免旧 daemon 冒充新设计。
            proc = _npi_close(profile, run, cfg, other)
            notes.append("关闭旧设计 %s（退出码 %s）" % (other, proc.returncode))
    others = [item for item in alive if not item.startswith(name + "@")]
    while len(others) + 1 > MAX_DESIGN_DAEMONS:
        victim = others.pop(0)
        _npi_close(profile, run, cfg, victim)
        notes.append("关闭 %s（腾出 daemon 槽位，上限 %d）" % (victim, MAX_DESIGN_DAEMONS))
    files = _npi_files(root, name, profile)
    cmd = "%s/bin/eda-mcp npi open %s" % (cfg["prefix"], shlex.quote(did))
    cmd += "".join(" --file %s" % shlex.quote(path) for path in files)
    if top:
        cmd += " --top %s" % shlex.quote(top)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("npi open 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    notes.insert(0, (proc.stdout or "").strip())
    notes.append("design=%s（files=%d）" % (did, len(files)))
    return did, "\n".join(note for note in notes if note)


def cmd_npi(root, name, opts, profile, run, cfg):
    act = opts.npi_action
    if act == "open":
        _did, note = _npi_open(root, name, profile, run, cfg, top=opts.top or "")
        return note, 0
    # 查询前核对 design_id 的摘要与本地当前 RTL 一致，不一致先重新打开。
    did = design_id(root, name)
    alive = _npi_alive(profile, run, cfg)
    note = ""
    if did not in alive:
        did, note = _npi_open(root, name, profile, run, cfg, top=opts.top or "", alive=alive)
    if act == "hier":
        cmd = "%s/bin/eda-mcp npi hier %s" % (cfg["prefix"], shlex.quote(did))
        if opts.root:
            cmd += " --root %s" % shlex.quote(opts.root)
        if opts.pattern:
            cmd += " --pattern %s" % shlex.quote(opts.pattern)
        if opts.max_depth is not None:
            cmd += " --max-depth %d" % int(opts.max_depth)
    elif act in ("module", "object"):
        if not opts.arg:
            raise DbgError("npi %s 需要 <对象路径>" % act)
        cmd = "%s/bin/eda-mcp npi %s %s %s" % (cfg["prefix"], act, shlex.quote(did), shlex.quote(opts.arg))
    elif act == "find":
        cmd = "%s/bin/eda-mcp npi find %s %s --limit %d" % (
            cfg["prefix"], shlex.quote(did), shlex.quote(opts.arg or "*"), int(opts.limit))
    elif act == "trace":
        if not opts.arg:
            raise DbgError("npi trace 需要 <信号全路径>")
        cmd = "%s/bin/eda-mcp npi trace %s %s --direction %s --limit %d" % (
            cfg["prefix"], shlex.quote(did), shlex.quote(opts.arg), opts.direction, int(opts.limit))
    else:
        raise DbgError("未知 npi 动作 %s" % act)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 npi %s 失败（退出码 %s）：%s" % (act, proc.returncode, _last(proc.stderr or proc.stdout)))
    parts = ([note] if note else []) + [(proc.stdout or "").rstrip()]
    return "\n".join(part for part in parts if part), 0


def _ensure_design(root, name, profile, run, cfg, top=""):
    """确保 NPI 设计对得上当前 RTL（不一致自动重开）；返回 (design_id, 过程说明)。"""
    did = design_id(root, name)
    alive = _npi_alive(profile, run, cfg)
    if did in alive:
        return did, ""
    did, note = _npi_open(root, name, profile, run, cfg, top=top, alive=alive)
    return did, note


# ------------------------------------------------------------------ windows / diff / trace / active / fsm


def cmd_windows(root, name, opts, profile, run, cfg):
    if not opts.expr:
        raise DbgError("windows 需要 --expr <布尔表达式>（如 \"top.u_dut.u_x.valid == 1\"）")
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    cmd = "%s/bin/eda-mcp windows %s --expr %s" % (
        cfg["prefix"], shlex.quote(fsdb), shlex.quote(opts.expr))
    if opts.start is not None:
        cmd += " --start %s" % shlex.quote(str(opts.start))
    if opts.end is not None:
        cmd += " --end %s" % shlex.quote(str(opts.end))
    if getattr(opts, "min_duration", None):
        cmd += " --min-duration %s" % shlex.quote(str(opts.min_duration))
    cmd += " --limit %d" % int(getattr(opts, "limit", 200) or 200)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 windows 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    try:
        res = json.loads(_json_part(proc.stdout))
    except ValueError as exc:
        raise DbgError("远端 windows 没有返回 JSON：%s" % exc)
    if res.get("status") != "ok":
        raise DbgError("windows 未成功：%s" % json.dumps(res, ensure_ascii=False))
    inherited = getattr(opts, "_inherited", [])
    fp = _fp_of("windows", fsdb, rec, mark, inherited,
                _remote_stat(profile, run, fsdb))
    res["_fp"] = fp
    local = os.path.join(eda_mcp.local_dbg_dir(root, name),
                         "case%s_windows.json" % opts.case)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    rel = os.path.relpath(local, root).replace(os.sep, "/")
    lines = ["区间 %d 条，不可决 %s（窗口 %s~%s）→ %s"
             % (res.get("total_hits", 0), res.get("undecidable_time", 0),
                (res.get("window") or {}).get("start"), (res.get("window") or {}).get("end"), rel)]
    for hit in (res.get("hits") or [])[:10]:
        lines.append("  [%s, %s) 持续 %s%s"
                     % (hit["start"], hit["end"], hit["duration"],
                        "（窗口末端仍成立）" if hit.get("open_ended") else ""))
    shown = (res.get("hits") or [])
    if len(shown) > 10:
        lines.append("  …其余 %d 条见 JSON" % (len(shown) - 10))
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


def cmd_diff(root, name, opts, profile, run, cfg):
    cases = [int(c) for c in (opts.case or [])]
    if len(cases) < 2:
        raise DbgError("diff 需要至少两份波形：--case 1 --case 2（可继续追加 --case 3 …）")
    scenario = _scenario(opts)
    module = getattr(opts, "module", "") or ""
    tag = getattr(opts, "tag", DEFAULT_TAG)
    paths = [eda_mcp.fsdb_remote_path(profile, scenario, name, module, c, tag)
             for c in cases]
    recs, marks = [], []
    for p in paths:
        rec, _stale, mark = _wave_record(root, name, opts, p)
        recs.append(rec)
        marks.append(mark)
    stale = STALE_NOTE % "、".join(str((r or {}).get("id") or "?") for r, mk in zip(recs, marks) if mk == "输入已变更") if any(
        mk == "输入已变更" for mk in marks) else ""
    cmd = "%s/bin/eda-mcp diff" % cfg["prefix"]
    cmd += "".join(" %s" % shlex.quote(p) for p in paths)
    if opts.signal:
        cmd += "".join(" -s %s" % shlex.quote(s) for s in opts.signal)
    if getattr(opts, "filter", None):
        cmd += " --filter %s" % shlex.quote(opts.filter)
    if getattr(opts, "clock", None):
        cmd += " --clock %s" % shlex.quote(opts.clock)
    if opts.start is not None:
        cmd += " --start %s" % shlex.quote(str(opts.start))
    if opts.end is not None:
        cmd += " --end %s" % shlex.quote(str(opts.end))
    cmd += " --max-report %d" % int(getattr(opts, "max_report", 50) or 50)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 diff 失败（退出码 %s）：%s" % (proc.returncode, _last(proc.stderr or proc.stdout)))
    try:
        res = json.loads(_json_part(proc.stdout))
    except ValueError as exc:
        raise DbgError("远端 diff 没有返回 JSON：%s" % exc)
    if res.get("status") != "ok":
        raise DbgError("diff 未成功：%s" % json.dumps(res, ensure_ascii=False))
    inherited = getattr(opts, "_inherited", [])
    fp = {
        "tool": "dbg diff",
        "waves": paths,
        "runs": [(r or {}).get("id") for r in recs],
        "freshness": marks,
        "from_ctx": list(inherited),
    }
    res["_fp"] = fp
    local = os.path.join(eda_mcp.local_dbg_dir(root, name),
                         "diff_%s.json" % "_vs_".join(str(c) for c in cases))
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    rel = os.path.relpath(local, root).replace(os.sep, "/")
    first = res.get("first_divergence")
    lines = []
    if first is None:
        lines.append("没有发现分歧（compared=%s）→ %s" % (res.get("compared"), rel))
    else:
        lines.append("首分歧时刻 %s（compared=%s 份信号，分歧 %s 条）→ %s"
                     % (first, res.get("compared"), res.get("diverging_signals"), rel))
        for row in (res.get("signals") or [])[:10]:
            vals = " | ".join("case%s=%s" % (c, v) for c, v in zip(cases, row["values"]))
            lines.append("  %s @ %s： %s" % (row["hier"], row["time"], vals))
        if res.get("truncated_report"):
            lines.append("  …更多分歧信号见 JSON")
        groups = res.get("groups")
        if groups:
            cl = "；".join("case%s=%s" % ("、".join(str(i + 1) for i in c["files"]), c["value"])
                          for c in groups["clusters"])
            lines.append("分歧簇（%s @ %s）： %s" % (groups["signal"], groups["time"], cl))
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


def _join_command(root, name, opts, profile, run, cfg, remote_cmd_name, extra_args, sidecar_kind):
    """trace / active / fsm 共用骨架：取波形 → 保证设计开着 → 远端调用 → 落盘+摘要。"""
    if not opts.signal:
        raise DbgError("%s 需要 -s <目标信号（FSDB 层次路径）>" % remote_cmd_name)
    fsdb = _fsdb_path(profile, name, opts)
    rec, stale, mark = _wave_record(root, name, opts, fsdb)
    did, note = _ensure_design(root, name, profile, run, cfg, top=getattr(opts, "top", "") or "")
    cmd = "%s/bin/eda-mcp %s %s --design %s -s %s" % (
        cfg["prefix"], remote_cmd_name, shlex.quote(fsdb), shlex.quote(did), shlex.quote(opts.signal))
    cmd += "".join(" %s" % extra for extra in extra_args)
    proc = eda_mcp.run_ssh(profile, cmd, run=run)
    if proc.returncode != 0:
        raise DbgError("远端 %s 失败（退出码 %s）：%s" % (remote_cmd_name, proc.returncode, _last(proc.stderr or proc.stdout)))
    try:
        res = json.loads(_json_part(proc.stdout))
    except ValueError as exc:
        raise DbgError("远端 %s 没有返回 JSON：%s" % (remote_cmd_name, exc))
    if res.get("status") != "ok":
        raise DbgError("%s 未成功：%s" % (remote_cmd_name, json.dumps(res, ensure_ascii=False)))
    inherited = getattr(opts, "_inherited", [])
    fp = _fp_of(remote_cmd_name, fsdb, rec, mark, inherited,
                _remote_stat(profile, run, fsdb))
    fp["design"] = did
    res["_fp"] = fp
    local = os.path.join(eda_mcp.local_dbg_dir(root, name),
                         "case%s_%s_%s.json" % (opts.case, sidecar_kind, _safe_name(opts.signal)))
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    rel = os.path.relpath(local, root).replace(os.sep, "/")
    return res, rel, stale, fp, note


def cmd_trace(root, name, opts, profile, run, cfg):
    extra = ["--time %s" % shlex.quote(str(opts.time))] if getattr(opts, "time", None) else []
    extra.append("--depth %d" % int(getattr(opts, "depth", 6) or 6))
    if getattr(opts, "x", False):
        extra.append("--x")
    extra.append("--max-nodes %d" % int(getattr(opts, "max_nodes", 200) or 200))
    res, rel, stale, fp, note = _join_command(
        root, name, opts, profile, run, cfg, "trace", extra, "trace")
    lines = []
    if note:
        lines.append(note)
    nodes = res.get("nodes") or []
    for n in nodes:
        pad = "  " * int(n.get("depth") or 0)
        val = n.get("value") if n.get("value") is not None else "（波形无值）"
        lines.append("%s%s = %s" % (pad, n["path"], val))
        if n.get("stmt"):
            lines.append("%s    语句 @%s:%s %s" % (pad, n["stmt"].get("file"), n["stmt"].get("line"), n["stmt"].get("rhs")))
    if res.get("x_roots") is not None:
        roots = res.get("x_roots") or []
        lines.append("X 根因候选 %d 条：%s" % (
            len(roots), "、".join(r["path"] for r in roots[:8]) or "无"))
    if res.get("truncated"):
        lines.append("警告：节点数达到上限，链路被截断（--max-nodes 调大或 --depth 调小）")
    lines.append("链路 %d 节点 → %s" % (len(nodes), rel))
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


def cmd_active(root, name, opts, profile, run, cfg):
    extra = ["--time %s" % shlex.quote(str(opts.time))] if getattr(opts, "time", None) else []
    if getattr(opts, "clock", None):
        extra.append("--clock %s" % shlex.quote(opts.clock))
    if getattr(opts, "edge", "posedge") != "posedge":
        extra.append("--edge %s" % opts.edge)
    res, rel, stale, fp, note = _join_command(
        root, name, opts, profile, run, cfg, "active", extra, "active")
    lines = []
    if note:
        lines.append(note)
    tgt = res.get("target") or {}
    lines.append("目标 %s @ %s = %s（%s）"
                 % (tgt.get("path"), tgt.get("time"), tgt.get("value"), tgt.get("npi_kind")))
    if res.get("capture_note"):
        lines.append("口径：%s" % res["capture_note"])
    for d in (res.get("drivers") or []):
        if d.get("kind") == "constant":
            lines.append("  [常量] %s" % d.get("path"))
        else:
            lines.append("  [%s] %s = %s" % (d.get("classification"), d.get("path"), d.get("value")))
    lines.append("分类 %s → %s" % (json.dumps(res.get("summary"), ensure_ascii=False), rel))
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


def cmd_fsm(root, name, opts, profile, run, cfg):
    extra = []
    if getattr(opts, "clock", None):
        extra.append("--clock %s" % shlex.quote(opts.clock))
    if getattr(opts, "edge", "posedge") != "posedge":
        extra.append("--edge %s" % opts.edge)
    if opts.start is not None:
        extra.append("--start %s" % shlex.quote(str(opts.start)))
    if opts.end is not None:
        extra.append("--end %s" % shlex.quote(str(opts.end)))
    extra.append("--limit %d" % int(getattr(opts, "limit", 200) or 200))
    res, rel, stale, fp, note = _join_command(
        root, name, opts, profile, run, cfg, "fsm", extra, "fsm")
    lines = []
    if note:
        lines.append(note)
    tgt = res.get("target") or {}
    lines.append("状态寄存器 %s（%s），窗口内值变 %s 次、转移 %s 种、X 进入 %s 次 → %s"
                 % (tgt.get("path"), tgt.get("npi_kind"), res.get("changes"),
                    res.get("count"), res.get("x_entries"), rel))
    for tr in (res.get("transitions") or [])[:12]:
        line = "  %s → %s  ×%s  首现 %s" % (tr["from"], tr["to"], tr["count"], tr["first_time"])
        if tr.get("capture_edge") is not None:
            drv = "、".join("%s=%s" % (d["path"].rsplit(".", 1)[-1], d["value"])
                            for d in (tr.get("drivers_at_capture") or []))
            line += "；采集沿 %s：%s" % (tr["capture_edge"], drv or "无驱动值")
        lines.append(line)
    lines.append(_fp_line(fp))
    return _with_stale(stale, "\n".join(lines)), 0


# ------------------------------------------------------------------ doctor


def cmd_doctor(root, run):
    """`dbg doctor` 的远端部分（同 doctor --mcp）。"""
    from framework import doctor as doctor_mod
    code, text = doctor_mod.run_mcp(root=root, run=run)
    return text, code


# ------------------------------------------------------------------ 入口


def _add_ctx_rev(sp):
    """给支持查询默认值的子命令挂上 --ctx-rev（钉住 rev，改动即报 ctx_conflict）。"""
    sp.add_argument("--ctx-rev", dest="ctx_rev", type=int, default=None,
                    help="钉住查询默认值版本；ctx 被改动时报 ctx_conflict，不静默换口径")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dbg", description="EDA MCP 观察面封装（只用 env/fsdb/wave/npi 组）")
    sub = parser.add_subparsers(dest="action", required=True)

    sp = sub.add_parser("waves", help="列远端工作目录的 *.fsdb 与所属运行记录的新鲜度")
    sp.add_argument("--module", default="")
    sp.add_argument("--run", default="", help="只看该运行记录（R0xx）名下的波形")
    sp.add_argument("--tag", default=DEFAULT_TAG, help="TB_DUMP_TAG（默认 wave）")

    sp = sub.add_parser("signals", help="列波形信号（eda-mcp signals）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("--pattern", default=None)
    sp.add_argument("--as-args", action="store_true", dest="as_args",
                    help="输出可直接粘进 wave -s 的参数串（配合 --pattern 一步取全名）")
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("wave", help="WaveDrom JSON 导出到 <sys>/work/dbg/")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", action="append", default=[], help="信号（可重复）")
    sp.add_argument("-t", "--time", default=None, help="中心时间点（如 500ns）")
    sp.add_argument("-c", "--cycles", type=int, default=20)
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--clock", default=None)
    sp.add_argument("--summary", default=None, choices=["flip"],
                    help="翻转段摘要（只列翻转时刻+值；长窗口用它，不读巨长的 wave 串）")
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("value", help="单点取值")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", default=None)
    sp.add_argument("--time", default=None)
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("extract", help="时钟沿采样导出节点序列（远端 wave_extract）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("--clock", default=None)
    sp.add_argument("--valid", default=None)
    sp.add_argument("--node", action="append", default=[], metavar="NAME=PATH",
                    help="节点名=层次路径（可重复；节点名必须在行 2 节点表里）")
    sp.add_argument("--start", type=int, default=None)
    sp.add_argument("--end", type=int, default=None)
    sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"])
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("windows", help="时间窗搜索：布尔表达式何时成立（区间答案）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("--expr", required=True,
                    help='布尔表达式，如 "top.u_dut.u_x.valid == 1 && top.u_dut.u_x.cnt > 3"')
    sp.add_argument("--start", default=None, help="窗口起点（fsdb 原值或 100ns 形式；缺省全波形）")
    sp.add_argument("--end", default=None)
    sp.add_argument("--min-duration", dest="min_duration", default=None,
                    help="只报至少持续这么长的区间（如 20ns）")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("diff", help="N 份 FSDB 首分歧定位（回归 pass/fail 第一入口）")
    sp.add_argument("--case", action="append", type=int, default=[],
                    help="波形用例号（至少两个，可重复：--case 1 --case 2）")
    sp.add_argument("-s", "--signal", action="append", default=[], help="只比这些信号（可重复）")
    sp.add_argument("--filter", dest="filter", default=None, help="信号通配裁剪")
    sp.add_argument("--clock", default=None, help="只在时钟上升沿比较（滤沿间毛刺）")
    sp.add_argument("--start", default=None, help="比较窗口起点")
    sp.add_argument("--end", default=None)
    sp.add_argument("--max-report", dest="max_report", type=int, default=50)
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("trace", help="驱动链带值回溯（NPI 驱动 × FSDB 值；--x 为 X 根因口径）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", default=None, help="目标信号（FSDB 层次路径）")
    sp.add_argument("--time", default=None, help="时刻（fsdb 原值或 85ns）")
    sp.add_argument("--depth", type=int, default=6)
    sp.add_argument("--x", action="store_true", help="X 根因口径：只沿 x/z 分支走")
    sp.add_argument("--max-nodes", dest="max_nodes", type=int, default=200)
    sp.add_argument("--top", default=None, help="打开设计时的顶层")
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("active", help="某一拍哪条驱动在起作用（值一致分类）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", default=None, help="目标信号（FSDB 层次路径）")
    sp.add_argument("--time", default=None, help="时刻（fsdb 原值或 81.5ns）")
    sp.add_argument("--clock", default=None, help="时钟（过程驱动的寄存器按采集沿取驱动值）")
    sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"])
    sp.add_argument("--top", default=None)
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("fsm", help="状态寄存器实际转移表（次数/首现/采集沿驱动值）")
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", default=None, help="状态寄存器（FSDB 层次路径）")
    sp.add_argument("--clock", default=None, help="时钟（给采集沿上的驱动值）")
    sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"])
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--top", default=None)
    sp.add_argument("--module", default="")
    sp.add_argument("--tag", default=DEFAULT_TAG)
    _add_ctx_rev(sp)

    sp = sub.add_parser("ctx", help="查询默认值：一套调试会话共享 case/信号/时钟/时间窗")
    sp.add_argument("ctx_action", choices=["get", "set", "clear"])
    sp.add_argument("--case", type=int, default=None)
    sp.add_argument("-s", "--signal", action="append", default=[], help="默认信号（可重复）")
    sp.add_argument("--clock", default=None)
    sp.add_argument("--valid", default=None)
    sp.add_argument("--start", type=int, default=None, help="默认窗口起点（fsdb 原值）")
    sp.add_argument("--end", type=int, default=None)
    sp.add_argument("--module", default=None)
    sp.add_argument("--tag", default=None)
    sp.add_argument("--field", action="append", default=[],
                    help="clear 只清这些字段（可重复；缺省全清）")

    sp = sub.add_parser("npi", help="Verdi NPI 设计模型查询")
    sp.add_argument("npi_action", choices=["open", "hier", "module", "object", "find", "trace"])
    sp.add_argument("arg", nargs="?", default="",
                    help="object/module 给对象路径；find 给通配；trace 给信号全路径")
    sp.add_argument("--module", default="",
                    help="保留参数：文件清单始终取 rtl/ 全量加例化到的 pub_code")
    sp.add_argument("--root", default=None, help="hier 层次根")
    sp.add_argument("--pattern", default=None)
    sp.add_argument("--max-depth", dest="max_depth", type=int, default=None)
    sp.add_argument("--direction", default="both", choices=["driver", "load", "both"])
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--top", default=None, help="打开设计时的顶层")

    sub.add_parser("doctor", help="远端部分（同 doctor --mcp）")
    return parser


def run_dbg(root, name, argv, run=None):
    """dbg 唯一入口。返回 (输出文本, 退出码)：0 成功、2 用法/校验错误、
    3 远端版本不一致。任何命令都不写 state.json。"""
    root = root or project_root()
    opts = build_parser().parse_args(list(argv))
    try:
        try:
            profile = _profile()
        except FileNotFoundError as exc:
            return "失败 %s" % exc, 2
        cfg = eda_mcp.load_config(profile)
        if cfg is None:
            return ("剖面 %s 未配置 eda_mcp 字段（toolchain/profiles/%s/profile.yaml），dbg 不可用"
                    % (profile.get("id", ""), profile.get("id", ""))), 2
        if opts.action == "doctor":
            if name and name != "doctor":
                raise DbgError("dbg doctor 不需要子系统名")
            return cmd_doctor(root, run=run)
        if not name or name == "doctor":
            raise DbgError("该命令需要子系统名：dbg <sys> %s ..." % opts.action)
        # 远端不是本地当前源码装出来的就明确报错（按会话缓存，不重复走 SSH）。
        ok, message = eda_mcp_deploy.version_check(profile=profile, root=root, run=run)
        if not ok:
            return message, 3
        # 查询默认值：显式参数优先；继承项在输出 from_ctx 里声明；--ctx-rev 钉版本。
        wanted = _CTX_WANTED.get(opts.action)
        if wanted:
            opts._inherited = _apply_ctx(root, name, opts, wanted)
        else:
            opts._inherited = []
        if (opts.action in ("signals", "wave", "value", "extract", "windows",
                            "trace", "active", "fsm")
                and getattr(opts, "case", None) is None):
            raise DbgError("缺 --case <用例号>（查询默认值里也没有；"
                           "先 dbg %s ctx set --case N）" % name)
        handlers = {
            "waves": cmd_waves, "signals": cmd_signals, "wave": cmd_wave,
            "value": cmd_value, "extract": cmd_extract, "npi": cmd_npi,
            "ctx": cmd_ctx, "windows": cmd_windows, "diff": cmd_diff,
            "trace": cmd_trace, "active": cmd_active, "fsm": cmd_fsm,
        }
        return handlers[opts.action](root, name, opts, profile, run, cfg)
    except DbgError as exc:
        return str(exc), 2
    except FileNotFoundError as exc:
        return "失败 %s" % exc, 2
