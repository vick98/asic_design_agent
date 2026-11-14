# 作者：vick 邮箱：ykun@yk9811.com

import os
import shutil
import subprocess
import sys

from framework.gates.docs import expected_chapters, load_chapter_model
from framework.gates.run import run_gates
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, checkout_root


def _plant(root):
    src = os.path.join(checkout_root(), "framework", "fixtures", "sample")
    dst = os.path.join(root, "sample")
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _names(line):
    """“必填章节：A、B”“必写：A、B。后面是说明” → {A, B}。"""
    body = line.split("：", 1)[1].split("。", 1)[0]
    return {item.strip() for item in body.split("、") if item.strip()}


class ChapterTests(RepoTest):
    def test_group_has_interface_chapters_at_stop_4(self):
        """group 在行 4 与 leaf 一样先写接口三章；行 5 才扩到组章节集。"""
        text = "模块类型：group"
        self.assertEqual(expected_chapters("spec_doc/glue_spec.md", 4, text, "demo"),
                         ["模块功能", "模块接口", "模块处理流程"])
        self.assertEqual(expected_chapters("spec_doc/glue_spec.md", 5, text, "demo"),
                         ["模块功能", "模块接口", "模块处理流程",
                          "组成模块", "模块连接关系"])

    def test_sample_passes_stops_1_to_6(self):
        init_sys(self.root, "sample")
        _plant(self.root)
        for sid in range(1, 7):
            state = load_state(self.root, "sample")
            findings = [item for item in run_gates(self.root, "sample", sid, state) if item.get("level") != "hint"]
            self.assertEqual(findings, [], "stop %d %s" % (sid, findings))

    def test_missing_chapter_and_bad_column_fail(self):
        init_sys(self.root, "sample")
        _plant(self.root)
        info = os.path.join(self.root, "sample", "info_input", "sample_info_overview.md")
        with open(info, encoding="utf-8") as fh:
            original = fh.read()
        try:
            with open(info, "w", encoding="utf-8") as fh:
                fh.write(original.replace("## 5. 红线五问\n\n时钟为单域。复位低有效且同步释放。接口为流式。吞吐由输入给定。溢出用饱和。\n", ""))
            state = load_state(self.root, "sample")
            findings = run_gates(self.root, "sample", 1, state)
            self.assertTrue(any(item["rule"] == "S1" for item in findings))
        finally:
            with open(info, "w", encoding="utf-8") as fh:
                fh.write(original)
        leaf = os.path.join(self.root, "sample", "spec_doc", "alu_spec.md")
        with open(leaf, encoding="utf-8") as fh:
            spec = fh.read()
        with open(leaf, "w", encoding="utf-8") as fh:
            fh.write(spec.replace("| 方向 |", "| 去向 |", 1))
        state = load_state(self.root, "sample")
        findings = run_gates(self.root, "sample", 6, state)
        self.assertTrue(any(item["rule"] == "S6" for item in findings))

    def test_rules_chapters_match_yaml(self):
        """双向比对：`必填章节：` 与 `必写：` 里的章节名都要来自 chapters.yaml。

        其中 `必写：` 与 `rules/steps.md` 这两条要等规则正文重写之后才通过（当时明说
        “本测试在重写合入前允许失败”）。
        """
        model = load_chapter_model()
        declared = set()
        for doc in model["documents"]:
            declared.update(doc["chapters"])
        required, must_write = set(), set()
        rules = os.path.join(checkout_root(), "rules")
        for dirpath, _dirs, files in os.walk(rules):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                text = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                for line in text.splitlines():
                    if line.startswith("必填章节："):
                        required.update(_names(line))
                    elif line.startswith("必写："):
                        must_write.update(_names(line))
        self.assertEqual(required, declared)
        self.assertEqual(sorted(must_write - declared), [],
                         "rules/ 的“必写：”里出现了 chapters.yaml 没有的章节名")
        steps = open(os.path.join(rules, "steps.md"), encoding="utf-8").read()
        steps_names = set()
        for line in steps.splitlines():
            if line.startswith("必写："):
                steps_names.update(_names(line))
        self.assertEqual(sorted(steps_names - declared), [],
                         "rules/steps.md 的章节名必须来自 chapters.yaml")

    def test_new_doc_writes_chapters(self):
        from framework.gates.docs import expected_chapters
        init_sys(self.root, "fresh")
        os.environ["ADF_ROOT"] = self.root
        import subprocess
        import sys
        proc = subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"),
             "new-doc", "fresh", "--stop", "1"],
            env=os.environ.copy(), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(self.root, "fresh", "info_input", "fresh_info_overview.md")
        text = open(path, encoding="utf-8").read()
        for name in expected_chapters("info_input/fresh_info_overview.md", 1, "", "fresh"):
            self.assertIn(name, text)


if __name__ == "__main__":
    import unittest
    unittest.main()
