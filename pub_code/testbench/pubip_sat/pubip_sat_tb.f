# pubip_sat_tb.f - pubip_sat 框架式自测平台编译文件清单（绝对路径）
# 由 tb_gen.py 生成，每次运行重新生成（由当前文件集推导）

+incdir+/home/your_account/proj/asic_design_agent/tb_common
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc

/home/your_account/proj/asic_design_agent/tb_common/tb_define.svh
/home/your_account/proj/asic_design_agent/tb_common/tb_clk_rst_if.sv
/home/your_account/proj/asic_design_agent/tb_common/tb_pkg.sv

# ---------- 参数宏中心（编译宏变体选择，先于 if/pkg） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/pubip_sat_cfg.svh

# ---------- DUT 平台文件（组件经 tb_pkg include，.svh 不单列） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/pubip_sat_if.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/pubip_sat_tb_pkg.sv

# ---------- 用例（tc_base 先于具体用例；factory 先于 sim_top） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_base.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_down_align.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_neg.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_ovf_pos.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_ovf_neg.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_zero_protect.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_random.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_expand.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_sat_unsigned.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_all.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/tc/pubip_sat_tc_factory.svh

# ---------- 仿真顶层（最后编译，引用全部类） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_sat/pubip_sat_sim_top.sv
