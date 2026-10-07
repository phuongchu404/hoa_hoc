# Hướng dẫn cài đặt ChemImage

ChemImage chuyển ảnh công thức cấu tạo và sơ đồ phản ứng thành bản vẽ ChemDraw có thể chỉnh sửa. Mọi xử lý diễn ra **ngay trên máy của bạn**. Chương trình không cần Internet và không gửi ảnh đi đâu.

## Máy cần có

| Yêu cầu | Chi tiết |
|---|---|
| Máy | Mac chip **Apple M1, M2, M3, M4** trở lên (không chạy trên Mac chip Intel) |
| macOS | 12 (Monterey) trở lên |
| Bộ nhớ trống | Khoảng **3 GB** |
| ChemDraw | Không bắt buộc. Nếu có, chương trình mở kết quả thẳng bằng ChemDraw |

Cách xem máy dùng chip gì: bấm biểu tượng **Apple** ở góc trên bên trái màn hình → **About This Mac** (Giới thiệu về máy Mac này) → dòng **Chip** phải ghi *Apple M…*.

## Bước 1 — Cài đặt

1. Nhấp đúp file **ChemImage-…-macOS-AppleSilicon.dmg**. Một cửa sổ hiện ra, có biểu tượng **ChemImage** và thư mục **Applications**.
2. **Kéo biểu tượng ChemImage thả vào thư mục Applications.** Đợi khoảng 1 phút để máy chép xong.
3. Đóng cửa sổ đó. Ở thanh bên trái của Finder, bấm nút ⏏ cạnh chữ **ChemImage** để tháo ổ đĩa ảo.

## Bước 2 — Mở lần đầu (chỉ làm một lần)

ChemImage không mua chứng nhận của Apple, nên lần đầu mở, macOS sẽ chặn với thông báo *"Apple không thể xác minh ChemImage…"*. Bạn làm như sau:

1. Mở **Applications** (Ứng dụng), nhấp đúp **ChemImage**. Khi thông báo hiện ra, bấm **Done** (Xong). **Không** bấm *Move to Trash*.
2. Bấm biểu tượng **Apple** → **System Settings** (Cài đặt hệ thống) → **Privacy & Security** (Quyền riêng tư & Bảo mật).
3. Kéo xuống dưới cùng. Bạn sẽ thấy dòng *"ChemImage was blocked…"*. Bấm **Open Anyway** (Vẫn mở).
4. Nhập mật khẩu máy (hoặc dùng Touch ID), rồi bấm **Open Anyway** thêm một lần nữa.

> **Trên macOS 14 trở về trước:** chỉ cần **chuột phải** (hoặc giữ phím Control rồi bấm) vào ChemImage → **Open** → bấm **Open**.

Từ lần sau, chỉ cần nhấp đúp ChemImage như mọi ứng dụng khác. Có thể kéo ChemImage xuống thanh Dock để mở nhanh hơn.

## Bước 3 — Sử dụng

1. Mở ChemImage. Một **cửa sổ nhỏ** hiện ra với dòng *"Đang khởi động…"*. **Lần đầu tiên** có thể mất **1–2 phút** vì macOS kiểm tra ứng dụng mới; các lần sau chỉ khoảng 10 giây. Đừng tắt trong lúc chờ.
2. Trình duyệt (Safari hoặc Chrome) **tự mở** trang ChemImage.
3. Đưa ảnh vào bằng một trong ba cách:
   - **kéo thả** file ảnh vào trang;
   - chụp màn hình bằng **⌘ + Shift + Control + 4** rồi vào trang nhấn **⌘ + V**;
   - bấm **Chọn ảnh**.
4. Sau 1–3 giây, kết quả hiện ra:
   - khung **xanh** là nhận dạng tốt;
   - khung **vàng** là cần kiểm tra lại;
   - khung **đỏ** là chương trình không đọc được.
5. Bấm **Mở tất cả trong ChemDraw**, hoặc **Copy cho ChemDraw** rồi nhấn ⌘ + V trong ChemDraw.

Nếu lỡ đóng trang trình duyệt, bấm biểu tượng **⌬** trên thanh menu → **Mở giao diện ChemImage**, hoặc nhấp đúp lại ChemImage trong Applications.

## Tắt chương trình

Chọn một cách bất kỳ:

- Trên trang ChemImage ở trình duyệt, bấm nút **Tắt chương trình** (góc trên bên phải).
- Bấm biểu tượng **⌬** trên thanh menu (góc trên bên phải màn hình) → **Thoát ChemImage**.
- **Chuột phải** vào biểu tượng ChemImage dưới Dock → **Thoát ChemImage**.
- Bấm **Thoát** trên cửa sổ nhỏ của ChemImage, hoặc đóng cửa sổ nhỏ đó.

> **Đóng trình duyệt thì sao?** Khi bạn đóng mọi trang ChemImage trên trình duyệt, chương trình **tự tắt sau khoảng 2 phút**. Nếu chỉ lỡ tay đóng trang, mở lại trong 2 phút này bằng biểu tượng **⌬** → **Mở giao diện ChemImage**.

## Gỡ cài đặt

1. Tắt ChemImage.
2. Mở **Applications**, kéo **ChemImage** vào **Thùng rác**.
3. Nếu muốn, xoá thêm thư mục **Documents → ChemImage Exports** (chứa các file đã mở bằng ChemDraw).

## Gặp sự cố?

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy nút *Open Anyway* | Mở ChemImage thêm một lần để macOS ghi nhận, rồi quay lại **Privacy & Security** |
| Báo *"ChemImage is damaged"* (hỏng) | File tải về bị lỗi giữa chừng. Hãy tải lại file .dmg |
| Cửa sổ nhỏ báo *"Lỗi khi khởi động"* | Thoát rồi mở lại. Nếu vẫn lỗi, gửi cho người hỗ trợ thư mục **Library → Logs → ChemImage** (trong Finder: menu **Go** → giữ phím **Option** → **Library**) |
| Trình duyệt không tự mở | Bấm biểu tượng **⌬** trên thanh menu → **Mở giao diện ChemImage** |
| Trang báo *"ChemImage đã tắt"* | Chương trình đã được tắt, hoặc tự tắt vì không có trang nào mở quá 2 phút. Mở lại ChemImage trong Applications |
| Nhận dạng sai nhiều | Chụp ảnh nét hơn (phóng to tài liệu trước khi chụp), rồi sửa bằng nút **Sửa** trên từng kết quả |
