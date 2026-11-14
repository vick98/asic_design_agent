# pubip_mseq_cal_spec

此文件描述了pubip_mseq_cal模块的基本功能，接口、模块处理流程、实现结构、逻辑实现等。

## 模块功能

pubip_mseq_cal 模块用于在有限拍数内完成任意转移次数的 M 序列计算。模块通过例化 15 个不同 TRANS_NUM 参数（2^0 ~ 2^14）的 pubip_mseq_gen 子模块构成"二进制转移链"，将输入的 15 bit 转移次数按二进制展开分别控制各级 mseq_gen 的 `i_cal_en` 端口，即可在若干拍内计算得到初始 M 序列经过任意 0 ~ 32767 次转移后的结果。

主要应用场景：
- 长距离/长周期 PN 序列或扰码序列的快速跳变生成
- 需要在少量时钟周期内跨越任意 LFSR 迭代次数的场景，例如帧头对齐、随机数生成器状态同步等

## 模块接口

### 参数表

| 参数名 | 缺省值 | 说明 |
|--------|--------|------|
| CAL_RULE | 31'h9 | LFSR 反馈多项式（本原多项式），透传给内部所有 mseq_gen 子模块 |
| SEQ_WIDTH | 31 | M 序列位宽（LFSR 级数），透传给内部所有 mseq_gen 子模块 |

模块内部固定结构（非参数化）：
- 二进制转移链共 15 级，各级 TRANS_NUM 依次为 2^14、2^13、...、2^1、2^0，最大支持转移次数 = 2^15 - 1 = 32767
- 转移次数控制信号位宽固定为 15 bit
- 流水打拍位置固定为 4 处（见后续章节），模块整体输入到输出延迟固定为 5 拍（输入锁存 1 拍 + 4 段流水）

### 端口表

| 端口名 | 方向 | 位宽 | 说明 |
|--------|------|------|------|
| clk_in | input | 1 | 时钟输入 |
| rst_n | input | 1 | 异步复位，低电平有效 |
| i_init_seq | input | SEQ_WIDTH | 初始 M 序列输入 |
| i_cal_vld | input | 1 | 计算有效指示，高电平时锁存当前 i_init_seq 与 i_trans_num 启动一次转移计算 |
| i_trans_num | input | 15 | 转移次数控制值，二进制无符号数，bit[14] ~ bit[0] 分别对应 2^14 ~ 2^0 级 mseq_gen 的 i_cal_en |
| o_seq_out | output | SEQ_WIDTH | 输出 M 序列（经 i_trans_num 次转移后的结果） |
| o_seq_vld | output | 1 | 输出 M 序列有效指示，相对 i_cal_vld 延迟 5 拍 |

## 模块处理流程

