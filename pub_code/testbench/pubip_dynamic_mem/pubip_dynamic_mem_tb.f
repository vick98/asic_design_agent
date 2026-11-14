# pubip_dynamic_mem_tb.f - pubip_dynamic_mem 框架式自测平台编译文件清单（绝对路径）
# 由 tb_gen.py 生成，每次运行重新生成（由当前文件集推导）

+incdir+/home/your_account/proj/asic_design_agent/tb_common
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc

/home/your_account/proj/asic_design_agent/tb_common/tb_define.svh
/home/your_account/proj/asic_design_agent/tb_common/tb_clk_rst_if.sv
/home/your_account/proj/asic_design_agent/tb_common/tb_pkg.sv

# ---------- DUT 平台文件（组件经 tb_pkg include，.svh 不单列） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/pubip_dynamic_mem_if.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/pubip_dynamic_mem_tb_pkg.sv

# ---------- 用例（tc_base 先于具体用例；factory 先于 sim_top） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_base.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_wr_rd.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_multi_id.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_full_depth.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_rd_last.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_conflict.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_remain.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_random.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_all.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/tc/pubip_dynamic_mem_tc_factory.svh

# ---------- 仿真顶层（最后编译，引用全部类） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/pubip_dynamic_mem/pubip_dynamic_mem_sim_top.sv
