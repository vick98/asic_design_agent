/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 参考模型：无状态纯函数 compute() 逐拍迭代独立 LFSR 参考实现
        （逐位抽头奇偶校验 + 右移反馈），与 RTL 综合期转移矩阵展开的实现路径不同；
        覆写 model() 回填期望字段（框架硬约定，只实现 compute 不覆写 model 会漏回填）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_GEN_TB_REFM
`define U_PUBIP_MSEQ_GEN_TB_REFM

//----------- pubip_mseq_gen_refm ------------
class pubip_mseq_gen_refm extends tb_refm_base;

    //----------- LFSR 参数（由 cfg 编译宏展开，保证与 DUT 参数一致） ------------
    localparam int                         L_SEQ_WIDTH = `PUBIP_MPG_SEQ_WIDTH ;//序列位宽（LFSR 级数）
    localparam logic [30 : 0]              L_CAL_RULE  = `PUBIP_MPG_CAL_RULE  ;//反馈多项式抽头掩码（位宽固定 31，与 RTL 参数声明一致）
    localparam int                         L_TRANS_NUM = `PUBIP_MPG_TRANS_NUM;//单次跨越步数

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（无状态：相同输入必得相同输出，不读写类成员/时间） ------------
    // 独立 LFSR 参考模型（逐拍迭代语义，与 RTL 矩阵化展开不同路径）：
    //   1) 每步反馈位 fb = 抽头位奇偶校验（CAL_RULE bit k = x^k 项，k 取 0..SEQ_WIDTH-1）
    //   2) 状态右移、fb 填入最高位：state = {fb, state[SEQ_WIDTH-1:1]}
    //   3) 迭代 L_TRANS_NUM 步后：i_cal_en=1 输出最终状态，i_cal_en=0 旁路 i_init_seq
    static function logic [L_SEQ_WIDTH - 1 : 0] compute(input logic [L_SEQ_WIDTH - 1 : 0] init_seq,
                                                        input bit cal_en);
        logic [L_SEQ_WIDTH - 1 : 0]  state;      //当前 LFSR 状态
        bit                          fb;         //反馈位（抽头奇偶校验）
        int                          step;       //步数下标
        int                          k;          //抽头位下标

        state = init_seq;
        for (step = 0; step < L_TRANS_NUM; step = step + 1) begin
            fb = 1'b0;
            for (k = 0; k < L_SEQ_WIDTH; k = k + 1) begin
                if ((L_CAL_RULE[k] == 1'b1) && (state[k] == 1'b1))
                    fb = fb ^ 1'b1;              //逐位抽头奇偶校验（等效 ^(CAL_RULE & state)）
            end
            state = {fb, state[L_SEQ_WIDTH - 1 : 1]};
        end
        return (cal_en ? state : init_seq);
    endfunction

    //----------- 模型计算：调用 compute 回填期望字段（基类 run() 随后统一广播） ------------
    virtual task model(tb_item_base it);
        pubip_mseq_gen_item dut_it;
        $cast(dut_it, it);
        dut_it.m_exp_seq = compute(dut_it.m_init_seq, dut_it.m_cal_en);
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TB_REFM
