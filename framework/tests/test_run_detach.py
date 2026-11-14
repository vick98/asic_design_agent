# 作者：vick 邮箱：ykun@yk9811.com

"""`run --detach` / `run wait` / `run jobs` 的用例。

本机剖面（`transport: local`）加回显驱动，不接真工具、不联网：

- `--detach` 立即返回作业号，后台子进程完整跑一遍（含 record_run）；
- `run wait` 拿到与同步运行一致的结论与运行记录号；
- `run jobs` 列出作业状态摘要；
- 运行失败、子进程失败、等待超时都非 0，且状态留在作业文件里。
"""

import json
import os
import re
import time
import unittest

from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, cli

# 测试剖面：本机执行，驱动只回显。rsync_line / pull_line 返回标记串，
# 本机通道不该执行它们——真被 shell 跑过，标记就会出现在 stdout 与产物清单里。
_DRIVER_HEAD = r'''"""测试用回显驱动。"""


def rsync_line(profile):
    del profile
    return "echo SYNC_RAN_HERE"


def pull_line(profile, sys_name, capability, scope=None):
    del profile, sys_name, capability, scope
    return "echo PULL_RAN_HERE"


def lint_script(profile, sys_name, rtl_rel):
    del profile, rtl_rel
    return (
'''

_DRIVER_TAIL = r'''    )


def parse(capability, log_text, artifact_dir=""):
    del capability, artifact_dir
    return {"errors": 0 if "RESULT: PASS" in (log_text or "") else 1}
'''

ECHO_BODY = r'''        "mkdir -p %s/lint\n"
        "echo check ok > %s/lint/local_echo.rpt\n"
        "echo lint RESULT: PASS\n" % (sys_name, sys_name)
'''

SLOW_BODY = r'''        "sleep 2\n"
        "mkdir -p %s/lint\n"
        "echo check ok > %s/lint/local_echo.rpt\n"
        "echo lint RESULT: PASS\n" % (sys_name, sys_name)
'''

FAIL_BODY = r'''        "echo lint RESULT: FAIL\n"
'''

