@nLint rc file Version 1.0
[RuleVersion]
Version = 20130.03

[Groups]
1 = "nLint"
2 = "RMM"
3 = "IPQ Design Guidelines"

[Default]
Default = nLint

[nLint.21001]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.21003]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.21005]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.21007]
vhdl_val="16"
vlog_val="16"
[nLint.21009]
vhdl_val="16"
vlog_val="16"
[nLint.21011]
vhdl_val="16"
vlog_val="16"
[nLint.21013]
vhdl_val="PREFIX","clk_"
vlog_val="PREFIX","clk_"
[nLint.21014]
vhdl_val="SUFFIX","_lat"
vlog_val="SUFFIX","_lat"
[nLint.21015]
vhdl_val="PREFIX","rst_"
vlog_val="PREFIX","rst_"
[nLint.21017]
vhdl_val="PREFIX","set_"
vlog_val="PREFIX","set_"
[nLint.21019]
vhdl_val="SUFFIX","_cs"
vlog_val="SUFFIX","_cs"
[nLint.21020]
vhdl_val="SUFFIX","_n"
vlog_val="SUFFIX","_n"
[nLint.21021]
vhdl_val="SUFFIX","_p"
vlog_val="SUFFIX","_p"
[nLint.21022]
vhdl_val="TRUE,RESET_LOW,rst_.*_n;FALSE,RESET_HIGH, rst_.*_p;TRUE,SET_LOW,set_.*_n; TRUE,SET_HIGH,set_.*_p; FALSE, LATCH_ENABLE_LOW; FALSE,LATCH_ENABLE_HIGH; FALSE,TRI_ENABLE_LOW; FALSE,TRI_ENABLE_HIGH"
vlog_val="TRUE,RESET_LOW,rst_.*_n;FALSE,RESET_HIGH, rst_.*_p;TRUE,SET_LOW,set_.*_n; TRUE,SET_HIGH,set_.*_p; FALSE, LATCH_ENABLE_LOW; FALSE,LATCH_ENABLE_HIGH; FALSE,TRI_ENABLE_LOW; FALSE,TRI_ENABLE_HIGH"
[nLint.21023]
vhdl_val="ZERO_BOUND","DOWN_TO"
vlog_val="ZERO_BOUND","DOWN_TO"
[nLint.21025]
vlog_val="IGNORE_LIB_CELL"
[nLint.21027]
vhdl_val="SUFFIX","_r"
vlog_val="SUFFIX","_r"
[nLint.21029]
vhdl_val="SUFFIX","_a"
vlog_val="SUFFIX","_a"
[nLint.21031]
vhdl_val="SUFFIX","_z"
vlog_val="SUFFIX","_z"
[nLint.21035]
vhdl_val="SUFFIX","_nxt"
vlog_val="SUFFIX","_nxt"
[nLint.21041]
vhdl_val="CASE_UPPER"
vlog_val="CASE_UPPER"
[nLint.21043]
vhdl_val="CHECK_ALL_MODULE"
vlog_val="CHECK_ALL_MODULE"
[nLint.21045]
vhdl_val="8","3"
vlog_val="8","3"
[nLint.21047]
vlog_val="O,0;I,1,l"
[nLint.21049]
vhdl_val="SUFFIX","_PROC"
vlog_val="SUFFIX","_PROC"
[nLint.21050]
vhdl_val=""
vlog_val="INITIAL, ALWAYS, ALWAYS_COMB, ALWAYS_FF, ALWAYS_LATCH, GENERATE, IF"
[nLint.21051]
vhdl_val="PREFIX","U_"
vlog_val="PREFIX","U_"
[nLint.21053]
vlog_val="PREFIX","gate_"
[nLint.21057]
vhdl_val="PREFIX"
vlog_val="PREFIX"
[nLint.22001]
vhdl_val="IGNORE_FLOATING","IGNORE_TRISTATE"
vlog_val="IGNORE_FLOATING","IGNORE_TRISTATE"
[nLint.22002]
[nLint.22003]
vhdl_val="LHS_GE_RHS","VAR_GE_CON"
vlog_val="LHS_GE_RHS","VAR_GE_CON"
[nLint.22004]
vhdl_val="VAR_GE_CON"
vlog_val="VAR_GE_CON"
[nLint.22005]
vhdl_val="CONSTANT"
vlog_val="CONSTANT"
[nLint.22007]
vhdl_val="INPUT,OUTPUT"
vlog_val="INPUT,OUTPUT"
[nLint.22009]
[nLint.22011]
vhdl_val="SYNC"
vlog_val="SYNC"
[nLint.22012]
vhdl_val="VAR_EQ_CON"
vlog_val="VAR_EQ_CON"
[nLint.22014]
vhdl_val="FALSE"
vlog_val="FALSE"
[nLint.22019]
[nLint.22025]
vhdl_val="80"
vlog_val="80"
[nLint.22026]
[nLint.22027]
vhdl_val="2","FIRST_INDENT,BEGIN_INDENT"
vlog_val="2","FIRST_INDENT,BEGIN_INDENT"
[nLint.22029]
vhdl_val="CHECK_WHOLE"
vlog_val="CHECK_WHOLE"
[nLint.22033]
vhdl_val="FALSE","INPUT, OUTPUT, INOUT, BUFFER, LINKAGE"
vlog_val="FALSE","INPUT, OUTPUT, INOUT, BUFFER, LINKAGE"
[nLint.22035]
vhdl_val="INPUT, OUTPUT, INOUT, BUFFER, LINKAGE","CLOCK, RESET, SET, ENABLE, TE, CONTROL"
vlog_val="INPUT, OUTPUT, INOUT, BUFFER, LINKAGE","CLOCK, RESET, SET, ENABLE, TE, CONTROL"
[nLint.22038]
vhdl_val="IGNORE_COMMENT"
vlog_val="IGNORE_COMMENT"
[nLint.22041]
vlog_val="IGNORE_ANSI_PORT"
[nLint.22043]
vhdl_val="MODULE"
vlog_val="MODULE"
[nLint.22049]
vhdl_val="ENTITY,ARCHITECTURE"
vlog_val="ENTITY,ARCHITECTURE"
[nLint.22051]
vlog_val="PASS_THROUGH_BUFFER_ASSIGNMENT, PASS_THROUGH_EVEN_INVERTERS"
[nLint.22052]
vlog_val="PASS_THROUGH_BUFFER_ASSIGNMENT, PASS_THROUGH_EVEN_INVERTERS"
[nLint.22056]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22057]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22059]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22061]
vhdl_val="CHECK_TYPE_DETAIL"
vlog_val="CHECK_TYPE_DETAIL"
[nLint.22075]
[nLint.22079]
vhdl_val="IGNORE_PARAMETER"
vlog_val="IGNORE_PARAMETER"
[nLint.22082]
vhdl_val="INPUT,OUTPUT,INOUT"
vlog_val="INPUT,OUTPUT,INOUT"
[nLint.22083]
vhdl_val="32"
vlog_val="32"
[nLint.22084]
vlog_val="DEF_GE_VAL"
[nLint.22089]
[nLint.22091]
[nLint.22101]
[nLint.22103]
[nLint.22104]
vhdl_val="VAR_GE_CON"
vlog_val="VAR_GE_CON"
[nLint.22105]
vhdl_val=""
vlog_val=""
[nLint.22106]
vlog_val="VAR_GE_CON"
[nLint.22107]
[nLint.22112]
[nLint.22113]
[nLint.22117]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22139]
[nLint.22151]
[nLint.22152]
[nLint.22155]
vhdl_val=""
vlog_val=""
[nLint.22161]
vlog_val="CHECK_ALL"
[nLint.22165]
vhdl_val="CHECK_ALL"
vlog_val="CHECK_ALL"
[nLint.22167]
[nLint.22168]
[nLint.22169]
[nLint.22177]
[nLint.22179]
[nLint.22194]
vlog_val="1000"
[nLint.22203]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22204]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22205]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22209]
vhdl_val="IGNORE_ADDR"
vlog_val="IGNORE_ADDR"
[nLint.22211]
[nLint.22213]
[nLint.22217]
[nLint.22218]
[nLint.22219]
[nLint.22225]
vhdl_val="TRUE"
vlog_val="TRUE"
[nLint.22227]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22228]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.22235]
[nLint.22239]
vhdl_val="IGNORE_CONSTCASEEXPR"
vlog_val="IGNORE_CONSTCASEEXPR"
[nLint.22243]
[nLint.22247]
vlog_val="IGNORE_DEPEND"
[nLint.22249]
vlog_val="VAR_GE_CON","ORIG_MUL_WIDTH"
[nLint.22250]
[nLint.22255]
vhdl_val="BOTH","CHECK_VOIDFUNC"
vlog_val="BOTH","CHECK_VOIDFUNC"
[nLint.22265]
vlog_val="VAR_GE_CON"
[nLint.22267]
vlog_val="IGNORE_INCRDECR"
[nLint.22269]
vhdl_val="SYNC","30"
vlog_val="SYNC","30"
[nLint.22271]
vhdl_val="10"
vlog_val="10"
[nLint.22273]
[nLint.22275]
[nLint.22277]
[nLint.22279]
vhdl_val="INPUT,OUTPUT,INOUT"
vlog_val="INPUT,OUTPUT,INOUT"
[nLint.22281]
vlog_val="INPUT,OUTPUT,INOUT"
[nLint.22283]
vlog_val="INPUT,OUTPUT,INOUT"
[nLint.22301]
vlog_val="IGNORE_CONST_RHS","ORIG_MUL_WIDTH"
[nLint.22303]
vlog_val="LHS_GE_RHS","VAR_EQ_CON"
[nLint.23001]
vhdl_val="IGNORE_IN_COMB"
vlog_val="IGNORE_IN_COMB"
[nLint.23002]
vhdl_val="REGISTER,LATCH,MEMORY,COUNTER"
vlog_val="REGISTER,LATCH,MEMORY,COUNTER"
[nLint.23003]
vhdl_val="FALSE"
vlog_val="FALSE"
[nLint.23006]
[nLint.23007]
vlog_val="IGNORE_IN_SEQ","FOLLOW_FULL_CASE_DIRECTIVE"
[nLint.23008]
vlog_val="IGNORE_IN_SEQ"
[nLint.23009]
[nLint.23010]
[nLint.23011]
[nLint.23013]
vhdl_val="BOTH","IGNORE_PART_SEL"
vlog_val="BOTH","IGNORE_PART_SEL"
[nLint.23015]
vlog_val="BLOCKING","REG_INFER_ASSIGN"
[nLint.23016]
vlog_val="NONBLOCKING","FALSE"
[nLint.23017]
vhdl_val="CHECK_BOTH"
vlog_val="CHECK_BOTH"
[nLint.23021]
vlog_val="NON_LEAF",""
[nLint.23027]
vhdl_val="IGNORE_SUBPROG"
vlog_val="IGNORE_SUBPROG"
[nLint.23031]
vhdl_val="IGNORE_CASEEQ"
vlog_val="IGNORE_CASEEQ"
[nLint.23033]
vlog_val="CONSTANT"
[nLint.23042]
vhdl_val="CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE"
vlog_val="CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE"
[nLint.23043]
vhdl_val="CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE"
vlog_val="CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE"
[nLint.23044]
vhdl_val="LATCH_ENABLE,TRI_ENABLE"
vlog_val="LATCH_ENABLE,TRI_ENABLE"
[nLint.23121]
vhdl_val="BOTH"
vlog_val="BOTH"
[nLint.23122]
vhdl_val="IGNORE_NOTFULL"
vlog_val="IGNORE_NOTFULL"
[nLint.23123]
vhdl_val="BOTH","IGNORE_MULTI_CHOICE"
vlog_val="BOTH","IGNORE_MULTI_CHOICE"
[nLint.23131]
vlog_val="IGNORE_DEFAULT"
[nLint.23401]
[nLint.23405]
[nLint.23407]
[nLint.23409]
[nLint.24007]
vlog_val="CHECK_ALL"
[nLint.24013]
vlog_val="IFDEF,IFNDEF"
[nLint.24015]
vhdl_val="synopsys,translate_off,translate_on,parallel_case,full_case,state_vector,enum,template,dc_script_begin, dc_script_end,map_to_module,return_port_name,sync_set_reset,async_set_reset,async_set_reset_local,sync_set_reset_local, async_set_reset_local_all,sync_set_reset_local_all,one_hot,one_cold"
vlog_val="synopsys,translate_off,translate_on,parallel_case,full_case,state_vector,enum,template,dc_script_begin, dc_script_end,map_to_module,return_port_name,sync_set_reset,async_set_reset,async_set_reset_local,sync_set_reset_local, async_set_reset_local_all,sync_set_reset_local_all,one_hot,one_cold"
[nLint.25001]
vhdl_val="CHECK_PART_SEL,IGNORE_INITIALVALUE,CHECK_TOP_SIGNAL"
vlog_val="CHECK_PART_SEL,IGNORE_INITIALVALUE,CHECK_TOP_SIGNAL"
[nLint.25003]
vhdl_val="CHECK_TOP_SIGNAL,CHECK_THROUGH_HIERARCHY"
vlog_val="CHECK_TOP_SIGNAL,CHECK_THROUGH_HIERARCHY"
[nLint.25005]
vlog_val="BOTH"
[nLint.25007]
vlog_val=""
[nLint.25009]
vhdl_val="10","CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE, SCAN_ENABLE"
vlog_val="10","CLOCK,RESET,SET,LATCH_ENABLE,TRI_ENABLE, SCAN_ENABLE"
[nLint.25011]
vhdl_val="10"
vlog_val="10"
[nLint.25013]
vhdl_val="10"
vlog_val="10"
[nLint.25014]
[nLint.26001]
vlog_val="1024"
[nLint.26009]
[nLint.26015]
vlog_val="8096"
[nLint.27007]
vhdl_val="CASE_LOWER"
[nLint.27015]
vhdl_val="vhd"
vlog_val="v"
[nLint.27028]
vhdl_val=""
vlog_val=""
[nLint.27055]
vhdl_val="1000"
vlog_val="1000"
[nLint.27063]
vhdl_val="CASE_UPPER"
[nLint.27083]
vhdl_val="RESOLVED"
[nLint.27105]
vhdl_val="DELAYED,STABLE,QUIET,TRANSACTION"
[nLint.27122]
vlog_val="IGNORE_IN_SEQ"
[nLint.27125]
vhdl_val="CHECK_REF_ONLY"
vlog_val="CHECK_REF_ONLY"
[nLint.27126]
vhdl_val="CHECK_REF_ONLY"
vlog_val="CHECK_REF_ONLY"
[nLint.27130]
vlog_val="NONBLOCKING","CHECK_INITASS"
[nLint.27131]
vlog_val="NONBLOCKING"
[nLint.27163]
vhdl_val=""
[nLint.27201]
vhdl_val="3","16"
[nLint.27203]
vhdl_val="CASE_LOWER"
[nLint.27205]
vhdl_val="SUFFIX","_ety"
[nLint.27209]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27211]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27213]
vhdl_val="SUFFIX","_arch"
vlog_val="SUFFIX","_module"
[nLint.27217]
vhdl_val="3","16"
[nLint.27219]
vhdl_val="CASE_LOWER"
[nLint.27221]
vhdl_val="SUFFIX","_pkg"
[nLint.27225]
vhdl_val="3","16"
[nLint.27227]
vhdl_val="CASE_LOWER"
[nLint.27229]
vhdl_val="SUFFIX","_cfg"
[nLint.27233]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27235]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27241]
vhdl_val="3","16"
[nLint.27245]
vhdl_val="PREFIX","com_"
[nLint.27249]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27251]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27257]
vhdl_val="3","16"
[nLint.27259]
vhdl_val="CASE_LOWER"
[nLint.27261]
vhdl_val="PREFIX","c_"
[nLint.27265]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27267]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27269]
vhdl_val="SUFFIX","_typ"
vlog_val="SUFFIX","_typ"
[nLint.27273]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27277]
vhdl_val="PREFIX","g_"
vlog_val="PREFIX","p_"
[nLint.27285]
vhdl_val="PREFIX","s_"
vlog_val="PREFIX","s_"
[nLint.27287]
vlog_val="var_.*"
[nLint.27288]
vlog_val="3","16"
[nLint.27289]
vlog_val=".*_fld"
[nLint.27290]
vlog_val="3","16"
[nLint.27293]
vhdl_val="PREFIX","v_"
vlog_val="PREFIX","v_"
[nLint.27297]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27299]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27301]
vhdl_val="PREFIX","f_"
vlog_val="PREFIX","f_"
[nLint.27305]
vhdl_val="3","16"
vlog_val="3","16"
[nLint.27307]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
[nLint.27309]
vhdl_val="PREFIX","p_"
vlog_val="PREFIX","p_"
[nLint.27313]
vhdl_val="3","16"
[nLint.27315]
vhdl_val="CASE_LOWER"
[nLint.27317]
vhdl_val="PREFIX","blk_"
[nLint.27321]
vhdl_val="3","16"
[nLint.27325]
vhdl_val="PREFIX","attr_"
[nLint.27329]
vlog_val="NET_DECL"
[nLint.27337]
vlog_val="CHECK_FULL_CASE"
[nLint.27338]
vlog_val="IGNORE_SIGNED_POSITIVE_CONST"
[nLint.27339]
vlog_val="CHECK_ALL"
[nLint.27349]
vlog_val="END"
[nLint.27351]
vhdl_val="UNARY_PLUS, UNARY_MINUS, MULTIPLY, DIVIDE, MOD, POWER"
vlog_val="UNARY_PLUS, UNARY_MINUS, MULTIPLY, DIVIDE, MOD, POWER"
[nLint.27353]
vlog_val=""
[nLint.27355]
vlog_val="INPUT_SIGNAL_TO_OUTPUT_PORT"
[nLint.27363]
vlog_val="IGNORE_GENERATEFOR"
[nLint.27365]
vlog_val="CASEX"
[nLint.27371]
vhdl_val="parallel_case,full_case"
vlog_val="parallel_case,full_case"
[nLint.27373]
vhdl_val="SUFFIX","_ns"
vlog_val="SUFFIX","_ns"
[nLint.27375]
vhdl_val=".*"
vlog_val=".*"
[nLint.27381]
vhdl_val="IGNORE_TIE_LOW_HIGH"
vlog_val="IGNORE_TIE_LOW_HIGH"
[nLint.27391]
vlog_val="logic"
[nLint.27393]
vlog_val="logic"
[nLint.27394]
vlog_val="logic"
[nLint.27395]
vlog_val="my_bit,bit,logic;"
[nLint.27399]
vhdl_val="--sync"
vlog_val="//sync"
[nLint.27412]
vlog_val="40"
[nLint.27415]
vlog_val="D1"
[nLint.27421]
vlog_val="CHECK_ALL"
[nLint.27423]
vlog_val="IGNORE_DEFAULT"
[nLint.27425]
[nLint.27427]
[nLint.27533]
[nLint.27664]
vlog_val="16"
[nLint.27668]
vlog_val="8"
[nLint.27671]
vlog_val="3"
[nLint.27672]
vlog_val="32"
[nLint.27673]
vlog_val="IGNORE_TEMPVAR"
[nLint.27807]
vlog_val="IGNORE_NOT_FULL_RET"
[nLint.27827]
vlog_val="ALL"
[nLint.27829]
vlog_val="CHECK_ALWAYS_LATCH, CHECK_ALWAYS_FF,CHECK_ALWAYS_COMB"
[nLint.29004]
vlog_val=".*GTECH.*"
[nLint.29005]
vlog_val="3"
[nLint.29006]
vlog_val="2"
[nLint.29108]
vlog_val="always,assign,initial,specify,function,task"
[nLint.29112]
vlog_val="BitNegOp, EqOp, NotEqOp"
[nLint.29804]
vlog_val="200"
[nLint.29815]
vlog_val="CHECK_CONDEXPR"
[nLint.29821]
vlog_val="m190c_list.txt"
[nLint.29822]
vlog_val="m190c_list.txt"


