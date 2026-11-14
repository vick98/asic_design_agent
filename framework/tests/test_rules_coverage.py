# 作者：vick 邮箱：ykun@yk9811.com

"""规则正文补齐后的自检。

pubip.md 的每个 IP 端口与参数逐条对 `pub_code/` 的 RTL（复用 gates/rtl.module_decl）；
其余薄规则文件补到能独立指导角色写作的程度。
"""

import os
import re
import unittest

from framework import pubip_doc
from framework.gates.rtl import module_decl, strip_comments
from framework.tests.util import RepoTest, checkout_root

# 公共模块清单以 pub_code/ 的 RTL 为唯一来源：新增 IP 自动进入逐端口/逐模块核对。
IPS = tuple(pubip_doc.pubip_modules())
PARAM = re.compile(
    r"parameter\s+(?:int\s+|integer\s+|bit\s+|logic\s+(?:\[[^\]]*\]\s+)?|\[[^\]]*\]\s+)?"
    r"([A-Za-z_]\w*)\s*=")


def _rules(name):
    with open(os.path.join(checkout_root(), "rules", name), encoding="utf-8") as fh:
        return fh.read()


def _rtl(doc_ips):
    for ext in (".sv", ".v"):
        path = os.path.join(checkout_root(), "pub_code", doc_ips + ext)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
    raise AssertionError("pub_code/ 里没有 %s" % doc_ips)


def _section(text, module):
    matched = re.search(r"^##\s+`?%s`?\s*$(.*?)(?=^##\s|\Z)" % re.escape(module),
                        text, re.M | re.S)
    return matched.group(1) if matched else ""


def _table(section, heading):
    """取 section 里某个 `### <heading>` 之后的表格数据行。"""
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
        rows.append(cells)
    return rows


class PubipDocTests(RepoTest):
    def setUp(self):
        self.doc = _rules("pubip.md")

    def test_every_ip_has_a_section(self):
        for module in IPS:
            self.assertTrue(_section(self.doc, module), "pubip.md 缺 %s 一节" % module)

    def test_ports_match_the_rtl(self):
        for module in IPS:
            section = _section(self.doc, module)
            _params, ports = module_decl(_rtl(module), module)
            self.assertTrue(ports, module)
            source = strip_comments(_rtl(module))
            documented = {}
            for cells in _table(section, "端口"):
                if len(cells) < 3 or cells[1].lower() not in ("input", "output", "inout"):
                    continue
                documented[cells[0]] = cells
            self.assertTrue(documented, "%s 没有端口表" % module)
            self.assertEqual(sorted(documented), sorted(p["name"] for p in ports), module)
            for port in ports:
                cells = documented[port["name"]]
                self.assertEqual(cells[1].lower(), port["direction"],
                                 "%s.%s 方向不符" % (module, port["name"]))
                want, got = port["width"], cells[2]
                if want is None:
                    # RTL 的位宽是参数表达式（module_decl 解析不出数字）：
                    # 文档要写出这个表达式，且它确实出现在 RTL 里。
                    self.assertFalse(re.fullmatch(r"\d+", got),
                                     "%s.%s 的 RTL 位宽是参数，文档不该写死数字" % (module, port["name"]))
                    self.assertIn(got, source, "%s.%s 的位宽 %s 在 RTL 里找不到"
                                  % (module, port["name"], got))
                else:
                    if got == str(want):
                        continue
                    # 参数化位宽允许写参数表达式（默认值解析会掩盖多实例差异，
                    # 如 pubip_counter.o_cnt_shift 随 MAX_NUM 变化）：
                    # 表达式须引用 RTL 参数名，且去空白后逐字出现在 RTL 源里。
                    param_names = set(_params) if _params else set()
                    if param_names and any(name in got for name in param_names) \
                            and got.replace(" ", "") in source.replace(" ", ""):
                        continue
                    self.assertEqual(got, str(want), "%s.%s 位宽不符" % (module, port["name"]))

    def test_parameters_match_the_rtl(self):
        for module in IPS:
            section = _section(self.doc, module)
            source = strip_comments(_rtl(module))
            body = source[source.index("module %s" % module):]
            body = body[: body.index("endmodule")]
            rtl_names = sorted(set(PARAM.findall(body)))
            documented = [row[0] for row in _table(section, "参数")
                          if row and row[0] not in ("参数名", "名字")]
            self.assertEqual(sorted(documented), rtl_names, module)

    def test_each_ip_has_an_instantiation_example(self):
        for module in IPS:
            section = _section(self.doc, module)
            self.assertIn("### 例化", section, module)
            body = section[section.index("### 例化"):]
            self.assertIn("%s #(" % module, body, module)
            _params, ports = module_decl(_rtl(module), module)
            for port in ports:
                self.assertIn(".%s" % port["name"], body,
                              "%s 的例化示例缺端口 %s" % (module, port["name"]))

    def test_nesting_is_stated(self):
        mem = _section(self.doc, "pubip_dynamic_mem")
        self.assertIn("sdpram_wrapper", mem)
        cal = _section(self.doc, "pubip_mseq_cal")
        self.assertIn("pubip_mseq_gen", cal)
        self.assertIn("15", cal)


