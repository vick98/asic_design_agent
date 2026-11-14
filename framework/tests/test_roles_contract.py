# 作者：vick 邮箱：ykun@yk9811.com

"""WP13 验收：角色契约与规则正文重写。"""

import os
import re

import yaml

from framework.gates.docs import load_chapter_model
from framework.hosts.render import load_roles
from framework.tests.util import RepoTest, checkout_root

REVIEWERS = ("spec_review", "rtl_review")
WRITERS = ("step0_info_input", "step1_sys_flow", "step2_sys_plan", "step3_sys_spec",
           "step3_module_spec", "spec2rtl", "sys_spec2rtl", "tb_build")


def _rules_files():
    root = os.path.join(checkout_root(), "rules")
    out = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for fn in files:
            if fn.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), checkout_root())
                           .replace(os.sep, "/"))
    return sorted(out)


def _refs_in(text):
    """正文里出现的 rules/*.md 路径。"""
    return set(re.findall(r"rules/[\w/]+\.md", text))


class ContractTests(RepoTest):
    def _roles(self):
        return {role["id"]: role for role in load_roles()}

    def test_every_rules_file_is_referenced(self):
        roles = self._roles()
        refs = set()
        for role in roles.values():
            refs.update(role["must_read"])
        for name in ("rules/methodology.md", "rules/host/design.md", "rules/host/code.md"):
            text = open(os.path.join(checkout_root(), name), encoding="utf-8").read()
            refs.update(_refs_in(text))
        # 主持卡本身由 render.py 的 HOSTS must_read 指向（生成投影时使用）。
        refs.update(("rules/host/design.md", "rules/host/code.md"))
        missing = [path for path in _rules_files() if path not in refs]
        self.assertEqual(missing, [], "rules/ 下没有被任何角色、主持卡或方法论引用的文件")

    def test_must_read_paths_exist(self):
        for role in load_roles():
            for path in role["must_read"]:
                self.assertTrue(os.path.isfile(os.path.join(checkout_root(), path)),
                                "%s 的必读缺失：%s" % (role["id"], path))

    def test_writer_tools_have_write_and_bash(self):
        roles = self._roles()
        for role_id in WRITERS:
            self.assertEqual(set(roles[role_id]["tools"]),
                             {"Read", "Edit", "Write", "Bash"},
                             "%s 工具应为 R8=A 写作四件套" % role_id)

    def test_reviewer_tools_read_only(self):
        roles = self._roles()
        for role_id in REVIEWERS:
            self.assertEqual(roles[role_id]["tools"], ["Read", "Bash"], role_id)
            self.assertNotIn("Edit", roles[role_id]["tools"])
            self.assertNotIn("Write", roles[role_id]["tools"])
        # 仿真与综合时序角色按职责给最小写权限，不再是纯只读。
        self.assertEqual(roles["rtl_sim"]["tools"], ["Read", "Edit", "Bash"], "rtl_sim")
        self.assertEqual(roles["midend_flow"]["tools"], ["Read", "Edit", "Write", "Bash"],
                         "midend_flow")

    def test_sim_and_midend_write_scopes(self):
        roles = self._roles()
        sim = roles["rtl_sim"]
        self.assertIn("rules/waveform.md", sim["must_read"])
        self.assertTrue(any("//DBG_BEGIN" in item and "//DBG_END" in item
                            for item in sim["forbidden"]),
                        "rtl_sim 未限定 TB 探针写域为 //DBG_BEGIN/END 块")
        self.assertTrue(any("dbg" in item and "不改 TB" in item for item in sim["forbidden"]),
                        "rtl_sim 未写明默认用 dbg 波形导出、不改 TB")
        mid = roles["midend_flow"]
        self.assertTrue(any("SDC" in item for item in mid["forbidden"]),
                        "midend_flow 未写明写域只限约束文件")
        self.assertIn("SDC", mid["description"])

    def test_sim_role_reads_debug_and_step2_reads_pubip(self):
        roles = self._roles()
        self.assertIn("rules/debug.md", roles["rtl_sim"]["must_read"])
        self.assertIn("rules/pubip.md", roles["step2_sys_plan"]["must_read"])
        self.assertIn("rules/coding.md", roles["spec2rtl"]["must_read"])
        self.assertIn("rules/coding.md", roles["rtl_review"]["must_read"])
        self.assertIn("rules/wrapper.md", roles["sys_spec2rtl"]["must_read"])
        self.assertIn("rules/templates/sys_spec.md", roles["step3_sys_spec"]["must_read"])
        self.assertIn("rules/templates/module_spec.md", roles["step3_module_spec"]["must_read"])
        self.assertIn("rules/review/spec.md", roles["spec_review"]["must_read"])
        self.assertIn("rules/review/rtl.md", roles["rtl_review"]["must_read"])

    def test_reviewer_role_files_limit_commands(self):
        for role_id in REVIEWERS:
            text = open(os.path.join(checkout_root(), "rules", "roles", role_id + ".md"),
                        encoding="utf-8").read()
            for cmd in ("gate", "fx", "status"):
                self.assertIn("`%s`" % cmd, text, "%s 未写明只允许 %s" % (role_id, cmd))
            self.assertIn("没有 `Edit`", text, role_id)

    def test_host_cards_read_decision_and_documents(self):
        for name in ("rules/host/design.md", "rules/host/code.md"):
            text = open(os.path.join(checkout_root(), name), encoding="utf-8").read()
            self.assertIn("rules/decision.md", text, name)
            self.assertIn("rules/documents.md", text, name)


