<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 公共模块

> **生成物，请勿手改**：本文的 `### 参数` 与 `### 端口` 两张表在标记区（`<!-- PUBIP_PARAMS -->` / `<!-- PUBIP_PORTS -->`）内由 `python3 script/framework.py hosts` 按 `pub_code/` 的 RTL 生成；正文、清单与例化示例手写。改表要改 RTL 后重跑该命令，直接改标记区会被下一次渲染覆盖。生成区与 RTL 的逐字节一致性由 `framework/tests/test_pubip_doc.py` 核对。

这些模块已经在仓库的公共代码里（`pub_code/`）。方案阶段优先复用：划分前先查本文件的清单，功能重合的按外部模块选用并在方案里标注来源，不新写设计。

例化时参数和端口都写全，未用的输入接到常量并注明原因。位宽一律以本文件的端口表为准，不另算一套。端口表与参数表都由 `pub_code/` 的 RTL 经 `hosts` 生成（见上面标记），改了 RTL 就重跑 `python3 script/framework.py hosts`；逐端口核对见 `framework/tests/test_pubip_doc.py`。

## 清单

| 模块 | 用途 | 时序 | 内部例化 |
|------|------|------|----------|
| `pubip_counter` | 计数器 | 时钟、复位 | 无 |
| `pubip_sat` | 定点饱和截位 | 纯组合 | 无 |
| `pubip_round` | 定点收尾舍入（half-up 右移 + 对称饱和） | 纯组合 | 无 |
| `pubip_mseq_gen` | M 序列单步产生 | 纯组合 | 无 |
| `pubip_mseq_cal` | M 序列任意步计算 | 时钟、复位 | `pubip_mseq_gen` ×15 |
| `pubip_dynamic_mem` | 按 ID 的动态存储调度 | 时钟、复位 | `sdpram_wrapper` ×1 |
| `pubip_complex_mult` | 复数乘法 | 纯组合 | 无 |
| `sdpram_wrapper` | 简单双口 RAM 封装 | 时钟 | 无 |
| `pubip_cdc_sync` | 两级同步器（单比特控制信号跨域） | 双时钟、复位（各自域） | 无 |
| `pubip_async_fifo` | 异步 FIFO（跨域数据流搬运与背压） | 双时钟、复位（各自域） | `pubip_cdc_sync` |

嵌套关系：`pubip_mseq_cal` 内部例化 15 个 `pubip_mseq_gen`（`TRANS_NUM` 取 2^0 ~ 2^14）；`pubip_dynamic_mem` 内部例化 1 个 `sdpram_wrapper` 存数据，链表指针与 bitmap 留在寄存器里；`pubip_async_fifo` 把读写指针的格雷码按位经 `pubip_cdc_sync` 同步到对方时钟域。子系统只例化最外层那一个，内部模块不用再写进模块连接关系。

## 跨时钟域公共单元

以下单元已登记（`pub_code/` 里有对应 RTL），跨时钟域设计可直接选用：

| 类别 | 单元 | 文件 | 用途 |
|------|------|------|------|
| 两级同步器 | `pubip_cdc_sync` | `pub_code/pubip_cdc_sync.sv` | 单比特控制信号跨域同步 |
| 异步 FIFO | `pubip_async_fifo` | `pub_code/pubip_async_fifo.sv` | 跨域数据流搬运与背压 |

- 连接表里源端与目标端时钟域不同的连接：说明列要写出所用跨域单元名（如 `pubip_cdc_sync`），或引用一条有效裁决号〔D…〕；两者都没有时闸门按 `CD1` 阻断。
- 握手 / 保持寄存器与复位同步器还没有公共单元，需要时按 `rules/coding.md` §例化与公共模块 提报，不自行新写。
- 跨域信号在规格书说明列点明处理方式；RTL 里每级同步器单独成块，命名体现时钟域与级数。

## 复用预检（行 3 选定公共模块时必须逐条给出）

