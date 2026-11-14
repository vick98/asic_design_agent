#!/usr/bin/env python3
# 作者：vick 邮箱：ykun@yk9811.com

"""asic_design_agent 命令入口。"""

import argparse
import json
import os
import subprocess
import sys
import time

_CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _CODE_ROOT)

from framework.digest import dump
from framework.engine import (
    EngineError, advance, commit_decision, record_run,
    set_module, status_report,
)
from framework.hosts.render import render
from framework.profile_run import (
    JOB_TERMINAL, create_job, find_job, job_now, list_jobs, read_job,
    run_other, run_sim, update_job,
)
from framework.state import (
    StateEncodingError, brief_report, init_sys, root_of, verify_state,
)
from framework.tbgen import generate
from framework.toolbox.fx import (
    FxError, add, addr_capacity, cmul, finish, fmt_s, golden_tol, latency, lift, line, mul, note_text,
    obs16, pack, parse_fmt, round_shr, run_chain, sac_shift, sat_bounds, shift, logical_shr, sub,
)


def _fmt(text):
    return parse_fmt(text)


def cmd_fx(args):
    try:
        if args.op == "mul":
            f1, f2 = _fmt(args.a), _fmt(args.b)
            result = mul(f1, f2)
            item = line("mul", "%s * %s" % (fmt_s(f1), fmt_s(f2)), result)
        elif args.op == "cmul":
            f1, f2 = _fmt(args.a), _fmt(args.b)
            result = cmul(f1, f2)
            item = line("cmul", "%s ** %s" % (fmt_s(f1), fmt_s(f2)), result)
        elif args.op == "add":
            f1, f2 = _fmt(args.a), _fmt(args.b)
            result = add(f1, f2)
            item = line("add", "%s + %s" % (fmt_s(f1), fmt_s(f2)), result)
        elif args.op == "sub":
            f1, f2 = _fmt(args.a), _fmt(args.b)
            result = sub(f1, f2)
            item = line("sub", "%s - %s" % (fmt_s(f1), fmt_s(f2)), result)
        elif args.op == "lift":
            result = lift(_fmt(args.a))
            item = line("lift", "lift %s" % fmt_s(_fmt(args.a)), result)
        elif args.op == "shift":
            src = _fmt(args.a)
            result = shift(src, args.n, shrink=args.shrink)
            expr = "%s >> %d%s" % (fmt_s(src), args.n, " shrink" if args.shrink else "")
            item = line("shift", expr, result)
        elif args.op == "sat":
            bounds = sat_bounds(_fmt(args.a), symmetric=args.symmetric)
            item = line("sat", "sat %s %s" % (fmt_s(_fmt(args.a)), bounds["mode"]), extra=bounds,
                        note=note_text("sat", bounds))
        elif args.op == "obs16":
            got = obs16(_fmt(args.a))
            item = line("obs16", "obs16 %s" % fmt_s(_fmt(args.a)), got["format"],
                        {"shift": got["shift"], "pad_low": got["pad_low"]})
        elif args.op == "pack":
            got = pack(args.widths)
            item = line("pack", "pack %s" % "+".join(str(w) for w in args.widths), extra=got,
                        note=note_text("pack", got))
        elif args.op == "addr":
            got = addr_capacity(args.depths, args.bits)
            item = line("addr", "addr %s bits=%d" % (args.depths, args.bits), extra=got,
                        note=note_text("addr", got))
        elif args.op == "round":
            if args.value is None:
                raise FxError("round 的输入要写成 --value <整数>，负数例如 --value -5")
            got = round_shr(args.value, args.n, args.mode)
            item = line("round", "round %d >> %d %s" % (args.value, args.n, args.mode),
                        extra={"value": got}, note=note_text("round", got))
        elif args.op == "tol":
            ref = _fmt(args.ref) if args.ref else None
            got = golden_tol(_fmt(args.a), args.lsb, ref)
            item = line("tol", "GOLDEN_TOL %s" % got["GOLDEN_TOL"], extra=got,
                        note=note_text("tol", got))
        elif args.op == "lshr":
            result = logical_shr(_fmt(args.a), args.n, shrink=args.shrink)
            item = line("lshr", "lshr %s >> %d" % (fmt_s(_fmt(args.a)), args.n), result)
        elif args.op == "chain":
            import json
            spec = json.loads(args.a)
            _env, rows = run_chain(spec["nodes"], spec["ops"])
            print("\n".join(row["text"] + "\nstamp: " + row["stamp"] for row in rows))
            return 0
        elif args.op == "latency":
            got = latency(args.cycles or [])
            item = line("latency", "latency %s" % (args.cycles or []), extra={"cycles": got},
                        note=note_text("latency", got))
        elif args.op == "sac":
            src, dst = _fmt(args.a), _fmt(args.b)
            n = sac_shift(src, dst)
            item = line("sac", "sac %s -> %s" % (fmt_s(src), fmt_s(dst)), extra={"shift": n},
                        note=note_text("sac", n))
        elif args.op == "finish":
            if not args.dest:
                raise FxError("finish 需要 --dest 给出目标容器，如 --dest \"<12,1,t>\"")
            src, dst = _fmt(args.a), _fmt(args.dest)
            got = finish(src, dst, args.n)
            item = line("finish", "finish %s >> %d half-up + sat -> %s"
                        % (fmt_s(src), args.n, fmt_s(dst)),
                        extra={"shift": got["shift"], "sat": got["sat"]},
                        note=note_text("finish", got))
        else:
            raise FxError("未知运算")
    except FxError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(item["text"])
    print("stamp: %s" % item["stamp"])
    return 0


def cmd_init(args):
    try:
        init_sys(root_of(), args.sys)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("已初始化 %s" % args.sys)
    return 0


def _subsystem_names():
    """仓库根下含 state.json 的子系统名（排除保留目录与隐藏目录）。"""
    from framework.state import RESERVED, SYS_NAME_RE
    root = root_of()
    names = []
    for name in sorted(os.listdir(root)):
        if name.startswith(".") or name in RESERVED or not SYS_NAME_RE.match(name):
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "state.json")):
            names.append(name)
    return names


def _subsystem_overview():
    """每个子系统的当前停点与等待开发者事项数（纯只读，复用 status_data）。"""
    from framework.engine import status_data
    rows = []
    for name in _subsystem_names():
        try:
            data = status_data(root_of(), name)
        except (FileNotFoundError, StateEncodingError) as exc:
            rows.append({"sys": name, "current": "", "current_stop": None,
                         "done": False, "human": 0, "error": str(exc)})
            continue
        current = data["current"]
        rows.append({
            "sys": name,
            "current": current["name"] if current else "",
            "current_stop": current["stop"] if current else None,
            "done": bool(data["done"]),
            "human": len(data["human"]),
        })
    return rows


def _render_subsystem_overview(rows):
    if not rows:
        return "仓库根下没有含 state.json 的子系统。"
    lines = ["仓库内子系统："]
    for row in rows:
        if row.get("error"):
            lines.append("%s：当前停点读取失败（%s）" % (row["sys"], row["error"]))
            continue
        current = row["current"] or "全部完成"
        human = ("有（%d 项）" % row["human"]) if row["human"] else "无"
        lines.append("%s：当前停点 %s；等待开发者 %s" % (row["sys"], current, human))
    return "\n".join(lines)


