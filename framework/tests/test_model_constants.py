# 作者：vick 邮箱：ykun@yk9811.com

"""模型驱动的常量：stage 字段、分阶段分桶、虚拟停点与模块行集合。

停点号与阶段号都来自 `framework/flow_model.yaml`，引擎不再保留静态常量：

- 每个停点声明 `stage:`；`stages:` 给出分阶段裁决表的分组与标题；
- `state.blank()` 的 `decisions`/`seq.D` 分桶与分阶段裁决表按模型的 stage 集合生成；
- `cmd_new_doc` 的停点 → 产物路径映射读 `product` 字段（模块规格书按 `--module` 换文件名）；
- 模块行集合（`modules` 的键、`module --row` 的 choices）由 `review:` 取值推导；
- 行 12 的签核前置遍历它自己的 `depends_on`。

验收在副本 flow_model.yaml 里插入一个**虚拟停点**（带一个全新的阶段）后走通：
init / tick / new-doc / decision commit / 状态渲染都不崩，且新阶段的分桶与标题都出现在
渲染物里。
"""

import os
import unittest

from framework import engine, flow
from framework.state import blank, init_sys, load_state
from framework.tests.util import RepoTest, cli, force_done

# 模型里声明的阶段（行 1→0，2→1，3→2，4–6→3，7–12→5）。
EXPECTED_STAGES = {1: 0, 2: 1, 3: 2, 4: 3, 5: 3, 6: 3, 7: 5, 8: 5, 9: 5,
                   10: 5, 11: 5, 12: 5}
EXPECTED_STAGE_KEYS = ["0", "1", "2", "3", "5"]

VIRTUAL_STAGE = 4
VIRTUAL_STAGE_TITLE = "调试与收敛"
VIRTUAL_STOP = 13
VIRTUAL_PRODUCT = "work/{sys}_extra.md"
AUTO_STOPS_ANCHOR = "    stops: [1, 2, 3, 4, 5, 7, 8, 9, 10]"
STAGES_ANCHOR = "  5: 编码与验证\n"


def _model_path(root):
    return os.path.join(root, "framework", "flow_model.yaml")


def _read(root):
    with open(_model_path(root), encoding="utf-8") as fh:
        return fh.read()


def _write(root, text):
    with open(_model_path(root), "w", encoding="utf-8") as fh:
        fh.write(text)


def add_virtual_stop(root):
    """在副本模型里插入阶段 4 与停点 13（依赖行 12、自动完成、无闸门）。"""
    text = _read(root)
    if "虚拟停点" in text:
        return  # 同类用例共享副本，重复 setUp 不重复插入
    # 阶段表：插在阶段 5 之前，保持声明序。
    assert STAGES_ANCHOR in text, "阶段表锚点不存在"
    text = text.replace(
        STAGES_ANCHOR,
        "  %d: %s\n" % (VIRTUAL_STAGE, VIRTUAL_STAGE_TITLE) + STAGES_ANCHOR, 1)
    # 归属：虚拟停点由自动归属完成。
    assert AUTO_STOPS_ANCHOR in text, "自动归属 stops 锚点不存在"
    text = text.replace(AUTO_STOPS_ANCHOR,
                        AUTO_STOPS_ANCHOR[:-1] + ", %d]" % VIRTUAL_STOP, 1)
    # stops 是文件的最后一个段，直接追加新停点。
    text = text.rstrip("\n") + "\n" + (
        "  - id: %d\n"
        "    step: 验证\n"
        "    name: 虚拟停点\n"
        "    depends_on: [12]\n"
        "    role: rtl_sim\n"
        "    gates: []\n"
        "    review: none\n"
        "    blocked_by_items: false\n"
        "    stage: %d\n"
        "    product: %s\n" % (VIRTUAL_STOP, VIRTUAL_STAGE, VIRTUAL_PRODUCT))
    _write(root, text)


