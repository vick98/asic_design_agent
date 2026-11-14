/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tb_pkg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 框架式 TB 包：参数宏中心 + 组件类集合（被 tc/sim_top include）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`ifndef U_PUBIP_SAT_TB_PKG
`define U_PUBIP_SAT_TB_PKG

`include "tb_define.svh"
`include "pubip_sat_cfg.svh"
package pubip_sat_tb_pkg;
    import tb_pkg::*;

    //----------- 组件类（各 .svh 内含宏守卫，可重复 include） ------------
`include "pubip_sat_tb_item.svh"
`include "pubip_sat_tb_driver.svh"
`include "pubip_sat_tb_monitor.svh"
`include "pubip_sat_tb_refm.svh"
`include "pubip_sat_tb_scoreboard.svh"
`include "pubip_sat_tb_env.svh"

endpackage
`endif //U_PUBIP_SAT_TB_PKG
