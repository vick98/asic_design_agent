# pubip_mseq_cal 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-08-27 移交。构建方：框架流程（pub_code 公共 IP 功能验证层，规格书 `pub_code/pubip_mseq_cal_spec.md` 测试要点为权威来源；报告 §7.2 已核实测试要点与代码一致）。

## 被测模块
`pub_code/pubip_mseq_cal.sv`（M 序列任意转移次数计算模块：15 级二进制加权转移链 + 4 段非均匀流水，输入锁存 1 拍 + 4 段流水 = **固定 5 拍延迟**）。
- 重点验收：规格书"段边界与打拍对齐测试"（含修复验收 F6 的 en 门控四段语义）、"与参考模型对比测试"

## 布局与参数
- 目录：`pub_code/testbench/pubip_mseq_cal/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- 编译：rules/sim.md 场景 C：`cd <MIRROR>/pub_code/work/pubip_mseq_cal/`，`vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_mseq_cal/pubip_mseq_cal_tb.f -y ../.. +libext+.v+.sv -l compile.log`
- **DUT 例化参数：默认（CAL_RULE=31'h9/SEQ_WIDTH=31）**——小参验不改动（内部 15 级转移链与 5 拍延迟固化），纯组合+流水仿真无压力
- 运行：`./simv +TC=<tc_name> +SEED=<n>`（随机用例种子由 +SEED 统一播种；默认 tc_all 回归）

## TC 清单（一测试点一用例，与规格书测试要点映射）
| 用例 | 规格书测试要点 | 期望要点 |
|------|----------------|----------|
| tc_cal_trans0 | 基础功能：i_trans_num=0 | 全部 i_cal_en=0，o_seq_out = i_init_seq 延迟 5 拍（3 个不同初值） |
| tc_cal_trans1 | 基础功能：i_trans_num=1 | 输出 = mseq_gen 单步转移（refm 独立 LFSR 1 次迭代） |
| tc_cal_pow2 | 基础功能：单 bit 场景 | 代表值 1/2/32/1024/16384（2^0/2^1/2^5/2^10/2^14）逐级验证 |
| tc_cal_full32767 | 基础功能：32767 全链路 | 全 15 bit=1 最长转移 + 紧邻背靠背（全流水） |
| tc_cal_seg1_bound | 段 1 边界 | 0x6000（bit[14:13]=1）：段 1 消耗后 d1[12:0] 正确传递（后段 en=0） |
| tc_cal_seg2_bound | 段 2 边界 | 0x1E00（bit[12:9]=1）：段 2 消耗后 d2[8:0] 正确传递 |
| tc_cal_vld_align | 流水线：vld 间隔拉高/断续脉冲 | 断续 vld（单拍/短间隙/长间隙/局部连续 3 拍），o_seq_vld 恒 5 拍对齐 + 间隙输出保持（check_out_hold） |
| tc_cal_multi_call | 流水线：连续多拍 vld=1 | 连续 8 拍背靠背、每拍 trans_num 不同（小值/段边界/全链路混合），逐次一一对应 |
| tc_cal_random | 与参考模型对比测试 | 连续 300 拍 vld=1 满载随机对拍（trans_num≤1023 域 75% + 段边界/极值 25% 混合；init_seq 随机非零），+SEED= 可复现 |

## 机制说明（调试必读）
- **一拍一 item**：driver 在 **negedge** 驱动（i_cal_vld/i_init_seq/i_trans_num，DUT 下一 posedge 采样）；monitor 每 **posedge+#mon_skew** 采样 o_seq_out/o_seq_vld；**先广播后驱动**（refm 同步计算期望入队）
- **期望值来源**：refm `compute(init_seq, trans_num)` 为**独立 LFSR 参考实现**——`state = {^(31'h9 & state), state[30:1]}` 单步迭代 trans_num 次（复用 mseq_gen 的 A^1 迭代语义），与 RTL 的 A^(2^k) 常量矩阵 + 联合链实现路径完全不同；trans_num=0 直接返回初值（旁路语义）
- **5 拍对齐机制（核心）**：refm 期望**无延迟入队**（vld=1 项）；scoreboard 按采集 `o_seq_vld` 消耗期望——`o_seq_vld=0` 拍跳过（仅 X 态检查、不消费），`o_seq_vld=1` 拍必须消费一个期望（队列空即"多余有效输出" fail）。期望入队顺序 = 有效输入顺序 = 有效输出顺序，因此连续/断续/背靠背任何节奏下 5 拍错位都被自然吸收，无需延迟缓冲
- **无效拍为何不比对数值**：en=0 时各段寄存器保持原值（规格书语义），数值可为旧值；保持性由 tc_cal_vld_align 的 check_out_hold 专项检查（间隙拍 o_seq_out 相等 + vld=0）
- **比对窗口 `m_cmp_start/m_watch`**：drive_seq 开窗越过采样点（~0.2ns 偏移）→ 从 item0 响应拍起 watch=1；尾巴追加 vld=0 静默 item 归还 i_cal_vld=0；`wait(seq.size()+5)` 覆盖最后响应采样后关窗
- **期望队列只含 vld=1 项**（scoreboard.push_exp 过滤），保持与有效输出 1:1

## 仿真验证重点
1. 上述 9 用例为规格书测试要点转化，**缺一即漏**（tc_all 聚合全部）；随机用例在 tc_all 内同样执行（种子 +SEED= 控制）
2. 每用例含 pass/fail 增量自检（有效输出数 == 有效输入拍数），scoreboard 逐拍比对 o_seq_out + X 态检查 + pending_count 防漏比（DUT 漏输出 → 期望残留计 fail）
3. 易错边界：trans_num=0（全旁路）、段 1/段 2 边界（trans_num 低位跨拍传递）、连续背靠背流水（期望与输出一一对应）、断续 vld（5 拍恒定）
4. random 用例 trans_num 限定 ≤1023 域 + 边界混合（32767×300 全距迭代拖慢仿真；边界值已含 32767/段边界点）

## 追加用例建议（验证覆盖面补充，非本轮阻塞）

仿真通过的 9 用例之外，规格书测试要点尚有未落用例条目，如需 100% 全覆盖可追加：
- 段 3/段 4 边界（0x0180 / 0x007F 仅使能对应段）
- 跨段组合 0x5555（bit 偶数位模式，多段同时使能）
- 段边界单 bit 翻转（13↔12、9↔8、7↔6：跨段临界转移）
- 运行中复位（i_cal_vld 有效流水中断后复位）
- SEQ_WIDTH 非默认值参数化验证（注：SEQ_WIDTH=31 默认路径已由本模块 15 级 mseq_gen 全链路用例覆盖，mseq_gen 单模块大位宽矩阵路径无需单独追加）

以上条目执行时遵循同一用例模式（一测试点一用例 + factory/tc_all 注册）。
