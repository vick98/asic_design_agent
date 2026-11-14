/*========================================FILE_HEADER=====================================
# Filename: pubip_async_fifo.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-17        vick           initial
#
#-----------------------------------------------------------------------------------------
# Description:
        1.异步 FIFO 公共单元：写域与读域各用自己的时钟，承载跨时钟域数据流与背压
        2.读写指针各留在自己的时钟域，跨域只搬运二进制指针的格雷码，按位经 pubip_cdc_sync 打拍
        3.满/空分别由写域、读域对格雷码比较得出；深度 2^ADDR_WIDTH
        4.读数据在读使能有效后的下一拍输出；读空、写满时读写都不推进指针
        5.读域与写域各用自己的异步复位，低有效
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_async_fifo #(
    .DATA_WIDTH               ( 32        ),//数据位宽
    .ADDR_WIDTH               ( 6         ),//地址位宽，深度 2^ADDR_WIDTH
    .SYNC_STAGES              ( 2         ) //格雷码指针跨域同步级数
) pubip_async_fifo_inst(
    .i_wr_clk                 (           ),//写时钟
    .i_wr_rst_n               (           ),//写域异步复位，低有效
    .i_wr_en                  (           ),//写使能，高有效
    .i_wr_data                (           ),//写数据
    .o_wr_full                (           ),//写满指示（写域）
    .i_rd_clk                 (           ),//读时钟
    .i_rd_rst_n               (           ),//读域异步复位，低有效
    .i_rd_en                  (           ),//读使能，高有效
    .o_rd_data                (           ),//读数据，读使能后下一拍输出
    .o_rd_empty               (           ) //读空指示（读域）
);
=========================================FILE_HEADER====================================*/
module pubip_async_fifo
#(
    parameter int DATA_WIDTH  = 32,//数据位宽
    parameter int ADDR_WIDTH  = 6 ,//地址位宽，深度 2^ADDR_WIDTH
    parameter int SYNC_STAGES = 2  //格雷码指针跨域同步级数
)
(
    input                               i_wr_clk                ,//写时钟
    input                               i_wr_rst_n              ,//写域异步复位，低有效
    input                               i_wr_en                 ,//写使能，高有效
    input       [DATA_WIDTH - 1 : 0]    i_wr_data               ,//写数据
    output                              o_wr_full               ,//写满指示（写域）
    input                               i_rd_clk                ,//读时钟
    input                               i_rd_rst_n              ,//读域异步复位，低有效
    input                               i_rd_en                 ,//读使能，高有效
    output      [DATA_WIDTH - 1 : 0]    o_rd_data               ,//读数据，读使能后下一拍输出
    output                              o_rd_empty               //读空指示（读域）
);

//======================== localparam define =================================
localparam int PTR_WIDTH = ADDR_WIDTH + 1;//格雷码指针位宽：地址位宽加 1 位区分空满
localparam int DEPTH     = 1 << ADDR_WIDTH;//存储深度

initial begin
    if (ADDR_WIDTH < 2)
        $error("pubip_async_fifo: ADDR_WIDTH 至少为 2（空满判据要用到指针高两位）");
end

//======================== main signal define =================================
logic       [DATA_WIDTH - 1 : 0]    reg_mem [DEPTH]             ;//双时钟行为级存储体
logic       [DATA_WIDTH - 1 : 0]    reg_rd_data                 ;//读域寄存器输出

logic       [PTR_WIDTH - 1 : 0]     reg_wr_bin                  ;//写域二进制写指针
logic       [PTR_WIDTH - 1 : 0]     reg_wr_gray                 ;//写域格雷码写指针
logic       [PTR_WIDTH - 1 : 0]     reg_rd_bin                  ;//读域二进制读指针
logic       [PTR_WIDTH - 1 : 0]     reg_rd_gray                 ;//读域格雷码读指针

