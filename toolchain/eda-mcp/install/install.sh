#!/bin/bash
#=======================================================================
# install.sh —— eda-mcp 安装脚本（服务器侧）
#-----------------------------------------------------------------------
# 目标环境特点（EDA 服务器常见）：
#   * 没有 pip / ensurepip（python3-venv 未安装，且无 sudo）
#   * 不能联网、不能装系统包
#   * 只需要 python3（>=3.9）与 g++（编 fsdbq 用）
#
# 因此本脚本**不依赖 pip**：
#   1) 编译 native/fsdbq（唯一需要编译的东西，一次装好长期用）
#   2) 把 src/ 挂到 ~/.local/lib/eda-mcp，并生成 ~/.local/bin/eda-mcp 启动器
#   3) 可选：离线安装 MCP SDK（install/vendor/*.whl 解包进 ~/.local/lib/eda-mcp/vendor）
#
# 用法：
#   bash install/install.sh                 # 默认装到 ~/.local
#   bash install/install.sh --prefix /opt/eda-mcp
#   bash install/install.sh --vendor        # 连同 install/vendor 的 wheel 一起装上
#   bash install/install.sh --verdi-home /opt/synopsys/verdi
#=======================================================================
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PKG=$(cd "$HERE/.." && pwd)
PREFIX="${HOME}/.local"
VERDI_HOME_ARG=""
DO_VENDOR=0
ZLIB_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix)     PREFIX="$2"; shift 2;;
    --prefix=*)   PREFIX="${1#--prefix=}"; shift;;
    --verdi-home) VERDI_HOME_ARG="$2"; shift 2;;
    --verdi-home=*) VERDI_HOME_ARG="${1#--verdi-home=}"; shift;;
    --zlib)       ZLIB_ARG="$2"; shift 2;;
    --zlib=*)     ZLIB_ARG="${1#--zlib=}"; shift;;
    --vendor)     DO_VENDOR=1; shift;;
    -h|--help)    sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "未知参数: $1" >&2; exit 2;;
  esac
done

LIBDIR="$PREFIX/lib/eda-mcp"
BINDIR="$PREFIX/bin"

say() { echo "[install] $*"; }
die() { echo "[install][ERROR] $*" >&2; exit 1; }

#--------------------------------------------------------------- 0. 前置检查
# 选一个 >=3.9 的 Python：PATH 里的 python3 不够新时按常见命名逐个尝试；
# 选中的解释器以**绝对路径**钉进启动器（远端 python3 可能是 3.6 的老系统）。
PYBIN=""
for cand in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
  command -v "$cand" >/dev/null 2>&1 || continue
  if "$cand" -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    PYBIN="$(command -v "$cand")"
    break
  fi