模块处理遵循以下处理流程：
  - 输入锁存
    - 当 i_cal_vld 为高时，锁存 i_init_seq 作为二进制转移链首级输入
    - 同时锁存 i_trans_num 作为链上各级 mseq_gen 的 i_cal_en 控制总线
    - reg_cal_vld 无条件打拍跟踪 i_cal_vld（不依赖 i_cal_vld 作为使能），作为流水线各段 en 门控源及有效信号打拍链的起点
  - 二进制转移链计算（从高位到低位依次串接）
    - 第 k 级子模块（k = 14 → 0）例化 pubip_mseq_gen，TRANS_NUM = 2^k
    - 第 k 级 i_cal_en 直接连接（打拍对齐后的）trans_num[k]
    - 第 k 级 o_seq_out 作为第 k-1 级的 i_init_seq 输入
    - trans_num[k]=1 时该级完成 2^k 步转移，否则旁路 i_init_seq
    - 全部 15 级串接后即完成 `sum(trans_num[k] * 2^k) = i_trans_num` 次转移
  - 分段流水打拍（4 段，总延迟 5 拍 = 输入锁存 1 拍 + 4 段流水）
    - 第 1 段：TRANS_NUM = 2^14、2^13 两级 mseq_gen 串接后打一拍，en 门控 = reg_cal_vld
    - 第 2 段：TRANS_NUM = 2^12、2^11、2^10、2^9 四级 mseq_gen 串接后打一拍，en 门控 = reg_cal_vld_dly1
    - 第 3 段：TRANS_NUM = 2^8、2^7 两级 mseq_gen 串接后打一拍，en 门控 = reg_cal_vld_dly2
    - 第 4 段：TRANS_NUM = 2^6、2^5、2^4、2^3、2^2、2^1、2^0 七级 mseq_gen 串接后打一拍，en 门控 = reg_cal_vld_dly3，作为最终输出
    - 每段数据与 trans_num 低位打拍均由对应拍的 cal_vld 延迟信号门控（en=0 时寄存器保持原值，避免无效数据污染流水线），同时保证到达每一级子模块的 i_cal_en 与其 i_init_seq 处于同一拍
  - 输出
    - 第 4 段末级寄存器直接作为 o_seq_out
    - reg_cal_vld 经 4 级打拍（reg_cal_vld_dly1~dly4）后作为 o_seq_vld，相对 i_cal_vld 延迟 5 拍
  - 边界条件
    - i_trans_num = 0：全部 i_cal_en=0，o_seq_out 等于延迟 5 拍后的 i_init_seq
    - i_cal_vld 未拉高时 reg_cal_vld 及各级 dly 保持 0，o_seq_vld 保持 0，各段数据寄存器因 en=0 保持原值不翻转
    - 支持连续多拍 i_cal_vld=1，多任务流水计算，每个输入 5 拍后从对应位置输出 o_seq_vld

## 模块实现结构

硬件实现使用以下结构或优化方法：
  - 二进制加权转移链结构：将任意转移次数 N 分解为二进制 N = Σ bit_k · 2^k（k=0..14），用 15 级 mseq_gen 分别完成 2^k 步固定跳变，通过 i_cal_en 选择是否启用该级
    - 每级 mseq_gen 内部为综合期折叠的 A^(2^k) 常量转移矩阵，纯组合逻辑
    - 从高位到低位串接：首级 TRANS_NUM = 2^14 = 16384，末级 TRANS_NUM = 2^0 = 1；串接顺序对最终数值结果无影响，从高到低串接便于阅读理解
  - 分段流水打拍策略：基于各级 mseq_gen 组合逻辑深度差异（大 TRANS_NUM 的转移矩阵异或宽度大、延迟大），采用非均匀分段打拍，共分 4 段
    - 段 1（2 级重逻辑）：2^14、2^13 → 打拍
    - 段 2（4 级中逻辑）：2^12、2^11、2^10、2^9 → 打拍
    - 段 3（2 级次中逻辑）：2^8、2^7 → 打拍
    - 段 4（7 级轻逻辑）：2^6 ~ 2^0 → 打拍并输出
    - 段划分依据：每段内部各级 mseq_gen 组合逻辑深度之和保持相近，均衡时序，避免任一段成为关键路径
  - 控制通路与数据通路严格同步：每段数据打拍的同时，将该段之后仍需使用的 trans_num 低位 bit 同步打拍寄存，保证每级 mseq_gen 的 i_cal_en 与其输入 i_init_seq 处于同一拍数据
  - en 门控策略：reg_cal_vld 无条件打拍跟踪 i_cal_vld，作段 1 数据与 trans_num 打拍的 en 门控；再经 3 级打拍生成 reg_cal_vld_dly1~dly3，分别作为段 2~段 4数据与 trans_num 打拍的 en 门控，第 4 级打拍输出 reg_cal_vld_dly4 驱动 o_seq_vld；en=0 时各段寄存器保持原值，避免无有效输入时流水线寄存器翻转产生无效中间结果
  - 基于上述结构，整个模块分为三层结构
    - 第一层（输入锁存层）：i_cal_vld 有效时锁存 i_init_seq、i_trans_num；reg_cal_vld 无条件打拍跟踪 i_cal_vld
    - 第二层（二进制转移链 + 4 段流水层）：15 级 pubip_mseq_gen 与 4 段流水寄存器组交替连接，完成任意次转移计算，同时同步传递 trans_num 低位，并由对应 cal_vld 延迟信号门控各段打拍
    - 第三层（输出层）：第 4 段末级寄存器直接输出为 o_seq_out、o_seq_vld
  - 结构设计带来的限制说明
    - 最大转移次数上限固定为 2^15 - 1 = 32767，超出范围的转移需求需外部截断或分多次调用
    - 模块整体拍数延迟固定为 5 拍（输入锁存 1 拍 + 4 段流水），与 i_trans_num 具体取值无关

