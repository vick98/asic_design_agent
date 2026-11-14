# 作者：vick 邮箱：ykun@yk9811.com

"""剖面 `eda_mcp` 字段、连接命令拼装与 `.mcp.json` 生成的用例。"""

import os
import unittest

from framework import eda_mcp
from framework.hosts.render import render
from framework.profile_run import load_profile
from framework.tests.util import RepoTest


def _cut_eda_mcp_field(root):
    """在副本剖面里去掉 eda_mcp 字段（返回恢复函数）。"""
    path = os.path.join(root, "toolchain", "profiles", "example", "profile.yaml")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.split("eda_mcp:")[0])

    def restore():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return restore


class McpConfigTests(RepoTest):
    def test_mcp_json_matches_render_byte_for_byte(self):
        """`.mcp.json` 生成物与渲染结果逐字节一致，且带 mirror_root 与四个组名。"""
        profile = load_profile()
        written = render()
        path = os.path.join(self.root, ".mcp.json")
        self.assertIn(path, written)
        expected = eda_mcp.mcp_json_text(profile)
        self.assertTrue(expected)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), expected.encode("utf-8"))
        # 连接命令：ssh <alias> EDA_MCP_WORKSPACE_ROOT=<mirror> \
        #   EDA_MCP_ENABLED_GROUPS=<groups> <prefix>/bin/eda-mcp-server
        self.assertIn('"command": "ssh"', expected)
        self.assertIn(profile["ssh_alias"], expected)
        self.assertIn("EDA_MCP_WORKSPACE_ROOT=%s" % profile["mirror_root"], expected)
        self.assertIn("EDA_MCP_ENABLED_GROUPS=env,fsdb,wave,npi", expected)
        self.assertIn("~/.local/opt/asic_design_agent/eda-mcp/bin/eda-mcp-server", expected)
        # 工作根不另写字段：只有 WORKSPACE_ROOT 一个环境变量
        self.assertEqual(expected.count("EDA_MCP_"), 2)

    def test_no_eda_mcp_field_generates_nothing(self):
        """剖面没有 eda_mcp 字段时不生成（已存在的旧文件也不擅自删）。"""
        restore = _cut_eda_mcp_field(self.root)
        path = os.path.join(self.root, ".mcp.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("stale\n")
            written = render()
            self.assertNotIn(path, written)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "stale\n")
        finally:
            restore()
            if os.path.exists(path):
                os.remove(path)

    def test_unconfigured_profile_expresses_not_configured(self):
        """剖面无 eda_mcp 字段时助手要能表达"未配置"（返回 None，不抛异常）。"""
        profile = {"id": "bare", "ssh_alias": "h", "mirror_root": "/srv/mirror"}
        self.assertIsNone(eda_mcp.load_config(profile))
        self.assertIsNone(eda_mcp.server_command(profile))
        self.assertIsNone(eda_mcp.mcp_json_text(profile))

    def test_unknown_group_is_rejected(self):
        profile = {"id": "b", "ssh_alias": "h", "mirror_root": "/srv/mirror",
                   "eda_mcp": {"prefix": "~/.local/opt/x", "groups": ["env", "flow"]}}
        with self.assertRaises(ValueError):
            eda_mcp.load_config(profile)

    def test_path_translation_follows_scenario_layout(self):
        """场景目录约定与 <TB_DUMP_TAG>_case<N>.fsdb 换算。"""
        profile = load_profile()
        mirror = profile["mirror_root"]
        self.assertEqual(eda_mcp.workdir(profile, "sys", "s1", ""), "%s/s1/work" % mirror)
        self.assertEqual(eda_mcp.workdir(profile, "module", "s1", "alu"), "%s/s1/work/alu" % mirror)
        self.assertEqual(eda_mcp.workdir(profile, "pubip", "", "pubip_counter"),
                         "%s/pub_code/work/pubip_counter" % mirror)
        self.assertEqual(eda_mcp.fsdb_remote_path(profile, "module", "s1", "alu", 3),
                         "%s/s1/work/alu/wave_case3.fsdb" % mirror)
        self.assertEqual(eda_mcp.fsdb_remote_path(profile, "sys", "s1", "", 12, tag="mdm"),
                         "%s/s1/work/mdm_case12.fsdb" % mirror)
        self.assertEqual(eda_mcp.mirror_of(profile, "s1/rtl/alu.sv"), "%s/s1/rtl/alu.sv" % mirror)
        self.assertEqual(eda_mcp.remote_dbg_dir(profile, "s1"), "%s/s1/work/dbg" % mirror)

    def test_source_digest_tracks_source_changes(self):
        """本地源码摘要随 toolchain/eda-mcp/src 内容变化。"""
        first = eda_mcp.source_digest(self.root)
        target = os.path.join(self.root, "toolchain", "eda-mcp", "src", "eda_mcp", "config.py")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n# digest probe\n")
        self.assertNotEqual(eda_mcp.source_digest(self.root), first)


if __name__ == "__main__":
    unittest.main()
