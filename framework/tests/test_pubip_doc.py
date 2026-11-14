# 作者：vick 邮箱：ykun@yk9811.com

"""rules/pubip.md 的参数/端口生成区与 pub_code/ 的 RTL 逐字节一致。

rules/pubip.md 的每个公共模块一节里，`### 参数` 与 `### 端口` 两张表由
`framework/pubip_doc.py` 从 `pub_code/` 的 RTL 生成，`python3 script/framework.py hosts`
写入。生成区之外（正文、清单、例化示例）手写，不受渲染影响。

本用例锁定三件事：仓库里的生成区与 RTL 一致；改了 RTL 而没重跑 `hosts` 会被判为
落后；`说明` 列保留规则文件里已有的文本，新增参数/端口才取 RTL 行尾 `//` 注释。
"""

import os
import re
import unittest

from framework import pubip_doc
from framework.gates.rtl import module_decl, strip_comments
from framework.hosts.render import render
from framework.tests.util import RepoTest

PARAMS_MARKER = "<!-- PUBIP_PARAMS -->"
PORTS_MARKER = "<!-- PUBIP_PORTS -->"
PARAM = re.compile(
    r"parameter\s+(?:int\s+|integer\s+|bit\s+|logic\s+(?:\[[^\]]*\]\s+)?|\[[^\]]*\]\s+)?"
    r"([A-Za-z_]\w*)\s*=")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _section(text, module):
    matched = re.search(r"^##\s+`?%s`?\s*$(.*?)(?=^##\s|\Z)" % re.escape(module),
                        text, re.M | re.S)
    return matched.group(1) if matched else ""


def _table(section, heading):
    """取 section 里某个 `### <heading>` 之后的表格数据行（去掉标记行与表头）。"""
    rows, capture = [], False
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            capture = heading in stripped
            continue
        if not capture or not stripped.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if cells and set("".join(cells)) <= set("-: "):
            continue
        if cells and cells[0] in ("参数名", "端口", "名字"):
            continue
        rows.append(cells)
    return rows


def _docs(text, module):
    section = _section(text, module)
    return {
        "params": {row[0]: row for row in _table(section, "参数") if row},
        "ports": {row[0]: row for row in _table(section, "端口") if row},
    }


def _rtl_path(root, module):
    for ext in (".sv", ".v"):
        path = os.path.join(root, "pub_code", module + ext)
        if os.path.isfile(path):
            return path
    raise AssertionError("pub_code/ 里没有 %s" % module)


def _rtl_params(module, root):
    """RTL 模块体里的参数名（与字段解析无关的独立口径）。"""
    source = strip_comments(_read(_rtl_path(root, module)))
    body = source[source.index("module %s" % module):]
    body = body[:body.index("endmodule")]
    return sorted(set(PARAM.findall(body)))


class PubipDocGenerationTests(RepoTest):
    def setUp(self):
        self.doc_path = os.path.join(self.root, "rules", "pubip.md")
        self.doc = _read(self.doc_path)

    def test_document_is_regenerated_byte_for_byte(self):
        """仓库里的 rules/pubip.md 就是生成结果：一个字节都不差。"""
        self.assertEqual(pubip_doc.render_pubip(self.doc), self.doc)

    def test_every_pub_code_module_has_both_generation_blocks(self):
        modules = pubip_doc.pubip_modules(self.root)
        self.assertTrue(modules)
        marker_lines = [line.strip() for line in self.doc.splitlines()]
        self.assertEqual(marker_lines.count(PARAMS_MARKER), len(modules))
        self.assertEqual(marker_lines.count(PORTS_MARKER), len(modules))
        for module in modules:
            section = _section(self.doc, module)
            self.assertTrue(section, "rules/pubip.md 缺 %s 一节" % module)
            self.assertIn(PARAMS_MARKER, section, module)
            self.assertIn(PORTS_MARKER, section, module)

    def test_parameter_and_port_names_match_the_rtl(self):
        for module in pubip_doc.pubip_modules(self.root):
            _params, ports = module_decl(_read(_rtl_path(self.root, module)), module)
            documented = _docs(self.doc, module)
            self.assertEqual(sorted(documented["params"]), _rtl_params(module, self.root), module)
            self.assertEqual(sorted(documented["ports"]),
                             sorted(port["name"] for port in ports), module)

    def test_port_direction_and_width_match_the_rtl(self):
        for module in pubip_doc.pubip_modules(self.root):
            source = strip_comments(_read(_rtl_path(self.root, module)))
            _decl_params, ports = module_decl(_read(_rtl_path(self.root, module)), module)
            param_names = _rtl_params(module, self.root)
            documented = _docs(self.doc, module)
            for port in ports:
                cells = documented["ports"][port["name"]]
                self.assertEqual(cells[1].lower(), port["direction"],
                                 "%s.%s 方向不符" % (module, port["name"]))
                got, want = cells[2], port["width"]
                if want is None:
                    self.assertFalse(re.fullmatch(r"\d+", got),
                                     "%s.%s 的 RTL 位宽解析不出具体值，文档不该写死数字"
                                     % (module, port["name"]))
                    self.assertTrue(got in source or got.replace(" ", "") in source.replace(" ", ""),
                                    "%s.%s 的位宽 %s 在 RTL 里找不到"
                                    % (module, port["name"], got))
                elif got == str(want):
                    continue
                else:
                    # 参数化位宽允许写参数表达式（多实例宽度随参数变化）。
                    self.assertTrue(param_names and any(name in got for name in param_names),
                                    "%s.%s 位宽 %s 与 RTL %s 不符" % (module, port["name"], got, want))
                    self.assertIn(got.replace(" ", ""), source.replace(" ", ""),
                                  "%s.%s 的位宽表达式 %s 在 RTL 里找不到"
                                  % (module, port["name"], got))

    def test_existing_descriptions_are_kept(self):
        """说明列优先保留规则文件里已有的文本，不因重新生成被 RTL 注释冲掉。"""
        counter = _docs(self.doc, "pubip_counter")
        self.assertIn("最大计数值", counter["params"]["MAX_NUM"][-1])
        self.assertIn("循环计数使能", counter["params"]["CYCLE_EN"][-1])
        self.assertEqual(counter["ports"]["clk_in"][-1], "时钟输入")
        sat = _docs(self.doc, "pubip_sat")
        self.assertIn("输入数据总位宽", sat["params"]["IN_TOTAL_WIDTH"][-1])
        self.assertEqual(sat["ports"]["i_data"][-1], "输入数据")
        mult = _docs(self.doc, "pubip_complex_mult")
        self.assertIn("第一路实部", mult["ports"]["i_dina_re"][-1])

    def test_markers_are_documented_in_the_header(self):
        self.assertIn("生成物", self.doc)
        self.assertIn("PUBIP_PARAMS", self.doc)
        self.assertIn("PUBIP_PORTS", self.doc)

    def test_missing_marker_is_rejected(self):
        section = _section(self.doc, "pubip_counter")
        broken = self.doc.replace(section, section.replace(PARAMS_MARKER, "", 1), 1)
        with self.assertRaises(ValueError) as ctx:
            pubip_doc.render_pubip(broken)
        self.assertIn("pubip_counter", str(ctx.exception))

    def test_render_writes_the_document(self):
        render()
        self.assertEqual(_read(self.doc_path), pubip_doc.render_pubip(_read(self.doc_path)))


