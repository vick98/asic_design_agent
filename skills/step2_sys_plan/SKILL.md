---
name: "step2_sys_plan"
description: "写模块划分、前后级与交互，不写 RTL。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 系统方案

输入：flow_doc/{sys}_flow.md

输出：plan_doc/{sys}_plan.md

必读：`rules/roles/step2_sys_plan.md`、`rules/templates/step2.md`、`rules/pubip.md`、`rules/decision.md`

禁止：不写 RTL、不手算位宽、不重写流程与定点化

返回格式：返回小结，列出模块划分和待点选项。

规则正文只读 `rules/roles/step2_sys_plan.md`。
