/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-07-04        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        1.pubip_mseq_cal 模块用于在固定 5 拍延迟内（输入锁存 1 拍 + 4 段流水）完成任意 0~32767 次转移的 M 序列计算
        2.通过例化 15 个不同 TRANS_NUM 参数（2^0 ~ 2^14）的 pubip_mseq_gen 子模块构成"二进制转移链"
        3.将 15 bit 转移次数按二进制展开分别控制各级 mseq_gen 的 i_cal_en 端口
        4.采用 4 段非均匀流水打拍策略，平衡各级组合逻辑深度，均衡时序
        5.控制通路（trans_num 低位 + cal_vld）与数据通路严格同步打拍
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_mseq_cal #(
    .CAL_RULE                 ( 31'h9       ),//LFSR反馈多项式（本原多项式）
    .SEQ_WIDTH                ( 31          ) //M序列位宽（LFSR级数）
) pubip_mseq_cal_inst(
    .clk_in                   (             ),//时钟输入
    .rst_n                    (             ),//异步复位，低电平有效
    .i_init_seq               (             ),//初始M序列输入，位宽 SEQ_WIDTH
    .i_cal_vld                (             ),//计算有效指示，高电平时锁存输入启动计算
    .i_trans_num              (             ),//转移次数控制值，位宽 15，二进制无符号数
    .o_seq_out                (             ),//输出M序列，位宽 SEQ_WIDTH
    .o_seq_vld                (             ) //输出M序列有效指示，相对 i_cal_vld 延迟 5 拍
);
=========================================FILE_HEADER====================================*/
module pubip_mseq_cal
#(
    parameter CAL_RULE  = 31'h9,//LFSR反馈多项式（本原多项式）
    parameter SEQ_WIDTH = 31    //M序列位宽（LFSR级数）
)
(
    input                               clk_in                  ,
    input                               rst_n                   ,
    input       [SEQ_WIDTH - 1 : 0]     i_init_seq              ,//初始M序列输入
    input                               i_cal_vld               ,//计算有效指示
    input       [14 : 0]                i_trans_num             ,//转移次数控制值
    output      [SEQ_WIDTH - 1 : 0]     o_seq_out               ,//输出M序列
    output                              o_seq_vld                //输出M序列有效指示
);

//======================== localparam define =================================

//======================== main signal define =================================
//------ 逻辑块1：输入锁存信号 ------
logic       [SEQ_WIDTH - 1 : 0]     reg_init_seq_d0         ;//锁存的初始M序列
logic       [14 : 0]                reg_trans_num_d0        ;//锁存的转移次数控制字
logic                               reg_cal_vld             ;//i_cal_vld 无条件打拍（拍1），作为段1 en 门控源

//------ 逻辑块2：段1转移链与打拍信号 ------
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s1_m14          ;//第1级(TRANS_NUM=16384)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s1_m13          ;//第2级(TRANS_NUM=8192)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     reg_seq_stage1          ;//段1打拍后的序列数据寄存器
logic       [12 : 0]                reg_trans_num_d1        ;//段1打拍后传递的trans_num低位bit[12:0]

//------ 逻辑块3：段2转移链与打拍信号 ------
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s2_m12          ;//第1级(TRANS_NUM=4096)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s2_m11          ;//第2级(TRANS_NUM=2048)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s2_m10          ;//第3级(TRANS_NUM=1024)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s2_m9           ;//第4级(TRANS_NUM=512)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     reg_seq_stage2          ;//段2打拍后的序列数据寄存器
logic       [8 : 0]                 reg_trans_num_d2        ;//段2打拍后传递的trans_num低位bit[8:0]

//------ 逻辑块4：段3转移链与打拍信号 ------
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s3_m8           ;//第1级(TRANS_NUM=256)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s3_m7           ;//第2级(TRANS_NUM=128)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     reg_seq_stage3          ;//段3打拍后的序列数据寄存器
logic       [6 : 0]                 reg_trans_num_d3        ;//段3打拍后传递的trans_num低位bit[6:0]

//------ 逻辑块5：段4转移链与打拍信号 ------
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m6           ;//第1级(TRANS_NUM=64)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m5           ;//第2级(TRANS_NUM=32)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m4           ;//第3级(TRANS_NUM=16)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m3           ;//第4级(TRANS_NUM=8)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m2           ;//第5级(TRANS_NUM=4)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m1           ;//第6级(TRANS_NUM=2)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     wir_seq_s4_m0           ;//第7级(TRANS_NUM=1)组合逻辑输出
logic       [SEQ_WIDTH - 1 : 0]     reg_seq_stage4          ;//段4打拍后的序列数据寄存器，直接连接至o_seq_out