class StageModelTests(RepoTest):
    def test_every_stop_declares_stage(self):
        model = flow.load()
        declared = set(flow.stages())
        for stop in model["stops"]:
            sid = int(stop["id"])
            self.assertIn("stage", stop, "停点 %s 缺 stage:" % sid)
            self.assertEqual(int(stop["stage"]), EXPECTED_STAGES[sid],
                             "停点 %s 的 stage 与既有口径不符" % sid)
            self.assertIn(EXPECTED_STAGES[sid], declared,
                          "停点 %s 的 stage 未在 stages: 表里声明" % sid)
            self.assertEqual(flow.stage_of_stop(sid), str(EXPECTED_STAGES[sid]))

    def test_stage_set_matches_model(self):
        self.assertEqual(flow.stages(), [0, 1, 2, 3, 5])
        self.assertEqual(flow.stage_title(0), "STEP0 信息输入")
        self.assertEqual(flow.stage_title(5), "编码与验证")
        with self.assertRaises(KeyError):
            flow.stage_of_stop(99)

    def test_blank_buckets_come_from_model(self):
        state = blank("demo")
        self.assertEqual(list(state["decisions"]), EXPECTED_STAGE_KEYS)
        self.assertEqual(list(state["seq"]["D"]), EXPECTED_STAGE_KEYS)
        self.assertTrue(all(rows == [] for rows in state["decisions"].values()))
        self.assertTrue(all(count == 0 for count in state["seq"]["D"].values()))

    def test_missing_stage_field_is_rejected(self):
        """模型缺 stage: 字段要报错，不能静默退回默认阶段。"""
        text = _read(self.root)
        marker = "    stage: 0\n"
        self.assertIn(marker, text)
        _write(self.root, text.replace(marker, "", 1))
        try:
            with self.assertRaises(ValueError):
                flow.stage_of_stop(1)
            with self.assertRaises(engine.EngineError):
                engine.stage_of_stop(1)
        finally:
            _write(self.root, text)
        self.assertEqual(flow.stage_of_stop(1), "0")

    def test_module_rows_come_from_review_field(self):
        """modules 的键与 module --row 的 choices 由 review: 推导，不写死 7/8/9。"""
        text = _read(self.root)
        marker = "    review: tb_review\n"
        self.assertIn(marker, text)
        _write(self.root, text.replace(marker, "    review: none\n", 1))
        try:
            self.assertEqual(flow.module_rows(), ["7", "8"])
            self.assertEqual(sorted(blank("demo")["modules"]), ["7", "8"])
            proc = cli(self.root, "module", "demo", "--row", "9", "--name", "x",
                       "--state", "退回")
            self.assertNotEqual(proc.returncode, 0,
                                "行 9 不再是模块行，--row 9 应被 argparse 拒绝")
        finally:
            _write(self.root, text)
        self.assertEqual(flow.module_rows(), ["7", "8", "9"])


class VirtualStopTests(RepoTest):
    """在副本模型里加一个停点与一个新阶段，验证引擎不再依赖写死的停点集合。"""

    def setUp(self):
        super().setUp()
        add_virtual_stop(self.root)

    def _state(self, name):
        return load_state(self.root, name)

    def test_blank_includes_virtual_stage_and_stop(self):
        state = blank("virt")
        self.assertEqual(sorted(state["decisions"]), ["0", "1", "2", "3", "4", "5"])
        self.assertIn("4", state["seq"]["D"])
        self.assertEqual(len(state["stops"]), VIRTUAL_STOP)
        self.assertEqual(flow.stage_of_stop(VIRTUAL_STOP), "4")

    def test_init_tick_new_doc_and_decision_commit_work(self):
        name = "virtflow"
        init_sys(self.root, name)
        state = self._state(name)
        self.assertEqual(len(state["stops"]), VIRTUAL_STOP)
        # 前置状态：行 1–12 直接置完成，虚拟停点由 tick 自动启动并完成。
        for sid in range(1, VIRTUAL_STOP):
            force_done(self.root, name, sid)
        engine.tick_report(self.root, name)
        state = self._state(name)
        self.assertEqual(engine.stop_row(state, VIRTUAL_STOP)["state"], flow.DONE,
                         "虚拟停点应当走通自动启动 + 自动完成")
        # new-doc 的路径来自 product 字段。
        proc = cli(self.root, "new-doc", name, "--stop", str(VIRTUAL_STOP))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        product = flow.product_path(flow.load()["by_id"][VIRTUAL_STOP], name)
        self.assertTrue(os.path.isfile(os.path.join(self.root, name, product)), product)
        # decision commit 落到新阶段的桶里，D 号前缀跟着模型走。
        did = engine.commit_decision(self.root, name, content="虚拟停点口径按模型走",
                                     kind="记录", stop=VIRTUAL_STOP)
        self.assertEqual(did, "D4-001")
        state = self._state(name)
        self.assertEqual([row["id"] for row in state["decisions"]["4"]], [did])
        # 渲染物：新阶段的分组标题进分阶段裁决表，虚拟停点进流程状态表。
        with open(os.path.join(self.root, name, "%s_decision.md" % name),
                  encoding="utf-8") as fh:
            decision_doc = fh.read()
        self.assertIn(VIRTUAL_STAGE_TITLE, decision_doc)
        with open(os.path.join(self.root, name, "%s_status.md" % name),
                  encoding="utf-8") as fh:
            status = fh.read()
        self.assertIn("虚拟停点", status)

    def test_problem_and_review_validation_use_model_stop_set(self):
        """问题/审查记录的停点校验读模型停点集合：虚拟停点合法，模型外停点非法。"""
        name = "virtcheck"
        init_sys(self.root, name)
        engine.add_problem(self.root, name, "阻断", VIRTUAL_STOP, "虚拟停点上的阻断")
        state = self._state(name)
        self.assertEqual(state["problems"][0]["stop"], VIRTUAL_STOP)
        with self.assertRaises(engine.EngineError):
            engine.add_problem(self.root, name, "阻断", 99, "模型外停点")
        with self.assertRaises(engine.EngineError):
            engine.review_record(self.root, name, 99, author="a", reviewer="b")


if __name__ == "__main__":
    unittest.main()
