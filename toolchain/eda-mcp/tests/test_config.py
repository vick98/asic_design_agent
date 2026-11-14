"""配置分层与工具探测测试。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp import config as cfgmod  # noqa: E402


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_defaults_present(self):
        c = cfgmod.Config(cfgmod.defaults())
        self.assertEqual(c.get("server.transport"), "stdio")
        self.assertEqual(c.get("eda.vcs_bin"), "vcs")
        self.assertFalse(c.get("security.allow_shell"))

    @unittest.skipIf(cfgmod._toml is None, "本机无 tomllib/tomli，跳过 TOML 解析用例")
    def test_toml_overrides_default(self):
        path = os.path.join(self.tmp, "c.toml")
        with open(path, "w") as fh:
            fh.write('[eda]\nvcs_bin = "/opt/x/vcs"\n[fsdb]\nmax_changes = 99\n')
        data = cfgmod._deep_merge(cfgmod.defaults(), cfgmod._load_toml(path))
        c = cfgmod.Config(data)
        self.assertEqual(c.get("eda.vcs_bin"), "/opt/x/vcs")
        self.assertEqual(c.get("fsdb.max_changes"), 99)
        # 未覆盖项保持不变
        self.assertEqual(c.get("eda.pt_bin"), "pt_shell")

    def test_env_overrides_toml(self):
        os.environ["EDA_MCP_VCS_BIN"] = "/env/vcs"
        os.environ["EDA_MCP_ALLOW_SHELL"] = "true"
        os.environ["EDA_MCP_PORT"] = "9999"
        c = cfgmod.load()
        self.assertEqual(c.get("eda.vcs_bin"), "/env/vcs")
        self.assertTrue(c.get("security.allow_shell"))
        self.assertEqual(c.get("server.port"), 9999)

    def test_path_expands_user_and_vars(self):
        os.environ["EDA_MCP_CACHE_DIR"] = "~/x/eda"
        c = cfgmod.load()
        self.assertTrue(c.cache_dir().startswith(os.path.expanduser("~")))
        self.assertNotIn("~", c.cache_dir())

    def test_coerce(self):
        self.assertIs(cfgmod._coerce("Yes"), True)
        self.assertIs(cfgmod._coerce("off"), False)
        self.assertEqual(cfgmod._coerce("42"), 42)
        self.assertEqual(cfgmod._coerce("/a/b"), "/a/b")

    def test_fsdbq_prefers_configured_path(self):
        exe = os.path.join(self.tmp, "fsdbq")
        with open(exe, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(exe, 0o755)
        c = cfgmod.Config(cfgmod._deep_merge(cfgmod.defaults(), {"fsdb": {"fsdbq_bin": exe}}))
        self.assertEqual(c.fsdbq(), exe)

    def test_verdi_home_falls_back_to_guess(self):
        c = cfgmod.Config(cfgmod.defaults())
        home = c.verdi_home()
        self.assertTrue(home is None or os.path.isdir(home) or isinstance(home, str))


if __name__ == "__main__":
    unittest.main(verbosity=2)
