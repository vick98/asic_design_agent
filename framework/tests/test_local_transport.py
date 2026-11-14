# 作者：vick 邮箱：ykun@yk9811.com

"""Transport 接口与本机通道（LocalTransport）的用例。

本机剖面只在临时副本里造：`toolchain/profiles/local_echo/`，驱动是回显脚本，不接任何
真工具、不联网。仓库里不新增本机剖面目录（不做本地开源工具剖面）。
"""

import os
import subprocess
import unittest

from framework.profile_run import (
    LocalTransport, SshTransport, make_transport, run_other,
)
from framework.state import init_sys
from framework.tests.util import RepoTest


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# 测试剖面的驱动：假装工具就是回显。rsync_line / pull_line 返回标记串，本机通道不该
# 执行它们——真被 shell 跑过，标记就会出现在 stdout 与产物清单里。
ECHO_DRIVER = '''"""测试用回显驱动。"""


def rsync_line(profile):
    del profile
    return "echo SYNC_RAN_HERE"


def pull_line(profile, sys_name, capability, scope=None):
    del profile, sys_name, capability, scope
    return "echo PULL_RAN_HERE"


def lint_script(profile, sys_name, rtl_rel):
    del profile, rtl_rel
    return ("mkdir -p %s/lint\\n"
            "echo check ok > %s/lint/local_echo.rpt\\n"
            "echo lint RESULT: PASS\\n" % (sys_name, sys_name))


def parse(capability, log_text, artifact_dir=""):
    del capability, artifact_dir
    return {"errors": 0 if "RESULT: PASS" in (log_text or "") else 1}
'''

PROFILE_YAML = """id: %s
title: 测试用本机回显剖面
transport: %s
local_root: ""
mirror_root: ""
tools:
  lint: {available: true}
"""

SYNC_MARKER = "SYNC_RAN_HERE"


class LocalTransportTests(RepoTest):
    """本机通道自己的一层：执行、超时、回拉、按字段选通道。"""

    def _transport(self, **kwargs):
        profile = {"id": "local_echo", "transport": "local", "local_root": self.root}
        return LocalTransport(profile, None, **kwargs)

    def test_execute_runs_the_script_here(self):
        log, returncode = self._transport().execute('echo "RESULT: PASS"\n')
        self.assertEqual(returncode, 0)
        self.assertIn("RESULT: PASS", log)

    def test_execute_runs_in_the_profile_local_root(self):
        self._transport().execute("echo marker > local_marker.txt\n")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local_marker.txt")))

    def test_wall_clock_limit_comes_back_as_a_timeout(self):
        log, returncode = self._transport().execute("sleep 5\n", 1)
        self.assertEqual(returncode, 124)
        self.assertIn("WALL_TIMEOUT", log)

    def test_sync_is_a_noop(self):
        self.assertTrue(self._transport().sync())

    def test_pull_lists_local_products_without_transferring(self):
        _write(os.path.join(self.root, "demo", "lint", "chk.rpt"), "ok\n")
        transport = self._transport(sys_name="demo", capability="lint")
        calls = []
        real = subprocess.run

        def spy(argv, **kwargs):
            calls.append(argv)
            return real(argv, **kwargs)

        subprocess.run = spy
        try:
            artifacts = transport.pull(["demo/lint/lint.log"])
        finally:
            subprocess.run = real
        self.assertEqual(calls, [], "本机执行没有主机可回拉")
        self.assertEqual(artifacts, ["demo/lint/chk.rpt", "demo/lint/lint.log"])

    def test_make_transport_picks_by_profile_field(self):
        local = {"transport": "local", "local_root": self.root}
        self.assertIsInstance(make_transport(local, None), LocalTransport)
        ssh = {"transport": "ssh", "local_root": self.root, "ssh_alias": "h",
               "mirror_root": "/m"}
        self.assertIsInstance(make_transport(ssh, None), SshTransport)
        # 没有这个字段的旧剖面仍按 ssh 走。
        self.assertIsInstance(make_transport({"local_root": self.root}, None), SshTransport)
        with self.assertRaises(ValueError):
            make_transport({"transport": "bogus"}, None)


class LocalProfileRunTests(RepoTest):
    """`transport: local` 的剖面能真跑通：本机执行，不同步、不回拉。"""

    def setUp(self):
        super().setUp()
        self.name = "localsys"
        init_sys(self.root, self.name)
        self._write_profile("local_echo", "local")
        self._write_profile("local_bogus", "bogus")
        self.active = os.path.join(self.root, "toolchain", "active")
        with open(self.active, encoding="utf-8") as fh:
            self.original_active = fh.read()
        self.addCleanup(_write, self.active, self.original_active)

    def _write_profile(self, profile_id, transport):
        base = os.path.join(self.root, "toolchain", "profiles", profile_id)
        _write(os.path.join(base, "profile.yaml"), PROFILE_YAML % (profile_id, transport))
        _write(os.path.join(base, "drivers", "eda.py"), ECHO_DRIVER)

    def _spy_subprocess(self):
        calls = []
        real = subprocess.run

        def spy(argv, **kwargs):
            calls.append(argv)
            return real(argv, **kwargs)

        subprocess.run = spy
        self.addCleanup(setattr, subprocess, "run", real)
        return calls

    def test_local_profile_runs_here_without_ssh_or_rsync(self):
        _write(self.active, "local_echo\n")
        calls = self._spy_subprocess()
        result = run_other("lint", {"sys": self.name})
        self.assertEqual(result["status"], "pass", result)
        self.assertTrue(calls, "本机执行要真的起一个进程")
        for argv in calls:
            self.assertIsInstance(argv, list, argv)
            self.assertEqual(argv[0], "bash", argv)
        self.assertIn("%s/lint/local_echo.rpt" % self.name, result["artifacts"])
        self.assertIn("lock", result)

    def test_local_dry_run_preview_has_no_sync_line(self):
        _write(self.active, "local_echo\n")
        result = run_other("lint", {"sys": self.name, "dry_run": True})
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("lint RESULT: PASS", result["summary"])
        self.assertNotIn(SYNC_MARKER, result["summary"])

    def test_unknown_transport_is_an_error_result(self):
        _write(self.active, "local_bogus\n")
        result = run_other("lint", {"sys": self.name})
        self.assertEqual(result["status"], "error", result)
        self.assertIn("transport", result["summary"])


if __name__ == "__main__":
    unittest.main()
