# 作者：vick 邮箱：ykun@yk9811.com

"""dbg / eda-mcp install / doctor --mcp 的 CLI 层测试。

与 test_dbg.py 的模块层用例互补：这里全部走 script/framework.py 的 main()
（进程内加载，不 spawn 子进程），SSH 与 rsync 用桩替换（FakeProc 做法）。
校验：三个新 CLI 入口的转发与退出码、远端命令行、导出落点 <sys>/work/dbg/、
dbg 前后 state.json 字节不变、安装前缀校验与 SOURCE_DIGEST、
`run sim --wave fsdb` 运行记录的 waves 字段与 dbg waves 的精确匹配。
"""

import contextlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import unittest

import yaml

from framework import eda_mcp, eda_mcp_deploy
from framework.engine import record_run
from framework.profile_run import load_profile
from framework.state import init_sys, load_state, state_path
from framework.tests.util import RepoTest, checkout_root

FLOW_DOC = """# {name} 处理流程

## 4. 节点表

| 节点 | 说明 | 来源 | 备注 |
|---|---|---|---|
| 加数 | 输入 | 上游 | — |
| 和 | 输出 | 本模块 | — |
"""

WAVE_JSON = json.dumps({
    "signal": [
        {"name": "top.clk", "wave": "p..."},
        {"name": "top.x", "wave": ".=", "data": ["d1"]},
    ]
})

_CLI_MOD = None


