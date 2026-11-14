"""工作区路径解析与安全护栏。

eda-mcp **只操作服务器上的镜像根**（同步由框架 `run` 的剖面驱动负责，上游旧脚本 `run_sim.sh` 不在本仓库）。
本模块负责：

* 场景 A/B/C → 工作目录 / `.f` 清单 / `-y` 搜索路径（与框架 `run` 的剖面驱动完全一致）；
* 路径白名单校验（所有路径必须在 ``security.allowed_roots`` 之下）；
* `.f` 清单里的**旧机器前缀**替换成镜像根（幂等）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import Config

__all__ = [
    "WorkspaceError",
    "Scenario",
    "resolve_scenario",
    "guard_path",
    "fix_filelist_prefixes",
    "ensure_work",
]

_SKIP_DIRS = {".git", "work", "dc", "pt", "lint", "node_modules"}


class WorkspaceError(RuntimeError):
    pass


@dataclass
class Scenario:
    kind: str            # A | B | C
    platform: str        # 平台名（子系统名或模块名）
    work: str            # 绝对工作目录
    filelist: str        # -f 的相对路径（相对 work）
    ydirs: List[str]     # -y 搜索路径（相对 work）
    rtl_dir: Optional[str] = None   # DC/PT 用的 RTL 绝对目录
    pos_dir: Optional[str] = None   # dc/ pt/ lint/ 归属目录

    def to_dict(self) -> Dict[str, object]:
        return {
            "scenario": self.kind,
            "platform": self.platform,
            "work": self.work,
            "filelist": self.filelist,
            "ydirs": self.ydirs,
            "rtl_dir": self.rtl_dir,
        }


def _root(cfg: Config) -> str:
    root = cfg.path("eda.workspace_root")
    if not root:
        raise WorkspaceError("未配置 eda.workspace_root（镜像根）")
    if not os.path.isdir(root):
        raise WorkspaceError("镜像根不存在: %s" % root)
    return os.path.abspath(root)


def resolve_scenario(
    cfg: Config, scenario: str, sys_name: Optional[str] = None, module: Optional[str] = None
) -> Scenario:
    """与框架 `run` 的剖面驱动场景映射保持一致（上游旧脚本不在本仓库；改一处必须同步另一处）。"""
    root = _root(cfg)
    kind = (scenario or "").strip().upper()
    if kind == "A":
        if not sys_name:
            raise WorkspaceError("场景 A 需要 sys 参数")
        return Scenario(
            kind="A",
            platform=sys_name,
            work=os.path.join(root, sys_name, "work"),
            filelist="../testbench/%s_tb.f" % sys_name,
            ydirs=["-y", "../rtl", "-y", "../../pub_code"],
            rtl_dir=os.path.join(root, sys_name, "rtl"),
            pos_dir=os.path.join(root, sys_name),
        )
    if kind == "B":
        if not (sys_name and module):
            raise WorkspaceError("场景 B 需要 sys 与 module 参数")
        return Scenario(
            kind="B",
            platform=module,
            work=os.path.join(root, sys_name, "work", module),
            filelist="../../testbench/%s/%s_tb.f" % (module, module),
            ydirs=["-y", "../../rtl", "-y", "../../../pub_code"],
            rtl_dir=os.path.join(root, sys_name, "rtl"),
            pos_dir=os.path.join(root, sys_name),
        )
    if kind == "C":
        if not module:
            raise WorkspaceError("场景 C 需要 module 参数")
        return Scenario(
            kind="C",
            platform=module,
            work=os.path.join(root, "pub_code", "work", module),
            filelist="../../testbench/%s/%s_tb.f" % (module, module),
            ydirs=["-y", "../.."],
            rtl_dir=os.path.join(root, "pub_code"),
            pos_dir=os.path.join(root, "pub_code"),
        )
    raise WorkspaceError("场景须为 A|B|C，收到: %r" % scenario)


def allowed_roots(cfg: Config) -> List[str]:
    roots = cfg.get("security.allowed_roots") or []
    out = [os.path.expanduser(os.path.expandvars(str(r))) for r in roots]
    ws = cfg.path("eda.workspace_root")
    if ws:
        out.append(ws)
    return [os.path.abspath(r) for r in out if r]


def guard_path(cfg: Config, path: str, must_exist: bool = False) -> str:
    """把路径规范化并校验它落在白名单根之下（越界直接报错，不静默放行）。"""
    p = os.path.abspath(os.path.expanduser(str(path)))
    roots = allowed_roots(cfg)
    if roots and not any(p == r or p.startswith(r.rstrip("/") + os.sep) for r in roots):
        raise WorkspaceError(
            "路径不在白名单内: %s\n  允许的根: %s\n  （改 security.allowed_roots 或 eda.workspace_root）"
            % (p, ", ".join(roots))
        )
    if must_exist and not os.path.exists(p):
        raise WorkspaceError("路径不存在: %s" % p)
    return p


_ABS_RE = re.compile(r"(/[\w./@+-]+)")


def fix_filelist_prefixes(cfg: Config) -> List[str]:
    """把镜像内所有 ``.f`` 里的**旧机器绝对前缀**替换成镜像根（幂等）。

    判定不依赖硬编码路径：镜像根的 basename（如 ``asic_design_agent``）在旧路径里
    出现的位置之后的部分，就是要保留的相对路径。也可用 ``eda.local_prefix``
    显式指定要替换的前缀。
    """
    root = _root(cfg)
    base = os.path.basename(root.rstrip("/"))
    explicit = cfg.path("eda.local_prefix")
    changed: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".f"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue

            if explicit:
                new = text.replace(explicit.rstrip("/"), root.rstrip("/"))
            else:
                out_lines = []
                for line in text.splitlines():
                    m = _ABS_RE.search(line)
                    if m:
                        p = m.group(1)
                        if not os.path.exists(p) and base in p.split("/"):
                            idx = p.rfind("/" + base + "/")
                            if idx >= 0:
                                line = line.replace(
                                    p, root.rstrip("/") + p[idx + len(base) + 1:]
                                )
                    out_lines.append(line)
                new = "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")

            if new != text:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new)
                changed.append(os.path.relpath(path, root))
    return changed


def ensure_work(work: str) -> str:
    os.makedirs(work, exist_ok=True)
    return work
