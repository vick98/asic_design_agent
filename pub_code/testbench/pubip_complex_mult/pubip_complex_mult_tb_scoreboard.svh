/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             逐拍比对复数实/虚部 + X 态检查
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 计分板：FIFO 期望队列入队、逐拍比对 o_dout_re/o_dout_im，
        含 X 态检查与"多余有效输出（期望队列空且 watch=1）"判fail
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_SCOREBOARD
`define U_PUBIP_COMPLEX_MULT_TB_SCOREBOARD

//----------- pubip_complex_mult_scoreboard ------------
class pubip_complex_mult_scoreboard extends tb_scoreboard_base;

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
        pubip_complex_mult_item dut_it;
        pubip_complex_mult_item exp_it;
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
            if (^dut_it.m_out_re === 1'bx || ^dut_it.m_out_im === 1'bx) begin
                `TB_ERROR($sformatf("%s: 输出 X 态 re=%b im=%b",
                                   m_name, dut_it.m_out_re, dut_it.m_out_im));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else if (dut_it.m_out_re !== exp_it.m_exp_re ||
                     dut_it.m_out_im !== exp_it.m_exp_im) begin
                `TB_ERROR($sformatf("%s: FAIL exp=(%0d,%0d) got=(%0d,%0d) A=(%0d,%0d) B=(%0d,%0d)",
                                   m_name, exp_it.m_exp_re, exp_it.m_exp_im,
                                   dut_it.m_out_re, dut_it.m_out_im,
                                   exp_it.m_ar, exp_it.m_ai, exp_it.m_br, exp_it.m_bi));
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
`endif //U_PUBIP_COMPLEX_MULT_TB_SCOREBOARD
