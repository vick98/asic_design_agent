/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             注册全部用例（cycle 用例宏隔离注册）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 用例工厂（+TC 选择）；tc_cycle 需 +define+PUBIP_CNT_CYCLE 编译
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_FACTORY
`define U_PUBIP_COUNTER_TC_FACTORY
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_factory ------------
class pubip_counter_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_basic":       begin pubip_counter_tc_basic       t = new("tc_basic");       return t; end
            "tc_max_end":     begin pubip_counter_tc_max_end     t = new("tc_max_end");     return t; end
            "tc_pow2_maxnum": begin pubip_counter_tc_pow2_maxnum t = new("tc_pow2_maxnum"); return t; end
            "tc_shift_width": begin pubip_counter_tc_shift_width t = new("tc_shift_width"); return t; end
            "tc_rst_clear":   begin pubip_counter_tc_rst_clear   t = new("tc_rst_clear");   return t; end
            "tc_cnt_rst":     begin pubip_counter_tc_cnt_rst     t = new("tc_cnt_rst");     return t; end
            "tc_cnt_end":     begin pubip_counter_tc_cnt_end     t = new("tc_cnt_end");     return t; end
`ifdef PUBIP_CNT_CYCLE
            "tc_cycle":       begin pubip_counter_tc_cycle       t = new("tc_cycle");       return t; end
`endif
            "tc_all":         begin pubip_counter_tc_all         t = new("tc_all");         return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_COUNTER_TC_FACTORY