def cli_main(argv):
    """进程内调 script/framework.py 的 main()，返回 (退出码, stdout, stderr)。"""
    global _CLI_MOD
    if _CLI_MOD is None:
        path = os.path.join(checkout_root(), "script", "framework.py")
        spec = importlib.util.spec_from_file_location("adf_cli", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CLI_MOD = mod
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _CLI_MOD.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _patch_run(fake):
    """进程内替换 subprocess.run（CLI 层的 SSH/rsync 都从它过），返回原实现。"""
    real = subprocess.run
    subprocess.run = fake
    return real


class CliHelpTests(unittest.TestCase):
    """三个新入口都要出现在 --help 里（test_cli 的 README 命令清单由此转绿）。"""

    def test_new_entries_are_in_help(self):
        help_out = subprocess.check_output(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"), "--help"],
            text=True)
        for token in ("dbg", "eda-mcp", "--mcp"):
            self.assertIn(token, help_out)


class CliDbgTests(RepoTest):
    """`framework.py dbg ...`：CLI 转发、远端命令行、导出落点、退出码。"""

    def setUp(self):
        eda_mcp_deploy.clear_cache()
        self.name = "clidbg" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)
        base = os.path.join(self.root, self.name)
        os.makedirs(os.path.join(base, "rtl"), exist_ok=True)
        os.makedirs(os.path.join(base, "flow_doc"), exist_ok=True)
        rtl = os.path.join(base, "rtl", "alu.sv")
        if not os.path.isfile(rtl):
            with open(rtl, "w", encoding="utf-8") as fh:
                fh.write("module alu();\nendmodule\n")
        with open(os.path.join(base, "flow_doc", "%s_flow.md" % self.name),
                  "w", encoding="utf-8") as fh:
            fh.write(FLOW_DOC.format(name=self.name))
        self.state_file = state_path(self.root, self.name)

    # ------------------------------------------------------------- 桩与工具

    def _patch(self, fake):
        real = _patch_run(fake)
        self.addCleanup(setattr, subprocess, "run", real)

    def _plant_run(self):
        record_run(self.root, self.name, {
            "capability": "sim", "status": "pass", "summary": "sim pass",
            "profile_id": "p", "scope": {"scenario": "sys", "module": ""},
        })

    def _write_dbg(self, filename, text):
        path = os.path.join(eda_mcp.local_dbg_dir(self.root, self.name), filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def _state_bytes(self):
        with open(self.state_file, "rb") as fh:
            return fh.read()

    def _calls_with(self, calls, needle):
        return [cmd for cmd in calls if needle in cmd]

    def _fake_run(self, remote_digest=None, alive=None, doctor_ok=True):
        """CLI 层全套桩：SSH（eda_mcp.run_ssh 的 argv 形式）、rsync（shell 字符串）、
        bash -s（run sim 用）。返回 (run 桩, 命令行清单)。"""
        calls = []
        profile = load_profile()
        ok_digest = eda_mcp.source_digest(self.root)
        mirror = str(profile["mirror_root"]).rstrip("/")

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.endswith(" true"):
                return FakeProc()
            if "ls -1 " in cmd and "*.fsdb" in cmd:
                return FakeProc("%s/%s/work/wave_case1.fsdb\n" % (mirror, self.name))
            if "SOURCE_DIGEST" in cmd and "cat" in cmd:
                return FakeProc((remote_digest if remote_digest is not None
                                 else ok_digest) + "\n")
            if "SOURCE_DIGEST" in cmd:
                return FakeProc("written\n")
            if " npi list" in cmd:
                rows = "".join("%s alive=%s pid=1 display=:99 files=1\n" % (d, a)
                               for d, a in (alive or []))
                return FakeProc(rows)
            if "wave_extract" in cmd:
                res = {"beats": 2,
                       "nodes": [{"name": "加数",
                                  "file": "%s/%s/work/dbg/加数.txt" % (mirror, self.name),
                                  "lines": 2}]}
                # 顺便模拟远端真的写了导出文件（rsync 桩不搬东西）
                self._write_dbg("加数.txt", "0 10 b0001\n1 20 b0010\n")
                return FakeProc(json.dumps(res, ensure_ascii=False))
            if "eda-mcp wave" in cmd:
                return FakeProc("源文件: x  (timescale=1ns)\n" + WAVE_JSON)
            if "eda-mcp signals" in cmd:
                return FakeProc("=== 信号列表 ===\n  top.x\n")
            if "eda-mcp doctor" in cmd:
                items = ([{"name": "Python", "status": "ok", "detail": "3.x"},
                          {"name": "镜像根 workspace_root", "status": "ok",
                           "detail": "%s（可写）" % str(profile["mirror_root"]).rstrip("/")},
                          {"name": "fsdbq（FFR 波形小工具）", "status": "ok",
                           "detail": "/bin/fsdbq"}] if doctor_ok else [])
                return FakeProc(json.dumps({"items": items}, ensure_ascii=False))
            if cmd.startswith("rsync"):
                return FakeProc()
            return FakeProc()

        return run, calls

    # ------------------------------------------------------------- 各子命令

    def test_signals_via_cli(self):
        self._plant_run()
        run, calls = self._fake_run()
        self._patch(run)
        before = self._state_bytes()
        code, out, err = cli_main(["dbg", self.name, "signals", "--case", "3"])
        self.assertEqual(code, 0, out + err)
        mirror = str(load_profile()["mirror_root"]).rstrip("/")
        hit = self._calls_with(calls, "eda-mcp signals")
        self.assertEqual(len(hit), 1)
        self.assertIn("%s/%s/work/wave_case3.fsdb" % (mirror, self.name), hit[0])
        self.assertIn("top.x", out)
        self.assertEqual(before, self._state_bytes())

    def test_wave_export_via_cli_lands_in_work_dbg(self):
        self._plant_run()
        run, calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "wave", "--case", "2",
                                   "-s", "top.x", "-t", "100ns", "-c", "5"])
        self.assertEqual(code, 0, out + err)
        local = os.path.join(self.root, self.name, "work", "dbg", "case2_x.json")
        self.assertTrue(os.path.isfile(local), out)
        with open(local, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["signal"][1]["name"], "top.x")
        self.assertIn("-t 100ns -c 5", self._calls_with(calls, "eda-mcp wave")[0])
        self.assertIn("%s/work/dbg/case2_x.json" % self.name, out)

    def test_extract_via_cli_lands_in_work_dbg(self):
        self._plant_run()
        run, calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "extract", "--case", "1",
                                   "--clock", "top.clk", "--node", "加数=top.a"])
        self.assertEqual(code, 0, out + err)
        mirror = str(load_profile()["mirror_root"]).rstrip("/")
        hit = self._calls_with(calls, "eda-mcp wave_extract")
        self.assertEqual(len(hit), 1)
        self.assertIn("--clock top.clk", hit[0])
        self.assertIn("--node %s" % shlex.quote("加数=top.a"), hit[0])
        self.assertIn("--out-dir %s/%s/work/dbg" % (mirror, self.name), hit[0])
        local = os.path.join(self.root, self.name, "work", "dbg", "case1_加数.txt")
        self.assertTrue(os.path.isfile(local), out)
        self.assertIn("%s/work/dbg/case1_加数.txt" % self.name, out)

    def test_npi_trace_via_cli(self):
        run, calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "npi", "trace", "top.x"])
        self.assertEqual(code, 0, out + err)
        from framework.dbg import design_id
        did = design_id(self.root, self.name)
        self.assertIn("npi trace %s top.x --direction both --limit 200" % did,
                      self._calls_with(calls, "npi trace")[0])
        # 摘要对不上时先 rsync 对齐再重新打开设计
        self.assertTrue(self._calls_with(calls, "rsync"))
        self.assertLess(calls.index(self._calls_with(calls, "rsync")[0]),
                        calls.index(self._calls_with(calls, "npi open")[0]))

    def test_waves_via_cli(self):
        self._plant_run()
        run, _calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "waves"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("共 1 个 *.fsdb", out)
        self.assertIn("R001", out)

    def test_doctor_via_cli(self):
        run, calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", "doctor"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("结论：通过", out)
        self.assertEqual(len(self._calls_with(calls, "eda-mcp doctor")), 1)

    # ------------------------------------------------------------- 退出码

    def test_usage_error_exits_2(self):
        self._plant_run()
        run, calls = self._fake_run()
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "wave", "--case", "1", "-s", "top.x"])
        self.assertEqual(code, 2)
        self.assertIn("-t", out)
        self.assertEqual(self._calls_with(calls, "eda-mcp wave"), [])

    def test_version_mismatch_exits_3(self):
        run, calls = self._fake_run(remote_digest="0" * 64)
        self._patch(run)
        code, out, err = cli_main(["dbg", self.name, "signals", "--case", "1"])
        self.assertEqual(code, 3, out + err)
        self.assertIn("framework.py eda-mcp install", out)
        self.assertEqual(self._calls_with(calls, "eda-mcp signals"), [])

    # ------------------------------------------------------------- 状态冻结

    def test_state_json_byte_identical_across_dbg_cli(self):
        """dbg 各子命令走 main() 前后 state.json 字节不变（CLI 层端到端）。"""
        self._plant_run()
        run, _calls = self._fake_run()
        self._patch(run)
        before = self._state_bytes()
        for argv in (["dbg", self.name, "waves"],
                     ["dbg", self.name, "signals", "--case", "1"],
                     ["dbg", self.name, "wave", "--case", "1", "-s", "top.x",
                      "-t", "1ns", "-c", "1"],
                     ["dbg", self.name, "extract", "--case", "1", "--clock", "top.clk",
                      "--node", "加数=top.a"],
                     ["dbg", self.name, "npi", "trace", "top.x"],
                     ["dbg", "doctor"]):
            code, out, err = cli_main(argv)
            self.assertEqual(code, 0, (argv, out, err))
        self.assertEqual(before, self._state_bytes())