logic       [PTR_WIDTH - 1 : 0]     wir_wr_bin_next             ;//写指针下一值（写域）
logic       [PTR_WIDTH - 1 : 0]     wir_rd_bin_next             ;//读指针下一值（读域）
logic       [PTR_WIDTH - 1 : 0]     wir_wr_gray_inc             ;//写指针加一的格雷码，用于满判据
logic       [PTR_WIDTH - 1 : 0]     wir_rd_gray_sync            ;//读格雷码同步到写域
logic       [PTR_WIDTH - 1 : 0]     wir_wr_gray_sync            ;//写格雷码同步到读域

//======================== main process ===================================
//----------- 写域：写指针推进与存储体写入（写满时冻结） ------------
assign wir_wr_bin_next = reg_wr_bin + 1'b1;
assign wir_wr_gray_inc = (reg_wr_bin + 1'b1) ^ ((reg_wr_bin + 1'b1) >> 1);

always_ff @(posedge i_wr_clk or negedge i_wr_rst_n) begin
    if (!i_wr_rst_n) begin
        reg_wr_bin  <= '0;
        reg_wr_gray <= '0;
    end else if (i_wr_en && !o_wr_full) begin
        reg_wr_bin  <= wir_wr_bin_next;
        reg_wr_gray <= wir_wr_bin_next ^ (wir_wr_bin_next >> 1);
    end
end

always_ff @(posedge i_wr_clk) begin
    if (i_wr_en && !o_wr_full)
        reg_mem[reg_wr_bin[ADDR_WIDTH - 1 : 0]] <= i_wr_data;
end

//----------- 读域：读指针推进与读数据寄存（读空时冻结） ------------
assign wir_rd_bin_next = reg_rd_bin + 1'b1;

always_ff @(posedge i_rd_clk or negedge i_rd_rst_n) begin
    if (!i_rd_rst_n) begin
        reg_rd_bin  <= '0;
        reg_rd_gray <= '0;
    end else if (i_rd_en && !o_rd_empty) begin
        reg_rd_bin  <= wir_rd_bin_next;
        reg_rd_gray <= wir_rd_bin_next ^ (wir_rd_bin_next >> 1);
    end
end

always_ff @(posedge i_rd_clk) begin
    if (i_rd_en && !o_rd_empty)
        reg_rd_data <= reg_mem[reg_rd_bin[ADDR_WIDTH - 1 : 0]];
end

assign o_rd_data = reg_rd_data;

//----------- 空满判据：各域用同步过来的对方格雷码 ------------
//满：写指针加一的格雷码 == 同步到写域的读指针高两位取反；空：读格雷码 == 同步到读域的写格雷码。
assign o_wr_full  = (wir_wr_gray_inc == {~wir_rd_gray_sync[PTR_WIDTH - 1 : PTR_WIDTH - 2],
                                         wir_rd_gray_sync[PTR_WIDTH - 3 : 0]});
assign o_rd_empty = (reg_rd_gray == wir_wr_gray_sync);

//----------- 格雷码指针跨域：逐位两级同步 ------------
genvar gwr;
genvar grd;
generate
    for (gwr = 0; gwr < PTR_WIDTH; gwr = gwr + 1) begin : gen_rd_gray_to_wr
        pubip_cdc_sync #(
            .STAGES (SYNC_STAGES)
        ) u_rd_gray_to_wr (
            .clk_in  (i_wr_clk     ),//目标域：写时钟
            .rst_n   (i_wr_rst_n   ),//目标域：写域复位
            .i_data  (reg_rd_gray[gwr]),//源域：读域格雷码
            .o_data  (wir_rd_gray_sync[gwr])
        );
    end
    for (grd = 0; grd < PTR_WIDTH; grd = grd + 1) begin : gen_wr_gray_to_rd
        pubip_cdc_sync #(
            .STAGES (SYNC_STAGES)
        ) u_wr_gray_to_rd (
            .clk_in  (i_rd_clk     ),//目标域：读时钟
            .rst_n   (i_rd_rst_n   ),//目标域：读域复位
            .i_data  (reg_wr_gray[grd]),//源域：写域格雷码
            .o_data  (wir_wr_gray_sync[grd])
        );
    end
endgenerate

endmodule