## 模块逻辑块描述

模块整体分为 6 个逻辑块：输入锁存逻辑、段 1 转移链与打拍逻辑、段 2 转移链与打拍逻辑、段 3 转移链与打拍逻辑、段 4 转移链与打拍逻辑与输出、cal_vld/seq_vld 打拍链。各逻辑块之间通过命名的寄存器信号连接，形成 4 级流水线。

### 逻辑块 1：输入锁存逻辑

- **功能要点**
  - 当 `i_cal_vld` 为高时，锁存 `i_init_seq` 作为二进制转移链首级的初始序列输入。
  - 当 `i_cal_vld` 为高时，锁存 `i_trans_num[14:0]` 作为各级 mseq_gen 的 `i_cal_en` 控制源。
  - `reg_cal_vld` 无条件打拍跟踪 `i_cal_vld`（独立于数据锁存使能），作为流水线各段 en 门控源及有效信号打拍链的起点。
  - 当 `i_cal_vld` 为低时，`reg_init_seq_d0`/`reg_trans_num_d0` 保持原值不变；`reg_cal_vld` 跟随 `i_cal_vld` 拉低，使下游各段 en=0 而保持原值，避免无效数据翻转。
- **关键信号**
  - `reg_init_seq_d0[SEQ_WIDTH-1:0]`：锁存的初始 M 序列，位宽 = `SEQ_WIDTH`（默认 31）。
  - `reg_trans_num_d0[14:0]`：锁存的转移次数控制字，位宽 = 15。
  - `reg_cal_vld`：`i_cal_vld` 的无条件打拍（拍1），作为段 1 en 门控源及打拍链起点，位宽 = 1。
- **复位/初始化行为**
  - 异步复位 `rst_n = 0` 时，`reg_init_seq_d0` 清零为全 0，`reg_trans_num_d0` 清零为全 0，`reg_cal_vld` 清零为 0。
- **实现说明**
  - 数据锁存使用 `always_ff @(posedge clk_in or negedge rst_n)` 描述，使能条件为 `i_cal_vld`，复位优先级高于使能。
  - `reg_cal_vld` 单独使用一个 `always_ff` 无条件打拍 `i_cal_vld`（不可与数据锁存共用 `else if (i_cal_vld)` 分支，否则 `i_cal_vld=0` 时进入隐式保持会导致 `reg_cal_vld` 置 1 后永不回 0）。
  - `reg_cal_vld` 一拍后送入 cal_vld 打拍链（逻辑块 6）。

### 逻辑块 2：段 1 转移链与打拍逻辑（TRANS_NUM = 16384、8192）

