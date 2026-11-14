# 作者：vick 邮箱：ykun@yk9811.com

"""按 toolchain/active 加载剖面 driver。框架不写死工具命令。"""

import contextlib
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import tempfile
import time

import yaml

from framework import diagnostics
from framework.paths import project_root

FOLDER = {"lint": "lint", "coverage": "work", "synth": "dc", "sta": "pt", "sim": "work",
          "lec": "work"}
KEEP_SUFFIX = (".rpt", ".log", ".v", ".sv", ".sdc", ".ddc", ".txt")
# --define 只接受标识符或 标识符=值；值不含空白与 shell 元字符——
# 远端脚本把这些宏拼进 bash -s，放开字符就是远端注入口。
DEFINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_+\-.:]*)?$")


def _validated_defines(req):
    defines = [str(item).strip() for item in (req.get("defines") or []) if str(item).strip()]
    for item in defines:
        if not DEFINE_RE.match(item):
            raise ValueError(
                "--define 只接受标识符或 标识符=值（值不含空白与 shell 元字符）：%r" % item)
    return defines


def active_name():
    with open(os.path.join(project_root(), "toolchain", "active"), encoding="utf-8") as fh:
        return fh.read().strip()


def load_profile():
    name = active_name()
    path = os.path.join(project_root(), "toolchain", "profiles", name, "profile.yaml")
    if not os.path.isfile(path):
        raise FileNotFoundError("剖面不存在：toolchain/profiles/%s（改 toolchain/active）" % name)
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data["id"] = data.get("id") or name
    data["_dir"] = os.path.dirname(path)
    if not data.get("local_root"):
        data["local_root"] = project_root()
    return data


