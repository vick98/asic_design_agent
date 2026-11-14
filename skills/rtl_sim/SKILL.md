---
name: "rtl_sim"
description: "用框架命令跑仿真；看节拍默认用 dbg 波形导出，失败时标明退回 tb、rtl 或 spec。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 仿真

输入：testbench/、rtl/

输出：运行记录

必读：`rules/roles/rtl_sim.md`、`rules/sim.md`、`rules/debug.md`、`rules/waveform.md`、`rules/templates/debug_evidence.md`、`rules/pitfalls.md`

禁止：不抄整段日志进状态、不手改 state.json、不改 TB 与 RTL 功能、默认用 dbg 波形导出不改 TB、只能改 testbench/ 里 //DBG_BEGIN 与 //DBG_END 之间的探针块

返回格式：返回小结，含运行结论、退回侧与回修定级（L0–L3，见 rules/debug.md）。

规则正文只读 `rules/roles/rtl_sim.md`。