选一个公共模块前，先对着它的 `### 参数` / `### 端口` 两节核这两项，答案写进行 3 的复用依据；答不出就别选，或者把它列为待点选：

- **逐拍使能/门控语义**：有没有计数使能或暂停输入？没有的话，凡是要求"逐符号门控""背压期间冻结""半组暂停"的场合都用不了。（`pubip_counter` 就是这一类：`CYCLE_EN=1` 下 `i_cnt_end` 同时清零计数与使能，没有暂停口。）
- **`generate` 展开规模**：参数驱动的内部例化在最大参数下会展开多少次？nLint 对单个 `generate` 展开 >10000 次直接报 Error 15001（`pubip_counter` 按 `MAX_NUM+1` 展开，大位宽计数会踩到）。规模上界写进复用依据。

## pubip_counter

计数器：按给定位宽计数，可同步清零。`i_cnt_start_b1` 是启动脉冲（脉冲当拍清零并开始计数，脉冲本身不计数），`i_cnt_rst` 在单次计数时停计数、在循环计数时清零；循环长度的改变由外部逻辑实现——外部比较器在计数值达到目标长度时产生本信号提前清零，编译期上界仍是 MAX_NUM（对齐 RTL v1.4 实际行为），`i_cnt_end` 停计数。`o_cnt_shift` 是脉冲输出，bit j 对应计数值 j。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `MAX_NUM` | 7 | 最大计数值，计数值为 0 ~ `MAX_NUM` |
| `CYCLE_EN` | 0 | 循环计数使能，0 关闭，非 0 开启 |
| `CNT_WIDTH` | `$clog2(MAX_NUM + 1)` | 计数器位宽，可不配置，默认按 `MAX_NUM` 自动算最小位宽 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `clk_in` | input | 1 | 时钟输入 |
| `rst_n` | input | 1 | 复位输入，低有效 |
| `i_cnt_start_b1` | input | 1 | 计数启动脉冲，脉冲到来清零并开始计数，脉冲本身不计数 |
| `i_cnt_rst` | input | 1 | 计数复位，单次计数时停止计数，循环计数时清零（循环长度改变由外部比较器配合实现） |
| `i_cnt_end` | input | 1 | 计数停止 |
| `o_cnt_en` | output | 1 | 计数使能 |
| `o_counter` | output | `CNT_WIDTH` | 计数器数值输出 |
| `o_cnt_shift` | output | `[MAX_NUM:0]` | 计数器脉冲输出，bit j 对应计数值 j（bit0 在计数使能时有效）；位宽随 MAX_NUM 变化（RTL v1.4 起） |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_counter #(
    .MAX_NUM                ( 7         ),//设置最大计数值，7 时计数值 0~7
    .CYCLE_EN               ( 0         ),//循环计数使能，0 关闭
    .CNT_WIDTH              ( 3         ) //计数器位宽，可不配置（默认 $clog2(MAX_NUM+1)）
) u_counter (
    .clk_in                 ( clk_in        ),
    .rst_n                  ( rst_n         ),
    .i_cnt_start_b1         ( cnt_start     ),
    .i_cnt_rst              ( cnt_rst       ),
    .i_cnt_end              ( cnt_end       ),
    .o_cnt_en               ( cnt_en        ),
    .o_counter              ( cnt_value     ),
    .o_cnt_shift            ( cnt_pulse     )
);
```

## pubip_sat

定点饱和截位：把更宽的整数收到目标位宽，正负两侧都饱和，不做舍入。纯组合，没有时钟复位。`PROTECT_EN=1` 且结果为零时输出最小正值。参数标的是输入输出各自的总位宽与整数位宽，`IS_SIGNED` 决定按有符号还是无符号判饱和界。

`IN_INT_WIDTH` / `OUT_INT_WIDTH` 标的是**不含符号位**的整数位宽：有符号时小数位 = `TOTAL − INT − 1`，无符号时 = `TOTAL − INT`（与 RTL 参考模型 `pub_code/testbench/pubip_sat/pubip_sat_tb_refm.svh:25-26` 一致，也与子系统定点三元组口径一致，见 `rules/dsp.md`）。子系统规格书实例化本模块时，`IN_INT_WIDTH` 直接填定点格式的 `I`，不要再加符号位。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `IN_TOTAL_WIDTH` | 16 | 输入数据总位宽 |
| `IN_INT_WIDTH` | 8 | 输入数据整数位宽 |
| `OUT_TOTAL_WIDTH` | 8 | 输出数据总位宽 |
| `OUT_INT_WIDTH` | 4 | 输出数据整数位宽 |
| `IS_SIGNED` | 1 | 1 有符号、0 无符号 |
| `PROTECT_EN` | 0 | 零值保护使能，1 开启（结果为 0 时输出最小正值） |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `i_data` | input | `IN_TOTAL_WIDTH` | 输入数据 |
| `o_data` | output | `OUT_TOTAL_WIDTH` | 输出数据，经过饱和截位后 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_sat #(
    .IN_TOTAL_WIDTH           ( 16          ),//输入数据总位宽
    .IN_INT_WIDTH             ( 8           ),//输入数据整数位宽
    .OUT_TOTAL_WIDTH          ( 8           ),//输出数据总位宽
    .OUT_INT_WIDTH            ( 4           ),//输出数据整数位宽
    .IS_SIGNED                ( 1           ),//1 有符号、0 无符号
    .PROTECT_EN               ( 0           ) //1 开启零保护
) u_sat (
    .i_data                   ( sat_in      ),
    .o_data                   ( sat_out     )
);
```

