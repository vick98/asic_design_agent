---
name: "spec_review"
description: "按派工给出的停点审查行 1–6 的规格产物，只报告发现和建议，不改规格书。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 规格审查

输入：spec_doc/、flow_doc/、plan_doc/、info_input/

输出：审查发现

必读：`rules/roles/spec_review.md`、`rules/review/spec.md`、`rules/steps.md`、`rules/templates/step0.md`、`rules/templates/step1.md`、`rules/templates/step2.md`、`rules/templates/module_spec.md`、`rules/templates/sys_spec.md`

禁止：不改规格书、不手算位宽、只跑 gate、fx、status 三类命令

返回格式：返回报告五列表（发现编号 | 级别 | 位置 | 建议 | 处置），原样交主持者落盘。

规则正文只读 `rules/roles/spec_review.md`。
