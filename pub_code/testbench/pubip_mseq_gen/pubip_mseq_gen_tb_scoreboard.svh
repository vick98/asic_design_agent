/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 计分板：FIFO 期望队列入队、逐拍比对 o_seq_out（含 X 态检查与队列空判 fail）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_GEN_TB_SCOREBOARD
`define U_PUBIP_MSEQ_GEN_TB_SCOREBOARD

//----------- pubip_mseq_gen_scoreboard ------------
class pubip_mseq_gen_scoreboard extends tb_scoreboard_base;

    tb_item_base                    m_exp_q[$]          ;//期望队列（先进先出）

    function new(string name = "m_scb");
        super.new(name);
    endfunction

    //----------- 期望入队 ------------
    virtual task push_exp(tb_item_base it);
        m_exp_q.push_back(it);
    endtask

    //----------- 采集比对（watch=1 才比对；X 态/数值不等记 fail） ------------
    virtual task check(tb_item_base it);
        pubip_mseq_gen_item dut_it;
        pubip_mseq_gen_item exp_it;
        dut_it = new();
        $cast(dut_it, it);
        if (dut_it.m_watch === 1'b0) return;   // 关闭窗口的采样不比对（保持队列配对）
        if (!m_enable) return;
        if (m_exp_q.size() == 0) begin
            `TB_ERROR($sformatf("%s: 多余有效输出（期望队列空）%s", m_name, dut_it.do_print()));
            m_fail_cnt = m_fail_cnt + 1;
        end
        else begin
            exp_it = new();
            $cast(exp_it, m_exp_q.pop_front());
            if ($isunknown(dut_it.m_out_seq)) begin
                `TB_ERROR($sformatf("%s: 输出 X 态 out=%h (exp=%h)", m_name, dut_it.m_out_seq, exp_it.m_exp_seq));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else if (dut_it.m_out_seq !== exp_it.m_exp_seq) begin
                `TB_ERROR($sformatf("%s: FAIL exp=%h got=%h init=%h cal=%0b",
                                    m_name, exp_it.m_exp_seq, dut_it.m_out_seq,
                                    exp_it.m_init_seq, exp_it.m_cal_en));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else begin
                m_pass_cnt = m_pass_cnt + 1;
            end
        end
    endtask

    //----------- 覆盖：返回内部期望队列大小（防漏比） ------------
    virtual function int pending_count();
        return m_exp_q.size();
    endfunction
endclass
`endif //U_PUBIP_MSEQ_GEN_TB_SCOREBOARD
