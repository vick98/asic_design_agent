# sdpram_wrapper 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-08-27 移交；2026-08-31 变更同步（INIT_FILE 功能删除）。构建方：tb_build_agent（public IP 模块级框架式 TB）。

## 被测模块
`pub_code/sdpram_wrapper.sv`（简单双口 RAM wrapper：写口字节使能 / 读口读使能 1 拍输出 / 写优先）。
- **P0-1**（2026-08-27 修复验收）：RAM 深度少一格（地址 63 丢数），修复为 `[RAM_DEPTH]`（深度 64）——tc_wr_rd 为验收用例
- **INIT_FILE 删除**（2026-08-31 变更）：`INIT_FILE` 参数与 `$readmemh` 初始化功能整体删除（string 参数 DC 综合不支持，见 [rules/syn.md](../../rules/syn.md)）；随删 tc_init_file 用例与 memdata.hex，RAM 上电内容不定（X），由使用方保证先写后读

## 布局与参数
- 目录：`pub_code/testbench/sdpram_wrapper/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- **DUT 例化参数（sim_top 固定）**：DATA_WIDTH=32、ADDR_WIDTH=6（深度 64）、BYTE_EN_WIDTH=4
- 小规模变体（`PUBIP_SDPRAM_SMALL`）未构建（任务标注可选；深度 64 完整测试在默认参数覆盖）

## 编译运行（rules/sim.md 场景 C：公共 IP 模块级）
```bash
# rsync 同步后，服务器上首次需 mkdir -p pub_code/work/sdpram_wrapper
cd <MIRROR>/pub_code/work/sdpram_wrapper/
vcs -sverilog -full64 -j 4 -f ../../testbench/sdpram_wrapper/sdpram_wrapper_tb.f \
    -y ../.. +libext+.v+.sv -l compile.log
./simv +TC=tc_all +SEED=1 2>&1 | tee sim.log     # 结果判定以 log 汇总行 grep 'RESULT.*PASS' 为准（退出码恒 0，见 rules/sim.md 退出码说明）
```

## TC 清单（一测试点一用例，factory/tc_all 均已注册）
| 用例 | 测试点 | 要点 |
|------|--------|------|
| tc_wr_rd | 写读回环（P0-1 验收） | 写 0 与 **63** 读回（原 bug 下 63 丢数）；全深度 0..63 各写一值（0xA0000000+addr）再全读回（64 点） |
| tc_byte_en | 字节使能 | 4'h0001/0010/0100/1000 逐字节写后读回：使能字节新值、其余保持旧值；另测 4'h0101 非相邻双字节与独立地址 |
| tc_write_first | 写优先 | 同拍同地址 wea+reb：读输出=新写入值（全字节使能）；bea=4'b0011 逐字节写优先；同拍异地址读写返回旧值；bea=0000 返回写前旧值 |
| tc_rand | 随机对拍 | 先全地址预写，再 300 拍随机 wea/bea/地址/数据/reb 与 refm 行为 RAM 对拍 |

## 机制说明（调试必读）
- **一拍一 item**：driver 在 **negedge** 驱动（先 `m_drv_mb` 广播再驱动）；monitor 每 **posedge+#mon_skew** 采样 `o_doutb`，`m_watch = m_cmp_start && i_reb`（窗口内且读使能才比对）
- **期望来源**：refm 行为 RAM 镜像（`m_mem[64]`），`compute()` 为**无状态纯函数**（内存经 ref 参数传入，写前状态算读期望→再更新内存；与 DUT 语义一致：写优先 bea 拼合、非写优先正常读）
- **配对**：期望仅读事务入队（`m_exp_vld`），与 watch=1 采样按序 1:1；`m_cmp_start` 由 drive_seq 随序列开关，窗口外读不产生比对
- **读时序换算**：item 在 negedge 后一拍 posedge 被 DUT 采样，读数据同拍 posedge 输出——若期望与波形差一拍，按此换算
- **X 态约定**：DUT 无复位端口（纯数据通路），RAM 上电为 X——用例保证**读地址均先被写/预写**（wr_rd/byte_en/write_first 先写后读，rand 先全地址预写），故比对路径无 X；`watch=0` 采样（含上电未初始化拍）不参与比对

## 仿真验证重点
1. tc_wr_rd 为**修复验收用例**，必须 PASS（预计在旧代码上 FAIL：P0-1 下地址 63 读回 X）
2. X 态检查在 scoreboard（watch=1 且输出含 X 记 fail）——若 rand/wr_rd 报"输出 X 态"，优先检查 read 地址是否未被预写
3. 若报"多余有效输出（期望队列空）"或 drain timeout，多为窗口错位/读使能在窗口外残留——按"机制说明"节换算拍序