## pubip_round

定点收尾舍入：把更宽的有符号定点数算术右移 N 位（round-half-up）后收进更窄的目标容器，两侧**对称**饱和，不做除法、不引入乘法，纯组合、没有时钟复位。对应 `rules/dsp.md` 的收尾（finish）一步：`finish <W_src,I_src,t> >> N half-up + sat -> <W_dst,I_dst,t>`，收尾移位量与出入容器由使用方按闭合式给定。要"先截位再饱和、不舍入"用 `pubip_sat`；要"截位后按半个 LSB 进位再饱和"用本模块。

舍入是 half-up：先加半个 LSB（`2^(N-1)`）再算术右移，0.5 LSB 边界向正方向取整（负数按"加半后向负无穷下取整"展开，-2.5 → -2）。`SHIFT_NUM = 0` 时退化为纯对称饱和收位。

饱和是对称饱和，输出界 `[1−2^(W_dst−1), 2^(W_dst−1)−1]`；并且**输出一律不出现补码的负最大值**（非对称最小 `−2^(W_dst−1)` 的位图）——右移结果数值恰为该值时钳到 `1−2^(W_dst−1)`。这条钳位判据与阈值饱和并列，不能只靠阈值比较（恰等于负满码的结果在阈值比较下算"界内"）。

`IN_INT_WIDTH` / `OUT_INT_WIDTH` 标的是**不含符号位**的整数位宽，与 `pubip_sat` 和定点三元组 `<W,I,t>` 同口径（`f = W − I − 1`）。闭合条件：`SHIFT_NUM = (W_src − I_src) − (W_dst − I_dst)`，即 `f_dst = f_src − N`；不闭合时 RTL 用 `$error` 报错，不静默。参数上限 `IN_TOTAL_WIDTH ≤ 63`（中间量 64 位）与 `OUT_TOTAL_WIDTH ≤ 63`（两侧饱和界在 64 位有符号容器里算）；越界按 `$error` 报错。