[nLint.include]
1 = "Simulation" Enable
2 = "Synthesis" Enable
3 = "DFT" Enable
4 = "ERC" Enable
5 = "Design Style" Enable
6 = "Language Construct" Enable
7 = "HDL Translation" Enable
8 = "Coding Style" Disable
9 = "Naming Convention" Disable
10 = "VITAL Compliant" Disable
11 = "Clock" Enable
12 = "Block Interconnect" Enable
13 = "CTS" Disable

[nLint.Simulation]
22005 =  Enable Enable
22006 =  Enable NONE
22009 =  Enable NONE
22011 =  Enable Enable
22013 =  Disable Disable
22014 =  Disable Disable
22016 =  Disable NONE
22018 =  Disable NONE
22019 =  Enable NONE
22024 =  Disable NONE
22026 =  Disable NONE
22079 =  Enable Enable
22082 =  Disable Disable
22083 =  Disable Disable
22085 =  Enable Enable
22089 =  Enable NONE
22091 =  Disable NONE
22109 =  Disable NONE
22112 =  Enable NONE
22113 =  Enable Enable
22115 =  Disable NONE
22139 =  Enable NONE
22151 =  Enable NONE
22169 =  Enable Enable
22179 =  Enable Enable
22187 =  Disable NONE
22195 =  Disable Disable
22217 =  Disable NONE
22235 =  Disable Disable
22243 =  Enable NONE
22247 =  Disable NONE
22269 =  Disable Disable
22271 =  Disable Disable
22279 =  Disable Disable
22281 =  Disable NONE
22283 =  Disable NONE
23008 =  Disable NONE
23011 =  Enable Enable
23013 =  Disable Disable
23028 =  Disable NONE
23029 =  Disable Disable
23030 =  Disable Disable
23123 =  Enable Enable
23125 =  Disable NONE
23131 =  Disable NONE
27003 =  Disable Disable
27071 =  NONE Disable
27099 =  NONE Disable
27101 =  NONE Disable
27105 =  NONE Disable
27109 =  NONE Disable
27111 =  NONE Disable
27115 =  NONE Disable
27123 =  Disable Disable
27125 =  Disable Disable
27127 =  Disable Disable
27335 =  Disable Disable
27337 =  Disable NONE
27550 =  NONE Disable
27573 =  NONE Disable
27661 =  Disable Disable
27662 =  Disable NONE
27672 =  Disable NONE
27673 =  Disable NONE
27676 =  Disable NONE
27805 =  Disable NONE
27821 =  Disable NONE
29807 =  Disable NONE

