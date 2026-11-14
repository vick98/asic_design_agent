# pubip_counter 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-08-27 移交。构建方：框架流程（pub_code 公共 IP 功能验证层首模块）。

## 被测模块
`pub_code/pubip_counter.v`（可配置计数器），测试重点为近期修复三项：
- **P0-5**：`CNT_WIDTH` 默认 `$clog2(MAX_NUM+1)`（MAX_NUM 取 2 的幂时计数 0~MAX_NUM 全走通）
- **P0-6**：`o_cnt_shift` 位宽 = MAX_NUM+1，bit j ↔ 计数值 j（含计数值 = MAX_NUM 的脉冲）
- 启动优先仲裁：同拍 start 与 end/rst 时启动生效（F16）

## 布局与参数
- 目录：`pub_code/testbench/pubip_counter/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- 编译：rules/sim.md 场景 C：`cd <MIRROR>/pub_code/work/pubip_counter/`，`vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_counter/pubip_counter_tb.f -y ../.. +libext+.v+.sv -l compile.log`
- **DUT 例化参数：MAX_NUM=8**（统一参验：CNT_WIDTH=4、o_cnt_shift 9bit），`CYCLE_EN=0`
- 循环模式用例需 **`+define+PUBIP_CNT_CYCLE` 重编译** 后单独 `+TC=tc_cycle` 运行（不在 tc_all 内）

## TC 清单（一测试点一用例）
| 用例 | 测试点 | 期望要点 |
|------|--------|----------|
| tc_basic | 基本计数 | start 脉冲 → 计数 1..8，计满自动停止，输出保持 0 |
| tc_max_end | 计满停止 | MAX_NUM=8 计满（wir_cnt_end）后 en=0、cnt=0（单次模式） |
| tc_pow2_maxnum | 2 的幂位宽 | 0~8 共 9 值全走通，o_counter 4bit 无截断（P0-5） |
| tc_shift_width | 脉冲位宽 | o_cnt_shift 9bit，bit j ↔ 计数值 j，含 bit8（P0-6） |
| tc_rst_clear | 异步复位 | 计数中 rst_n 拉低清零；恢复后 en=0（单次模式保持） |
| tc_cnt_rst | i_cnt_rst | 单次模式计数中输入复位脉冲 → 停止并清零 |
| tc_cnt_end | i_cnt_end | 任何时刻 i_cnt_end → 停止计数（en=0） |
| tc_cycle | 循环计数 | `+define+PUBIP_CNT_CYCLE` 编译：1..8 回绕两轮 + i_cnt_end 停止 |

## 机制说明（调试必读）
- **逐拍事务**：一拍一个 item。driver 在 **negedge** 驱动接口脉冲（DUT 下一 posedge 采样）；monitor 每 **posedge+#mon_skew** 采样；期望字段由用例按 DUT 语义**预置**在 item 中，refm 的 `compute()` 为无状态透传（期望向量即激励封包）
- **对齐**：driver 每拍广播（negedge）→ 期望入队；monitor 同拍序采样（下个 posedge）→ 逐拍 pop 比对，队列 1:1；复位窗口由 `m_cmp_start`/`m_watch` 隔离（比对跳过但保持队列配对）
- 驱动时序关键点：脉冲激励在 negedge 生效、DUT 在下一个 posedge 采样——若用例期望序列与仿真波形差一拍，按此换算

## 仿真验证重点
1. tc_pow2_maxnum / tc_shift_width 是修复验收用例，**必须 PASS**（预计在旧代码上会 FAIL）
2. 每拍扫描比对 en/counter/shift 三信号 + X 态检查（scoreboard 逐拍）
3. rst_clear 用例经 `m_rst_if.rst_n` 在计数中干预复位（用例内允许访问 rst_if，见 rules/tb.md 6.4）
