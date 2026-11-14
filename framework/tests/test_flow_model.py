# 作者：vick 邮箱：ykun@yk9811.com

"""flow_model.yaml 的模型层测试（依赖表、里程碑、动作策略表、闸门读取面与状态枚举）。

依赖图测试：每个停点闸门读取的产物路径必须落在其依赖闭包的产物内。
闸门读取面按 gates/ 的实际代码取：docs/numeric 用 gates/products.py 对
fixtures/sample 枚举具体产物文件；其余闸门的读取前缀在 GATE_READS 里显式声明，
每项注明代码来源——不是永真断言，依赖表写错（比如行 8 漏掉行 7）时这里会失败。
"""

import os
import unittest

from framework import engine, flow
from framework.flow import load, product_path
from framework.gates import products as gate_products
from framework.state import init_sys, load_state

from .util import RepoTest, checkout_root

SYS = "sample"
FIXTURE_ROOT = os.path.join(checkout_root(), "framework", "fixtures", "sample")

# 建议的依赖表（原样照抄，实施方不得改选）。
EXPECTED_DEPENDS_ON = {
    1: [],
    2: [1],
    3: [2],
    4: [3],
    5: [4],
    6: [5],
    7: [6],
    8: [4, 7],
    9: [6, 8],
    10: [7, 8, 9],
    11: [7, 8],
    12: [10, 11],
}

# 里程碑定义（开发者点选）。
EXPECTED_MILESTONES = {
    "M1": {"name": "方案确认", "covers": [1, 2, 3], "blocks": [4], "terminal": False},
    "M2": {"name": "规格冻结", "covers": [4, 5, 6], "blocks": [7], "terminal": False},
    "M3": {"name": "签核放行", "covers": [7, 8, 9, 10, 11, 12], "blocks": [], "terminal": True},
}

# 六条红线动作都必须在动作策略表里且 class 为 redline。
EXPECTED_REDLINES = {
    "decision_directional",     # 1. 方向/数值裁决的入库、改写、撤回
    "cov_threshold_down",       # 2. 降低覆盖率阈值
    "allow_violation",          # 3. 带违例送审
    "problem_close_tradeoff",   # 4. 关闭需要取舍的阻断问题
    "milestone_confirm",        # 5. 里程碑确认
    "flow_policy_change",       # 6. 改动作策略表或里程碑定义
}

LEGAL_CLASSES = {"auto", "decision", "milestone", "redline"}

# 各闸门读取的产物路径（子系统相对路径，前缀即可）。每一项注明代码来源：
# - numeric: gates/numeric.py scan_tree → products.doc_texts → products.DOC_FOLDERS，
#   即四个文档目录里的具体产物文件（info_input/ 只认总览），下方按 fixture 枚举。
# - docs: gates/docs.py scan_docs → doc_texts 同上；scan_notes/_refs 读的也是这些产物 md。
# - lint: gates/run.py _lint_findings → engine.inputs_digest 的 lint 输入集 rtl/ +
#   pub_code + include 链；pub_code 是子系统产物之外的公共件，不进产物比对。
# - rtl: gates/rtl.py scan_rtl 逐模块读 spec_doc/<mod>_spec.md 与 rtl/<mod>.sv。
# - conn: gates/rtl.py scan_conn 只读 rtl/（顶层与模块）。
# - tc: gates/tc.py scan_tc 只读 testbench/。
# - sim: 仿真输入集 rtl/ + testbench/（tb_common、pub_code 在子系统产物之外）。
# - coverage: gates/run.py _coverage_findings 绑定最近一次 sys 全量回归，输入同 sim。
# - synth: 综合输入 rtl/ + pub_code + SDC；SDC 路径由运行记录 --sdc 携带（任意路径，
#   不是固定产物文件），动作上归 sdc_constraints 决策，不进本比对。
# - sta: 时序输入 = 综合网表（行 11 自身产物 dc/）+ SDC（同上）。
# - signoff: gates/run.py 行 12 只读状态（行 11 是否已完成），不读产物路径。
GATE_READS = {
    "numeric": ("docs",),
    "docs": ("docs",),
    "lint": ("rtl/",),
    "rtl": ("spec_doc/", "rtl/"),
    "conn": ("rtl/",),
    "tc": ("testbench/",),
    "sim": ("rtl/", "testbench/"),
    "coverage": ("rtl/", "testbench/"),
    "synth": ("rtl/",),
    "sta": ("dc/",),
    "signoff": (),
}


