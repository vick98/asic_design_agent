"""``eda-mcp doctor`` —— 环境自检。

一次把「换台 EDA 服务器要确认的事」全查完：工具存在性/可执行性、Verdi 与 FFR 库、
Xvfb、License、镜像根可写性、fsdbq 可用性；``--deep`` 再跑一次真实波形冒烟。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .config import Config, load as load_config

OK = "ok"
WARN = "warn"
FAIL = "fail"

_MARK = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}


def _run(cmd: List[str], timeout: int = 20) -> tuple:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or ""
    except Exception as exc:  # noqa: BLE001
        return 127, str(exc)


class Report:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def add(self, name: str, status: str, detail: str = "", hint: str = "") -> None:
        self.items.append(
            {"name": name, "status": status, "detail": detail, "hint": hint}
        )

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i["status"] == status)

    @property
    def failed(self) -> bool:
        return self.count(FAIL) > 0

    def conclusion(self) -> str:
        if self.count(FAIL):
            return "不可用：有 %d 项失败" % self.count(FAIL)
        if self.count(WARN):
            return "可主持（有 %d 项告警）" % self.count(WARN)
        return "可主持"


# ------------------------------------------------------------------ 各项检查


def _check_tool(rep: Report, cfg: Config, key: str, label: str, required: bool) -> Optional[str]:
    path = cfg.which(key)
    if not path:
        rep.add(
            label,
            FAIL if required else WARN,
            "未找到（配置项 %s）" % key,
            "在 ~/.config/eda-mcp/config.toml 里指定 %s 的绝对路径" % key,
        )
        return None
    rc, out = _run([path, "-version"], timeout=25)
    if rc != 0:
        rc, out = _run([path, "-h"], timeout=25)
    first = (out.strip().splitlines() or [""])[0][:110]
    rep.add(label, OK, "%s  %s" % (path, first))
    return path


def _check_verdi_ffr(rep: Report, cfg: Config) -> None:
    home = cfg.verdi_home()
    if not home:
        rep.add("Verdi / FFR", WARN, "未定位到 VERDI_HOME", "设置环境变量 VERDI_HOME")
        return
    ffr = os.path.join(home, "share", "FsdbReader", "linux64", "libnffr.so")
    hdr = os.path.join(home, "share", "FsdbReader", "ffrAPI.h")
    if os.path.isfile(ffr) and os.path.isfile(hdr):
        rep.add("Verdi / FFR", OK, "%s (libnffr.so + ffrAPI.h)" % home)
    else:
        rep.add(
            "Verdi / FFR",
            FAIL,
            "%s 下缺少 share/FsdbReader/{ffrAPI.h,linux64/libnffr.so}" % home,
            "确认 VERDI_HOME 指向 Verdi 安装根目录",
        )


def _check_fsdbq(rep: Report, cfg: Config) -> Optional[str]:
    exe = cfg.fsdbq()
    if not exe:
        rep.add(
            "fsdbq（FFR 波形小工具）",
            FAIL,
            "未找到",
            "运行 eda-mcp build-native --dest ~/.local/bin/fsdbq",
        )
        return None
    rc, out = _run([exe], timeout=15)
    usage = "usage:" in out
    rep.add("fsdbq（FFR 波形小工具）", OK if usage else WARN, "%s" % exe)
    return exe


def _check_xvfb(rep: Report, cfg: Config) -> None:
    if not cfg.get("xvfb.enabled", True):
        rep.add("Xvfb（Verdi 设计模型需要）", WARN, "配置里已禁用")
        return
    exe = cfg.path("xvfb.xvfb_bin") or "/usr/bin/Xvfb"
    if os.path.isfile(exe) and os.access(exe, os.X_OK):
        rep.add("Xvfb（Verdi 设计模型需要）", OK, exe)
    else:
        rep.add(
            "Xvfb（Verdi 设计模型需要）",
            FAIL,
            "不可执行: %s" % exe,
            "apt install xvfb；⚠️ 不要用 verdi/bin/Xvfb（坏包装脚本）",
        )


def _check_workspace(rep: Report, cfg: Config) -> None:
    root = cfg.path("eda.workspace_root")
    if not root:
        rep.add("镜像根 workspace_root", WARN, "未配置", "设置 eda.workspace_root")
        return
    if not os.path.isdir(root):
        rep.add("镜像根 workspace_root", FAIL, "目录不存在: %s" % root)
        return
    probe = os.path.join(root, ".eda_mcp_write_probe")
    try:
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        rep.add("镜像根 workspace_root", OK, "%s（可写）" % root)
    except OSError as exc:
        rep.add("镜像根 workspace_root", FAIL, "不可写: %s" % exc)


def _check_python(rep: Report) -> None:
    rep.add("Python", OK, "%s" % sys.version.split()[0])
    missing = []
    for mod in ("tomllib", "tomli"):
        try:
            __import__(mod)
            break
        except Exception:
            missing.append(mod)
    else:
        rep.add("TOML 解析", WARN, "无 tomllib/tomli，配置文件将被忽略", "upgrade to Python>=3.11")
        return
    rep.add("TOML 解析", OK, mod)
    try:
        import mcp  # noqa: F401

        rep.add("MCP SDK", OK, getattr(mcp, "__version__", "已安装"))
    except Exception:
        rep.add(
            "MCP SDK",
            WARN,
            "未安装（不影响 CLI 与波形通路）",
            "pip install 'eda-mcp[server]' 或从 install/vendor 离线安装",
        )


def _check_deep(rep: Report, cfg: Config, source: Optional[str]) -> None:
    if not source:
        rep.add("深检（波形冒烟）", WARN, "未提供 FSDB，跳过", "doctor --deep <file.fsdb>")
        return
    try:
        from .fsdb import open_fsdb

        fs = open_fsdb(source, cfg)
        info = fs.info()
        sigs = fs.signals(limit=5)
        rep.add(
            "深检（波形冒烟）",
            OK if sigs or info else FAIL,
            "%s scale_unit=%s min=%s max=%s 信号=%d"
            % (source, info.get("scale_unit"), info.get("min_time"), info.get("max_time"), len(sigs)),
        )
    except Exception as exc:  # noqa: BLE001
        rep.add("深检（波形冒烟）", FAIL, "%s" % exc)


# ------------------------------------------------------------------ 入口


def build_report(
    cfg: Optional[Config] = None, deep: bool = False, source: Optional[str] = None
) -> Report:
    c = cfg or load_config()
    rep = Report()
    _check_python(rep)
    _check_verdi_ffr(rep, c)
    _check_fsdbq(rep, c)
    _check_tool(rep, c, "eda.vcd2fsdb_bin", "vcd2fsdb", required=False)
    _check_tool(rep, c, "eda.vcs_bin", "VCS", required=False)
    _check_tool(rep, c, "eda.verdi_bin", "Verdi", required=False)
    _check_tool(rep, c, "eda.nlint_bin", "nLint", required=False)
    _check_tool(rep, c, "eda.dc_bin", "Design Compiler", required=False)
    _check_tool(rep, c, "eda.pt_bin", "PrimeTime", required=False)
    _check_xvfb(rep, c)
    _check_workspace(rep, c)
    if deep:
        _check_deep(rep, c, source)
    return rep


def run_doctor(deep: bool = False, as_json: bool = False, source: Optional[str] = None) -> int:
    cfg = load_config()
    rep = build_report(cfg, deep=deep, source=source or os.environ.get("EDA_MCP_SMOKE_FSDB"))
    if as_json:
        print(
            json.dumps(
                {
                    "conclusion": rep.conclusion(),
                    "sources": cfg.sources,
                    "items": rep.items,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("eda-mcp doctor   配置来源: %s" % (", ".join(cfg.sources) or "内置默认"))
        print("-" * 76)
        for item in rep.items:
            print("%s %-28s %s" % (_MARK[item["status"]], item["name"], item["detail"]))
            if item["hint"]:
                print("       %s-> %s" % (" " * 29, item["hint"]))
        print("-" * 76)
        print(
            "OK %d / WARN %d / FAIL %d"
            % (rep.count(OK), rep.count(WARN), rep.count(FAIL))
        )
        print("结论：%s" % rep.conclusion())
    return 1 if rep.failed else 0
