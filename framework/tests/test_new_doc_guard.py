# 作者：vick 邮箱：ykun@yk9811.com

"""`new-doc` 不得无提示覆盖已有内容的产物。"""

import os
import shutil
import subprocess
import sys

from framework.tests.util import RepoTest, checkout_root


class NewDocGuardTests(RepoTest):
    SYS = "fresh"

    def setUp(self):
        super().setUp()
        # 同一个临时仓库被本类所有用例共用，每个用例先清干净目标与备份目录。
        path = self._target("flow_doc/%s_flow.md" % self.SYS)
        if os.path.exists(path):
            os.remove(path)
        backup_dir = os.path.join(self.root, self.SYS, ".new_doc_backups")
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir)

    def _target(self, rel):
        return os.path.join(self.root, self.SYS, rel)

    def _run(self, *extra):
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        return subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"),
             "new-doc", self.SYS, "--stop", "2"] + list(extra),
            env=env, capture_output=True, text=True,
        )

    def _plant(self, text):
        path = self._target("flow_doc/%s_flow.md" % self.SYS)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_existing_content_rejected_and_untouched(self):
        original = "# fresh_flow\n\n已经写好的流程正文，不能被覆盖。\n"
        path = self._plant(original)
        proc = self._run()
        self.assertNotEqual(proc.returncode, 0, "已有内容时 new-doc 应拒绝")
        self.assertIn("已存在", proc.stderr)
        self.assertIn("--force", proc.stderr)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original, "拒绝后原文件必须保持原样")
        self.assertFalse(os.path.exists(os.path.join(self.root, self.SYS, ".new_doc_backups")),
                         "拒绝时不应产生备份")

    def test_force_overwrites_and_backs_up(self):
        original = "# fresh_flow\n\n旧的实质内容。\n"
        path = self._plant(original)
        proc = self._run("--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(path, encoding="utf-8") as fh:
            self.assertIn("待填写。", fh.read(), "--force 应写入新模板")
        backup_dir = os.path.join(self.root, self.SYS, ".new_doc_backups")
        backups = sorted(os.listdir(backup_dir))
        self.assertEqual(len(backups), 1, backups)
        self.assertTrue(backups[0].startswith("fresh_flow.md."), backups[0])
        self.assertTrue(backups[0].endswith(".bak"), backups[0])
        with open(os.path.join(backup_dir, backups[0]), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original, "备份内容应等于原文件")

    def test_missing_target_created(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = self._target("flow_doc/%s_flow.md" % self.SYS)
        with open(path, encoding="utf-8") as fh:
            self.assertIn("待填写。", fh.read())

    def test_empty_or_blank_target_overwritten_without_backup(self):
        for text in ("", "   \n\n"):
            path = self._plant(text)
            proc = self._run()
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(path, encoding="utf-8") as fh:
                self.assertIn("待填写。", fh.read())
        self.assertFalse(os.path.exists(os.path.join(self.root, self.SYS, ".new_doc_backups")),
                         "空白目标无需备份")

    def test_non_markdown_product_rejected(self):
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        proc = subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"),
             "new-doc", self.SYS, "--stop", "8"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0, "停点 8 的产物不是文档，new-doc 应拒绝")
        self.assertIn("只用于 Markdown 文档产物", proc.stderr)
        self.assertFalse(os.path.exists(self._target("rtl/%s_top.sv" % self.SYS)))


if __name__ == "__main__":
    import unittest
    unittest.main()
