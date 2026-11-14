# 作者：vick 邮箱：ykun@yk9811.com

"""环境自检。"""

import importlib.util
import json
import os
import sys

from framework.paths import project_root
from framework.profile_run import active_name


def run_doctor(ssh=False):
    root = project_root()
    lines = []
    ok = True
    py_ok = sys.version_info >= (3, 9)
    lines.append("%s Python %s" % ("通过" if py_ok else "失败", sys.version.split()[0]))
    ok = ok and py_ok
    try:
        import yaml
        lines.append("通过 PyYAML %s" % getattr(yaml, "__version__", ""))
    except ImportError as exc:
        lines.append("失败 未安装 PyYAML")
        ok = False
    name = ""
    try:
        name = active_name()
    except OSError as exc:
        lines.append("失败 读不到 toolchain/active：%s" % exc)
        ok = False
    profile = os.path.join(root, "toolchain", "profiles", name) if name else ""
    yaml_path = os.path.join(profile, "profile.yaml") if profile else ""
    drivers = os.path.join(profile, "drivers") if profile else ""
    struct_ok = bool(name) and os.path.isfile(yaml_path) and os.path.isdir(drivers)
    lines.append("%s 剖面 %s" % ("通过" if struct_ok else "失败", name or "（无）"))
    ok = ok and struct_ok
    for filename in ("sim.py", "eda.py"):
        path = os.path.join(drivers, filename) if drivers else ""
        imported = False
        if path and os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("doctor_" + filename[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                imported = True
            except Exception as exc:
                lines.append("失败 导入 %s：%s" % (filename, exc))
        else:
            lines.append("失败 缺少 %s" % filename)
        if imported:
            lines.append("通过 导入 %s" % filename)
        else:
            ok = False
    if ssh:
        import subprocess
        alias = ""
        try:
            import yaml as yamllib
            with open(yaml_path, encoding="utf-8") as fh:
                alias = (yamllib.safe_load(fh) or {}).get("ssh_alias") or ""
        except OSError as exc:
            pass
        if not alias:
            lines.append("失败 ssh 别名未配置")
            ok = False
        else:
            proc = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
                 alias, "true"],
                capture_output=True, text=True)
            ssh_ok = proc.returncode == 0
            lines.append("%s ssh %s" % ("通过" if ssh_ok else "失败", alias))
            if not ssh_ok:
                # 别只报“失败 ssh”：把退出码与 stderr 一起写出来，否则一次网络抖动
                #（比如本机开着代理）会被误读成环境不可用。
                detail = [line for line in (proc.stderr or proc.stdout or "").strip().splitlines()
                          if line.strip()]
                lines.append("    退出码 %s；%s" % (
                    proc.returncode, detail[-1] if detail else "无输出"))
                lines.append("    复查：ssh -o BatchMode=yes %s true；本机开着代理时先关掉再试" % alias)
            ok = ok and ssh_ok
    else:
        lines.append("跳过 ssh")
    lines.append("结论：%s" % ("通过" if ok else "失败"))
    return 0 if ok else 1, "\n".join(lines)


# ---------------------------------------------------------------- doctor --mcp


def _last_line(text):
    detail = [line for line in (text or "").strip().splitlines() if line.strip()]
    return detail[-1] if detail else "无输出"


def _mcp_profile(profile):
    if profile is None:
        from framework.profile_run import load_profile
        profile = load_profile()
    return profile


