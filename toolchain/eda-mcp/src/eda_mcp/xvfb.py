"""托管 Xvfb。

Verdi 的 `-batch` **仍然需要真实可用的 X display**（`verdi -h` 说不需要，实测要）。
本模块负责：挑空闲 display、用**绝对路径**启动 `/usr/bin/Xvfb`、等待 socket 就绪、
进程退出时回收。

⚠️ 必须用 `/usr/bin/Xvfb`：`$VERDI_HOME/bin/Xvfb` 是一个损坏的包装脚本，
一旦进 PATH 就会遮蔽系统 Xvfb（报 `cannot execute: required file not found`）。
同理**不要**用 `xvfb-run`。
"""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import time
from typing import Optional

from .config import Config

__all__ = ["Xvfb", "XvfbError"]


class XvfbError(RuntimeError):
    pass


def _socket_path(display: str) -> str:
    num = display.lstrip(":").split(".")[0]
    return "/tmp/.X11-unix/X%s" % num


def _lock_path(display: str) -> str:
    num = display.lstrip(":").split(".")[0]
    return "/tmp/.X%s-lock" % num


def _in_use(display: str) -> bool:
    """socket 或 lock 存在即认为被占用（陈旧残留也一律避开，不冒险复用）。"""
    return os.path.exists(_socket_path(display)) or os.path.exists(_lock_path(display))


class Xvfb:
    """一个托管的 Xvfb 实例。"""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg
        self.display: Optional[str] = None
        self.proc: Optional[subprocess.Popen] = None
        self._started_by_us = False

    # ---- 配置 ----
    def _bin(self) -> str:
        path = None
        if self.cfg is not None:
            path = self.cfg.path("xvfb.xvfb_bin")
        path = path or "/usr/bin/Xvfb"
        if os.path.basename(path) == "Xvfb" and "verdi" in path.lower():
            raise XvfbError(
                "xvfb_bin 指向了 Verdi 自带的坏包装脚本（%s）；请改用 /usr/bin/Xvfb" % path
            )
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            raise XvfbError("Xvfb 不可执行: %s" % path)
        return path

    def _screen(self) -> str:
        if self.cfg is not None:
            return self.cfg.get("xvfb.screen", "1280x1024x24")
        return "1280x1024x24"

    def configured_display(self) -> Optional[str]:
        if self.cfg is not None:
            d = self.cfg.get("xvfb.display") or ""
            if d:
                return d if d.startswith(":") else ":" + str(d)
        return None

    def pick_display(self, start: int = 100, end: int = 200) -> str:
        for n in range(start, end):
            d = ":%d" % n
            if not _in_use(d):
                return d
        raise XvfbError("在 :%d..:%d 里找不到空闲 display" % (start, end))

    # ---- 生命周期 ----
    def ensure(self, timeout: float = 15.0) -> str:
        """确保有一个可用 display，返回其编号（如 ``:101``）。

        已有可用 display（配置指定或 :100 起第一个空闲）时直接复用，不再起进程。
        """
        want = self.configured_display()
        if want:
            if os.path.exists(_socket_path(want)):
                self.display = want
                return want
            self.display = want
        else:
            self.display = self.pick_display()

        exe = self._bin()
        cmd = [
            exe,
            self.display,
            "-screen",
            "0",
            self._screen(),
            "-nolisten",
            "tcp",
        ]
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise XvfbError("无法启动 Xvfb: %s" % exc)
        self._started_by_us = True

        deadline = time.time() + timeout
        sock = _socket_path(self.display)
        while time.time() < deadline:
            if os.path.exists(sock):
                return self.display
            if self.proc.poll() is not None:
                raise XvfbError(
                    "Xvfb 启动即退出（rc=%s）：%s" % (self.proc.returncode, " ".join(cmd))
                )
            time.sleep(0.1)
        self.stop()
        raise XvfbError("Xvfb 启动超时（%ss，未出现 %s）" % (timeout, sock))

    def stop(self) -> None:
        if self.proc is not None and self._started_by_us:
            try:
                self.proc.send_signal(signal.SIGTERM)
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except OSError as exc:
                if exc.errno != errno.ESRCH:
                    pass
        self.proc = None
        self._started_by_us = False

    def env(self) -> dict:
        env = dict(os.environ)
        if self.display:
            env["DISPLAY"] = self.display
        return env

    def __enter__(self) -> "Xvfb":
        self.ensure()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
