/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_cm_re_basic.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现实部基本运算用例（正数点 + 代表性向量）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cm_re_basic：CONJ_EN=0 实部公式 Re=ar*br-ai*bi。主测点 A=3+2j, B=1+4j
        → Re=3*1-2*4=-5（16bit 有符号补码输出 0xFFFB），附代表性向量与零向量基线。
        期望由 refm.compute 公式回填（scoreboard 比对）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_CM_RE_BASIC
`define U_PUBIP_COMPLEX_MULT_TC_CM_RE_BASIC
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_cm_re_basic ------------
class pubip_complex_mult_tc_cm_re_basic extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_cm_re_basic");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_item seq[$];
        pubip_complex_mult_item it;
        reset_wait();
        `TB_CASE_BEGIN("TC1: cm_re_basic");
        m_env.m_scb.m_enable = 1'b1;
        // 零向量基线：(0,0)(0,0) → Re=0, Im=0
        it = new("v0"); it.m_ar = 0; it.m_ai = 0; it.m_br = 0; it.m_bi = 0; seq.push_back(it);
        // 主测点：(3,2)(1,4) → Re=3*1-2*4=-5, Im=3*4+2*1=14
        it = new("v1"); it.m_ar = 3; it.m_ai = 2; it.m_br = 1; it.m_bi = 4; seq.push_back(it);
        // 代表向量：(4,3)(2,2) → Re=8-6=2, Im=8+6=14
        it = new("v2"); it.m_ar = 4; it.m_ai = 3; it.m_br = 2; it.m_bi = 2; seq.push_back(it);
        // 代表向量：(7,-2)(3,5) → Re=21+10=31, Im=35-6=29
        it = new("v3"); it.m_ar = 7; it.m_ai = -2; it.m_br = 3; it.m_bi = 5; seq.push_back(it);
        // 代表向量：(-2,7)(4,1) → Re=-8-7=-15, Im=-2+28=26
        it = new("v4"); it.m_ar = -2; it.m_ai = 7; it.m_br = 4; it.m_bi = 1; seq.push_back(it);
        drive_seq(seq);
        `TB_CASE_END("TC1: cm_re_basic", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_CM_RE_BASIC
