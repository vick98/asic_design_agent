# 作者：vick 邮箱：ykun@yk9811.com

"""当前剖面的仿真命令。远程执行由调用方决定是否真正发出。"""

import os

EXCLUDES = ("simv", "simv.daidir", "csrc", "*.vdb", "*.fsdb", "*.vcd", "ucli.key",
            "*.daidir", "*.so", "*.o", "*.a", "*.key", "*.log.bak")


def workdir(profile, scenario, sys_name, module):
    mirror = profile["mirror_root"]
    if scenario == "sys":
        return "%s/%s/work" % (mirror, sys_name)
    if scenario == "module":
        return "%s/%s/work/%s" % (mirror, sys_name, module)
    if scenario == "pubip":
        return "%s/pub_code/work/%s" % (mirror, module)
    raise ValueError("scenario 须为 sys、module 或 pubip")


def filelist_and_ydirs(scenario, sys_name, module):
    if scenario == "sys":
        return "../testbench/%s_tb.f" % sys_name, "-y ../rtl -y ../../pub_code"
    if scenario == "module":
        return "../../testbench/%s/%s_tb.f" % (module, module), "-y ../../rtl -y ../../../pub_code"
    return "../../testbench/%s/%s_tb.f" % (module, module), "-y ../.."


def vcs_line(profile, scenario, sys_name, module, wave="off", coverage=False, defines=()):
    fr, ydirs = filelist_and_ydirs(scenario, sys_name, module)
    vcs = profile.get("vcs") or {}
    common = [str(item) for item in (vcs.get("common") or [])]
    parts = [vcs.get("bin") or "sim"] + common + ["-f", fr, ydirs, vcs.get("libext", "+libext+.v+.sv")]
    if wave == "fsdb":
        parts.append(vcs.get("fsdb_extra", "+nolibcell"))
        parts.append("+define+DEBUG_CODE_EN +define+TB_DUMP_FSDB")
        parts.append(vcs.get("fsdb_debug", "-debug_access+all"))
        tab = vcs.get("fsdb_pli_tab", "")
        pli = vcs.get("fsdb_pli_a", "")
        if tab:
            parts.append("-P %s" % tab)
        if pli:
            parts.append(pli)
        parts.append(vcs.get("fsdb_ldflags", ""))
    elif wave == "vcd":
        parts.append("+define+DEBUG_CODE_EN")
    if coverage:
        # -cm_libs yv：-y 搜到的 DUT 也进覆盖率，否则 URG 只剩 TB 顶层。
        parts.append("+define+TB_COV_EN -cm line+cond+fsm+tgl -cm_libs yv")
    # 变体编译宏透传（framework 侧已校验为标识符[=值]，这里只管拼）。
    for item in defines or ():
        parts.append("+define+" + str(item))
    parts.append("-l compile.log")
    return " ".join(p for p in parts if p)


