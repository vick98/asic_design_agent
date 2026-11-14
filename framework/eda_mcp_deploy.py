# 作者：vick 邮箱：ykun@yk9811.com

"""eda-mcp 安装与版本一致性。

- `install`：**先按剖面 driver 把本地工作树同步到镜像根**——`install.sh` 与源码都取自镜像，
  镜像过期会让安装莫名失败（"没有那个文件或目录"），所以安装前先对齐；再经剖面 `ssh_alias`
  执行镜像里的
  `bash <mirror_root>/toolchain/eda-mcp/install/install.sh --prefix <prefix> --verdi-home <verdi_home>`，
  成功后把本地 `toolchain/eda-mcp/src` 的内容摘要写到远端
  `<prefix>/lib/eda-mcp/SOURCE_DIGEST`。`sync=False`（CLI 的 `--no-sync`）跳过同步，
  直接用当前镜像状态安装。
- `version_check`：比对远端 SOURCE_DIGEST 与本地源码摘要；不一致给出
  "本地 eda-mcp 已更新，先运行 `framework.py eda-mcp install`"，
  供 `dbg` 按会话缓存使用（同进程不重复走 SSH）。

CLI 子命令（`framework.py eda-mcp install`）由后续包接线；本模块只提供可被
测试用桩驱动（`run` 参数，FakeProc 做法）的函数。
"""

import os
import subprocess

from framework import eda_mcp
from framework.paths import project_root

# 拒绝等于 ~/.local 的前缀（会覆盖 ~/.local/bin 下其他项目正在使用的 eda-mcp）；
# ~/.local 下的独立子目录允许。
FORBIDDEN_LOCAL_PREFIX = "~/.local"

# 会话内缓存：远端 SOURCE_DIGEST 按 (ssh 别名, prefix) 缓存一份，
# 同进程的多次 dbg 调用不重复走 SSH；install 成功后清空。
_REMOTE = {}


def clear_cache():
    """清掉会话内的远端摘要缓存（装完即查的场景由 install 自己清）。"""
    _REMOTE.clear()


class DeployError(Exception):
    """安装前缀等部署参数不合法。"""


def validate_prefix(prefix, mirror_root):
    """前缀校验。返回规范化后的绝对路径；不合法抛 DeployError（中文报错）。

    规则：
    1. 不得等于 `~/.local`（展开后比较）——会覆盖 `~/.local/bin` 下其他项目
       在用的 `eda-mcp`；`~/.local` 下的独立子目录允许。
    2. 不得位于 `mirror_root` 之内（含本身等于镜像根）——每次运行的
       `rsync --delete` 会把它删掉。
    """
    raw = str(prefix or "").strip()
    if not raw:
        raise DeployError("安装前缀为空：剖面 eda_mcp.prefix 未配置")
    norm = os.path.normpath(os.path.abspath(os.path.expanduser(raw)))
    local_home = os.path.normpath(os.path.expanduser(FORBIDDEN_LOCAL_PREFIX))
    if norm == local_home:
        raise DeployError(
            "安装前缀不能是 %s：会把 ~/.local/bin 下其他项目正在使用的 eda-mcp 一并覆盖；"
            "~/.local 下的独立子目录可以（如 ~/.local/opt/asic_design_agent/eda-mcp）"
            % FORBIDDEN_LOCAL_PREFIX)
    mirror = str(mirror_root or "").strip()
    if mirror:
        mirror_norm = os.path.normpath(os.path.abspath(os.path.expanduser(mirror)))
        if norm == mirror_norm or norm.startswith(mirror_norm.rstrip("/") + "/"):
            raise DeployError(
                "安装前缀 %s 位于镜像根 %s 之内：每次运行的 rsync --delete 会把它删掉，"
                "请换到镜像根之外的独立前缀" % (raw, mirror))
    return norm


