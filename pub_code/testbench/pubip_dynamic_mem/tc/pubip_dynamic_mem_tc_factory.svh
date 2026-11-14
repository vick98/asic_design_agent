/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 用例工厂（+TC 选择）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_FACTORY
`define U_PUBIP_DYNAMIC_MEM_TC_FACTORY
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_factory ------------
// 用例工厂：按名称创建用例对象（sim_top 中 +TC=<name> 选择）
// 注意：static 函数无法多态覆盖，直接重新定义同名函数遮蔽基类
class pubip_dynamic_mem_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_wr_rd": begin pubip_dynamic_mem_tc_wr_rd t = new("tc_wr_rd"); return t; end
            "tc_multi_id": begin pubip_dynamic_mem_tc_multi_id t = new("tc_multi_id"); return t; end
            "tc_full_depth": begin pubip_dynamic_mem_tc_full_depth t = new("tc_full_depth"); return t; end
            "tc_rd_last": begin pubip_dynamic_mem_tc_rd_last t = new("tc_rd_last"); return t; end
            "tc_conflict": begin pubip_dynamic_mem_tc_conflict t = new("tc_conflict"); return t; end
            "tc_remain": begin pubip_dynamic_mem_tc_remain t = new("tc_remain"); return t; end
            "tc_random": begin pubip_dynamic_mem_tc_random t = new("tc_random"); return t; end
            "tc_all":    begin pubip_dynamic_mem_tc_all t = new("tc_all"); return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_FACTORY
