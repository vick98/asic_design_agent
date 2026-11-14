# pubip_mseq_gen_tb.f - pubip_mseq_gen 框架式自测平台编译文件清单（绝对路径）
# 由 tb_gen.py 生成，每次运行重新生成（由当前文件集推导）

+incdir+/home/your_account/proj/asic_design_agent/tb_common
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc

/home/your_account/proj/asic_design_agent/tb_common/tb_define.svh
/home/your_account/proj/asic_design_agent/tb_common/tb_clk_rst_if.sv
/home/your_account/proj/asic_design_agent/tb_common/tb_pkg.sv

# ---------- 参数宏中心（编译宏变体选择，先于 if/pkg） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/pubip_mseq_gen_cfg.svh

# ---------- DUT 平台文件（组件经 tb_pkg include，.svh 不单列） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/pubip_mseq_gen_if.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/pubip_mseq_gen_tb_pkg.sv

# ---------- 用例（tc_base 先于具体用例；factory 先于 sim_top） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_base.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_mseq_trans1.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_mseq_trans_n.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_mseq_border.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_mseq_random.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_all.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/tc/pubip_mseq_gen_tc_factory.svh

# ---------- 仿真顶层（最后编译，引用全部类） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_mseq_gen/pubip_mseq_gen_sim_top.sv