本模块的 TB 与验证证据：平台 `pub_code/testbench/pubip_round/`（8 个参数变体编译宏、一测试点一用例，含负满码钳位专项与 `W_dst > 32` 的宽输出变体 `PUBIP_ROUND_Z4`），移交说明 `pub_code/testbench/tb_handoff_round.md`（含逐变体回归命令）。使用方挂接点的容器与移位量按各自规格书用 `fx finish` 复算。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `IN_TOTAL_WIDTH` | 24 | 输入数据总位宽 `W_src` |
| `IN_INT_WIDTH` | 2 | 输入数据整数位宽 `I_src`，不含符号位 |
| `OUT_TOTAL_WIDTH` | 12 | 输出数据总位宽 `W_dst` |
| `OUT_INT_WIDTH` | 1 | 输出数据整数位宽 `I_dst`，不含符号位 |
| `SHIFT_NUM` | 12 | 右移位数 `N`（half-up 舍入的移位量） |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `i_data` | input | `IN_TOTAL_WIDTH` | 输入数据，补码 `<W_src,I_src,t>` |
| `o_data` | output | `OUT_TOTAL_WIDTH` | 输出数据，half-up 舍入 + 对称饱和后，补码 `<W_dst,I_dst,t>` |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
//发射成形收尾：finish <33,11,t> >> 11 half-up + sat -> <12,1,t>
pubip_round #(
    .IN_TOTAL_WIDTH           ( 33          ),//输入数据总位宽
    .IN_INT_WIDTH             ( 11          ),//输入数据整数位宽，不含符号位
    .OUT_TOTAL_WIDTH          ( 12          ),//输出数据总位宽
    .OUT_INT_WIDTH            ( 1           ),//输出数据整数位宽，不含符号位
    .SHIFT_NUM                ( 11          ) //右移位数 N
) u_round_tx (
    .i_data                   ( tx_fir_sum  ),//输入数据
    .o_data                   ( tx_finish   ) //输出数据
);
```

## pubip_mseq_gen

M 序列单步产生：按给定本原多项式把序列迭代 `TRANS_NUM` 次。`i_cal_en=1` 时输出迭代后的序列，`i_cal_en=0` 时直接旁路 `i_init_seq`。纯组合，没有时钟复位，是 `pubip_mseq_cal` 的积木。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `CAL_RULE` | `31'h9` | LFSR 反馈多项式（本原多项式） |
| `SEQ_WIDTH` | 31 | 序列位宽（LFSR 级数） |
| `TRANS_NUM` | 1 | 单次跨越的 LFSR 迭代次数 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `i_init_seq` | input | `SEQ_WIDTH` | 初始序列 |
| `i_cal_en` | input | 1 | 计算使能：1 输出跨越后的序列，0 旁路 `i_init_seq` |
| `o_seq_out` | output | `SEQ_WIDTH` | 输出序列 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_mseq_gen #(
    .CAL_RULE                 ( 31'h9       ),//LFSR 反馈多项式
    .SEQ_WIDTH                ( 31          ),//序列位宽
    .TRANS_NUM                ( 1           ) //单次跨越的 LFSR 迭代次数
) u_gen (
    .i_init_seq               ( seq_in      ),
    .i_cal_en                 ( gen_en      ),
    .o_seq_out                ( seq_out     )
);
```

## pubip_mseq_cal

M 序列计算：在固定 5 拍延迟内（输入锁存 1 拍 + 4 段流水）完成 0 ~ 32767 次转移的 M 序列计算，`o_seq_vld` 相对 `i_cal_vld` 延迟 5 拍。内部把 15 bit 转移次数按二进制展开，分别控制 15 个 `TRANS_NUM` 为 2^0 ~ 2^14 的 `pubip_mseq_gen`，构成二进制转移链。供长序列对齐检查用。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `CAL_RULE` | `31'h9` | LFSR 反馈多项式（本原多项式） |
| `SEQ_WIDTH` | 31 | M 序列位宽（LFSR 级数） |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `clk_in` | input | 1 | 时钟输入 |
| `rst_n` | input | 1 | 异步复位，低电平有效 |
| `i_init_seq` | input | `SEQ_WIDTH` | 初始 M 序列输入 |
| `i_cal_vld` | input | 1 | 计算有效指示，高电平锁存输入并启动计算 |
| `i_trans_num` | input | 15 | 转移次数控制值，二进制无符号数 |
| `o_seq_out` | output | `SEQ_WIDTH` | 输出 M 序列 |
| `o_seq_vld` | output | 1 | 输出 M 序列有效指示，相对 `i_cal_vld` 延迟 5 拍 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_mseq_cal #(
    .CAL_RULE                 ( 31'h9       ),//LFSR 反馈多项式
    .SEQ_WIDTH                ( 31          ) //M 序列位宽
) u_mseq_cal (
    .clk_in                   ( clk_in      ),
    .rst_n                    ( rst_n       ),
    .i_init_seq               ( init_seq    ),
    .i_cal_vld                ( cal_vld     ),
    .i_trans_num              ( trans_num   ),
    .o_seq_out                ( seq_out     ),
    .o_seq_vld                ( seq_vld     )
);
```

## pubip_dynamic_mem

按 ID 的动态存储调度：用链表管理多 ID 的数据存储，支持多 ID 交叉写入、first-fit 空闲地址分配、FIFO 顺序读出，T0 调度 ID、T1 输出数据与 ID 指示（借用 `sdpram_wrapper` 的 1 拍读延迟）。`o_wr_ready` / `o_rd_ready` 是握手就绪，`o_free_cnt` 是剩余空间，`o_schd_id` 与 `o_schd_id_remain` 给出当前调度的 ID 与该 ID 剩余笔数，`o_rd_last` 标出某 ID 的最后一笔。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `MEM_DEPTH` | 64 | 存储深度（笔数） |
| `DATA_WIDTH` | 32 | 数据位宽 |
| `ID_WIDTH` | 4 | ID 位宽，ID 个数与存储深度独立配置 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `clk_in` | input | 1 | 时钟输入 |
| `rst_n` | input | 1 | 异步复位，低有效 |
| `o_wr_ready` | output | 1 | 模块写入就绪指示 |
| `i_wr_vld` | input | 1 | 写入有效指示 |
| `i_wr_id` | input | `ID_WIDTH` | 写入数据对应 ID |
| `i_wr_data` | input | `DATA_WIDTH` | 写入数据 |
| `i_rd_id_vld` | input | 1 | 读取调度 ID 有效指示 |
| `i_rd_id` | input | `ID_WIDTH` | 读取调度 ID |
| `o_rd_ready` | output | 1 | 模块读取就绪指示 |
| `i_rd_vld` | input | 1 | 后级读取有效指示 |
| `o_rd_data` | output | `DATA_WIDTH` | 读取数据输出 |
| `o_rd_last` | output | 1 | 当前输出为对应 ID 最后一笔指示 |
| `o_free_cnt` | output | `$clog2(MEM_DEPTH+1)` | 当前剩余空间个数 |
| `o_schd_id` | output | `ID_WIDTH` | 当前调度输出 ID 指示 |
| `o_schd_id_remain` | output | `$clog2(MEM_DEPTH+1)` | 当前调度 ID 剩余数据个数 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_dynamic_mem #(
    .MEM_DEPTH               ( 64            ),//存储深度
    .DATA_WIDTH              ( 32            ),//数据位宽
    .ID_WIDTH                ( 4             ) //ID 位宽
) u_dyn_mem (
    .clk_in                  ( clk_in        ),
    .rst_n                   ( rst_n         ),
    .o_wr_ready              ( wr_ready      ),
    .i_wr_vld                ( wr_vld        ),
    .i_wr_id                 ( wr_id         ),
    .i_wr_data               ( wr_data       ),
    .i_rd_id_vld             ( rd_id_vld     ),
    .i_rd_id                 ( rd_id         ),
    .o_rd_ready              ( rd_ready      ),
    .i_rd_vld                ( rd_vld        ),
    .o_rd_data               ( rd_data       ),
    .o_rd_last               ( rd_last       ),
    .o_free_cnt              ( free_cnt      ),
    .o_schd_id               ( schd_id       ),
    .o_schd_id_remain        ( schd_remain   )
);
```

