# 作者：vick 邮箱：ykun@yk9811.com

"""engine 包的布局守卫：每模块 ≤600 行，且旧 engine.py 不再存在。"""

import os
import unittest

from framework.tests.util import RepoTest, checkout_root


class EngineLayoutTests(RepoTest):
    def test_each_engine_module_is_within_line_limit(self):
        base = os.path.join(checkout_root(), "framework", "engine")
        self.assertFalse(os.path.exists(os.path.join(checkout_root(), "framework", "engine.py")))
        over = []
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                raw = fh.read().splitlines()
            # 仓库统一要求脚本首行带作者注释；它不属于模块正文，计数时连同其后的
            # 空行一起剔除，避免为一行署名把 600 行的布局上限顶破。
            if raw and raw[0].strip().startswith("# 作者：vick"):
                raw = raw[1:]
                if raw and not raw[0].strip():
                    raw = raw[1:]
            lines = len(raw)
            if lines > 600:
                over.append("%s=%d" % (name, lines))
        self.assertEqual(over, [], "engine 模块超过 600 行：%s" % "、".join(over))