- **功能要点**
  - 例化 2 个 pubip_mseq_gen 子模块，TRANS_NUM 分别为 16384（2^14）和 8192（2^13）。
  - 第 1 级（16384）接收 `reg_init_seq_d0` 作为 `i_init_seq`，`reg_trans_num_d0[14]` 作为 `i_cal_en`。
  - 第 2 级（8192）接收第 1 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d0[13]` 作为 `i_cal_en`。
  - 第 2 级的 `o_seq_out`（组合逻辑输出）作为本段数据打拍的输入。
  - 本段数据打拍后输出 `reg_seq_stage1[SEQ_WIDTH-1:0]`，送入段 2 首级。
- **关键信号**
  - `wir_seq_s1_m14[SEQ_WIDTH-1:0]`：第 1 级（TRANS_NUM=16384）的组合逻辑输出，位宽 = `SEQ_WIDTH`。
  - `wir_seq_s1_m13[SEQ_WIDTH-1:0]`：第 2 级（TRANS_NUM=8192）的组合逻辑输出，位宽 = `SEQ_WIDTH`。
  - `reg_seq_stage1[SEQ_WIDTH-1:0]`：段 1 打拍后的序列数据寄存器，位宽 = `SEQ_WIDTH`。
  - `reg_trans_num_d1[12:0]`：段 1 打拍后传递的 trans_num 低位 bit[12:0]，位宽 = 13。
    - bit[12:0] 对应后续段仍需使用的 TRANS_NUM = 4096、2048、1024、512、256、128、64、32、16、8、4、2、1。
    - bit[14:13] 已在段 1 消耗，不再传递。
- **复位/初始化行为**
  - 异步复位时，`reg_seq_stage1` 清零为全 0，`reg_trans_num_d1` 清零为全 0。
- **实现说明**
  - 两个 pubip_mseq_gen 实例直连，无中间寄存器，纯组合逻辑链。
  - 数据打拍寄存器与 trans_num 低位打拍寄存器位于同一个 `always_ff` 块中，由 `reg_cal_vld` 门控（en=1 时更新，en=0 时保持原值），保证时序对齐且无有效输入时不翻转。
  - pubip_mseq_gen 例化参数：`CAL_RULE` 透传顶层参数，`SEQ_WIDTH` 透传顶层参数，`TRANS_NUM` 分别设置为 16384 和 8192。

### 逻辑块 3：段 2 转移链与打拍逻辑（TRANS_NUM = 4096、2048、1024、512）

- **功能要点**
  - 例化 4 个 pubip_mseq_gen 子模块，TRANS_NUM 分别为 4096（2^12）、2048（2^11）、1024（2^10）、512（2^9）。
  - 第 1 级（4096）接收 `reg_seq_stage1` 作为 `i_init_seq`，`reg_trans_num_d1[12]` 作为 `i_cal_en`。
  - 第 2 级（2048）接收第 1 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d1[11]` 作为 `i_cal_en`。
  - 第 3 级（1024）接收第 2 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d1[10]` 作为 `i_cal_en`。
  - 第 4 级（512）接收第 3 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d1[9]` 作为 `i_cal_en`。
  - 第 4 级的 `o_seq_out` 作为本段数据打拍的输入。
  - 本段数据打拍后输出 `reg_seq_stage2[SEQ_WIDTH-1:0]`，送入段 3 首级。
- **关键信号**
  - `wir_seq_s2_m12[SEQ_WIDTH-1:0]`：第 1 级（TRANS_NUM=4096）的组合逻辑输出。
  - `wir_seq_s2_m11[SEQ_WIDTH-1:0]`：第 2 级（TRANS_NUM=2048）的组合逻辑输出。
  - `wir_seq_s2_m10[SEQ_WIDTH-1:0]`：第 3 级（TRANS_NUM=1024）的组合逻辑输出。
  - `wir_seq_s2_m9[SEQ_WIDTH-1:0]`：第 4 级（TRANS_NUM=512）的组合逻辑输出。
  - `reg_seq_stage2[SEQ_WIDTH-1:0]`：段 2 打拍后的序列数据寄存器。
  - `reg_trans_num_d2[8:0]`：段 2 打拍后传递的 trans_num 低位 bit[8:0]，位宽 = 9。
    - bit[8:0] 对应后续段仍需使用的 TRANS_NUM = 256、128、64、32、16、8、4、2、1。
    - bit[12:9] 已在段 2 消耗，不再传递。
- **复位/初始化行为**
  - 异步复位时，`reg_seq_stage2` 清零为全 0，`reg_trans_num_d2` 清零为全 0。
