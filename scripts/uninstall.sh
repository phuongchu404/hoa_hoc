#!/usr/bin/env bash
# Gỡ cài đặt ChemImage → ChemDraw.
#   ./scripts/uninstall.sh            gỡ (hỏi xác nhận từng bước)
#   ./scripts/uninstall.sh --dry-run  chỉ liệt kê, không xoá gì
#   ./scripts/uninstall.sh --yes      không hỏi lại phần chính (dự án + file xuất)
# Không bao giờ đụng tới: Homebrew, uv, Node.js, ChemDraw, ~/.cache/huggingface
# (có thể chứa model của dự án khác).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY=0
YES=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  esac
done

# The script lives inside the folder it deletes: run from a temporary copy.
if [ -z "${CHEMIMAGE_UNINSTALL_COPY:-}" ] && [ "$DRY" = 0 ]; then
  tmp="$(mktemp -t chemimage-uninstall).sh"
  cp "$0" "$tmp"
  CHEMIMAGE_UNINSTALL_COPY=1 CHEMIMAGE_ROOT="$ROOT" exec bash "$tmp" "$@"
fi
ROOT="${CHEMIMAGE_ROOT:-$ROOT}"

EXPORTS="${CHEM_EXPORT_DIR:-$HOME/Documents/ChemImage Exports}"
size() { [ -e "$1" ] && du -sh "$1" 2>/dev/null | cut -f1 || echo "-"; }
ask() {  # ask "question" -> 0 if yes
  [ "$DRY" = 1 ] && return 1
  read -r -p "$1 [y/N] " ans </dev/tty 2>/dev/null || return 1
  [[ "$ans" =~ ^[YyCc] ]]
}
remove() {  # remove path, honouring --dry-run
  if [ "$DRY" = 1 ]; then echo "   (dry-run) sẽ xoá: $1"; else rm -rf "$1" && echo "   ✓ đã xoá: $1"; fi
}

case "$ROOT" in
  "$HOME"|"/"|"") echo "Thư mục dự án không hợp lệ: '$ROOT'"; exit 1 ;;
esac
if [ ! -f "$ROOT/backend/app/main.py" ] || [ ! -d "$ROOT/frontend" ]; then
  echo "Không nhận ra '$ROOT' là thư mục ChemImage → ChemDraw. Dừng lại để an toàn."
  exit 1
fi

echo "== Gỡ cài đặt ChemImage → ChemDraw =="
[ "$DRY" = 1 ] && echo "(chế độ xem trước: không xoá gì)"
echo
echo "Sẽ xoá:"
printf "  %-48s %8s\n" "$ROOT  (toàn bộ dự án)" "$(size "$ROOT")"
printf "     %-45s %8s\n" "trong đó model  backend/models" "$(size "$ROOT/backend/models")"
printf "     %-45s %8s\n" "môi trường Python  backend/.venv" "$(size "$ROOT/backend/.venv")"
printf "     %-45s %8s\n" "thư viện giao diện  frontend/node_modules" "$(size "$ROOT/frontend/node_modules")"
printf "  %-48s %8s\n" "$EXPORTS  (file đã mở bằng ChemDraw)" "$(size "$EXPORTS")"
echo

# 1. project + exports (the running app is stopped only after confirmation)
if [ "$YES" = 1 ] || ask "Xoá thư mục dự án và file xuất ở trên?"; then
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    echo "→ Tắt ứng dụng đang chạy…"
    pkill -f "uvicorn app.main:app" || true
  fi
  if [ -d "$EXPORTS" ]; then
    if [ "$YES" = 1 ] || ask "  Xoá luôn các file .cdxml đã xuất trong $EXPORTS?"; then
      remove "$EXPORTS"
    else
      echo "   giữ lại: $EXPORTS"
    fi
  fi
  remove "$ROOT"
else
  if [ "$DRY" = 1 ]; then
    pgrep -f "uvicorn app.main:app" >/dev/null 2>&1 && echo "   (dry-run) sẽ tắt ứng dụng đang chạy"
    echo "   (dry-run) sẽ xoá: $EXPORTS (nếu đồng ý) và $ROOT"
  else
    echo "Đã huỷ. Không xoá gì."; exit 0
  fi
fi

# 2. optional shared caches (also used by other projects)
echo
echo "Tuỳ chọn — bộ nhớ đệm DÙNG CHUNG với dự án khác (xoá thì lần sau các dự án đó tải lại):"
UV_CACHE="$(uv cache dir 2>/dev/null || echo "$HOME/.cache/uv")"
printf "  %-48s %8s\n" "$UV_CACHE  (gói Python đã tải)" "$(size "$UV_CACHE")"
printf "  %-48s %8s\n" "$HOME/.npm  (gói Node.js đã tải)" "$(size "$HOME/.npm")"
TORCH_CK="$HOME/.cache/torch/hub/checkpoints/resnet50-0676ba61.pth"
[ -e "$TORCH_CK" ] && printf "  %-48s %8s\n" "$TORCH_CK" "$(size "$TORCH_CK")"
if ask "Dọn bộ nhớ đệm gói Python (uv cache clean)?"; then
  uv cache clean >/dev/null 2>&1 && echo "   ✓ đã dọn uv cache" || remove "$UV_CACHE"
fi
if ask "Dọn bộ nhớ đệm npm (npm cache clean --force)?"; then
  npm cache clean --force >/dev/null 2>&1 && echo "   ✓ đã dọn npm cache" || true
fi
if [ -e "$TORCH_CK" ] && ask "Xoá $TORCH_CK?"; then remove "$TORCH_CK"; fi

echo
echo "Không đụng tới: Homebrew, uv, Node.js, ChemDraw, ~/.cache/huggingface."
echo "Python 3.11 do uv cài vẫn còn (dùng chung); muốn gỡ: uv python uninstall 3.11"
echo "Xong."
