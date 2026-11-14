---
name: "step3_sys_spec"
description: "写子系统规格书和模块接口，推不出的位宽列为待点选。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 接口定义

输入：plan_doc/{sys}_plan.md

输出：spec_doc/{sys}_spec.md

必读：`rules/roles/step3_sys_spec.md`、`rules/spec.md`、`rules/templates/sys_spec.md`、`rules/templates/module_spec.md`、`rules/decision.md`

禁止：不手算位宽、不提前写逻辑块、不重新划分模块

返回格式：返回小结，列出接口产物和待点选的位宽。

规则正文只读 `rules/roles/step3_sys_spec.md`。