- **实现说明**
  - 4 个 pubip_mseq_gen 实例直连，无中间寄存器，纯组合逻辑链。
  - 数据打拍寄存器与 trans_num 低位打拍寄存器位于同一个 `always_ff` 块中，由 `reg_cal_vld_dly1` 门控。
  - pubip_mseq_gen 例化参数：`CAL_RULE`、`SEQ_WIDTH` 透传顶层参数，`TRANS_NUM` 分别设置为 4096、2048、1024、512。

### 逻辑块 4：段 3 转移链与打拍逻辑（TRANS_NUM = 256、128）

- **功能要点**
  - 例化 2 个 pubip_mseq_gen 子模块，TRANS_NUM 分别为 256（2^8）和 128（2^7）。
  - 第 1 级（256）接收 `reg_seq_stage2` 作为 `i_init_seq`，`reg_trans_num_d2[8]` 作为 `i_cal_en`。
  - 第 2 级（128）接收第 1 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d2[7]` 作为 `i_cal_en`。
  - 第 2 级的 `o_seq_out` 作为本段数据打拍的输入。
  - 本段数据打拍后输出 `reg_seq_stage3[SEQ_WIDTH-1:0]`，送入段 4 首级。
- **关键信号**
  - `wir_seq_s3_m8[SEQ_WIDTH-1:0]`：第 1 级（TRANS_NUM=256）的组合逻辑输出。
  - `wir_seq_s3_m7[SEQ_WIDTH-1:0]`：第 2 级（TRANS_NUM=128）的组合逻辑输出。
  - `reg_seq_stage3[SEQ_WIDTH-1:0]`：段 3 打拍后的序列数据寄存器。
  - `reg_trans_num_d3[6:0]`：段 3 打拍后传递的 trans_num 低位 bit[6:0]，位宽 = 7。
    - bit[6:0] 对应后续段仍需使用的 TRANS_NUM = 64、32、16、8、4、2、1。
    - bit[8:7] 已在段 3 消耗，不再传递。
- **复位/初始化行为**
  - 异步复位时，`reg_seq_stage3` 清零为全 0，`reg_trans_num_d3` 清零为全 0。
- **实现说明**
  - 2 个 pubip_mseq_gen 实例直连，无中间寄存器，纯组合逻辑链。
  - 数据打拍寄存器与 trans_num 低位打拍寄存器位于同一个 `always_ff` 块中，由 `reg_cal_vld_dly2` 门控。
  - pubip_mseq_gen 例化参数：`CAL_RULE`、`SEQ_WIDTH` 透传顶层参数，`TRANS_NUM` 分别设置为 256、128。

### 逻辑块 5：段 4 转移链与打拍逻辑（TRANS_NUM = 64、32、16、8、4、2、1）与输出

- **功能要点**
  - 例化 7 个 pubip_mseq_gen 子模块，TRANS_NUM 分别为 64（2^6）、32（2^5）、16（2^4）、8（2^3）、4（2^2）、2（2^1）、1（2^0）。
  - 第 1 级（64）接收 `reg_seq_stage3` 作为 `i_init_seq`，`reg_trans_num_d3[6]` 作为 `i_cal_en`。
  - 第 2 级（32）接收第 1 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[5]` 作为 `i_cal_en`。
  - 第 3 级（16）接收第 2 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[4]` 作为 `i_cal_en`。
  - 第 4 级（8）接收第 3 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[3]` 作为 `i_cal_en`。
  - 第 5 级（4）接收第 4 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[2]` 作为 `i_cal_en`。
  - 第 6 级（2）接收第 5 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[1]` 作为 `i_cal_en`。
  - 第 7 级（1）接收第 6 级的 `o_seq_out` 作为 `i_init_seq`，`reg_trans_num_d3[0]` 作为 `i_cal_en`。
  - 第 7 级的 `o_seq_out` 作为本段数据打拍的输入。
  - 本段打拍后输出 `reg_seq_stage4[SEQ_WIDTH-1:0]`，直接驱动 `o_seq_out`。