[nLint.Synthesis]
22019 =  Enable NONE
22075 =  Disable NONE
22077 =  Disable NONE
22083 =  Disable Disable
22119 =  Enable NONE
22121 =  Disable NONE
22177 =  Enable NONE
22193 =  Disable NONE
22194 =  Disable NONE
22207 =  Disable NONE
22211 =  Enable Enable
22213 =  Enable Enable
22218 =  Disable NONE
22239 =  Enable Enable
22247 =  Disable NONE
23001 =  Disable Disable
23002 =  Disable Disable
23003 =  Enable Enable
23004 =  Disable Disable
23005 =  Enable Enable
23008 =  Disable NONE
23011 =  Enable Enable
23015 =  Enable NONE
23016 =  Enable NONE
23017 =  Disable Disable
23021 =  Disable NONE
23025 =  Disable Disable
23026 =  Disable NONE
23027 =  Disable Disable
23031 =  Enable Enable
23033 =  Disable NONE
23034 =  Disable NONE
23035 =  Disable NONE
23037 =  Enable NONE
23039 =  Disable Disable
23042 =  Disable Disable
23043 =  Disable Disable
23044 =  Disable Disable
23045 =  Disable NONE
23047 =  Disable Disable
23049 =  Disable NONE
23050 =  Disable NONE
23051 =  Disable NONE
23053 =  Disable NONE
23055 =  Disable NONE
23057 =  Disable NONE
23059 =  Disable NONE
23061 =  Disable NONE
23065 =  Disable NONE
23069 =  Enable NONE
23071 =  Disable Disable
23073 =  Disable NONE
23075 =  Disable NONE
23077 =  Disable NONE
23079 =  Disable NONE
23083 =  Disable NONE
23087 =  Disable NONE
23089 =  Disable NONE
23091 =  Disable NONE
23095 =  Disable NONE
23097 =  Disable NONE
23099 =  Disable NONE
23101 =  Disable NONE
23103 =  Disable NONE
23105 =  Disable NONE
23107 =  Disable NONE
23109 =  Disable NONE
23115 =  Disable NONE
23117 =  Disable NONE
23119 =  Disable NONE
23123 =  Enable Enable
23125 =  Disable NONE
23127 =  Disable NONE
23129 =  Disable NONE
23133 =  Enable NONE
23135 =  Disable NONE
23137 =  Enable NONE
24017 =  Disable NONE
27081 =  NONE Disable
27083 =  NONE Disable
27107 =  NONE Disable
27122 =  Disable NONE
27123 =  Disable Disable
27126 =  Disable Disable
27128 =  Disable Disable
27181 =  NONE Disable
27335 =  Disable Disable
27337 =  Disable NONE
27505 =  NONE Disable
27507 =  NONE Disable
27509 =  NONE Disable
27515 =  NONE Disable
27517 =  NONE Disable
27518 =  NONE Disable
27519 =  NONE Disable
27521 =  NONE Disable
27522 =  NONE Disable
27523 =  NONE Disable
27524 =  Disable Disable
27525 =  NONE Disable
27529 =  NONE Disable
27531 =  NONE Disable
27533 =  NONE Disable
27535 =  NONE Disable
27536 =  NONE Disable
27537 =  NONE Disable
27539 =  NONE Disable
27541 =  NONE Disable
27543 =  NONE Disable
27545 =  NONE Disable
27549 =  NONE Disable
27550 =  NONE Disable
27551 =  NONE Disable
27553 =  NONE Disable
27557 =  NONE Disable
27559 =  NONE Disable
27561 =  NONE Disable
27563 =  NONE Disable
27565 =  NONE Disable
27567 =  NONE Disable
27571 =  NONE Disable
27573 =  NONE Disable
27575 =  NONE Disable
27577 =  NONE Disable
27581 =  NONE Disable
27585 =  NONE Disable
27587 =  NONE Disable
27589 =  NONE Disable
27595 =  NONE Disable
27597 =  NONE Disable
27598 =  NONE Disable
27599 =  NONE Disable
27601 =  NONE Disable
27605 =  NONE Disable
27609 =  NONE Disable
27610 =  NONE Disable
27613 =  NONE Disable
27615 =  NONE Disable
27617 =  NONE Disable
27619 =  NONE Disable
27621 =  NONE Disable
27623 =  NONE Disable
27625 =  NONE Disable
27627 =  NONE Disable
27629 =  NONE Disable
27631 =  NONE Disable
27633 =  NONE Disable
27635 =  NONE Disable
27639 =  NONE Disable
27641 =  NONE Disable
27643 =  NONE Disable
27645 =  NONE Disable
27649 =  NONE Disable
27651 =  NONE Disable
27653 =  NONE Disable
27655 =  NONE Disable
27657 =  NONE Disable
27661 =  Disable Disable
27662 =  Disable NONE
27663 =  NONE Disable
27664 =  Disable NONE
27667 =  Disable NONE
27668 =  Disable NONE
27669 =  Disable NONE
27670 =  Disable NONE
27671 =  Disable NONE
27674 =  Disable NONE
27676 =  Disable NONE
27801 =  Disable NONE
27803 =  Disable NONE
27805 =  Disable NONE
27813 =  Disable NONE
27821 =  Disable NONE
27823 =  Disable NONE
27825 =  Disable NONE
27829 =  Disable NONE
29112 =  Disable NONE
29113 =  Disable NONE
29115 =  Disable NONE
29116 =  Disable NONE
29118 =  Disable NONE
29201 =  Disable NONE
29810 =  Disable NONE
29818 =  Disable NONE
29819 =  Disable NONE
29820 =  Disable NONE
29821 =  Disable NONE
29822 =  Disable NONE
29823 =  Disable NONE

[nLint.DFT]
22001 =  Enable Enable
22002 =  Disable Disable
22007 =  Disable Disable
22008 =  Enable NONE
22011 =  Enable Enable
22013 =  Disable Disable
22014 =  Disable Disable
22020 =  Disable Disable
22053 =  Enable Enable
22054 =  Disable Disable
22055 =  Disable Disable
22056 =  Disable Disable
22057 =  Disable Disable
22058 =  Disable Disable
22059 =  Disable Disable
22127 =  Enable Enable
22128 =  Disable Disable
22129 =  Enable Enable
22130 =  Enable Enable
22131 =  Disable Disable
22132 =  Disable Disable
22134 =  Disable NONE
22181 =  Disable Disable
22203 =  Disable Disable
22204 =  Disable Disable
22205 =  Disable Disable
22227 =  Disable Disable
22228 =  Disable Disable
22229 =  Enable Enable
22231 =  Enable Enable
22269 =  Disable Disable
22271 =  Disable Disable
25001 =  Enable Enable
25003 =  Enable Enable
25014 =  Disable NONE
27381 =  Disable Disable
27383 =  Disable Disable
27385 =  Disable Disable
27387 =  Disable Disable

[nLint.ERC]
23401 =  Disable NONE
23405 =  Enable NONE
23407 =  Enable NONE
23409 =  Disable NONE

[nLint.Design Style]
22001 =  Enable Enable
22002 =  Disable Disable
22007 =  Disable Disable
22008 =  Enable NONE
22010 =  Disable Disable
22011 =  Enable Enable
22013 =  Disable Disable
22014 =  Disable Disable
22017 =  Enable Enable
22045 =  Disable NONE
22053 =  Enable Enable
22054 =  Disable Disable
22055 =  Disable Disable
22056 =  Disable Disable
22057 =  Disable Disable
22058 =  Disable Disable
22059 =  Disable Disable
22061 =  Disable Disable
22063 =  Enable Enable
22067 =  Disable Disable
22097 =  Disable NONE
22105 =  Disable Disable
22117 =  Disable Disable
22118 =  Disable NONE
22120 =  Disable NONE
22122 =  Disable NONE
22123 =  Disable NONE
22124 =  Disable NONE
22126 =  Disable NONE
22131 =  Disable Disable
22149 =  Disable Disable
22152 =  Disable NONE
22153 =  Disable NONE
22159 =  Disable Disable
22167 =  Disable Disable
22168 =  Disable NONE
22175 =  Disable Disable
22176 =  Disable Disable
22181 =  Disable Disable
22201 =  Disable Disable
22203 =  Disable Disable
22204 =  Disable Disable
22205 =  Disable Disable
22221 =  Disable Disable
22223 =  Disable Disable
22225 =  Enable Enable
22227 =  Disable Disable
22228 =  Disable Disable
22229 =  Enable Enable
22231 =  Enable Enable
22233 =  Disable Disable
22252 =  Disable NONE
22254 =  Disable NONE
22261 =  Disable Disable
22263 =  Enable NONE
22269 =  Disable Disable
22271 =  Disable Disable
22273 =  Disable Disable
22275 =  Disable Disable
22277 =  Disable Disable
23001 =  Disable Disable
23035 =  Disable NONE
23037 =  Enable NONE
23042 =  Disable Disable
23043 =  Disable Disable
23044 =  Disable Disable
23121 =  Disable Disable
23122 =  Disable Disable
25001 =  Enable Enable
25003 =  Enable Enable
25005 =  Disable NONE
25007 =  Disable NONE
25009 =  Disable Disable
25011 =  Disable Disable
25013 =  Disable Disable
25015 =  Disable Disable
25016 =  Disable Disable
25017 =  Disable NONE
27327 =  NONE Disable
27328 =  Disable NONE
27329 =  Disable NONE
27331 =  NONE Disable
27341 =  NONE Disable
27343 =  Disable NONE
27359 =  Disable NONE
27361 =  Disable Disable
27369 =  Disable Disable
27401 =  Disable Disable
27413 =  Disable Disable
27417 =  Disable Disable
27421 =  Disable NONE
27423 =  Disable NONE
27425 =  Disable NONE
27427 =  Disable NONE
27827 =  Disable NONE
29108 =  Disable NONE
29114 =  Disable NONE
29802 =  Disable NONE
29803 =  Disable NONE
29808 =  Disable NONE
29809 =  Disable NONE
29813 =  Disable NONE
29814 =  Disable NONE
29815 =  Disable NONE
29816 =  Disable NONE
29817 =  Disable NONE

[nLint.Language Construct]
22003 =  Enable Enable
22004 =  Enable Enable
22005 =  Enable Enable
22006 =  Enable NONE
22009 =  Enable NONE
22012 =  Enable Enable
22015 =  Disable NONE
22018 =  Disable NONE
22019 =  Enable NONE
22022 =  Disable NONE
22024 =  Disable NONE
22026 =  Disable NONE
22083 =  Disable Disable
22084 =  Disable NONE
22085 =  Enable Enable
22089 =  Enable NONE
22091 =  Disable NONE
22098 =  Disable NONE
22101 =  Disable NONE
22103 =  Enable NONE
22104 =  Disable Disable
22106 =  Disable NONE
22109 =  Disable NONE
22119 =  Enable NONE
22121 =  Disable NONE
22125 =  Disable NONE
22139 =  Enable NONE
22151 =  Enable NONE
22155 =  Enable Enable
22157 =  Enable Enable
22165 =  Enable Enable
22169 =  Enable Enable
22187 =  Disable NONE
22199 =  Disable NONE
22209 =  Enable Enable
22210 =  Disable NONE
22219 =  Enable NONE
22220 =  Disable NONE
22243 =  Enable NONE
22249 =  Enable NONE
22250 =  Disable NONE
22251 =  Enable NONE
22255 =  Enable Enable
22259 =  Disable NONE
22265 =  Enable NONE
22267 =  Disable NONE
22268 =  Disable NONE
22301 =  Disable NONE
22303 =  Disable NONE
23006 =  Disable NONE
23007 =  Enable NONE
23010 =  Disable NONE
23028 =  Disable NONE
23029 =  Disable Disable
23030 =  Disable Disable
23031 =  Enable Enable
24011 =  Disable NONE
24013 =  Disable NONE
24015 =  Disable Disable
24019 =  Disable Disable
24021 =  Disable NONE
26001 =  Disable NONE
26003 =  Disable NONE
26005 =  Disable NONE
26007 =  Disable NONE
26009 =  Disable NONE
26011 =  Disable NONE
26013 =  Disable NONE
26015 =  Disable NONE
27333 =  Disable NONE
27345 =  Disable NONE
27665 =  Disable NONE
29805 =  Disable NONE
29806 =  Disable NONE
29807 =  Disable NONE

