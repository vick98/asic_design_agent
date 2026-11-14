/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             注册全部用例（9 条测试要点 + tc_all 聚合）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 用例工厂（+TC 选择）；tc_all 为聚合用例（顺序执行全部子用例）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_FACTORY
`define U_PUBIP_MSEQ_CAL_TC_FACTORY
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_factory ------------
// 用例工厂：按名称创建用例对象（sim_top 中 +TC=<name> 选择）
// 注意：static 函数无法多态覆盖，直接重新定义同名函数遮蔽基类
class pubip_mseq_cal_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_cal_trans0":     begin pubip_mseq_cal_tc_cal_trans0     t = new("tc_cal_trans0");     return t; end
            "tc_cal_trans1":     begin pubip_mseq_cal_tc_cal_trans1     t = new("tc_cal_trans1");     return t; end
            "tc_cal_pow2":       begin pubip_mseq_cal_tc_cal_pow2       t = new("tc_cal_pow2");       return t; end
            "tc_cal_full32767":  begin pubip_mseq_cal_tc_cal_full32767  t = new("tc_cal_full32767");  return t; end
            "tc_cal_seg1_bound": begin pubip_mseq_cal_tc_cal_seg1_bound t = new("tc_cal_seg1_bound"); return t; end
            "tc_cal_seg2_bound": begin pubip_mseq_cal_tc_cal_seg2_bound t = new("tc_cal_seg2_bound"); return t; end
            "tc_cal_vld_align":  begin pubip_mseq_cal_tc_cal_vld_align  t = new("tc_cal_vld_align");  return t; end
            "tc_cal_multi_call": begin pubip_mseq_cal_tc_cal_multi_call t = new("tc_cal_multi_call"); return t; end
            "tc_cal_random":     begin pubip_mseq_cal_tc_cal_random     t = new("tc_cal_random");     return t; end
            "tc_all":            begin pubip_mseq_cal_tc_all            t = new("tc_all");            return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_FACTORY
