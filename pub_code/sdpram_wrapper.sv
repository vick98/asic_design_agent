/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-05-10        vick           initial
#   1.1     2026-08-27          vick             端口补充 i_/o_ 前缀
#   1.2     2026-08-27          vick             修复 RAM 深度少一格（[RAM_DEPTH-1]）与 INIT_FILE 类型错误（int→string）
#   1.3     2026-08-27          vick             内部信号补 reg_ 前缀，时钟端口统一 clk_in，补齐子块分隔线空格
#   1.4     2026-08-27          vick             写端口块 always_ff→always（行为级RAM模型，兼容 $readmemh initial 初始化，VCS2017 ICPD）
#   1.5     2026-08-31          vick             删除 INIT_FILE 参数与 $readmemh 初始化功能（string 参数 DC 不可综合）；写端口恢复 always_ff
#
#-----------------------------------------------------------------------------------------
# Description:
        1.简单双口RAM（Simple Dual-Port RAM / 假双口RAM）wrapper
        2.端口A：写端口，带字节使能（byte enable），时钟沿写入
        3.端口B：读端口，带读使能，读使能有效后下一拍出数据
        4.写优先模式（Write-First）：同地址同时读写时，读端口输出新写入数据
        5.默认使用行为级模型，用户可根据项目需要自行替换为实际RAM宏
#-----------------------------------------------------------------------------------------
#快速例化示例
sdpram_wrapper #(
    .DATA_WIDTH               ( 32         ),//数据位宽
    .ADDR_WIDTH               ( 6          ),//地址位宽，对应深度 2^ADDR_WIDTH
    .BYTE_EN_WIDTH            ( 4          ) //字节使能位宽，通常为 DATA_WIDTH/8
) sdpram_wrapper_inst(
    .clk_in                   (           ),//时钟输入
    .i_wea                    (           ),//写使能，高有效
    .i_bea                    (           ),//字节使能，每bit对应一个字节
    .i_addra                  (           ),//写地址
    .i_dina                   (           ),//写数据
    .i_reb                    (           ),//读使能，高有效
    .i_addrb                  (           ),//读地址
    .o_doutb                  (           ) //读数据，i_reb有效后下一拍输出
);
=========================================FILE_HEADER====================================*/
module sdpram_wrapper
#(
    parameter int DATA_WIDTH     = 32 ,//数据位宽
    parameter int ADDR_WIDTH     = 6  ,//地址位宽，对应深度 2^ADDR_WIDTH
    parameter int BYTE_EN_WIDTH  = 4   //字节使能位宽，通常为 DATA_WIDTH/8
)
(
    input                               clk_in                  ,//时钟输入
    input                               i_wea                   ,//写使能，高有效
    input       [BYTE_EN_WIDTH-1:0]     i_bea                   ,//字节使能，每bit对应一个字节
    input       [ADDR_WIDTH-1:0]        i_addra                 ,//写地址
    input       [DATA_WIDTH-1:0]        i_dina                  ,//写数据
    input                               i_reb                   ,//读使能，高有效
    input       [ADDR_WIDTH-1:0]        i_addrb                 ,//读地址
    output      [DATA_WIDTH-1:0]        o_doutb                  //读数据，i_reb有效后下一拍输出
);

//======================== localparam define =================================
localparam int RAM_DEPTH = 1 << ADDR_WIDTH; // RAM深度 = 2^ADDR_WIDTH

//======================== main signal define =================================
logic       [DATA_WIDTH-1:0]        reg_ram [RAM_DEPTH]  ;//行为级RAM模型
logic       [DATA_WIDTH-1:0]        reg_doutb            ;//寄存器输出的读数据

//======================== main process ===================================
//----------- 端口A：写操作（带字节使能） ------------
always_ff @(posedge clk_in) begin
    if (i_wea) begin
        for (int i = 0; i < BYTE_EN_WIDTH; i = i + 1) begin
            if (i_bea[i])
                reg_ram[i_addra][8*i +: 8] <= i_dina[8*i +: 8];
        end
    end
end

//----------- 端口B：读操作（带读使能，寄存器输出，写优先模式） ------------
always_ff @(posedge clk_in) begin
    if (i_reb) begin
        if (i_wea && (i_addra == i_addrb)) begin
            // 同地址同时读写，写优先模式
            // 对每个字节分别判断字节使能
            for (int i = 0; i < BYTE_EN_WIDTH; i = i + 1) begin
                if (i_bea[i])
                    reg_doutb[8*i +: 8] <= i_dina[8*i +: 8];
                else
                    reg_doutb[8*i +: 8] <= reg_ram[i_addrb][8*i +: 8];
            end
        end else begin
            reg_doutb <= reg_ram[i_addrb];
        end
    end
end

assign o_doutb = reg_doutb;

endmodule
