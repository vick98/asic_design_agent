"""作业（长任务）管理。

VCS 编译、仿真、DC/PT 都是分钟级到小时级的任务，**不能让 MCP 调用阻塞**：
`submit` 立刻返回 `job_id`，客户端用 `job_status` / `job_log` 轮询，
需要同步时给 `wait_seconds`。

状态全部落盘（`<cache>/jobs/<id>.json`），所以 MCP 服务端重启也不丢——
进程是 `start_new_session` 起的独立进程组，退出码由包装脚本写进 `<id>.rc`。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import Config

__all__ = ["JobError", "Job", "JobManager"]

RUNNING = "running"
DONE = "completed"
FAILED = "failed"
KILLED = "killed"


class JobError(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    name: str
    cmd: str
    cwd: str
    log_path: str
    rc_path: str
    meta_path: str
    pid: Optional[int] = None
    started_at: float = 0.0
    ended_at: float = 0.0
    rc: Optional[int] = None
    state: str = RUNNING
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        end = self.ended_at or (time.time() if self.state == RUNNING else self.started_at)
        return max(0.0, end - self.started_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.id,
            "name": self.name,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "pid": self.pid,
            "state": self.state,
            "rc": self.rc,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_s": round(self.duration, 1),
            "log": self.log_path,
            **self.extra,
        }


class JobManager:
    def __init__(self, cfg: Optional[Config] = None, root: Optional[str] = None):
        self.cfg = cfg
        base = root or (
            os.path.join(cfg.cache_dir(), "jobs") if cfg is not None
            else os.path.expanduser("~/.cache/eda-mcp/jobs")
        )
        self.root = base
        os.makedirs(self.root, exist_ok=True)

    # ------------------------------------------------------------ 内部
    def _paths(self, job_id: str):
        d = os.path.join(self.root, job_id)
        return d, os.path.join(d, "job.json"), os.path.join(d, "run.log"), os.path.join(d, "run.rc")

    def _save(self, job: Job) -> None:
        tmp = job.meta_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(job.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, job.meta_path)

    def _load(self, job_id: str) -> Job:
        _d, meta, log, rc_path = self._paths(job_id)
        if not os.path.isfile(meta):
            raise JobError("作业不存在: %s" % job_id)
        with open(meta) as fh:
            d = json.load(fh)
        job = Job(
            id=d["job_id"],
            name=d.get("name", ""),
            cmd=d.get("cmd", ""),
            cwd=d.get("cwd", ""),
            log_path=log,
            rc_path=rc_path,
            meta_path=meta,
            pid=d.get("pid"),
            started_at=float(d.get("started_at") or 0.0),
            ended_at=float(d.get("ended_at") or 0.0),
            rc=d.get("rc"),
            state=d.get("state", RUNNING),
            extra={k: v for k, v in d.items() if k not in (
                "job_id", "name", "cmd", "cwd", "pid", "state", "rc",
                "started_at", "ended_at", "duration_s", "log")},
        )
        return self._refresh(job)

    @staticmethod
    def _pid_alive(pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError as exc:
            import errno

            return exc.errno == errno.EPERM

    def _refresh(self, job: Job) -> Job:
        if job.state != RUNNING:
            return job
        if os.path.isfile(job.rc_path):
            try:
                with open(job.rc_path) as fh:
                    job.rc = int(fh.read().strip() or 0)
            except (OSError, ValueError):
                job.rc = 0
            job.state = DONE if job.rc == 0 else FAILED
            job.ended_at = os.path.getmtime(job.rc_path)
            self._save(job)
            return job
        if not self._pid_alive(job.pid):
            # 进程没了但没有 rc：被外部杀掉或上次服务端退出时遗留
            job.state = KILLED
            job.ended_at = job.ended_at or time.time()
            self._save(job)
        return job

    # ------------------------------------------------------------ 对外
    def submit(
        self,
        name: str,
        cmd: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Job:
        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        d, meta, log, rc_path = self._paths(job_id)
        os.makedirs(d, exist_ok=True)

        workdir = cwd or os.getcwd()
        # 用包装脚本落退出码，这样 MCP 服务端重启后仍能判终态
        # 必须用子 shell 而不是 { }：命令里若含 exit，花括号形式会直接退出整个
        # 包装 shell，导致退出码文件永远不写（实测踩到）。
        wrapped = "( %s ) > %s 2>&1; echo $? > %s" % (cmd, shlex.quote(log), shlex.quote(rc_path))
        full_env = dict(os.environ)
        if env:
            full_env.update(env)

        proc = subprocess.Popen(
            ["bash", "-lc", wrapped],
            cwd=workdir,
            env=full_env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        job = Job(
            id=job_id,
            name=name,
            cmd=cmd,
            cwd=workdir,
            log_path=log,
            rc_path=rc_path,
            meta_path=meta,
            pid=proc.pid,
            started_at=time.time(),
            state=RUNNING,
            extra=extra or {},
        )
        self._save(job)
        self.prune()
        return job

    def get(self, job_id: str) -> Job:
        return self._load(job_id)

    def list(self, limit: int = 20, state: Optional[str] = None) -> List[Job]:
        out: List[Job] = []
        if not os.path.isdir(self.root):
            return out
        names = sorted(os.listdir(self.root), reverse=True)
        for n in names:
            if not os.path.isdir(os.path.join(self.root, n)):
                continue
            try:
                job = self._load(n)
            except JobError:
                continue
            if state and job.state != state:
                continue
            out.append(job)
            if len(out) >= limit:
                break
        return out

    def log(self, job_id: str, tail_lines: int = 200, grep: Optional[str] = None) -> str:
        job = self._load(job_id)
        try:
            with open(job.log_path, errors="replace") as fh:
                text = fh.read()
        except OSError:
            return ""
        if grep:
            try:
                rx = re.compile(grep)
            except re.error as exc:
                raise JobError("grep 正则非法: %s" % exc)
            text = "\n".join(ln for ln in text.splitlines() if rx.search(ln))
            if not text:
                return ""
        if tail_lines and tail_lines > 0:
            lines = text.splitlines()
            text = "\n".join(lines[-tail_lines:])
        return text

    def kill(self, job_id: str) -> Job:
        job = self._load(job_id)
        if job.state != RUNNING:
            return job
        pid = job.pid
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
        try:
            with open(job.rc_path, "w") as fh:
                fh.write("137")
        except OSError:
            pass
        return self._load(job_id)

    def wait(self, job_id: str, timeout: float = 0.0, poll: float = 0.5) -> Job:
        """等到终态或超时（timeout<=0 表示不等待，立即返回当前状态）。"""
        deadline = time.time() + max(0.0, timeout)
        job = self._load(job_id)
        while job.state == RUNNING and time.time() < deadline:
            time.sleep(poll)
            job = self._load(job_id)
        return job

    def prune(self, keep: Optional[int] = None) -> int:
        """只保留最近 N 个作业目录（防止 cache 无限增长）。"""
        limit = keep
        if limit is None:
            limit = int(self.cfg.get("jobs.max_jobs", 200)) if self.cfg is not None else 200
        if not os.path.isdir(self.root):
            return 0
        names = sorted((n for n in os.listdir(self.root)
                        if os.path.isdir(os.path.join(self.root, n))), reverse=True)
        removed = 0
        for n in names[limit:]:
            d = os.path.join(self.root, n)
            try:
                for fn in os.listdir(d):
                    os.remove(os.path.join(d, fn))
                os.rmdir(d)
                removed += 1
            except OSError:
                pass
        return removed
