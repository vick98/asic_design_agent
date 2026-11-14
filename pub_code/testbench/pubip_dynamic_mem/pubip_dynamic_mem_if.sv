/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 DUT 端口补全信号（MEM_DEPTH=64/ID_WIDTH=4/DATA_WIDTH=32）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 接口：与 DUT 端口一一对应（默认参数 64 深度 / ID_WIDTH=4 / DATA_WIDTH=32）
        i_ 输入信号均赋初值（VCS 按 X 仿真，未初始化输入会经 DUT 打拍链传播至 o_ 控制信号造成 X 态误报）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_IF
`define U_PUBIP_DYNAMIC_MEM_TB_IF

//----------- pubip_dynamic_mem_if ------------
// clk/rst 由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)
interface pubip_dynamic_mem_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    //----------- 写口 ------------
    logic                           o_wr_ready          ;//模块写入就绪指示（有空闲空间）
    logic                           i_wr_vld    = 1'b0  ;//写入有效指示
    logic [3:0]                     i_wr_id     = '0    ;//写入数据对应ID（ID_WIDTH=4）
    logic [31:0]                    i_wr_data   = '0    ;//写入数据（DATA_WIDTH=32）

    //----------- 读口（调度 + 后级） ------------
    logic                           i_rd_id_vld = 1'b0  ;//读取调度ID有效指示
    logic [3:0]                     i_rd_id     = '0    ;//读取调度ID
    logic                           o_rd_ready          ;//模块读取就绪指示（T1拍：当前有数据可读）
    logic                           i_rd_vld    = 1'b0  ;//后级读取有效指示（rd_ready=1 时采样表示消费一拍）
    logic [31:0]                    o_rd_data           ;//读取数据输出
    logic                           o_rd_last           ;//当前输出为对应ID最后一笔指示

    //----------- 状态指示 ------------
    logic [6:0]                     o_free_cnt          ;//当前剩余空间个数（$clog2(64+1)=7bit）
    logic [3:0]                     o_schd_id           ;//当前调度输出ID指示
    logic [6:0]                     o_schd_id_remain    ;//当前调度ID剩余数据个数

endinterface
`endif //U_PUBIP_DYNAMIC_MEM_TB_IF
