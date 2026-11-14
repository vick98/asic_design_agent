"""配置加载与工具自动探测。

分层（后者覆盖前者）::

    ① 内置默认（按 $VERDI_HOME / $VCS_HOME / PATH 自动探测）
    ② /etc/eda-mcp/config.toml        （机器级）
    ③ ~/.config/eda-mcp/config.toml   （用户级，推荐）
    ④ 环境变量 EDA_MCP_*              （最高优先级）

包里**没有任何硬编码的服务器路径**——换个 EDA 机只改配置或环境变量。
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

try:  # Python >= 3.11
    import tomllib as _toml
except Exception:  # pragma: no cover - 3.9/3.10 回退
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None  # type: ignore

SERVER_CONFIG = "/etc/eda-mcp/config.toml"
USER_CONFIG = os.path.expanduser("~/.config/eda-mcp/config.toml")

# 环境变量名 -> 配置键路径
ENV_MAP = {
    "EDA_MCP_TRANSPORT": "server.transport",
    "EDA_MCP_HOST": "server.host",
    "EDA_MCP_PORT": "server.port",
    "EDA_MCP_WORKSPACE_ROOT": "eda.workspace_root",
    "EDA_MCP_VCS_BIN": "eda.vcs_bin",
    "EDA_MCP_VERDI_BIN": "eda.verdi_bin",
    "EDA_MCP_VCD2FSDB_BIN": "eda.vcd2fsdb_bin",
    "EDA_MCP_NLINT_BIN": "eda.nlint_bin",
    "EDA_MCP_DC_BIN": "eda.dc_bin",
    "EDA_MCP_PT_BIN": "eda.pt_bin",
    "EDA_MCP_VERDI_HOME": "verdi.verdi_home",
    "EDA_MCP_FSDBQ_BIN": "fsdb.fsdbq_bin",
    "EDA_MCP_FSDB_VERDI_HOME": "fsdb.verdi_home",
    "EDA_MCP_FSDB_ZLIB": "fsdb.zlib",
    "EDA_MCP_XVFB_BIN": "xvfb.xvfb_bin",
    "EDA_MCP_DISPLAY": "xvfb.display",
    "EDA_MCP_CACHE_DIR": "jobs.cache_dir",
    "EDA_MCP_ALLOW_SHELL": "security.allow_shell",
    "EDA_MCP_ENABLED_GROUPS": "security.enabled_groups",
}

# 工具组的合法取值。空（未配置）= 全开，与上游现状等价。
ALL_GROUPS = ("env", "fsdb", "wave", "npi", "flow", "shell")


def _deep_merge(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in other.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_toml(path: str) -> Dict[str, Any]:
    if _toml is None or not os.path.isfile(path):
        return {}
    with open(path, "rb") as fh:
        return _toml.load(fh)


def _set_dotted(cfg: Dict[str, Any], dotted: str, value: Any) -> None:
    cur = cfg
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _coerce(text: str) -> Any:
    low = text.strip().lower()
    if low in ("true", "1", "yes", "on"):
        return True
    if low in ("false", "0", "no", "off"):
        return False
    try:
        return int(text)
    except ValueError:
        return text


def _which(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    found = shutil.which(name)
    return found or (name if os.path.isfile(name) else None)


def defaults() -> Dict[str, Any]:
    """内置默认：全部按环境变量 / PATH 探测，不含任何机器相关常量。"""
    verdi_home = os.environ.get("VERDI_HOME") or ""
    vcs_home = os.environ.get("VCS_HOME") or ""
    cfg: Dict[str, Any] = {
        "server": {"transport": "stdio", "host": "127.0.0.1", "port": 8710},
        "eda": {
            "workspace_root": os.environ.get("EDA_MCP_WORKSPACE_ROOT") or "",
            "vcs_bin": "vcs",
            "verdi_bin": "verdi",
            "vcd2fsdb_bin": "vcd2fsdb",
            "nlint_bin": "nLint",
            "dc_bin": "dc_shell",
            "pt_bin": "pt_shell",
        },
        "verdi": {"verdi_home": verdi_home, "extra_args": [], "import_timeout_s": 300},
        "fsdb": {
            "fsdbq_bin": "",
            "verdi_home": verdi_home,
            "zlib": "",
            "max_changes": 2000,
        },
        "xvfb": {
            "enabled": True,
            "xvfb_bin": "/usr/bin/Xvfb",  # 必须绝对路径：verdi/bin/Xvfb 是坏的包装脚本
            "screen": "1280x1024x24",
            "display": "",
        },
        "daemon": {
            "max_design_daemons": 2,
            "idle_ttl_s": 1800,
            "start_timeout_s": 120,
        },
        "jobs": {"cache_dir": "~/.cache/eda-mcp", "max_jobs": 200},
        "security": {
            "allow_shell": False,
            "allowed_roots": [os.path.expanduser("~")],
            "enabled_groups": [],  # 空 = 全部工具组（与上游现状等价）；取值见 ALL_GROUPS
        },
        "_probe": {"vcs_home": vcs_home, "path": os.environ.get("PATH", "")},
    }
    return cfg


def enabled_groups(cfg: Optional["Config"] = None) -> frozenset:
    """解析 ``security.enabled_groups``（工具组开关）。

    * 未设置 / 空串 / 空列表 -> 全部组（与上游现状等价：缺省全开）；
    * 字符串按逗号分隔，列表逐项取；
    * 非法组名直接报错（宁可启动失败，不静默放开或静默吞掉）。
    """
    raw = cfg.get("security.enabled_groups") if cfg is not None else None
    if raw is None:
        return frozenset(ALL_GROUPS)
    if isinstance(raw, str):
        items = [p.strip() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip() for p in raw]
    else:
        raise ValueError(
            "security.enabled_groups 必须是逗号分隔字符串或列表，得到: %r" % (raw,)
        )
    items = [p for p in items if p]
    if not items:
        return frozenset(ALL_GROUPS)
    unknown = sorted(set(items) - set(ALL_GROUPS))
    if unknown:
        raise ValueError(
            "security.enabled_groups 含未知工具组: %s（合法取值: %s）"
            % (", ".join(unknown), ", ".join(ALL_GROUPS))
        )
    return frozenset(items)


class Config:
    """点号取值的只读配置视图。"""

    def __init__(self, data: Dict[str, Any], sources: Optional[List[str]] = None):
        self._d = data
        self.sources = sources or []

    # ---- 取值 ----
    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self._d
        for p in dotted.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def path(self, dotted: str, default: Optional[str] = None) -> Optional[str]:
        """取一个可执行文件/目录路径，展开 ~ 与 $VAR。"""
        raw = self.get(dotted, default)
        if not raw:
            return None
        return os.path.expanduser(os.path.expandvars(str(raw)))

    def which(self, dotted: str) -> Optional[str]:
        return _which(self.path(dotted))

    def as_dict(self) -> Dict[str, Any]:
        return self._d

    # ---- 探测 ----
    def verdi_home(self) -> Optional[str]:
        home = self.path("fsdb.verdi_home") or self.path("verdi.verdi_home")
        if home and os.path.isdir(home):
            return home
        for cand in ("/opt/synopsys/verdi", "/usr/synopsys/verdi"):
            if os.path.isdir(cand):
                return cand
        # 从 verdi 可执行文件反推
        exe = self.which("eda.verdi_bin")
        if exe:
            guess = os.path.dirname(os.path.dirname(os.path.realpath(exe)))
            if os.path.isdir(os.path.join(guess, "share", "FsdbReader")):
                return guess
        return home or None

    def fsdbq(self) -> Optional[str]:
        """定位 fsdbq：配置 -> 包内 native 目录（安装期编译产物）。"""
        raw = self.path("fsdb.fsdbq_bin")
        if raw and os.path.isfile(raw) and os.access(raw, os.X_OK):
            return raw
        here = os.path.dirname(os.path.abspath(__file__))
        for cand in (
            os.path.join(here, "native", "fsdbq"),          # 源码树内构建
            os.path.join(here, "bin", "fsdbq"),             # 打包安装
            os.path.expanduser("~/.local/bin/fsdbq"),
            "/opt/eda-mcp/bin/fsdbq",
        ):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        return _which("fsdbq")

    def cache_dir(self) -> str:
        return os.path.expanduser(self.path("jobs.cache_dir") or "~/.cache/eda-mcp")


def load(extra_paths: Optional[List[str]] = None) -> Config:
    """按分层规则加载配置。"""
    sources: List[str] = []
    data = defaults()

    for path in [SERVER_CONFIG, USER_CONFIG] + list(extra_paths or []):
        loaded = _load_toml(path)
        if loaded:
            data = _deep_merge(data, loaded)
            sources.append(path)

    for env_name, dotted in ENV_MAP.items():
        if env_name in os.environ:
            _set_dotted(data, dotted, _coerce(os.environ[env_name]))
            sources.append("env:" + env_name)

    # 缺省探测：workspace_root 未设时不强猜（不假设 $HOME/proj/<仓库> 之类路径）
    if not data["eda"].get("workspace_root"):
        data["eda"]["workspace_root"] = ""

    if not data["fsdb"].get("max_changes"):
        data["fsdb"]["max_changes"] = 2000

    return Config(data, sources)
