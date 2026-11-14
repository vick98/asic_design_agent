/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             期望由用例侧行为模型预置，compute 无状态透传
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 参考模型：期望由用例侧的逐拍行为模型（pubip_dynamic_mem_model，
        数组+链表思想，见 _tb_model.svh）预置到 item，refm 的 compute() 作无状态纯函数透传。
        偏离说明（相对 rules/tb.md 9.3 节"compute 承载核心计算"）：本模块为带
        状态链表+T0-T1 展示流水线的握手模块，期望值依赖全部历史（数据与状态），无法用
        纯函数表达——期望生成放用例侧（事件/逐拍模型），refm 保持纯函数透传契约
        （差异：唯一被"绕过"的是 compute 的核心计算位置，model()/compute() 结构不变）。
        详见表 3 说明见 tb_handoff_dynamic_mem.md。
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_REFM
`define U_PUBIP_DYNAMIC_MEM_TB_REFM

//----------- pubip_dynamic_mem_refm ------------
class pubip_dynamic_mem_refm extends tb_refm_base;

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 无状态纯函数：期望向量已随激励事务预置，透传返回 ------------
    static function pubip_dynamic_mem_item compute(pubip_dynamic_mem_item in);
        return in;
    endfunction

    //----------- 模型计算：经 compute 透传，广播原事务（期望字段已被用例侧模型预置回填） ------------
    virtual task model(tb_item_base it);
        pubip_dynamic_mem_item dut_it;
        $cast(dut_it, it);
        compute(dut_it);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TB_REFM