def _driver(profile, filename):
    path = os.path.join(profile["_dir"], "drivers", filename)
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("profile_%s" % filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_state(sys_name):
    if not sys_name:
        return {}
    try:
        from framework.state import load_state
        return load_state(project_root(), sys_name)
    except FileNotFoundError as exc:
        del exc
        return {}


def judge(capability, checks, profile=None, sys_root="", state=None):
    """只根据结构化 checks 判定。厂商日志格式留在剖面 driver。"""
    checks = checks or {}
    if checks.get("wall_timeout") or checks.get("compile_error") or checks.get("compiler_error"):
        return "error"
    if capability == "sim":
        if checks.get("sim_crash"):
            return "error"
        if checks.get("compile_only"):
            # 只编译的仿真没有 RESULT 行，判据就是编译过没过。
            return "pass"
        if checks.get("seeds_failed") or checks.get("result_fail"):
            return "fail"
        if checks.get("result_pass"):
            return "pass"
        return "error"
    if capability == "lint":
        if "errors" not in checks:
            return "error"
        if checks.get("errors"):
            return "fail"
        return "pass"
    if capability == "coverage":
        from framework.coverage import audit
        live = {row.get("id") for rows in ((state or {}).get("decisions") or {}).values()
                for row in rows if not row.get("withdrawn")}
        waivers = [item for item in (state or {}).get("waivers") or [] if item.get("decision") in live]
        limits, unwaived = audit(profile or {}, sys_root=sys_root, waivers=waivers)
        if unwaived:
            checks["cov_unwaived"] = ["%s=%s 低于默认 %s" % (key, value, default)
                                      for key, value, default in unwaived]
            return "fail"
        for key in ("line", "cond", "fsm", "tgl"):
            if key not in checks:
                return "error"
            value = checks[key]
            if isinstance(value, str) and value.strip().lower() == "na":
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                del exc
                return "error"
            if numeric < float(limits[key]):
                return "fail"
        return "pass"
    if capability == "synth":
        if checks.get("no_clock"):
            return "error"
        for key in ("errors", "latches", "setup_wns", "setup_violations", "area"):
            if key not in checks:
                return "error"
        if checks["errors"] or checks["latches"] or checks["setup_violations"] or float(checks["setup_wns"]) < 0:
            return "fail"
        return "pass"
    if capability == "sta":
        if checks.get("tool_error") or checks.get("unconstrained") or checks.get("no_clock"):
            return "error"
        corners = checks.get("corners") or []
        if not corners:
            return "error"
        for corner in corners:
            for key in ("setup_wns", "hold_wns", "setup_violations", "hold_violations"):
                if key not in corner:
                    return "error"
            if (float(corner["setup_wns"]) < 0 or float(corner["hold_wns"]) < 0
                    or corner["setup_violations"] or corner["hold_violations"]):
                return "fail"
        return "pass"
    if capability == "lec":
        # 等价性检查：driver 报 NOTOOL（远端没有 yosys）或没有结论行都判 error；
        # 结论只有 EQUIV（等价）与 DIFF（不等价）两态，分别 pass 与 fail。
        if checks.get("tool_error") or checks.get("no_report"):
            return "error"
        if "equiv" not in checks:
            return "error"
        return "pass" if checks["equiv"] else "fail"
    return "error"


def _conclusion(capability, status):
    return "%s %s" % (capability, status)


def _mirror_path(profile, path):
    """本地路径 → 远端镜像路径。工具在远端执行，拿到本地路径找不到文件。"""
    if not path:
        return ""
    local = (profile.get("local_root") or "").rstrip("/")
    mirror = profile["mirror_root"].rstrip("/")
    absolute = path if os.path.isabs(path) else os.path.join(local, path)
    inside = os.path.relpath(absolute, local)
    if inside.startswith(".."):
        return path
    return "%s/%s" % (mirror, inside.replace(os.sep, "/"))


def _sdc_has_clock(path):
    """SDC 是否至少有一条 create_clock。文件不存在时返回 None，交给工具判。"""
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return re.search(r"(?m)^\s*create_clock\b", text) is not None


def _sys_platforms(sys_name):
    """sys 场景该数哪些平台：`testbench/<sys>_tb.f` 实际引用的那个（T3）。

    子系统同时有模块级平台时，把它们的用例算进全量回归的期望值会把
    “跑全了”判成“没跑全”。清单不在时返回 None，维持按全部平台统计。
    """
    if not sys_name:
        return None
    from framework.gates.tc import referenced_platforms
    path = os.path.join(project_root(), sys_name, "testbench", "%s_tb.f" % sys_name)
    return referenced_platforms(path)


def _tc_all_cases(sys_name, module, scenario="sys"):
    """tc_all 枚举用例数。子系统自己的 testbench 里没有平台时，退到
    `pub_code/testbench/<module>`（pubip 场景的 TB 根目录，见 tc 闸门的三种平台根目录）。"""
    from framework.gates.tc import case_count
    root = project_root()
    only = _sys_platforms(sys_name) if (scenario == "sys" and not module) else None
    total = case_count(os.path.join(root, sys_name), module or "", only=only)
    if total or only is not None:
        return total
    if module and os.path.isdir(os.path.join(root, "pub_code", "testbench", module)):
        return case_count(os.path.join(root, "pub_code"), module)
    return total


def _regression_expectation(sys_name, module, req, checks):
    """行 10 的全量回归口径：用例覆盖证据要等于 tc_all 枚举用例数 × seed 数。

    证据优先用 driver 报的 `cases_run`（本平台 TB 每个用例打一行 `[CASE_END]`）；
    driver 报不出用例数时，退回按 RESULT 行数核对（每用例一行 RESULT 的 TB）。
    只看 RESULT 行数会把“每个 seed 汇总一行 RESULT”的真实 TB 误判成没跑全。
    """
    seeds = [item for item in (req.get("seeds") or []) if item]
    if not seeds:
        seeds = [req.get("seed") or ""]
    out = {"seeds": len(seeds)}
    if not sys_name:
        return out
    cases = _tc_all_cases(sys_name, module, req.get("scenario") or "sys")
    expected = cases * len(seeds)
    out["tc_all_cases"] = cases
    out["expected_results"] = expected
    observed = int(checks.get("cases_run") or 0)
    if observed:
        out["observed_cases"] = observed
        out["cases_source"] = "cases"
        covered = observed == expected
    else:
        out["observed_cases"] = int(checks.get("result_pass") or 0)
        out["cases_source"] = "results"
        covered = int(checks.get("result_pass") or 0) == expected
    ok = (cases > 0
          and covered
          and not checks.get("sim_crash")
          and not checks.get("result_fail")
          and int(checks.get("seeds_failed") or 0) == 0)
    out["full_regression"] = 1 if ok else 0
    return out


def _tool_versions(checks):
    """运行记录里的工具版本：能力 → 版本串。

    版本串来自剖面 driver 的 parse 从脚本开头那行 `TOOL_VERSION` 里取的值；这里只把
    形状收口（dict、键值都是非空字符串），免得半截数据进 state.json。没取到（旧剖面、
    工具不在 PATH 上）时返回空表，调用方就不要写这个字段。
    """
    raw = (checks or {}).get("tool_versions")
    if not isinstance(raw, dict):
        return {}
    return {str(key).strip(): str(value).strip()
            for key, value in raw.items() if str(value).strip()}


def _version_note(profile, capability, checks):
    """实测工具版本与剖面 expect_versions 的比对（只提示不阻断）。

    expect_versions 是「能力 → 期望版本里应出现的片段」：实测版本串含该片段即算一致。
    剖面没声明期望值时不提示；声明了却没取到版本、或对不上，都返回一句 note 说明，
    由运行记录带给 tick，status 与闸门判据不受影响。
    """
    expected = (profile.get("expect_versions") or {}).get(capability)
    if not expected:
        return ""
    got = _tool_versions(checks).get(capability) or ""
    if not got:
        return "%s 没取到工具版本，无法核对 expect_versions（期望含 %s）" % (capability, expected)
    if str(expected) in got:
        return ""
    return "%s 的工具版本与 expect_versions 不一致：期望含 %s，实测 %s" % (
        capability, expected, got)


def _pre_run_digest(capability, sys_name, scenario="", module="",
                    extra_paths=None, netlist=""):
    """rsync 之前算一次输入摘要，作为"运行期间输入未变"的基线。

    输入集按能力分（engine.CAPABILITY_INPUTS）。没有子系统名时不设基线，
    record_run 也就不做前后比对。
    """
    if not sys_name:
        return None
    from framework.engine import inputs_digest
    return inputs_digest(project_root(), sys_name, list(extra_paths or []),
                         scenario=scenario, module=module,
                         capability=capability, netlist=netlist)


def _pre_lint_module_digests(local_root, sys_name, rtl):
    """lint 在编译前按模块算摘要（module_digests 的前基线）。"""
    if not sys_name:
        return {}
    from framework.engine import module_digest
    base = os.path.join(local_root, sys_name)
    return {mod: module_digest(base, mod)
            for mod in _lint_modules(local_root, sys_name, rtl)}


@contextlib.contextmanager
def _workdir_lock(local_root, sys_name, scenario, module):
    """同一 (sys, scenario, module) 的工作目录本地串行，防止并行派工
    互相覆盖远端 `<sys>/work` 里的 simv 与波形文件。

    锁文件 `<sys>/.run.lock.<scenario>.<module>`，fcntl.flock 排他。锁只在本机
    profile_run 这一层；不要挪进 state_txn 事务体——同进程对同一把锁重复加锁
    会自死锁（见 framework/state.py 的 docstring）。
    """
    base = os.path.join(local_root, sys_name or "pub_code")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, ".run.lock.%s.%s" % (scenario or "sys", module or ""))
    info = {"file": os.path.relpath(path, local_root).replace(os.sep, "/"),
            "waited_s": 0.0}
    fh = open(path, "a+")
    start = time.monotonic()
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        info["waited_s"] = round(time.monotonic() - start, 3)
        yield info
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _note_lock(sys_name, info):
    """锁出现等待（有并行派工）时写一条事件进子系统台账；没有台账时跳过。"""
    if not sys_name or not info.get("waited_s"):
        return
    try:
        from framework.state import record_event, state_txn
        with state_txn(project_root(), sys_name, cmd="run_lock") as state:
            record_event(state, "运行锁", obj=info["file"],
                         evidence="等待 %.1fs 后串行执行" % info["waited_s"])
    except (OSError, FileNotFoundError):
        pass


