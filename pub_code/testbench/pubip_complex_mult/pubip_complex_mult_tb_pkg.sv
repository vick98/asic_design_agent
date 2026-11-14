/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_pkg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 框架式 TB 包：组件类集合（被 tc/sim_top include）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`ifndef U_PUBIP_COMPLEX_MULT_TB_PKG
`define U_PUBIP_COMPLEX_MULT_TB_PKG

`include "tb_define.svh"
package pubip_complex_mult_tb_pkg;
    import tb_pkg::*;

    //----------- 组件类（各 .svh 内含宏守卫，可重复 include） ------------
`include "pubip_complex_mult_tb_item.svh"
`include "pubip_complex_mult_tb_driver.svh"
`include "pubip_complex_mult_tb_monitor.svh"
`include "pubip_complex_mult_tb_refm.svh"
`include "pubip_complex_mult_tb_scoreboard.svh"
`include "pubip_complex_mult_tb_env.svh"

endpackage
`endif //U_PUBIP_COMPLEX_MULT_TB_PKG