[nLint.HDL Translation]
24001 =  Disable NONE
24003 =  NONE Disable
24005 =  Disable NONE
24007 =  Enable NONE
24011 =  Disable NONE
24013 =  Disable NONE
27143 =  NONE Disable
27144 =  NONE Disable

[nLint.Coding Style]
21023 =  Enable Enable
21043 =  Disable Disable
21044 =  Disable Disable
22021 =  Disable Disable
22023 =  Disable Disable
22025 =  Disable Disable
22027 =  Disable Disable
22029 =  Disable Disable
22031 =  Disable Disable
22032 =  Disable Disable
22033 =  Disable Disable
22035 =  Disable Disable
22038 =  Disable Disable
22039 =  Disable Disable
22041 =  Disable NONE
22043 =  Enable Enable
22044 =  Disable Disable
22049 =  Disable Disable
22107 =  Disable NONE
22108 =  Disable NONE
22161 =  Disable NONE
22163 =  Disable NONE
22246 =  Disable NONE
22306 =  Disable NONE
23009 =  Disable NONE
24009 =  Disable Disable
27001 =  NONE Disable
27027 =  NONE Disable
27028 =  Disable Disable
27029 =  NONE Disable
27031 =  NONE Disable
27033 =  NONE Disable
27035 =  NONE Disable
27037 =  NONE Disable
27039 =  NONE Disable
27041 =  NONE Disable
27043 =  NONE Disable
27044 =  NONE Disable
27045 =  NONE Disable
27047 =  NONE Disable
27049 =  NONE Disable
27051 =  NONE Disable
27055 =  Disable Disable
27069 =  NONE Disable
27071 =  NONE Disable
27077 =  NONE Disable
27081 =  NONE Disable
27083 =  NONE Disable
27085 =  NONE Disable
27093 =  NONE Disable
27095 =  NONE Disable
27099 =  NONE Disable
27101 =  NONE Disable
27105 =  NONE Disable
27107 =  NONE Disable
27109 =  NONE Disable
27111 =  NONE Disable
27115 =  NONE Disable
27119 =  NONE Disable
27124 =  NONE Disable
27130 =  Disable NONE
27131 =  Disable NONE
27143 =  NONE Disable
27144 =  NONE Disable
27338 =  Disable NONE
27339 =  Disable NONE
27347 =  Disable Disable
27349 =  Disable NONE
27351 =  Disable Disable
27353 =  Disable NONE
27357 =  Disable NONE
27363 =  Disable NONE
27365 =  Disable NONE
27367 =  Disable NONE
27371 =  Disable Disable
27377 =  Enable Enable
27379 =  Disable NONE
27389 =  Disable NONE
27391 =  Disable NONE
27393 =  Disable NONE
27394 =  Disable NONE
27395 =  Disable NONE
27397 =  Disable NONE
27399 =  Disable Disable
27411 =  Disable NONE
27412 =  Disable NONE
27675 =  Disable NONE
27807 =  Disable NONE
27815 =  Disable NONE
27817 =  Disable NONE
27819 =  Disable NONE
29003 =  Disable NONE
29005 =  Disable NONE
29006 =  Disable NONE
29100 =  Disable NONE
29103 =  Disable NONE
29801 =  Disable NONE
29804 =  Disable NONE
29811 =  Disable NONE
29812 =  Disable NONE

[nLint.Naming Convention]
21001 =  Disable Disable
21003 =  Disable Disable
21005 =  Disable Disable
21007 =  Disable Disable
21009 =  Disable Disable
21011 =  Disable Disable
21013 =  Disable Disable
21014 =  Disable Disable
21015 =  Disable Disable
21017 =  Disable Disable
21019 =  Disable Disable
21020 =  Disable Disable
21021 =  Disable Disable
21022 =  Disable Disable
21025 =  Disable NONE
21027 =  Disable Disable
21029 =  Disable Disable
21031 =  Disable Disable
21035 =  Disable Disable
21041 =  Disable Disable
21045 =  Disable Disable
21047 =  Disable NONE
21049 =  Disable Disable
21050 =  Disable Disable
21051 =  Disable Disable
21052 =  Disable NONE
21053 =  Disable NONE
21055 =  Disable NONE
21057 =  Disable Disable
24007 =  Enable NONE
27007 =  NONE Disable
27015 =  Disable Disable
27063 =  NONE Disable
27201 =  NONE Disable
27203 =  NONE Disable
27205 =  NONE Disable
27209 =  Disable Disable
27211 =  Disable Disable
27213 =  Disable Disable
27217 =  NONE Disable
27219 =  NONE Disable
27221 =  NONE Disable
27225 =  NONE Disable
27227 =  NONE Disable
27229 =  NONE Disable
27233 =  Disable Disable
27235 =  Disable Disable
27241 =  NONE Disable
27245 =  NONE Disable
27249 =  Disable Disable
27251 =  Disable Disable
27257 =  NONE Disable
27259 =  NONE Disable
27261 =  NONE Disable
27265 =  Disable Disable
27267 =  Disable Disable
27269 =  Disable Disable
27273 =  Disable Disable
27277 =  Disable Disable
27285 =  Disable Disable
27287 =  Disable NONE
27288 =  Disable NONE
27289 =  Disable NONE
27290 =  Disable NONE
27293 =  Disable Disable
27297 =  Disable Disable
27299 =  Disable Disable
27301 =  Disable Disable
27305 =  Disable Disable
27307 =  Disable Disable
27309 =  Disable Disable
27313 =  NONE Disable
27315 =  NONE Disable
27317 =  NONE Disable
27321 =  NONE Disable
27325 =  NONE Disable
27373 =  Disable Disable
27375 =  Disable Disable
27415 =  Disable NONE
29002 =  Disable NONE
29004 =  Disable NONE

[nLint.VITAL Compliant]
27155 =  NONE Enable
27159 =  NONE Disable
27163 =  NONE Disable

[nLint.Clock]
22051 =  Disable NONE
22052 =  Disable NONE
22130 =  Enable Enable
22133 =  Disable NONE
27419 =  Disable Disable
28009 =  Disable Disable
28011 =  Disable Disable
28015 =  Disable Disable

[nLint.Block Interconnect]
27355 =  Enable NONE
27356 =  Disable NONE

[nLint.CTS]
25019 =  Disable NONE
25021 =  Disable NONE