class ThinRulesTests(RepoTest):
    """薄规则补到能独立指导角色写作：有清单、有判据，且不残留悬空来源引用。"""

    def _check(self, name, keywords, least_lines):
        text = _rules(name)
        self.assertGreaterEqual(len(text.splitlines()), least_lines, name)
        for word in keywords:
            self.assertIn(word, text, "%s 里没有 %s" % (name, word))

    def test_no_source_comparison_section_or_dangling_ids(self):
        """来源对照节与旧改进编号（对应台账已删除）不得再出现在规则里。"""
        dangling = re.compile(r"来源对照|[（(]G\d{2}|WP\d|第三轮\s*T\d")
        for root, _dirs, files in os.walk(os.path.join(checkout_root(), "rules")):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        self.assertIsNone(
                            dangling.search(line),
                            "%s:%d 残留悬空引用：%s" % (path, lineno, line.strip()))

    def test_pubip_covers_every_ip_and_the_reuse_rule(self):
        text = _rules("pubip.md")
        for module in IPS:
            self.assertIn(module, text)
        self.assertIn("外部模块", text)
        self.assertIn("例化时参数和端口都写全", text)

    def test_spec_covers_the_three_writes_and_tables(self):
        self._check("spec.md", ["行 4", "行 5", "行 6", "端口表", "测试要点", "fx", "group"], 40)

    def test_debug_covers_log_first_and_waveform(self):
        self._check("debug.md", ["RESULT", "波形", "WaveDrom", "小结", "复现"], 40)

    def test_documents_covers_control_and_product_files(self):
        self._check("documents.md", ["_status.md", "_decision.md", "〔D", "产物", "章节"], 40)


