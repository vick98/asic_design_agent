# pubip_dynamic_mem 框架式自测平台 移交说明（tb_build_agent → rtl_sim_agent）

移交对象：`pub_code/testbench/pubip_dynamic_mem/` 框架式模块级 TB（公共 IP，无子系统归属）。
DUT：`pub_code/pubip_dynamic_mem.sv`（默认 MEM_DEPTH=64/DATA_WIDTH=32/ID_WIDTH=4）。
本模块为「多 ID 链表存储 + T0→T1 全流水读取」握手类模块，自测平台采用**一拍一 item** 逐拍对拍
模式（参考 pubip_counter 样板），期望值由用例侧行为模型按拍预置。

## 1. TC 清单（一测试点一用例，factory/tc_all 已注册 7 用例）

| 用例 | 测试要点 | 场景摘要 |
|------|---------|---------|
| `tc_wr_rd` | 1. 单ID写N笔→FIFO读出 | ID0 写 8 笔（数据 32'hA5B0_0000|i）→ 调度读出 8 笔 → 链空后 ready=0/remain=0 |
| `tc_multi_id` | 2. 多ID交叉写入乱序调度 | ID0×4/ID1×3/ID2×3 交叉写（0,1,2,0,1,2,0,1,2,0）→ 按 2→1→0 乱序调度读出，o_schd_id/remain 逐笔核对 |
| `tc_full_depth` | 3. P0-7 满深度验收 | 单 ID 连续写满 64 笔（first-fit 覆盖地址 0..63，数据=i 含地址语义）→ 满时 o_wr_ready=0 且再写被拒 → 64 笔全部读出（第 64 笔=地址 63 数据，last=1） |
| `tc_rd_last` | 4. 各ID链尾 o_rd_last | ID0×3/ID1×2/ID2×1/ID3×1 各链读到尾（last=1）；单节点链展示保持（rd_vld=0 → 同数据重复展示一拍后消费） |
| `tc_conflict` | 5. 同拍读写冲突 | (a) 单节点链展示同拍写同 ID+消费（冲突覆盖：新节点成为新头、读展示仍为旧头数据、隔一拍展示新数据）；(b) 双节点链消费+后继提升同拍写不同 ID；(c) 写不同 ID 链展开 |
| `tc_remain` | 6. o_free_cnt/remain 随动 | 16×ID0 + 16×ID1 → 读 ID0 16 笔且中段同拍追加 ID1 8 笔（读写同拍不同 ID）→ 读 ID1 24 笔 → 链空核对 |
| `tc_random` | 7. 随机500拍对拍 | 500 拍随机写(60%)/调度(40%)/读(40%)，`+SEED=` 播种，行为模型逐拍对拍 |

## 2. 组件复用 / 新编

- 新建完整模块级平台（无既有组件可复用）：if / item / driver / monitor / scoreboard / env / sim_top /
  用例基类与外露 7 用例，均位于 `pub_code/testbench/pubip_dynamic_mem/`。
- 新编**用例侧行为参考模型** `pubip_dynamic_mem_tb_model.svh`（类 `pubip_dynamic_mem_model`）：
  数组+链表思想的**行为级独立模型**（bitmap/head/tail/link 数组 + T0-T1 展示流水锁存），
  不抄 RTL 位操作；经 tb_pkg include（.f 不单列）。

## 3. 握手/事件模型与逐拍时序（模型依据，检查要点）

- 一拍 = 一次握手窗口（negedge 驱动 → DUT 下一 posedge 采样/提交 → 采样拍 S=posedge+mon_skew 取值）。
- **写路径**：wr 握手 = i_wr_vld && 有空闲（first-fit 最低空闲地址）；posedge 提交入链（bitmap/link/tail/head，
  链尾指向新节点）；o_wr_ready 与 o_free_cnt 采样值为**提交后**状态（o_wr_ready = 提交后空闲>0）。
- **读路径（T0→T1 流水）**：T0 拍按有效调度 ID（i_rd_id_vld?i_rd_id:开关预留 reg_schd_id 回退）匹配链头 →
  T1 拍展示 o_rd_ready/o_rd_data/o_rd_last/o_schd_id；展示拍末 posedge 由 i_rd_vld 消费（弹头，后继提升为头）。
  **展示的是旧头数据；同拍写扩展单节点链（冲突覆盖）→ 新节点成为新头，新数据隔一拍随后续调度展示**。
  - 因此每拍的期望 =「匹配结果（展示）+ 提交后状态（free_cnt/wr_ready/remain 含同拍同消）」，模型 step()
    按此顺序推进。
  - IO 对齐关键：S(k+1) 采样值对应第 k 拍激励（item k 的期望 = step(item k 激励) 的输出，1:1 配对）。
