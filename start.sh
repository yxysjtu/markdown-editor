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
  read -r -p "Press Enter to close..."
  exit 1
}

if [ -n "$1" ]; then
  FOLDER=$(cd "$1" 2>/dev/null && pwd -W) || fail "Folder not found: $1"
  URL="$URL?root=$(python -c 'import sys, urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$FOLDER")"
fi

cd "$(dirname "$0")" || fail "Could not find the editor folder"

if (exec 3<>"/dev/tcp/localhost/$PORT") 2>/dev/null; then
  echo "The editor is already running. Opening: $URL"
  start chrome "$URL"
  read -r -t 3 -p "This window closes in 3 seconds..."
  exit 0
fi

(
  sleep 1 # 等服务启动
  start chrome "$URL"
) &
python editor.py "$PORT" || fail "Could not start the editor. If a module is missing, run: pip install -r requirements.txt"