[RMM.21001]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
vlog_indexname = "5.2.1-G1-1"
vhdl_indexname = "5.2.1-G1-1"
vhdl_description = "Use lowercase letters for all signal names"
vlog_description = "Use lowercase letters for all signal names"
[RMM.21003]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
vlog_indexname = "5.2.1-G1-2"
vhdl_indexname = "5.2.1-G1-2"
vhdl_description = "Use lowercase letters for all variable names"
vlog_description = "Use lowercase letters for all variable names"
[RMM.21005]
vhdl_val="CASE_LOWER"
vlog_val="CASE_LOWER"
vlog_indexname = "5.2.1-G1-3"
vhdl_indexname = "5.2.1-G1-3"
vhdl_description = "Use lowercase letters for all port names"
vlog_description = "Use lowercase letters for all port names"
[RMM.21013]
vhdl_val="PREFIX","\"clk_\""
vlog_val="PREFIX","\"clk_\""
vlog_indexname = "5.2.1-G5"
vhdl_indexname = "5.2.1-G5"
vhdl_description = "User the name clk or prefix clk for the clock signals."
vlog_description = "User the name clk or prefix clk for the clock signals."
[RMM.21015]
vlog_indexname = "5.2.1-G9"
vhdl_indexname = "5.2.1-G9"
vhdl_description = "Name or prefix rst used for reset signals"
vlog_description = "Name or prefix rst used for reset signals"
[RMM.21020]
vlog_indexname = "5.2.1-G7"
vhdl_indexname = "5.2.1-G7"
vhdl_description = "For active low signal, end the signal name with an underscore followed by a lowercase character"
vlog_description = "For active low signal, end the signal name with an underscore followed by a lowercase character"
[RMM.21023]
vhdl_val="ZERO_BOUND","DOWN_TO"
vlog_val="ZERO_BOUND","DOWN_TO"
vlog_indexname = "5.2.1-G10"
vhdl_indexname = "5.2.1-G10"
vhdl_description = "Use desending bit order with zero bound in range declaration"
vlog_description = "Use desending bit order with zero bound in range declaration"
[RMM.21025]
vlog_indexname = "5.2.1-G11"
vlog_description = "Same name or similar names, for ports and signals that are connected."
[RMM.21027]
vlog_indexname = "5.2.1-G12-5"
vhdl_indexname = "5.2.1-G12-5"
vhdl_description = "use suffix '_r' for register output signal name"
vlog_description = "use suffix '_r' for register output signal name"
[RMM.21029]
vhdl_val="SUFFIX","_a"
vlog_val="SUFFIX","_a"
vlog_indexname = "5.2.1-G12-1"
vhdl_indexname = "5.2.1-G12-1"
vhdl_description = "use suffix '_a' for asynchronous signal name"
vlog_description = "use suffix '_a' for asynchronous signal name"
[RMM.21031]
vlog_indexname = "5.2.1-G12-2"
vhdl_indexname = "5.2.1-G12-2"
vhdl_description = "use suffix '_z' for tri-state internal signal name"
vlog_description = "use suffix '_z' for tri-state internal signal name"
[RMM.21035]
vlog_indexname = "5.2.1-G12-4"
vhdl_indexname = "5.2.1-G12-4"
vhdl_description = "use suffix '_nxt' for the name of data before being registered"
vlog_description = "use suffix '_nxt' for the name of data before being registered"
[RMM.21041]
vhdl_val="CASE_UPPER"
vlog_val="CASE_UPPER"
vlog_indexname = "5.2.1-G2-1"
vhdl_indexname = "5.2.1-G2-1"
vhdl_description = "Use uppercase letters for names of GENERIC"
vlog_description = "Use uppercase letters for names of parameter"
[RMM.21049]
vhdl_val="SUFFIX","\"_PROC\""
vlog_val="SUFFIX","\"_PROC\""
vlog_indexname = "5.2.15.G1"
vhdl_indexname = "5.2.15.G1"
vhdl_description = "Each process block labeled <name>_PROC"
vlog_description = "Each process block labeled <name>_PROC"
[RMM.21050]
vlog_indexname = "5.2.15-R1"
vhdl_indexname = "5.2.15-R1"
vhdl_description = "Each process block labeled with meaningful name"
vlog_description = "Each process block labeled with meaningful name"
[RMM.21051]
vhdl_val="PREFIX","\"U_\""
vlog_val="PREFIX","\"U_\""
vlog_indexname = "5.2.15-G2"
vhdl_indexname = "5.2.15-G2"
vhdl_description = "Each instance labeled U_<name>."
vlog_description = "Each instance labeled U_<name>."
[RMM.21057]
vhdl_val="PREFIX"
vlog_val="PREFIX"
vlog_indexname = "5.2.1-G6"
vhdl_indexname = "5.2.1-G6"
vhdl_description = "Use the same name for all clock signals that are driven from the same clock source"
vlog_description = "Use the same name for all clock signals that are driven from the same clock source"
[RMM.22011]
vlog_indexname = "5.5.4-G1"
vhdl_indexname = "5.5.4-G1"
vhdl_description = "No combinational feedback"
vlog_description = "No combinational feedback"
[RMM.22023]
vlog_indexname = "5.2.6-R1"
vhdl_indexname = "5.2.6-R1"
vhdl_description = "Use separate line for each HDL statement"
vlog_description = "Use separate line for each HDL statement"
[RMM.22025]
vhdl_val="72"
vlog_val="72"
vlog_indexname = "5.2.7-G1"
vhdl_indexname = "5.2.7-G1"
vhdl_description = "Keep the line length to 72 characters or less"
vlog_description = "Keep the line length to 72 characters or less"
[RMM.22027]
vhdl_val="2"
vlog_val="2"
vlog_indexname = "5.2.8-G1"
vhdl_indexname = "5.2.8-G1"
vhdl_description = "User indentation with consistent spaces number to improve the readability"
vlog_description = "User indentation with consistent spaces number to improve the readability"
[RMM.22029]
vlog_indexname = "5.2.8-G2"
vhdl_indexname = "5.2.8-G2"
vhdl_description = "Avoid using tabs"
vlog_description = "Avoid using tabs"
[RMM.22031]
vlog_indexname = "5.2.5-G1-1"
vhdl_indexname = "5.2.5-G1-1"
vhdl_description = "Use comments to explain ports"
vlog_description = "Use comments to explain ports"
[RMM.22033]
vlog_indexname = "5.2.11-G1"
vhdl_indexname = "5.2.11-G1"
vhdl_description = "Blank line between the input and output ports to improve readability"
vlog_description = "Blank line between the input and output ports to improve readability"
[RMM.22033]
vlog_indexname = "5.2.11-G1"
vhdl_indexname = "5.2.11-G1"
vhdl_description = "Blank line between the input and output ports to improve readability"
vlog_description = "Blank line between the input and output ports to improve readability"
[RMM.22035]
vlog_indexname = "5.2.10-G2-1"
vhdl_indexname = "5.2.10-G2-1"
vhdl_description = "Declare ports in a logical order"
vlog_description = "Declare ports in a logical order"
[RMM.22038]
vlog_indexname = "5.2.5-G1-2"
vhdl_indexname = "5.2.5-G1-2"
vhdl_description = "Use comments to explain signals and variables"
vlog_description = "Use comments to explain signals and variables"
[RMM.22039]
vlog_indexname = "5.2.10-R1"
vhdl_indexname = "5.2.10-R1"
vhdl_description = "Declare ports in a logical order"
vlog_description = "Declare ports in a logical order"
[RMM.22043]
vlog_indexname = "5.2.11-R1-1"
vhdl_indexname = "5.2.11-R1-1"
vhdl_description = "Use explicit mapping for ports"
vlog_description = "Use explicit mapping for ports"
[RMM.22044]
vlog_indexname = "5.2.11-R1-2"
vhdl_indexname = "5.2.11-R1-2"
vhdl_description = "Use explicit mapping for generic"
vlog_description = "Use explicit mapping for parameter"
[RMM.22049]
vlog_indexname = "5.3.2-G1"
vhdl_indexname = "5.3.2-G1"
vhdl_description = "No hard-coded numeric values in your design (with possible exception of 1 and 0)."
vlog_description = "No hard-coded numeric values in your design (with possible exception of 1 and 0)."
[RMM.22053]
vlog_indexname = "5.4.3-G1"
vhdl_indexname = "5.4.3-G1"
vhdl_description = "No gated clocks in design."
vlog_description = "No gated clocks in design."
[RMM.22055]
vlog_indexname = "5.4.2-G1"
vhdl_indexname = "5.4.2-G1"
vhdl_description = "No clock buffers in design; inserted after synthesis in physical design stage."
vlog_description = "No clock buffers in design; inserted after synthesis in physical design stage."
[RMM.22056]
vlog_indexname = "5.4.6-G1-1"
vhdl_indexname = "5.4.6-G1-1"
vhdl_description = "No internally generated"
vlog_description = "No internally generated"
[RMM.22063]
vlog_indexname = "5.5.9-G1"
vhdl_indexname = "5.5.9-G1"
vhdl_description = "describe state machines into two processes"
vlog_description = "describe state machines into two processes"
[RMM.22067]
vlog_indexname = "5.5.9-G3"
vhdl_indexname = "5.5.9-G3"
vhdl_description = "FSM logic and non-FSM logic separated into different modules."
vlog_description = "FSM logic and non-FSM logic separated into different modules."
[RMM.22131]
vlog_indexname = "5.4.4-G1"
vhdl_indexname = "5.4.4-G1"
vhdl_description = "No internally generated clocks in design."
vlog_description = "No internally generated clocks in design."
[RMM.22225]
vlog_indexname = "5.4.1-G1"
vhdl_indexname = "5.4.1-G1"
vhdl_description = "Avoid using both positive-edge and negative-edge triggered flip-flops in your design"
vlog_description = "Avoid using both positive-edge and negative-edge triggered flip-flops in your design"
[RMM.22269]
vlog_indexname = "5.6.3-G1"
vhdl_indexname = "5.6.3-G1"
vhdl_description = "Critical path logic isolated in a separate module from noncritical path logic"
vlog_description = "Critical path logic isolated in a separate module from noncritical path logic"
[RMM.22271]
vlog_indexname = "5.6.2-G1"
vhdl_indexname = "5.6.2-G1"
vhdl_description = "Related combinational logic placed together in the same module."
vlog_description = "Related combinational logic placed together in the same module."
[RMM.22271]
vlog_indexname = "5.6.2-G1"
vhdl_indexname = "5.6.2-G1"
vhdl_description = "Related combinational logic placed together in the same module."
vlog_description = "Related combinational logic placed together in the same module."
[RMM.22273]
vlog_indexname = "5.4.5-G1-1"
vhdl_indexname = "5.4.5-G1-1"
vhdl_description = "separate clock generate circuit in different modules"
vlog_description = "separate clock generate circuit in different modules"
[RMM.22275]
vlog_indexname = "5.4.6-G2"
vhdl_indexname = "5.4.6-G2"
vhdl_description = "separate reset generate circuit into different modules"
vlog_description = "separate reset generate circuit into different modules"
[RMM.23003]
vlog_indexname = "5.5.2-G1"
vhdl_indexname = "5.5.2-G1"
vhdl_description = "No latch inference"
vlog_description = "No latch inference"
[RMM.23011]
vlog_indexname = "5.5.5-G1"
vhdl_indexname = "5.5.5-G1"
vhdl_description = "Complete sensitivity list in each process (VHDL) or always (Verilog) blocks."
vlog_description = "Complete sensitivity list in each process (VHDL) or always (Verilog) blocks."
[RMM.23013]
vlog_indexname = "5.5.5-G2"
vhdl_indexname = "5.5.5-G2"
vhdl_description = "Only necessary signals in each process sensitivity lists"
vlog_description = "Only necessary signals in each process sensitivity lists"
[RMM.23015]
vlog_indexname = "5.5.6-G1"
vlog_description = "nonblocking assignments always used in sequencial blocks for synthesis"
[RMM.23017]
vlog_indexname = "5.5.8.1"
vhdl_indexname = "5.5.8.1"
vhdl_description = "Case statements used rather than an if-then-else statement wherever possible"
vlog_description = "Case statements used rather than an if-then-else statement wherever possible"
[RMM.23021]
vlog_indexname = "5.6.8-G1"
vlog_description = "No instantiated gate-level logic at the top level of the design hierarchy."
[RMM.23043]
vlog_indexname = "5.4.6-G1-1"
vhdl_indexname = "5.4.6-G1-1"
vhdl_description = "No conditional resets"
vlog_description = "No conditional resets"
[RMM.23121]
vlog_indexname = "5.5.1-G1-2"
vhdl_indexname = "5.5.1-G1-2"
vhdl_description = "Use the design's reset signal to initialize registered signals."
vlog_description = "Use the design's reset signal to initialize registered signals."
[RMM.24001]
vlog_indexname = "5.2.9-G1-1"
vlog_description = "Do not use VHDL reserved words for names in RTL source files"
[RMM.24003]
vhdl_indexname = "5.2.9-G1-2"
vhdl_description = "Do not user verilog reserved words for names in RTL source files."
[RMM.24009]
vlog_indexname = "5.2.15-R3"
vhdl_indexname = "5.2.15-R3"
vhdl_description = "Signal, variable, or entity names are not duplicated."
vlog_description = "Signal, variable, or entity names are not duplicated."
[RMM.25015]
vlog_indexname = "5.6.1-G1"
vhdl_indexname = "5.6.1-G1"
vhdl_description = "For each block of a hierarchical design, all output signals should be registered"
vlog_description = "For each block of a hierarchical design, all output signals should be registered"
[RMM.27063]
vhdl_val="CASE_UPPER"
vhdl_indexname = "5.2.1-G2-3"
vhdl_description = "Use uppercase letters for names of literal"
[RMM.27069]
vhdl_indexname = "5.3.1-R1"
vhdl_description = "use Only IEEE Standard Types"
[RMM.27071]
vhdl_indexname = "5.3.1-G3"
vhdl_description = "If VHDL, then types bit or bit_vector not used."
[RMM.27083]
vhdl_val="RESOLVED"
vhdl_indexname = "5.3.1-G1"
vhdl_description = "std_logic and std_logic_vector packages used rather than std_ulogic and std_ulogic_vector."
[RMM.27143]
vhdl_indexname = "5.3.7-G2"
vhdl_description = "Do not use BLOCK constructs"
[RMM.27144]
vhdl_indexname = "5.3.7-G1"
vhdl_description = "do not use generate statements."
[RMM.27155]
vhdl_indexname = "5.2.2-R1"
vhdl_description = "no underscores in entity port declarations for top-level macros."
[RMM.27159]
vhdl_indexname = "5.2.2-R4"
vhdl_description = "Default"
[RMM.27163]
vhdl_indexname = "5.2.2-R3-1"
vhdl_description = "type marks in top-level entity port shall denote a type or subtype that is declared in package std_logic_1164"
[RMM.27181]
vhdl_indexname = "5.5.7-G1-1"
vhdl_description = "use signals instead of variables for synthesizable RTL."
[RMM.27259]
vhdl_val="CASE_UPPER"
vhdl_indexname = "5.2.1-G2-2"
vhdl_description = "Use uppercase letters for names of CONSTANT"
[RMM.27273]
vhdl_val="3","16"
vlog_val="3","16"
vlog_indexname = "5.2.1-G4"
vhdl_indexname = "5.2.1-G4"
vhdl_description = "Use short but descriptive names for GENERIC"
vlog_description = "Use short but descriptive names for parameters"
[RMM.27524]
vlog_indexname = "5.5.1-G1-3"
vhdl_indexname = "5.5.1-G1-3"
vhdl_description = "do not initialize the signal in the declaration;"
[RMM.27551]
vhdl_indexname = "5.2.2-R2"
vhdl_description = "no ports declared in top-level entity of mode LINKAGE"


[RMM.include]
1 = "Coding Practice" Disable
2 = "Clocks and Resets" Enable
3 = "Coding for Synthesis" Enable
4 = "Coding for Portability" Enable
5 = "Partition for Synthesis" Enable

