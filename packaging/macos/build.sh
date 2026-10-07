#!/usr/bin/env bash
# Build dist/ChemImage.app and dist/ChemImage-<version>-macOS-AppleSilicon.dmg
# Requirements on the build machine: ./scripts/setup.sh done once (models,
# frontend, Python 3.11 via uv), Xcode command line tools (clang).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/packaging/macos"
VERSION="${VERSION:-1.0.0}"
DIST="$ROOT/dist"
APP="$DIST/ChemImage.app"
RES="$APP/Contents/Resources"
MOLSCRIBE_REF=7296a30413eb55436702011efdff78131f66d162
RXNSCRIBE_REF=ad6b1c75d40e563e68deca0491918885948d69c7

step() { printf "\n\033[1m→ %s\033[0m\n" "$*"; }

[ "$(uname -m)" = arm64 ] || { echo "Cần build trên Mac chip Apple Silicon"; exit 1; }
for f in swin_base_char_aux_1m680k.pth pix2seq_reaction_full.ckpt; do
  [ -f "$ROOT/backend/models/$f" ] || { echo "Thiếu model $f — chạy ./scripts/setup.sh trước"; exit 1; }
done

step "Build giao diện"
(cd "$ROOT/frontend" && { [ -d node_modules ] || npm ci; } && npm run build >/dev/null)

step "Tạo khung ứng dụng"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES"
sed "s/__VERSION__/$VERSION/g" "$HERE/Info.plist" > "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

step "Python 3.11 độc lập"
PYSRC="$(cd "$(dirname "$(uv python find 3.11)")/.." && pwd -P)"
cp -R "$PYSRC" "$RES/python"
PY="$RES/python/bin/python3.11"
rm -f "$RES/python/lib/python3.11/EXTERNALLY-MANAGED"
"$PY" -c "import sys; assert sys.version_info[:2] == (3, 11)"

step "Cài thư viện vào app (dùng bộ đệm uv, không tải lại nếu đã có)"
uv pip install -q --python "$PY" -r "$ROOT/backend/requirements.txt"
uv pip install -q --python "$PY" --no-deps \
  "molscribe @ git+https://github.com/thomas0809/MolScribe.git@${MOLSCRIBE_REF}" \
  "rxnscribe @ git+https://github.com/thomas0809/RxnScribe.git@${RXNSCRIBE_REF}"

step "Chép mã nguồn, model, giao diện"
mkdir -p "$RES/backend" "$RES/frontend"
cp -R "$ROOT/backend/app" "$ROOT/backend/vendor" "$RES/backend/"
mkdir -p "$RES/backend/models"
cp "$ROOT/backend/models/"*.pth "$ROOT/backend/models/"*.ckpt "$RES/backend/models/"
cp -R "$ROOT/frontend/dist" "$RES/frontend/dist"

step "Biểu tượng"
"$ROOT/backend/.venv/bin/python" "$HERE/make_icon.py" "$RES/AppIcon.icns"
rm -f "$RES/AppIcon.png"

step "Biên dịch trình khởi động"
clang -O2 -arch arm64 -mmacosx-version-min=12.0 \
  -I "$RES/python/include/python3.11" "$HERE/launcher.c" \
  -L "$RES/python/lib" -lpython3.11 \
  -Wl,-rpath,@executable_path/../Resources/python/lib \
  -o "$APP/Contents/MacOS/ChemImage"

step "Dọn bớt dung lượng"
SP="$RES/python/lib/python3.11/site-packages"
rm -rf "$SP"/torch/include "$SP"/torch/share/cmake "$SP"/torch/test 2>/dev/null || true
find "$RES" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
# (keep *.pyi: scikit-image loads its lazy imports from __init__.pyi)
find "$RES" -name "*.a" -delete 2>/dev/null || true
rm -rf "$RES/python/lib/python3.11/test" "$RES/python/lib/python3.11/idlelib" "$RES/python/lib/python3.11/ensurepip"

step "Biên dịch trước mã Python (khởi động nhanh hơn)"
"$PY" -m compileall -q -j 0 "$RES/backend" "$SP" "$RES/python/lib/python3.11" >/dev/null 2>&1 || true

step "Kiểm tra nhanh trong app"
PYTHONPATH="$RES/backend" "$PY" -c "
import app.main, app.desktop, molscribe, rxnscribe, torch, rdkit, Vision
print('  imports ok — torch', torch.__version__, '| mps', torch.backends.mps.is_available())"

step "Ký ad-hoc (bắt buộc với Apple Silicon)"
codesign --force --deep --sign - "$APP" 2>/dev/null
codesign --verify --deep --strict "$APP" && echo "  chữ ký hợp lệ"

step "Đóng gói DMG"
STAGE="$DIST/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
[ -f "$HERE/HUONG_DAN_CAI_DAT.pdf" ] && cp "$HERE/HUONG_DAN_CAI_DAT.pdf" "$STAGE/Hướng dẫn cài đặt.pdf"
DMG="$DIST/ChemImage-$VERSION-macOS-AppleSilicon.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "ChemImage" -srcfolder "$STAGE" -fs APFS -format ULMO "$DMG"
rm -rf "$STAGE"

echo
echo "✓ App: $APP  ($(du -sh "$APP" | cut -f1))"
echo "✓ DMG: $DMG  ($(du -sh "$DMG" | cut -f1))"
