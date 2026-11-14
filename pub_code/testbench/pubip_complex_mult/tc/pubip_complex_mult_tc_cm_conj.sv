/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_cm_conj.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现共轭用例（需 +define+PUBIP_CM_CONJ 编译）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cm_conj：CONJ_EN=1 A*conj(B) 公式 Re=ar*br+ai*bi、Im=ai*br-ar*bi。
        固定点：B=1+4j → conj(B)=1-4j，A=(3,2) → Re=3+8=11, Im=2-12=-10，另附 100 拍随机。
        注意：需要 sim_top 以 +define+PUBIP_CM_CONJ 编译（CONJ_EN=1 例化），
        本类整体置于宏保护内：未定义该宏时不编译、factory 不注册；不在 tc_all 聚合内，
        单独 +TC=tc_cm_conj 运行
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_CM_CONJ
`define U_PUBIP_COMPLEX_MULT_TC_CM_CONJ
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

`ifdef PUBIP_CM_CONJ
//----------- pubip_complex_mult_tc_cm_conj ------------
class pubip_complex_mult_tc_cm_conj extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_cm_conj");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_item seq[$];
        pubip_complex_mult_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC5: cm_conj");
        m_env.m_scb.m_enable = 1'b1;
        // 固定点：(3,2)(1,4) → conj(B)=1-4j，Re=3+8=11, Im=2-12=-10
        it = new("v0"); it.m_ar = 3; it.m_ai = 2; it.m_br = 1; it.m_bi = 4;  seq.push_back(it);
        // 固定点：(3,2)(1,-4) → conj(B)=1+4j，Re=3*1+2*(-4)=-5, Im=2*1-3*(-4)=14
        it = new("v1"); it.m_ar = 3; it.m_ai = 2; it.m_br = 1; it.m_bi = -4; seq.push_back(it);
        // 固定点：(-3,2)(1,4) → Re=-3+8=5, Im=2*1-(-3)*4=14
        it = new("v2"); it.m_ar = -3; it.m_ai = 2; it.m_br = 1; it.m_bi = 4; seq.push_back(it);
        // 100 拍随机向量：$urandom_range 全码域（种子由 +SEED= 统一控制）
        for (i = 0; i < 100; i = i + 1) begin
            it = new($sformatf("rand%0d", i));
            it.m_ar = $urandom_range(0, 1023);
            it.m_ai = $urandom_range(0, 1023);
            it.m_br = $urandom_range(0, 63);
            it.m_bi = $urandom_range(0, 63);
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC5: cm_conj", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //PUBIP_CM_CONJ
`endif //U_PUBIP_COMPLEX_MULT_TC_CM_CONJ
