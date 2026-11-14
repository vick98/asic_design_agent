/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_factory.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             注册全部用例（init_file 用例宏隔离注册）
#   1.2     2026-08-31        vick             移除 tc_init_file 注册（INIT_FILE 功能随 DUT 删除）
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 用例工厂（+TC 选择）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_FACTORY
`define U_SDPRAM_WRAPPER_TC_FACTORY
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_factory ------------
// 用例工厂：按名称创建用例对象（sim_top 中 +TC=<name> 选择）
// 注意：static 函数无法多态覆盖，直接重新定义同名函数遮蔽基类
class sdpram_wrapper_tc_factory extends tb_factory;

    static function tb_test_base create(string name);
        case (name)
            "tc_wr_rd":       begin sdpram_wrapper_tc_wr_rd       t = new("tc_wr_rd");       return t; end
            "tc_byte_en":     begin sdpram_wrapper_tc_byte_en     t = new("tc_byte_en");     return t; end
            "tc_write_first": begin sdpram_wrapper_tc_write_first t = new("tc_write_first"); return t; end
            "tc_rand":        begin sdpram_wrapper_tc_rand        t = new("tc_rand");        return t; end
            "tc_all":         begin sdpram_wrapper_tc_all         t = new("tc_all");         return t; end
            default: $fatal(1, "Unknown testcase: %s", name);
        endcase
        return null;
    endfunction
endclass
`endif //U_SDPRAM_WRAPPER_TC_FACTORY
