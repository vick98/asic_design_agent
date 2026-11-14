/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             逐拍比对期望/采集（en/count/shift + X 态检查）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 计分板：FIFO 期望队列入队、逐拍比对 o_cnt_en/o_counter/o_cnt_shift，
        含 X 态检查与"多余有效输出（期望队列空且 watch=1）"判fail
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_SCOREBOARD
`define U_PUBIP_COUNTER_TB_SCOREBOARD

//----------- pubip_counter_scoreboard ------------
class pubip_counter_scoreboard extends tb_scoreboard_base;

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
        pubip_counter_item dut_it;
        pubip_counter_item exp_it;
        dut_it = new();
        $cast(dut_it, it);
        if (dut_it.m_watch === 1'b0) return;   // 复位/关闭窗口的采样不比对（保持队列配对）
        if (!m_enable) return;
        if (m_exp_q.size() == 0) begin
            `TB_ERROR($sformatf("%s: 多余有效输出（期望队列空）%s", m_name, dut_it.do_print()));
            m_fail_cnt = m_fail_cnt + 1;
        end
        else begin
            exp_it = new();
            $cast(exp_it, m_exp_q.pop_front());
            if (dut_it.m_out_cnt === 'x || dut_it.m_out_shift === 'x) begin
                `TB_ERROR($sformatf("%s: 输出 X 态 en=%0b cnt=%0h shift=%0h",
                                   m_name, dut_it.m_out_en, dut_it.m_out_cnt, dut_it.m_out_shift));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else if (dut_it.m_out_en !== exp_it.m_exp_en ||
                     dut_it.m_out_cnt !== exp_it.m_exp_cnt ||
                     dut_it.m_out_shift !== exp_it.m_exp_shift) begin
                `TB_ERROR($sformatf("%s: FAIL exp=%0b/%0h/%0h got=%0b/%0h/%0h",
                                   m_name, exp_it.m_exp_en, exp_it.m_exp_cnt, exp_it.m_exp_shift,
                                   dut_it.m_out_en, dut_it.m_out_cnt, dut_it.m_out_shift));
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
`endif //U_PUBIP_COUNTER_TB_SCOREBOARD