def _product_strings(model):
    """{停点号: 产物路径前缀}，{sys} 换成 sample。目录产物以 / 结尾。"""
    return {sid: product_path(stop, SYS) for sid, stop in model["by_id"].items()}


def _owner(path, prods):
    """路径归属的最小停点号；不属于任何停点产物则 None。"""
    owners = [sid for sid in sorted(prods) if path.startswith(prods[sid])]
    return owners[0] if owners else None


def _doc_files():
    """fixtures/sample 里的文档产物（相对路径），与 docs/numeric 闸门的读取面同源。"""
    return sorted(gate_products.doc_paths(FIXTURE_ROOT))


def _gate_reads(stop, prods, doc_files):
    """停点闸门会读取的产物路径集合，只保留该停点运行时已存在的部分。

    存在性按归属停点号判断：闸门读的是磁盘上已写出的产物，行 s 运行时
    行 1..s-1 的产物与自身产物已存在（执行顺序就是行号顺序）。
    """

    def present(path):
        owner = _owner(path, prods)
        return owner is not None and owner <= stop["id"]

    reads = set()
    for gate in stop.get("gates") or []:
        for item in GATE_READS[gate]:
            if item == "docs":
                reads.update(doc_files)
            else:
                reads.add(item)
    return {path for path in reads if present(path)}