## pubip_complex_mult

复数乘法：两路复数相乘，实部虚部分开，`CONJ_EN=1` 时对第二路取共轭。纯组合，没有时钟复位。输入按各自的位宽声明为有符号，输出位宽是两路输入位宽之和。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `DINA_WIDTH` | 10 | 第一路复数的实部/虚部位宽 |
| `DINB_WIDTH` | 6 | 第二路复数的实部/虚部位宽 |
| `CONJ_EN` | 0 | 1 时对第二路取共轭 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `i_dina_re` | input | `DINA_WIDTH` | 第一路实部，有符号 |
| `i_dina_im` | input | `DINA_WIDTH` | 第一路虚部，有符号 |
| `i_dinb_re` | input | `DINB_WIDTH` | 第二路实部，有符号 |
| `i_dinb_im` | input | `DINB_WIDTH` | 第二路虚部，有符号 |
| `o_dout_re` | output | `DINA_WIDTH + DINB_WIDTH` | 乘积实部，有符号 |
| `o_dout_im` | output | `DINA_WIDTH + DINB_WIDTH` | 乘积虚部，有符号 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_complex_mult #(
    .DINA_WIDTH         ( 10        ),
    .DINB_WIDTH         ( 6         ),
    .CONJ_EN            ( 0         )
) u_cmult (
    .i_dina_re           ( a_re      ),
    .i_dina_im           ( a_im      ),
    .i_dinb_re           ( b_re      ),
    .i_dinb_im           ( b_im      ),
    .o_dout_re           ( p_re      ),
    .o_dout_im           ( p_im      )
);
```

## sdpram_wrapper

简单双口 RAM 封装：端口 A 写、带字节使能，端口 B 读、读使能有效后下一拍出数据；同地址同时读写按写优先（Write-First），读端口输出新写入的数据。默认是行为级模型，要换实际 RAM 宏时只改这一个文件。`pubip_dynamic_mem` 用它存数据，也可单独复用作延迟缓冲。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `DATA_WIDTH` | 32 | 数据位宽 |
| `ADDR_WIDTH` | 6 | 地址位宽，对应深度 2^`ADDR_WIDTH` |
| `BYTE_EN_WIDTH` | 4 | 字节使能位宽，通常为 `DATA_WIDTH`/8 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `clk_in` | input | 1 | 时钟输入 |
| `i_wea` | input | 1 | 写使能，高有效 |
| `i_bea` | input | `BYTE_EN_WIDTH` | 字节使能，每 bit 对应一个字节 |
| `i_addra` | input | `ADDR_WIDTH` | 写地址 |
| `i_dina` | input | `DATA_WIDTH` | 写数据 |
| `i_reb` | input | 1 | 读使能，高有效 |
| `i_addrb` | input | `ADDR_WIDTH` | 读地址 |
| `o_doutb` | output | `DATA_WIDTH` | 读数据，`i_reb` 有效后下一拍输出 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
sdpram_wrapper #(
    .DATA_WIDTH               ( 32         ),//数据位宽
    .ADDR_WIDTH               ( 6          ),//地址位宽，深度 2^ADDR_WIDTH
    .BYTE_EN_WIDTH            ( 4          ) //字节使能位宽
) u_sdpram (
    .clk_in                   ( clk_in     ),
    .i_wea                    ( ram_wea    ),
    .i_bea                    ( ram_bea    ),
    .i_addra                  ( ram_addra  ),
    .i_dina                   ( ram_dina   ),
    .i_reb                    ( ram_reb    ),
    .i_addrb                  ( ram_addrb  ),
    .o_doutb                  ( ram_doutb  )
);
```

