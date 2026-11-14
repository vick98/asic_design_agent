/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_clamp_check.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 clamp_check：负满码钳位的**自检**用例（不依赖 refm，独立在用例里算闭式）
        遍历源位图全值域，对每个 x 用闭式算出"舍入后的数值"，判定：
          - 舍入值恰为负满码 -2^(W_dst-1) 时，RTL 输出必须等于对称负界 1-2^(W_dst-1)
          - 其余情况输出不得等于负满码位图（全值域不变量）
        闭式（half-up）：N=0 时 y=x；N>0 时 y=(x + 2^(N-1)) >>> N（算术右移，负数向负无穷）
        与 refm 的值语义公式同源但**独立实现**（用例内直接算，不复用 refm.compute）
        W_src > 16 的变体不遍历全值域，改为构造负满码邻域与随机抽样
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_CLAMP_CHECK
`define U_PUBIP_ROUND_TC_CLAMP_CHECK
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_clamp_check ------------
class pubip_round_tc_clamp_check extends pubip_round_tc_base;

    int m_clamp_hits  = 0;//负满码钳位实际触发次数（0 说明这条判据没被覆盖）
    int m_dut_fail    = 0;//DUT 违反判据次数

    function new(string name = "pubip_round_tc_clamp_check");
        super.new(name);
    endfunction

    //----------- 闭式：源位图 -> 舍入后的有符号数值 ------------
    function longint rounded_value(input logic [`PUBIP_ROUND_IN_TOTAL - 1 : 0] bits);
        longint sv;
        sv = $signed(bits);
        if (`PUBIP_ROUND_SHIFT > 0)
            return (sv + (64'sd1 <<< (`PUBIP_ROUND_SHIFT - 1))) >>> `PUBIP_ROUND_SHIFT;
        else
            return sv;
    endfunction

    //----------- 逐拍激励 + 施加判据（复用基类序列与驱动时序） ------------
    task check_value(input longint value);
        pubip_round_item seq[$];
        longint y;
        logic [`PUBIP_ROUND_OUT_TOTAL - 1 : 0] exp_out;
        push_value(seq, value);
        drive_seq(seq);
        y = rounded_value(bits_of(value));
        if (y == `PUBIP_ROUND_NEG_ASYM) begin
            //负满码：必须钳到对称负界
            m_clamp_hits = m_clamp_hits + 1;
            exp_out = `PUBIP_ROUND_OUT_TOTAL'(`PUBIP_ROUND_NEG_SYM);
            if (m_dut_if.o_data !== exp_out) begin
                m_dut_fail = m_dut_fail + 1;
                `TB_ERROR($sformatf("clamp_check: 负满码未钳位 in=%h y=%0d got=%h exp=%h",
                                    bits_of(value), y, m_dut_if.o_data, exp_out));
            end
        end
        //全值域不变量：输出任何时刻都不得是负满码位图
        if (m_dut_if.o_data === `PUBIP_ROUND_OUT_TOTAL'(`PUBIP_ROUND_NEG_ASYM)) begin
            m_dut_fail = m_dut_fail + 1;
            `TB_ERROR($sformatf("clamp_check: 输出负满码 in=%h y=%0d out=%h",
                                bits_of(value), y, m_dut_if.o_data));
        end
    endtask

    //----------- 批量驱动：构造序列 + 驱动（判据由计分板与 clamp 统计各管一段） ------------
    virtual task body();
        longint i;
        longint neg_asym;
        longint half;
        int     k;
        reset_wait();
        `TB_CASE_BEGIN("TC8: clamp_check 负满码钳位自检");
        m_env.m_scb.m_enable = 1'b1;
        neg_asym = `PUBIP_ROUND_NEG_ASYM          ;//负满码
        half     = (`PUBIP_ROUND_SHIFT > 0) ? (64'sd1 <<< (`PUBIP_ROUND_SHIFT - 1)) : 0;//半个 LSB
        if (`PUBIP_ROUND_IN_TOTAL <= 16) begin
            //小位宽：全值域逐个过判据
            for (i = 0; i < (64'sd1 << `PUBIP_ROUND_IN_TOTAL); i = i + 1)
                check_value(i);
        end
        else begin
            //大位宽：负满码整点邻域 + 饱和界邻域 + 随机抽样
            for (k = -2; k <= 2; k = k + 1) begin
                check_value(neg_asym + k * (64'sd1 <<< `PUBIP_ROUND_SHIFT));
                check_value(neg_asym + k * (64'sd1 <<< `PUBIP_ROUND_SHIFT) + half);
            end
            push_half_boundary_clamp();
            for (i = 0; i < 5000; i = i + 1)
                check_value({$urandom(), $urandom()});
        end
        //无论走哪一档分支：大位宽变体下也把"加半后落在负满码邻域"的源点驱动一遍
        check_value(neg_asym);
        check_value(neg_asym - 1);
        check_value(neg_asym + 1);
        `TB_INFO($sformatf("clamp_check: 负满码钳位触发 %0d 次，DUT 违反 %0d 次",
                           m_clamp_hits, m_dut_fail));
        if (m_dut_fail != 0)
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + m_dut_fail;
        `TB_CASE_END("TC8: clamp_check 负满码钳位自检", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask

    //----------- 负满码整点邻域批量驱动（大位宽分支用） ------------
    task push_half_boundary_clamp();
        pubip_round_item seq[$];
        longint out_unit;
        longint pos_sym;
        int     k;
        out_unit = 64'sd1 <<< `PUBIP_ROUND_SHIFT;
        pos_sym  = (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) - 1;
        for (k = -2; k <= 2; k = k + 1) begin
            push_value(seq, pos_sym * out_unit + k);
            push_value(seq, -pos_sym * out_unit + k);
            push_value(seq, (pos_sym + 1) * out_unit + k);
        end
        drive_seq(seq);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_CLAMP_CHECK
