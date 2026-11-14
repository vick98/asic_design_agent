/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_neg_asym.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 neg_asym：负满码（补码负最大值）钳位专项——需求书 §1 补充需求
        1) 源位图上直接给负满码位图 2^(W_dst-1)：输出必须是对称负界 1-2^(W_dst-1)，不得是负满码
        2) 正/负相邻点：负满码 -1（对称负界处）、负满码 +1、0、1 都要正确
        3) 能否在源尺度上构造出"加半右移后恰等于负满码"的激励：能则一并覆盖（N=0 路径必然能）
           说明：N>0 时加半会把 -k*2^N 抬到 -(k*2^N)+2^(N-1)，右移后得 -k*2^N+2^(N-1) 再下取整，
           恰好等于负满码需要 2^(N-1)-1 < 0，不成立；所以该判据真正生效的是 N=0 及其近邻情形，
           这里无论能否构造都显式驱动一遍，保证判据被覆盖而不是被推断掉
        4) 全值域不变量由计分板逐拍检查（输出 === 负满码位图即记 fail）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_NEG_ASYM
`define U_PUBIP_ROUND_TC_NEG_ASYM
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_neg_asym ------------
class pubip_round_tc_neg_asym extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_neg_asym");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        longint neg_asym;
        longint out_unit;
        int     k;
        reset_wait();
        `TB_CASE_BEGIN("TC5: neg_asym 负满码钳位");
        m_env.m_scb.m_enable = 1'b1;
        neg_asym = -(64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1));//负满码数值 -2^(W_dst-1)
        out_unit = 64'sd1 <<< `PUBIP_ROUND_SHIFT            ;//1 个输出整数单位（源 LSB 计）
        // 1) 负满码位图（源容器里直接给这个位图）
        push_value(seq, neg_asym);
        // 2) 负满码邻域：-1（对称负界）、+1、以及更负的一侧
        push_value(seq, neg_asym - out_unit);
        push_value(seq, neg_asym + 1);
        push_value(seq, neg_asym - 1);
        push_value(seq, neg_asym + out_unit);
        // 3) 数值上恰为负满码的所有输出整数单位倍数（k>=2），逐个驱动
        for (k = 2; k <= 4; k = k + 1)
            push_value(seq, neg_asym * k);
        // 4) 构造"加半右移后落在负满码邻域"的源值：x = neg_asym*2^N + half + delta
        //    N=0 时 half=0，x 即负满码位图本身；N>0 时把负满码整点两侧各 1 个 LSB 都驱动一遍
        for (k = -1; k <= 1; k = k + 1)
            push_value(seq, neg_asym * out_unit + (out_unit / 2) + k);
        // 5) 零与最小正值邻域
        push_value(seq, 0);
        push_value(seq, 1);
        push_value(seq, -1);
        drive_seq(seq);
        `TB_CASE_END("TC5: neg_asym 负满码钳位", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_NEG_ASYM
