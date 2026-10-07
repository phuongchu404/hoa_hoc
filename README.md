# ChemImage → ChemDraw

Chuyển ảnh cấu trúc hóa học hoặc sơ đồ phản ứng thành file **ChemDraw sửa được**. Toàn bộ xử lý chạy trên máy, không gửi dữ liệu ra ngoài. Chỉ cần mạng ở lần cài đặt đầu tiên.

- Nhận dạng **cấu trúc** (MolScribe): nhóm viết tắt (CO2Et, Ph, Boc, OTBS, N2…), lập thể E/Z và R/S (liên kết nêm/gạch), dị vòng.
- Nhận dạng **sơ đồ phản ứng** (RxnScribe): chất tham gia, sản phẩm, mũi tên.
- Đọc **điều kiện phản ứng** (Apple Vision OCR), tự sửa chỉ số dưới (Rh½(OAc)4 → Rh₂(OAc)₄).
- Xuất ra **CDXML gốc của ChemDraw**: giữ nhãn viết tắt dạng nickname, mũi tên, chữ điều kiện có chỉ số dưới, `<scheme>` phản ứng. Bố cục được dàn lại theo chuẩn ACS (liên kết 14.4 pt, chữ Arial 10 pt).
- Sửa cấu trúc ngay trong trình duyệt bằng **Ketcher** (chạy offline bằng WebAssembly).
- Ba cách đưa vào ChemDraw:
  - **Mở trong ChemDraw**: lưu file `.cdxml` rồi mở thẳng bằng ChemDraw.
  - **Copy cho ChemDraw**: sau đó chỉ cần nhấn ⌘V trong ChemDraw.
  - Tải về `.cdxml`, `.sdf`, `.rxn`, `.mol`, `.smi`.

## Cài đặt (một lần)

Yêu cầu: macOS (Apple Silicon hoặc Intel), Node.js ≥ 20, khoảng 6 GB trống. Python 3.11 được cài tự động qua `uv`.

```bash
./scripts/setup.sh
```

Script sẽ tạo môi trường Python, cài thư viện, tải model (khoảng 1.6 GB, vào `backend/models/`) rồi build giao diện.

## Chạy

```bash
./scripts/start.sh
```

Hoặc nhấp đúp file **`ChemImage.command`** trong Finder. Trình duyệt sẽ tự mở `http://127.0.0.1:8000` khi model đã nạp xong (khoảng 10 giây).

Tắt: nhấp đúp **`Tắt ChemImage.command`**, hoặc chạy `./scripts/stop.sh`, hoặc nhấn Ctrl + C trong cửa sổ Terminal đang chạy.

Cách dùng: kéo thả ảnh, dán ảnh bằng ⌘V (ví dụ sau khi chụp màn hình bằng ⌘⇧⌃4), hoặc bấm "Chọn ảnh".

- Khung xanh/vàng/đỏ trên ảnh cho biết độ tin cậy của từng phân tử. Bấm vào khung để xem thẻ kết quả tương ứng.
- **+ Chọn vùng**: kéo chuột quanh cấu trúc bị bỏ sót để nhận dạng riêng.
- **Sửa**: mở Ketcher. Sau khi lưu, SMILES, công thức phân tử, khối lượng phân tử và file xuất được cập nhật theo.
- Ô điều kiện phản ứng sửa trực tiếp được. Nội dung sửa sẽ đi vào file ChemDraw.
- **Giữ nhãn viết tắt**: bật thì CO2Et, Ph… giữ dạng nhãn giống ảnh. Tắt thì vẽ đầy đủ nguyên tử.

File đã mở trong ChemDraw được lưu ở `~/Documents/ChemImage Exports/`.

## Đóng gói thành ứng dụng Mac (cho người dùng không rành máy tính)

```bash
./packaging/macos/build.sh
```

Tạo ra `dist/ChemImage.app` và `dist/ChemImage-1.0.0-macOS-AppleSilicon.dmg` (khoảng 1.8 GB). File DMG chứa sẵn Python, thư viện, model, giao diện và [hướng dẫn cài đặt](packaging/macos/HUONG_DAN_CAI_DAT.md) dạng PDF. Người dùng chỉ cần kéo app vào Applications rồi nhấp đúp; không cần Terminal, không cần Internet.

