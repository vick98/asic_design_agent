# pubip_complex_mult 框架式 TB 移交说明（tb_build → rtl_sim）

> 2026-08-27 移交。构建方：框架流程（pub_code 公共 IP 功能验证层）。

## 被测模块
`pub_code/pubip_complex_mult.v`（纯组合可配置复数乘法器），验证对象与依据：
- 公式依据 `rules/pubip.md`（2026-08-27 已与代码核对）
  - CONJ_EN=0（A*B）：Re = ar*br - ai*bi；Im = ar*bi + ai*br
  - CONJ_EN=1（A*conj(B)）：Re = ar*br + ai*bi；Im = ai*br - ar*bi
- 参数：DINA_WIDTH=10 / DINB_WIDTH=6 / CONJ_EN=0；输出 o_dout_* = DINA+DINB = **16bit signed 补码**
- DUT 无时钟/复位端口（纯组合），TB 时钟仅供组件逐拍节奏使用

## 布局与参数
- 目录：`pub_code/testbench/pubip_complex_mult/`（公共 IP 模块级布局，见 rules/tb.md §1.2）
- 编译（rules/sim.md 场景 C）：
  ```bash
  cd <MIRROR>/pub_code/work/pubip_complex_mult/   # 首次需服务器侧 mkdir -p（rsync 排除 work/）
  vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_complex_mult/pubip_complex_mult_tb.f \
      -y ../.. +libext+.v+.sv -l compile.log
  ./simv +TC=<tc_name> +SEED=<n> 2>&1 | tee sim.log
  ```
- **DUT 例化：CONJ_EN=0 默认**；CONJ_EN=1 变体需编译加 **`+define+PUBIP_CM_CONJ`** 重编译后单独 `+TC=tc_cm_conj` 运行（refm/工厂/sim_top 均按该宏联动，cm_conj 不在 tc_all 内）

## TC 清单（一测试点一用例）
| 用例 | 测试点 | 要点 |
|------|--------|------|
| tc_cm_re_basic | 实部基本（CONJ_EN=0） | (3,2)(1,4)→Re=3*1-2*4=**-5**（16bit 补码 0xFFFB）；另附零向量与 3 个代表向量 |
| tc_cm_im_basic | 虚部基本（CONJ_EN=0） | (3,2)(1,4)→Im=3*4+2*1=**14**；随后 **300 拍** `$urandom_range` 随机（A 10bit / B 6bit 全码域，`+SEED=` 复现） |
| tc_cm_neg | 负数/混合符号象限 | 按输出 (Re,Im) 四象限各取一：(3,2)(1,4)→(-5,14)、(-3,2)(1,4)→(-11,-10)、(-3,-2)(1,4)→(5,-14)、(3,-2)(1,4)→(11,10)；另附 B 虚部为负 (-3,2)(1,-4)→(5,14)、B 双负 (3,2)(-1,-4)→(5,-14) |
| tc_cm_overflow_range | 最大幅值/边界 | (511,511)(31,31)→Re=0, Im=**31682**（16bit 带符号可容纳）；A=-512 / B=-32 边界组合 6 向量；含 32768 回绕角点 (-512,-512)(-32,-32)→Im=32768 回绕为 **-32768**（RTL 与 refm 语义一致，属 16bit 补码标准回绕） |
| tc_cm_conj | 共轭（CONJ_EN=1） | `+define+PUBIP_CM_CONJ` 编译；固定点 (3,2)(1,4)→Re=3+8=11, Im=2-12=-10、(3,2)(1,-4)→Re=-5, Im=14、(-3,2)(1,4)→(5,14)；另附 100 拍随机 |

tc_all 聚合：cm_re_basic → cm_im_basic → cm_neg → cm_overflow_range（cm_conj 需宏变体，不聚合）。

## 机制说明（调试必读）
- **一拍一 item**：driver 在 **negedge** 驱动 A/B 输入（先 `m_drv_mb.put` 广播再驱动，见 rules/tb.md 7.2 竞态约定）；DUT 为 0 延迟纯组合，输出在驱动后立即稳定；monitor 每 **posedge+#mon_skew** 采样 o_dout_re/o_dout_im
- **期望回填**：refm 覆写虚任务 `model()`，调用无状态纯函数 `compute(ar,ai,br,bi,conj,exp_re,exp_im)` 按参考公式回填（基类 `run()` 统一广播，见 rules/tb.md 9.3 节）
- **compute 数学实现**（关键）：先把 10/6bit 输入**符号扩展**到 18bit，做精确乘加（乘积 16bit 精确、和差 17bit 内），再赋值 16bit 输出**自动截取低 16bit**——与 RTL 16bit 有符号补码回绕语义严格等价（对任意输入成立，含 32768→-32768 角点）
- **对齐**：期望队列入队（driver 广播时）与 DUT 采样（下一 posedge）逐拍 1:1；比对窗口由 `m_cmp_start`（monitor）/`m_watch`（item）隔离——watch=0 的采样跳过比对但不 pop，保持队列配对
- **驱动时序关键点**：激励在 negedge 生效、组合输出立即可见、posedge+skew 采样——若期望序列与波形差一拍，按此换算

## 仿真验证重点
1. **有符号数**：输入/输出均为 2 的补码；接口与 item 全用 `logic signed`，scoreboard 用 `!==`（按位 case 比较）比对 16bit 有符号值，X 态用 `^sig === 1'bx` 约简判定（部分 X 也可检出）
2. **期望值计算依据**：全部期望由 refm.compute 公式产生（独立数学公式，非照抄 RTL）；固定向量经手工核算落在测试语句注释中，作为公式锚点
3. **随机向量易错点**：全码域随机会命中 16bit 回绕组合（如 ±16384 相加 = ±32768），属"输出位宽内已知回绕"——refm 与 RTL 一致回绕即 PASS；若怀疑误报，先核对 refm 截位语义（精确算术低 16bit）与 RTL（16bit 回绕）等价性
4. **CONJ 变体**：`+define+PUBIP_CM_CONJ` 一并切换 sim_top 例化参数、refm 公式、factory 注册；变体编译下跑 `tc_all`（不含 conj 专用用例）同样 PASS（双侧一致），CONJ 语义验收以 `+TC=tc_cm_conj` 为准
5. **预检状态**：本地 verible lint 全部通过（唯一告警为 sim_top 框架规定 `$srandom` 播种，见 rules/tb.md 7.2，与 pubip_counter 参考平台一致，属预期）；框架合规自检（无 clocking/program/rand/constraint、无自造时钟/复位/超时/波形命名、接口 i_ 初值、driver 先广播后驱动、refm 覆写 model、scoreboard 覆写 pending_count、filelist 绝对路径）通过
