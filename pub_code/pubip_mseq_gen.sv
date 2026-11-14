/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-07-02        vick             initial
#   1.1     2026-08-27          vick             端口补充 i_/o_ 前缀，按框架规范重排分隔线与声明区
#   1.2     2026-08-27          vick             内部信号补充 wir_ 前缀，数组显式化范围（[N]→[0:N-1]）
#
#-----------------------------------------------------------------------------------------
# Description:
        1.M序列（最大长度LFSR）生成器，纯组合逻辑实现
        2.基于LFSR转移矩阵理论，通过 CAL_RULE 参数配置反馈多项式（本原多项式）
        3.支持一次跳变多个步长：TRANS_NUM 参数控制一次输出跨越的 LFSR 迭代次数
        4.通过 generate 块 + function 在综合期计算 A^TRANS_NUM 转移矩阵并折叠为常量
        5.i_cal_en=1 时输出经过 TRANS_NUM 次迭代后的序列；i_cal_en=0 时直接旁路 i_init_seq
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_mseq_gen #(
    .CAL_RULE                 ( 31'h9       ),//LFSR反馈多项式（本原多项式）
    .SEQ_WIDTH                ( 31          ),//序列位宽
    .TRANS_NUM                ( 1           ) //单次跨越的LFSR迭代次数
) pubip_mseq_gen_inst(
    .i_init_seq               (             ),//初始序列，位宽 SEQ_WIDTH
    .i_cal_en                 (             ),//计算使能：1=输出跨越后的序列，0=旁路 i_init_seq
    .o_seq_out                (             ) //输出序列，位宽 SEQ_WIDTH
);
=========================================FILE_HEADER====================================*/
module pubip_mseq_gen #(
    parameter CAL_RULE  = 31'h9,//b1001,
    parameter SEQ_WIDTH = 31,
    parameter TRANS_NUM = 1
) (
    input   [SEQ_WIDTH - 1 : 0]     i_init_seq,
    input                           i_cal_en,
    output  [SEQ_WIDTH - 1 : 0]     o_seq_out
);

//======================== localparam define =================================

//======================== main signal define =================================
//----------- 转移矩阵信号 ------------
wire        [SEQ_WIDTH - 1 : 0]     wir_trans_mtrx [SEQ_WIDTH] ;//列优先，wir_trans_mtrx[j] = 第 j 列
wire        [SEQ_WIDTH - 1 : 0]     wir_cal_mtrx   [SEQ_WIDTH] ;//行优先，wir_cal_mtrx[i][j] = 第 i 行第 j 列

//======================== main process ===================================
//----------- 函数：计算单列的转移矩阵 ------------
// 输入：列索引 j （该列只有第 j 位为 1）
// 返回：经过 TRANS_NUM 次 LFSR 迭代后该列的值（即 A^TRANS_NUM 的第 j 列）
function automatic [SEQ_WIDTH-1:0] calc_trans_col;
    input integer j;
    reg [SEQ_WIDTH-1:0] state;
    integer step;
    begin
        // 初始基向量：第 j 位为 1，其余为 0
        state = {{(SEQ_WIDTH-1){1'b0}}, 1'b1} << j;
        // 迭代 TRANS_NUM 次
        for (step = 0; step < TRANS_NUM; step = step + 1) begin
            state = {^(CAL_RULE & state), state[SEQ_WIDTH-1:1]};
        end
        calc_trans_col = state;
    end
endfunction

//----------- 生成列矩阵 ------------
// 按列生成 wir_trans_mtrx（每一列即 calc_trans_col(j)）
genvar j;
generate
    for (j = 0; j < SEQ_WIDTH; j = j + 1) begin : col_gen
        assign wir_trans_mtrx[j] = calc_trans_col(j);   // 右边已无任何迭代变量
    end
endgenerate

//----------- 转置：列矩阵转行矩阵 ------------
// 再将 wir_trans_mtrx 转置为 wir_cal_mtrx，便于后续按行与 i_init_seq 相与
genvar m, k;
generate
    for (m = 0; m < SEQ_WIDTH; m = m + 1) begin : row_gen
        for (k = 0; k < SEQ_WIDTH; k = k + 1) begin : bit_gen
            assign wir_cal_mtrx[m][k] = wir_trans_mtrx[k][m];
        end
    end
endgenerate

//----------- 最终输出 ------------
genvar l;
generate
    for (l = 0; l < SEQ_WIDTH; l = l + 1) begin : out_gen
        assign o_seq_out[l] = i_cal_en ? (^(wir_cal_mtrx[l] & i_init_seq)) : i_init_seq[l];
    end
endgenerate

endmodule