- **o_schd_id_remain** = 提交后 bitmap 中该 o_schd_id 条目数（popcount；同拍消费+同拍写同 ID 均计入）。
- **o_rd_data 仅在 o_rd_ready=1 拍比对**（ready=0 时 SDPRAM 保持/任意值，跳过；ready=1 时另查 X 态）。
- **满深度验收点（P0-7）**：64 笔写满（地址 0..63 均被 first-fit 覆盖）后：
  ① o_free_cnt=0 且 o_wr_ready=0（65 拍写请求被拒）；② 第 64 笔数据（地址 63）完整入链并可在链尾读出
  （last=1，数据 = 0xB070_0000+63；链寄存器组少一格时地址 63 的 link_id 丢失 → 链尾不可达/顺序断裂 → 必 fail）。

## 4. 偏离说明（相对 rules/tb.md 9.3 节）

- **期望生成在用例侧（逐拍行为模型），refm 透传**：本模块为带状态链表 + T0-T1 展示流水线的握手模块，
  期望值依赖全部历史（数据序列与状态），无法用无状态纯函数表达。故 refm 的 model()/compute() 保持
  框架契约（model() 覆写并调用纯函数 compute() 透传），核心计算移入用例侧 `pubip_dynamic_mem_model`
  （用例内状态允许；handoff 记录偏离）。子系统级如需复用：compute 仍为透传，期望计算逻辑独立于 refm。
- 其余框架约定全部遵守：无 clocking/program/rand/constraint（随机仅 $urandom_range/$urandom，播种 +SEED=）、
  时钟/复位/超时/波形/结果汇总均由框架与 sim_top 承担，i_ 信号均赋初值，driver 先广播后驱动。

## 5. 仿真验证重点 / 易错点

- 模型与 DUT 依据同一套逐拍语义推进——任何链路指针、head/tail 标志、冲突覆盖、free/remain 计数偏差
  都会**逐拍全信号**暴露（控制信号全拍比对 + 数据 ready 拍比对）。
- 易错边界：① 同拍读写同 ID 单节点链（冲突覆盖时序、隔拍展示新数据）；② 单节点链展示保持（rd_vld=0 重复展示）；
  ③ 满 64 笔后写拒绝；④ 链空后 o_schd_id/remain 行为（reg_schd_id 回退语义）；⑤ 最终 drain 尾拍。
- tc_all 串联前提：各前置用例结束时链均已清空、显式调度回 ID0（reg_schd=0），与下一用例模型复位态一致
  （每用例 body 尾部 push_tail(seq,3) + 头拍可无调度）；tc_random 尾链存留不影响（其为末位用例）。
- 未初始化 X 态：接口输入均已赋初值；DUT 无复位链区（link_id/link_addr/SDPRAM）仅在 bitmap/head/tail 保护下
  使用，逐拍比对已核对。

## 6. 编译运行（场景 C：公共 IP 模块级）

```bash
# 服务器（ubuntu）镜像下
cd <MIRROR>/pub_code/work/pubip_dynamic_mem/        # 先 mkdir -p
vcs -sverilog -full64 -j 4 -f ../../testbench/pubip_dynamic_mem/pubip_dynamic_mem_tb.f \
    -y ../.. +libext+.v+.sv -l compile.log
./simv +TC=tc_all +SEED=1 2>&1 | tee sim.log
# 单用例：+TC=tc_full_depth（P0-7 验收主用例）；小深度边界扫描：编译加 +define+PUBIP_DMEM_SMALL（DUT 16 深，模型经 mem_depth() 同步）
# 波形：编译加 +define+DEBUG_CODE_EN（每用例独立 wave_caseN.vcd）
# 结果判定：以 log 汇总行 grep "RESULT.*PASS" 为准（VCS 2017.03 无 -exitstatus，$finish(n) 不映射退出码，见 rules/sim.md 退出码说明）；等待时间 = TB 超时 2 倍（默认 1s）
```
