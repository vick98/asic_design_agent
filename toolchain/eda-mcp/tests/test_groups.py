"""工具组开关测试：MCP 工具列表与 CLI 子命令都按组过滤。

缺省（未设置 ``security.enabled_groups``）全开，与上游现状等价；
``EDA_MCP_ENABLED_GROUPS`` 环境变量覆盖配置（经 config.ENV_MAP）。
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp import cli, config, server  # noqa: E402
from eda_mcp.config import ALL_GROUPS, Config, defaults, enabled_groups  # noqa: E402


@contextlib.contextmanager
def _quiet_stderr():
    """静音被刻意触发的 argparse 报错。

    未启用组的子命令会让 ``parse_args`` 往 stderr 打多行 usage，断言的是
    ``SystemExit``，usage 本身不是被测行为，不该污染 selftest 输出。
    """
    with contextlib.redirect_stderr(io.StringIO()):
        yield


def _cfg(groups):
    data = defaults()
    data["security"]["enabled_groups"] = groups
    return Config(data)


def _names(cfg):
    return sorted(fn.__name__ for fn in server.tool_functions(cfg))


class TestEnabledGroups(unittest.TestCase):
    def test_default_is_all_groups(self):
        # 未设置（空列表 / None / 空串）= 全开，等价上游现状
        for empty in ([], None, ""):
            self.assertEqual(enabled_groups(_cfg(empty)), frozenset(ALL_GROUPS))

    def test_mapping_covers_every_tool(self):
        all_fns = {fn.__name__ for fn in server.tool_functions(_cfg(list(ALL_GROUPS)))}
        self.assertEqual(all_fns, set(server.TOOL_GROUPS))

    def test_mcp_tools_filtered_by_subset(self):
        names = _names(_cfg(["env", "fsdb"]))
        self.assertEqual(
            names,
            sorted(
                [
                    "eda_env_info", "eda_doctor",
                    "fsdb_info", "fsdb_scopes", "fsdb_signals", "fsdb_find",
                    "fsdb_value", "fsdb_wave", "fsdb_check",
                ]
            ),
        )
        # 未启用组的工具绝不出现
        self.assertNotIn("sim_run", names)
        self.assertNotIn("shell_run", names)
        self.assertNotIn("wave_extract", names)

    def test_env_and_wave_group(self):
        names = _names(_cfg(["wave"]))
        self.assertIn("wave_extract", names)
        self.assertIn("wave_gen", names)
        self.assertNotIn("fsdb_info", names)

    def test_unknown_group_rejected(self):
        with self.assertRaises(ValueError):
            enabled_groups(_cfg(["env", "nope"]))

    def test_env_var_override(self):
        saved = os.environ.get("EDA_MCP_ENABLED_GROUPS")
        try:
            os.environ["EDA_MCP_ENABLED_GROUPS"] = "env, wave"
            cfg = config.load()  # 环境变量是最高优先级，覆盖文件与默认
            self.assertEqual(enabled_groups(cfg), frozenset({"env", "wave"}))
        finally:
            if saved is None:
                os.environ.pop("EDA_MCP_ENABLED_GROUPS", None)
            else:
                os.environ["EDA_MCP_ENABLED_GROUPS"] = saved


class TestCliFiltering(unittest.TestCase):
    def test_disabled_group_subcommand_not_registered(self):
        parser = cli.build_parser(_cfg(["env", "fsdb"]))
        with _quiet_stderr():
            with self.assertRaises(SystemExit):
                parser.parse_args(["job", "list"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["shell", "ls"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["npi", "list"])

    def test_enabled_group_subcommand_registered(self):
        parser = cli.build_parser(_cfg(["fsdb"]))
        args = parser.parse_args(["info", "a.fsdb"])
        self.assertEqual(args.func, cli.cmd_info)

    def test_wave_extract_subcommand(self):
        parser = cli.build_parser(_cfg(["wave"]))
        args = parser.parse_args(
            ["wave_extract", "a.fsdb", "--clock", "top.clk", "--edge", "negedge",
             "--valid", "top.u.valid", "--node", "data=top.u.data",
             "--node", "q=top.u.q", "--start", "100", "--end", "200",
             "--out-dir", "out"]
        )
        self.assertEqual(args.func, cli.cmd_wave_extract)
        self.assertEqual(args.clock, "top.clk")
        self.assertEqual(args.edge, "negedge")
        self.assertEqual(args.valid, "top.u.valid")
        self.assertEqual(args.node, ["data=top.u.data", "q=top.u.q"])
        self.assertEqual(args.start, 100)
        self.assertEqual(args.end, 200)
        self.assertEqual(args.out_dir, "out")

    def test_default_registers_everything(self):
        parser = cli.build_parser(Config(defaults()))
        for argv in (["job", "list"], ["shell", "ls"], ["npi", "list"],
                     ["wave_extract", "a.fsdb", "--clock", "c", "--out-dir", "o"],
                     ["serve"]):
            args = parser.parse_args(argv)  # 不抛 SystemExit 即已注册
            self.assertTrue(callable(getattr(args, "func", None)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