done
[ -n "$PYBIN" ] || die "需要 Python >= 3.9：PATH 里的 python3 不满足，也没找到 python3.9~3.13"
PYV=$("$PYBIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
say "python $PYV  ($PYBIN)"

#--------------------------------------------------------------- 1. 编译 fsdbq
VH="${VERDI_HOME_ARG:-${VERDI_HOME:-}}"
if [ -z "$VH" ]; then
  for c in /opt/synopsys/verdi /usr/synopsys/verdi; do
    [ -d "$c/share/FsdbReader" ] && VH="$c" && break
  done
fi
[ -n "$VH" ] || die "未定位 VERDI_HOME（用 --verdi-home 指定，或设置环境变量）"
say "VERDI_HOME = $VH"

command -v g++ >/dev/null || die "找不到 g++（编译 fsdbq 需要）"
mkdir -p "$BINDIR"
MAKEARGS="VERDI_HOME=$VH"
[ -n "$ZLIB_ARG" ] && MAKEARGS="$MAKEARGS ZLIB=$ZLIB_ARG"
say "编译 fsdbq ..."
make -C "$PKG/src/eda_mcp/native" $MAKEARGS all >/dev/null \
  || die "fsdbq 编译失败：请检查 $VH/share/FsdbReader/{ffrAPI.h,linux64/libnffr.so} 与 libz 路径"
install -m 0755 "$PKG/src/eda_mcp/native/fsdbq" "$BINDIR/fsdbq"
say "已安装 $BINDIR/fsdbq"

#--------------------------------------------------------------- 2. 装 Python 包
mkdir -p "$LIBDIR"
rm -rf "$LIBDIR/eda_mcp"
cp -R "$PKG/src/eda_mcp" "$LIBDIR/eda_mcp"
say "已安装 Python 包 -> $LIBDIR/eda_mcp"

#--------------------------------------------------------------- 3. 离线 MCP SDK
# 说明：stdio 传输**不需要**官方 SDK（包内 mcp_stdio.py 是零依赖实现）；
#       只有用 HTTP 传输或想用官方 SDK 时才需要 --vendor。
if [ "$DO_VENDOR" -eq 1 ]; then
  VENDOR="$LIBDIR/vendor"
  mkdir -p "$VENDOR"
  if [ -d "$PKG/install/site" ]; then
    cp -R "$PKG/install/site/." "$VENDOR/"
    say "已复制离线依赖树 install/site -> $VENDOR"
  fi
  count=0
  for whl in "$PKG"/install/vendor/*.whl; do
    [ -e "$whl" ] || continue
    "$PYBIN" -c "import zipfile,sys;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$whl" "$VENDOR"
    count=$((count + 1))
  done
  [ "$count" -gt 0 ] && say "已解包 $count 个离线 wheel -> $VENDOR"
  if [ ! -d "$PKG/install/site" ] && [ "$count" -eq 0 ]; then
    say "未发现离线依赖（先在联网机器上跑 install/fetch-vendor.sh）；stdio 传输不需要它"
  fi
fi

#--------------------------------------------------------------- 4. 启动器
cat > "$BINDIR/eda-mcp" <<EOF
#!/bin/sh
# eda-mcp 启动器（由 install.sh 生成；解释器为安装时选定的 Python >= 3.9 绝对路径）
LIBDIR="$LIBDIR"
BINDIR="$BINDIR"
export PYTHONPATH="\$LIBDIR\${PYTHONPATH:+:\$PYTHONPATH}"
[ -d "\$LIBDIR/vendor" ] && export PYTHONPATH="\$LIBDIR/vendor:\$PYTHONPATH"
export EDA_MCP_FSDBQ_BIN="\${EDA_MCP_FSDBQ_BIN:-\$BINDIR/fsdbq}"
exec "$PYBIN" -m eda_mcp.cli "\$@"
EOF
chmod 0755 "$BINDIR/eda-mcp"

cat > "$BINDIR/eda-mcp-server" <<EOF
#!/bin/sh
# eda-mcp MCP 服务端启动器（stdio；由 install.sh 生成）
exec "$BINDIR/eda-mcp" serve "\$@"
EOF
chmod 0755 "$BINDIR/eda-mcp-server"
say "已生成 $BINDIR/eda-mcp 与 $BINDIR/eda-mcp-server"

#--------------------------------------------------------------- 5. 自检
say "运行 doctor ..."
PATH="$BINDIR:$PATH" "$BINDIR/eda-mcp" doctor || true

cat <<EOF

[install] 完成。请确认 \$PATH 含 $BINDIR（通常 ~/.local/bin 已在 PATH 中）：
    export PATH="$BINDIR:\$PATH"
下一步：
    eda-mcp doctor --deep <某个.fsdb>      # 真实波形冒烟
    eda-mcp wave <fsdb> -t 100ns -c 10 -s <信号> -o out.json
客户端（DeepSeek Harness）MCP 配置：
    command = "ssh"
    args    = ["<eda-host>", "$BINDIR/eda-mcp-server"]
EOF
