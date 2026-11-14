/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 用例工厂（+TC 选择）；full_scan 按 W_src <= 16 条件注册
        （W_src > 16 的变体用 half_bound、sat_pos/sat_neg、neg_asym、random 覆盖，见 cfg 变体宏）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_FACTORY
`define U_PUBIP_ROUND_TC_FACTORY
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_factory ------------
class pubip_round_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
`ifdef PUBIP_ROUND_HAVE_FULL_SCAN
            "tc_full_scan":  begin pubip_round_tc_full_scan  t = new("tc_full_scan");  return t; end
`endif
            "tc_half_bound": begin pubip_round_tc_half_bound t = new("tc_half_bound"); return t; end
            "tc_sat_pos":    begin pubip_round_tc_sat_pos    t = new("tc_sat_pos");    return t; end
            "tc_sat_neg":    begin pubip_round_tc_sat_neg    t = new("tc_sat_neg");    return t; end
            "tc_neg_asym":   begin pubip_round_tc_neg_asym   t = new("tc_neg_asym");   return t; end
            "tc_nzero":      begin pubip_round_tc_nzero      t = new("tc_nzero");      return t; end
            "tc_random":     begin pubip_round_tc_random     t = new("tc_random");     return t; end
            "tc_clamp_check":begin pubip_round_tc_clamp_check t = new("tc_clamp_check"); return t; end
            "tc_all":        begin pubip_round_tc_all        t = new("tc_all");        return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_ROUND_TC_FACTORY