- **关键信号**
  - `wir_seq_s4_m6[SEQ_WIDTH-1:0]`：第 1 级（TRANS_NUM=64）的组合逻辑输出。
  - `wir_seq_s4_m5[SEQ_WIDTH-1:0]`：第 2 级（TRANS_NUM=32）的组合逻辑输出。
  - `wir_seq_s4_m4[SEQ_WIDTH-1:0]`：第 3 级（TRANS_NUM=16）的组合逻辑输出。
  - `wir_seq_s4_m3[SEQ_WIDTH-1:0]`：第 4 级（TRANS_NUM=8）的组合逻辑输出。
  - `wir_seq_s4_m2[SEQ_WIDTH-1:0]`：第 5 级（TRANS_NUM=4）的组合逻辑输出。
  - `wir_seq_s4_m1[SEQ_WIDTH-1:0]`：第 6 级（TRANS_NUM=2）的组合逻辑输出。
  - `wir_seq_s4_m0[SEQ_WIDTH-1:0]`：第 7 级（TRANS_NUM=1）的组合逻辑输出。
  - `reg_seq_stage4[SEQ_WIDTH-1:0]`：段 4 打拍后的序列数据寄存器，直接连接至 `o_seq_out`。
- **复位/初始化行为**
  - 异步复位时，`reg_seq_stage4` 清零为全 0。
- **实现说明**
  - 7 个 pubip_mseq_gen 实例直连，无中间寄存器，纯组合逻辑链。
  - 段 4 不再需要传递 trans_num 低位（所有 15 bit 均已在本段消耗完毕）。
  - `reg_seq_stage4` 由 `reg_cal_vld_dly3` 门控打拍，使用 `assign` 直接连接到 `o_seq_out`。
  - pubip_mseq_gen 例化参数：`CAL_RULE`、`SEQ_WIDTH` 透传顶层参数，`TRANS_NUM` 分别设置为 64、32、16、8、4、2、1。
- **i_cal_en 分配校验**
  - trans_num bit 与各级 TRANS_NUM 的对应关系为：
    - bit[14] → TRANS_NUM=16384，bit[13] → 8192，bit[12] → 4096，bit[11] → 2048
    - bit[10] → 1024，bit[9] → 512，bit[8] → 256，bit[7] → 128
    - bit[6] → 64，bit[5] → 32，bit[4] → 16，bit[3] → 8
    - bit[2] → 4，bit[1] → 2，bit[0] → 1
  - 各级 i_cal_en 来源随流水级逐段传递：段 1 使用 `reg_trans_num_d0[14:13]`，段 2 使用 `reg_trans_num_d1[12:9]`，段 3 使用 `reg_trans_num_d2[8:7]`，段 4 使用 `reg_trans_num_d3[6:0]`。

### 逻辑块 6：cal_vld/seq_vld 打拍链

- **功能要点**
  - 将逻辑块 1 产生的 `reg_cal_vld` 经过 4 级流水打拍，与数据通路的 4 段延迟严格对齐。
  - `reg_cal_vld_dly1`/`dly2`/`dly3` 分别作为段 2/段 3/段 4 数据与 trans_num 打拍的 en 门控信号。
  - 第 4 级打拍输出 `reg_cal_vld_dly4` 直接驱动 `o_seq_vld`。
  - 该打拍链与各段数据打拍位于同一时钟域、同一拍数，保证 `o_seq_vld` 与 `o_seq_out` 时序对齐。
- **关键信号**
  - `reg_cal_vld`：来自逻辑块 1 的输入（拍1，对应 `reg_init_seq_d0`），位宽 = 1。
  - `reg_cal_vld_dly1`：拍2 延迟，段 2 en 门控，位宽 = 1。
  - `reg_cal_vld_dly2`：拍3 延迟，段 3 en 门控，位宽 = 1。
  - `reg_cal_vld_dly3`：拍4 延迟，段 4 en 门控，位宽 = 1。
  - `reg_cal_vld_dly4`：拍5 延迟，直接连接至 `o_seq_vld`，位宽 = 1。
