# 作者：vick 邮箱：ykun@yk9811.com

"""digest 认三种定点写法与 S5 模块表解析/批次注记的用例。

改动前会失败的点：
- `_formats()` 只认写法 2，写法 3 `12（<12,1,t>）` 完全不被识别 → IR 的 fixed_point 为空；
- `_index()` 用字面量 `"| leaf |"` 嗅探、类型格要求恰好 `leaf`/`group`，
  带注记的行既不检查、也让整个 S5 在认不出表时**静默返回空集**。
"""

import os
import tempfile
import unittest

from framework.digest import _formats, digest
from framework.gates.docs import _index, check_chapters, expected_chapters


def _mksys(files):
    """files: {相对路径: 内容} → 返回临时 sys_root（调用方负责清理）。"""
    root = tempfile.mkdtemp(prefix="adf-g-")
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


class FormatNotationTests(unittest.TestCase):
    def test_form3_port_notation_is_parsed(self):
        text = "| o_x | output | 12（<12,1,t>） | D3-001 |"
        self.assertEqual([{"name": "o_x", "format": "<12,1,t>"}], _formats(text))

    def test_form3_half_width_parens(self):
        self.assertEqual([{"name": "o_x", "format": "<12,1,t>"}],
                         _formats("| o_x | output | 12(<12,1,t>) |"))

    def test_form3_width_mismatch_rejected(self):
        self.assertEqual([], _formats("| o_x | output | 13（<12,1,t>） |"))

    def test_form2_still_parsed(self):
        self.assertEqual([{"name": "n_corr", "format": "<24,3,t>"}],
                         _formats("`n_corr` <24,3,t>"))

    def test_digest_reports_fixed_point_from_form3(self):
        root = _mksys({"spec_doc/m1_spec.md":
                       "## 2. 接口\n\n| 名字 | 方向 | 位宽 |\n|------|------|------|\n"
                       "| o_x | output | 12（<12,1,t>） |\n"})
        try:
            out = digest(root, "t")  # 子系统名取 t，模块 m1 才会留在 module_details 里
            details = {item["name"]: item for item in out["module_details"]}
            self.assertTrue(details["m1"]["fixed_point"],
                            "写法 3 必须产出 fixed_point：%r" % details["m1"]["fixed_point"])
        finally:
            import shutil
            shutil.rmtree(root, True)


class ModuleIndexTests(unittest.TestCase):
    TABLE_ANNOTATED = ("## 2. 模块摘要\n\n| 模块 | 类型 |\n|------|------|\n"
                       "| alu | leaf（寄存器配置模块） |\n| grp_a | group（行 5） |\n")

    def test_annotated_rows_missing_spec_reported(self):
        root = _mksys({"spec_doc/t_spec.md": self.TABLE_ANNOTATED})
        try:
            findings = _index(root)
            self.assertTrue(any(f["rule"] == "S5" and "alu" in f["detail"] for f in findings),
                            "带注记的行也必须检查：%r" % findings)
        finally:
            import shutil
            shutil.rmtree(root, True)

    def test_annotated_rows_with_specs_pass(self):
        root = _mksys({"spec_doc/t_spec.md": self.TABLE_ANNOTATED,
                       "spec_doc/alu_spec.md": "# alu\n",
                       "spec_doc/grp_a_spec.md": "# grp_a\n"})
        try:
            self.assertEqual([], _index(root))
        finally:
            import shutil
            shutil.rmtree(root, True)

    def test_unrecognizable_table_is_not_silent(self):
        root = _mksys({"spec_doc/t_spec.md": "## 2. 模块摘要\n\n| 模块 | 类型 |\n|--|--|\n| alu | 逻辑块 |\n"})
        try:
            findings = _index(root)
            self.assertTrue(any(f["rule"] == "S5" for f in findings),
                            "认不出摘要表时必须报错，不能静默关闭 S5：%r" % findings)
        finally:
            import shutil
            shutil.rmtree(root, True)

    def test_external_module_must_be_mentioned(self):
        table = ("## 2. 模块摘要\n\n| 模块 | 类型 |\n|------|------|\n| ip_round | 外部模块 |\n")
        root = _mksys({"spec_doc/t_spec.md": table})
        try:
            findings = _index(root)
            self.assertTrue(any(f["rule"] == "S5" and "ip_round" in f["detail"] for f in findings),
                            "外部模块找不到契约提及要报 S5：%r" % findings)
        finally:
            import shutil
            shutil.rmtree(root, True)
        root = _mksys({"spec_doc/t_spec.md": table,
                       "spec_doc/pubip_contracts.md": "u_round 例化 ip_round\n"})
        try:
            self.assertEqual([], _index(root))
        finally:
            import shutil
            shutil.rmtree(root, True)


class GroupChapterHintTests(unittest.TestCase):
    def test_group_extra_chapter_is_hint_only(self):
        text = "模块类型：group\n"
        expected = expected_chapters("spec_doc/g1_spec.md", 5, text, "t")
        self.assertTrue(expected, "夹具应能给出 group 的章节集")
        body = "# g1\n\n模块类型：group\n\n" + "\n\n".join(
            "## %d. %s\n\n正文。" % (index, chapter)
            for index, chapter in enumerate(expected, 2))
        body += "\n\n## 9. 测试要点\n\n正文。\n"
        findings = check_chapters(body, "spec_doc/g1_spec.md", 5, "t")
        hints = [item for item in findings if item.get("level") == "hint"]
        self.assertTrue(hints, "group 多写章节只提示：%r" % findings)


if __name__ == "__main__":
    unittest.main()