class PubipDocFreshnessTests(RepoTest):
    """改 RTL 后生成区必须变红；重跑 hosts 后恢复。用例都在副本仓库里改 RTL。"""

    def setUp(self):
        self.doc_path = os.path.join(self.root, "rules", "pubip.md")
        self.doc = _read(self.doc_path)

    def _edit_rtl(self, module, old, new):
        path = _rtl_path(self.root, module)
        original = _read(path)
        self.addCleanup(_write, path, original)
        self.assertTrue(old in original, "RTL 里找不到要替换的片段：%s" % old)
        _write(path, original.replace(old, new, 1))
        return path

    def test_parameter_default_change_makes_the_document_stale(self):
        self.addCleanup(_write, self.doc_path, self.doc)
        self._edit_rtl("pubip_counter", "parameter int MAX_NUM = 7",
                       "parameter int MAX_NUM = 15")
        self.assertNotEqual(pubip_doc.render_pubip(self.doc), self.doc,
                            "RTL 改了参数默认值，生成区应当落后")
        render()
        self.assertEqual(_read(self.doc_path), pubip_doc.render_pubip(_read(self.doc_path)))

    def test_new_rtl_item_takes_its_comment_and_missing_comment_gets_a_dash(self):
        """新增参数/端口从 RTL 行尾注释取说明；没有注释的留 `—`。"""
        self._edit_rtl(
            "pubip_sat",
            "    parameter int PROTECT_EN      = 0      //零值保护使能，1表示开启保护，0表示关闭保护\n)",
            "    parameter int PROTECT_EN      = 0,     //零值保护使能，1表示开启保护，0表示关闭保护\n"
            "    parameter int NEW_FLAG        = 0      //新增标志位（测试用）\n)")
        self._edit_rtl(
            "pubip_sat",
            "    output  logic   [OUT_TOTAL_WIDTH - 1 : 0]   o_data   //输出数据（经过饱和截位后）\n);",
            "    output  logic   [OUT_TOTAL_WIDTH - 1 : 0]   o_data  ,//输出数据（经过饱和截位后）\n"
            "    input   i_new_flagged ,//新加端口，带说明\n"
            "    input   i_new_quiet\n);")
        fresh = pubip_doc.render_pubip(self.doc)
        documented = _docs(fresh, "pubip_sat")
        self.assertEqual(documented["params"]["NEW_FLAG"][-1], "新增标志位（测试用）")
        self.assertEqual(documented["ports"]["i_new_flagged"][-1], "新加端口，带说明")
        self.assertEqual(documented["ports"]["i_new_quiet"][-1], "—")
        # 既有条目的说明仍然是规则文件里的文本，不被 RTL 注释替换。
        self.assertIn("零值保护使能", documented["params"]["PROTECT_EN"][-1])

    def test_unregistered_pub_code_module_is_rejected(self):
        path = os.path.join(self.root, "pub_code", "pubip_unregistered.sv")
        self.addCleanup(os.remove, path)
        _write(path, "module pubip_unregistered(input logic clk_in);\nendmodule\n")
        with self.assertRaises(ValueError) as ctx:
            pubip_doc.render_pubip(self.doc)
        self.assertIn("pubip_unregistered", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
