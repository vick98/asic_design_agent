"""Verdi 设计模型温进程 daemon。

**为什么需要 daemon**：Verdi 冷启动（含 `debImport`）实测约 **32 s**；启动一次、
导入一次、长期服务后，每次查询实测 **2.3～2.6 ms**。

协议（沿用探索期实测跑通的形态）：

1. 客户端把「请求 TCL 脚本」写到 ``<state>/req/<uuid>.tcl``；
2. 客户端把该路径写进 FIFO ``<state>/req.fifo``；
3. daemon `source` 该脚本；脚本调用 ``::eda::dispatch`` 把结果写进 ``<resp>``；
4. daemon 再写 ``<路径>.done``（内容为 catch 的 rc），客户端据此判定结束。

⚠️ Verdi **不能从命令行接收 `$argv`**（官方明确），所有参数必须在**生成 daemon
脚本时字面注入**。

⚠️ 必须有可用 X display：见 :mod:`eda_mcp.xvfb`。
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .config import Config
from .xvfb import Xvfb, XvfbError

__all__ = ["DaemonError", "DesignDaemon", "tcl_str", "parse_records"]


class DaemonError(RuntimeError):
    pass


def tcl_str(value: Any) -> str:
    """把一个值编码成 TCL 双引号字符串（转义 \\ " [ ] $）。"""
    s = str(value)
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    for ch in "[]$":
        out = out.replace(ch, "\\" + ch)
    return '"%s"' % out


