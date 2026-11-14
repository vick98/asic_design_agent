/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             逐拍比对 7 个 o_ 信号（数据仅 rd_ready 拍比对，其余全拍比对）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 计分板：FIFO 期望队列入队、逐拍比对 o_wr_ready/o_rd_ready/o_rd_data/
        o_rd_last/o_schd_id/o_schd_id_remain/o_free_cnt，含 X 态检查与"多余有效输出"判 fail
        （o_rd_data 仅在 o_rd_ready=1 拍比对——DUT 就绪无效时数据为 SDPRAM 保持/任意值，不构成规格语义）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_SCOREBOARD
`define U_PUBIP_DYNAMIC_MEM_TB_SCOREBOARD

//----------- pubip_dynamic_mem_scoreboard ------------
class pubip_dynamic_mem_scoreboard extends tb_scoreboard_base;

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
        pubip_dynamic_mem_item dut_it;
        pubip_dynamic_mem_item exp_it;
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
            //----------- 全拍比对：wr_ready / rd_ready / rd_last / schd_id / remain / free_cnt ------------
            if (dut_it.m_out_wr_ready !== exp_it.m_exp_wr_ready ||
                dut_it.m_out_rd_ready !== exp_it.m_exp_rd_ready ||
                dut_it.m_out_rd_last  !== exp_it.m_exp_rd_last  ||
                dut_it.m_out_schd_id  !== exp_it.m_exp_schd_id  ||
                dut_it.m_out_remain   !== exp_it.m_exp_remain   ||
                dut_it.m_out_free_cnt !== exp_it.m_exp_free_cnt) begin
                `TB_ERROR($sformatf("%s: FAIL(ctl) exp=rw%0b/rd%0b/l%0b/id%0d/rm%0d/fc%0d got=rw%0b/rd%0b/l%0b/id%0d/rm%0d/fc%0d",
                                    m_name, exp_it.m_exp_wr_ready, exp_it.m_exp_rd_ready, exp_it.m_exp_rd_last,
                                    exp_it.m_exp_schd_id, exp_it.m_exp_remain, exp_it.m_exp_free_cnt,
                                    dut_it.m_out_wr_ready, dut_it.m_out_rd_ready, dut_it.m_out_rd_last,
                                    dut_it.m_out_schd_id, dut_it.m_out_remain, dut_it.m_out_free_cnt));
                m_fail_cnt = m_fail_cnt + 1;
            end
            //----------- 数据仅 rd_ready=1 拍比对（含 X 态检查） ------------
            else if (dut_it.m_out_rd_ready === 1'b1) begin
                if (^dut_it.m_out_rd_data === 1'bx) begin
                    `TB_ERROR($sformatf("%s: 输出 X 态 rd_data=%0h", m_name, dut_it.m_out_rd_data));
                    m_fail_cnt = m_fail_cnt + 1;
                end
                else if (dut_it.m_out_rd_data !== exp_it.m_exp_rd_data) begin
                    `TB_ERROR($sformatf("%s: FAIL(data) exp=%0h got=%0h", m_name, exp_it.m_exp_rd_data, dut_it.m_out_rd_data));
                    m_fail_cnt = m_fail_cnt + 1;
                end
                else begin
                    m_pass_cnt = m_pass_cnt + 1;
                end
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
`endif //U_PUBIP_DYNAMIC_MEM_TB_SCOREBOARD
