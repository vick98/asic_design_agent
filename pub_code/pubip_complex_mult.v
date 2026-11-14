/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult.v
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2023-10-09         vick              initial
#   1.1     2026-08-27          vick             修复 CONJ_EN 极性定义（1=A*conj(B)），端口补充 i_/o_ 前缀
#   1.2     2026-08-27          vick             输出端口补充 signed，按框架规范补齐主分隔线与子块分隔线
#
#-----------------------------------------------------------------------------------------
# Description:
        1.实现复数乘法器，可设置复数相乘或a乘以b的共轭
        2.纯组合逻辑代码块
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_complex_mult #(
    .DINA_WIDTH         ( 10        ),
    .DINB_WIDTH         ( 6         ),
    .CONJ_EN            ( 0         )
) pubip_complex_mult_inst(
    .i_dina_re           (           ),
    .i_dina_im           (           ),
    .i_dinb_re           (           ),
    .i_dinb_im           (           ),

    .o_dout_re           (           ),
    .o_dout_im           (           )
);
=========================================FILE_HEADER====================================*/

module pubip_complex_mult #(
    parameter int DINA_WIDTH    =   10  ,
    parameter int DINB_WIDTH    =   6   ,
    parameter int CONJ_EN       =   0
) (
    input signed [DINA_WIDTH - 1 : 0]   i_dina_re ,
    input signed [DINA_WIDTH - 1 : 0]   i_dina_im ,
    input signed [DINB_WIDTH - 1 : 0]   i_dinb_re ,
    input signed [DINB_WIDTH - 1 : 0]   i_dinb_im ,

    output signed [DINA_WIDTH + DINB_WIDTH - 1 : 0]  o_dout_re ,
    output signed [DINA_WIDTH + DINB_WIDTH - 1 : 0]  o_dout_im
);

//======================== localparam define =================================

//======================== main signal define =================================

//======================== main process ===================================
//----------- 复数乘加实现（按 CONJ_EN 选择计算公式）------------
generate
    if(CONJ_EN) begin:gen_a_mult_conjb
        // CONJ_EN=1：输出 A * conj(B)
        assign o_dout_re = i_dina_re * i_dinb_re + i_dina_im * i_dinb_im  ;
        assign o_dout_im = i_dina_im * i_dinb_re - i_dina_re * i_dinb_im  ;
    end
    else begin:gen_a_mult_b
        // CONJ_EN=0：输出 A * B
        assign o_dout_re = i_dina_re * i_dinb_re - i_dina_im * i_dinb_im  ;
        assign o_dout_im = i_dina_re * i_dinb_im + i_dina_im * i_dinb_re  ;
    end
endgenerate

endmodule