def sync_mirror(profile, run=None):
    """把本地工作树同步到镜像根；返回 (是否成功, 说明)。

    用的是剖面 driver 的 `rsync_line`——与 `run` 同一行（`--delete` + `sync_excludes`），
    所以镜像口径与运行时一致。`run` 可注入桩（测试沿用 FakeProc 做法）。
    """
    from framework.profile_run import _driver
    drv = _driver(profile, "eda.py") or _driver(profile, "sim.py")
    if drv is None or not hasattr(drv, "rsync_line"):
        return False, "剖面 %s 没有可用的同步驱动（drivers/eda.py 或 sim.py）" % profile.get("id", "")
    line = drv.rsync_line(profile)
    run = run or subprocess.run
    proc = run(line, shell=True, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        detail = [item for item in ((proc.stdout or "") + (proc.stderr or "")).splitlines()
                  if item.strip()]
        return False, (detail[-1] if detail else "rsync 退出码 %s" % proc.returncode)
    return True, "镜像已同步（rsync）"


def install(root=None, profile=None, run=None, sync=True):
    """安装到 EDA 主机并写入 SOURCE_DIGEST。返回 (输出文本, 退出码)。

    `sync=True`（缺省）先同步镜像再装；同步失败即中止，不用过期镜像硬装。
    """
    root = root or project_root()
    if profile is None:
        from framework.profile_run import load_profile
        profile = load_profile()
    cfg = eda_mcp.load_config(profile)
    if cfg is None:
        return "剖面 %s 未配置 eda_mcp 字段，无法安装（见 toolchain/CONTRACT.md）" % profile.get("id", ""), 1
    try:
        validate_prefix(cfg["prefix"], profile.get("mirror_root"))
    except DeployError as exc:
        return "拒绝安装：%s" % exc, 2
    out = ""
    if sync:
        ok, text = sync_mirror(profile, run=run)
        if not ok:
            return ("同步镜像失败：%s\n"
                    "eda-mcp 的源码与安装脚本都取自远端镜像，镜像过期会让安装直接失败；"
                    "排除 rsync 问题后重试，或加 --no-sync 用当前镜像状态安装。\n" % text), 1
        out += text + "\n"
    mirror = str(profile["mirror_root"]).rstrip("/")
    script = "bash %s/toolchain/eda-mcp/install/install.sh --prefix %s" % (mirror, cfg["prefix"])
    if cfg["verdi_home"]:
        script += " --verdi-home %s" % cfg["verdi_home"]
    proc = eda_mcp.run_ssh(profile, script, run=run)
    out += (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        detail = [line for line in out.strip().splitlines() if line.strip()]
        return (out + "\n安装失败（退出码 %s）%s" % (
            proc.returncode, detail[-1] if detail else "")).strip() + "\n", 1
    digest = eda_mcp.source_digest(root)
    lib_dir = "%s/lib/eda-mcp" % cfg["prefix"]
    expr = _remote_path_expr(lib_dir)
    line = "mkdir -p %s && printf '%%s\\n' '%s' > %s/SOURCE_DIGEST" % (expr, digest, expr)
    put = eda_mcp.run_ssh(profile, line, run=run)
    if put.returncode != 0:
        detail = [item for item in ((put.stdout or "") + (put.stderr or "")).splitlines() if item.strip()]
        return "SOURCE_DIGEST 写入失败（退出码 %s）%s\n" % (
            put.returncode, detail[-1] if detail else ""), 1
    out += "\nSOURCE_DIGEST 已写入 %s/SOURCE_DIGEST（%s…）" % (lib_dir, digest[:12])
    clear_cache()
    return out + "\n", 0


def _remote_path_expr(prefix):
    """把剖面 prefix（可能以 ``~`` 开头）转成远端 shell 可展开的路径表达式。

    坑（实测踩过）：``~`` 在**单引号里不展开**——deploy 用单引号包路径时，
    ``mkdir -p '~/.local/...'`` 会在远端家目录下创建一个字面名为 ``~`` 的
    目录，SOURCE_DIGEST 被写进影子树，version_check 读的也是影子（两边一致
    所以自检还都能过）。正确做法：``~`` 前缀转成双引号 ``"$HOME/..."``
    （双引号内展开），其余部分保持字面；不以 ``~`` 开头的路径按原样单引号。
    """
    p = str(prefix or "").strip()
    if p == "~":
        return '"$HOME"'
    if p.startswith("~/"):
        return '"$HOME/' + p[2:] + '"'
    return "'%s'" % p


def _remote_digest(profile, cfg, run, use_cache):
    """读远端 SOURCE_DIGEST（会话缓存）；读不到返回 None。"""
    key = (str(profile.get("ssh_alias")), cfg["prefix"])
    if use_cache and key in _REMOTE:
        return _REMOTE[key]
    proc = eda_mcp.run_ssh(
        profile, "cat %s/SOURCE_DIGEST 2>/dev/null"
        % _remote_path_expr("%s/lib/eda-mcp" % cfg["prefix"]), run=run)
    fields = (proc.stdout or "").strip().split()
    value = fields[0] if (proc.returncode == 0 and fields) else None
    if use_cache:
        _REMOTE[key] = value
    return value


def version_check(profile=None, root=None, run=None, use_cache=True):
    """远端 SOURCE_DIGEST 与本地源码摘要比对。返回 (一致?, 说明文本)。"""
    root = root or project_root()
    if profile is None:
        from framework.profile_run import load_profile
        profile = load_profile()
    cfg = eda_mcp.load_config(profile)
    if cfg is None:
        return False, "剖面 %s 未配置 eda_mcp 字段" % profile.get("id", "")
    local = eda_mcp.source_digest(root)
    remote = _remote_digest(profile, cfg, run, use_cache)
    if not remote:
        result = (False, "远端还没有 SOURCE_DIGEST（未安装或旧版安装），先运行 framework.py eda-mcp install")
    elif remote != local:
        result = (False, "本地 eda-mcp 已更新，先运行 framework.py eda-mcp install")
    else:
        result = (True, "远端 eda-mcp 与本地源码摘要一致")
    return result
