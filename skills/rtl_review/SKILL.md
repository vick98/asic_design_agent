---
name: "rtl_review"
description: "只报告发现和建议，不改 RTL。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# RTL 审查

输入：rtl/

输出：审查发现

必读：`rules/roles/rtl_review.md`、`rules/review/rtl.md`、`rules/coding.md`

禁止：不改 RTL、只跑 gate、fx、status 三类命令

返回格式：返回报告五列表（发现编号 | 级别 | 位置 | 建议 | 处置），原样交主持者落盘。

规则正文只读 `rules/roles/rtl_review.md`。