class FlowModelTests(RepoTest):
    """模型测试只读，借 RepoTest 固定 ADF_ROOT，读到的模型与正式文件逐字节同源。"""

    def test_yaml_loads_and_version(self):
        model = load()
        self.assertEqual(model["version"], 2)
        self.assertIn("by_id", model)
        self.assertEqual(sorted(model["by_id"]), list(range(1, 13)))

    def test_states_unchanged(self):
        model = load()
        self.assertEqual(model["states"], ["未开始", "进行中", "已送审", "完成（审核通过）"])
        self.assertEqual(set(model["transitions"]), set(model["states"]))
        # "待里程碑"是派生显示态，不得写进 states。
        self.assertNotIn("待里程碑", model["states"])

    def test_dead_config_removed(self):
        """human 与 explicit_enter 已从模型删除（开发者点选），引擎不读、模型不再声明。"""
        model = load()
        self.assertNotIn("explicit_enter", model, "explicit_enter 是死配置")
        for stop in model["stops"]:
            self.assertNotIn("human", stop,
                             "停点 %s 仍声明 human（已删除，完成归属由动作表决定）" % stop["id"])

    def test_depends_on_matches_table(self):
        model = load()
        for sid, expected in EXPECTED_DEPENDS_ON.items():
            actual = [int(x) for x in model["by_id"][sid].get("depends_on") or []]
            self.assertEqual(actual, expected, "停点 %s 的 depends_on 与建议表不符" % sid)
        for sid in EXPECTED_DEPENDS_ON:
            self.assertEqual(flow.depends_on(sid), EXPECTED_DEPENDS_ON[sid])

    def test_depends_on_references_known_stops(self):
        model = load()
        for stop in model["stops"]:
            for dep in stop.get("depends_on") or []:
                self.assertIn(int(dep), model["by_id"], "停点 %s 依赖不存在的停点 %s" % (stop["id"], dep))

    def test_milestones_match_flow_table(self):
        self.assertEqual(flow.milestones(), load()["milestones"])
        for mid, expected in EXPECTED_MILESTONES.items():
            item = flow.milestone(mid)
            self.assertIsNotNone(item, "缺里程碑 %s" % mid)
            for key in ("id", "name", "covers", "blocks", "terminal"):
                self.assertIn(key, item, "里程碑 %s 缺字段 %s" % (mid, key))
            self.assertEqual(item["id"], mid)
            self.assertEqual(item["name"], expected["name"])
            self.assertEqual([int(x) for x in item["covers"]], expected["covers"])
            self.assertEqual([int(x) for x in item["blocks"]], expected["blocks"])
            self.assertIs(item["terminal"], expected["terminal"])

    def test_m3_is_only_terminal(self):
        terminals = [m["id"] for m in flow.milestones() if m["terminal"]]
        self.assertEqual(terminals, ["M3"])

    def test_milestones_partition_all_stops(self):
        covered = []
        for item in flow.milestones():
            covered.extend(int(x) for x in item["covers"])
        self.assertEqual(sorted(covered), list(range(1, 13)))

    def test_milestone_blocks_point_outside_coverage(self):
        for item in flow.milestones():
            covers = {int(x) for x in item["covers"]}
            for blocked in item["blocks"]:
                self.assertNotIn(blocked, covers,
                                 "里程碑 %s 阻塞了自身覆盖的停点 %s" % (item["id"], blocked))

    def test_milestone_of_stop(self):
        self.assertEqual(flow.milestone_of_stop(2)["id"], "M1")
        self.assertEqual(flow.milestone_of_stop(5)["id"], "M2")
        self.assertEqual(flow.milestone_of_stop(11)["id"], "M3")
        self.assertIsNone(flow.milestone_of_stop(99))

    def test_dependency_closure_topological_with_self(self):
        self.assertEqual(flow.dependency_closure(1), [1])
        self.assertEqual(flow.dependency_closure(2), [1, 2])
        closure = flow.dependency_closure(10)
        self.assertEqual(closure[-1], 10)
        position = {sid: idx for idx, sid in enumerate(closure)}
        for sid in closure:
            for dep in flow.depends_on(sid):
                self.assertIn(dep, position, "闭包缺依赖 %s" % dep)
                self.assertLess(position[dep], position[sid], "闭包顺序不是依赖在前")

    def test_dependents_are_direct_downstream(self):
        self.assertEqual(flow.dependents(7), [8, 10, 11])
        self.assertEqual(flow.dependents(4), [5, 8])
        self.assertEqual(flow.dependents(12), [])

    def test_action_table_shape(self):
        actions = flow.actions()
        ids = [item["id"] for item in actions]
        self.assertEqual(len(ids), len(set(ids)), "动作 id 重复")
        for item in actions:
            self.assertIn(item["class"], LEGAL_CLASSES,
                          "动作 %s 的 class 非法：%s" % (item["id"], item.get("class")))
            self.assertTrue(item.get("name"), "动作 %s 缺 name" % item["id"])
        self.assertEqual(flow.action("waive_add")["class"], "auto")
        self.assertIsNone(flow.action("no_such_action"))
        self.assertEqual({item["id"] for item in flow.actions_by_class("redline")}, EXPECTED_REDLINES)

    def test_action_table_covers_new_ownership(self):
        """新归属逐条落表：每条现有交互动作都有归属条目。"""
        ids = {item["id"] for item in flow.actions()}
        for expected in (
            "stop_done_auto", "stop_done_milestone", "decision_directional",
            "decision_record", "review_record", "waive_add", "problem_close",
            "problem_close_tradeoff", "item_end", "debug_fix_l0_l1",
            "debug_fix_l2_l3", "allow_violation", "cov_threshold_down",
            "marks_harvest", "git_snapshot", "dispatch_batch", "sdc_constraints",
            "milestone_confirm", "flow_policy_change", "multi_sys_pick",
        ):
            self.assertIn(expected, ids, "动作策略表缺 %s" % expected)
        # 自动类的前提是可选字段（动作表逐条定，有的动作天然无前提）；
        # 写了就必须是非空列表。红线类永不自动，用例在 EXPECTED_REDLINES 上另有断言。
        for item in flow.actions():
            requires = item.get("requires")
            if requires is not None:
                self.assertIsInstance(requires, list)
                self.assertTrue(requires, "动作 %s 的 requires 是空列表" % item["id"])

    # 动作前提（requires）的唯一事实源是动作策略表；执行层（framework/policy.py）按表
    # 执行，两层覆盖关系由 test_policy 双向锁住，这里锁表本身的内容与读取助手。
    EXPECTED_ACTION_REQUIRES = {
        "stop_done_auto": ["gate_pass", "no_blocking", "no_open_item", "review_record"],
        "review_record": ["author_ne_reviewer", "blocking_zero"],
        "waive_add": ["decision_exists_directional"],
        "problem_close": ["evidence_exists_later"],
        "allow_violation": ["decision_id"],
        "cov_threshold_down": ["decision_id"],
    }

    def test_action_requires_match_table(self):
        for aid, expected in self.EXPECTED_ACTION_REQUIRES.items():
            self.assertEqual(flow.requires_of(aid), expected,
                             "动作 %s 的 requires 与动作策略表口径不符" % aid)
        for item in flow.actions():
            if item["id"] not in self.EXPECTED_ACTION_REQUIRES:
                self.assertNotIn("requires", item,
                                 "动作 %s 不该有 requires" % item["id"])

    def test_action_read_helpers(self):
        ids = flow.action_ids()
        self.assertEqual(ids, {item["id"] for item in flow.actions()})
        self.assertEqual(len(ids), len(flow.actions()), "动作号重复")
        self.assertEqual(flow.requires_of("waive_add"), ["decision_exists_directional"])
        self.assertEqual(flow.requires_of("decision_record"), [], "没写 requires 应返回空列表")
        with self.assertRaises(KeyError):
            flow.requires_of("no_such_action")
        got = flow.requires_of("stop_done_auto")
        got.append("no_such_requirement")
        self.assertEqual(flow.requires_of("stop_done_auto"),
                         self.EXPECTED_ACTION_REQUIRES["stop_done_auto"],
                         "requires_of 返回的必须是副本，改副本不能改到模型")

    def test_done_ownership_is_table_driven(self):
        """停点完成归属（自动 vs 里程碑）只由动作表 stops 字段决定，
        引擎不再保留静态常量。两表互斥并恰好覆盖行 1–12。"""
        auto = [int(x) for x in flow.action("stop_done_auto")["stops"]]
        ms = [int(x) for x in flow.action("stop_done_milestone")["stops"]]
        self.assertEqual(auto, [1, 2, 3, 4, 5, 7, 8, 9, 10])
        self.assertEqual(ms, [6, 11, 12])
        self.assertEqual(sorted(auto + ms), list(range(1, 13)))
        self.assertEqual(set(auto) & set(ms), set())
        # 里程碑覆盖停点里的"由里程碑完成"停点都有归属里程碑（派生显示态用）。
        for sid in ms:
            self.assertIsNotNone(flow.milestone_of_stop(sid),
                                 "行 %d 由里程碑完成但无覆盖里程碑" % sid)

    def test_gate_names_all_declared(self):
        """模型里出现的闸门名必须在 GATE_READS 有读取面声明，防止测试静默漏检。"""
        used = set()
        for stop in load()["stops"]:
            used.update(stop.get("gates") or [])
        self.assertEqual(used, set(GATE_READS))

    def test_gate_reads_within_dependency_closure(self):
        """每个停点闸门读取的产物路径都必须落在其依赖闭包的产物内。"""
        model = load()
        prods = _product_strings(model)
        doc_files = _doc_files()
        self.assertTrue(doc_files, "fixture 没有文档产物，docs/numeric 的读取面会比真")
        for stop in model["stops"]:
            sid = stop["id"]
            closure = flow.dependency_closure(sid)
            closure_prods = [prods[d] for d in closure]
            for path in sorted(_gate_reads(stop, prods, doc_files)):
                self.assertTrue(
                    any(path.startswith(prod) for prod in closure_prods),
                    "停点 %s（%s）的闸门读取 %s 不在其依赖闭包 %s 的产物内"
                    % (sid, stop["name"], path, closure))
            # 防真空：文档类停点至少要读到自身产物；行 7 必须同时读到规格书与 rtl。
            if sid in (1, 2, 3, 4):
                self.assertTrue(_gate_reads(stop, prods, doc_files))
            if sid == 7:
                reads = _gate_reads(stop, prods, doc_files)
                self.assertTrue(any(p.startswith("spec_doc/") for p in reads))
                self.assertIn("rtl/", reads)

    def test_load_and_product_path_compat(self):
        model = load()
        self.assertEqual(model["by_id"][8]["name"], "顶层 wrapper")
        self.assertEqual(product_path(model["by_id"][1], "demo"), "info_input/demo_info_overview.md")
        self.assertEqual(product_path(model["by_id"][8], "demo"), "rtl/demo_top.sv")
        self.assertEqual(product_path(model["by_id"][5], "demo"), "spec_doc/")

    def test_review_and_item_block_fields_declared(self):
        """`review:` 与 `blocked_by_items:` 是引擎判据的唯一来源，每个停点都必须声明，
        取值合法且与既有口径一致（引擎里不再写死停点号）。"""
        for stop in load()["stops"]:
            sid = stop["id"]
            self.assertIn(stop["review"], flow.STOP_REVIEWS,
                          "停点 %s 的 review 取值非法" % sid)
            self.assertIsInstance(stop["blocked_by_items"], bool,
                                  "停点 %s 的 blocked_by_items 必须是布尔" % sid)
        self.assertEqual(
            [s["id"] for s in load()["stops"] if flow.stop_review(s["id"]) == "spec_review"],
            [1, 2, 3, 4, 5, 6], "spec_review 范围与 action 表口径不一致")
        self.assertEqual(flow.stop_review(7), "rtl_review_per_module")
        self.assertEqual(flow.stop_review(8), "rtl_review")
        self.assertEqual(
            [s["id"] for s in load()["stops"] if flow.stop_blocked_by_items(s["id"])],
            [7, 8, 9, 10, 11, 12], "在途调试事项的阻挡范围与既有口径不一致")

    def test_review_field_drives_criterion(self):
        """验收：改 flow_model.yaml 某停点的 `review:`，引擎判据随之变化。

        RepoTest 的副本仓库是独立路径，改动会变 mtime/大小，flow 的解析缓存按这两栏失效，
        所以改完立刻生效——不必重启进程（缓存语义）。"""
        name = "revfield"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        ok, reason, _ = engine._review_record_ok(self.root, name, state, 1)
        self.assertFalse(ok, "行 1 是 spec_review，没登记审查记录时判据不该通过")
        self.assertIn("spec_review", reason)
        # 只改行 1 的 review: 字段（唯一事实源），改成 none。
        path = os.path.join(self.root, "framework", "flow_model.yaml")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        changed = text.replace(
            "    gates: [numeric, docs]\n    review: spec_review\n    blocked_by_items: false\n"
            "    product: info_input/{sys}_info_overview.md",
            "    gates: [numeric, docs]\n    review: none\n    blocked_by_items: false\n"
            "    product: info_input/{sys}_info_overview.md")
        self.assertNotEqual(changed, text, "没有定位到行 1 的 review 字段")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(changed)
        self.assertEqual(flow.stop_review(1), "none", "改了 review: 字段但引擎没跟着读")
        ok, reason, ref = engine._review_record_ok(
            self.root, name, load_state(self.root, name), 1)
        self.assertTrue(ok, reason)
        self.assertEqual(ref, "")
        # 同一字段也驱动登记入口：none 不接受 review record。
        from framework.engine import EngineError, review_record
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author="a", reviewer="b")
        self.assertIn("不需要 review record", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
