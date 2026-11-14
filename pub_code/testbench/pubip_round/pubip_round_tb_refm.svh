/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 参考模型：无状态纯函数 compute() 按"定点值语义"独立实现参考公式
        （补码位图 -> 有符号整数 -> 加半个 LSB -> 算术右移 -> 对称饱和 -> 输出位图），
        与 RTL 的"位图 + 阈值判据"实现不同路径；
        覆写 model() 回填期望字段（框架硬约定，只实现 compute 不覆写 model 会漏回填）
        同公式的仓库侧对照：`python3 script/framework.py fx finish <W,I,t> --dest <W,I,t> --n N`
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_ROUND_TB_REFM
`define U_PUBIP_ROUND_TB_REFM

//----------- pubip_round_refm ------------
class pubip_round_refm extends tb_refm_base;

    //----------- 定点参数（由 cfg 编译宏展开，保证与 DUT 参数一致） ------------
    localparam int L_IN_FRAC  = `PUBIP_ROUND_F_SRC   ;//输入小数位宽 f_src
    localparam int L_OUT_FRAC = `PUBIP_ROUND_F_DST   ;//输出小数位宽 f_dst
    localparam int L_SHIFT    = `PUBIP_ROUND_SHIFT   ;//右移位数 N（闭合式复算）
    //v1.1：界常量用 64 位有符号承载——W_dst > 32 时 32 位 int 会溢出成 -1（PUBIP_ROUND_Z4）
    localparam longint signed L_NEG_SYM  = `PUBIP_ROUND_NEG_SYM ;//对称负饱和界 1-2^(W-1)
    localparam longint signed L_POS_SYM  = `PUBIP_ROUND_POS_MAX ;//对称正饱和界 2^(W-1)-1
    localparam longint signed L_NEG_ASYM = `PUBIP_ROUND_NEG_ASYM;//负满码 -2^(W-1)，禁止输出

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（无状态：相同输入必得相同输出，不读写类成员/时间） ------------
    // 参考公式（值语义，独立于 RTL 位图实现）：
    //   1) 补码位图 -> 有符号整数（0.5 LSB 边界向正方向取整由"加半后下取整"展开）
    //   2) N=0 不加不移；N>0 先加 2^(N-1) 再算术右移 N 位
    //   3) 对称饱和到 [1-2^(W-1), 2^(W-1)-1]：低于对称负界的（含负满码）一律钳到对称负界
    //   4) 取低 W 位作为输出位图（目标更宽时高位补 0）
    static function logic [`PUBIP_ROUND_OUT_TOTAL - 1 : 0] compute(input logic [`PUBIP_ROUND_IN_TOTAL - 1 : 0] in_data);
        longint signed              sv_val      ;//输入有符号值
        longint signed              sv_rounded  ;//加半并右移后的值
        logic [`PUBIP_ROUND_OUT_TOTAL - 1 : 0]  uv_neg_sym;//对称负饱和输出位图
        logic [`PUBIP_ROUND_OUT_TOTAL - 1 : 0]  uv_pos_sym;//对称正饱和输出位图

        uv_neg_sym = `PUBIP_ROUND_OUT_TOTAL'(L_NEG_SYM);
        uv_pos_sym = `PUBIP_ROUND_OUT_TOTAL'(L_POS_SYM);

        //1) 补码位图 -> 有符号值
        sv_val = $signed(in_data);

        //2) half-up：先加半个 LSB 再算术右移（N=0 时两个动作都不做）
        if (L_SHIFT > 0)
            sv_rounded = (sv_val + (64'sd1 <<< (L_SHIFT - 1))) >>> L_SHIFT;
        else
            sv_rounded = sv_val;

        //3) 对称饱和 + 负满码钳位（值语义下 L_NEG_ASYM < L_NEG_SYM，由同一条下界判据覆盖）
        if (sv_rounded > L_POS_SYM)
            compute = uv_pos_sym;
        else if (sv_rounded < L_NEG_SYM)
            compute = uv_neg_sym;
        //4) 界内：取低 W 位（目标更宽时高位补 0）
        else
            compute = `PUBIP_ROUND_OUT_TOTAL'(sv_rounded);

        //参考模型自检：无论走哪条分支，输出都不得是补码负最大值
        if (compute == `PUBIP_ROUND_OUT_TOTAL'(L_NEG_ASYM))
            `TB_ERROR($sformatf("refm: 参考模型输出负满码 in=%h out=%h", in_data, compute));
    endfunction

    //----------- 模型计算：调用 compute 回填期望字段（基类 run() 随后统一广播） ------------
    virtual task model(tb_item_base it);
        pubip_round_item dut_it;
        $cast(dut_it, it);
        dut_it.m_exp = compute(dut_it.m_data);
    endtask
endclass
`endif //U_PUBIP_ROUND_TB_REFM