PROFILE_YAML = """id: %s
title: 测试用本机回显剖面
transport: local
local_root: ""
mirror_root: ""
tools:
  lint: {available: true}
"""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class RunDetachTests(RepoTest):
    """run 的后台作业面：detach 立即返回、wait 对齐同步运行、jobs 看状态。"""

    def setUp(self):
        super().setUp()
        self.name = "detach" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)
        self._write_profile("local_echo", ECHO_BODY)
        self._write_profile("local_slow", SLOW_BODY)
        self._write_profile("local_fail", FAIL_BODY)
        self.active = os.path.join(self.root, "toolchain", "active")
        self._activate("local_echo")

    def _write_profile(self, profile_id, body):
        base = os.path.join(self.root, "toolchain", "profiles", profile_id)
        _write(os.path.join(base, "profile.yaml"), PROFILE_YAML % profile_id)
        _write(os.path.join(base, "drivers", "eda.py"), _DRIVER_HEAD + body + _DRIVER_TAIL)

    def _activate(self, profile_id):
        _write(self.active, profile_id + "\n")

    def _detach(self, *extra):
        proc = cli(self.root, "run", "lint", "--sys", self.name, "--detach", *extra)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        match = re.search(r"后台作业已启动：(\S+)", proc.stdout)
        self.assertIsNotNone(match, "detach 输出里要有作业号：\n" + proc.stdout)
        return match.group(1), proc

    def _wait(self, job_id, *extra):
        return cli(self.root, "run", "wait", "--job", job_id, *extra)

    def _job_path(self, job_id):
        return os.path.join(self.root, self.name, "work", "jobs", job_id + ".json")

    def _read_job(self, job_id):
        path = self._job_path(job_id)
        self.assertTrue(os.path.isfile(path), "作业文件不存在：%s" % path)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_detach_is_immediate_then_wait_times_out_and_completes(self):
        """慢运行下 detach 立即返回；wait 先超时非 0，再等到与同步一致的结论。"""
        self._activate("local_slow")
        start = time.monotonic()
        job_id, proc = self._detach()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.5, "detach 不得等运行结束（用时 %.2fs）" % elapsed)
        self.assertIn("作业文件", proc.stdout)

        job = self._read_job(job_id)
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["capability"], "lint")
        self.assertEqual(job["sys"], self.name)
        self.assertEqual(job["request"]["sys"], self.name)
        self.assertIn(job["status"], ("pending", "running"), job)
        self.assertTrue(job["created_at"])

        timed = self._wait(job_id, "--timeout", "0.2")
        self.assertNotEqual(timed.returncode, 0, timed.stdout + timed.stderr)
        self.assertIn("超时", timed.stdout + timed.stderr)

        waited = self._wait(job_id, "--timeout", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
        self.assertIn("lint pass", waited.stdout)
        self.assertIn("status: pass", waited.stdout)
        self.assertIn("已记入运行记录：R001", waited.stdout)

        job = self._read_job(job_id)
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(job["result"]["status"], "pass")
        self.assertEqual(job["record"], "R001")
        self.assertEqual(job["exit_code"], 0)
        self.assertGreater(job["pid"], 0)
        self.assertTrue(job["started_at"])
        self.assertTrue(job["finished_at"])
        runs = load_state(self.root, self.name)["runs"]
        self.assertEqual(len(runs), 1, "运行记录只在完成时写一次")

    def test_wait_matches_the_synchronous_run(self):
        sync = cli(self.root, "run", "lint", "--sys", self.name)
        self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
        job_id, _proc = self._detach()
        waited = self._wait(job_id, "--timeout", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
        runs = load_state(self.root, self.name)["runs"]
        self.assertEqual(len(runs), 2, "同步一次 + 后台一次")
        sync_run, async_run = runs
        self.assertEqual(sync_run["id"], "R001")
        self.assertEqual(async_run["id"], "R002")
        for key in ("capability", "status", "summary", "checks", "artifacts", "scope"):
            self.assertEqual(async_run[key], sync_run[key], key)

    def test_jobs_lists_the_status_summary(self):
        job_id, _proc = self._detach()
        waited = self._wait(job_id, "--timeout", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
        listing = cli(self.root, "run", "jobs", "--sys", self.name)
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn(job_id, listing.stdout)
        self.assertIn("lint", listing.stdout)
        self.assertIn("done", listing.stdout)

    def test_failed_run_keeps_failed_status_and_records_once(self):
        self._activate("local_fail")
        job_id, _proc = self._detach()
        waited = self._wait(job_id, "--timeout", "30")
        self.assertEqual(waited.returncode, 1, waited.stdout + waited.stderr)
        self.assertIn("lint fail", waited.stdout)
        self.assertIn("status: fail", waited.stdout)
        self.assertIn("已记入运行记录：R001", waited.stdout)
        job = self._read_job(job_id)
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["result"]["status"], "fail")
        self.assertEqual(job["exit_code"], 1)
        self.assertGreater(job["pid"], 0)
        runs = load_state(self.root, self.name)["runs"]
        self.assertEqual(len(runs), 1, "运行记录只在完成时写一次")
        self.assertEqual(runs[0]["status"], "fail")

    def test_background_failure_keeps_failed_status(self):
        """后台子进程自己失败（剖面不存在）也要在作业文件里留状态。"""
        self._activate("no_such_profile")
        job_id, _proc = self._detach()
        waited = self._wait(job_id, "--timeout", "30")
        self.assertEqual(waited.returncode, 1, waited.stdout + waited.stderr)
        self.assertIn("失败", waited.stdout + waited.stderr)
        job = self._read_job(job_id)
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("剖面不存在", job.get("error") or "")
        self.assertFalse(job.get("result"))
        self.assertEqual(load_state(self.root, self.name)["runs"], [])

    def test_wait_reports_an_unknown_job(self):
        proc = cli(self.root, "run", "wait", "--job", "no-such-job-001", "--timeout", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("找不到作业", proc.stdout + proc.stderr)

    def test_detach_requires_sys_and_rejects_dry_run(self):
        no_sys = cli(self.root, "run", "lint", "--detach")
        self.assertEqual(no_sys.returncode, 2, no_sys.stdout + no_sys.stderr)
        self.assertIn("--sys", no_sys.stderr)
        dry = cli(self.root, "run", "lint", "--sys", self.name, "--detach", "--dry-run")
        self.assertEqual(dry.returncode, 2, dry.stdout + dry.stderr)
        self.assertIn("--dry-run", dry.stderr)

    def test_hidden_execute_entry_is_not_in_help(self):
        run_help = cli(self.root, "run", "--help")
        self.assertIn("--detach", run_help.stdout)
        self.assertIn("--job", run_help.stdout)
        self.assertNotIn("_execute-job", run_help.stdout)
        self.assertNotIn("_execute-job", cli(self.root, "--help").stdout)


if __name__ == "__main__":
    unittest.main()