[RMM.Coding Practice]
21001 =  Enable Enable
21003 =  Enable Enable
21005 =  Enable Enable
21013 =  Enable Enable
21015 =  Enable Enable
21020 =  Enable Enable
21023 =  Enable Enable
21025 =  Enable NONE
21027 =  Enable Enable
21029 =  Enable Enable
21031 =  Enable Enable
21035 =  Enable Enable
21041 =  Enable Enable
21049 =  Enable Enable
21050 =  Enable Enable
21051 =  Enable Enable
21057 =  Enable Enable
22023 =  Enable Enable
22025 =  Enable Enable
22027 =  Enable Enable
22029 =  Enable Enable
22031 =  Enable Enable
22033 =  Enable Enable
22033 =  Enable Enable
22035 =  Enable Enable
22038 =  Enable Enable
22039 =  Enable Enable
22043 =  Enable Enable
22044 =  Enable Enable
24001 =  Enable NONE
24003 =  NONE Enable
24009 =  Enable Enable
27063 =  NONE Enable
27259 =  NONE Enable
27273 =  Enable Enable

[RMM.Clocks and Resets]
22053 =  Enable Enable
22055 =  Enable Enable
22056 =  Enable Enable
22131 =  Enable Enable
22225 =  Enable Enable
22273 =  Enable Enable
22275 =  Enable Enable
23043 =  Enable Enable

[RMM.Coding for Synthesis]
22011 =  Enable Enable
22063 =  Enable Enable
22067 =  Enable Enable
23003 =  Enable Enable
23011 =  Enable Enable
23013 =  Enable Enable
23015 =  Enable NONE
23017 =  Enable Enable
23121 =  Enable Enable
27181 =  NONE Enable
27524 =  Enable Enable

[RMM.Coding for Portability]
22049 =  Enable Enable
27069 =  NONE Enable
27071 =  NONE Enable
27083 =  NONE Enable
27143 =  NONE Enable
27144 =  NONE Enable

[RMM.Partition for Synthesis]
22269 =  Enable Enable
22271 =  Enable Enable
22271 =  Enable Enable
23021 =  Enable NONE
25015 =  Enable Enable