def cmd_status(args):
    try:
        if not args.sys:
            # 不带子系统名：列出仓库内全部子系统，不给单系统的长文。
            rows = _subsystem_overview()
            if getattr(args, "json", False):
                print(json.dumps(rows, ensure_ascii=False))
            else:
                print(_render_subsystem_overview(rows))
        elif getattr(args, "json", False):
            # 机器可读版：只打印一份 JSON（status_data 是纯只读结构），不混文本。
            from framework.engine import status_data
            print(json.dumps(status_data(root_of(), args.sys), ensure_ascii=False))
        elif getattr(args, "brief", False):
            # 只打印简报前两节（"需要你做的" + "自上一个里程碑以来"），
            # 供主持者在会话里引用，不复述长文。
            print(brief_report(root_of(), args.sys))
        else:
            print(status_report(root_of(), args.sys))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_state(args):
    """state.json 的只读校验入口。"""
    if args.action == "verify":
        ok, message = verify_state(root_of(), args.sys)
        print(message if ok else "校验失败：%s" % message)
        return 0 if ok else 1
    return 2


def cmd_advance(args):
    try:
        print(advance(
            root_of(), args.sys, args.stop, args.to,
            allow_violation=args.allow_violation,
            decision=args.decision or "",
        ))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _table(headers, rows):
    lines = ["| %s |" % " | ".join(headers), "|%s|" % "|".join("---" for _ in headers)]
    for row in rows:
        lines.append("| %s |" % " | ".join("" if cell is None else str(cell) for cell in row))
    return lines


def _related_hint(sys_name, content, exclude=""):
    """列出与本次正文相近的既有裁决，提醒"同一内容不要开新号"。

    自动重合度只认字面，同义改写判不出来，所以这里用低阈值做提示，
    真正的判定留给主持者（rules/decision.md「一个内容一条裁决」）。
    """
    from framework.engine import content_overlaps
    from framework.state import load_state
    hits = [row for row in content_overlaps(load_state(root_of(), sys_name), content,
                                            threshold=0.2, limit=4)
            if row[1] != exclude]
    if not hits:
        return
    print("相近条目（同一内容请用 override 改写在原编号下，不要开新号）："
          + "；".join("%s 相近 %.0f%%" % (did, score * 100.0) for score, did, _ in hits))


def _filter_desc(**parts):
    """list 过滤条件的可读描述（text 视图标题下的一行）。"""
    used = []
    for key, value in parts.items():
        if value in (None, "", 0):
            continue
        used.append("%s=%s" % (key, value))
    return "；".join(used)


def _stop_int(text):
    """problem list 的 --stop 过滤：停点号转 int；空串给 None。"""
    text = str(text or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise EngineError("--stop 过滤要停点号（整数），收到 %r" % text)


def cmd_decision(args):
    try:
        from framework.state import load_state
        if args.action == "commit":
            if not args.kind:
                raise EngineError("decision commit 必须带 --kind，取 方向 / 数值 / 记录 之一")
            if args.kind == "记录" and not args.content.strip():
                raise EngineError("记录类入库必须带 --content 写明裁决正文")
            if args.kind in ("方向", "数值") and not (args.from_problem or args.source):
                raise EngineError(
                    "方向/数值类入库必须有点选来源：--from <待裁决问题号> --pick <选项>"
                    "（开发者点选），或 marks --harvest（开发者亲笔）")
            did = commit_decision(
                root_of(), args.sys, content=args.content, kind=args.kind,
                from_problem=args.from_problem, pick=args.pick or "",
                source=args.source or "", stop=args.stop or None, note=args.note or "",
                force=args.force, reason=args.reason or "",
            )
            print(did)
            hint = args.content
            if args.kind == "记录":
                # 记录类入库不要求来源，但正文疑似方向/数值类时提示（防夹带）。
                from framework.engine import record_kind_hints
                hints = record_kind_hints(root_of(), args.sys, hint)
                if hints:
                    print("提示：疑似方向或数值类（%s）——记录类不承载变更、"
                          "不级联，实质变更请走 problem add + commit --from/--pick"
                          % "；".join(hints))
            _related_hint(args.sys, hint, exclude=did)
        elif args.action == "list":
            from framework.engine import query
            state = load_state(root_of(), args.sys)
            pending, deferred = query.problem_sections(state)
            if getattr(args, "json", False):
                # --json 口径与 status --json 一致：stdout 只有一份 JSON，
                # 错误走 stderr、退出码非 0。
                if args.id:
                    payload = query.decision_detail(state, args.id)
                else:
                    rows = query.query_decisions(
                        state, kind=args.kind, stop=args.stop, stage=args.stage,
                        grep=args.grep, threshold=args.threshold, limit=args.limit)
                    if args.open:
                        rows = []
                    payload = query.decision_list_payload(state, rows, pending, deferred)
                print(json.dumps(payload, ensure_ascii=False))
            elif args.id:
                # 单条全档：正文、来源、修订历史与关闭问题。
                print(query.render_decision_detail(query.decision_detail(state, args.id)))
            elif args.open:
                print(query.render_decision_list([], pending, deferred,
                                                 show_decisions=False))
            else:
                rows = query.query_decisions(
                    state, kind=args.kind, stop=args.stop, stage=args.stage,
                    grep=args.grep, threshold=args.threshold, limit=args.limit)
                print(query.render_decision_list(
                    rows, pending, deferred,
                    filter_desc=_filter_desc(kind=args.kind, stop=args.stop,
                                             stage=args.stage, grep=args.grep,
                                             limit=args.limit)))
        elif args.action == "similar":
            # 入库前的只读比对：给定正文按重合度排名，判"是不是同一条"。
            from framework.engine import query
            if not args.content.strip():
                raise EngineError("decision similar 要 --content 给出要比对的正文")
            state = load_state(root_of(), args.sys)
            rows = query.similar_decisions(state, args.content,
                                           threshold=args.threshold,
                                           limit=args.limit or 8)
            if args.json:
                print(json.dumps(query.similar_payload(state, args.content, rows),
                                 ensure_ascii=False))
            else:
                print(query.render_similar(rows))
        elif args.action == "withdraw":
            from framework.engine import withdraw_decision
            print(withdraw_decision(root_of(), args.sys, args.id))
        elif args.action == "override":
            from framework.engine import override_decision
            print(override_decision(
                root_of(), args.sys, args.id, args.content, args.note or "",
                kind=args.kind or "",
            ))
        else:
            raise EngineError("尚未实现的裁决动作 %s" % args.action)
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


# `run --detach` 派生的后台进程入口。放在顶层选项区之外、也不写进 argparse：
# 父进程用它启动作业，用户只需要 `run <能力>` / `run wait` / `run jobs`。
HIDDEN_EXECUTE_JOB = "--_execute-job"


def _request_from_args(args):
    return {
        "scenario": args.scenario,
        "sys": args.sys,
        "module": args.module,
        "wave": args.wave,
        "coverage": args.coverage,
        "dry_run": args.dry_run,
        "compile_only": args.compile_only,
        "rtl": args.rtl,
        "lib": args.lib,
        "corner": args.corner,
        "seed": getattr(args, "seed", "") or "",
        "tc": getattr(args, "tc", "") or "",
        "wall": getattr(args, "wall", 3600) or 3600,
        "seeds": [s for s in (getattr(args, "seeds", "") or "").split(",") if s],
        "defines": list(getattr(args, "define", []) or []),
        "timeout_us": getattr(args, "timeout_us", "") or "",
        "no_sync": getattr(args, "no_sync", False),
        "no_record": bool(getattr(args, "no_record", False)),
        "top": getattr(args, "top", "") or "",
        "rtl_dir": getattr(args, "rtl_dir", "") or "",
        "sdc": getattr(args, "sdc", "") or "",
        "netlist": getattr(args, "netlist", "") or "",
        "gold": getattr(args, "gold", "") or "",
    }


def _run_result(capability, req):
    """跑完一次运行（同步与后台共用的入口）：返回结果 dict，不打印不记录。"""
    if capability == "sim":
        return run_sim(req)
    return run_other(capability, req)


def _emit_result(capability, result, sys_name, record=True):
    """打印一次运行的结论并按需记运行记录；返回 (退出码, 运行记录号)。

    同步运行与后台作业共用这一段，`run wait` 的结论才与同步运行一致；
    运行记录只在这里写一次，`wait` 只读作业文件、不重复记录。
    """
    print(result["summary"])
    print("status: %s" % result["status"])
    if result.get("status") == "unavailable":
        # 剖面没有这项能力不是通过：退出码单独一档，按规则与裁决豁免路径处理。
        print("当前剖面未提供 %s，走规则与裁决豁免路径" % capability)
    if result.get("status") == "dry_run":
        return 0, ""
    record_id = ""
    if sys_name and record:
        record_id = record_run(root_of(), sys_name, result)
        print("已记入运行记录：%s" % record_id)
    elif not sys_name:
        # 缺 --sys 时静默不记录，等于把刚跑出来的证据丢掉，闸门随后只会说"缺运行记录"。
        print("提示：没有 --sys，本次运行未记入运行记录；要进闸门请加 --sys <子系统>",
              file=sys.stderr)
    if result.get("status") == "unavailable":
        return 3, record_id
    return (0 if result["status"] == "pass" else 1), record_id


def _detach_run(capability, req):
    """写作业文件并起后台进程，父进程立即返回作业号。"""
    root = root_of()
    sys_name = req.get("sys") or ""
    path, job = create_job(root, sys_name, capability, req, wall=req.get("wall") or 0)
    argv = [sys.executable, os.path.abspath(__file__), HIDDEN_EXECUTE_JOB, path]
    try:
        out_path = os.path.join(root, job["output"])
        with open(out_path, "w", encoding="utf-8") as out:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out,
                             stderr=subprocess.STDOUT, cwd=root,
                             env=os.environ.copy())
    except OSError as exc:
        update_job(path, status="failed", finished_at=job_now(),
                   exit_code=1, error="后台进程启动失败：%s" % exc)
        print("后台进程启动失败：%s" % exc, file=sys.stderr)
        return 1
    print("后台作业已启动：%s" % job["id"])
    print("作业文件：%s" % job["job_file"])
    print("等待结果：python3 script/framework.py run wait --job %s" % job["id"])
    return 0