- **复位/初始化行为**
  - 异步复位时，4 级打拍寄存器全部清零为 0。
- **实现说明**
  - 4 级打拍寄存器串接：`reg_cal_vld` → `reg_cal_vld_dly1` → `reg_cal_vld_dly2` → `reg_cal_vld_dly3` → `reg_cal_vld_dly4`。
  - 所有 4 级打拍合并到同一个 `always_ff` 块中，每拍无条件传递上一级的值（无需使能控制，因为源 `reg_cal_vld` 已是无条件跟踪 `i_cal_vld` 的脉冲）。
  - `reg_cal_vld_dly1`/`dly2`/`dly3` 在对应拍与段 2/3/4 数据寄存器同拍更新，作为其 en 门控。
  - `reg_cal_vld_dly4` 使用 `assign` 直接连接到 `o_seq_vld`。
  - 该打拍链相对 `i_cal_vld` 延迟 5 拍（`reg_cal_vld` 拍1 + 4 级 dly），与数据通路拍数严格一致，由同一时钟驱动。

### 逻辑块间连接关系总结

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                    cal_vld 打拍链（逻辑块 6）                    │
                    │  reg_cal_vld → dly1 → dly2 → dly3 → dly4 → o_seq_vld        │
                    └──────────────────────────────────────────────────────────────┘

i_init_seq ─┬─→ [reg_init_seq_d0] ─────────────────────────────────────────────┐
i_trans_num ─┘   [reg_trans_num_d0]                                             │
                    │                                                            │
                    ▼                                                            │
    ┌───────────────────────────────────┐                                        │
    │  段1: mseq(16384) → mseq(8192)   │ i_cal_en[14:13] ← reg_trans_num_d0[14:13]
    │        ↓ 打拍                      │                                        │
    │  reg_seq_stage1                    │                                        │
    │  reg_trans_num_d1[12:0]           │                                        │
    └───────────────┬───────────────────┘                                        │
                    │                                                            │
                    ▼                                                            │
    ┌───────────────────────────────────────────────┐                            │
    │  段2: mseq(4096)→mseq(2048)→mseq(1024)→mseq(512)│ i_cal_en[12:9] ← d1[12:9] │
    │        ↓ 打拍                                    │                         │
    │  reg_seq_stage2                                  │                         │
    │  reg_trans_num_d2[8:0]                           │                         │
    └───────────────┬─────────────────────────────────┘                         │
                    │                                                            │
                    ▼                                                            │
    ┌───────────────────────────────┐                                            │
    │  段3: mseq(256) → mseq(128)  │ i_cal_en[8:7] ← d2[8:7]                      │
    │        ↓ 打拍                  │                                           │
    │  reg_seq_stage3                │                                           │
    │  reg_trans_num_d3[6:0]         │                                           │
    └───────────────┬───────────────┘                                            │
                    │                                                            │
                    ▼                                                            │
    ┌───────────────────────────────────────────────────────────────┐           │
    │  段4: mseq(64)→mseq(32)→mseq(16)→mseq(8)→mseq(4)→mseq(2)→mseq(1)│        │
    │        ↓ 打拍                    i_cal_en[6:0] ← d3[6:0]        │           │
    │  reg_seq_stage4 → o_seq_out                                    │           │
    └───────────────────────────────────────────────────────────────┘           │