- Chạy trên Mac chip Apple Silicon (M1 trở lên), macOS 12+.
- App ký ad-hoc, chưa công chứng với Apple. Lần đầu mở, người dùng vào *System Settings → Privacy & Security → Open Anyway* (xem hướng dẫn cài đặt).
- Lần mở đầu tiên mất khoảng 1 phút (macOS kiểm tra ứng dụng). Các lần sau khoảng 10 giây.
- Tắt: nút **Tắt chương trình** trên trang web, biểu tượng ⌬ trên thanh menu, chuột phải biểu tượng Dock → Thoát, hoặc ⌘Q. Đóng mọi tab ChemImage thì app tự tắt sau 2 phút.
- Đổi số phiên bản: `VERSION=1.1.0 ./packaging/macos/build.sh`.

## Gỡ cài đặt

```bash
./scripts/uninstall.sh --dry-run   # xem trước, không xoá gì
./scripts/uninstall.sh             # gỡ (hỏi xác nhận)
```

Chi tiết: mục 10 trong [HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md).

## Kiến trúc

```
frontend/  React + Vite + TypeScript (Ketcher editor, lazy-loaded)
backend/   FastAPI (Python 3.11) – phục vụ API + giao diện đã build trên cổng 8000
  app/pipeline.py            ảnh → Document (bố cục → phân tử → OCR → mũi tên)
  app/engines/               MolScribe, RxnScribe, Vision OCR
  app/chem/structure.py      graph → RDKit: mở rộng nhãn viết tắt, E/Z, R/S, kiểm tra hóa trị
  app/chem/abbreviations.py  từ điển ~150 nhãn viết tắt
  app/chem/cdxml.py          bộ ghi ChemDraw CDXML + dàn trang sơ đồ phản ứng
  app/chem/io.py             molfile (S-group SUP), SVG, công thức, InChI
  vendor/onmt/               phần nhỏ của OpenNMT-py mà MolScribe cần (MIT)
```

Tốc độ đo trên M1 Max với ảnh mẫu 2 phản ứng / 5 phân tử: khoảng **1.5 giây**. Encoder chạy trên GPU (MPS), decoder chạy trên CPU vì như vậy nhanh nhất. Mỗi phân tử được đọc 2 lần ở hai tỷ lệ khác nhau để tự kiểm tra chéo. Nếu hai lần cho kết quả khác nhau, thẻ phân tử sẽ hiện cảnh báo "cần xem lại" kèm phương án thay thế.

## Kiểm thử

```bash
cd backend && source .venv/bin/activate && pytest
```

Bộ test gồm 67 test (gồm 29 hình mẫu từ 2007.docx):

- Unit test cho phần hóa học.
- Test end-to-end trên `tests/fixtures/reaction_scheme.png`: kiểm tra SMILES chính xác của 5 phân tử, phân vai trong phản ứng, chữ điều kiện, tốc độ, và đọc lại CDXML bằng RDKit.

Đã kiểm tra thêm thủ công với **ChemDraw 21** (mở file và dán qua clipboard): ChemDraw nhận đủ 5 phân tử và 2 mũi tên, "Copy As SMILES" khớp 100%, lập thể giữ đúng (bao gồm menthol với 3 tâm lập thể).

## Giới hạn cần biết

- Ảnh in/vẽ bằng phần mềm cho kết quả tốt nhất. Ảnh chụp mờ, nghiêng hoặc độ phân giải thấp sẽ kém hơn. **Ảnh vẽ tay** độ chính xác thấp.
- Cấu trúc Markush, polymer, phức kim loại phức tạp, hoặc nhãn lạ không có trong từ điển sẽ được giữ thành nhóm R hoặc nhãn và có cảnh báo, cần sửa tay.
- Sơ đồ có mũi tên dọc hoặc nhiều tầng dùng bố cục theo vị trí trong ảnh, chưa được dàn lại tự động như sơ đồ ngang.
- OCR dùng Apple Vision nên chỉ có trên macOS. Trên hệ điều hành khác, phần chữ điều kiện sẽ để trống.

## Cấu hình (biến môi trường)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CHEM_ACCELERATOR` | `auto` | `mps` / `cuda` / `none` cho encoder |
| `CHEM_TTA` | `1` | đọc 2 lần để kiểm tra chéo (tắt = nhanh hơn ~30%) |
| `CHEM_EXPORT_DIR` | `~/Documents/ChemImage Exports` | nơi lưu file mở bằng ChemDraw |
| `PORT` | `8000` | cổng web |

Phát triển giao diện với hot-reload: `./scripts/dev.sh` (Vite chạy ở :5173, tự proxy `/api` sang :8000).

## Giấy phép thành phần

MolScribe, RxnScribe (MIT) · RDKit (BSD) · Ketcher (Apache-2.0) · OpenNMT-py (MIT) · FastAPI (MIT) · React (MIT).