def _execute_job(job_file):
    """后台入口：完整跑一遍运行流程（含 record_run），结束回写作业文件。"""
    try:
        job = read_job(job_file)
    except (OSError, ValueError) as exc:
        print("读不到作业文件 %s：%s" % (job_file, exc), file=sys.stderr)
        return 2
    capability = job.get("capability") or ""
    req = dict(job.get("request") or {})
    try:
        update_job(job_file, status="running", pid=os.getpid(), started_at=job_now())
        result = _run_result(capability, req)
        code, record_id = _emit_result(capability, result, req.get("sys") or "",
                                       record=not req.get("no_record"))
        # 运行流程跑完但结论是 fail/error 时也记 failed：作业文件直接能看出这次没成。
        status = "done" if code in (0, 3) else "failed"
        update_job(job_file, status=status, finished_at=job_now(), exit_code=code,
                   record=record_id,
                   result={"capability": result.get("capability") or capability,
                           "status": result.get("status") or "error",
                           "summary": result.get("summary") or ""})
        return code
    except Exception as exc:  # 后台进程的兜底：异常也要在作业文件里留状态
        message = ("%s: %s" % (type(exc).__name__, exc)) if str(exc) else type(exc).__name__
        try:
            update_job(job_file, status="failed", finished_at=job_now(),
                       exit_code=1, error=message)
        except (OSError,):
            pass
        print("作业执行失败：%s" % message, file=sys.stderr)
        return 1


def _cmd_run_wait(args):
    """`run wait --job <id> [--timeout s]`：等到作业结束，打印与同步运行一致的结论。"""
    job_id = (getattr(args, "job", "") or "").strip()
    if not job_id:
        print("run wait 需要 --job <作业号>", file=sys.stderr)
        return 2
    root = root_of()
    path = find_job(root, job_id, args.sys or "")
    if not path:
        print("找不到作业 %s（用 run jobs 看现有作业）" % job_id, file=sys.stderr)
        return 1
    deadline = 0.0
    if getattr(args, "timeout", 0) and args.timeout > 0:
        deadline = time.monotonic() + float(args.timeout)
    while True:
        try:
            job = read_job(path)
        except (OSError, ValueError) as exc:
            print("读不到作业文件：%s" % exc, file=sys.stderr)
            return 1
        if job.get("status") in JOB_TERMINAL:
            break
        if deadline and time.monotonic() >= deadline:
            print("等待超时：作业 %s 仍在运行（状态 %s）；继续等用 run wait --job %s"
                  % (job_id, job.get("status") or "", job_id), file=sys.stderr)
            return 124
        time.sleep(0.1)
    result = job.get("result") or {}
    if result:
        print(result.get("summary") or "")
        print("status: %s" % (result.get("status") or "error"))
        if result.get("status") == "unavailable":
            print("当前剖面未提供 %s，走规则与裁决豁免路径" % (job.get("capability") or ""))
        if job.get("record"):
            print("已记入运行记录：%s" % job["record"])
        elif not job.get("sys"):
            print("提示：没有 --sys，本次运行未记入运行记录；要进闸门请加 --sys <子系统>",
                  file=sys.stderr)
        code = job.get("exit_code")
        return int(code) if code is not None else 0
    print("作业失败：%s" % (job.get("error") or "后台进程异常退出"), file=sys.stderr)
    return 1


def _cmd_run_jobs(args):
    """`run jobs [--sys <子系统>]`：列出作业状态摘要（新→旧）。"""
    jobs = list_jobs(root_of(), args.sys or "")
    if not jobs:
        print("（没有作业）")
        return 0
    rows = []
    for job in jobs:
        result = job.get("result") or {}
        rows.append([job.get("id", ""), job.get("capability", ""), job.get("status", ""),
                     job.get("started_at") or job.get("created_at") or "",
                     result.get("summary") or job.get("error") or ""])
    print("\n".join(_table(["作业", "能力", "状态", "开始时间", "结论"], rows)))
    return 0


def cmd_run(args):
    if args.target == "wait":
        return _cmd_run_wait(args)
    if args.target == "jobs":
        return _cmd_run_jobs(args)
    capability = args.target
    req = _request_from_args(args)
    if getattr(args, "detach", False):
        if not args.sys:
            print("run --detach 需要 --sys：作业文件落在 <子系统>/work/jobs/", file=sys.stderr)
            return 2
        if args.dry_run:
            print("run --detach 不与 --dry-run 同用：dry-run 立即出结论，不必后台执行",
                  file=sys.stderr)
            return 2
        return _detach_run(capability, req)
    result = _run_result(capability, req)
    code, _record = _emit_result(capability, result, args.sys,
                                 record=not getattr(args, "no_record", False))
    return code


