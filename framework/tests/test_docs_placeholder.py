# 作者：vick 邮箱：ykun@yk9811.com

"""docs 闸门：文档骨架里的占位串必须报出来，写成实际内容后才放行。"""

import os
import unittest

from framework.engine import tick_report
from framework.flow import DONE
from framework.gates.docs import PLACEHOLDER_MARKERS, PLACEHOLDER_TEXT, expected_chapters
from framework.gates.run import run_gates
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, cli, force_done, plant_sample, review


class DocsPlaceholderTests(RepoTest):
    def _findings(self, name, stop):
        return [item for item in run_gates(self.root, name, stop, load_state(self.root, name))
                if item.get("level") != "hint"]

    def _s7(self, name, stop):
        return [item for item in self._findings(name, stop) if item["rule"] == "S7"]

    def _new_doc(self, name, stop, *extra):
        proc = cli(self.root, "new-doc", name, "--stop", str(stop), *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def _path(self, name, rel):
        return os.path.join(self.root, name, *rel.split("/"))

    def _read(self, name, rel):
        with open(self._path(name, rel), encoding="utf-8") as fh:
            return fh.read()

    def _write(self, name, rel, text):
        path = self._path(name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_new_doc_skeleton_reports_s7_for_lead_and_every_chapter(self):
        name = "plchnew"
        init_sys(self.root, name)
        self._new_doc(name, 2)
        rel = "flow_doc/%s_flow.md" % name
        text = self._read(name, rel)
        chapters = expected_chapters(rel, 2, "", name)
        self.assertTrue(chapters)
        self.assertIn(PLACEHOLDER_TEXT, text, "new-doc 应写入 PLACEHOLDER_TEXT")
        for chapter in chapters:
            self.assertIn(chapter, text)
        hits = self._s7(name, 2)
        # 开篇简介一处 + 每个章节正文一处。
        self.assertEqual(len(hits), len(chapters) + 1, hits)
        self.assertTrue(all(item["where"] == rel for item in hits), hits)

    def test_filling_each_chapter_clears_s7(self):
        name = "plchfill"
        init_sys(self.root, name)
        self._new_doc(name, 2)
        rel = "flow_doc/%s_flow.md" % name
        text = self._read(name, rel)
        self.assertTrue(self._s7(name, 2), "骨架文档应先报 S7")
        pieces = text.split(PLACEHOLDER_TEXT)
        filled = [pieces[0]]
        for index, rest in enumerate(pieces[1:], 1):
            filled.append("第 %d 段实际设计内容，已经写明依据、数值与结论，可复核。" % index)
            filled.append(rest)
        filled = "".join(filled)
        self.assertNotIn(PLACEHOLDER_TEXT, filled)
        self._write(name, rel, filled)
        self.assertEqual(self._s7(name, 2), [], "各章写成实际内容后不应再报 S7")

    def test_markers_cover_the_placeholder_vocabulary(self):
        for marker in ("待填写", "待设计", "TODO", "TBD"):
            self.assertIn(marker, PLACEHOLDER_MARKERS)
        self.assertEqual(PLACEHOLDER_TEXT, PLACEHOLDER_TEXT.strip())

    def test_sample_fixture_has_no_s7(self):
        name = "plchsample"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 7):
            self.assertEqual(self._s7(name, sid), [], "停点 %d 不应误报 S7" % sid)

    def test_tick_leaves_new_doc_skeleton_unfinished(self):
        name = "plchtick"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        force_done(self.root, name, 1)
        self._new_doc(name, 2, "--force")
        review(self.root, name, 2)
        tick_report(self.root, name)
        state = load_state(self.root, name)
        row = next(item for item in state["stops"] if int(item["id"]) == 2)
        self.assertNotEqual(row["state"], DONE, "占位文档未过闸门，tick 不应自动完成停点 2")
        self.assertTrue(self._s7(name, 2), "闸门应报 S7")


if __name__ == "__main__":
    unittest.main()