```

## 测试要点

> 注：公共 IP 无独立 TB 目录，本节测试要点供模块级 TB 参考；用例按"一测试点一用例文件"组织，文件命名 `tc/pubip_mseq_cal_tc_<名>.sv`。

此处描述模块测试/验证关注的测试点，这些测试点或许容易存在bug

### 基础功能测试
- i_trans_num = 0：全部 i_cal_en=0，o_seq_out 应等于 i_init_seq 延迟 5 拍
- i_trans_num = 1、2、4、8、16、32、64、128、256、512、1024、2048、4096、8192、16384 单 bit 场景：逐一验证每级 mseq_gen 独立正确
- i_trans_num = 32767（全 15 bit 置 1）：验证全链路使能场景，所有 15 级 mseq_gen 的 i_cal_en 同时为 1

### 段边界与打拍对齐测试
- **段 1 边界**：i_trans_num = 0x6000（bit[14:13]=1，其余 0），仅使能段 1 两级，验证 reg_trans_num_d1[12:0] 正确传递
- **段 2 边界**：i_trans_num = 0x1E00（bit[12:9]=1，其余 0），仅使能段 2 四级，验证 reg_trans_num_d2[8:0] 正确传递
- **段 3 边界**：i_trans_num = 0x0180（bit[8:7]=1，其余 0），仅使能段 3 两级，验证 reg_trans_num_d3[6:0] 正确传递
- **段 4 边界**：i_trans_num = 0x007F（bit[6:0]=1，其余 0），仅使能段 4 七级
- **跨段组合**：i_trans_num = 0x5555（交替使能），验证跨段时 i_cal_en 与对应级 i_init_seq 处于同一拍
- **段边界单 bit 翻转**：i_trans_num 仅 bit[13] 与 bit[12] 交替（段 1→段 2 边界），验证 d0[13]（段 1 末级）与 d1[12]（段 2 首级）的跨拍对齐
- **段 2→段 3 边界**：i_trans_num 仅 bit[9] 与 bit[8] 交替，验证 d1[9] 与 d2[8] 的正确对齐
- **段 3→段 4 边界**：i_trans_num 仅 bit[7] 与 bit[6] 交替，验证 d2[7] 与 d3[6] 的正确对齐

### 流水线功能测试
- 连续多拍 i_cal_vld=1，每拍 i_trans_num 不同：验证流水乱序无干扰、每拍 o_seq_vld 与对应输入一一对应
- 连续多拍 i_cal_vld=1，i_trans_num 依次递增（0→1→2→...→32767）：验证长序列流水填充与排空无数据错位
- i_cal_vld 间隔拉高（如每 2 拍拉高一次）：验证流水气泡场景下 o_seq_vld 仍正确对应
- 单拍 i_cal_vld=1 后长时间不再拉高：验证流水排空后 o_seq_vld 正确回 0
- i_cal_vld 单拍脉冲后跟随多拍低电平：验证各段 en 门控生效，无有效输入时 reg_seq_stage* 与 reg_trans_num_d* 保持原值不翻转，o_seq_vld 仅在对应拍拉高一拍
- reg_cal_vld 跟踪 i_cal_vld 验证：i_cal_vld 拉低后下一拍 reg_cal_vld 必须为 0（不复位为 1 后永久保持）

### 复位与初始化测试
- 复位后立即拉高 i_cal_vld：确认无 X 态传播，所有 pipeline 寄存器正确复位为 0
- 运行中复位（流水线内有数据时拉低 rst_n）：复位后重新启动计算，确认前一拍残留数据不污染新计算
- 复位释放后首个时钟沿同时 i_cal_vld=1：验证复位释放与有效指示的竞争处理

### 与参考模型对比测试
- 与软件参考模型（逐拍迭代 LFSR N 次）对比典型随机 i_trans_num 结果
- 覆盖 i_trans_num 从 0 到 32767 均匀随机采样 1000 个点，与软件模型逐点对比

### 边界与极端场景测试
- i_trans_num = 32767 连续多拍：最大转移次数全流水场景，验证时序不违例
- i_cal_vld 常高、i_trans_num 每拍随机翻转：验证最恶劣翻转场景下 i_cal_en 打拍对齐无错拍
- SEQ_WIDTH 非默认值场景（参数化验证）：SEQ_WIDTH 配置为较小值（如 8）或较大值（如 64）时功能正确
