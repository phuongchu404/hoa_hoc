#!/usr/bin/env bash
# Tắt ChemImage → ChemDraw đang chạy (server ở cổng 8000 và Vite nếu đang ở chế độ dev).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pids() {
  { pgrep -f "uvicorn app.main:app" 2>/dev/null
    pgrep -f "$ROOT/frontend/node_modules/.bin/vite" 2>/dev/null
    pgrep -f "$ROOT/frontend/node_modules/vite/bin/vite.js" 2>/dev/null
  } | sort -u
}

running="$(pids)"
if [ -z "$running" ]; then
  echo "ChemImage không chạy — không có gì để tắt."
  exit 0
fi

echo "→ Đang tắt ChemImage (tiến trình: $(echo $running | tr '\n' ' '))…"
kill $running 2>/dev/null
for _ in 1 2 3 4 5 6 7 8 9 10; do
  sleep 0.5
  [ -z "$(pids)" ] && { echo "✓ Đã tắt."; exit 0; }
done
# still alive after 5 s: force
left="$(pids)"
[ -n "$left" ] && kill -9 $left 2>/dev/null
sleep 0.5
if [ -z "$(pids)" ]; then
  echo "✓ Đã tắt (buộc dừng)."
else
  echo "✗ Không tắt được. Mở Activity Monitor, tìm 'python' hoặc 'uvicorn' rồi bấm Force Quit."
  exit 1
fi
