/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             期望为用例预置的逐拍向量，compute 作无状态透传
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 参考模型：期望由用例按 DUT 计数语义预置为逐拍向量（每 item 自带），
        compute() 为无状态纯函数透传（框架约定：期望经 model() 调用 compute() 后广播）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_REFM
`define U_PUBIP_COUNTER_TB_REFM

//----------- pubip_counter_refm ------------
class pubip_counter_refm extends tb_refm_base;

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 无状态纯函数：期望向量已随激励事务预置，透传返回 ------------
    static function pubip_counter_item compute(pubip_counter_item in);
        return in;
    endfunction

    //----------- 模型计算：经 compute 透传，广播原事务（期望字段已被用例预置回填） ------------
    virtual task model(tb_item_base it);
        pubip_counter_item dut_it;
        $cast(dut_it, it);
        compute(dut_it);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TB_REFM