def _decode(chunk):
    """子进程输出统一成 str（超时异常里的 stdout/stderr 可能是 bytes 或 None）。"""
    if chunk is None:
        return ""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", "replace")
    return str(chunk)


def _local_products(profile, sys_name, capability, scope, paths):
    """产物清单：运行前算好的日志路径 + 本地工作目录里的报告。"""
    paths = list(paths or [])
    scope = scope or {}
    if not sys_name:
        return sorted(set(paths))
    if (capability in ("sim", "coverage") and scope.get("scenario") == "pubip"
            and scope.get("module")):
        # pubip 产物落 pub_code/work/<module>/，不混进子系统台账。
        base = os.path.join(profile["local_root"], "pub_code", "work", scope["module"])
    else:
        base = os.path.join(profile["local_root"], sys_name, FOLDER.get(capability, "work"))
    if os.path.isdir(base):
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = [item for item in dirnames if item != "__pycache__"]
            for fn in sorted(files):
                if not fn.endswith(KEEP_SUFFIX):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), profile["local_root"])
                paths.append(rel.replace(os.sep, "/"))
    return sorted(set(paths))


class Transport:
    """运行层与执行主机之间的唯一通道（契约见 toolchain/CONTRACT.md）。

    driver 只把工具命令拼成脚本；Transport 把脚本送到主机、把输出与产物拿回
    本地。`run_sim` / `run_other` 因此只剩"组装请求 → 解析 → 判定 → 记录"，
    不再各写一份"同步 → 工作目录锁 → ssh 执行 → 回拉"。

    三个必需成员：
      sync()                 把本地工作树同步到执行主机；本机执行是空操作。
      execute(script, wall)  在主机上执行脚本，返回 (log, returncode)。
      pull(paths)            把主机产物收回本地，返回本地产物清单。

    运行层只用 run()/preview()/waves()：run() 是"同步 → 执行 → 回拉"整段，
    全程持同一把工作目录锁；preview() 给 dry_run 用；waves() 给运行记录用。
    """

    name = ""

    def __init__(self, profile, driver, sys_name="", capability="", scenario="sys",
                 module="", scope=None):
        self.profile = profile
        self.driver = driver
        self.sys_name = sys_name or ""
        self.capability = capability or ""
        self.scenario = scenario or "sys"
        self.module = module or ""
        self.scope = scope or {}

    def sync(self):
        raise NotImplementedError

    def execute(self, script, wall=0):
        raise NotImplementedError

    def pull(self, paths=()):
        """默认：产物已经在本机（本机执行），只把清单归一。"""
        return _local_products(self.profile, self.sys_name, self.capability,
                               self.scope, paths)

    def run(self, script, wall=0, sync=True):
        """同步 → 执行 → 回拉，整段在一把工作目录锁里做完。

        回拉必须在锁内：放到锁外的话，并行派工的下一次运行会先覆盖主机上的
        工作目录，这次运行拉回的就是别人的半成品。返回
        (log, returncode, artifacts, lock, error)，error 非空表示同步失败。
        """
        with _workdir_lock(self.profile["local_root"], self.sys_name,
                           self.scenario, self.module) as lock:
            _note_lock(self.sys_name, lock)
            if sync and not self.sync():
                return "", 0, [], lock, "同步失败"
            log, returncode = self.execute(script, wall)
            artifacts = self.pull([])
            return log, returncode, artifacts, lock, ""

    def preview(self, script, sync=True):
        """dry_run 要打印的"将要执行什么"；本机执行只有脚本本身。"""
        del sync
        return script

    def waves(self, wave):
        """这次仿真写出的波形路径；执行不落本机工作目录时为空。"""
        del wave
        return []