//------ 逻辑块6：cal_vld/seq_vld打拍链信号 ------
logic                               reg_cal_vld_dly1        ;//cal_vld 打拍2，段2 en 门控
logic                               reg_cal_vld_dly2        ;//cal_vld 打拍3，段3 en 门控
logic                               reg_cal_vld_dly3        ;//cal_vld 打拍4，段4 en 门控
logic                               reg_cal_vld_dly4        ;//cal_vld 打拍5，直接连接至 o_seq_vld



//======================== main process ===================================
//----------- 逻辑块1：输入锁存逻辑 ------------
// 数据与 trans_num 仅在 i_cal_vld 有效时锁存
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n) begin
        reg_init_seq_d0  <= '0;
        reg_trans_num_d0 <= '0;
    end
    else if (i_cal_vld) begin
        reg_init_seq_d0  <= i_init_seq;
        reg_trans_num_d0 <= i_trans_num;
    end
end

// cal_vld 无条件打拍跟踪 i_cal_vld，作为流水线各段 en 门控源（拍1有效指示）
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n)
        reg_cal_vld <= 1'b0;
    else
        reg_cal_vld <= i_cal_vld;
end

//----------- 逻辑块2：段1转移链与打拍逻辑（TRANS_NUM = 16384、8192） ------------
// 第1级：TRANS_NUM = 16384 (2^14)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 16384         )
) u_mseq_gen_s1_m14 (
    .i_init_seq               ( reg_init_seq_d0     ),
    .i_cal_en                 ( reg_trans_num_d0[14]),
    .o_seq_out                ( wir_seq_s1_m14      )
);

// 第2级：TRANS_NUM = 8192 (2^13)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 8192          )
) u_mseq_gen_s1_m13 (
    .i_init_seq               ( wir_seq_s1_m14      ),
    .i_cal_en                 ( reg_trans_num_d0[13]),
    .o_seq_out                ( wir_seq_s1_m13      )
);

// 段1数据打拍 + trans_num低位打拍，en 门控使用 reg_cal_vld（对应 reg_init_seq_d0 的有效拍）
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n) begin
        reg_seq_stage1   <= '0;
        reg_trans_num_d1 <= '0;
    end
    else if (reg_cal_vld) begin
        reg_seq_stage1   <= wir_seq_s1_m13;
        reg_trans_num_d1 <= reg_trans_num_d0[12:0];
    end
end

//----------- 逻辑块3：段2转移链与打拍逻辑（TRANS_NUM = 4096、2048、1024、512） ------------
// 第1级：TRANS_NUM = 4096 (2^12)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 4096          )
) u_mseq_gen_s2_m12 (
    .i_init_seq               ( reg_seq_stage1      ),
    .i_cal_en                 ( reg_trans_num_d1[12]),
    .o_seq_out                ( wir_seq_s2_m12      )
);

// 第2级：TRANS_NUM = 2048 (2^11)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 2048          )
) u_mseq_gen_s2_m11 (
    .i_init_seq               ( wir_seq_s2_m12      ),
    .i_cal_en                 ( reg_trans_num_d1[11]),
    .o_seq_out                ( wir_seq_s2_m11      )
);

// 第3级：TRANS_NUM = 1024 (2^10)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 1024          )
) u_mseq_gen_s2_m10 (
    .i_init_seq               ( wir_seq_s2_m11      ),
    .i_cal_en                 ( reg_trans_num_d1[10]),
    .o_seq_out                ( wir_seq_s2_m10      )
);

// 第4级：TRANS_NUM = 512 (2^9)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 512           )
) u_mseq_gen_s2_m9 (
    .i_init_seq               ( wir_seq_s2_m10      ),
    .i_cal_en                 ( reg_trans_num_d1[9] ),
    .o_seq_out                ( wir_seq_s2_m9       )
);

// 段2数据打拍 + trans_num低位打拍，en 门控使用 reg_cal_vld_dly1（对应 reg_seq_stage1 的有效拍）
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n) begin
        reg_seq_stage2   <= '0;
        reg_trans_num_d2 <= '0;
    end
    else if (reg_cal_vld_dly1) begin
        reg_seq_stage2   <= wir_seq_s2_m9;
        reg_trans_num_d2 <= reg_trans_num_d1[8:0];
    end
end

//----------- 逻辑块4：段3转移链与打拍逻辑（TRANS_NUM = 256、128） ------------
// 第1级：TRANS_NUM = 256 (2^8)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 256           )
) u_mseq_gen_s3_m8 (
    .i_init_seq               ( reg_seq_stage2      ),
    .i_cal_en                 ( reg_trans_num_d2[8] ),
    .o_seq_out                ( wir_seq_s3_m8       )
);

