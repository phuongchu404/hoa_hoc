#!/usr/bin/env bash
# Double-click in Finder to stop ChemImage → ChemDraw.
cd "$(dirname "$0")" && ./scripts/stop.sh
echo
read -r -t 5 -p "Cửa sổ này sẽ tự đóng sau 5 giây…" _ 2>/dev/null || true
