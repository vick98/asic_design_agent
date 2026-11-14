# 作者：vick 邮箱：ykun@yk9811.com

"""缓存的行为测试：flow.load() 按（路径, mtime, 大小）失效，
run_gates 按（停点号, state 内容摘要, 磁盘输入 mtime 集合）备忘，
章节模型（chapters.yaml）与 flow_model 同口径。

缓存只是提速手段，语义必须零变化，所以这里断言的全是可观察行为：

- 在 RepoTest 副本里改 flow_model.yaml / chapters.yaml 后立刻看到新内容；
- 同一份未改的模型只解析一次，且每次返回独立深拷贝；
- 同一份 (state, 磁盘输入) 下 run_gates 只算一遍，磁盘或 state 一变就重算；
- 返回值是副本：调用方改 findings 不会污染备忘里的那份。

另外钉住本包附带的一处收紧：行 9 的平台状态由文件与用例核对推导，骨架不再算合格。
"""

import os
import unittest
from unittest import mock

from framework import flow
from framework.flow import load
from framework.gates import docs
from framework.gates import run as gates_run
from framework.state import init_sys, load_state, sys_dir

from .util import RepoTest, plant_sample


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class FlowLoadCacheTests(RepoTest):
    def test_change_of_copy_is_visible_immediately(self):
        """RepoTest 副本里改 flow_model.yaml，load() 必须重解析（不能读缓存里的旧模型）。"""
        path = flow.model_path()
        self.assertEqual(os.path.realpath(os.path.dirname(path)),
                         os.path.realpath(os.path.join(self.root, "framework")))
        original = _text(path)
        self.assertNotIn("cache_probe", original)
        try:
            _write(path, original + "\ncache_probe: 1\n")
            self.assertEqual(load().get("cache_probe"), 1)
            # 再改一次：缓存键里的 mtime/大小两栏任一变化都要失效。
            _write(path, original + "\ncache_probe: 22\n")
            self.assertEqual(load().get("cache_probe"), 22)
        finally:
            _write(path, original)
        self.assertIsNone(load().get("cache_probe"), "改回原样后 load() 不能还留着探针字段")

    def test_unchanged_model_parses_once(self):
        """同一份未改的 flow_model.yaml 在一次进程里只解析一次。"""
        load()  # 预热
        flow._YAML_CACHE.clear()
        calls = []
        real = flow.yaml.safe_load

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        with mock.patch.object(flow.yaml, "safe_load", counting):
            first = load()
            second = load()
        self.assertEqual(len(calls), 1, "未改动的 flow_model.yaml 不该解析第二次")
        self.assertEqual(first["version"], second["version"])

    def test_load_returns_independent_copy(self):
        """cached_yaml 内部留着原件，调用方拿到的必须是深拷贝（旧行为每次都是新对象）。"""
        name = load()["stops"][0]["name"]
        first = load()
        first["stops"][0]["name"] = "被调用方改掉的名字"
        first["by_id"][1]["name"] = "同一个字典，也改了"
        self.assertEqual(load()["stops"][0]["name"], name)
        self.assertEqual(load()["by_id"][1]["name"], name)


class GateMemoTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "memo"
        init_sys(self.root, self.name)
        plant_sample(self.root, self.name)
        self.base = sys_dir(self.root, self.name)

    def _counted(self, fn):
        """跑 fn，返回 (结果, _run_gates 被真正执行的次数)。"""
        calls = []
        real = gates_run._run_gates

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        with mock.patch.object(gates_run, "_run_gates", counting):
            result = fn()
        return result, len(calls)

    def test_same_state_and_disk_runs_gates_once(self):
        state = load_state(self.root, self.name)
        first, n1 = self._counted(lambda: gates_run.run_gates(self.root, self.name, 7, state))
        second, n2 = self._counted(lambda: gates_run.run_gates(self.root, self.name, 7, state))
        self.assertEqual(n2, 0, "同一份 (state, 磁盘输入) 的第二次调用必须命中备忘")
        self.assertGreater(n1, 0)
        self.assertEqual(first, second)
        # 返回值是副本：调用方往 findings 里塞东西不能污染备忘。
        second.append({"rule": "污染", "where": "", "detail": ""})
        third = gates_run.run_gates(self.root, self.name, 7, state)
        self.assertEqual(third, first)

    def test_disk_change_invalidates(self):
        state = load_state(self.root, self.name)
        before = gates_run.run_gates(self.root, self.name, 7, state)
        _write(os.path.join(self.base, "rtl", "newmod.sv"), "module newmod; endmodule\n")
        after, n = self._counted(lambda: gates_run.run_gates(self.root, self.name, 7, state))
        self.assertEqual(n, 1, "子系统目录里多了文件，闸门必须重算")
        self.assertNotEqual(after, before)
        self.assertTrue(any("newmod" in (item.get("detail") or "") for item in after),
                        "新模块必须出现在行 7 的发现里：%s" % after)

    def test_state_change_invalidates(self):
        state = load_state(self.root, self.name)
        before = gates_run.run_gates(self.root, self.name, 7, state)
        self.assertTrue(any("行 7 缺 lint 记录" in (item.get("detail") or "") for item in before))
        # 状态内容的真实变化：补上该模块的两条证据——lint 运行记录与对得上当前文件的
        # rtl_review 记录（模块通过态由证据推导，不再手工登记 modules 状态）。
        from framework.engine import module_digest
        digest = module_digest(self.base, "alu")
        state["runs"] = [{
            "id": "R001", "capability": "lint", "status": "pass", "summary": "lint pass",
            "profile_id": "p", "scope": {"modules": ["alu"], "module_digests": {"alu": digest}},
            "checks": {"errors": 0},
        }]
        state["modules"]["7"] = [{
            "name": "alu", "kind": "rtl_review", "author": "author-01",
            "reviewer": "reviewer-02", "findings": 0, "digest": digest,
        }]
        after, n = self._counted(lambda: gates_run.run_gates(self.root, self.name, 7, state))
        self.assertEqual(n, 1, "state 内容变了，闸门必须重算")
        self.assertNotEqual(after, before)
        self.assertFalse(any("alu" in (item.get("detail") or "") for item in after),
                         "补上审查证据后 alu 不该再出现在行 7 的发现里：%s" % after)

    def test_same_file_content_change_invalidates(self):
        """文件集合没变、只是某个产物内容变了：闸门也要重算（mtime/大小进键）。"""
        state = load_state(self.root, self.name)
        gates_run.run_gates(self.root, self.name, 7, state)
        _write(os.path.join(self.base, "rtl", "alu.sv"), "module alu; // 改过了\nendmodule\n")
        _, n = self._counted(lambda: gates_run.run_gates(self.root, self.name, 7, state))
        self.assertEqual(n, 1, "同一份 state 下改了产物内容，闸门必须重算")