class SshTransport(Transport):
    """远端执行：rsync 同步 → ssh bash -s → rsync 回拉。"""

    name = "ssh"

    def sync(self):
        proc = subprocess.run(self.driver.rsync_line(self.profile), shell=True,
                              capture_output=True, text=True, errors="replace")
        return proc.returncode == 0

    def execute(self, script, wall=0):
        # 远端的墙钟上限由脚本自己落实（超时回 124），这里不再套一层。
        del wall
        proc = subprocess.run(["ssh", self.profile["ssh_alias"], "bash -s"],
                              input=script, capture_output=True, text=True, errors="replace")
        return (proc.stdout or "") + (proc.stderr or ""), proc.returncode

    def pull(self, paths=()):
        if not self.sys_name or not hasattr(self.driver, "pull_line"):
            return sorted(set(str(item) for item in (paths or []) if item))
        subprocess.run(self.driver.pull_line(self.profile, self.sys_name,
                                             self.capability, self.scope),
                       shell=True, capture_output=True, text=True, errors="replace")
        return super().pull(paths)

    def preview(self, script, sync=True):
        line = "" if not sync else self.driver.rsync_line(self.profile) + "\n"
        return line + script

    def waves(self, wave):
        return _remote_waves(self.profile, self.scenario, self.sys_name,
                             self.module, wave)


class LocalTransport(Transport):
    """本机执行：本地工作树就是执行目录，不同步、也不回拉。"""

    name = "local"

    def sync(self):
        return True

    def execute(self, script, wall=0):
        """在本机跑脚本；wall 是墙钟上限，超时按远端 timeout 的口径回 124。"""
        try:
            proc = subprocess.run(["bash", "-s"], input=script, capture_output=True,
                                  text=True, errors="replace",
                                  cwd=self.profile["local_root"], timeout=wall or None)
        except subprocess.TimeoutExpired as exc:
            return _decode(exc.stdout) + _decode(exc.stderr) + "\nWALL_TIMEOUT\n", 124
        return (proc.stdout or "") + (proc.stderr or ""), proc.returncode


TRANSPORT_TYPES = {"ssh": SshTransport, "local": LocalTransport}


def make_transport(profile, driver, sys_name="", capability="", scenario="sys",
                   module="", scope=None):
    """按剖面的 transport 字段选执行通道（取值见 toolchain/CONTRACT.md）。

    旧剖面没有这个字段时按 ssh 处理；取值不在表里抛 ValueError，运行层把它
    翻成 error 运行记录，不让 `run` 崩在 traceback 上。
    """
    name = str(profile.get("transport") or "").strip() or "ssh"
    kind = TRANSPORT_TYPES.get(name)
    if kind is None:
        raise ValueError("未知 transport：%s（本框架支持 %s）"
                         % (name, "、".join(sorted(TRANSPORT_TYPES))))
    return kind(profile, driver, sys_name=sys_name, capability=capability,
                scenario=scenario, module=module, scope=scope)


def _open_transport(profile, driver, sys_name, capability, scenario, module, scope):
    """构造执行通道；剖面声明了未知 transport 时把错误摘要交回调用方。"""
    try:
        return make_transport(profile, driver, sys_name=sys_name, capability=capability,
                              scenario=scenario, module=module, scope=scope), ""
    except ValueError as exc:
        return None, str(exc)