[IPQ Design Guidelines.21001]
vhdl_val="CASE_LOWER"
vhdl_severity=Level2
vlog_val="CASE_LOWER"
vlog_severity=Level2
vlog_indexname = "NC.9-1"
vhdl_indexname = "NC.9-1"
vhdl_description = "Signals names are lowercase letters"
vlog_description = "Signals names are lowercase letters"
[IPQ Design Guidelines.21005]
vhdl_val="CASE_LOWER"
vhdl_severity=Level2
vlog_val="CASE_LOWER"
vlog_severity=Level2
vlog_indexname = "NC.9-5"
vhdl_indexname = "NC.9-5"
vhdl_description = "Port names are lowercase letters"
vlog_description = "Port names are lowercase letters"
[IPQ Design Guidelines.21007]
vhdl_val="32"
vhdl_severity=Level2
vlog_val="32"
vlog_severity=Level2
vlog_indexname = "NC.19-1"
vhdl_indexname = "NC.19-1"
vhdl_description = "The length of signal names does not exceed 32 characters"
vlog_description = "The length of signal names does not exceed 32 characters"
[IPQ Design Guidelines.21009]
vhdl_val="32"
vhdl_severity=Level2
vlog_val="32"
vlog_severity=Level2
vlog_indexname = "NC.19-2"
vhdl_indexname = "NC.19-2"
vhdl_description = "The length of signal names does not exceed 32 characters"
vlog_description = "The length of signal names does not exceed 32 characters"
[IPQ Design Guidelines.21013]
vhdl_val="SUB_STRING","clk"
vhdl_severity=Level2
vlog_val="SUB_STRING","clk"
vlog_severity=Level2
vlog_indexname = "NC.11"
vhdl_indexname = "NC.11"
vhdl_description = "Consistent clock signal name"
vlog_description = "Consistent clock signal name"
[IPQ Design Guidelines.21014]
vhdl_val="SUFFIX","_lat"
vhdl_severity=Level1
vlog_val="SUFFIX","_lat"
vlog_severity=Level1
vlog_indexname = "NC.15"
vhdl_indexname = "NC.15"
vhdl_description = "For latch variables, end in _lat"
vlog_description = "For latch variables, end in _lat"
[IPQ Design Guidelines.21015]
vhdl_val="SUB_STRING","rst"
vhdl_severity=Level2
vlog_val="SUB_STRING","rst"
vlog_severity=Level2
vlog_indexname = "NC.12"
vhdl_indexname = "NC.12"
vhdl_description = "Consistent reset signal name"
vlog_description = "Consistent reset signal name"
[IPQ Design Guidelines.21019]
vhdl_val="SUFFIX","_cs"
vhdl_severity=Level1
vlog_val="SUFFIX","_cs"
vlog_severity=Level1
vlog_indexname = "NC.14-1"
vhdl_indexname = "NC.14-1"
vhdl_description = "For FSM variables, naming in <fsm_cs>, <fsm_ns>"
vlog_description = "For FSM variables, naming in <fsm_cs>, <fsm_ns>"
[IPQ Design Guidelines.21020]
vhdl_val="SUFFIX","_n"
vhdl_severity=Level2
vlog_val="SUFFIX","_n"
vlog_severity=Level2
vlog_indexname = "NC.13"
vhdl_indexname = "NC.13"
vhdl_description = "Consistent active-low signal name"
vlog_description = "Consistent active-low signal name"
[IPQ Design Guidelines.21023]
vhdl_val="ZERO_BOUND","DOWN_TO"
vhdl_severity=Level2
vlog_val="ZERO_BOUND","DOWN_TO"
vlog_severity=Level2
vlog_indexname = "NC.23"
vhdl_indexname = "NC.23"
vhdl_description = "Consistent ordering of bits for describing multibit buses"
vlog_description = "Consistent ordering of bits for describing multibit buses"
[IPQ Design Guidelines.21029]
vhdl_val="SUFFIX","_a"
vhdl_severity=Level1
vlog_val="SUFFIX","_a"
vlog_severity=Level1
vlog_indexname = "NC.17"
vhdl_indexname = "NC.17"
vhdl_description = "For asynchronous signals, end in _a"
vlog_description = "For asynchronous signals, end in _a"
[IPQ Design Guidelines.21031]
vhdl_val="SUFFIX","_z"
vhdl_severity=Level1
vlog_val="SUFFIX","_z"
vlog_severity=Level1
vlog_indexname = "NC.16"
vhdl_indexname = "NC.16"
vhdl_description = "For tri-state signals, end in _z"
vlog_description = "For tri-state signals, end in _z"
[IPQ Design Guidelines.21041]
vhdl_val="CASE_UPPER"
vhdl_severity=Level2
vlog_val="CASE_UPPER"
vlog_severity=Level2
vlog_indexname = "NC.8-1"
vhdl_indexname = "NC.8-1"
vlog_description = "Parameters are uppercase letters"
[IPQ Design Guidelines.21043]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "NC.1"
vhdl_indexname = "NC.1"
vhdl_description = "A file must contain at most one module unit"
vlog_description = "A file must contain at most one module unit"
[IPQ Design Guidelines.21044]
vhdl_severity=Level1
vlog_severity=Level1
vlog_indexname = "NC.2"
vhdl_indexname = "NC.2"
vhdl_description = "File name should be identical to design unit name"
vlog_description = "File name should be identical to design unit name"
[IPQ Design Guidelines.21057]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "NC.7-2"
vhdl_indexname = "NC.7-2"
vhdl_description = "Use consistent clock signal names throughout the hierarchy"
vlog_description = "Use consistent clock signal names throughout the hierarchy"
[IPQ Design Guidelines.22002]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.1-2"
vhdl_indexname = "DFT.1-2"
vhdl_description = "Avoid tri-state device"
vlog_description = "Avoid tri-state device"
[IPQ Design Guidelines.22003]
vhdl_val="LHS_EQ_RHS","VAR_EQ_CON"
vhdl_severity=Level3
vlog_val="LHS_EQ_RHS","VAR_EQ_CON"
vlog_severity=Level3
vlog_indexname = "CS.15-1"
vhdl_indexname = "CS.15-1"
vhdl_description = "Operand size must match in assignment"
vlog_description = "Operand size must match in assignment"
[IPQ Design Guidelines.22004]
vhdl_val="VAR_EQ_CON"
vhdl_severity=Level3
vlog_val="VAR_EQ_CON"
vlog_severity=Level3
vlog_indexname = "CS.15-2"
vhdl_indexname = "CS.15-2"
vhdl_description = "Operand size must match in assignment"
vlog_description = "Operand size must match in assignment"
[IPQ Design Guidelines.22007]
vhdl_val="INPUT"
vhdl_severity=Level1
vlog_val="INPUT"
vlog_severity=Level1
vlog_indexname = "DFT.10-2"
vhdl_indexname = "DFT.10-2"
vhdl_description = "Avoid constant inputs on instance"
vlog_description = "Avoid constant inputs on instance"
[IPQ Design Guidelines.22008]
vlog_severity=Level3
vlog_indexname = "CS.11"
vlog_description = "Avoid expression in port connections"
[IPQ Design Guidelines.22011]
vhdl_val="SYNC"
vhdl_severity=Level2
vlog_val="SYNC"
vlog_severity=Level2
vlog_indexname = "DFT.9/STA.1"
vhdl_indexname = "DFT.9/STA.1"
vhdl_description = "Avoid Combinational feedback loop"
vlog_description = "Avoid Combinational feedback loop"
[IPQ Design Guidelines.22020]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.1-1"
vhdl_indexname = "DFT.1-1"
vhdl_description = "Avoid tri-state device"
vlog_description = "Avoid tri-state device"
[IPQ Design Guidelines.22021]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "CS.13"
vhdl_indexname = "CS.13"
vhdl_description = "Use parentheses in complex equations"
vlog_description = "Use parentheses in complex equations"
[IPQ Design Guidelines.22023]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "CS.3"
vhdl_indexname = "CS.3"
vhdl_description = "Use a separate line for each HDL statement"
vlog_description = "Use a separate line for each HDL statement"
[IPQ Design Guidelines.22025]
vhdl_val="72"
vhdl_severity=Level1
vlog_val="72"
vlog_severity=Level1
vlog_indexname = "CS.7"
vhdl_indexname = "CS.7"
vhdl_description = "Keep line length within 72 characters"
vlog_description = "Keep line length within 72 characters"
[IPQ Design Guidelines.22027]
vhdl_val="2","FIRST_INDENT,BEGIN_INDENT"
vhdl_severity=Level2
vlog_val="2","FIRST_INDENT,BEGIN_INDENT"
vlog_severity=Level2
vlog_indexname = "CS.1"
vhdl_indexname = "CS.1"
vhdl_description = "Code should be aligned in a tabular format"
vlog_description = "Code should be aligned in a tabular format"
[IPQ Design Guidelines.22029]
vhdl_val="CHECK_WHOLE"
vhdl_severity=Level2
vlog_val="CHECK_WHOLE"
vlog_severity=Level2
vlog_indexname = "CS.2"
vhdl_indexname = "CS.2"
vhdl_description = "Use space instead of tab stops for code indentation"
vlog_description = "Use space instead of tab stops for code indentation"
[IPQ Design Guidelines.22031]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "CS.4"
vhdl_indexname = "CS.4"
vhdl_description = "Use a separate line for each port declaration"
vlog_description = "Use a separate line for each port declaration"
[IPQ Design Guidelines.22032]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "COM.1"
vhdl_indexname = "COM.1"
vhdl_description = "Use comments for port declarations"
vlog_description = "Use comments for port declarations"
[IPQ Design Guidelines.22038]
vhdl_val="CHECK_COMMENT"
vhdl_severity=Level1
vlog_val="CHECK_COMMENT"
vlog_severity=Level1
vlog_indexname = "COM.2"
vhdl_indexname = "COM.2"
vhdl_description = "Comment signal declarations"
vlog_description = "Comment signal declarations"
[IPQ Design Guidelines.22043]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "CS.10"
vhdl_indexname = "CS.10"
vhdl_description = "Use explicit port mapping instead of positional association in module instantiation"
vlog_description = "Use explicit port mapping instead of positional association in module instantiation"
[IPQ Design Guidelines.22053]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "D.4-1/DFT.5-1/STA.3-1"
vhdl_indexname = "D.4-1/DFT.5-1/STA.3-1"
vhdl_description = "Simplify the register clock origin--avoid gated clock"
vlog_description = "Simplify the register clock origin--avoid gated clock"
[IPQ Design Guidelines.22054]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "D.4-2/DFT.5-2/STA.3-2"
vhdl_indexname = "D.4-2/DFT.5-2/STA.3-2"
vhdl_description = "Simplify the register clock origin--avoid inverted clock"
vlog_description = "Simplify the register clock origin--avoid inverted clock"
[IPQ Design Guidelines.22055]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "D.4-3/DFT.5-3/STA.3-3"
vhdl_indexname = "D.4-3/DFT.5-3/STA.3-3"
vhdl_description = "Simplify the register clock origin--avoid buffered clock"
vlog_description = "Simplify the register clock origin--avoid buffered clock"
[IPQ Design Guidelines.22056]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.7-1"
vhdl_indexname = "DFT.7-1"
vhdl_description = "Internal clear"
vlog_description = "Internal clear"
[IPQ Design Guidelines.22057]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.7-2"
vhdl_indexname = "DFT.7-2"
vhdl_description = "Internal preset"
vlog_description = "Internal preset"
[IPQ Design Guidelines.22063]
vhdl_severity=Level1
vlog_severity=Level1
vlog_indexname = "CS.17"
vhdl_indexname = "CS.17"
vhdl_description = "\"Finite State Machine (FSM) coding style"
vlog_description = "\"Finite State Machine (FSM) coding style"
[IPQ Design Guidelines.22082]
vhdl_val="INPUT,OUTPUT"
vhdl_severity=Level3
vlog_val="INPUT,OUTPUT"
vlog_severity=Level3
vlog_indexname = "SYN.6~7-1"
vhdl_indexname = "SYN.6~7-1"
vhdl_description = "All unused module inputs must be driven, outputs should be connected"
vlog_description = "All unused module inputs must be driven, outputs should be connected"
[IPQ Design Guidelines.22091]
vlog_severity=Level1
vlog_indexname = "CS.16"
vlog_description = "Expression in condition should be 1- bit value"
[IPQ Design Guidelines.22112]
vlog_severity=Level3
vlog_indexname = "SYN.1.6-3"
vlog_description = "Loop must be in a static range"
[IPQ Design Guidelines.22113]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "SYN.1.6-2"
vhdl_indexname = "SYN.1.6-2"
vhdl_description = "Loop must be in a static range"
vlog_description = "Loop must be in a static range"
[IPQ Design Guidelines.22127]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.8-1/STA.5-1"
vhdl_indexname = "DFT.8-1/STA.5-1"
vhdl_description = "Avoid clocks as data (of registers)"
vlog_description = "Avoid clocks as data (of registers)"
[IPQ Design Guidelines.22130]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.8-2/STA.5-2"
vhdl_indexname = "DFT.8-2/STA.5-2"
vhdl_description = "Avoid clocks as primary output"
vlog_description = "Avoid clocks as primary output"
[IPQ Design Guidelines.22131]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.6/STA.3-4"
vhdl_indexname = "DFT.6/STA.3-4"
vhdl_description = "Simplify the register clock origin--Simplify the register clock origin--avoid sequential clock"
vlog_description = "Simplify the register clock origin--Simplify the register clock origin--avoid sequential clock"
[IPQ Design Guidelines.22132]
vhdl_severity=Level1
vlog_severity=Level1
vlog_indexname = "D.1.2"
vhdl_indexname = "D.1.2"
vhdl_description = "Registers in an IP's interface should be clocked in a single edge of the same clock"
vlog_description = "Registers in an IP's interface should be clocked in a single edge of the same clock"
[IPQ Design Guidelines.22161]
vlog_severity=Level3
vlog_indexname = "CS.14"
vlog_description = "Wire must be explicitly declared"
[IPQ Design Guidelines.22165]
vhdl_severity=Level1
vlog_severity=Level1
vlog_indexname = "DFT.10-1"
vhdl_indexname = "DFT.10-1"
vhdl_description = "Avoid constant inputs in core"
vlog_description = "Avoid constant inputs in core"
[IPQ Design Guidelines.22167]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.2"
vhdl_indexname = "DFT.2"
vhdl_description = "Avoid bi-directional nets"
vlog_description = "Avoid bi-directional nets"
[IPQ Design Guidelines.22203]
vhdl_val="BOTH"
vhdl_severity=Level2
vlog_val="BOTH"
vlog_severity=Level2
vlog_indexname = "DFT.8-4"
vhdl_indexname = "DFT.8-4"
vhdl_description = "reset signal used as data input"
vlog_description = "reset signal used as data input"
[IPQ Design Guidelines.22204]
vhdl_val="BOTH"
vhdl_severity=Level2
vlog_val="BOTH"
vlog_severity=Level2
vlog_indexname = "DFT.8-5"
vhdl_indexname = "DFT.8-5"
vhdl_description = "reset signal feeds into primary output"
vlog_description = "reset signal feeds into primary output"
[IPQ Design Guidelines.22225]
vhdl_val="TRUE"
vhdl_severity=Level2
vlog_val="TRUE"
vlog_severity=Level2
vlog_indexname = "D.2/DFT.4/STA.2-2"
vhdl_indexname = "D.2/DFT.4/STA.2-2"
vhdl_description = "Using synchronous design practices"
vlog_description = "Using synchronous design practices"
[IPQ Design Guidelines.22227]
vhdl_val="BOTH"
vhdl_severity=Level2
vlog_val="BOTH"
vlog_severity=Level2
vlog_indexname = "DFT.8-3"
vhdl_indexname = "DFT.8-3"
vhdl_description = "set signal used as data input"
vlog_description = "set signal used as data input"
[IPQ Design Guidelines.22228]
vhdl_val="BOTH"
vhdl_severity=Level2
vlog_val="BOTH"
vlog_severity=Level2
vlog_indexname = "DFT.8-6"
vhdl_indexname = "DFT.8-6"
vhdl_description = "set signal feeds into primary output"
vlog_description = "set signal feeds into primary output"
[IPQ Design Guidelines.22275]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "STA.3-5"
vhdl_indexname = "STA.3-5"
vhdl_description = "Simplify the register clock origin--separate clock generator"
vlog_description = "Simplify the register clock origin--separate clock generator"
[IPQ Design Guidelines.22279]
vhdl_val="INPUT,OUTPUT"
vhdl_severity=Level3
vlog_val="INPUT,OUTPUT"
vlog_severity=Level3
vlog_indexname = "SYN.6~7-2"
vhdl_indexname = "SYN.6~7-2"
vhdl_description = "All unused module inputs must be driven, outputs should be connected"
vlog_description = "All unused module inputs must be driven, outputs should be connected"
[IPQ Design Guidelines.23003]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "DFT.3/STA.6/SYN.4"
vhdl_indexname = "DFT.3/STA.6/SYN.4"
vhdl_description = "Specify code fragments for combinational logic completely"
vlog_description = "Specify code fragments for combinational logic completely"
[IPQ Design Guidelines.23007]
vlog_val="IGNORE_IN_SEQ"
vlog_severity=Level2
vlog_indexname = "SYN.9"
vlog_description = "Incomplete case statements should have default case assignments"
[IPQ Design Guidelines.23011]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "SIM.3"
vhdl_indexname = "SIM.3"
vhdl_description = "Avoid missing sensitivity lists in combinational always block"
vlog_description = "Avoid missing sensitivity lists in combinational always block"
[IPQ Design Guidelines.23013]
vhdl_val="BOTH","IGNORE_PART_SEL"
vhdl_severity=Level3
vlog_val="BOTH","IGNORE_PART_SEL"
vlog_severity=Level3
vlog_indexname = "SIM.4"
vhdl_indexname = "SIM.4"
vhdl_description = "Avoid redundant sensitivity lists"
vlog_description = "Avoid redundant sensitivity lists"
[IPQ Design Guidelines.23015]
vlog_val="BLOCKING",""
vlog_severity=Level3
vlog_indexname = "SIM.1"
vlog_description = "Use non-blocking assignments in sequential always blocks"
[IPQ Design Guidelines.23016]
vlog_val="NONBLOCKING","FALSE"
vlog_severity=Level3
vlog_indexname = "SIM.2"
vlog_description = "Use blocking assignments in combinational always blocks"
[IPQ Design Guidelines.23021]
vlog_val="DESIGN",""
vlog_severity=Level3
vlog_indexname = "SYN.5-1"
vlog_description = "Verilog primitives are prohibited"
[IPQ Design Guidelines.23027]
vhdl_val="IGNORE_SUBPROG"
vhdl_severity=Level3
vlog_val="IGNORE_SUBPROG"
vlog_severity=Level3
vlog_indexname = "SYN.1.6-1"
vhdl_indexname = "SYN.1.6-1"
vhdl_description = "Loop must be in a static range"
vlog_description = "Loop must be in a static range"
[IPQ Design Guidelines.23045]
vlog_severity=Level3
vlog_indexname = "SYN.1.4-2"
vlog_description = "Data type of time is prohibited"
[IPQ Design Guidelines.23047]
vhdl_severity=Level3
vlog_severity=Level3
vlog_indexname = "SYN.1.4-1"
vhdl_indexname = "SYN.1.4-1"
vhdl_description = "Data type of real is prohibited"
vlog_description = "Data type of real is prohibited"
[IPQ Design Guidelines.23051]
vlog_severity=Level3
vlog_indexname = "SYN.1.4-3"
vlog_description = "Data type of event is prohibited"
[IPQ Design Guidelines.23053]
vlog_severity=Level3
vlog_indexname = "SYN.5-2"
vlog_description = "UDP instance not synthesizable"
[IPQ Design Guidelines.23057]
vlog_severity=Level3
vlog_indexname = "SYN.1.1"
vlog_description = "Waveform statement are prohibited"
[IPQ Design Guidelines.23061]
vlog_severity=Level3
vlog_indexname = "SYN.5-3"
vlog_description = "UDP not synthesizable"
[IPQ Design Guidelines.23075]
vlog_severity=Level3
vlog_indexname = "SYN.1.3-2"
vlog_description = "# delay statements are prohibited"
[IPQ Design Guidelines.23089]
vlog_severity=Level3
vlog_indexname = "SIM.7/SYN.1.3-3"
vlog_description = "Avoid using delayed assignments"
[IPQ Design Guidelines.23095]
vlog_severity=Level3
vlog_indexname = "SYN.1.3-1"
vlog_description = "Wait statements are prohibited"
[IPQ Design Guidelines.23103]
vlog_severity=Level3
vlog_indexname = "SYN.1.2"
vlog_description = "System task for simulation (e.g. $display, $monitor, $printf, ) are prohibited"
[IPQ Design Guidelines.23121]
vhdl_val="BOTH"
vhdl_severity=Level2
vlog_val="BOTH"
vlog_severity=Level2
vlog_indexname = "D.5.1/SIM.5"
vhdl_indexname = "D.5.1/SIM.5"
vhdl_description = "Initialize control storage elements"
vlog_description = "Initialize control storage elements"
[IPQ Design Guidelines.23131]
vlog_val="CHECK_DEFAULT"
vlog_severity=Level3
vlog_indexname = "SIM.6"
vlog_description = "Do not assign signals don't care (x) value"
[IPQ Design Guidelines.23133]
vlog_severity=Level3
vlog_indexname = "SYN.1.5"
vlog_description = "Only one clock per always sensitivity list"
[IPQ Design Guidelines.24001]
vlog_severity=Level3
vlog_indexname = "NC.18"
vlog_description = "VHDL keywords are prohibited"
[IPQ Design Guidelines.24007]
vlog_severity=Level3
vlog_indexname = "NC.5"
vlog_description = "Names can not be distinguishable in letter case only"
[IPQ Design Guidelines.24019]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "SYN.2"
vhdl_indexname = "SYN.2"
vhdl_description = "Avoid any embedded synthesis scripts"
vlog_description = "Avoid any embedded synthesis scripts"
[IPQ Design Guidelines.25003]
vhdl_severity=Level1
vlog_severity=Level1
vlog_indexname = "DFT.10-3"
vhdl_indexname = "DFT.10-3"
vhdl_description = "Avoid floating output"
vlog_description = "Avoid floating output"
[IPQ Design Guidelines.25015]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "D.1.1"
vhdl_indexname = "D.1.1"
vhdl_description = "Output signals must be registered"
vlog_description = "Output signals must be registered"
[IPQ Design Guidelines.27235]
vhdl_val="CASE_LOWER"
vhdl_severity=Level2
vlog_val="CASE_LOWER"
vlog_severity=Level2
vlog_indexname = "NC.9-4"
vhdl_indexname = "NC.9-4"
vhdl_description = "Instances names are lowercase letters"
vlog_description = "Instances names are lowercase letters"
[IPQ Design Guidelines.27287]
vlog_val="[a-z]+"
vlog_severity=Level2
vlog_indexname = "NC.9-1"
vlog_description = "Signals names are lowercase letters"
[IPQ Design Guidelines.27288]
vlog_val="1","32"
vlog_severity=Level2
vlog_indexname = "NC.19-1"
vlog_description = "The length of signal names does not exceed 32 characters"
[IPQ Design Guidelines.27299]
vhdl_val="CASE_LOWER"
vhdl_severity=Level2
vlog_val="CASE_LOWER"
vlog_severity=Level2
vlog_indexname = "NC.9-2"
vhdl_indexname = "NC.9-2"
vhdl_description = "Functions names are lowercase letters"
vlog_description = "Functions names are lowercase letters"
[IPQ Design Guidelines.27307]
vhdl_val="CASE_LOWER"
vhdl_severity=Level2
vlog_val="CASE_LOWER"
vlog_severity=Level2
vlog_indexname = "NC.9-3"
vhdl_indexname = "NC.9-3"
vhdl_description = "Tasks names are lowercase letters"
vlog_description = "Tasks names are lowercase letters"
[IPQ Design Guidelines.27371]
vhdl_val="parallel_case,full_case"
vhdl_severity=Level2
vlog_val="parallel_case,full_case"
vlog_severity=Level2
vlog_indexname = "SYN.3"
vhdl_indexname = "SYN.3"
vhdl_description = "Avoid full_case and parallel_case synthesis directive"
vlog_description = "Avoid full_case and parallel_case synthesis directive"
[IPQ Design Guidelines.27373]
vhdl_val="SUFFIX","_ns"
vhdl_severity=Level1
vlog_val="SUFFIX","_ns"
vlog_severity=Level1
vlog_indexname = "NC.14-2"
vhdl_indexname = "NC.14-2"
vhdl_description = "For FSM variables, naming in <fsm_cs>, <fsm_ns>"
vlog_description = "For FSM variables, naming in <fsm_cs>, <fsm_ns>"
[IPQ Design Guidelines.27375]
vhdl_val="^[a-zA-Z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*"
vhdl_severity=Level2
vlog_val="^[a-zA-Z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*"
vlog_severity=Level2
vlog_indexname = "NC.4"
vhdl_indexname = "NC.4"
vhdl_description = "Names starting with a letter"
vlog_description = "Names starting with a letter"
[IPQ Design Guidelines.27411]
vlog_severity=Level3
vlog_indexname = "CS.12"
vlog_description = "Use parameters for FSM state encoding"
[IPQ Design Guidelines.27413]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "STA.2-1"
vhdl_indexname = "STA.2-1"
vhdl_description = "Using synchronous design practices"
vlog_description = "Using synchronous design practices"
[IPQ Design Guidelines.27417]
vhdl_severity=Level2
vlog_severity=Level2
vlog_indexname = "SYN.8"
vhdl_indexname = "SYN.8"
vhdl_description = "Avoid top level glue logic"
vlog_description = "Avoid top level glue logic"
[IPQ Design Guidelines.29001]
vlog_severity=Level2
vlog_indexname = "NC.9-6"
vlog_description = "udpdefn name lower case"
[IPQ Design Guidelines.29002]
vlog_severity=Level2
vlog_indexname = "NC.22"
vlog_description = "Instance names must be identical to the module name."
[IPQ Design Guidelines.29100]
vlog_severity=Level2
vlog_indexname = "CS.5"
vlog_description = "Preserve port order"
[IPQ Design Guidelines.29101]
vlog_severity=Level1
vlog_indexname = "CS.6"
vlog_description = "Declare all internal nets in one section"
[IPQ Design Guidelines.29102]
vlog_severity=Level1
vlog_indexname = "COM.3"
vlog_description = "Use comments for functional sections"
[IPQ Design Guidelines.29103]
vlog_severity=Level1
vlog_indexname = "COM.4"
vlog_description = "Use one-line comments instead of mulltiple-line comments"
[IPQ Design Guidelines.29104]
vlog_severity=Level2
vlog_indexname = "COM.5"
vlog_description = "Use comments for cell instantiations"
[IPQ Design Guidelines.29105]
vlog_severity=Level1
vlog_indexname = "COM.7"
vlog_description = "Use comments for synthesis directives"
[IPQ Design Guidelines.29106]
vlog_severity=Level2
vlog_indexname = "FH.1~4"
vlog_description = "Check file header format"
[IPQ Design Guidelines.29107]
vlog_severity=Level1
vlog_indexname = "COM.8"
vlog_description = "Use comments for compiler directives"
[IPQ Design Guidelines.29109]
vlog_val="CASE_UPPER"
vlog_severity=Level2
vlog_indexname = "NC.8-2"
vlog_description = "Text macros are uppercase letters"
[IPQ Design Guidelines.29110]
vlog_severity=Level2
vlog_indexname = "NC.7-1"
vlog_description = "Use consistent signal names throughout the hierarchy"
[IPQ Design Guidelines.29111]
vlog_severity=Level2
vlog_indexname = "FH.5~7"
vlog_description = "Check construct header format"


