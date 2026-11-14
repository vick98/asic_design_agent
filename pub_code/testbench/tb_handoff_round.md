# pubip_round 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-10-06 移交。构建方：框架流程（pub_code 公共 IP 功能验证层，仿照 pubip_sat）。
> 被测件：`pub_code/pubip_round.sv`（定点收尾舍入：half-up 右移 + 对称饱和，纯组合零延迟）。
> 契约与参数口径以 `rules/pubip.md` 的 `pubip_round` 一节为准（需求书为开发期输入，已随交付归档删除）。

## 被测模块

`pub_code/pubip_round.sv`，收尾（finish）一步：`sat_sym((x + 2^(N-1)) >>> N)` 收进更窄容器。

- **舍入**：half-up，先加半个 LSB 再算术右移 N 位；0.5 LSB 边界向正方向取整（-2.5 → -2）。
- **饱和**：对称饱和，界 `[1−2^(W_dst−1), 2^(W_dst−1)−1]`（`I` 不含符号位）。
- **负满码钳位（补充需求）**：输出一律不得等于补码负最大值 `2^(W_dst−1)`（非对称最小）；右移结果数值恰为该值时钳到 `1−2^(W_dst−1)`。
- `SHIFT_NUM = 0` 退化为纯对称饱和收位；`IN_TOTAL_WIDTH ≤ 63`（中间量 64 位）。

## 布局与参数