def _remote_waves(profile, scenario, sys_name, module, wave):
    """这次仿真写出的远端波形路径列表（运行记录的 `waves` 字段）。

    波形由 TB 的 TB_DUMP_TAG 落在远端工作目录（与 dbg 用的 eda_mcp.workdir
    同一口径），远端列一次 `*.fsdb`（或 `*.vcd`）。pull 的排除表里有
    `*.fsdb`/`*.vcd`，波形不回拉，所以这里只有远端路径、没有本地路径；
    dbg 读波形时按路径精确匹配这条运行记录判新鲜度。
    列不出（wave=off、没有 --sys、远端目录里没有波形或 ssh 失败）返回 []。
    """
    if wave not in ("fsdb", "vcd"):
        return []
    if not sys_name and not (scenario == "pubip" and module):
        return []
    from framework import eda_mcp
    suffix = ".fsdb" if wave == "fsdb" else ".vcd"
    wd = eda_mcp.workdir(profile, scenario, sys_name or "", module or "")
    argv = eda_mcp.ssh_argv(profile, "ls -1 %s/*%s 2>/dev/null" % (shlex.quote(wd), suffix))
    proc = subprocess.run(argv, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return []
    return sorted(line.strip() for line in (proc.stdout or "").splitlines()
                  if line.strip().endswith(suffix))


def run_sim(req):
    profile = load_profile()
    if not (profile.get("tools") or {}).get("sim", {}).get("available"):
        return _result("sim", "unavailable", "当前剖面未提供仿真", profile)
    drv = _driver(profile, "sim.py")
    if drv is None:
        return _result("sim", "unavailable", "剖面缺少 drivers/sim.py", profile)
    scenario = req.get("scenario") or "sys"
    sys_name = req.get("sys") or ""
    module_name = req.get("module") or ""
    defines = _validated_defines(req)
    wall = req.get("wall") or 3600
    script = drv.remote_script(
        profile, scenario, sys_name, module_name,
        req.get("wave") or "off", bool(req.get("coverage")), bool(req.get("compile_only")),
        req.get("tc") or "", req.get("seed") or "", req.get("seeds") or [],
        wall, req.get("timeout_us") or "", defines=defines,
    )
    scope = {
        "scenario": scenario, "module": module_name,
        "tc": req.get("tc") or "",
        # 覆盖率记录要绑到带 --coverage 的那次仿真，标志得先记下来。
        "coverage": bool(req.get("coverage")),
        "compile_only": bool(req.get("compile_only")),
        "seeds": [item for item in (req.get("seeds") or []) if item] or [req.get("seed") or ""],
        # 变体宏进记录，闸门与复查能看到这次跑的是哪个变体。
        "defines": defines,
    }
    transport, error = _open_transport(profile, drv, sys_name, "sim", scenario,
                                       module_name, scope)
    if error:
        return _result("sim", "error", error, profile)
    sync = not req.get("no_sync")
    if req.get("dry_run"):
        return _result("sim", "dry_run", transport.preview(script, sync=sync), profile,
                       {"dry_run": True})
    # 同步之前先算输入摘要，拉回后由 record_run 再算一次比对。
    pre = _pre_run_digest("sim", sys_name, scenario, module_name)
    log, returncode, products, lock, error = transport.run(script, wall, sync=sync)
    if error:
        return _result("sim", "error", error, profile)
    checks = drv.parse("sim", log, "")
    # driver 从脚本开头的探针行取到的工具版本进记录（形状在这里收口）。
    versions = _tool_versions(checks)
    if versions:
        checks["tool_versions"] = versions
    if returncode == 124:
        checks["wall_timeout"] = 1
    if returncode == 2:
        checks["compile_error"] = 1
    if req.get("compile_only"):
        # 只编译时不套全量回归口径：它本就没有 RESULT 可数。
        checks["compile_only"] = 1
    else:
        checks.update(_regression_expectation(sys_name, module_name, req, checks))
    status = judge("sim", checks, profile, state=_load_state(sys_name))
    note = _version_note(profile, "sim", checks)
    # pubip 的日志与 pull 落 pub_code/work/<module>/，不写 <sys>/work/sim.log
    # 盖掉子系统自己的仿真日志；日志名带 define，多变体互不覆盖。
    if scenario == "pubip" and module_name:
        log_dir = os.path.join("pub_code", "work", module_name)
    else:
        log_dir = os.path.join(sys_name, "work") if sys_name else ""
    stem = "sim"
    if defines:
        stem += "_" + "_".join(item.replace("=", "_") for item in defines)
    log_rel = _write_log(log_dir, stem, log)
    artifacts = sorted(set(products) | set(log_rel))
    result = _result("sim", status, _conclusion("sim", status), profile, checks, artifacts, scope)
    _attach_output(result, log, log_rel)
    result["lock"] = lock
    result["inputs_digest_pre"] = pre
    if note:
        result["note"] = note
    # 带波形跑的仿真把远端波形路径记进运行记录（compile_only 没有波形可列，
    # 不列——否则会把目录里上次运行留下的旧波形错挂到这条记录上）。
    if (req.get("wave") or "off") != "off" and not req.get("compile_only"):
        result["waves"] = transport.waves(req.get("wave") or "off")
    return result


def run_other(capability, req):
    profile = load_profile()
    spec = (profile.get("tools") or {}).get(capability) or {}
    if not spec.get("available", False):
        return _result(capability, "unavailable", "当前剖面未提供 %s" % capability, profile)
    drv = _driver(profile, "eda.py")
    if drv is None:
        return _result(capability, "unavailable", "剖面缺少 drivers/eda.py", profile)
    sys_name = req.get("sys") or ""
    local_root = profile["local_root"]
    sdc = req.get("sdc") or ""
    if capability == "synth" and not sdc:
        return _result(capability, "error", "综合没有 SDC", profile)
    if capability == "synth" and _sdc_has_clock(_resolve(local_root, sdc)) is False:
        return _result(capability, "error", "综合用的 SDC 没有 create_clock", profile)
    netlist = req.get("netlist") or _synth_netlist(sys_name)
    if capability == "sta" and not netlist:
        return _result(capability, "error", "时序没有网表", profile)
    gold = ""
    if capability == "lec":
        # 候选 = rtl/<模块>.sv|.v；黄金参考由 --gold 给出（相对仓库根）。
        module_name = req.get("module") or ""
        if not module_name:
            return _result(capability, "error", "等价性检查需要 --module 指定候选模块", profile)
        cand = ""
        for ext in (".sv", ".v"):
            path = os.path.join(local_root, sys_name, "rtl", module_name + ext)
            if os.path.isfile(path):
                cand = path
                break
        if not cand:
            return _result(capability, "error",
                           "候选模块不存在：%s/rtl/%s.sv（或 .v）" % (sys_name, module_name), profile)
        gold = req.get("gold") or ""
        if not gold:
            return _result(capability, "error",
                           "等价性检查没有黄金参考：加 --gold <黄金 RTL 文件>", profile)
        if not os.path.isfile(_resolve(local_root, gold)):
            return _result(capability, "error", "黄金参考不存在：%s" % gold, profile)
    # 只有 sta 才去找“上一次综合生成的 SDC”；把它挂到 coverage/lint 的运行记录上，
    # 会让那份记录随后被判定“输入已变更”，把本来有效的运行挡在闸门外。
    sdc_used = ""
    if capability == "sta":
        sdc_used = sdc or _synth_sdc(sys_name)
        if not sdc_used:
            return _result(capability, "error", "时序没有 SDC", profile)
    builders = {
        "lint": lambda: drv.lint_script(profile, sys_name, req.get("rtl") or ("%s/rtl" % sys_name)),
        "coverage": lambda: drv.coverage_script(
            profile, sys_name, req.get("module") or "", req.get("scenario") or "sys"),
        "synth": lambda: drv.synth_script(
            profile, sys_name, req.get("lib") or "default",
            req.get("top") or "", req.get("rtl_dir") or "", _mirror_path(profile, sdc)),
        "sta": lambda: drv.sta_script(
            profile, sys_name, req.get("corner") or "typical",
            _mirror_path(profile, netlist), _mirror_path(profile, sdc_used)),
        "lec": lambda: drv.lec_script(
            profile, sys_name, module_name, _mirror_path(profile, gold)),
    }
    if capability not in builders:
        return _result(capability, "error", "未知能力 %s" % capability, profile)
    script = builders[capability]()
    scenario = req.get("scenario") or "sys"
    module_name = req.get("module") or ""
    scope = {
        "scenario": scenario,
        "module": module_name,
        "rtl": req.get("rtl") or "",
        "rtl_dir": req.get("rtl_dir") or "",
        "sdc": sdc,
        "netlist": netlist,
        "top": req.get("top") or "",
        "corner": req.get("corner") or "typical",
        "gold": gold,
    }
    if capability == "lint":
        # 行 7 按模块查记录，先定下这次 lint 覆盖了哪些模块。
        scope["modules"] = _lint_modules(local_root, sys_name, scope["rtl"])
    transport, error = _open_transport(profile, drv, sys_name, capability, scenario,
                                       module_name, scope)
    if error:
        return _result(capability, "error", error, profile)
    if req.get("dry_run"):
        return _result(capability, "dry_run", transport.preview(script), profile,
                       {"dry_run": True})
    # SDC 是输入不是产物，路径清单在运行前就能定死；前后摘要按同一组路径算。
    sdc_paths = []
    if capability in ("synth", "sta"):
        for candidate in (sdc, sdc_used):
            path = _resolve(local_root, candidate)
            if path and os.path.isfile(path) and path not in sdc_paths:
                sdc_paths.append(path)
    if capability == "lec" and gold:
        # 黄金参考是输入不是产物：进 extra_paths（运行记录的 sdc_paths 通用扩展位），
        # 输入摘要才会把它咬住。
        sdc_paths.append(gold)
    # 同步之前先算输入摘要与（lint 的）逐模块摘要，拉回后由 record_run 再算一次比对。
    pre = _pre_run_digest(capability, sys_name, scenario, module_name,
                          extra_paths=sdc_paths, netlist=netlist)
    pre_modules = {}
    if capability == "lint":
        pre_modules = _pre_lint_module_digests(
            local_root, sys_name, req.get("rtl") or ("%s/rtl" % sys_name))
    log, _returncode, products, lock, error = transport.run(script, req.get("wall") or 3600)
    if error:
        return _result(capability, "error", error, profile)
    folder = FOLDER.get(capability, "work")
    log_rel = _write_log(os.path.join(sys_name, folder) if sys_name else "", capability, log)
    checks = drv.parse(capability, log, "")
    # driver 从脚本开头的探针行取到的工具版本进记录（形状在这里收口）。
    versions = _tool_versions(checks)
    if versions:
        checks["tool_versions"] = versions
    if capability == "synth" and hasattr(drv, "synth_products"):
        # 本次综合写出的网表与 SDC 文件名：run sta 按名字取，不按字母序猜。
        checks.update(drv.synth_products(sys_name, req.get("top") or ""))
    sys_root = os.path.join(local_root, sys_name) if sys_name else ""
    status = judge(capability, checks, profile, sys_root=sys_root, state=_load_state(sys_name))
    artifacts = sorted(set(products) | set(log_rel))
    notes = []
    if checks.get("cov_unwaived"):
        notes.append("cov_gate.txt 下调了阈值但没有豁免：" + "；".join(checks["cov_unwaived"]))
    version_note = _version_note(profile, capability, checks)
    if version_note:
        notes.append(version_note)
    result = _result(capability, status, _conclusion(capability, status), profile,
                     checks, artifacts, scope, sdc_paths)
    _attach_output(result, log, log_rel)
    result["lock"] = lock
    result["inputs_digest_pre"] = pre
    if capability == "lint":
        result["module_digests_pre"] = pre_modules
    if notes:
        result["note"] = "；".join(notes)
    return result


def _resolve(local_root, path):
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(local_root, path)


def _lint_modules(local_root, sys_name, rtl):
    """这次 lint 到底覆盖了哪些模块（行 7 按模块查记录）。"""
    target = rtl or ("%s/rtl" % sys_name)
    path = _resolve(local_root, target)
    modules = []
    if os.path.isfile(path):
        modules.append(os.path.basename(path).rsplit(".", 1)[0])
    elif os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if fn.endswith((".v", ".sv")):
                modules.append(fn.rsplit(".", 1)[0])
    return modules


def _latest_synth_run(sys_name):
    if not sys_name:
        return None
    try:
        from framework.state import load_state
        state = load_state(project_root(), sys_name)
    except FileNotFoundError as exc:
        del exc
        return None
    for run in reversed(state.get("runs") or []):
        if run.get("capability") == "synth":
            return run
    return None


def _synth_product(sys_name, key, suffix):
    """按上一轮综合记下的文件名取网表 / SDC。

    不带 --netlist 时原是在最近一次综合的全部产物里按字母序取第一个 `.v`，
    `dc/` 里有别的顶层留下的网表时就会取错。综合驱动在 checks 里报了本次
    写出的文件名，这里按名字取；老记录没有名字时退回按后缀取。
    """
    run = _latest_synth_run(sys_name)
    name = ((run or {}).get("checks") or {}).get(key) or ""
    if name:
        for art in run.get("artifacts") or []:
            text = str(art)
            if text == name or text.endswith("/" + name):
                return text
    return _artifact_ending(sys_name, suffix)


def _synth_netlist(sys_name):
    return _synth_product(sys_name, "netlist", ".v")


def _synth_sdc(sys_name):
    return _synth_product(sys_name, "sdc", ".sdc")


def _artifact_ending(sys_name, suffix):
    if not sys_name:
        return ""
    try:
        from framework.state import load_state
        state = load_state(project_root(), sys_name)
    except FileNotFoundError as exc:
        del exc
        return ""
    for run in reversed(state.get("runs") or []):
        if run.get("capability") != "synth":
            continue
        for art in run.get("artifacts") or []:
            if str(art).endswith(suffix):
                return art
    return ""


def _write_log(rel_dir, stem, log):
    """把整段输出写到 <rel_dir>/<stem>.log，返回相对路径列表。

    先写同目录临时文件再原子替换：日志落盘在工作目录锁之外，同一
    (sys, scenario, module) 的并行派工可能写同一个路径，读到的要么是完整的
    一份、要么是另一份，不会是两份交错的半截。
    """
    if not rel_dir:
        return []
    rel = os.path.join(rel_dir, stem + ".log")
    path = os.path.join(project_root(), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=stem + ".",
                                  suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(log)
    os.replace(tmp, path)
    return [rel.replace(os.sep, "/")]


def _attach_output(result, log, log_rel):
    """把输出侧证据挂到结果上：日志路径与内容摘要、结构化诊断清单。

    日志摘要在 record_run 落库，闸门判"新鲜"时复算比对——日志被改过，
    这条运行记录的结论就不可信（framework/gates/run.py 的 _output_findings）。
    诊断清单只做回修入口，不改变 judge 的判定。
    """
    if log_rel:
        result["log"] = log_rel[0]
        result["log_digest"] = hashlib.sha256((log or "").encode("utf-8")).hexdigest()
    items, total = diagnostics.extract(log)
    if items:
        result["diagnostics"] = items
        result["diagnostics_total"] = total
    return result


def _result(capability, status, summary, profile, checks=None, artifacts=None,
            scope=None, sdc_paths=None):
    return {
        "capability": capability,
        "status": status,
        "summary": summary,
        "checks": checks or {},
        "artifacts": artifacts or [],
        "scope": scope or {},
        "sdc_paths": list(sdc_paths or []),
        "profile_id": profile.get("id", ""),
    }


# ---- 长任务作业（run --detach）----------------------------------------------
# 作业文件落在 `<sys>/work/jobs/<job_id>.json`：父进程写请求与初始状态后立即返回，
# 后台子进程（`--_execute-job <作业文件>`）跑完整个运行流程再回写状态与结果摘要。
# 状态只有四种：pending（已排）、running（后台进程已启动并持工作目录锁）、
# done（运行流程跑完且结论是 pass/dry_run/unavailable）、failed（运行结论 fail/error，
# 或后台进程自己异常退出）；失败与超时都靠这份文件留痕。
JOB_STATUSES = ("pending", "running", "done", "failed")
JOB_TERMINAL = ("done", "failed")


def job_now():
    """作业时间戳：与 state 记录同格式（秒级），便于并排阅读。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def jobs_dir(root, sys_name):
    return os.path.join(root, sys_name, "work", "jobs")


def job_path(root, sys_name, job_id):
    return os.path.join(jobs_dir(root, sys_name), job_id + ".json")


def new_job_id(capability):
    """作业号：能力 + 时间 + 随机后缀；同一秒内并发 detach 也不重名。"""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return "%s-%s-%s" % (capability, stamp, os.urandom(2).hex())


def job_output_path(path):
    """后台进程的 stdout/stderr 落点；后缀 `.out` 不在 KEEP_SUFFIX 里，
    不会被 `_local_products` 当成运行产物收进运行记录。"""
    stem = path[:-len(".json")] if path.endswith(".json") else path
    return stem + ".out"


def read_job(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_job(path, job):
    """原子写作业文件：读的一方要么看到上一版、要么看到完整的新一版。"""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(job, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return job


def update_job(path, **fields):
    """读最新内容再改字段后写回：后台进程启动时补 pid/状态，不会被父进程覆盖。"""
    try:
        job = read_job(path)
    except (OSError, ValueError):
        job = {}
    job.update(fields)
    return write_job(path, job)


def create_job(root, sys_name, capability, req, wall=0):
    """父进程写作业文件并返回 (路径, 作业 dict)。pid 由后台进程启动时补。"""
    job_id = new_job_id(capability)
    path = job_path(root, sys_name, job_id)
    job = {
        "id": job_id,
        "capability": capability,
        "sys": sys_name,
        "request": dict(req),
        "status": "pending",
        "pid": 0,
        "created_at": job_now(),
        "started_at": "",
        "finished_at": "",
        "result": None,
        "record": "",
        "exit_code": None,
        "error": "",
        "job_file": os.path.relpath(path, root).replace(os.sep, "/"),
        "output": os.path.relpath(job_output_path(path), root).replace(os.sep, "/"),
        "wall": int(wall or 0),
    }
    write_job(path, job)
    return path, job


def _job_sys_names(root):
    """仓库里哪些子系统目录下有作业（不带 --sys 时按目录找，不读 state.json）。"""
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        del exc
        return []
    return [name for name in names
            if not name.startswith(".")
            and os.path.isdir(os.path.join(root, name, "work", "jobs"))]


def find_job(root, job_id, sys_name=""):
    """按作业号找工作文件；不给 sys 时扫所有带 jobs 目录的子系统。"""
    if sys_name:
        path = job_path(root, sys_name, job_id)
        return path if os.path.isfile(path) else ""
    for name in _job_sys_names(root):
        path = job_path(root, name, job_id)
        if os.path.isfile(path):
            return path
    return ""


def list_jobs(root, sys_name=""):
    """作业摘要（新→旧）：id、能力、状态、开始时间、结论。"""
    names = [sys_name] if sys_name else _job_sys_names(root)
    jobs = []
    for name in names:
        folder = jobs_dir(root, name)
        try:
            items = sorted(os.listdir(folder))
        except OSError as exc:
            del exc
            continue
        for fn in items:
            if not fn.endswith(".json"):
                continue
            try:
                jobs.append(read_job(os.path.join(folder, fn)))
            except (OSError, ValueError):
                continue
    return sorted(jobs, key=lambda item: (item.get("created_at") or "",
                                          item.get("id") or ""), reverse=True)