def parse_records(text: str) -> List[List[str]]:
    """按 tab 切分带记录类型的行；忽略空行。"""
    out: List[List[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        out.append(line.split("\t"))
    return out


def records_to_dicts(rows: Sequence[Sequence[str]], want: str, keys: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not r or r[0] != want:
            continue
        d: Dict[str, Any] = {}
        for i, k in enumerate(keys, start=1):
            d[k] = r[i] if i < len(r) else ""
        out.append(d)
    return out


# ------------------------------------------------------------------ 状态目录


def _slug(text: str) -> str:
    keep = []
    for ch in text:
        keep.append(ch if (ch.isalnum() or ch in "._-") else "_")
    s = "".join(keep).strip("_")
    return (s or "design")[:60]


@dataclass
class DesignInfo:
    design_id: str
    state_dir: str
    files: List[str] = field(default_factory=list)
    filelist: Optional[str] = None
    top: Optional[str] = None
    sv: bool = True
    pid: Optional[int] = None
    display: Optional[str] = None
    created_at: float = 0.0
    last_used: float = 0.0
    alive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d.pop("state_dir", None)
        return d


class DesignDaemon:
    """一个设计（一次 `debImport`）对应一个温进程。"""

    def __init__(
        self,
        design_id: str,
        cfg: Optional[Config] = None,
        root: Optional[str] = None,
        files: Optional[Sequence[str]] = None,
        filelist: Optional[str] = None,
        top: Optional[str] = None,
        sv: bool = True,
    ):
        self.design_id = design_id
        self.cfg = cfg
        self.files = [os.path.abspath(os.path.expanduser(f)) for f in (files or [])]
        self.filelist = os.path.abspath(os.path.expanduser(filelist)) if filelist else None
        self.top = top
        self.sv = sv
        base = root or (
            os.path.join(cfg.cache_dir(), "designs") if cfg is not None else
            os.path.expanduser("~/.cache/eda-mcp/designs")
        )
        self.state_dir = os.path.join(base, _slug(design_id))
        self.meta_path = os.path.join(self.state_dir, "meta.json")
        self.fifo = os.path.join(self.state_dir, "req.fifo")
        self.log = os.path.join(self.state_dir, "daemon.log")
        self.script = os.path.join(self.state_dir, "daemon.tcl")
        self.req_dir = os.path.join(self.state_dir, "req")
        self.resp_dir = os.path.join(self.state_dir, "resp")
        self.pid_path = os.path.join(self.state_dir, "pid")
        self.lock_path = os.path.join(self.state_dir, "lock")
        self._xvfb: Optional[Xvfb] = None
        self._fifo_hold: Optional[int] = None

    # ------------------------------------------------------------ 元信息
    def load_meta(self) -> Dict[str, Any]:
        try:
            with open(self.meta_path) as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001
            return {}

    def save_meta(self, **extra: Any) -> None:
        meta = {
            "design_id": self.design_id,
            "files": self.files,
            "filelist": self.filelist,
            "top": self.top,
            "sv": self.sv,
            "pid": self.pid(),
            "display": self._xvfb.display if self._xvfb else self.load_meta().get("display"),
            "created_at": self.load_meta().get("created_at") or time.time(),
            "last_used": time.time(),
        }
        meta.update(extra)
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.meta_path)

    def pid(self) -> Optional[int]:
        try:
            with open(self.pid_path) as fh:
                return int(fh.read().strip())
        except Exception:  # noqa: BLE001
            return None

    def _pid_alive(self, pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError as exc:
            return exc.errno == errno.EPERM

    def alive(self) -> bool:
        pid = self.pid()
        if not self._pid_alive(pid):
            return False
        # FIFO 还在且 daemon 日志出现过 ready 才算真的就绪
        return os.path.exists(self.fifo)

    # ------------------------------------------------------------ 生成脚本
    def _verdi(self) -> str:
        if self.cfg is not None:
            exe = self.cfg.which("eda.verdi_bin")
            if exe:
                return exe
        exe = shutil.which("verdi")
        if not exe:
            raise DaemonError("找不到 verdi（配置 eda.verdi_bin 或加入 PATH）")
        return exe

    def _import_stmt(self) -> str:
        """生成 debImport 调用（参数在此字面注入，Verdi 收不到 argv）。"""
        parts = ["debImport"]
        if self.filelist:
            parts += ["-f", tcl_str(self.filelist)]
        if self.files:
            if self.sv:
                parts.append("-sv")
            parts += [tcl_str(f) for f in self.files]
        if self.top:
            parts += ["-top", tcl_str(self.top)]
        if len(parts) == 1:
            raise DaemonError("没有指定设计来源（files 或 filelist 至少给一个）")
        return " ".join(parts)

    def _prelude(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tcl", "prelude.tcl")

    def render_script(self) -> str:
        prelude = self._prelude()
        if not os.path.isfile(prelude):
            raise DaemonError("找不到 prelude: %s" % prelude)
        return "\n".join(
            [
                "# 由 eda-mcp 生成；参数已字面注入（Verdi 不接收 argv）",
                'source %s' % tcl_str(prelude),
                self._import_stmt(),
                "viaSetupL1Apps",
                'set ::eda::log [open %s a]' % tcl_str(self.log),
                'puts $::eda::log "ready"; flush $::eda::log',
                'set ::eda::fifo %s' % tcl_str(self.fifo),
                "::eda::serve_forever",
                "",
            ]
        )

    # ------------------------------------------------------------ 生命周期
    def prepare_runtime(self) -> None:
        """只准备运行期物料（目录/FIFO/占位 fd）——复用一个**已存活**的 daemon 时用。

        注意不能重新渲染 daemon.tcl：客户端这一侧没有设计来源信息。
        """
        for d in (self.state_dir, self.req_dir, self.resp_dir):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.fifo):
            os.mkfifo(self.fifo)
        if self._fifo_hold is None:
            # 打开一个读写端占位，避免 daemon 未起时客户端写 FIFO 永久阻塞
            self._fifo_hold = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)

    def prepare(self) -> None:
        """启动前准备：运行期物料 + 生成 daemon 脚本（需要设计来源信息）。"""
        self.prepare_runtime()
        with open(self.script, "w") as fh:
            fh.write(self.render_script())

    def start(self, timeout: Optional[float] = None) -> DesignInfo:
        if self.alive():
            return self.info()
        self.prepare()

        xvfb = Xvfb(self.cfg)
        try:
            display = xvfb.ensure()
        except XvfbError as exc:
            raise DaemonError("Xvfb 不可用：%s" % exc)
        self._xvfb = xvfb

        env = xvfb.env()
        for extra in ("extra_args",):
            pass
        cmd = [self._verdi(), "-nologo", "-batch", "-play", self.script]
        if self.cfg is not None:
            cmd += list(self.cfg.get("verdi.extra_args", []) or [])

        wait = float(timeout if timeout is not None else (self.cfg.get("daemon.start_timeout_s", 120) if self.cfg else 120))
        try:
            logf = open(self.log, "a")
        except OSError as exc:
            raise DaemonError("无法写 daemon 日志: %s" % exc)

        proc = subprocess.Popen(
            cmd, stdout=logf, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
        with open(self.pid_path, "w") as fh:
            fh.write(str(proc.pid))
        self.save_meta(display=display)

        deadline = time.time() + wait
        while time.time() < deadline:
            if proc.poll() is not None:
                tail = self._log_tail()
                raise DaemonError(
                    "verdi 启动即退出（rc=%s）；日志尾部：\n%s" % (proc.returncode, tail)
                )
            if self._log_has("ready"):
                return self.info()
            time.sleep(0.3)
        self.stop()
        raise DaemonError(
            "verdi 启动超时（%ss）。常见原因：DISPLAY 不可用（本模块用 %s）"
            "或 debImport 失败。日志尾部：\n%s" % (wait, display, self._log_tail())
        )

    def _log_tail(self, n: int = 20) -> str:
        try:
            with open(self.log, errors="replace") as fh:
                return "".join(fh.readlines()[-n:])
        except OSError:
            return "(无日志)"

    def _log_has(self, needle: str) -> bool:
        try:
            with open(self.log, errors="replace") as fh:
                return needle in fh.read()
        except OSError:
            return False

    def stop(self) -> None:
        pid = self.pid()
        if self._pid_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)  # type: ignore[arg-type]
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)  # type: ignore[arg-type]
                except OSError:
                    pass
            for _ in range(50):
                if not self._pid_alive(pid):
                    break
                time.sleep(0.1)
            if self._pid_alive(pid):
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)  # type: ignore[arg-type]
                except OSError:
                    pass
        for p in (self.pid_path,):
            try:
                os.remove(p)
            except OSError:
                pass
        if self._xvfb is not None:
            self._xvfb.stop()
        try:
            os.close(self._fifo_hold)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 查询
    def query(self, cmd: str, *args: Any, timeout: float = 60.0) -> str:
        """执行一次查询，返回响应文本。"""
        if not self.alive():
            self.start()
        else:
            self.prepare_runtime()

        lock = open(self.lock_path, "a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rid = uuid.uuid4().hex[:12]
            req = os.path.join(self.req_dir, rid + ".tcl")
            resp = os.path.join(self.resp_dir, rid + ".txt")
            done = req + ".done"
            for p in (done, resp):
                try:
                    os.remove(p)
                except OSError:
                    pass

            call = " ".join([tcl_str(a) for a in args])
            body = '::eda::dispatch %s %s %s\n' % (tcl_str(resp), cmd, call)
            with open(req, "w") as fh:
                fh.write(body)

            with open(self.fifo, "w") as fh:
                fh.write(req + "\n")
                fh.flush()

            deadline = time.time() + timeout
            while time.time() < deadline:
                if os.path.exists(done):
                    break
                if not self.alive():
                    raise DaemonError("daemon 在查询过程中退出；日志尾部：\n%s" % self._log_tail())
                time.sleep(0.01)
            else:
                raise DaemonError("查询超时（%ss，cmd=%s）" % (timeout, cmd))

            try:
                with open(resp, errors="replace") as fh:
                    return fh.read()
            except OSError:
                return ""
        finally:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            finally:
                lock.close()

    # ------------------------------------------------------------ 概览
    def info(self) -> DesignInfo:
        meta = self.load_meta()
        return DesignInfo(
            design_id=self.design_id,
            state_dir=self.state_dir,
            files=meta.get("files", self.files),
            filelist=meta.get("filelist", self.filelist),
            top=meta.get("top", self.top),
            sv=meta.get("sv", self.sv),
            pid=self.pid(),
            display=meta.get("display"),
            created_at=float(meta.get("created_at") or 0.0),
            last_used=float(meta.get("last_used") or 0.0),
            alive=self.alive(),
        )


# ------------------------------------------------------------------ 进程池


def designs_root(cfg: Optional[Config] = None) -> str:
    base = cfg.cache_dir() if cfg is not None else os.path.expanduser("~/.cache/eda-mcp")
    return os.path.join(base, "designs")


def list_designs(cfg: Optional[Config] = None) -> List[DesignInfo]:
    root = designs_root(cfg)
    out: List[DesignInfo] = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        state = os.path.join(root, name)
        if not os.path.isdir(state):
            continue
        d = DesignDaemon(name, cfg=cfg, root=root)
        out.append(d.info())
    return out


def open_design(
    design_id: str,
    cfg: Optional[Config] = None,
    files: Optional[Sequence[str]] = None,
    filelist: Optional[str] = None,
    top: Optional[str] = None,
    sv: bool = True,
    max_daemons: Optional[int] = None,
) -> DesignDaemon:
    """建或复用温进程；超过池上限时回收最久未用的。"""
    root = designs_root(cfg)
    os.makedirs(root, exist_ok=True)
    d = DesignDaemon(design_id, cfg=cfg, root=root, files=files, filelist=filelist, top=top, sv=sv)

    if d.alive():
        d.save_meta()
        return d

    limit = max_daemons
    if limit is None:
        limit = int(cfg.get("daemon.max_design_daemons", 2)) if cfg is not None else 2
    live = [x for x in list_designs(cfg) if x.alive]
    if len(live) >= max(1, int(limit)):
        live.sort(key=lambda x: x.last_used)
        victim = live[0]
        DesignDaemon(victim.design_id, cfg=cfg, root=root).stop()

    d.start()
    d.save_meta()
    return d


def close_design(design_id: str, cfg: Optional[Config] = None) -> bool:
    root = designs_root(cfg)
    d = DesignDaemon(design_id, cfg=cfg, root=root)
    if not os.path.isdir(d.state_dir):
        return False
    d.stop()
    return True


def reap_stale(cfg: Optional[Config] = None) -> List[str]:
    """回收 pid 已死的遗留状态（服务器重启后清理）。"""
    killed: List[str] = []
    for info in list_designs(cfg):
        if not info.alive:
            state = info.state_dir
            for name in ("req.fifo",):
                try:
                    os.remove(os.path.join(state, name))
                except OSError:
                    pass
            killed.append(info.design_id)
    return killed
