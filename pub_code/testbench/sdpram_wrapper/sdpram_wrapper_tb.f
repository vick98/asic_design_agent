# sdpram_wrapper_tb.f - sdpram_wrapper 框架式自测平台编译文件清单（绝对路径）
# 由 tb_gen.py 生成，每次运行重新生成（由当前文件集推导）

+incdir+/home/your_account/proj/asic_design_agent/tb_common
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper
+incdir+/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc

/home/your_account/proj/asic_design_agent/tb_common/tb_define.svh
/home/your_account/proj/asic_design_agent/tb_common/tb_clk_rst_if.sv
/home/your_account/proj/asic_design_agent/tb_common/tb_pkg.sv

# ---------- DUT 平台文件（组件经 tb_pkg include，.svh 不单列） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/sdpram_wrapper_if.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/sdpram_wrapper_tb_pkg.sv

# ---------- 用例（tc_base 先于具体用例；factory 先于 sim_top） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_base.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_wr_rd.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_byte_en.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_write_first.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_rand.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_all.sv
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/tc/sdpram_wrapper_tc_factory.svh

# ---------- 仿真顶层（最后编译，引用全部类） ----------
/home/your_account/proj/asic_design_agent/pub_code/testbench/sdpram_wrapper/sdpram_wrapper_sim_top.sv