// 第2级：TRANS_NUM = 128 (2^7)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 128           )
) u_mseq_gen_s3_m7 (
    .i_init_seq               ( wir_seq_s3_m8       ),
    .i_cal_en                 ( reg_trans_num_d2[7] ),
    .o_seq_out                ( wir_seq_s3_m7       )
);

// 段3数据打拍 + trans_num低位打拍，en 门控使用 reg_cal_vld_dly2（对应 reg_seq_stage2 的有效拍）
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n) begin
        reg_seq_stage3   <= '0;
        reg_trans_num_d3 <= '0;
    end
    else if (reg_cal_vld_dly2) begin
        reg_seq_stage3   <= wir_seq_s3_m7;
        reg_trans_num_d3 <= reg_trans_num_d2[6:0];
    end
end

//----------- 逻辑块5：段4转移链与打拍逻辑（TRANS_NUM = 64、32、16、8、4、2、1）与输出 ------------
// 第1级：TRANS_NUM = 64 (2^6)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 64            )
) u_mseq_gen_s4_m6 (
    .i_init_seq               ( reg_seq_stage3      ),
    .i_cal_en                 ( reg_trans_num_d3[6] ),
    .o_seq_out                ( wir_seq_s4_m6       )
);

// 第2级：TRANS_NUM = 32 (2^5)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 32            )
) u_mseq_gen_s4_m5 (
    .i_init_seq               ( wir_seq_s4_m6       ),
    .i_cal_en                 ( reg_trans_num_d3[5] ),
    .o_seq_out                ( wir_seq_s4_m5       )
);

// 第3级：TRANS_NUM = 16 (2^4)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 16            )
) u_mseq_gen_s4_m4 (
    .i_init_seq               ( wir_seq_s4_m5       ),
    .i_cal_en                 ( reg_trans_num_d3[4] ),
    .o_seq_out                ( wir_seq_s4_m4       )
);

// 第4级：TRANS_NUM = 8 (2^3)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 8             )
) u_mseq_gen_s4_m3 (
    .i_init_seq               ( wir_seq_s4_m4       ),
    .i_cal_en                 ( reg_trans_num_d3[3] ),
    .o_seq_out                ( wir_seq_s4_m3       )
);

// 第5级：TRANS_NUM = 4 (2^2)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 4             )
) u_mseq_gen_s4_m2 (
    .i_init_seq               ( wir_seq_s4_m3       ),
    .i_cal_en                 ( reg_trans_num_d3[2] ),
    .o_seq_out                ( wir_seq_s4_m2       )
);

// 第6级：TRANS_NUM = 2 (2^1)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 2             )
) u_mseq_gen_s4_m1 (
    .i_init_seq               ( wir_seq_s4_m2       ),
    .i_cal_en                 ( reg_trans_num_d3[1] ),
    .o_seq_out                ( wir_seq_s4_m1       )
);

// 第7级：TRANS_NUM = 1 (2^0)
pubip_mseq_gen #(
    .CAL_RULE                 ( CAL_RULE      ),
    .SEQ_WIDTH                ( SEQ_WIDTH     ),
    .TRANS_NUM                ( 1             )
) u_mseq_gen_s4_m0 (
    .i_init_seq               ( wir_seq_s4_m1       ),
    .i_cal_en                 ( reg_trans_num_d3[0] ),
    .o_seq_out                ( wir_seq_s4_m0       )
);

// 段4数据打拍，en 门控使用 reg_cal_vld_dly3（对应 reg_seq_stage3 的有效拍）
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n)
        reg_seq_stage4 <= '0;
    else if (reg_cal_vld_dly3)
        reg_seq_stage4 <= wir_seq_s4_m0;
end

// 输出赋值
assign o_seq_out = reg_seq_stage4;

//----------- 逻辑块6：cal_vld/seq_vld 打拍链 ------------
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n) begin
        reg_cal_vld_dly1 <= 1'b0;
        reg_cal_vld_dly2 <= 1'b0;
        reg_cal_vld_dly3 <= 1'b0;
        reg_cal_vld_dly4 <= 1'b0;
    end
    else begin
        reg_cal_vld_dly1 <= reg_cal_vld;
        reg_cal_vld_dly2 <= reg_cal_vld_dly1;
        reg_cal_vld_dly3 <= reg_cal_vld_dly2;
        reg_cal_vld_dly4 <= reg_cal_vld_dly3;
    end
end

assign o_seq_vld = reg_cal_vld_dly4;

endmodule
