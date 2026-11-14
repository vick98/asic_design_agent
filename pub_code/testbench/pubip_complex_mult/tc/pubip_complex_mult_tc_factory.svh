/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             注册全部用例（cm_conj 宏隔离注册）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 用例工厂（+TC 选择）；tc_cm_conj 需 +define+PUBIP_CM_CONJ 编译
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_FACTORY
`define U_PUBIP_COMPLEX_MULT_TC_FACTORY
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_factory ------------
class pubip_complex_mult_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_cm_re_basic":       begin pubip_complex_mult_tc_cm_re_basic       t = new("tc_cm_re_basic");       return t; end
            "tc_cm_im_basic":       begin pubip_complex_mult_tc_cm_im_basic       t = new("tc_cm_im_basic");       return t; end
            "tc_cm_neg":            begin pubip_complex_mult_tc_cm_neg            t = new("tc_cm_neg");            return t; end
            "tc_cm_overflow_range": begin pubip_complex_mult_tc_cm_overflow_range t = new("tc_cm_overflow_range"); return t; end
`ifdef PUBIP_CM_CONJ
            "tc_cm_conj":           begin pubip_complex_mult_tc_cm_conj           t = new("tc_cm_conj");           return t; end
`endif
            "tc_all":               begin pubip_complex_mult_tc_all               t = new("tc_all");               return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_FACTORY