## pubip_cdc_sync

两级同步器：把已在源时钟域寄存一拍的单比特控制信号同步到目标时钟域，目标域按 `STAGES` 级寄存器链打拍（默认两级，第一级只采样、不带组合逻辑）。异步复位只在目标域生效，低有效。多比特总线不得逐位经本单元同步，要按 `rules/coding.md` §跨时钟域 用握手、保持寄存器或 `pubip_async_fifo`；输出只作控制使用。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `STAGES` | 2 | 同步级数，默认两级（第一级只寄存，不带组合逻辑） |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `clk_in` | input | 1 | 目标域时钟 |
| `rst_n` | input | 1 | 目标域异步复位，低有效 |
| `i_data` | input | 1 | 源域信号，已在源域寄存 |
| `o_data` | output | 1 | 目标域同步后信号 |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_cdc_sync #(
    .STAGES                   ( 2         ) //同步级数，默认两级
) u_cdc_sync (
    .clk_in                   ( clk_dst   ),//目标域时钟
    .rst_n                    ( rst_n_dst ),//目标域异步复位，低有效
    .i_data                   ( src_flag  ),//源域信号，已在源域寄存
    .o_data                   ( dst_flag  ) //目标域同步后信号
);
```

## pubip_async_fifo

异步 FIFO：写域与读域各用自己的时钟与复位，跨域搬运数据流并给出写满/读空背压。读写指针各留在自己的时钟域，跨域只搬二进制指针的格雷码，按位经 `pubip_cdc_sync` 打拍；深度为 `2^ADDR_WIDTH`。读数据在 `i_rd_en` 有效后的下一拍输出；写满时写指针与存储体都不推进，读空时读指针不推进。多比特数据不得逐位当同步器用，跨域数据流一律走本单元。

### 参数

<!-- PUBIP_PARAMS -->
| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `DATA_WIDTH` | 32 | 数据位宽 |
| `ADDR_WIDTH` | 6 | 地址位宽，深度 2^ADDR_WIDTH |
| `SYNC_STAGES` | 2 | 格雷码指针跨域同步级数 |
<!-- /PUBIP_PARAMS -->

### 端口

<!-- PUBIP_PORTS -->
| 端口 | 方向 | 位宽 | 说明 |
|------|------|------|------|
| `i_wr_clk` | input | 1 | 写时钟 |
| `i_wr_rst_n` | input | 1 | 写域异步复位，低有效 |
| `i_wr_en` | input | 1 | 写使能，高有效 |
| `i_wr_data` | input | `DATA_WIDTH` | 写数据 |
| `o_wr_full` | output | 1 | 写满指示（写域） |
| `i_rd_clk` | input | 1 | 读时钟 |
| `i_rd_rst_n` | input | 1 | 读域异步复位，低有效 |
| `i_rd_en` | input | 1 | 读使能，高有效 |
| `o_rd_data` | output | `DATA_WIDTH` | 读数据，读使能后下一拍输出 |
| `o_rd_empty` | output | 1 | 读空指示（读域） |
<!-- /PUBIP_PORTS -->

### 例化

```systemverilog
pubip_async_fifo #(
    .DATA_WIDTH               ( 32        ),//数据位宽
    .ADDR_WIDTH               ( 6         ),//地址位宽，深度 2^ADDR_WIDTH
    .SYNC_STAGES              ( 2         ) //格雷码指针跨域同步级数
) u_async_fifo (
    .i_wr_clk                 ( clk_a     ),//写时钟
    .i_wr_rst_n               ( rst_n_a   ),//写域异步复位，低有效
    .i_wr_en                  ( wr_en     ),//写使能，高有效
    .i_wr_data                ( wr_data   ),//写数据
    .o_wr_full                ( wr_full   ),//写满指示（写域）
    .i_rd_clk                 ( clk_b     ),//读时钟
    .i_rd_rst_n               ( rst_n_b   ),//读域异步复位，低有效
    .i_rd_en                  ( rd_en     ),//读使能，高有效
    .o_rd_data                ( rd_data   ),//读数据，读使能后下一拍输出
    .o_rd_empty               ( rd_empty  ) //读空指示（读域）
);
```

## 来源

- 例化示例以 `pub_code/` 各模块 RTL 为准转录，端口、参数与位宽逐条对 RTL；模块文件头不再要求例化示例（`rules/coding.md`）。
