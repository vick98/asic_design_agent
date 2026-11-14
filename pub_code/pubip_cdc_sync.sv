/*========================================FILE_HEADER=====================================
# Filename: pubip_cdc_sync.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-17        vick           initial
#
#-----------------------------------------------------------------------------------------
# Description:
        1.两级同步器公共单元：把已在源域寄存的单比特控制信号同步到目标时钟域
        2.目标域寄存器链打拍，STAGES 默认 2；第一级只寄存采样值，不带组合逻辑
        3.异步复位只在目标域生效，低有效；各时钟域的复位释放由使用方各自同步
        4.只同步单比特控制；多比特数据不得逐位经本单元同步，要用握手、保持寄存器或异步 FIFO
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_cdc_sync #(
    .STAGES                   ( 2         ) //同步级数，默认两级
) pubip_cdc_sync_inst(
    .clk_in                   (           ),//目标域时钟
    .rst_n                    (           ),//目标域异步复位，低有效
    .i_data                   (           ),//源域信号，已在源域寄存
    .o_data                   (           ) //目标域同步后信号
);
=========================================FILE_HEADER====================================*/
module pubip_cdc_sync
#(
    parameter int STAGES = 2     //同步级数，默认两级（第一级只寄存，不带组合逻辑）
)
(
    input                               clk_in                  ,//目标域时钟
    input                               rst_n                   ,//目标域异步复位，低有效
    input                               i_data                  ,//源域信号，已在源域寄存
    output                              o_data                   //目标域同步后信号
);

//======================== localparam define =================================

//======================== main signal define =================================
logic       [STAGES - 1 : 0]        reg_sync                ;//目标域同步寄存器链，bit0 为第一级

//======================== main process ===================================
//----------- 目标域寄存器链：第一级只采样，后续级逐级打拍 ------------
always_ff @(posedge clk_in or negedge rst_n) begin
    if (!rst_n)
        reg_sync <= '0;
    else begin
        reg_sync[0] <= i_data;
        for (int stage = 1; stage < STAGES; stage = stage + 1)
            reg_sync[stage] <= reg_sync[stage-1];
    end
end

assign o_data = reg_sync[STAGES - 1];

endmodule
