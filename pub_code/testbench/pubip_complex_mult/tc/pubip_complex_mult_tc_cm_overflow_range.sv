/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_cm_overflow_range.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现最大幅值/边界用例（16bit 输出位宽内数值正确）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cm_overflow_range：常数项最大幅值与边界值。主测点 A=511+511j, B=31+31j
        → Re=15841-15841=0, Im=15841+15841=31682（16bit 有符号最大值 32767 之内）；
        附 A 取 10bit 最小值 -512、B 取 6bit 边界 -32/31 的组合向量。
        期望由 refm.compute 公式回填（精确算术后截取 16bit，与 RTL 回绕语义一致）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_CM_OVERFLOW_RANGE
`define U_PUBIP_COMPLEX_MULT_TC_CM_OVERFLOW_RANGE
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_cm_overflow_range ------------
class pubip_complex_mult_tc_cm_overflow_range extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_cm_overflow_range");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_item seq[$];
        pubip_complex_mult_item it;
        reset_wait();
        `TB_CASE_BEGIN("TC4: cm_overflow_range");
        m_env.m_scb.m_enable = 1'b1;
        // 主测点（最大幅值正数）：(511,511)(31,31) → Re=0, Im=31682（16bit 内）
        it = new("v1"); it.m_ar = 511;  it.m_ai = 511;  it.m_br = 31;  it.m_bi = 31;   seq.push_back(it);
        // 负向最大组合：(-512,-512)(31,31) → Re=(-512)*31-(-512)*31=0, Im=-31744
        it = new("v2"); it.m_ar = -512; it.m_ai = -512; it.m_br = 31;  it.m_bi = 31;   seq.push_back(it);
        // B 取负：(-512,-512)(-32,-32) → Re=16384-16384=0, Im=16384+16384=32768 超出16bit → 回绕 -32768
        it = new("v3"); it.m_ar = -512; it.m_ai = -512; it.m_br = -32; it.m_bi = -32;  seq.push_back(it);
        // 实部最大正值：(511,-511)(31,-31) → Re=15841-15841=0, Im=511*(-31)+(-511)*31=-31744
        it = new("v4"); it.m_ar = 511;  it.m_ai = -511; it.m_br = 31;  it.m_bi = -31;  seq.push_back(it);
        // 实部取大：(511,511)(31,-31) → Re=15841+15841=31682, Im=511*(-31)+511*31=0
        it = new("v5"); it.m_ar = 511;  it.m_ai = 511;  it.m_br = 31;  it.m_bi = -31;  seq.push_back(it);
        // 边界组合：(-512,511)(-32,31) → Re=16384-15841=543, Im=(-512)*31+511*(-32)=-32224
        it = new("v6"); it.m_ar = -512; it.m_ai = 511;  it.m_br = -32; it.m_bi = 31;   seq.push_back(it);
        drive_seq(seq);
        `TB_CASE_END("TC4: cm_overflow_range", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_CM_OVERFLOW_RANGE