class RoleFileTests(RepoTest):
    def test_role_files_have_depth(self):
        for path in _rules_files():
            if not path.startswith("rules/roles/"):
                continue
            lines = [ln for ln in open(os.path.join(checkout_root(), path),
                                       encoding="utf-8").read().splitlines() if ln.strip()]
            self.assertGreaterEqual(len(lines), 40, "%s 正文行数不足" % path)

    def test_role_files_not_echoing_yaml(self):
        with open(os.path.join(checkout_root(), "framework", "hosts", "roles.yaml"),
                  encoding="utf-8") as fh:
            descriptions = {role["id"]: role["description"] for role in yaml.safe_load(fh)["roles"]}
        for role_id, description in descriptions.items():
            path = os.path.join(checkout_root(), "rules", "roles", role_id + ".md")
            text = open(path, encoding="utf-8").read()
            self.assertGreater(len(text), len(description) * 3,
                               "%s 的正文疑似只复述 description" % role_id)
            for section in ("工作步骤", "判断标准", "常见错误", "返回小结字段示例"):
                self.assertIn(section, text, "%s 缺小节：%s" % (path, section))

    def test_steps_chapter_names_from_yaml(self):
        declared = set()
        for doc in load_chapter_model()["documents"]:
            declared.update(doc["chapters"])
        text = open(os.path.join(checkout_root(), "rules", "steps.md"), encoding="utf-8").read()
        used = set()
        for line in text.splitlines():
            if line.startswith("必写：") or line.startswith("必填章节："):
                body = line.split("：", 1)[1].split("。", 1)[0]
                used.update(item.strip() for item in body.split("、") if item.strip())
        self.assertTrue(used, "steps.md 没有“必写：”行可检查")
        stray = sorted(used - declared)
        self.assertEqual(stray, [], "steps.md 出现 chapters.yaml 之外的章节名")

    def test_sim_doc_states_cov_threshold_order(self):
        text = open(os.path.join(checkout_root(), "rules", "sim.md"), encoding="utf-8").read()
        self.assertIn("cov_gate.txt", text)
        self.assertIn("只能上调", text)
        self.assertIn("豁免", text)
        for key in ("框架默认", "剖面", "来源顺序"):
            self.assertIn(key, text)


if __name__ == "__main__":
    import unittest
    unittest.main()
