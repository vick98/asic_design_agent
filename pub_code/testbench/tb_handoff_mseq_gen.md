# pubip_mseq_gen 模块级框架式自测平台移交说明

> 移交 rtl_sim_agent 进行仿真验证（框架式，公共 IP 场景 C）。

## 1. TC 清单（一测试点一用例）

| 用例名（+TC=） | 测试要点 | 内容 |
|---------------|---------|------|
| `tc_mseq_trans1` | 要点 1：TRANS_NUM=1 单步转移 | 定向单 bit/全 1 等 + 18 拍随机初始值；i_cal_en=1 对拍 LFSR 一步值；i_cal_en=0 验证旁路（输出=i_init_seq） |
| `tc_mseq_trans_n` | 要点 2：TRANS_NUM=4 多步跨步（**变体宏**） | 定向 4 步链（0x1/0x7/0xF）+ 20 拍随机；refm 迭代 4 次；**编译需 +define+PUBIP_MPG_TRANS4**（工厂注册宏隔离） |
| `tc_mseq_border` | 要点 3：边界/非法态 | i_init_seq 全 0（LFSR 全零非法态保持 0）与全 1 边界；i_cal_en 随机翻转（10 拍） |
| `tc_mseq_random` | 要点 4：随机 300 拍 | 300 拍 $urandom_range 随机种子/使能逐拍对拍 |

聚合：`tc_all` = tc_mseq_trans1 + tc_mseq_border + tc_mseq_random（默认配置）；编译加 `+define+PUBIP_MPG_TRANS4` 时追加 tc_mseq_trans_n。

## 2. 复用/新编组件

全新构建，无复用（拟作为公共 IP 独立模块 TB；与子系统内模块同构）：

- 参数宏中心：`pubip_mseq_gen_cfg.svh`（单一事实源：`SEQ_WIDTH=4`、`CAL_RULE=31'h3`、`TRANS_NUM=1/4` 随 `PUBIP_MPG_TRANS4`）。
- if / item / driver / monitor / refm / scoreboard / env / sim_top / tc_base / 4 用例 / tc_all / factory。
- 框架组件 `tb_common/` 只读引用；未改 `pub_code/pubip_mseq_gen.sv`。

## 3. 小参验配置与宏变体（关键）

- **默认例化**：`SEQ_WIDTH=4`、`CAL_RULE=31'h3`、`TRANS_NUM=1`（4-bit LFSR 可完整枚举，矩阵展开编译快）。
- **本原多项式映射已校验**（枚举/GF(2) 验证）：RTL 语义 `state={^(CAL_RULE & state), state>>1}` 下，CAL_RULE 位 k = 多项式 x^k 项抽头，x^4+x+1 → 抽头 bits {1,0} → **4'b0011（31'h3）**，周期 15 为最大长度（本原）。注意：x^4+x+1 **不是** 4'b1001（4'b1001 = x^4+x^3+1 也本原，但与本例 x^4+x+1 的语义表达不符，勿用）。
- **变体**：`+define+PUBIP_MPG_TRANS4` → TRANS_NUM=4（cfg.svh 选择），仅供 tc_mseq_trans_n 使用；同一编译产物勿混用不同 +TC。

## 4. 仿真验证重点

1. **期望值计算**：refm.compute() 为独立 LFSR 参考实现（逐拍、逐位抽头奇偶校验 `state={fb,state>>1}`，迭代 `L_TRANS_NUM` 步）——与 RTL 综合期矩阵展开路径不同，校验 `i_cal_en=1` 多步转移与 `i_cal_en=0` 旁路（期望=i_init_seq，不做任何转移）。
2. **纯组合逐拍对拍**：driver negedge（drv_skew 0.1ns）驱动 → 下一 posedge+mon_skew 0.1ns 采样；item 与响应 1:1 配对（`m_cmp_start` 窗口防竞态，时序与 pubip_sat/pubip_counter 样板一致，勿改 base/drive_seq 时序）。
3. **易错边界**：
   - LFSR 全零态为非法态（反馈=移位=0，恒保持 0）——用例定向检查不放"非法态循环"假设。
   - 旁路路径与转移路径的切换（i_cal_en 翻转）期望必须分别计算：旁路输出初始值、转移输出迭代值。
   - 全 1 逐步转移链：1111→0111→0011→0001→1000（反馈 bit0^bit1），用例注释即来源。
4. **两处 X 态防线**：接口 i_init_seq/i_cal_en 已赋初值（`'0`/`1'b0`）；DUT 纯组合无 clk/rst 与寄存器，无打拍链，复位仅作 TB 框架流程用。
5. 判定：以 log 汇总行 `RESULT.*PASS` 为准（`$finish(n)` 入参不映射进程退出码，VCS 2017.03 不支持 `-exitstatus`、退出码恒 0，见 rules/sim.md 退出码说明）；`pending_count()` 覆盖防漏比。

## 5. 编译运行方式（rules/sim.md 场景 C 公共 IP 模块级）

```bash
# 服务器镜像（EDA 服务器 ubuntu，<MIRROR> 见 toolchain/profiles/<剖面>/profile.yaml）；先 rsync 同步 + 将 .f 绝对路径 sed 替换 + mkdir -p 工作目录
cd <MIRROR>/pub_code/work/pubip_mseq_gen/
vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_mseq_gen/pubip_mseq_gen_tb.f \
    -y ../.. +libext+.v+.sv -l compile.log
# 默认配置（TRANS_NUM=1）：
./simv +TC=tc_all +SEED=1 2>&1 | tee sim.log           # 或 +TC=tc_mseq_trans1/border/random
# 变体（TRANS_NUM=4）：重编译（编译加 +define+PUBIP_MPG_TRANS4）
./simv +TC=tc_mseq_trans_n +SEED=1 2>&1 | tee sim.log
# 波形：编译加 +define+DEBUG_CODE_EN（可选 TB_DUMP_TAG）；超时默认 1s（+TB_TIMEOUT_US= 覆盖），等待时间为超时 2 倍
```

注：`tc_all` 运行默认覆盖要点 1/3/4（4 个用例，约 350 拍）；变体用例需单独宏编译运行。