[IPQ Design Guidelines.include]
1 = "Naming Convention" Enable
2 = "File Header" Enable
3 = "Comments" Enable
4 = "Coding Style" Enable
5 = "Synthesis" Enable
6 = "Static Timing Analysis" Enable
7 = "Simulation" Enable
8 = "Design For Test" Enable
9 = "Design Style" Enable

[IPQ Design Guidelines.Naming Convention]
21001 =  Enable Enable
21005 =  Enable Enable
21007 =  Enable Enable
21009 =  Enable Enable
21013 =  Enable Enable
21014 =  Enable Enable
21015 =  Enable Enable
21019 =  Enable Enable
21020 =  Enable Enable
21023 =  Enable Enable
21029 =  Enable Enable
21031 =  Enable Enable
21041 =  Enable Enable
21043 =  Enable Enable
21044 =  Enable Enable
21057 =  Enable Enable
24001 =  Enable NONE
24007 =  Enable NONE
27235 =  Enable Enable
27287 =  Enable NONE
27288 =  Enable NONE
27299 =  Enable Enable
27307 =  Enable Enable
27373 =  Enable Enable
27375 =  Enable Enable
29001 =  Enable NONE
29002 =  Enable NONE
29109 =  Enable NONE
29110 =  Enable NONE

[IPQ Design Guidelines.File Header]
29106 =  Enable NONE
29111 =  Enable NONE

[IPQ Design Guidelines.Comments]
22032 =  Enable Enable
22038 =  Enable Enable
29102 =  Enable NONE
29103 =  Enable NONE
29104 =  Enable NONE
29105 =  Enable NONE
29107 =  Enable NONE

[IPQ Design Guidelines.Coding Style]
22003 =  Enable Enable
22004 =  Enable Enable
22008 =  Enable NONE
22021 =  Enable Enable
22023 =  Enable Enable
22025 =  Enable Enable
22027 =  Enable Enable
22029 =  Enable Enable
22031 =  Enable Enable
22043 =  Enable Enable
22063 =  Enable Enable
22091 =  Enable NONE
22161 =  Enable NONE
27411 =  Enable NONE
29100 =  Enable NONE
29101 =  Enable NONE

[IPQ Design Guidelines.Synthesis]
22082 =  Enable Enable
22112 =  Enable NONE
22113 =  Enable Enable
22279 =  Enable Enable
23003 =  Enable Enable
23007 =  Enable NONE
23021 =  Enable NONE
23027 =  Enable Enable
23045 =  Enable NONE
23047 =  Enable Enable
23051 =  Enable NONE
23053 =  Enable NONE
23057 =  Enable NONE
23061 =  Enable NONE
23075 =  Enable NONE
23089 =  Enable NONE
23095 =  Enable NONE
23103 =  Enable NONE
23133 =  Enable NONE
24019 =  Enable Enable
27371 =  Enable Enable
27417 =  Enable Enable

[IPQ Design Guidelines.Static Timing Analysis]
22011 =  Enable Enable
22053 =  Enable Enable
22054 =  Enable Enable
22055 =  Enable Enable
22127 =  Enable Enable
22130 =  Enable Enable
22131 =  Enable Enable
22225 =  Enable Enable
22275 =  Enable Enable
23003 =  Enable Enable
27413 =  Enable Enable

[IPQ Design Guidelines.Simulation]
23011 =  Enable Enable
23013 =  Enable Enable
23015 =  Enable NONE
23016 =  Enable NONE
23089 =  Enable NONE
23121 =  Enable Enable
23131 =  Enable NONE

[IPQ Design Guidelines.Design For Test]
22002 =  Enable Enable
22007 =  Enable Enable
22011 =  Enable Enable
22020 =  Enable Enable
22053 =  Enable Enable
22054 =  Enable Enable
22055 =  Enable Enable
22056 =  Enable Enable
22057 =  Enable Enable
22127 =  Enable Enable
22130 =  Enable Enable
22131 =  Enable Enable
22165 =  Enable Enable
22167 =  Enable Enable
22203 =  Enable Enable
22204 =  Enable Enable
22227 =  Enable Enable
22228 =  Enable Enable
23003 =  Enable Enable
25003 =  Enable Enable

[IPQ Design Guidelines.Design Style]
22053 =  Enable Enable
22054 =  Enable Enable
22055 =  Enable Enable
22131 =  Enable Enable
22132 =  Enable Enable
25015 =  Enable Enable

