# pubip_mseq_cal_tb.f - pubip_mseq_cal 框架式自测平台编译文件清单（绝对路径）
# 由 tb_gen.py 生成，每次运行重新生成（由当前文件集推导）

+incdir+/home/your_account/proj/asic_design_agent/tb_common
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc

/home/your_account/proj/asic_design_agent/tb_common/tb_define.svh
/home/your_account/proj/asic_design_agent/tb_common/tb_clk_rst_if.sv
/home/your_account/proj/asic_design_agent/tb_common/tb_pkg.sv

# ---------- DUT 平台文件（组件经 tb_pkg include，.svh 不单列） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/pubip_mseq_cal_if.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/pubip_mseq_cal_tb_pkg.sv

# ---------- 用例（tc_base 先于具体用例；factory 先于 sim_top） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_base.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_trans0.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_trans1.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_pow2.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_full32767.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_seg1_bound.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_seg2_bound.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_vld_align.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_multi_call.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_cal_random.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_all.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/tc/pubip_mseq_cal_tc_factory.svh

# ---------- 仿真顶层（最后编译，引用全部类） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_cal/pubip_mseq_cal_sim_top.sv
