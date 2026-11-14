/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             独立 LFSR 参考实现（复用 mseq_gen 单步迭代语义）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 参考模型：无状态纯函数 compute() 按 LFSR 单步迭代语义独立实现
        （state = {^(CAL_RULE & state), state[30:1]}，迭代 trans_num 次），与 RTL
        的 A^(2^k) 常量矩阵 + 15 级二进制加权转移链实现路径完全不同；
        覆写 model() 回填期望字段（框架硬约定：只实现 compute() 不覆写 model() 会漏回填）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_CAL_TB_REFM
`define U_PUBIP_MSEQ_CAL_TB_REFM

//----------- pubip_mseq_cal_refm ------------
// 期望 = 初始序列经 LFSR 迭代 i_trans_num 次（与 DUT 默认参数 CAL_RULE=31'h9/SEQ_WIDTH=31 一致）
class pubip_mseq_cal_refm extends tb_refm_base;

    //----------- 参考模型参数（与 DUT 默认例化参数一致，内部 15 级转移链固定） ------------
    localparam logic [30:0]       L_CAL_RULE  = 31'h9   ;//LFSR 反馈多项式（本原多项式）

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（无状态：相同输入必得相同输出，不读写类成员/时间） ------------
    // 参考语义（独立于 RTL 的 A^(2^k) 矩阵实现）：
    //   对 state 反复迭代 i_trans_num 次单步转移：
    //     step: state = {^(L_CAL_RULE & state), state[30:1]}   （反馈 bit 移入 MSB，右移 1 位）
    //   i_trans_num=0 直接返回 init_seq（对应全部 i_cal_en=0 的旁路场景）
    static function logic [30:0] compute(input logic [30:0] init_seq,
                                         input logic [14:0] trans_num);
        logic [30:0] state;
        int          step;
        state = init_seq;
        for (step = 0; step < int'(trans_num); step = step + 1) begin
            state = {^(L_CAL_RULE & state), state[30:1]};
        end
        compute = state;
    endfunction

    //----------- 模型计算：调用 compute 回填期望字段（基类 run() 随后统一广播） ------------
    virtual task model(tb_item_base it);
        pubip_mseq_cal_item dut_it;
        $cast(dut_it, it);
        if (dut_it.m_vld) begin
            dut_it.m_exp_seq = compute(dut_it.m_init_seq, dut_it.m_trans_num);
        end
        else begin
            dut_it.m_exp_seq = '0;   // 无效拍期望置 0（scoreboard 按 m_vld 过滤，不入期望队列）
        end
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TB_REFM