class CliInstallTests(RepoTest):
    """`framework.py eda-mcp install`：安装命令行、前缀校验、SOURCE_DIGEST。"""

    def setUp(self):
        eda_mcp_deploy.clear_cache()
        self.profile = load_profile()

    def _profile_path(self):
        return os.path.join(self.root, "toolchain", "profiles",
                            self.profile["id"], "profile.yaml")

    def _set_prefix(self, prefix):
        with open(self._profile_path(), encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        data["eda_mcp"]["prefix"] = prefix
        with open(self._profile_path(), "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True)

    def test_install_via_cli_writes_source_digest(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(" ".join(argv) if isinstance(argv, list) else str(argv))
            return FakeProc("[install] ok\n")

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)
        code, out, err = cli_main(["eda-mcp", "install"])
        self.assertEqual(code, 0, out + err)
        cfg = eda_mcp.load_config(self.profile)
        self.assertEqual(len(calls), 3, calls)
        self.assertIn("rsync -avz --delete", calls[0], "install 必须先同步镜像")
        self.assertIn("bash %s/toolchain/eda-mcp/install/install.sh --prefix %s --verdi-home %s" % (
            str(self.profile["mirror_root"]).rstrip("/"), cfg["prefix"], cfg["verdi_home"]), calls[1])
        digest = eda_mcp.source_digest(self.root)
        self.assertIn("SOURCE_DIGEST", calls[2])
        self.assertIn(digest, calls[2])
        self.assertIn("SOURCE_DIGEST 已写入", out)

    def test_install_via_cli_rejects_forbidden_prefixes(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(" ".join(argv) if isinstance(argv, list) else str(argv))
            return FakeProc()

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)
        with open(self._profile_path(), encoding="utf-8") as fh:
            original = fh.read()
        self.addCleanup(self._restore_profile, original)
        mirror = str(self.profile["mirror_root"]).rstrip("/")
        for prefix, needle in (("~/.local", "覆盖"), ("%s/eda-mcp" % mirror, "rsync --delete")):
            self._set_prefix(prefix)
            code, out, err = cli_main(["eda-mcp", "install"])
            self.assertEqual(code, 2, (prefix, out + err))
            self.assertIn("拒绝安装", out)
            self.assertIn(needle, out)
        self.assertEqual(calls, [], "被拒绝的安装不得发出任何远端命令")

    def test_install_aborts_when_mirror_sync_fails(self):
        """镜像同步失败即中止：不得用过期镜像硬装。"""
        calls = []

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.startswith("rsync"):
                return FakeProc("", "rsync: connection unexpectedly closed", returncode=23)
            return FakeProc("[install] ok\n")

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)
        code, out, err = cli_main(["eda-mcp", "install"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("同步镜像失败", out)
        self.assertIn("connection unexpectedly closed", out)
        self.assertEqual([item for item in calls if "install.sh" in item], [],
                         "同步失败后不得继续安装")

    def test_install_no_sync_skips_the_rsync(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(" ".join(argv) if isinstance(argv, list) else str(argv))
            return FakeProc("[install] ok\n")

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)
        code, out, err = cli_main(["eda-mcp", "install", "--no-sync"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(calls), 2, calls)
        self.assertIn("install.sh", calls[0])
        self.assertNotIn("rsync", " ".join(calls))

    def _restore_profile(self, original):
        with open(self._profile_path(), "w", encoding="utf-8") as fh:
            fh.write(original)


class CliDoctorMcpTests(RepoTest):
    """`framework.py doctor --mcp`：失败项带退出码与 stderr 末行；不带开关行为不变。"""

    def test_failure_reports_exit_code_and_last_stderr_line(self):
        calls = []

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.endswith(" true"):
                return FakeProc()
            if "SOURCE_DIGEST" in cmd:
                return FakeProc(eda_mcp.source_digest(self.root) + "\n")
            if "eda-mcp doctor" in cmd:
                # 远端 doctor 崩了：退出码 1、stderr 只有一行
                return FakeProc("", "nvstrings: cannot open shared object\n", 1)
            return FakeProc()

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)
        code, out, err = cli_main(["doctor", "--mcp"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("失败 远端 eda-mcp doctor", out)
        self.assertIn("退出码 1", out)
        self.assertIn("nvstrings: cannot open shared object", out)
        self.assertIn("结论：失败", out)

    def test_without_mcp_flag_behaviour_unchanged(self):
        code, out, err = cli_main(["doctor"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("跳过 ssh", out)
        self.assertNotIn("eda-mcp", out)


class WaveRecordTests(RepoTest):
    """`run sim --wave fsdb` 的运行记录带 waves 字段，dbg waves 精确匹配。"""

    WAVE = "wave_case1.fsdb"

    def setUp(self):
        self.name = "wavefield" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)
        profile = load_profile()
        mirror = str(profile["mirror_root"]).rstrip("/")
        self.wave_path = "%s/%s/work/%s" % (mirror, self.name, self.WAVE)
        self.calls = []

    def _fake(self):
        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            self.calls.append(cmd)
            if isinstance(argv, list) and argv[:1] == ["ssh"]:
                if argv[-1] == "bash -s":
                    return FakeProc("RESULT : PASS\n")
                if "ls -1 " in argv[-1] and ("*.fsdb" in argv[-1] or "*.vcd" in argv[-1]):
                    return FakeProc(self.wave_path + "\n")
                if "SOURCE_DIGEST" in cmd and "cat" in cmd:
                    return FakeProc(eda_mcp.source_digest(self.root) + "\n")
                return FakeProc()
            return FakeProc()

        real = _patch_run(run)
        self.addCleanup(setattr, subprocess, "run", real)

    def _run_sim(self, *extra):
        code, out, err = cli_main(["run", "sim", "--sys", self.name, *extra])
        self.assertEqual(code, 0, out + err)
        runs = load_state(self.root, self.name)["runs"]
        self.assertEqual(len(runs), 1, out + err)
        return runs[0]

    def test_fsdb_run_records_waves_and_dbg_matches_precisely(self):
        self._fake()
        row = self._run_sim("--wave", "fsdb")
        self.assertEqual(row["waves"], [self.wave_path])
        self.assertEqual(len([c for c in self.calls if "ls -1 " in c]), 1)
        # dbg waves 按 waves 字段精确匹配这条记录，不再标"（推断）"
        eda_mcp_deploy.clear_cache()
        code, out, err = cli_main(["dbg", self.name, "waves"])
        self.assertEqual(code, 0, out + err)
        self.assertIn(self.wave_path, out)
        self.assertIn("R001", out)
        self.assertIn("输入摘要一致", out)
        self.assertNotIn("（推断）", out)

    def test_off_run_has_no_waves_field(self):
        self._fake()
        row = self._run_sim()
        self.assertNotIn("waves", row)
        self.assertEqual([c for c in self.calls if "ls -1 " in c], [])

    def test_compile_only_run_does_not_list_waves(self):
        self._fake()
        row = self._run_sim("--wave", "fsdb", "--compile-only")
        self.assertNotIn("waves", row)
        self.assertEqual([c for c in self.calls if "ls -1 " in c], [])

    def test_record_run_keeps_waves_verbatim_and_dbg_falls_back_without_it(self):
        # record_run 原样写入 waves；旧记录没有 waves 字段时 dbg 退回推断（两条路径都工作）
        record_run(self.root, self.name, {
            "capability": "sim", "status": "pass", "summary": "sim pass",
            "profile_id": "p", "scope": {"scenario": "sys", "module": ""},
            "waves": ["/mirror/x/work/wave_case1.fsdb"],
        })
        row = load_state(self.root, self.name)["runs"][0]
        self.assertEqual(row["waves"], ["/mirror/x/work/wave_case1.fsdb"])
        record_run(self.root, self.name, {
            "capability": "sim", "status": "pass", "summary": "sim pass",
            "profile_id": "p", "scope": {"scenario": "sys", "module": ""},
        })
        self.assertNotIn("waves", load_state(self.root, self.name)["runs"][1])


if __name__ == "__main__":
    unittest.main()
