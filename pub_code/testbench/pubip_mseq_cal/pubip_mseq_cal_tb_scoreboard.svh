/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 o_seq_vld 消耗期望（5 拍延迟对齐），vld=0 拍仅 X 检查
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 计分板：期望只入列 m_vld=1 的项（FIFO），采集按 o_seq_vld 消费——
        DUT 输出固定延迟 5 拍（输入锁存 1 拍 + 4 段流水），期望入队无延迟但 vld=0 拍
        不消耗期望，天然错开采样拍与响应拍的 5 拍错位（连续/断续/背靠背流水均成立）
        含 X 态检查与"多余有效输出（期望队列空）"判 fail；pending_count 防漏比
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_CAL_TB_SCOREBOARD
`define U_PUBIP_MSEQ_CAL_TB_SCOREBOARD

//----------- pubip_mseq_cal_scoreboard ------------
class pubip_mseq_cal_scoreboard extends tb_scoreboard_base;

    tb_item_base                    m_exp_q[$]          ;//期望队列（先进先出，仅 vld=1 项）

    function new(string name = "m_scb");
        super.new(name);
    endfunction

    //----------- 期望入队（过滤 vld=0 项：vld=0 无期望输出，不入队以保持 1:1 配对） ------------
    virtual task push_exp(tb_item_base it);
        pubip_mseq_cal_item exp_it;
        $cast(exp_it, it);
        if (exp_it.m_vld === 1'b1) begin
            m_exp_q.push_back(it);
        end
    endtask

    //----------- 采集比对（watch=1 且 vld=1 才消费期望；vld=0 拍仅 X 态检查） ------------
    virtual task check(tb_item_base it);
        pubip_mseq_cal_item dut_it;
        pubip_mseq_cal_item exp_it;
        dut_it = new();
        $cast(dut_it, it);
        if (dut_it.m_watch === 1'b0) return;   // 关闭窗口的采样不比对（复位/非激励时期）
        if (!m_enable) return;
        // X 态检查：vld 与数据（窗口内任一拍均不允许 X）
        if (dut_it.m_out_vld === 1'bx) begin
            `TB_ERROR($sformatf("%s: 输出 vld X 态 out_vld=%0b out=%0h", m_name, dut_it.m_out_vld, dut_it.m_out_seq));
            m_fail_cnt = m_fail_cnt + 1;
            return;
        end
        if (^dut_it.m_out_seq === 1'bx) begin
            `TB_ERROR($sformatf("%s: 输出 seq X 态 out_vld=%0b out=%0h", m_name, dut_it.m_out_vld, dut_it.m_out_seq));
            m_fail_cnt = m_fail_cnt + 1;
            return;
        end
        if (dut_it.m_out_vld === 1'b0) begin
            // 无效拍：数据保持/任意值（en=0 寄存器保持），不比对、不消耗期望
            return;
        end
        // 有效拍：必须消费一个期望（5 拍延迟对齐：期望入队顺序与有效输出顺序一致）
        if (m_exp_q.size() == 0) begin
            `TB_ERROR($sformatf("%s: 多余有效输出（期望队列空）%s", m_name, dut_it.do_print()));
            m_fail_cnt = m_fail_cnt + 1;
            return;
        end
        exp_it = new();
        $cast(exp_it, m_exp_q.pop_front());
        if (dut_it.m_out_seq !== exp_it.m_exp_seq) begin
            `TB_ERROR($sformatf("%s: FAIL txn=%0h init=%0h exp=%0h got=%0h",
                                m_name, exp_it.m_trans_num, exp_it.m_init_seq,
                                exp_it.m_exp_seq, dut_it.m_out_seq));
            m_fail_cnt = m_fail_cnt + 1;
        end
        else begin
            m_pass_cnt = m_pass_cnt + 1;
        end
    endtask

    //----------- 覆盖：返回内部期望队列大小（防漏比：DUT 漏输出时期望残留计 fail） ------------
    virtual function int pending_count();
        return m_exp_q.size();
    endfunction
endclass
`endif //U_PUBIP_MSEQ_CAL_TB_SCOREBOARD
