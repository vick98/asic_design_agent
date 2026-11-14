# fsdbq —— FFR (FSDB File Reader) 薄壳，编译一次即可长期使用。
#
# 全部路径按 $(VERDI_HOME) 推导，不硬编码机器相关路径：
#   make VERDI_HOME=/opt/synopsys/verdi
#
# 注意：libz 必须给绝对路径 —— 目标 EDA 机通常没有 zlib1g-dev，-lz 会找不到。
#      可用 ZLIB=... 覆盖（如 aarch64: /lib/aarch64-linux-gnu/libz.so.1）。

VERDI_HOME ?= /opt/synopsys/verdi
FFR_DIR    ?= $(VERDI_HOME)/share/FsdbReader
FFR_LIB    ?= $(FFR_DIR)/linux64
# libz 按发行版常见位置逐个探测（WSL/老系统可能是 /lib64，部分机器在 /usr/lib）
ZLIB      ?= $(firstword $(foreach c,/lib/x86_64-linux-gnu/libz.so.1 \
              /lib64/libz.so.1 /usr/lib/x86_64-linux-gnu/libz.so.1 \
              /usr/lib/libz.so.1 /lib/aarch64-linux-gnu/libz.so.1,\
              $(if $(wildcard $c),$c)))

CXX      ?= g++
CXXFLAGS ?= -O2 -g -I$(FFR_DIR) -DPORT_LINUXAMD64 -DSVR4 -D_REENTRANT -fPIC -fpermissive -w
LDFLAGS  ?=

TARGET   ?= fsdbq

.PHONY: all check clean

all: $(TARGET)

$(TARGET): fsdbq.cpp
	@test -f "$(FFR_DIR)/ffrAPI.h" || { echo "ERR: 找不到 $(FFR_DIR)/ffrAPI.h（VERDI_HOME 是否正确？）"; exit 1; }
	@test -f "$(FFR_LIB)/libnffr.so" || { echo "ERR: 找不到 $(FFR_LIB)/libnffr.so"; exit 1; }
	@test -f "$(ZLIB)" || { echo "ERR: 找不到 $(ZLIB)（用 ZLIB=... 指定）"; exit 1; }
	$(CXX) $(CXXFLAGS) fsdbq.cpp -o $@ \
	    $(FFR_LIB)/libnffr.so $(FFR_LIB)/libnsys.so $(ZLIB) \
	    -lm -lpthread -ldl $(LDFLAGS)
	@echo "built: $@"

check: $(TARGET)
	@./$(TARGET) 2>&1 | head -1 || true

clean:
	rm -f $(TARGET)
