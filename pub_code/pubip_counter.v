/*========================================FILE_HEADER=====================================
# Filename: pubip_counter.v
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2023-09-24         vick              initial
#   1.1     2023-09-27         vick             增加可变计数最大值
#   1.2     2026-04-05         vick             修改启动逻辑：启动脉冲仅作为触发，本身不计数，端口重命名
#   1.3     2026-08-27          vick             修复 CNT_WIDTH 缺省位宽差一位：$clog2(MAX_NUM) → $clog2(MAX_NUM+1)
#   1.4     2026-08-27          vick             修复 o_cnt_shift 脉冲输出截断：端口加宽至 [MAX_NUM:0]，脉冲位与计数值一一对应
#   1.5     2026-08-27          vick             规范化：补齐逻辑块分隔线、启动优先级统一、修正缩进、补全快速例化示例
#
#-----------------------------------------------------------------------------------------
# Description:
        1.公用模块，实现计数器功能，输出脉冲
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_counter #(
    .MAX_NUM                ( 7         ),//设置最大计数值，7时计数值0~7
    .CYCLE_EN               ( 0         ),//设置循环计数使能，0关闭，1或其他使能
    .CNT_WIDTH              ( 3         ) //计数器位宽，可不配置（默认自动计算 $clog2(MAX_NUM+1)）
) pubip_counter_inst(
    .clk_in                 (           ),//时钟输入
    .rst_n                  (           ),//复位输入
    .i_cnt_start_b1         (           ),//计数启动脉冲，脉冲到来清零并开始计数，脉冲本身不计数
    .i_cnt_rst              (           ),//计数复位
    .i_cnt_end              (           ),//计数停止

    .o_cnt_en               (           ),//计数使能
    .o_counter              (           ),//计数器数值输出
    .o_cnt_shift            (           ) //计数器脉冲输出
);
=========================================FILE_HEADER====================================*/

module pubip_counter
#(
    parameter int MAX_NUM = 7,//设置最大计数值，7时计数值0~7
    parameter int CYCLE_EN = 0,//设置循环计数使能，0关闭，1或其他使能
    parameter int CNT_WIDTH = $clog2(MAX_NUM + 1)   //默认自动计算计数器最小位宽
)
(
    input                               clk_in                  ,//时钟输入
    input                               rst_n                   ,//复位输入
    input                               i_cnt_start_b1          ,//计数启动脉冲，脉冲到来清零并开始计数，脉冲本身不计数
    input                               i_cnt_rst               ,//计数复位，单次计数时停止计数，循环计数时清零改变循环最大值
    input                               i_cnt_end               ,//计数停止

    output                              o_cnt_en                ,//计数使能
    output      [CNT_WIDTH - 1 : 0]     o_counter               ,//计数器数值输出
    output      [MAX_NUM     : 0]     o_cnt_shift              //计数器脉冲输出，bit j 对应计数值 j（bit0 计数使能时有效）
);

//======================== localparam define =================================


//======================== main signal define =================================
reg         [CNT_WIDTH - 1 : 0]     reg_counter         ;//计数器
wire        [MAX_NUM       : 0]     wir_decoder         ;//解码器
reg                                 reg_cnt_en          ;//计数使能
wire                                wir_cnt_end         ;//计数结束脉冲

//======================== main process ===================================
//----------- 计数器主逻辑 ------------
assign wir_cnt_end = reg_counter == MAX_NUM ;

always @(posedge clk_in,negedge rst_n)
    if(!rst_n)
        reg_counter <= {CNT_WIDTH{1'b0}}    ;
    else if(wir_cnt_end | i_cnt_end | i_cnt_rst | i_cnt_start_b1)
        reg_counter <= {CNT_WIDTH{1'b0}}    ;
    else if(reg_cnt_en)
        reg_counter <= reg_counter + 1'b1   ;

//----------- 单次/多次计数生成 ------------
generate
    if(CYCLE_EN == 0) begin:gen_cnt_once_gen
        always @(posedge clk_in, negedge rst_n )
            if(!rst_n)
                reg_cnt_en <= 1'b0;
            else if(i_cnt_start_b1)
                reg_cnt_en <= 1'b1;
            else if(wir_cnt_end | i_cnt_end | i_cnt_rst)
                reg_cnt_en <= 1'b0;
    end
    else begin:gen_cycle_cnt_gen
        always @(posedge clk_in, negedge rst_n )
            if(!rst_n)
                reg_cnt_en <= 1'b0;
            else if(i_cnt_start_b1)
                reg_cnt_en <= 1'b1;
            else if(i_cnt_end)
                reg_cnt_en <= 1'b0;
    end
endgenerate

//----------- 解码器生成 ------------
genvar decode_i;
generate
    for(decode_i = 0;decode_i <= MAX_NUM;decode_i = decode_i + 1)begin:gen_counter_decode
        assign wir_decoder[decode_i] = (reg_counter == decode_i) ? 1'b1 : 1'b0;
    end
endgenerate

assign o_cnt_en = reg_cnt_en;
assign o_cnt_shift = {wir_decoder[MAX_NUM:1],(wir_decoder[0] & reg_cnt_en)};
assign o_counter = reg_counter;

endmodule
