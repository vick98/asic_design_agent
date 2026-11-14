# pubip_sat 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-08-27 移交。构建方：框架流程（pub_code 公共 IP 功能验证层第二模块，仿照 pubip_counter）。

## 被测模块
`pub_code/pubip_sat.sv`（通用饱和截位，纯组合零延迟），测试重点为近期修复两项 + 全路径覆盖：
- **P0-3**：小数位重对齐（输入小数位 > 输出小数位右移丢弃低位；< 左移补零）——默认配置 <16,8,s>→<8,4,s>（IN_FRAC=7 → OUT_FRAC=3，右移 4 位）
- **P0-4**：位宽扩展配置反向 part-select——<8,4,s>→<16,8,s>（IN_FRAC=3 → OUT_FRAC=7，左移 4 位）
- 有符号对称负饱和（-16.0 非对称最小 → 0x81）、负溢出饱满、零值保护、无符号饱和

## 布局与参数
- 目录：`pub_code/testbench/pubip_sat/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- 编译：rules/sim.md 场景 C：`cd <MIRROR>/pub_code/work/pubip_sat/`，`vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_sat/pubip_sat_tb.f -y ../.. +libext+.v+.sv -l compile.log`
- 运行：`./simv +TC=<tc_name> +SEED=<n> 2>&1 | tee sim.log`（默认 +TC=tc_all）
- 参数单一事实源：`pubip_sat_cfg.svh`（编译宏选择变体，DUT 例化/if/item/refm/scoreboard 全部引用该宏集合）
  - 默认（无宏）：<16,8,s>→<8,4,s>，PROTECT_EN=0
  - `+define+PUBIP_SAT_EXPAND`：<8,4,s>→<16,8,s>（P0-4）
  - `+define+PUBIP_SAT_USIGNED`：<16,8,u>→<8,4,u>
  - `+define+PUBIP_SAT_PROTECT`：默认位宽 + PROTECT_EN=1

## TC 清单（一测试点一用例）
| 用例 | 测试点 | 期望要点 |
|------|--------|----------|
| tc_sat_down_align | 默认配置正数重对齐（**P0-3 验收**） | 2.0=16'h0100→8'h10、2.5=16'h0140→8'h14、0.125→8'h01、1/128→8'h00（低位丢弃） |
| tc_sat_neg | 有符号负数 | -2.0=16'hFF00→8'hF0、-4.0→8'hE0、-8.0→8'hC0、-16.0(16'hF800)→8'h81（对称饱和）、-1LSB(16'hFFFF)→8'hFF（向负无穷截断） |
| tc_sat_ovf_pos | 正溢出饱和 | 15.992=16'h07FF→8'h7F（不溢出边界）；16.0=16'h0800 起→8'h7F 饱和 |
| tc_sat_ovf_neg | 负溢出对称饱和 | -16.0→8'h81（非对称最小饱和）、-16.0078/16'hF7FF→8'h81、-24.0/16'hF400→8'h81 |
| tc_sat_zero_protect | 零值保护 | `+define+PUBIP_SAT_PROTECT` 编译：0→8'h01、截位为 0（0x0001/0x000F）→8'h01；非零正常；对称饱和优先于保护（-16.0→8'h81） |
| tc_sat_random | 全值域随机对拍 | 500 拍 `$urandom_range`，期望由 refm.compute() 公式自算（右移/饱和/对称/保护判定全覆盖） |
| tc_sat_expand | 位宽扩展（**P0-4 验收**） | `+define+PUBIP_SAT_EXPAND` 编译：2.0=8'h10→16'h100、-2.0=8'hF0→16'hFF00、15.875→16'h7F0、-16.0→16'hF800 + 随机 100 拍 |
| tc_sat_unsigned | 无符号路径 | `+define+PUBIP_SAT_USIGNED` 编译：1.0→8'h10、16.0（16'h1000）→8'hFF 饱和、0.125→8'h02 + 随机 100 拍 |

变体用例（protect/expand/unsigned）**不在默认 tc_all 内**，需对应宏重编译后 `+TC=tc_sat_<name>` 单独运行；默认编译下 tc_all = down_align/neg/ovf_pos/ovf_neg/random 五段顺序执行。

## 机制说明（调试必读）
- **逐拍事务**：一拍一个 item。driver 在 **negedge+#drv_skew** 驱动 i_data（先 `m_drv_mb` 广播，refm 同步算期望入队，再驱动接口）；纯组合 DUT 零延迟，monitor 在下一个 **posedge+#mon_skew** 采样 o_data（驱动半周期后输出已稳定）；期望队列与采样 1:1；`m_cmp_start`/`m_watch` 隔离复位窗口比对
- **纯组合等待**：`drive_seq` 驱动后 `wait_cycles(N)` 覆盖全部响应拍采样，关窗前错开采样点（`#(mon_skew+0.1)`），随后 `wait_cycles(2)` 保险
- **期望值链**：用例只填激励 `m_data`，期望由 `pubip_sat_tb_refm.svh` 的 `compute()`（无状态纯函数，**值语义参考公式**：整数部分范围判定 + 算术移位对齐 + 输出位图截取 + 饱和/保护后处理）回填；negedge 驱动 timing 与仿真波形差一拍按此换算

## 仿真验证重点
1. **tc_sat_down_align / tc_sat_expand 是修复验收用例**：P0-3 旧代码右移失效（直接截位）时 down_align 会 FAIL；P0-4 旧代码反向 part-select 时 expand 会 FAIL
2. refm 公式已与本库 RTL 位图公式 Python 交叉验证 48 向量 0 mismatch（截图于构建记录）；4 变体参数下边界值（16.0/15.992、-16.0/-16.0078、无符号 16.0）均覆盖
3. 每拍比对 o_data + X 态检查（`$isunknown`）+ 期望队列空判"多余输出"fail（scoreboard）
4. 随机用例 `+SEED=<n>` 播种于 sim_top（用例内无 `$srandom`），换种子可复现
