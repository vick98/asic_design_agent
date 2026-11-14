#!/bin/bash
#=======================================================================
# fetch-vendor.sh —— 在**有网络的机器**上生成离线 wheel 包（可选）
#-----------------------------------------------------------------------
# 只有在需要官方 MCP SDK 时才需要它（例如用 HTTP 传输）。
# **stdio 传输不需要**：eda-mcp 内置零依赖的 MCP stdio 实现，
# 在 air-gap 的 EDA 服务器上直接可用。
#
# 用法（在 Mac / 任意有网机器，仓库根目录）：
#   bash install/fetch-vendor.sh                       # 默认 linux/amd64 + py3.12
#   bash install/fetch-vendor.sh --python 3.10 --platform x86_64-unknown-linux-gnu
#
# 产出：install/vendor/*.whl
# 目标机安装：bash install/install.sh --vendor
#=======================================================================
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VENDOR="$HERE/vendor"
PYVER="3.12"
PLATFORM="x86_64-unknown-linux-gnu"
SPEC="mcp>=2.1,<3"

while [ $# -gt 0 ]; do
  case "$1" in
    --python)   PYVER="$2"; shift 2;;
    --python=*) PYVER="${1#--python=}"; shift;;
    --platform) PLATFORM="$2"; shift 2;;
    --platform=*) PLATFORM="${1#--platform=}"; shift;;
    --spec)     SPEC="$2"; shift 2;;
    --spec=*)   SPEC="${1#--spec=}"; shift;;
    -h|--help)  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "未知参数: $1" >&2; exit 2;;
  esac
done

mkdir -p "$VENDOR"
rm -f "$VENDOR"/*.whl

if command -v uv >/dev/null 2>&1; then
  # uv 支持跨平台解析
  UV_CACHE_DIR="${UV_CACHE_DIR:-$HERE/../.uvcache}" \
  uv pip download --help >/dev/null 2>&1 || true
  TMP=$(mktemp -d)
  UV_CACHE_DIR="${UV_CACHE_DIR:-$HERE/../.uvcache}" \
    uv pip install --target "$TMP" \
      --python-platform "$PLATFORM" --python-version "$PYVER" \
      --only-binary :all: "$SPEC" >/dev/null
  # 反查回 wheel 不方便时，直接打包解包后的目录
  rm -rf "$HERE/site"
  mv "$TMP" "$HERE/site"
  echo "[fetch-vendor] 已生成解包目录 $HERE/site（install.sh --vendor 会直接复制它）"
else
  echo "[fetch-vendor] 未找到 uv，改用 pip（只能取本机平台的 wheel）" >&2
  python3 -m pip download -d "$VENDOR" --only-binary :all: "$SPEC"
  echo "[fetch-vendor] 已生成 $VENDOR/*.whl"
fi