def mcp_checks(profile=None, root=None, run=None):
    """doctor --mcp 的检查项，返回结构化结果列表。

    每项 {"item", "ok", "detail"}，依次：
    1. SSH 可达；2. 远端安装存在且 SOURCE_DIGEST 与本地 toolchain/eda-mcp/src
    摘要一致；3. 远端 `eda-mcp doctor`（工具、Verdi/FFR、Xvfb）；
    4. 远端 workspace_root 与剖面 mirror_root 一致；5. fsdbq 可用。

    `run` 可注入 subprocess.run 桩（FakeProc 做法），测试不碰真 SSH。
    后续 4、5 项取自第 3 项 `eda-mcp doctor --json` 的输出，不再重复连接。
    """
    from framework import eda_mcp, eda_mcp_deploy

    root = root or project_root()
    profile = _mcp_profile(profile)
    cfg = eda_mcp.load_config(profile)
    if cfg is None:
        return [{"item": "eda_mcp 配置", "ok": False,
                 "detail": "剖面 %s 没有 eda_mcp 字段（未配置）" % profile.get("id", "")}]
    mirror = str(profile["mirror_root"]).rstrip("/")
    checks = []

    # 1. SSH 可达
    proc = eda_mcp.run_ssh(profile, "true", run=run)
    ssh_ok = proc.returncode == 0
    checks.append({"item": "ssh %s" % profile["ssh_alias"], "ok": ssh_ok,
                   "detail": "可达" if ssh_ok else
                   "退出码 %s；%s" % (proc.returncode, _last_line(proc.stderr or proc.stdout))})
    if not ssh_ok:
        return checks  # 后面的检查都走 SSH，不可达时不必逐项报失败

    # 2. 远端安装存在且 SOURCE_DIGEST 与本地源码一致
    local = eda_mcp.source_digest(root)
    from framework.eda_mcp_deploy import _remote_path_expr
    digest_expr = _remote_path_expr("%s/lib/eda-mcp/SOURCE_DIGEST" % cfg["prefix"])
    proc = eda_mcp.run_ssh(profile, "cat %s 2>/dev/null" % digest_expr, run=run)
    remote = (proc.stdout or "").strip().split()
    if proc.returncode != 0 or not remote:
        checks.append({"item": "远端安装与 SOURCE_DIGEST", "ok": False,
                       "detail": "读不到 %s/lib/eda-mcp/SOURCE_DIGEST（未安装），"
                                 "先运行 framework.py eda-mcp install"
                                 "（它会先同步镜像；远端镜像过期时这步是必需的）" % cfg["prefix"]})
    elif remote[0] != local:
        checks.append({"item": "远端安装与 SOURCE_DIGEST", "ok": False,
                       "detail": "本地 eda-mcp 已更新，先运行 framework.py eda-mcp install"})
    else:
        checks.append({"item": "远端安装与 SOURCE_DIGEST", "ok": True,
                       "detail": "与本地源码摘要一致（%s…）" % local[:12]})

    # 3. 远端 eda-mcp doctor（工具、Verdi/FFR、Xvfb）——用 --json 拿结构化结果
    remote_cmd = ("EDA_MCP_WORKSPACE_ROOT=%s EDA_MCP_ENABLED_GROUPS=%s "
                  "%s/bin/eda-mcp doctor --json" % (mirror, ",".join(cfg["groups"]), cfg["prefix"]))
    proc = eda_mcp.run_ssh(profile, remote_cmd, run=run)
    items = []
    text = (proc.stdout or "").strip()
    if text.startswith("{"):
        try:
            items = (json.loads(text) or {}).get("items") or []
        except ValueError as exc:
            del exc
            items = []
    fail = [item for item in items if item.get("status") == "fail"]
    doctor_ok = proc.returncode == 0 and not fail and bool(items)
    names = "、".join(item.get("name", "") for item in fail) or _last_line(proc.stderr or proc.stdout)
    checks.append({"item": "远端 eda-mcp doctor", "ok": doctor_ok,
                   "detail": "全部通过" if doctor_ok else
                   "退出码 %s；失败项：%s" % (proc.returncode, names)})

    def _item(name_prefix):
        for item in items:
            if str(item.get("name", "")).startswith(name_prefix):
                return item
        return None

    # 4. workspace_root 与 mirror_root 一致
    ws = _item("镜像根 workspace_root")
    ws_ok = bool(ws) and ws.get("status") == "ok" and mirror in str(ws.get("detail", ""))
    checks.append({"item": "workspace_root 与 mirror_root 一致", "ok": ws_ok,
                   "detail": (ws or {}).get("detail", "") or "远端 doctor 没有报告 workspace_root"})
    # 5. fsdbq 可用
    fq = _item("fsdbq")
    fq_ok = bool(fq) and fq.get("status") == "ok"
    checks.append({"item": "fsdbq 可用", "ok": fq_ok,
                   "detail": (fq or {}).get("detail", "") or "远端 doctor 没有报告 fsdbq"})
    return checks


def run_mcp(profile=None, root=None, run=None):
    """doctor --mcp 的输出（CLI 接线在后续包）。沿用 --ssh 的写法：退出码 + 明细行。"""
    try:
        checks = mcp_checks(profile=profile, root=root, run=run)
    except FileNotFoundError as exc:
        return 1, "失败 %s" % exc
    lines = []
    ok = True
    for item in checks:
        ok = ok and item["ok"]
        lines.append("%s %s：%s" % ("通过" if item["ok"] else "失败", item["item"], item["detail"]))
    lines.append("结论：%s" % ("通过" if ok else "失败"))
    return (0 if ok else 1), "\n".join(lines)