def baked_roots(profile, sys_name, module):
    """从本地 `.f` 里找出被烘死的绝对根路径。

    `.f` 由 tb_gen 生成，里面写的是生成当时的绝对路径；数据根一旦换成副本
    （验收副本、临时目录），只替换当前 local_root 会漏掉，编译在远端就找不到文件。
    这里按顶层目录名（pub_code、tb_common、子系统名、模块名）把真正的根摘出来。
    """
    local = (profile.get("local_root") or "").rstrip("/")
    tops = [name for name in ("pub_code", "tb_common", sys_name, module) if name]
    roots = set()
    for dirpath, dirnames, files in os.walk(local):
        dirnames[:] = [name for name in dirnames
                       if name not in (".git", "work", "dc", "pt", "lint", "__pycache__")]
        for name in files:
            if not name.endswith(".f"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    text = line.strip()
                    if text.startswith("+incdir+"):
                        text = text[len("+incdir+"):]
                    if not text.startswith("/"):
                        continue
                    parts = text.split("/")
                    for index, part in enumerate(parts):
                        if index >= 1 and part in tops:
                            roots.add("/".join(parts[:index]))
                            break
    roots.add(local)
    return sorted(roots)


def rewrite_line(profile, sys_name, module):
    """把 `.f` 里的绝对根路径改写成镜像根。"""
    mirror = profile["mirror_root"].rstrip("/")
    expressions = " ".join("-e 's|%s|%s|g'" % (root, mirror)
                           for root in baked_roots(profile, sys_name, module) if root)
    return ("find '%s' -name '*.f' -not -path '*/.git/*' -not -path '*/work/*' -print0 "
            "| xargs -0 -r sed -i %s" % (mirror, expressions))


def version_line(profile):
    """工具版本探针：脚本开头打一行 `TOOL_VERSION sim <版本串>`。

    版本串只取首行——`<bin> -ID` 后面还跟若干行 build 信息，多行会把日志撑乱，
    也让 expect_versions 的片段比对没法用。工具不在时这一行只剩标记，parse 会丢掉，
    运行记录里就没有这个字段（不阻断运行）。
    """
    binary = (profile.get("vcs") or {}).get("bin") or "vcs"
    return "echo \"TOOL_VERSION sim $(%s -ID 2>&1 | head -n 1)\"" % binary


def remote_script(profile, scenario, sys_name, module, wave="off", coverage=False,
                  compile_only=False, tc="", seed="", seeds=None, wall=3600, timeout_us="",
                  defines=()):
    work = workdir(profile, scenario, sys_name, module)
    compile_line = vcs_line(profile, scenario, sys_name, module, wave, coverage, defines)
    mirror = profile["mirror_root"]
    seed_list = [s for s in (seeds or []) if s] or ([seed] if seed else [""])
    # 日志名带 define，多个变体跑同一模块不互相覆盖（sim_PUBIP_ROUND_Z4.log）。
    tag = "_".join(str(d).replace("=", "_") for d in (defines or ()))
    lines = [
        "set -u",
        version_line(profile),
        rewrite_line(profile, sys_name, module),
        "mkdir -p '%s'" % work,
        "cd '%s'" % work,
        compile_line,
        "rc=$?",
        "if [ \"$rc\" -ne 0 ]; then echo COMPILE_FAIL; exit 2; fi",
    ]
    if not compile_only:
        lines.append("set +e")
        for one in seed_list:
            plus = []
            if tc:
                plus.append("+TC=%s" % tc)
            if one:
                plus.append("+SEED=%s" % one)
            if timeout_us:
                plus.append("+TB_TIMEOUT_US=%s" % timeout_us)
            if coverage:
                plus.append("-cm line+cond+fsm+tgl")
            base = "sim" + (("_" + tag) if tag else "")
            log_name = ("%s_seed%s.log" % (base, one)) if one else (base + ".log")
            lines.append("timeout %s ./simv %s > %s 2>&1" % (int(wall), " ".join(plus), log_name))
            lines.append("run_rc=$?")
            lines.append("echo \"SEED_RUN seed=%s rc=$run_rc log=%s\"" % (one or "0", log_name))
            lines.append("if [ \"$run_rc\" -eq 124 ]; then echo WALL_TIMEOUT seed=%s; fi" % (one or "0"))
            lines.append("if [ \"$run_rc\" -ne 0 ] && [ \"$run_rc\" -ne 124 ]; then echo SEED_CRASH seed=%s rc=$run_rc; fi" % (one or "0"))
            lines.append("echo \"SEED_RESULT seed=%s pass=$(grep -c 'RESULT.*PASS' %s || true) fail=$(grep -c 'RESULT.*FAIL' %s || true)\"" % (
                one or "0", log_name, log_name))
            lines.append("cat %s" % log_name)
        lines.append("set -e")
    return "\n".join(lines) + "\n"


def rsync_line(profile):
    host = profile["ssh_alias"]
    local = profile["local_root"].rstrip("/") + "/"
    mirror = profile["mirror_root"]
    excludes = " ".join("--exclude %s" % item for item in profile.get("sync_excludes") or [])
    return "rsync -avz --delete %s %s %s:%s/" % (excludes, local, host, mirror)


def pull_line(profile, sys_name, capability, scope=None):
    """把远端报告目录拉回本地。pubip 场景落 `pub_code/work/<module>/`，
    不写进 `<sys>/work/`（变体记录不顶掉子系统自己的仿真日志）。"""
    scope = scope or {}
    host = profile["ssh_alias"]
    mirror = profile["mirror_root"].rstrip("/")
    local = (profile.get("local_root") or "").rstrip("/")
    scenario = scope.get("scenario") or "sys"
    module = scope.get("module") or ""
    if capability in ("sim", "coverage"):
        remote = workdir(profile, scenario, sys_name, module)
        if scenario == "pubip" and module:
            dest = "%s/pub_code/work/%s" % (local, module)
        else:
            dest = "%s/%s/work" % (local, sys_name)
    else:
        remote = "%s/%s/%s" % (mirror, sys_name, {"lint": "lint"}.get(capability, "work"))
        dest = "%s/%s/work" % (local, sys_name)
    excludes = " ".join("--exclude '%s'" % item for item in EXCLUDES)
    return ("rsync -avz %s %s:%s/ %s/ || true"
            % (excludes, host, remote, dest))


def _tool_versions(text):
    """日志里的 `TOOL_VERSION <能力> <版本串>` 行。

    版本为空的探针行（工具不在 PATH 上）不记：宁缺勿错，运行记录里要么是实测版本、
    要么没有这个字段。同一能力出现多行时取最后一行。
    """
    import re
    return dict(re.findall(r"(?m)^TOOL_VERSION\s+(\S+)[ \t]+(.+?)[ \t]*$", text or ""))


def parse(capability, log_text, artifact_dir=""):
    import re
    text = log_text or ""
    if artifact_dir and os.path.isdir(artifact_dir):
        for name in sorted(os.listdir(artifact_dir)):
            path = os.path.join(artifact_dir, name)
            if os.path.isfile(path) and name.endswith(".log"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text += "\n" + fh.read()
    checks = {
        "result_pass": len(re.findall(r"RESULT\s*:\s*PASS", text)),
        "result_fail": len(re.findall(r"RESULT\s*:\s*FAIL", text)),
        "compile_error": 1 if ("COMPILE_FAIL" in text) else 0,
        "wall_timeout": 1 if ("WALL_TIMEOUT" in text) else 0,
        "seeds_total": 0,
        "seeds_failed": 0,
        "sim_crash": 0,
    }
    versions = _tool_versions(text)
    if versions:
        checks["tool_versions"] = versions
    # 逐个 seed 的 RESULT 与退出码，不再只在整段文本上计数。
    per_seed = {}
    for matched in re.finditer(r"SEED_RESULT seed=(\S+) pass=(\d+) fail=(\d+)", text):
        per_seed[matched.group(1)] = {"pass": int(matched.group(2)), "fail": int(matched.group(3))}
    if per_seed:
        checks["seed_results"] = per_seed
        checks["seeds_total"] = len(per_seed)
        checks["seeds_failed"] = sum(1 for item in per_seed.values() if item["fail"])
    # 本平台的 testbench 每个用例打一行 [CASE_END]，每个 seed 才汇总一行 RESULT。
    # “全量回归”要按真正跑过的用例数核对，不能只看 RESULT 行数（框架侧用这个数对 tc_all）。
    cases_run = len(re.findall(r"\[CASE_END\]", text))
    if cases_run:
        checks["cases_run"] = cases_run
    counted = re.search(r"SIM_COUNTS PASS=(\d+) FAIL=(\d+)", text)
    if counted:
        checks["seeds_total"] = max(checks["seeds_total"],
                                    int(counted.group(1)) + int(counted.group(2)))
        checks["seeds_failed"] = max(checks["seeds_failed"], int(counted.group(2)))
    crashes = re.findall(r"SEED_CRASH seed=(\S+) rc=(\d+)", text)
    if crashes:
        checks["sim_crash"] = 1
        checks["crashes"] = ["%s rc=%s" % (seed, rc) for seed, rc in crashes]
    if checks["result_fail"]:
        checks["seeds_failed"] = max(checks["seeds_failed"], checks["result_fail"])
    return checks