- 目录：`pub_code/testbench/pubip_round/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- 编译（rules/sim.md 场景 C）：`cd <MIRROR>/pub_code/work/pubip_round/`，
  `vcs -sverilog -full64 -j 4 -assert svaext -f ../../testbench/pubip_round/pubip_round_tb.f -y ../.. +libext+.v+.sv -l compile.log`
- 运行：`./simv +TC=<tc_name> +SEED=<n> 2>&1 | tee sim.log`（默认 `+TC=tc_all`）
- 参数单一事实源：`pubip_round_cfg.svh`——宏选变体，**N 由闭合式 `N = (W_src−I_src) − (W_dst−I_dst)` 在 cfg 里编译期复算**，DUT 例化/if/item/refm/scoreboard/用例全部引用同一组宏，不存在第二处填数。
- 逐变体回归（8 个变体各编译一次再跑 `tc_all`）。G01 评审落地后框架提供编译宏透传，
  一条命令完成同步、编译、运行、回拉与运行记录，不再手工 ssh：
  ```bash
  # <SYS> 为发起改动的子系统（记录挂它）；日志与回拉产物落 pub_code/work/pubip_round/，
  # 日志名带变体宏（如 sim_PUBIP_ROUND_Z4.log），多变体互不覆盖。
  python3 script/framework.py run sim --scenario pubip --module pubip_round \
      --sys <SYS> --define PUBIP_ROUND_Z4 --seeds 20261006
  ```
  逐个变体替换 `--define`（取空/`PUBIP_ROUND_RXMF`/`PUBIP_ROUND_CORR`/`PUBIP_ROUND_NZERO`/
  `PUBIP_ROUND_DELTAI`/`PUBIP_ROUND_EXPAND`/`PUBIP_ROUND_SMALL`/`PUBIP_ROUND_Z4`；
  默认变体不带 `--define`）。变体宏见 `pubip_round_cfg.svh`；每轮判据看日志末行的
  `RESULT : PASS/FAIL` 与 `Total checks`。
  2026-10-11 补：新增 `PUBIP_ROUND_Z4`（`<48,7,t>` → `<34,23,t>`，N=30）——`W_dst > 32`
  时界常量在 32 位 `int` 里会溢出成 -1（RTL 与 refm 都中招），本变体把这条覆盖住。
  变体共 8 个，回归要 8 轮。

## 变体与挂接点

| 变体宏 | 输入 → 输出 | N | 对应挂接点 / 用途 |
|--------|-------------|---|-------------------|
| （默认，无宏） | `<33,11,t>` → `<12,1,t>` | 11 | tx_fir 发射成形收尾（stamp 7ebf9bcd0944） |
| `PUBIP_ROUND_RXMF` | `<33,13,t>` → `<12,1,t>` | 9 | rx_mf 匹配滤波收尾（stamp 79322e61bd99） |
| `PUBIP_ROUND_CORR` | `<24,2,t>` → `<12,1,t>` | 11 | rx_corr 抽样收尾 / rx_costas 环路递推收尾（stamp 3813b351ecf7） |
| `PUBIP_ROUND_NZERO` | `<12,1,t>` → `<12,1,t>` | 0 | N=0 退化（纯对称饱和收位，负满码钳位唯一必然可达的路径） |
| `PUBIP_ROUND_DELTAI` | `<16,8,t>` → `<12,4,t>` | 0 | I_dst < I_src 的缩径饱和（16 位穷举） |
| `PUBIP_ROUND_EXPAND` | `<16,8,t>` → `<20,12,t>` | 0 | 输出比输入宽（同格式扩张，验证低位取法/符号位处理） |
| `PUBIP_ROUND_SMALL` | `<8,3,t>` → `<4,1,t>` | 2 | 小位宽 + 非零移位（穷举 256 点） |
| `PUBIP_ROUND_Z4` | `<48,7,t>` → `<34,23,t>` | 30 | `W_dst > 32` 宽输出（32 位界常量溢出回归；宽出窄入 z4 收尾挂接点） |

## TC 清单（一测试点一用例）

| 用例 | 测试点 | 期望要点 |
|------|--------|----------|
| `tc_full_scan` | 全值域穷举（`W_src ≤ 16` 的变体才进 `tc_all`） | 0 ~ 2^W_src−1 逐点与 refm 值语义公式零差异：DELTAI/EXPAND 65536 点、NZERO 4096 点、SMALL 256 点 |
| `tc_half_bound` | 0.5 LSB 半值边界（正负各一组，delta ∈ {−1,0,+1}） | `x = k·2^N + 2^(N−1) + delta`；delta=0 处 half-up 向正方向取整（−2.5 → −2） |
| `tc_sat_pos` | 正侧对称饱和 | `+2^(W_dst−1)` 邻域 ±3 个输出整数单位：界内保留、越界钳 `2^(W_dst−1)−1` |
| `tc_sat_neg` | 负侧对称饱和 | `−2^(W_dst−1)` 邻域：钳到 `1−2^(W_dst−1)`，不得出现负满码 |
| `tc_neg_asym` | **负满码钳位专项** | 负满码位图/邻域/整数倍逐个驱动；计数板另有"输出 === 负满码"逐拍不变量 |
| `tc_nzero` | N=0 纯饱和收位 | 0、±1、±界、负满码、源极值 |
| `tc_random` | 随机扫描 | 2000 拍，一半全位宽随机、一半以 `±2^(W_dst−1)` 为中心的小偏移（33/24 位变体靠这一档补覆盖） |
| `tc_clamp_check` | **负满码钳位自检**（不依赖 refm，用例内独立闭式） | `W_src ≤ 16` 全值域逐点判、大位宽走构造邻域 + 5000 随机；负满码必须钳到对称负界，且统计"钳位实际触发次数" |
| `tc_all` | 聚合 | 按 `ifdef PUBIP_ROUND_HAVE_FULL_SCAN` 决定是否含 `tc_full_scan`，其余全含 |

单个用例可单独跑：`./simv +TC=tc_neg_asym +SEED=1`。变体用例必须对应宏重编译。

## 机制说明（调试必读）

- **逐拍事务**：一拍一个 item。driver 在 negedge+`drv_skew` 驱动 `i_data`（先 `m_drv_mb` 广播，refm 同步算期望入队，再驱动接口）；纯组合 DUT 零延迟，monitor 在下一拍 posedge+`mon_skew` 采样 `o_data`；期望队列与采样 1:1。
- **比对窗口**：`m_cmp_start` 在序列驱动前后错开采样点置位/清位（`drive_seq` 里 `#(mon_skew+0.1)`），关窗拍的 `m_watch=0` 不比对，避免首尾多比/漏比。
- **期望值链**：用例只填激励，期望由 `pubip_round_tb_refm.svh` 的 `compute()`（无状态纯函数，**值语义**：补码位图 → 有符号整数 → 加半右移 → 对称饱和 → 输出位图）回填。与 RTL 的"位图 + 阈值比较"是两条不同实现路径。
- **三方口径对照（开发期已做，脚本随交付归档删除）**：值语义参考公式（= refm 的 `compute()`）、RTL 位图复刻、以及 `framework/toolbox/fx.py` 的 `round_shr`/`sat_bounds`（即 `python3 script/framework.py fx finish <src> --dest <dst> --n N`）三者做全值域互钉，开发期结论是零差异。现在改 RTL 或 refm 时，可比对的两端是：refm 的值语义公式（本文件 §机制说明）与 `fx finish` 的输出（含 stamp），RTL 侧直接看仿真比对。
- **`tc_clamp_check` 的自检口径**：它自己在用例里算闭式（`y = (x + 2^(N−1)) >>> N`，N=0 时 `y = x`），不调用 refm；`$sformatf` 打印的 `clamp hits` 为 0 说明这条判据在该变体下没被覆盖——只有 NZERO（N=0）必然能触发（N>0 时加半会把 `−k·2^N` 抬到 `−k·2^N + 2^(N−1)`，右移后不可能恰好等于负满码）。其余变体仍逐拍检查"输出不得等于负满码"的不变量。

## 仿真验证重点

1. **负满码钳位（本次补充需求的验收点）**：`tc_neg_asym` + `tc_clamp_check` + 计分板的逐拍不变量三处覆盖；NZERO 变体是判据真正生效的路径（RTL 里 `wir_shifted_asym_min` 分支被走到）。
2. **0.5 LSB 半值方向**：`tc_half_bound` 的负数点验证"先加后移"是向正方向取整，不是向负无穷截断；与 RTL 的 `(x + 2^(N−1)) >>> N` 同式。
3. **位宽几何两种异常**（v1.0 开发中实测踩到，已修）：负满码判据若按位图判会误钳界内值；窄有符号容器移位再赋值在位宽扩张配置下会给出错误位图。EXPAND/DELTAI 是这两条的回归用例。
4. **每拍比对** `o_data` + X 态检查（`$isunknown`）+ 期望队列空判"多余输出"（scoreboard），比对数为 0 也判 FAIL（框架 `report_summary` 的零比对保护）。
5. **随机可复现**：`+SEED=<n>` 在 sim_top 里 `$srandom(seed)`；用例内不再播种。换种子可复跑 `tc_random` 与 `tc_clamp_check` 的随机档。
