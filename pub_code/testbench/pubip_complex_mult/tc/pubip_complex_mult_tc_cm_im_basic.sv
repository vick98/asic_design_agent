/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_cm_im_basic.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现虚部基本运算用例（固定点 + 300 随机向量）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cm_im_basic：CONJ_EN=0 虚部公式 Im=ar*bi+ai*br。固定点 A=3+2j, B=1+4j
        → Im=3*4+2*1=14；随后 300 拍 $urandom_range 随机向量（A 10bit 全码域、B 6bit 全码域）
        期望由 refm.compute 公式回填（独立于 RTL 实现的参考公式）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_CM_IM_BASIC
`define U_PUBIP_COMPLEX_MULT_TC_CM_IM_BASIC
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_cm_im_basic ------------
class pubip_complex_mult_tc_cm_im_basic extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_cm_im_basic");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_item seq[$];
        pubip_complex_mult_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC2: cm_im_basic");
        m_env.m_scb.m_enable = 1'b1;
        // 固定点：(3,2)(1,4) → Im=3*4+2*1=14, Re=3*1-2*4=-5
        it = new("v0"); it.m_ar = 3; it.m_ai = 2; it.m_br = 1; it.m_bi = 4; seq.push_back(it);
        // 300 拍随机向量：$urandom_range 覆盖输入 2 的补码全码域（种子由 +SEED= 统一控制）：
        //   A 10bit 有效值域 -512..511（$urandom_range(0,1023) 逐 bit 均匀），B 6bit 域 -32..31
        for (i = 0; i < 300; i = i + 1) begin
            it = new($sformatf("rand%0d", i));
            it.m_ar = $urandom_range(0, 1023);
            it.m_ai = $urandom_range(0, 1023);
            it.m_br = $urandom_range(0, 63);
            it.m_bi = $urandom_range(0, 63);
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC2: cm_im_basic", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_CM_IM_BASIC
