#!/usr/bin/env bash
# 一键打开编辑器。用法：bash start.sh [文件夹]，也可以在资源管理器里双击。按 Ctrl+C 停止。
# 编辑器已经在运行时，只会再打开一个窗口，不会重复启动。

PORT=${PORT:-8001} # 8001 被占用时可以换端口：PORT=8002 bash start.sh
URL="http://localhost:$PORT/"

export PYTHONUTF8=1 # 否则 Git Bash 里中文提示会乱码

# 双击运行时窗口会立刻关闭，出错要停一下才能看到原因
fail() {
  echo
  echo "$1"
  read -r -p "按回车键关闭..."
  exit 1
}

if [ -n "$1" ]; then
  FOLDER=$(cd "$1" 2>/dev/null && pwd -W) || fail "找不到文件夹：$1"
  URL="$URL?root=$(python -c 'import sys, urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$FOLDER")"
fi

cd "$(dirname "$0")" || fail "找不到编辑器所在的文件夹"

if (exec 3<>"/dev/tcp/localhost/$PORT") 2>/dev/null; then
  echo "编辑器已在运行，直接打开：$URL"
  start chrome "$URL"
  read -r -t 3 -p "3 秒后自动关闭此窗口..."
  exit 0
fi

(
  sleep 1 # 等服务启动
  start chrome "$URL"
) &
python editor.py "$PORT" || fail "编辑器启动失败。如果提示缺少模块，请先运行：pip install -r requirements.txt"