def cmd_new_doc(args):
    from framework.flow import load, product_path
    from framework.gates.docs import PLACEHOLDER_TEXT, expected_chapters
    from framework.paths import project_root
    kind_line = "模块类型：group\n\n" if args.kind == "group" else ""
    if args.kind == "leaf":
        kind_line = "模块类型：leaf\n\n"
    stop = load()["by_id"].get(int(args.stop))
    if stop is None:
        print("没有停点 %s（停点号见 framework/flow_model.yaml）" % args.stop, file=sys.stderr)
        return 1
    # 停点 → 产物路径只读模型的 product: 字段；模块规格书按 --module 换文件名。
    rel = product_path(stop, args.sys)
    if rel.endswith("/"):
        folder = rel[:-1]
        if folder != "spec_doc":
            print("new-doc 只用于文档产物：停点 %d 的产物是目录 %s"
                  % (args.stop, rel), file=sys.stderr)
            return 1
        rel = os.path.join(folder, "%s_spec.md" % (args.module or args.sys))
    elif args.module and os.path.dirname(rel) == "spec_doc":
        rel = os.path.join("spec_doc", "%s_spec.md" % args.module)
    if not rel.endswith(".md"):
        print("new-doc 只用于 Markdown 文档产物：停点 %d 的产物是 %s"
              % (args.stop, rel), file=sys.stderr)
        return 1
    chapters = expected_chapters(rel, args.stop, kind_line, args.sys)
    lines = ["# %s" % os.path.basename(rel)[:-3], "", PLACEHOLDER_TEXT, ""]
    if kind_line:
        lines.append(kind_line.strip())
        lines.append("")
    for index, name in enumerate(chapters, 2):
        lines.extend(["## %d. %s" % (index, name), "", PLACEHOLDER_TEXT, ""])
    path = os.path.join(project_root(), args.sys, rel)
    # 不许无提示覆盖已写好的产物。已有实质内容（非空白）时拒绝，
    # 除非 --force；--force 先把原文件备份到
    # <sys>/.new_doc_backups/<文件名>.<时间戳>.bak，再写新模板。
    if os.path.exists(path):
        with open(path, "rb") as fh:
            existing = fh.read()
        if existing.strip():
            if not getattr(args, "force", False):
                print("已存在：%s" % path, file=sys.stderr)
                print("拒绝覆盖（文件保持原样）；确需重写请加 --force，"
                      "会先备份到 %s/.new_doc_backups/"
                      % os.path.join(project_root(), args.sys), file=sys.stderr)
                return 1
            import time
            backup_dir = os.path.join(project_root(), args.sys, ".new_doc_backups")
            os.makedirs(backup_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = os.path.join(backup_dir, "%s.%s.bak" % (os.path.basename(path), stamp))
            serial = 1
            while os.path.exists(backup):
                backup = os.path.join(
                    backup_dir,
                    "%s.%s-%d.bak" % (os.path.basename(path), stamp, serial))
                serial += 1
            with open(backup, "wb") as fh:
                fh.write(existing)
            print("原文件已备份：%s" % backup)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(rel)
    return 0


def cmd_hosts(_args):
    paths = render()
    print("已写入 %s" % ", ".join(paths))
    return 0


def cmd_problem(args):
    from framework.engine import add_problem, close_problem, problem_defer
    from framework.state import load_state
    try:
        if args.action == "add":
            if not args.kind:
                print("problem add 必须带 --kind（阻断 / 待裁决）：问题类型只有两种，"
                      "阻断挡流程、待裁决等开发者点选", file=sys.stderr)
                return 1
            if not str(args.stop).strip():
                print("problem add 必须带 --stop，写明所属停点（见 framework/flow_model.yaml）",
                      file=sys.stderr)
                return 1
            print(add_problem(root_of(), args.sys, args.kind, args.stop, args.text, args.source,
                              options=args.options or "", blocks=args.blocks or ""))
        elif args.action == "defer":
            # 推迟不是裁决：问题保持打开，条件满足后 tick/status 重新列进需要开发者。
            print(problem_defer(root_of(), args.sys, args.id, args.until,
                                reason=args.reason or ""))
        elif args.action == "close":
            # 关闭靠证据（R号|审查记录|D号），不要终端（--confirm 已删）。
            print(close_problem(root_of(), args.sys, args.id, evidence=args.evidence or ""))
        else:
            from framework.engine import query
            if args.open and args.all:
                raise EngineError("--open 与 --all 不要同给：缺省即只看打开的问题")
            state = load_state(root_of(), args.sys)
            # 缺省只看打开的问题；--all 连已关闭一起列（问题清单的事实源）。
            rows = query.query_problems(state, open_only=not args.all, kind=args.kind,
                                        stop=_stop_int(args.stop), grep=args.grep,
                                        limit=args.limit)
            if args.json:
                print(json.dumps(query.problems_payload(state, rows), ensure_ascii=False))
            else:
                print(query.render_problems(rows))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_item(args):
    # 调试/综合优化事项。开、改、删不要确认语句；调试事项带侧别；
    # item end 即闭合；L2/L3 的人工背书在裁决入库上。
    from framework.engine import item_end, item_open, item_set
    from framework.state import load_state
    try:
        if args.action == "open":
            print(item_open(root_of(), args.sys, args.kind, args.text, side=args.side or ""))
        elif args.action == "set":
            print(item_set(root_of(), args.sys, args.id, args.text,
                           evidence=list(getattr(args, "evidence", []) or [])))
        elif args.action == "end":
            print(item_end(root_of(), args.sys, args.id, args.level,
                           sync=args.sync or "", decision=args.decision or ""))
        else:
            from framework.engine import query
            state = load_state(root_of(), args.sys)
            items = query.items_view(state)
            if args.json:
                print(json.dumps(query.items_payload(state, items), ensure_ascii=False))
            else:
                print(query.render_items(items))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_events(args):
    """事件日志查询：events.jsonl 的过滤视图，只读。"""
    from framework.engine import query
    try:
        rows = query.query_events(query.load_events(root_of(), args.sys),
                                  grep=args.grep or "", limit=args.limit)
        if args.json:
            print(json.dumps(query.events_payload(args.sys, rows), ensure_ascii=False))
        else:
            print(query.render_events(rows))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_handoff(args):
    from framework.engine import set_handoff
    try:
        print(set_handoff(root_of(), args.sys, args.text))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_summary(args):
    from framework.engine import add_summary
    try:
        print(add_summary(root_of(), args.sys, args.text))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_review(args):
    stop = args.stop
    if args.action != "record":
        if not stop:
            print("review 要带 --stop <停点号>（或 review record 登记审查记录）", file=sys.stderr)
            return 1
        from framework.review_pack import review_text
        print(review_text(root_of(), args.sys, stop))
        return 0
    from framework.engine import review_record
    if not (args.report or "").strip():
        print("review record 要 --report report/<文件>.md（必填）：必须存在且晚于产物最后一次修改",
              file=sys.stderr)
        return 1
    if not (args.author or "").strip() or not (args.reviewer or "").strip():
        print("review record 要 --author <派工号> --reviewer <派工号>（两者必须不同）"
              "与 --report report/<文件>.md（必填，报告要晚于产物最后一次修改）",
              file=sys.stderr)
        return 1
    try:
        print(review_record(root_of(), args.sys, stop, module=args.module,
                            author=args.author, reviewer=args.reviewer,
                            findings=args.findings, blocking=args.blocking,
                            report=args.report or ""))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_tick(args):
    """两张清单 + 自动完成 + 复核恢复。只读 + 写事件，退出码恒 0。"""
    try:
        if getattr(args, "json", False):
            # 与普通 tick 同一事务：先推进到不动点，再把结果结构打成一份 JSON。
            from framework.engine import tick_data
            print(json.dumps(tick_data(root_of(), args.sys), ensure_ascii=False))
        else:
            from framework.engine import tick_report
            print(tick_report(root_of(), args.sys))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_trace(args):
    """需求追溯矩阵：默认打 Markdown，--json 输出机器可读结构。"""
    from framework.state import load_state, sys_dir
    from framework.trace import TraceMatrix
    root = root_of()
    try:
        state = load_state(root, args.sys)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    matrix = TraceMatrix(sys_dir(root, args.sys), state)
    if args.json:
        print(json.dumps(matrix.as_dict(), ensure_ascii=False))
    else:
        text = matrix.markdown()
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_milestone(args):
    """里程碑审阅包与确认/拒绝（M3 要交互终端照抄）。"""
    from framework.engine import milestone_confirm, milestone_reject
    from framework.review_pack import milestone_report
    try:
        if args.action == "show":
            text = milestone_report(root_of(), args.sys, args.id)
            path = os.path.join(root_of(), args.sys, "milestone_%s.md" % args.id)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(text, end="" if text.endswith("\n") else "\n")
            print("审阅包已生成：%s" % path)
        elif args.action == "confirm":
            result = milestone_confirm(root_of(), args.sys, args.id,
                                       confirm=args.confirm or "", pick=args.pick or "")
            # 审阅包若已落盘，确认后重渲染，避免包内嵌的签核记录仍写“未确认”。
            path = os.path.join(root_of(), args.sys, "milestone_%s.md" % args.id)
            if os.path.isfile(path):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(milestone_report(root_of(), args.sys, args.id))
            print(result)
        else:
            print(milestone_reject(root_of(), args.sys, args.id, args.reason,
                                   stop=args.stop or None))
    except (EngineError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args):
    if getattr(args, "mcp", False):
        # doctor --mcp 检查远端 eda-mcp 安装与工具；`dbg doctor` 同口径。
        from framework.doctor import run_mcp
        code, text = run_mcp()
        print(text)
        return code
    from framework.doctor import run_doctor
    code, text = run_doctor(ssh=args.ssh)
    print(text)
    return code


def cmd_dbg(args):
    """`dbg <sys> ...` / `dbg doctor` 的 CLI 入口。

    转发给 dbg.run_dbg(root, name, argv)，打印返回文本并按其退出码退出
    （0 成功 / 2 用法与校验错误 / 3 远端版本不一致）。
    run 显式传 subprocess.run：extract 与 npi open 里的 rsync 步骤直接调用
    注入的 run，run_dbg 缺省 None 会在 CLI 路径上炸，这里补齐（dbg.py 接口不动）。
    """
    import subprocess as _sp
    from framework.dbg import run_dbg
    argv = list(args.argv or [])
    name = ""
    if argv and argv[0] != "doctor":
        name, argv = argv[0], argv[1:]
    text, code = run_dbg(root_of(), name, argv, run=_sp.run)
    print(text)
    return code


def cmd_eda_mcp(args):
    """`eda-mcp install` 的 CLI 入口——同步镜像、安装到 EDA 主机并写 SOURCE_DIGEST。"""
    from framework.eda_mcp_deploy import install
    text, code = install(sync=not args.no_sync)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return code


def cmd_tb_gen(args):
    from framework.state import sys_dir
    from framework.tbgen import port_check
    diffs, parser, errors = port_check(sys_dir(root_of(), args.sys), args.sys, args.dut)
    if errors:
        for item in errors:
            print("端口校验跳过（%s）：%s" % (parser or "解析器不可用", item))
    elif diffs:
        for item in diffs:
            print("端口不一致：%s" % item)
        print("tb-gen 已拦截：RTL 端口与交付 IR 不一致；先回修规格（行 4/5）并重新生成 IR，"
              "或确认 RTL 改动已同步规格。解析器：%s" % parser)
        return 1
    else:
        print("端口校验通过（%s）：%s" % (parser, args.dut))
    for line in generate(sys_dir(root_of(), args.sys), args.sys, args.dut, force=args.force):
        print(line)
    # 行 9 平台不再手工登记——平台清单由 testbench/ 推导、状态由用例核对推导
    # （gates.tc.platform_state），刚生成的骨架自然判"骨架"（T6 阻断）。
    return 0


def cmd_waive(args):
    from framework.engine import add_waiver
    try:
        # 豁免自动，只要裁决引用合法（忽略型 --confirm 已删）。
        print(add_waiver(root_of(), args.sys, args.rule, args.where, args.decision))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_marks(args):
    from framework.marks import harvest_marks, list_marks, marks_cap, marks_plan
    from framework.state import load_state
    if args.harvest:
        if not args.kind:
            print("marks --harvest 必须带 --kind（方向 / 数值 / 记录）："
                  "走查标记按原文直接入库，类别由主持者判定", file=sys.stderr)
            return 1
        if not args.stop:
            print("marks --harvest 必须带 --stop：它决定 D 号的阶段号与级联起点",
                  file=sys.stderr)
            return 1
        fresh, known = marks_plan(root_of(), args.sys)
        try:
            cap = marks_cap(load_state(root_of(), args.sys))
            done = harvest_marks(root_of(), args.sys, args.kind, args.stop)
        except EngineError as exc:
            print(exc, file=sys.stderr)
            return 1
        for did, line in done:
            print("%s ← %s" % (did, line))
        print("已收割 %d 条，已收割过 %d 条%s"
              % (len(done), len(known), ("，上限 %d 条" % cap) if cap else ""))
        for line in fresh[len(done):]:
            print("未收割（超过上限）：%s" % line)
    else:
        for line in list_marks(root_of(), args.sys):
            print(line)
    return 0


def cmd_gate(args):
    import json
    from framework.gates.run import run_gates
    from framework.state import load_state
    try:
        state = load_state(root_of(), args.sys)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    # 缺省按"当前停点"检查：优先取进行中/已送审的最小停点号，
    # 否则取已完成的最大停点号。章节模型随停点渐进（chapters.yaml 的
    # stop_min/stop_max），裸跑 gate 不再默认按行 6 的完整模型报未来缺章。
    stop_id = args.stop
    if stop_id is None:
        active = [int(row["id"]) for row in state["stops"]
                  if row["state"] in ("进行中", "已送审")]
        done = [int(row["id"]) for row in state["stops"]
                if row["state"] == "完成（审核通过）"]
        stop_id = min(active) if active else (max(done) if done else 1)
    findings = run_gates(root_of(), args.sys, stop_id, state)
    blocking = [item for item in findings if item.get("level") != "hint"]
    if args.json:
        print(json.dumps({"stop": stop_id, "fail": len(blocking), "findings": findings}, ensure_ascii=False, indent=2))
        return 0 if not blocking else 1
    if not blocking:
        print("闸门通过（按停点 %d 检查）" % stop_id)
        return 0
    for item in findings:
        print("[%s] %s %s" % (item.get("rule", "?"), item.get("where", ""), item.get("detail", "")))
    print("失败项 %d（按停点 %d 检查）" % (len(blocking), stop_id))
    return 1


def cmd_module(args):
    try:
        print(set_module(root_of(), args.sys, args.row, args.name, args.state))
    except EngineError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_golden(args):
    """参考数据登记与查看。行 10 闸门按它判"未登记/需重新生成"。"""
    from framework.engine import register_golden
    from framework.state import golden_records, load_state
    try:
        if args.action == "register":
            gid = register_golden(root_of(), args.sys, args.data, args.gen, args.inputs)
            print("%s（%s ← %s；输入 %s）"
                  % (gid, args.data, args.gen, "、".join(args.inputs) or "（无）"))
            return 0
        records = golden_records(load_state(root_of(), args.sys))
        if not records:
            print("（没有登记的参考数据）")
            return 0
        for row in records:
            print("%s %s ← %s；输入 %s；登记 %s；摘要 %s"
                  % (row["id"], row["data"], row["gen"], "、".join(row["inputs"]),
                     row["time"], str(row["digest"])[:12]))
    except (EngineError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_lock(args):
    """写权限台账：主持者据此协调多成员的写域；成员写前自查。

    协调机制，不是强制机制——宿主的文件工具不会被脚本拦住，
    成员按 `rules/team.md` 的口径在动手前 `lock check`。
    """
    from framework.locks import (
        LockError, cancel, check, grant, listing, renew, request, revoke, waiting,
    )
    root = root_of()
    try:
        if args.action == "grant":
            row = grant(root, args.to, args.task, args.paths, args.ttl, args.note)
            print("已授予 %s（任务：%s）：%s；限时 %g 分钟"
                  % (row["member"], "、".join(row["tasks"]),
                     "、".join(row["paths"]), row["ttl_minutes"]))
        elif args.action == "renew":
            row = renew(root, args.to, args.ttl)
            print("已续期 %s：%s；限时 %g 分钟"
                  % (row["member"], "、".join(row["paths"]), row["ttl_minutes"]))
        elif args.action == "revoke":
            revoke(root, args.to, args.path)
            print("已撤销 %s 的写权限%s"
                  % (args.to, ("：" + args.path) if args.path else ""))
        elif args.action == "request":
            row = request(root, args.to, args.task, args.paths, args.note)
            print("已排队 %s（任务：%s）：%s；等主持者授予（lock list 看队列与阻塞）"
                  % (row["member"], "、".join(row["tasks"]), "、".join(row["paths"])))
        elif args.action == "cancel":
            cancel(root, args.to)
            print("已取消 %s 的排队" % args.to)
        elif args.action == "check":
            allowed, why = check(root, args.to, args.path)
            print(("已授予：" if allowed else "未授予：") + why)
            return 0 if allowed else 1
        else:
            queue, dropped = waiting(root)
            rows, more = listing(root)
            dropped = list(dropped) + list(more)
            if dropped:
                print("（已自动释放 %d 条超时条目：%s）"
                      % (len(dropped), "、".join(str(item.get("member")) for item in dropped)))
            if queue:
                print("等待队列（按申请先后，先到的先授）：")
                for index, row in enumerate(queue, 1):
                    blocked = ("等 " + "、".join(row["blocked_by"])) if row["blocked_by"] \
                        else "可立即授予"
                    print("  %d. %s（任务：%s）→ %s；%s%s"
                          % (index, row["member"], "、".join(row["tasks"]),
                             "、".join(row["paths"]), blocked,
                             ("；备注：" + row["note"]) if row["note"] else ""))
            else:
                print("（等待队列为空）")
            if not rows:
                print("（当前没有有效写权限）")
                return 0
            for row in rows:
                print("%s（任务：%s）→ %s；剩余 %.0f 分钟%s"
                      % (row["member"], "、".join(row["tasks"]), "、".join(row["paths"]),
                         row["remaining_minutes"],
                         ("；备注：" + row["note"]) if row["note"] else ""))
    except (LockError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_digest(args):
    from framework.state import sys_dir
    try:
        print(dump(sys_dir(root_of(), args.sys), args.sys))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def selftest():
    """框架用例 + 并入的上游 eda-mcp 用例合并自检。

    上游测试只纳入 `toolchain/eda-mcp/tests/test_*.py`；`tests/integration/`
    需要真机（缺 `__init__.py`，`discover` 也不会误扫）。发现口径用
    `top_level_dir=tests_dir`（`tests/` 无 `__init__.py`，`-t .` 口径会
    ImportError），并把 `toolchain/eda-mcp` 与其 `src` 插进 `sys.path`
    供上游用例 `import eda_mcp`。
    """
    import unittest

    loader = unittest.defaultTestLoader
    suites = []
    start = os.path.join(_CODE_ROOT, "framework", "tests")
    suites.append(loader.discover(start, pattern="test_*.py", top_level_dir=_CODE_ROOT))

    up_root = os.path.join(_CODE_ROOT, "toolchain", "eda-mcp")
    up_tests = os.path.join(up_root, "tests")
    if os.path.isdir(up_tests):
        for path in (up_root, os.path.join(up_root, "src")):
            if path not in sys.path:
                sys.path.insert(0, path)
        suites.append(loader.discover(up_tests, pattern="test_*.py", top_level_dir=up_tests))

    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    if result.wasSuccessful():
        print("SELFTEST PASS")
        return 0
    print("SELFTEST FAIL")
    return 1



def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    # 隐藏入口：`run --detach` 起的后台进程走这里，不进 argparse（帮助里不暴露）。
    if argv and argv[0] == HIDDEN_EXECUTE_JOB:
        if len(argv) != 2:
            print("用法：%s <作业文件>" % HIDDEN_EXECUTE_JOB, file=sys.stderr)
            return 2
        return _execute_job(argv[1])
    parser = argparse.ArgumentParser(description="asic_design_agent")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("init")
    p.add_argument("sys")

    p = sub.add_parser("status")
    p.add_argument("sys", nargs="?", default="",
                   help="不带时列出仓库内全部子系统（名字 / 当前停点 / 是否等待开发者）")
    p.add_argument("--brief", action="store_true",
                   help="只打印开发者简报前两节（需要你做的 + 自上一个里程碑以来）")
    p.add_argument("--json", action="store_true",
                   help="只输出机器可读 JSON：单系统是当前位置 + 两张清单结构，"
                        "不带 sys 时是各子系统一行结构的数组；纯只读，"
                        "与 --brief 同时给出时以 --json 优先")

    p = sub.add_parser("state")
    p.add_argument("action", choices=("verify",))
    p.add_argument("sys")

    p = sub.add_parser("advance")
    p.add_argument("sys")
    p.add_argument("--stop", type=int, required=True)
    p.add_argument("--to", required=True,
                   help="只保留两种真用法：进行中（主动重做退回）与 "
                        "已送审 --allow-violation（带违例送审）；"
                        "启动/普通送审/完成已由 tick 自动处理（其余调用不改状态）")
    p.add_argument("--allow-violation", action="store_true",
                   help="带违例送审（红线）：必须配 --decision <D号>")
    p.add_argument("--decision", default="",
                   help="--allow-violation 指向的已入库方向/数值裁决号")

    p = sub.add_parser("decision")
    p.add_argument("sys")
    p.add_argument("action", choices=("commit", "list", "similar", "withdraw", "override"),
                   help="两步链路：problem add --kind 待裁决 --options …登记问题，"
                        "commit --from <问题号> --pick <选项> 点选即入库；"
                        "list/similar 是只读查询，similar 按重合度比对正文")
    p.add_argument("--content", default="")
    p.add_argument("--note", default="")
    p.add_argument("--kind", default="", choices=("", "方向", "数值", "记录"))
    p.add_argument("--from", dest="from_problem", default="",
                   help="待裁决问题号（如 I003）：方向/数值类的点选来源")
    p.add_argument("--pick", default="", help="开发者点选的候选（问题 --options 里的一个）")
    p.add_argument("--source", default="",
                   help="点选来源（marks --harvest 内部用 mark:<文件>:<行>）")
    p.add_argument("--stop", type=int, default=0,
                   help="停点：决定 D 号的阶段号与级联起点；缺省取问题的停点；"
                        "list 过滤：只看该停点入库的裁决")
    p.add_argument("--force", action="store_true")
    p.add_argument("--reason", default="")
    p.add_argument("--id", default="",
                   help="withdraw/override 的裁决号；list --id 给单条全档"
                        "（含修订历史与关闭问题）")
    p.add_argument("--stage", type=int, default=None,
                   help="list 过滤：阶段号（D 号前缀，见 flow_model.yaml 的 stages:）")
    p.add_argument("--grep", default="",
                   help="list 过滤：对正文/备注/编号/来源做子串或正则匹配；"
                        "未命中的再按重合度给相近条目（标进匹配列）")
    p.add_argument("--limit", type=int, default=None, help="最多列出多少条")
    p.add_argument("--threshold", type=float, default=0.25,
                   help="similar 的重合度阈值（缺省 0.25，入库守卫是 0.60）")
    p.add_argument("--open", action="store_true",
                   help="list：只看待裁决与已推迟问题，不列裁决")
    p.add_argument("--json", action="store_true",
                   help="list/similar：stdout 只输出一份 JSON（错误走 stderr）")

    p = sub.add_parser("fx")
    p.add_argument("op", choices=("mul", "cmul", "add", "sub", "lift", "shift", "lshr", "sat", "obs16", "pack", "addr", "round", "tol", "latency", "sac", "chain", "finish"))
    p.add_argument("a", nargs="?")
    p.add_argument("b", nargs="?")
    p.add_argument("--n", type=int, default=0)
    p.add_argument("--shrink", action="store_true")
    p.add_argument("--dest", default="")
    p.add_argument("--symmetric", action="store_true")
    p.add_argument("--widths", type=int, nargs="*")
    p.add_argument("--depths", type=int, nargs="*")
    p.add_argument("--bits", type=int, default=0)
    p.add_argument("--mode", default="trunc", choices=("trunc", "half_up", "even"))
    p.add_argument("--cycles", type=int, nargs="*")
    p.add_argument("--lsb", type=int, default=1)
    p.add_argument("--ref", default="")
    p.add_argument("--value", type=int, default=None)

    p = sub.add_parser("run", help="运行工具能力；长任务用 --detach 后台跑，"
                                   "run wait / run jobs 看作业")
    p.add_argument("target", metavar="<capability|wait|jobs>",
                   choices=("sim", "lint", "coverage", "synth", "sta", "cdc", "lec",
                            "wait", "jobs"),
                   help="能力取 sim/lint/coverage/synth/sta/cdc/lec；"
                        "wait 等后台作业、jobs 列作业摘要")
    p.add_argument("--scenario", default="sys", choices=("sys", "module", "pubip"))
    p.add_argument("--sys", default="")
    p.add_argument("--module", default="")
    p.add_argument("--wave", default="off", choices=("off", "fsdb", "vcd"))
    p.add_argument("--coverage", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--compile-only", action="store_true")
    p.add_argument("--rtl", default="")
    p.add_argument("--lib", default="default")
    p.add_argument("--corner", default="typical", choices=("typical", "slow", "fast"))
    p.add_argument("--seed", default="")
    p.add_argument("--tc", default="")
    p.add_argument("--wall", type=int, default=3600)
    p.add_argument("--seeds", default="")
    p.add_argument("--timeout-us", default="")
    p.add_argument("--define", action="append", default=[],
                   help="编译宏透传（可重复）：标识符或 标识符=值；值不含空白与 shell 元字符")
    p.add_argument("--no-sync", action="store_true")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--top", default="")
    p.add_argument("--rtl-dir", default="")
    p.add_argument("--sdc", default="")
    p.add_argument("--netlist", default="")
    p.add_argument("--gold", default="",
                   help="lec 用：黄金参考 RTL 文件（相对仓库根，模块名与候选一致）")
    p.add_argument("--detach", action="store_true",
                   help="后台执行：立即返回作业号，用 run wait --job <作业号> 取结论")
    p.add_argument("--job", default="", help="wait 用：作业号（--detach 打印的那个）")
    p.add_argument("--timeout", type=float, default=0,
                   help="wait 用：等待上限（秒），缺省一直等；超时退出码 124")

    sub.add_parser("hosts")
    p = sub.add_parser("new-doc")
    p.add_argument("sys")
    p.add_argument("--stop", type=int, required=True)
    p.add_argument("--module", default="")
    p.add_argument("--kind", default="", choices=("", "leaf", "group"))
    p.add_argument("--force", action="store_true",
                   help="目标已有内容时覆盖，覆盖前先备份原文件")
    p = sub.add_parser("problem")
    p.add_argument("sys")
    p.add_argument("action", choices=("add", "defer", "close", "list"))
    p.add_argument("--kind", default="", choices=("", "阻断", "待裁决"),
                   help="add 必填：阻断（挡流程）或待裁决（等开发者点选）")
    p.add_argument("--stop", default="")
    p.add_argument("--text", default="")
    p.add_argument("--source", default="")
    p.add_argument("--options", default="",
                   help="候选项，用 | 分隔（如 \"A|B|C\"）；带 options 的问题关闭须用裁决号")
    p.add_argument("--blocks", default="",
                   help="被阻塞的停点号，用 , 分隔（模块级阻塞暂不支持）；带 blocks 的问题关闭须用裁决号")
    p.add_argument("--id", default="")
    p.add_argument("--until", default="",
                   help="defer 用：推迟目标，停点号（模型里的停点）或里程碑号 M1|M2|M3")
    p.add_argument("--reason", default="", help="defer 用：推迟原因")
    p.add_argument("--evidence", default="",
                   help="关闭证据：R号 | review:<停点>[/模块] | D号；带 options/blocks 的问题只能用 D号；须晚于问题登记时间")
    p.add_argument("--open", action="store_true",
                   help="list：只看打开的问题（缺省即只看打开，显式写出以便读命令的人确认）")
    p.add_argument("--all", action="store_true",
                   help="list：连已关闭问题一起列（--open 与 --all 不要同给）")
    p.add_argument("--grep", default="",
                   help="list 过滤：对描述/编号/来源/候选做子串或正则匹配")
    p.add_argument("--limit", type=int, default=None, help="最多列出多少条")
    p.add_argument("--json", action="store_true",
                   help="list：stdout 只输出一份 JSON（错误走 stderr）")
    p = sub.add_parser("item")
    p.add_argument("sys")
    p.add_argument("action", choices=("open", "set", "end", "list"))
    p.add_argument("--kind", default="", choices=("", "调试", "综合优化"))
    p.add_argument("--side", default="", choices=("", "tb", "rtl", "spec"),
                   help="调试事项的退回侧：tb=测试平台、rtl=设计、spec=规格")
    p.add_argument("--text", default="")
    p.add_argument("--id", default="")
    p.add_argument("--evidence", action="append", default=[],
                   help="证据（路径或 R 号，可重复，累加去重）")
    p.add_argument("--level", default="", choices=("", "L0", "L1", "L2", "L3"),
                   help="收尾级别，缺省 L0")
    p.add_argument("--sync", default="",
                   help="收尾时写明回修了哪一章；只用于当次检查，不落库")
    p.add_argument("--decision", default="",
                   help="L2/L3 收尾必须指向已入库的结构或方案裁决（D 号）")
    p.add_argument("--json", action="store_true",
                   help="list：stdout 只输出一份 JSON（错误走 stderr）")

    p = sub.add_parser("events", help="事件日志查询（只读）：events <sys> "
                                      "[--grep <词|正则>] [--limit N] [--json]")
    p.add_argument("sys")
    p.add_argument("--grep", default="",
                   help="匹配动作/对象/证据/命令/操作者（子串或正则）")
    p.add_argument("--limit", type=int, default=None, help="取最后 N 条")
    p.add_argument("--json", action="store_true",
                   help="stdout 只输出一份 JSON（错误走 stderr）")
    p = sub.add_parser("handoff")
    p.add_argument("sys")
    p.add_argument("action", choices=("set",))
    p.add_argument("--text", required=True)
    p = sub.add_parser("summary")
    p.add_argument("sys")
    p.add_argument("action", choices=("add",))
    p.add_argument("--text", required=True)
    p = sub.add_parser("review")
    p.add_argument("sys")
    p.add_argument("action", nargs="?", default="", choices=("", "record"))
    p.add_argument("--stop", type=int, default=0)
    p.add_argument("--module", default="")
    p.add_argument("--author", default="", help="作者派工号（与审查者必须不同）")
    p.add_argument("--reviewer", default="", help="审查者派工号（与作者必须不同）")
    p.add_argument("--blocking", type=int, default=None,
                   help="可选：阻断发现数；给了就与报告发现表解析结果比对，不一致直接拒")
    p.add_argument("--findings", type=int, default=None,
                   help="可选：发现数；给了就与报告发现表数据行数比对，不一致直接拒")
    p.add_argument("--report", default="",
                   help="审查报告 report/<文件>.md（review record 必填）："
                        "必须存在且晚于产物最后一次修改")
    p = sub.add_parser("doctor")
    p.add_argument("--ssh", action="store_true")
    p.add_argument("--mcp", action="store_true",
                   help="检查远端 eda-mcp 安装与工具（SOURCE_DIGEST 一致性、"
                        "远端 doctor、workspace_root、fsdbq）；dbg doctor 同口径")
    p = sub.add_parser("dbg", help="EDA MCP 观察面封装：dbg <sys> waves|signals|wave|"
                                   "value|extract|npi ...；dbg doctor 同 doctor --mcp")
    p.add_argument("argv", nargs=argparse.REMAINDER, metavar="...",
                   help="<子系统名> 或 doctor 打头，其后参数原样转给 dbg（不写 state.json）")
    p = sub.add_parser("eda-mcp",
                       help="把 toolchain/eda-mcp 安装到 EDA 主机并写 SOURCE_DIGEST（版本比对用）")
    p.add_argument("action", choices=("install",))
    p.add_argument("--no-sync", action="store_true",
                   help="不先同步镜像，直接用当前镜像状态安装（缺省会先同步）")
    p = sub.add_parser("tick")
    p.add_argument("sys", help="两张清单（可推进的工作 / 需要开发者），每个工作包后跑一次")
    p.add_argument("--json", action="store_true",
                   help="只输出机器可读 JSON：动作摘要 + 两张清单结构；"
                        "与普通 tick 一样推进状态")
    p = sub.add_parser("trace",
                       help="需求追溯矩阵：输入要点→节点→模块→测试要点→用例→最近全量回归")
    p.add_argument("sys")
    p.add_argument("--json", action="store_true",
                   help="输出机器可读 JSON（矩阵行、统计、未覆盖清单、提示与最近全量回归）")
    p = sub.add_parser("milestone")
    p.add_argument("sys")
    p.add_argument("action", choices=("show", "confirm", "reject"))
    p.add_argument("--id", required=True, help="里程碑号 M1|M2|M3（milestones: 表里声明的）")
    p.add_argument("--confirm", default="",
                   help="M3（terminal: true）签核的确认原话，交互终端照抄")
    p.add_argument("--pick", default="",
                   help="M1/M2 的点选来源：必须 --pick 通过（来自主持者的点选工具）")
    p.add_argument("--reason", default="",
                   help="reject 必填：不通过的理由，转成问题登记")
    p.add_argument("--stop", type=int, default=0,
                   help="reject 指定退回的停点号（缺省取最早一个有问题的覆盖停点）")
    p = sub.add_parser("tb-gen")
    p.add_argument("sys")
    p.add_argument("--dut", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("waive")
    p.add_argument("sys")
    p.add_argument("action", choices=("add",))
    p.add_argument("--rule", required=True)
    p.add_argument("--where", required=True)
    p.add_argument("--decision", required=True,
                   help="引用的已入库方向/数值裁决号（点选入库）")
    p = sub.add_parser("marks")
    p.add_argument("sys")
    p.add_argument("--harvest", action="store_true",
                   help="按原文直接入库（来源记 mark 文件:行）；需 --kind 与 --stop")
    p.add_argument("--kind", default="", choices=("", "方向", "数值", "记录"))
    p.add_argument("--stop", type=int, default=0)
    p = sub.add_parser("gate")
    p.add_argument("sys")
    p.add_argument("--stop", type=int, default=None,
                   help="缺省按当前停点检查（进行中/已送审的最小停点，否则已完成的最大停点）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("module")
    p.add_argument("sys")
    from framework.flow import module_rows as _module_rows
    p.add_argument("--row", required=True, choices=tuple(_module_rows()),
                   help="模块行（由模型 review: 推导，当前 %s）" % " / ".join(_module_rows()))
    p.add_argument("--name", required=True)
    p.add_argument("--state", required=True, choices=("退回",),
                   help="只接受 退回：模块清单由文件推导、通过态由证据推导，"
                        "不再手工登记（要标通过请改证据：lint 记录、review record 或闸门）")

    p = sub.add_parser("digest")
    p.add_argument("sys")

    p = sub.add_parser("golden")
    p.add_argument("sys")
    p.add_argument("action", choices=("register", "list"),
                   help="register：登记参考数据的生成脚本与输入；list：看已登记记录")
    p.add_argument("--data", default="",
                   help="产物路径（testbench/<dut>/data/<文件>）")
    p.add_argument("--gen", default="", help="生成脚本路径")
    p.add_argument("--inputs", nargs="*", default=[], help="生成脚本读的输入路径")

    p = sub.add_parser("lock",
                       help="写权限台账（协调机制，非强制）：主持者授予/续期/撤销成员写哪些文件或目录")
    p.add_argument("action", choices=("grant", "list", "renew", "revoke", "check",
                                      "request", "cancel"),
                   help="grant 主持者授予；renew 续期；revoke 撤销（任务完成即撤销）；"
                        "check 写前自查（退出码 0 = 已授予）；request 成员排队申请；"
                        "cancel 撤销申请；list 看板（等待队列 + 已授予）")
    p.add_argument("--to", default="", help="成员标识（派工时用的名字）")
    p.add_argument("--task", default="", help="任务名：同一成员的路径并入同一条")
    p.add_argument("--paths", nargs="*", default=[],
                   help="文件路径，或以 / 结尾的目录；仓库里已存在的目录也按目录处理")
    p.add_argument("--path", default="", help="check / revoke 用的单个路径")
    p.add_argument("--ttl", type=float, default=None,
                   help="限时（分钟），缺省 30；超时自动释放，要继续写须由主持者续期")
    p.add_argument("--note", default="", help="备注（为什么授予，便于回溯）")

    sub.add_parser("selftest")

    args = parser.parse_args(argv)
    # problem add 的 --kind 是必填。同一个 problem parser 还承载 defer/close/list，
    # argparse 的 required=True 会连带要求它们也带 --kind，所以在这里按动作补校验
    # （parser.error 给标准的用法报错与退出码）。
    if args.cmd == "problem" and getattr(args, "action", "") == "add" \
            and not getattr(args, "kind", ""):
        parser.error("problem add 必须带 --kind（阻断 / 待裁决）：问题类型只有两种")
    dispatch = {
        "init": cmd_init,
        "status": cmd_status,
        "state": cmd_state,
        "advance": cmd_advance,
        "decision": cmd_decision,
        "fx": cmd_fx,
        "run": cmd_run,
        "hosts": cmd_hosts,
        "new-doc": cmd_new_doc,
        "problem": cmd_problem,
        "item": cmd_item,
        "events": cmd_events,
        "handoff": cmd_handoff,
        "summary": cmd_summary,
        "review": cmd_review,
        "doctor": cmd_doctor,
        "dbg": cmd_dbg,
        "eda-mcp": cmd_eda_mcp,
        "tick": cmd_tick,
        "trace": cmd_trace,
        "milestone": cmd_milestone,
        "tb-gen": cmd_tb_gen,
        "waive": cmd_waive,
        "marks": cmd_marks,
        "gate": cmd_gate,
        "module": cmd_module,
        "digest": cmd_digest,
        "golden": cmd_golden,
        "lock": cmd_lock,
        "selftest": lambda _args: selftest(),
    }
    handler = dispatch.get(args.cmd)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args)
    except StateEncodingError as exc:
        # 编码类错误在落盘前就抛出，这里只负责给一行可读报错。
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
