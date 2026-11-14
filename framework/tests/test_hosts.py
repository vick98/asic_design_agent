# 作者：vick 邮箱：ykun@yk9811.com

import os
import unittest

import yaml

from framework.hosts.render import load_roles, render
from framework.tests.util import _SKIP_DIRS, RepoTest, checkout_root


def _needle():
    return "192." + "168"


def _snapshot(root, skip=()):
    """源码树的 mtime/size 快照。

    跳过 `.git` 与 EDA 临时目录（`work/`、`dc/`、`pt/`、`lint/`，与 `util._SKIP_DIRS`
    和剖面 `sync_excludes` 同一套口径）：这些目录是工具产物，还会留下指向未拉回目标的
    悬空符号链接，`os.stat` 会直接失败，让这条测试跟"跑没跑过仿真"绑在一起。
    剩下的路径用 `lstat` 取，符号链接本身也能稳定取到 mtime/size。
    `skip` 是要排除的相对路径（生成物不在这条"不许触碰"守卫的范围里，改由
    `test_generated_files_match_sources` 逐字节比对源与产物）。
    """
    skipped = {item.replace(os.sep, "/") for item in skip}
    rows = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [name for name in dirnames
                       if name not in _SKIP_DIRS and name not in (".git", "__pycache__")]
        for fn in files:
            path = os.path.join(dirpath, fn)
            if not os.path.lexists(path):
                continue
            rel = os.path.relpath(path, root)
            if rel.replace(os.sep, "/") in skipped:
                continue
            st = os.lstat(path)
            rows.append((rel, st.st_mtime_ns, st.st_size))
    return tuple(sorted(rows))


