---
name: "tb_build"
description: "按规则写框架式 testbench，用例结果行使用 RESULT。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# TB 构建

输入：spec_doc/、rtl/

输出：testbench/

必读：`rules/roles/tb_build.md`、`rules/review/tb.md`、`rules/tb.md`、`rules/sim.md`

禁止：不改被测 RTL 功能、不自研时钟复位与统计

返回格式：返回小结，列出用例名和 factory 注册情况。

规则正文只读 `rules/roles/tb_build.md`。