class NewInteractionModelTests(RepoTest):
    """规则正文按新交互模型重写后的口径自检。

    三种通道（决策 / 里程碑 / 简报）、自动送完成、调试事项、dbg 波形查询；
    禁词（迭代降级、代判、--loop-side none、enter-structure）对应新交互模型的收缩口径。
    """

    BANNED = re.compile(r"迭代降级|代判|--loop-side none|enter-structure")

    def test_banned_legacy_phrases_are_gone(self):
        for root, _dirs, files in os.walk(os.path.join(checkout_root(), "rules")):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        self.assertIsNone(
                            self.BANNED.search(line),
                            "%s:%d 残留旧交互模型措辞：%s" % (path, lineno, line.strip()))

    def test_methodology_describes_three_channels(self):
        text = _rules("methodology.md")
        for word in ("用停点名字", "每个工作包后跑 tick", "决策", "里程碑", "简报",
                     "红线", "M3", "点选即入库"):
            self.assertIn(word, text)
        self.assertIn("作者与审查者必须不同", text)
        self.assertIn("派工号", text)

    def test_decision_is_select_to_commit_with_record_hint(self):
        text = _rules("decision.md")
        self.assertIn("点选即入库", text)
        self.assertIn("疑似方向或数值类", text)
        self.assertIn("<w,f,t>", text)
        self.assertIn("里程碑审阅包里高亮", text)
        self.assertNotIn("## 谁执行", text)
        # 既有不变量仍在正文里（现在 withdraw 只标已撤回、不再领 T 号、
        # 也不再有队列上限与 --step：断言随之换成新口径的关键短语）。
        for word in ("编号只增不复用", "--force --reason", "history", "只标",
                     "已撤回", "--from", "--pick", "--stop", "mark:<文件>:<行>"):
            self.assertIn(word, text)

    def test_debug_routes_fix_and_loops_through_items(self):
        text = _rules("debug.md")
        self.assertIn("## 波形与设计查询", text)
        for word in ("dbg", "rules/waveform.md", "+nolibcell", "-fno-lto",
                     "item <sys> open", "--side tb|rtl|spec", "item <sys> set", "item <sys> end",
                     "L0/L1 由智能体按证据自行决定", "L2/L3 是决策",
                     "blocked_by_items", "停点总表", "rules/waveform.md"):
            self.assertIn(word, text, word)
        self.assertNotIn("--loop-side", text)
        self.assertIn("取代", text)  # dbg extract 取代 TB 探针作为默认做法
        self.assertIn("后备", text)  # TB 探针降级为后备

    def test_steps_use_review_focus_not_manual_review(self):
        text = _rules("steps.md")
        self.assertGreaterEqual(text.count("审查要点"), 12)
        self.assertIsNone(re.search(r"人工审核（", text), text)
        self.assertIn("开发者审阅集中到里程碑", text)

    def test_host_cards_route_through_tick_and_milestones(self):
        design = _rules("host/design.md")
        code = _rules("host/code.md")
        for text in (design, code):
            self.assertIn("tick", text)
            self.assertIn("milestone", text)
            self.assertIn("动作策略表", text)
        for stale in ("五种确认档位", "## 谁执行命令", "可提交包", "是否确认通过"):
            self.assertNotIn(stale, design, stale)
            self.assertNotIn(stale, code, stale)
        self.assertNotIn("每批范围先请开发者确认", code)
        self.assertIn("每个工作包后跑 tick", design)
        self.assertIn("每个工作包后跑 tick", code)
        # 终端照抄只保留在 M3；design 卡只留里程碑那一条确认语句模板
        self.assertIn("--id M3", design)
        self.assertNotIn("裁决入库：", design)
        self.assertNotIn("闭合回路侧：", design)

    def test_roles_do_not_carry_loop_side_or_premilestone_sdc_review(self):
        sim = _rules(os.path.join("roles", "rtl_sim.md"))
        self.assertNotIn("--loop-side", sim)
        self.assertIn("item <sys> open", sim)
        self.assertIn("--side", sim)
        self.assertIn("--evidence", sim)
        mid = _rules(os.path.join("roles", "midend_flow.md"))
        self.assertIn("M3 审阅包", mid)
        self.assertNotIn("须经开发者审查", mid)


class DispatchGuidanceTests(RepoTest):
    """派工与并行：鼓励派子代理，但先划文件归属，同一文件只有一个写入者。"""

    def test_methodology_has_the_three_constraints(self):
        text = _rules("methodology.md")
        self.assertIn("## 派工与并行", text)
        section = text[text.index("## 派工与并行"):]
        for word in ("子代理", "文件归属", "同一文件", "写入者", "state.json",
                     "走查与生产分离", "只读", "并行"):
            self.assertIn(word, section, section)
        self.assertIn("改别人负责的文件", section)

    def test_both_host_cards_point_at_the_guidance(self):
        for name in ("host/design.md", "host/code.md"):
            text = _rules(name)
            self.assertIn("子代理", text, name)
            self.assertIn("rules/methodology.md", text, name)
            self.assertIn("文件归属", text, name)

    def test_code_card_names_the_exclusive_folders(self):
        text = _rules("host/code.md")
        for word in ("testbench/", "dc|pt|lint/"):
            self.assertIn(word, text, text)

    def test_standing_entry_carries_the_one_line_rule(self):
        name = "AGENTS.md"
        with open(os.path.join(checkout_root(), name), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("rules/methodology.md", text, name)
        self.assertIn("同一文件同一时间只有一个写入者", text, name)
        self.assertLess(len(text.encode("utf-8")), 10240, name)


if __name__ == "__main__":
    unittest.main()
