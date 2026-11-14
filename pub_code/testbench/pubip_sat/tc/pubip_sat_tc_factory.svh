/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 用例工厂（+TC 选择）；变体用例按编译宏隔离注册：
          PUBIP_SAT_PROTECT -> tc_sat_zero_protect（单独 +TC 运行）
          PUBIP_SAT_EXPAND  -> tc_sat_expand（单独 +TC 运行）
          PUBIP_SAT_USIGNED -> tc_sat_unsigned（单独 +TC 运行）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_FACTORY
`define U_PUBIP_SAT_TC_FACTORY
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_factory ------------
class pubip_sat_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_sat_down_align": begin pubip_sat_tc_sat_down_align t = new("tc_sat_down_align"); return t; end
            "tc_sat_neg":       begin pubip_sat_tc_sat_neg       t = new("tc_sat_neg");       return t; end
            "tc_sat_ovf_pos":   begin pubip_sat_tc_sat_ovf_pos   t = new("tc_sat_ovf_pos");   return t; end
            "tc_sat_ovf_neg":   begin pubip_sat_tc_sat_ovf_neg   t = new("tc_sat_ovf_neg");   return t; end
            "tc_sat_random":    begin pubip_sat_tc_sat_random    t = new("tc_sat_random");    return t; end
`ifdef PUBIP_SAT_PROTECT
            "tc_sat_zero_protect": begin pubip_sat_tc_sat_zero_protect t = new("tc_sat_zero_protect"); return t; end
`endif
`ifdef PUBIP_SAT_EXPAND
            "tc_sat_expand":    begin pubip_sat_tc_sat_expand    t = new("tc_sat_expand");    return t; end
`endif
`ifdef PUBIP_SAT_USIGNED
            "tc_sat_unsigned":  begin pubip_sat_tc_sat_unsigned  t = new("tc_sat_unsigned");  return t; end
`endif
            "tc_all":           begin pubip_sat_tc_all           t = new("tc_all");           return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_SAT_TC_FACTORY
