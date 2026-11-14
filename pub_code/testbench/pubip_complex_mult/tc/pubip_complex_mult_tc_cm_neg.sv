/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_cm_neg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现负数象限用例（四象限各取一 + 负 B 向量）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cm_neg：CONJ_EN=0 负数/混合符号象限。按输出 (Re,Im) 四象限各取一：
        (3,2)(1,4)→(-5,14) 负正 | (-3,2)(1,4)→(-11,-10) 负负 | (-3,-2)(1,4)→(5,-14) 正负 |
        (3,-2)(1,4)→(11,10) 正正；另附 B 虚部为负向量 (-3,2)(1,-4)→(5,14) 与
        双负向量 (3,2)(-1,-4)→(5,-14)。期望由 refm.compute 公式回填
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_CM_NEG
`define U_PUBIP_COMPLEX_MULT_TC_CM_NEG
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_cm_neg ------------
class pubip_complex_mult_tc_cm_neg extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_cm_neg");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_item seq[$];
        pubip_complex_mult_item it;
        reset_wait();
        `TB_CASE_BEGIN("TC3: cm_neg");
        m_env.m_scb.m_enable = 1'b1;
        // Q(-,+): (3,2)(1,4) → Re=-5, Im=14
        it = new("v1"); it.m_ar = 3;  it.m_ai = 2;  it.m_br = 1; it.m_bi = 4;  seq.push_back(it);
        // Q(-,-): (-3,2)(1,4) → Re=-3-8=-11, Im=-12+2=-10
        it = new("v2"); it.m_ar = -3; it.m_ai = 2;  it.m_br = 1; it.m_bi = 4;  seq.push_back(it);
        // Q(+,-): (-3,-2)(1,4) → Re=-3+8=5, Im=-12-2=-14
        it = new("v3"); it.m_ar = -3; it.m_ai = -2; it.m_br = 1; it.m_bi = 4;  seq.push_back(it);
        // Q(+,+): (3,-2)(1,4) → Re=3+8=11, Im=12-2=10
        it = new("v4"); it.m_ar = 3;  it.m_ai = -2; it.m_br = 1; it.m_bi = 4;  seq.push_back(it);
        // B 虚部为负：(-3,2)(1,-4) → Re=-3*1-2*(-4)=5, Im=(-3)(-4)+2*1=14
        it = new("v5"); it.m_ar = -3; it.m_ai = 2;  it.m_br = 1; it.m_bi = -4; seq.push_back(it);
        // B 实虚均为负：(3,2)(-1,-4) → Re=3*(-1)-2*(-4)=5, Im=3*(-4)+2*(-1)=-14
        it = new("v6"); it.m_ar = 3;  it.m_ai = 2;  it.m_br = -1; it.m_bi = -4; seq.push_back(it);
        drive_seq(seq);
        `TB_CASE_END("TC3: cm_neg", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_CM_NEG