class SkeletonPlatformTests(RepoTest):
    """行 9 的平台状态由文件与用例核对推导：平台清单来自
    testbench/<dut>/tc，"骨架"不再能靠手工登记蒙过闸门——骨架标记由 tc 的 T6
    规则管，三方（用例文件 / factory / tc_all）一致才 "tc_check 通过"。"""

    def setUp(self):
        super().setUp()
        self.name = "skel"
        init_sys(self.root, self.name)
        self.base = sys_dir(self.root, self.name)
        self.dut = "alu"
        self.tc = os.path.join(self.base, "testbench", self.dut, "tc")
        self._plant_assembled()

    def _plant_assembled(self):
        """造一个三方一致、且不含 tb-gen 骨架标记的平台。"""
        _write(os.path.join(self.tc, "alu_tc_all.sv"),
               "class alu_tc_all;\n"
               "  task body();\n"
               '    alu_tc_basic tc1 = new("tc_basic");\n'
               "    tc1.body();\n"
               "  endtask\n"
               "endclass\n")
        _write(os.path.join(self.tc, "alu_tc_factory.svh"),
               "function alu_tc_base make(string name);\n"
               "  case (name)\n"
               '    "tc_basic": return alu_tc_basic::new("tc_basic");\n'
               "  endcase\n"
               "endfunction\n")
        _write(os.path.join(self.tc, "alu_tc_basic.sv"),
               "class alu_tc_basic;\n"
               "endclass\n")

    def test_assembled_platform_passes_module_check(self):
        findings = gates_run._tc_module_findings(load_state(self.root, self.name), self.base)
        self.assertEqual(findings, [])
        from framework.gates.tc import platform_state
        self.assertEqual(platform_state(self.base, self.dut), "tc_check 通过")

    def test_skeleton_platform_is_not_done(self):
        """用例文件仍是 tb-gen 骨架：平台状态是"骨架"，行 9 报未完成，T6 报出标记。"""
        from framework.gates.tc import platform_state, scan_tc
        from framework.tbgen import SKELETON_MARKS
        _write(os.path.join(self.tc, "alu_tc_basic.sv"),
               "class alu_tc_basic;\n// %s\nendclass\n" % SKELETON_MARKS[0])
        self.assertEqual(platform_state(self.base, self.dut), "骨架")
        findings = gates_run._tc_module_findings(load_state(self.root, self.name), self.base)
        self.assertTrue(any("平台未完成" in item["detail"] for item in findings), findings)
        self.assertTrue(any(item.get("rule") == "T6" for item in scan_tc(self.base)),
                        "骨架标记必须由 T6 规则报出：%s" % scan_tc(self.base))

    def test_incomplete_platform_still_reported(self):
        """装配对不上（factory 没注册用例）：平台没完成，行 9 必须报出来。"""
        _write(os.path.join(self.tc, "alu_tc_factory.svh"), "// 没有注册任何用例\n")
        findings = gates_run._tc_module_findings(load_state(self.root, self.name), self.base)
        self.assertTrue(any("平台未完成" in item["detail"] for item in findings), findings)


class ChapterModelCacheTests(RepoTest):
    """章节模型与 flow_model 同口径：按（路径, mtime_ns, size）失效。

    章节模型原来每次扫描文档都重新 yaml.safe_load 一遍（一次 tick 里几十次），
    接 cached_yaml 后同一份文件只解析一次；改文件必须立刻看到新内容。
    """

    def test_chapters_change_in_copy_is_visible_immediately(self):
        path = docs.chapters_path()
        self.assertEqual(os.path.realpath(os.path.dirname(path)),
                         os.path.realpath(os.path.join(self.root, "framework", "templates")))
        original = _text(path)
        self.assertNotIn("cache_probe", original)
        try:
            _write(path, original + "\ncache_probe: 1\n")
            self.assertEqual(docs.load_chapter_model().get("cache_probe"), 1)
            # 再改一次：mtime/大小任一变化都要失效。
            _write(path, original + "\ncache_probe: 22\n")
            self.assertEqual(docs.load_chapter_model().get("cache_probe"), 22)
            self.assertIsInstance(docs.load_chapter_model().get("documents"), list)
        finally:
            _write(path, original)
        self.assertIsNone(docs.load_chapter_model().get("cache_probe"),
                          "改回原样后章节模型不能还留着探针字段")

    def test_unchanged_chapters_parse_once(self):
        model = docs.load_chapter_model()  # 预热
        flow._YAML_CACHE.pop(docs.chapters_path(), None)
        calls = []
        real = flow.yaml.safe_load

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        with mock.patch.object(flow.yaml, "safe_load", counting):
            first = docs.load_chapter_model()
            second = docs.load_chapter_model()
        self.assertEqual(len(calls), 1, "未改动的 chapters.yaml 不该解析第二次")
        self.assertEqual(first["documents"], second["documents"])
        self.assertEqual(first, model)
        # 深拷贝：调用方改一份不能串到下一份。
        first["documents"].append({"folder": "污染"})
        self.assertNotIn({"folder": "污染"}, docs.load_chapter_model()["documents"])


if __name__ == "__main__":
    unittest.main()
