# Hướng dẫn chạy ChemImage → ChemDraw

Tài liệu này hướng dẫn từng bước: cài đặt, chạy, sử dụng, đưa kết quả vào ChemDraw và xử lý lỗi thường gặp.
Mọi lệnh bên dưới gõ trong ứng dụng **Terminal** của macOS.

---

## Mục lục

1. [Yêu cầu hệ thống](#1-yêu-cầu-hệ-thống)
2. [Cài đặt lần đầu](#2-cài-đặt-lần-đầu)
3. [Khởi động ứng dụng](#3-khởi-động-ứng-dụng)
4. [Sử dụng](#4-sử-dụng)
5. [Đưa kết quả vào ChemDraw](#5-đưa-kết-quả-vào-chemdraw)
6. [Tắt ứng dụng](#6-tắt-ứng-dụng)
7. [Xử lý lỗi thường gặp](#7-xử-lý-lỗi-thường-gặp)
8. [Cấu hình nâng cao](#8-cấu-hình-nâng-cao)
9. [Kiểm thử và phát triển](#9-kiểm-thử-và-phát-triển)
10. [Chuyển sang máy khác / gỡ cài đặt](#10-chuyển-sang-máy-khác--gỡ-cài-đặt)

---

## 1. Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | macOS 12 trở lên. Chip Apple Silicon (M1/M2/M3…) chạy nhanh nhất; chip Intel vẫn chạy được nhưng chậm hơn |
| RAM | Tối thiểu 8 GB, khuyến nghị 16 GB |
| Ổ đĩa trống | Khoảng **4 GB**: model ~1.5 GB, thư viện Python ~1 GB, thư viện giao diện ~0.5 GB |
| Node.js | Phiên bản 20 trở lên. Chỉ cần lúc cài đặt để build giao diện |
| Internet | **Chỉ cần ở lần cài đặt đầu tiên**. Sau đó chạy hoàn toàn offline |
| ChemDraw | Không bắt buộc. Nếu có cài (đã thử với ChemDraw 21), nút "Mở trong ChemDraw" sẽ mở thẳng file |

Python **không cần cài trước**: script cài đặt tự cài Python 3.11 qua công cụ `uv`.

### Kiểm tra Node.js

```bash
node --version
```

Nếu báo `command not found` hoặc phiên bản dưới `v20`, cài Node bằng Homebrew:

```bash
brew install node
```

Nếu chưa có Homebrew, tải Node.js bản LTS tại https://nodejs.org rồi cài như ứng dụng thông thường.

---

## 2. Cài đặt lần đầu

### Bước 1 — Mở Terminal tại thư mục dự án

```bash
cd ~/phuongcm/hoa_hoc
```

### Bước 2 — Chạy script cài đặt

```bash
./scripts/setup.sh
```

Script tự làm lần lượt các việc sau (mất khoảng 5–15 phút tuỳ tốc độ mạng):

| Bước | Việc làm | Ghi chú |
|---|---|---|
| 1 | Cài `uv` nếu chưa có | Dùng Homebrew nếu có, không thì tải từ astral.sh |
| 2 | Tạo môi trường Python 3.11 tại `backend/.venv` | Không ảnh hưởng Python khác trên máy |
| 3 | Cài thư viện Python (PyTorch, RDKit, FastAPI…) | Khoảng 1 GB |
| 4 | Cài MolScribe và RxnScribe từ GitHub | Phiên bản đã cố định |
| 5 | Tải 2 file model vào `backend/models/` | ~1.1 GB + ~0.4 GB. Đã có thì bỏ qua |
| 6 | Cài thư viện giao diện và build vào `frontend/dist/` | |

Khi thấy dòng sau là đã cài xong:

```
✓ Xong. Chạy ứng dụng bằng: ./scripts/start.sh
```

> Script chạy lại nhiều lần được. Nếu cài bị gián đoạn (mất mạng…), chỉ cần chạy lại `./scripts/setup.sh`.

---

## 3. Khởi động ứng dụng

Có hai cách, chọn một.

### Cách A — Nhấp đúp trong Finder (dễ nhất)

1. Mở thư mục `hoa_hoc` trong Finder.
2. Nhấp đúp file **`ChemImage.command`**.
3. Một cửa sổ Terminal mở ra. **Giữ cửa sổ này mở** trong suốt thời gian dùng.

> **Lần đầu**, macOS có thể chặn với thông báo "không thể mở vì không xác định được nhà phát triển". Khi đó:
> chuột phải vào `ChemImage.command` → **Open** → bấm **Open** lần nữa. Các lần sau nhấp đúp bình thường.

### Cách B — Dùng Terminal

```bash
cd ~/phuongcm/hoa_hoc
./scripts/start.sh
```

### Sau khi khởi động

- Model mất khoảng **10 giây** để nạp. Xong là trình duyệt **tự mở** trang:

  **http://127.0.0.1:8000**

- Góc trên trang hiện chấm xanh **"Sẵn sàng · MPS+CPU · offline"** là dùng được.
  - Nếu hiện "Đang nạp model…", đợi thêm vài giây.
  - Chip **"ChemDraw ✓"** nghĩa là ứng dụng đã tìm thấy ChemDraw trên máy.
- Nếu trình duyệt không tự mở, bạn tự gõ địa chỉ trên vào Chrome/Safari.

---

## 4. Sử dụng

### 4.1. Đưa ảnh vào

Chọn một trong ba cách:

| Cách | Thao tác |
|---|---|
| Kéo thả | Kéo file ảnh từ Finder thả vào trang |
| Dán | Copy ảnh (hoặc chụp màn hình vào clipboard bằng **⌘ ⇧ ⌃ 4**), rồi vào trang nhấn **⌘ V** hoặc bấm nút **"Dán ảnh ⌘V"**. Dán được cả khi đã có kết quả của ảnh trước và khi con trỏ đang ở trong ô nhập liệu |
| Chọn file | Bấm nút **"Chọn ảnh"** ở góc trên phải |

- Định dạng hỗ trợ: PNG, JPG, GIF, BMP, TIFF, WEBP. Tối đa 25 MB.
- Ảnh có thể là một phân tử, một sơ đồ phản ứng, hoặc nhiều phản ứng.
- Thời gian xử lý thường 1–3 giây.

> **Ảnh độ phân giải thấp** (mỗi liên kết dưới ~25 px) sẽ có thông báo ở đầu kết quả. Khung cấu trúc thường vẫn đúng, nhưng nhãn (Boc, TBDPSO…) có thể được "đoán" từ chữ đọc mờ (có cảnh báo trên thẻ) và lập thể (nêm/gạch) dễ bị mất. Hãy kiểm tra các thẻ màu vàng.
>
> **Mẹo để có kết quả tốt:** dùng ảnh chụp màn hình từ PDF hoặc bài báo, đủ nét, không nghiêng. Phóng to tài liệu trước khi chụp sẽ cho kết quả chính xác hơn.

### 4.2. Đọc kết quả

**Bên trái** là ảnh gốc, có khung đánh dấu:

| Ký hiệu | Ý nghĩa |
|---|---|
| Khung **xanh lá** | Phân tử nhận dạng tốt |
| Khung **vàng** | Cần xem lại (độ tin cậy thấp, hoặc hai lần đọc cho kết quả khác nhau) |
| Khung **đỏ** | Cấu trúc lỗi (sai hóa trị…), cần sửa |
| Khung nét đứt tím | Chữ điều kiện phản ứng |
| Mũi tên xanh | Mũi tên phản ứng đã phát hiện |

Bấm vào một khung để cuộn tới thẻ kết quả tương ứng.

**Bên phải** là kết quả, chia theo từng phản ứng: chất tham gia → mũi tên kèm điều kiện → sản phẩm.
Mỗi thẻ phân tử hiển thị:
- công thức phân tử, khối lượng mol, SMILES;
- độ tin cậy (%);
- cảnh báo nếu có;
- "Phương án khác" khi hai lần đọc không khớp. Bấm vào phương án để thay thế cấu trúc.

### 4.3. Sửa kết quả

| Việc cần làm | Thao tác |
|---|---|
| Sửa cấu trúc | Bấm **Sửa** trên thẻ → trình vẽ Ketcher mở ra → chỉnh → bấm **Lưu cấu trúc**. SMILES, công thức và file xuất tự cập nhật |
| Sửa chữ điều kiện | Gõ trực tiếp vào ô điều kiện cạnh mũi tên |
| Thêm phân tử bị sót | Bấm **"+ Chọn vùng"** → kéo chuột khoanh quanh cấu trúc trên ảnh. Nhấn **Esc** để huỷ |
| Thêm phân tử từ SMILES | Gõ SMILES vào ô "Thêm phân tử từ SMILES…" cuối trang → **Thêm** |
| Xoá phân tử nhận nhầm | Bấm **Xoá** trên thẻ |

> Lần đầu mở trình vẽ Ketcher mất 2–5 giây (tải khoảng 28 MB từ máy local). Các lần sau nhanh hơn.

### 4.4. Tuỳ chọn "Giữ nhãn viết tắt"

- **Bật** (mặc định): CO2Et, Ph, Me, Boc… giữ dạng nhãn như trong ảnh. Trong ChemDraw, nhãn vẫn được hiểu đúng hóa học và có thể bung ra bằng *Expand Label*.
- **Tắt**: xuất mọi nguyên tử ra đầy đủ.

---

## 5. Đưa kết quả vào ChemDraw

| Nút | Kết quả | Khi nào dùng |
|---|---|---|
| **Mở tất cả trong ChemDraw** | Lưu file `.cdxml` rồi mở thẳng bằng ChemDraw | Cách nhanh và đầy đủ nhất |
| **Copy cho ChemDraw** | Copy toàn bộ sơ đồ. Mở ChemDraw và nhấn **⌘ V** | Dán vào một tài liệu ChemDraw đang làm |
| **Copy ChemDraw / Mở ChemDraw** trên từng thẻ | Như trên nhưng chỉ cho một phân tử | Lấy riêng một chất |
| **Tải xuống ▾** | `.cdxml` (ChemDraw), `.sdf` (tất cả phân tử), `.rxn` (phản ứng), `.smi` (SMILES) | Lưu trữ, dùng cho phần mềm khác |
| **SMILES / Copy reaction SMILES** | Copy chuỗi SMILES | Tra cứu (PubChem, Reaxys, SciFinder…) |

- File mở bằng ChemDraw được lưu tại: **`~/Documents/ChemImage Exports/`**
- Trong ChemDraw, mọi thứ đều sửa được: phân tử, nhãn, mũi tên, chữ điều kiện.
  - Muốn chỉnh bố cục theo chuẩn tạp chí: chọn tất cả rồi dùng *Structure → Clean Up Structure*, hoặc *File → Apply Document Settings from → ACS Document 1996*.
- Lưu ý: nút "Copy cho ChemDraw" copy dạng văn bản CDXML. Nếu dán vào Word hay Notes sẽ thấy mã XML; nó chỉ dành để dán vào ChemDraw.

---

## 6. Tắt ứng dụng

Ứng dụng chạy cho tới khi bạn tắt. **Đóng tab trình duyệt không tắt ứng dụng**: server vẫn chạy ngầm và giữ cổng 8000. Chọn một trong các cách sau.

| Cách | Thao tác | Khi nào dùng |
|---|---|---|
| **A. Nhấp đúp file tắt** (dễ nhất) | Trong Finder, mở thư mục `hoa_hoc` → nhấp đúp **`Tắt ChemImage.command`** | Mọi lúc, kể cả khi không biết ứng dụng đang chạy ở cửa sổ nào |
| **B. Ctrl + C** | Bấm vào cửa sổ Terminal đang chạy ứng dụng (cửa sổ hiện chữ `Uvicorn running on http://127.0.0.1:8000`) → nhấn **Ctrl + C** | Khi cửa sổ Terminal đó vẫn còn mở |
| **C. Lệnh tắt** | Mở Terminal bất kỳ, chạy `~/phuongcm/hoa_hoc/scripts/stop.sh` | Khi đang làm việc trong Terminal |
| **D. Đóng cửa sổ Terminal** | Đóng cửa sổ Terminal đang chạy ứng dụng. macOS hỏi *"Terminate running processes?"* → chọn **Terminate** | Cách nhanh, nhưng chỉ tắt được ứng dụng chạy trong chính cửa sổ đó |

Cách A và C làm cùng một việc. Chúng tìm mọi tiến trình của ứng dụng, kể cả server Vite khi đang ở chế độ phát triển, rồi tắt lần lượt:

1. Gửi lệnh tắt bình thường và đợi tối đa 5 giây.
2. Nếu tiến trình vẫn chưa dừng thì buộc dừng.
3. Báo kết quả: **"✓ Đã tắt."**, hoặc **"ChemImage không chạy — không có gì để tắt."** nếu ứng dụng vốn đã tắt.

```bash
~/phuongcm/hoa_hoc/scripts/stop.sh
```

### Kiểm tra ứng dụng đã tắt hẳn chưa

```bash
curl -s http://127.0.0.1:8000/api/health || echo "Đã tắt"
```

- In ra **"Đã tắt"** là ứng dụng đã dừng hẳn.
- Nếu in ra một dòng có `"ready":true` thì ứng dụng vẫn đang chạy. Khi đó dùng lại cách A hoặc C.

### Nếu vẫn không tắt được

1. Mở **Activity Monitor** (Spotlight: ⌘ + Space → gõ *Activity Monitor*).
2. Ô tìm kiếm góc trên phải: gõ **python**.
3. Chọn tiến trình có cột *User* là bạn và dùng nhiều bộ nhớ (khoảng 2–4 GB) → bấm nút **⊗** → **Force Quit**.

Hoặc dùng lệnh (tắt mọi tiến trình server của ứng dụng):

```bash
pkill -9 -f "uvicorn app.main:app"
```

### Bật lại sau khi tắt

Nhấp đúp **`ChemImage.command`** hoặc chạy `./scripts/start.sh` (xem [mục 3](#3-khởi-động-ứng-dụng)). Dữ liệu và cài đặt không bị mất khi tắt. Chỉ các kết quả nhận dạng đang lưu tạm trong bộ nhớ được làm mới.

---

## 7. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân / Cách xử lý |
|---|---|
| `./scripts/setup.sh: Permission denied` | Cấp quyền chạy: `chmod +x scripts/*.sh ChemImage.command` rồi chạy lại |
| `Cần Node.js ≥ 20` khi cài | Cài Node theo [mục 1](#kiểm-tra-nodejs) rồi chạy lại `./scripts/setup.sh` |
| `Thiếu model ...` khi khởi động | Model chưa tải xong. Chạy: `cd backend && source .venv/bin/activate && python scripts/download_models.py` |
| `address already in use` / cổng 8000 bận | Ứng dụng đang chạy ở cửa sổ khác: dùng luôn http://127.0.0.1:8000, hoặc nhấp đúp `Tắt ChemImage.command` rồi bật lại (xem [mục 6](#6-tắt-ứng-dụng)). Hoặc chạy ở cổng khác: `PORT=8010 ./scripts/start.sh` |
| Trang báo "Frontend chưa được build" | Chạy: `cd frontend && npm install && npm run build` |
| Trang mãi "Đang kết nối backend…" | Xem cửa sổ Terminal có báo lỗi không. Thử tắt rồi chạy lại `./scripts/start.sh` |
| macOS chặn `ChemImage.command` | Chuột phải → **Open** → **Open** (chỉ lần đầu) |
| Chip "Chưa thấy ChemDraw" | Ứng dụng tìm ChemDraw trong `/Applications`. Nếu ChemDraw nằm chỗ khác, file `.cdxml` vẫn được lưu và mở bằng ứng dụng mặc định. Bạn có thể tải `.cdxml` về rồi tự mở |
| Nhận dạng sai / khung vàng nhiều | Chụp lại ảnh nét hơn (phóng to tài liệu trước khi chụp), hoặc khoanh từng cấu trúc bằng "+ Chọn vùng", rồi sửa bằng nút **Sửa** |
| Nhấn ⌘V không có gì xảy ra | Clipboard chưa có ảnh: chuột phải vào ảnh → **Copy Image**, hoặc chụp bằng ⌘⇧⌃4. Copy *file* ảnh trong Finder chỉ dán được trên Chrome; nếu không được, dùng kéo thả. Có thể bấm nút **"Dán ảnh ⌘V"** (trình duyệt sẽ hỏi quyền đọc clipboard lần đầu) |
| Thiếu chữ điều kiện phản ứng | OCR dùng Apple Vision có sẵn trong macOS. Kiểm tra ảnh có đủ nét; có thể gõ thẳng vào ô điều kiện |
| Chậm trên máy chip Intel | Thử tắt chế độ đọc 2 lần: `CHEM_TTA=0 ./scripts/start.sh` (nhanh hơn khoảng 30%) |

**Xem log chi tiết:** toàn bộ log hiện trong cửa sổ Terminal đang chạy ứng dụng. Khi cần hỗ trợ, hãy copy phần log có chữ `ERROR`.

**Kiểm tra nhanh tình trạng backend:**

```bash
curl http://127.0.0.1:8000/api/health
```

Kết quả có `"ready":true` là backend hoạt động bình thường.

---

## 8. Cấu hình nâng cao

Đặt biến môi trường trước lệnh chạy, ví dụ:

```bash
CHEM_TTA=0 PORT=8010 ./scripts/start.sh
```

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PORT` | `8000` | Cổng web |
| `NO_BROWSER` | `0` | Đặt `1` để không tự mở trình duyệt |
| `CHEM_TTA` | `1` | Đọc mỗi phân tử 2 lần để kiểm tra chéo. Đặt `0` để nhanh hơn |
| `CHEM_ACCELERATOR` | `auto` | Bộ tăng tốc cho encoder: `mps` (GPU Apple) / `cuda` / `none` (chỉ CPU) |
| `CHEM_DEVICE` | `cpu` | Thiết bị chạy decoder. Nên giữ `cpu`, vì nhanh nhất trên Mac |
| `CHEM_EXPORT_DIR` | `~/Documents/ChemImage Exports` | Thư mục lưu file mở bằng ChemDraw |
| `CHEM_LOW_CONFIDENCE` | `0.85` | Dưới ngưỡng độ tin cậy này, phân tử bị đánh dấu "cần xem lại" |
| `CHEM_MAX_UPLOAD_MB` | `25` | Dung lượng ảnh tối đa |

Ứng dụng chỉ lắng nghe trên `127.0.0.1`, nên máy khác trong mạng **không** truy cập được. Đây là thiết lập có chủ đích để bảo mật.

---

## 9. Kiểm thử và phát triển

### Chạy bộ test

```bash
cd ~/phuongcm/hoa_hoc/backend
source .venv/bin/activate
pytest                 # toàn bộ 67 test (~80 giây, gồm 29 hình mẫu 2007.docx)
pytest -m "not slow"   # chỉ test nhanh, không nạp model (~2 giây)
```

Test end-to-end dùng các ảnh mẫu trong `backend/tests/fixtures/`: `reaction_scheme.png` (2 phản ứng, ảnh nét), `multistep_scheme.png` (10 chất, 8 bước, ảnh mờ có mũi tên gấp khúc) và 29 hình trong `docx2007/` (lấy từ file 2007.docx). Các test kiểm tra:
- cấu trúc (SMILES) của từng chất đã được đối chiếu với hình vẽ;
- chữ điều kiện;
- tốc độ;
- file xuất CDXML, SDF, RXN.

### Chế độ phát triển (tự tải lại khi sửa code)

```bash
./scripts/dev.sh
```

- Mở **http://localhost:5173** (giao diện Vite, cập nhật ngay khi sửa code).
- Backend ở cổng 8000 tự khởi động lại khi sửa file Python.
- Sau khi sửa giao diện xong, build lại cho chế độ thường: `cd frontend && npm run build`.

### Tài liệu API

Khi ứng dụng đang chạy, xem tài liệu API tương tác tại **http://127.0.0.1:8000/docs**.

---

## 10. Chuyển sang máy khác / gỡ cài đặt

### Chuyển sang máy khác

1. Copy cả thư mục `hoa_hoc`. Có thể **bỏ qua** các thư mục sau cho nhẹ: `backend/.venv`, `frontend/node_modules`, `frontend/dist`. Script cài đặt sẽ tạo lại.
   - Nên **giữ** `backend/models/` (1.5 GB) để không phải tải model lại.
   - Máy mới không có mạng vẫn cài được nếu đã có sẵn model **và** thư viện. Nếu không, cần mạng ở bước cài.
2. Trên máy mới chạy `./scripts/setup.sh`, rồi `./scripts/start.sh`.

### Gỡ cài đặt

Dùng script gỡ cài đặt có sẵn. Script sẽ hỏi xác nhận trước khi xoá, và có chế độ xem trước.

**Bước 1 — Xem trước những gì sẽ bị xoá (không xoá gì):**

```bash
cd ~/phuongcm/hoa_hoc
./scripts/uninstall.sh --dry-run
```

**Bước 2 — Gỡ thật:**

```bash
./scripts/uninstall.sh
```

Script làm lần lượt:

| Bước | Việc làm | Có hỏi trước không |
|---|---|---|
| 1 | Xoá **toàn bộ thư mục dự án** (~3 GB: model 1.5 GB, môi trường Python ~1 GB, thư viện giao diện ~0.5 GB) | Có |
| 2 | Tắt ứng dụng nếu đang chạy | Chỉ sau khi đã đồng ý ở bước 1 |
| 3 | Xoá thư mục `~/Documents/ChemImage Exports` (các file `.cdxml` đã mở bằng ChemDraw) | Có, chọn N để giữ lại |
| 4 | Dọn bộ nhớ đệm gói Python (`~/.cache/uv`) | Có, mặc định **không** |
| 5 | Dọn bộ nhớ đệm npm (`~/.npm`) | Có, mặc định **không** |

> Bước 4 và 5 là bộ nhớ đệm **dùng chung** với các dự án khác trên máy. Xoá không làm hỏng gì, nhưng lần sau các dự án đó sẽ phải tải lại gói. Nếu máy còn dùng Python/Node cho việc khác, nên chọn **N**.

Script **không bao giờ** xoá: Homebrew, `uv`, Node.js, ChemDraw, và thư mục `~/.cache/huggingface` (có thể chứa model của phần mềm khác).

Nếu muốn gỡ luôn Python 3.11 do `uv` cài (chỉ khi không dự án nào khác dùng):

```bash
uv python uninstall 3.11
```

**Gỡ thủ công (không dùng script):** tắt ứng dụng rồi xoá hai thư mục:

```bash
pkill -f "uvicorn app.main:app"
rm -rf ~/phuongcm/hoa_hoc
rm -rf ~/Documents/"ChemImage Exports"
```

Ứng dụng không cài gì vào hệ thống (không có dịch vụ chạy nền, không tự khởi động cùng máy, không sửa cài đặt macOS). Vì vậy xoá các thư mục trên là gỡ sạch.
