/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_pkg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-31        vick             删除 SDPRAM_INIT_FILE 宏（INIT_FILE 功能随 DUT 删除）
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 框架式 TB 包：组件类集合（被 tc/sim_top include）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`ifndef U_SDPRAM_WRAPPER_TB_PKG
`define U_SDPRAM_WRAPPER_TB_PKG

`include "tb_define.svh"
package sdpram_wrapper_tb_pkg;
    import tb_pkg::*;

    //----------- 组件类（各 .svh 内含宏守卫，可重复 include） ------------
`include "sdpram_wrapper_tb_item.svh"
`include "sdpram_wrapper_tb_driver.svh"
`include "sdpram_wrapper_tb_monitor.svh"
`include "sdpram_wrapper_tb_refm.svh"
`include "sdpram_wrapper_tb_scoreboard.svh"
`include "sdpram_wrapper_tb_env.svh"

endpackage
`endif //U_SDPRAM_WRAPPER_TB_PKG