class HostTests(RepoTest):
    def test_sources_have_no_host_ip(self):
        needle = _needle()
        banned = []
        for base in ("framework", "rules", "toolchain/eda-mcp"):
            for dirpath, dirnames, files in os.walk(os.path.join(self.root, base)):
                dirnames[:] = [name for name in dirnames if name != "__pycache__"]
                for fn in files:
                    if fn.endswith((".py", ".md", ".yaml")):
                        text = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                        if needle in text:
                            banned.append(os.path.relpath(os.path.join(dirpath, fn), self.root))
        self.assertEqual(banned, [])

    def test_render_stays_in_copy(self):
        from framework.paths import project_root
        self.assertEqual(os.path.realpath(project_root()), os.path.realpath(self.root))
        before = _snapshot(checkout_root())
        targets = render()
        self.assertEqual(_snapshot(checkout_root()), before)
        root = os.path.realpath(self.root)
        for path in targets:
            self.assertTrue(os.path.realpath(path).startswith(root + os.sep))
        agents = open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8").read()
        self.assertLess(len(agents.encode("utf-8")), 10240)
        self.assertNotIn(_needle(), agents)

    def test_render_does_not_touch_rules(self):
        """`rules/**` 是手写源文档，render 一个字节都不许写——例外是两份生成物。

        `rules/steps.md`（源 `framework/hosts/steps.md`）与 `rules/pubip.md`（参数/端口表
        由 `pub_code/` 的 RTL 生成）是生成物，守卫强度没有降低，只是**转移**：
        从"禁止触碰"转到 `test_generated_files_match_sources` 的"产物与源逐字节一致"
        （比 mtime/size 更强的判据）。其余 `rules/**` 仍逐字节不许碰。
        """
        rules = os.path.join(self.root, "rules")
        before = _snapshot(rules, skip=("steps.md", "pubip.md"))
        render()
        self.assertEqual(_snapshot(rules, skip=("steps.md", "pubip.md")), before)

    def test_light_stop_dispatch_rule_is_in_the_projection(self):
        """动作策略表是唯一事实源，要渲染进入口投影；主持者按 tick 的两张清单行动，
        rules/methodology.md 里要写同一句（由并发包落笔，串必须一致）。"""
        agents = open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8").read()
        self.assertIn("| 动作 | 归属 |", agents)
        for label in ("自动", "决策", "里程碑", "红线"):
            self.assertIn(label, agents)
        self.assertIn("每个工作包后跑 tick", agents)
        self.assertNotIn("<!-- ACTIONS_TABLE -->", agents)
        rules = open(os.path.join(self.root, "rules", "methodology.md"), encoding="utf-8").read()
        self.assertIn("每个工作包后跑 tick", rules)

    def test_stage_name_rule_is_in_the_projection(self):
        """停点要用名字称呼，不能只报编号：入口与方法论都要写清。"""
        agents = open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8").read()
        self.assertIn("用停点名字", agents)
        rules = open(os.path.join(self.root, "rules", "methodology.md"), encoding="utf-8").read()
        self.assertIn("用停点名字", rules)

    def test_decision_dispatch_rule_is_in_the_projection(self):
        """方向与数值类裁决点选即入库，不再追加一次"是否确认"，入口与规则都要写清
        （rules/decision.md 由并发包落笔，串必须一致）。"""
        agents = open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8").read()
        self.assertIn("点选即入库", agents)
        rules = open(os.path.join(self.root, "rules", "decision.md"), encoding="utf-8").read()
        self.assertIn("点选即入库", rules)

    def test_generated_files_match_sources(self):
        """生成物落后于源要在这里失败——改 `framework/hosts/` 源后必须跑
        `python3 script/framework.py hosts` 重新生成。

        对 render() 写出的每个路径比较渲染前后的正文：比内容，不比 mtime（render
        会重写文件）。副本在类初始化时从仓库整树复制，生成物就是提交的那一份；
        源改了而没重新生成时，渲染输出与副本里的旧正文逐字节不一致，这里即失败。
        `rules/steps.md` 与 `rules/pubip.md` 也在本表：它们是 `rules/**` 里的两份生成物。
        steps.md 的源是 `framework/hosts/steps.md`；pubip.md 的参数/端口表由
        `pub_code/` 的 RTL 生成。忘了重跑 `hosts` 时，由这里逐字节拦下。
        本用例必须是本类里第一个调用 render() 的（按字母序它恰好是），否则比对
        会被前面的渲染洗成永真。
        """
        from framework.hosts.render import HOSTS
        root = self.root
        paths = [os.path.join(root, "AGENTS.md"),
                 os.path.join(root, "rules", "steps.md"),
                 os.path.join(root, "rules", "pubip.md")]
        for role in load_roles():
            paths.append(os.path.join(root, "skills", role["id"], "SKILL.md"))
        for host in HOSTS:
            paths.append(os.path.join(root, "skills", host["id"], "SKILL.md"))
        before = {path: open(path, encoding="utf-8").read() for path in paths}
        render()
        for path, text in before.items():
            self.assertEqual(
                open(path, encoding="utf-8").read(), text,
                "生成物落后于源：%s（先跑 python3 script/framework.py hosts 重新生成）"
                % os.path.relpath(path, root))

    def test_generated_frontmatter(self):
        render()
        roles = {role["id"]: role for role in load_roles()}
        for role_id, role in roles.items():
            skill = os.path.join(self.root, "skills", role_id, "SKILL.md")
            skill_data = _front(skill)
            self.assertEqual(skill_data["name"], role_id)
            self.assertTrue(skill_data["description"])
            text = open(skill, encoding="utf-8").read()
            self.assertIn("rules/roles/%s.md" % role_id, text)
        for host_id, pointer in (("host_design", "rules/host/design.md"), ("host_code", "rules/host/code.md")):
            skill = os.path.join(self.root, "skills", host_id, "SKILL.md")
            data = _front(skill)
            self.assertEqual(data["name"], host_id)
            self.assertTrue(data["description"])
            self.assertIn(pointer, open(skill, encoding="utf-8").read())

    def test_skills_directories_match_roles(self):
        """skills/ 下只允许角色卡与两张主持卡，避免删角色后留下旧技能卡。"""
        from framework.hosts.render import HOSTS
        expected = {role["id"] for role in load_roles()} | {host["id"] for host in HOSTS}
        skills = os.path.join(self.root, "skills")
        actual = {name for name in os.listdir(skills)
                  if os.path.isdir(os.path.join(skills, name))}
        self.assertEqual(actual, expected)

    def test_review_kinds_map_to_roles(self):
        """每个非 none 审查要求都要有角色卡覆盖对应停点，不能只靠通用子代理。

        `rtl_review_per_module` 是引擎的逐模块口径，写卡的角色同名 `rtl_review`；
        其余取值与角色号同名。角色卡缺 `stops` 覆盖时也在这里报出来。
        """
        from framework import flow
        roles = {role["id"]: role for role in load_roles()}
        mapped = {"rtl_review_per_module": "rtl_review"}
        for stop in flow.load()["stops"]:
            sid = int(stop["id"])
            kind = flow.stop_review(sid)
            if kind == "none":
                continue
            role_id = mapped.get(kind, kind)
            self.assertIn(role_id, roles,
                          "停点 %d 的审查要求 %s 在 roles.yaml 里没有对应角色" % (sid, kind))
            covered = [int(x) for x in roles[role_id].get("stops") or []]
            self.assertIn(sid, covered,
                          "角色 %s 的 stops 未覆盖审查停点 %d" % (role_id, sid))


def _front(path):
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---\n"):
        raise AssertionError(path)
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


if __name__ == "__main__":
    unittest.main()
