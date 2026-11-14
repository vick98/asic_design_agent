---
name: "tb_review"
description: "行 9 的独立审查插点，只报告发现和建议，不改 TB 与规格书。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# TB 审查

输入：testbench/、spec_doc/、rtl/

输出：审查发现

必读：`rules/roles/tb_review.md`、`rules/review/tb.md`、`rules/tb.md`、`rules/templates/module_spec.md`

禁止：不改 TB、不改规格书、不手算位宽、只跑 gate、fx、status 三类命令

返回格式：返回报告五列表（发现编号 | 级别 | 位置 | 建议 | 处置），原样交主持者落盘。

规则正文只读 `rules/roles/tb_review.md`。
