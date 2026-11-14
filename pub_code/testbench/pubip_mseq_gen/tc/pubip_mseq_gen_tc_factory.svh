/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 用例工厂（+TC 选择）；变体用例按编译宏隔离注册：
          PUBIP_MPG_TRANS4 -> tc_mseq_trans_n（+define+PUBIP_MPG_TRANS4 后 +TC 单独运行）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_FACTORY
`define U_PUBIP_MSEQ_GEN_TC_FACTORY
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_factory ------------
class pubip_mseq_gen_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_mseq_trans1":  begin pubip_mseq_gen_tc_mseq_trans1  t = new("tc_mseq_trans1");  return t; end
            "tc_mseq_border":  begin pubip_mseq_gen_tc_mseq_border  t = new("tc_mseq_border");  return t; end
            "tc_mseq_random":  begin pubip_mseq_gen_tc_mseq_random  t = new("tc_mseq_random");  return t; end
`ifdef PUBIP_MPG_TRANS4
            "tc_mseq_trans_n": begin pubip_mseq_gen_tc_mseq_trans_n t = new("tc_mseq_trans_n"); return t; end
`endif
            "tc_all":          begin pubip_mseq_gen_tc_all          t = new("tc_all");          return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_FACTORY
