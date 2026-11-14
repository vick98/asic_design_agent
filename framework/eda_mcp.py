# 作者：vick 邮箱：ykun@yk9811.com

"""eda-mcp 共用层：剖面 `eda_mcp` 字段、远端连接命令拼装、本地源码摘要。

约定：
- 剖面字段 `eda_mcp: {prefix, verdi_home, groups}`；没有这一段时按"未配置"表达
  （`load_config`/`mcp_json_text` 返回 None，调用方不得生成 `.mcp.json` 或发起连接）。
- 工作根不另写字段，固定取剖面的 `mirror_root`，经 `EDA_MCP_WORKSPACE_ROOT` 传给远端。
- 远端服务入口 `<prefix>/bin/eda-mcp-server`，CLI 为 `<prefix>/bin/eda-mcp`。
- groups 只接受观察组取值（env/fsdb/wave/npi，不含 flow、shell）。

本层与上层 `dbg` 只用观察组（env/fsdb/wave/npi）；作业组命令
绝不在这里拼装。入账运行仍只经 `framework.py run`。
"""

import hashlib
import json
import os
import subprocess

from framework.paths import project_root

# 本框架只启用这四组（工具组开关在远端落实）；剖面 groups 与之对齐。
GROUPS = ("env", "fsdb", "wave", "npi")

MCP_JSON_REL = ".mcp.json"

# 本框架只允许这四个观察组。剖面 groups 里出现 flow/shell 直接报错，
# 不静默收窄——作业面禁用是机制不是约定。
_ALLOWED_GROUPS = frozenset(("env", "fsdb", "wave", "npi"))


def load_config(profile):
    """读剖面 `eda_mcp` 字段。未配置（缺字段或缺 prefix）返回 None。

    返回 {"prefix", "verdi_home", "groups"}；prefix 保留原样（`~` 由远端 shell
    展开——不能在本地 expanduser，远端账号与本机账号不同）。
    """
    cfg = (profile or {}).get("eda_mcp") or {}
    prefix = str(cfg.get("prefix") or "").strip()
    if not prefix:
        return None
    groups = [str(item).strip() for item in (cfg.get("groups") or GROUPS) if str(item).strip()]
    bad = [item for item in groups if item not in _ALLOWED_GROUPS]
    if bad:
        raise ValueError("剖面 eda_mcp.groups 含未知组 %s（允许：%s）"
                         % ("、".join(bad), "/".join(_ALLOWED_GROUPS)))
    return {
        "prefix": prefix,
        "verdi_home": str(cfg.get("verdi_home") or "").strip(),
        "groups": groups,
    }


def server_command(profile):
    """`.mcp.json` / MCP 客户端用的连接：(ssh 别名, 远端命令串)。未配置返回 None。"""
    cfg = load_config(profile)
    if cfg is None:
        return None
    remote = "EDA_MCP_WORKSPACE_ROOT=%s EDA_MCP_ENABLED_GROUPS=%s %s/bin/eda-mcp-server" % (
        str(profile["mirror_root"]).rstrip("/"), ",".join(cfg["groups"]), cfg["prefix"])
    return str(profile["ssh_alias"]), remote


def mcp_json_text(profile):
    """仓库根 `.mcp.json` 的全文。剖面未配置时返回 None（不生成）。"""
    pair = server_command(profile)
    if pair is None:
        return None
    alias, remote = pair
    doc = {"mcpServers": {"eda": {"command": "ssh", "args": [alias, remote]}}}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def ssh_argv(profile, remote_cmd):
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            str(profile["ssh_alias"]), remote_cmd]


def run_ssh(profile, remote_cmd, run=None, **kwargs):
    """经 SSH 在远端执行一条命令串；`run` 可注入桩（测试沿用 FakeProc 做法）。"""
    run = run or subprocess.run
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("errors", "replace")
    return run(ssh_argv(profile, remote_cmd), **kwargs)


def rsync_line(profile):
    """把仓库同步到镜像根（NPI 打开前对齐当前 RTL 用）。

    与剖面 drivers 的 rsync 行同口径（--delete + sync_excludes；work/ 在排除表里，
    不会碰远端 `<sys>/work` 里的波形与 dbg 导出）。
    """
    local = (profile.get("local_root") or project_root()).rstrip("/") + "/"
    excludes = " ".join("--exclude %s" % item for item in profile.get("sync_excludes") or [])
    return "rsync -avz --delete %s %s %s:%s/" % (
        excludes, local, profile["ssh_alias"], str(profile["mirror_root"]).rstrip("/"))


def mirror_of(profile, rel):
    """子系统相对路径 → 镜像绝对路径（路径换算）。"""
    rel = str(rel).replace(os.sep, "/").lstrip("/")
    return "%s/%s" % (str(profile["mirror_root"]).rstrip("/"), rel)


def workdir(profile, scenario, sys_name, module):
    """远端工作目录，与剖面 drivers/sim.py 的场景目录约定一致。"""
    mirror = str(profile["mirror_root"]).rstrip("/")
    if scenario == "sys":
        return "%s/%s/work" % (mirror, sys_name)
    if scenario == "module":
        return "%s/%s/work/%s" % (mirror, sys_name, module)
    if scenario == "pubip":
        return "%s/pub_code/work/%s" % (mirror, module)
    raise ValueError("scenario 须为 sys、module 或 pubip")


def fsdb_remote_path(profile, scenario, sys_name, module, case, tag="wave"):
    """`<TB_DUMP_TAG>_case<N>.fsdb` 的远端路径。tag 默认 wave（tb_define.svh 的
    TB_DUMP_TAG 缺省值；TB_DUMP_TAG=… 变体编译的记录可显式传入）。"""
    return "%s/%s_case%d.fsdb" % (workdir(profile, scenario, sys_name, module), tag, int(case))


def remote_dbg_dir(profile, sys_name):
    """导出落点的远端侧：`<mirror_root>/<sys>/work/dbg`。"""
    return mirror_of(profile, "%s/work/dbg" % sys_name)


def local_dbg_dir(root, sys_name):
    """导出落点的本地侧：`<sys>/work/dbg`（工具产物，不入 git）。"""
    return os.path.join(root, sys_name, "work", "dbg")


def source_digest(root=None):
    """本地 `toolchain/eda-mcp/src` 的内容摘要（远端 SOURCE_DIGEST 与之比对）。"""
    base = os.path.join(root or project_root(), "toolchain", "eda-mcp", "src")
    if not os.path.isdir(base):
        raise FileNotFoundError("找不到 toolchain/eda-mcp/src（eda-mcp 源码未并入？）")
    digest = hashlib.sha256()
    found = 0
    for dirpath, dirnames, files in os.walk(base):
        dirnames[:] = sorted(item for item in dirnames if item != "__pycache__")
        for fn in sorted(files):
            if fn.endswith(".pyc") or fn.endswith(".o") or fn == "fsdbq":
                continue  # 编译产物不进摘要（与 .gitignore 同口径）
            path = os.path.join(dirpath, fn)
            digest.update(os.path.relpath(path, base).replace(os.sep, "/").encode())
            digest.update(b"\0")
            with open(path, "rb") as fh:
                digest.update(fh.read())
            found += 1
    if not found:
        raise FileNotFoundError("toolchain/eda-mcp/src 为空，无法计算源码摘要")
    return digest.hexdigest()
