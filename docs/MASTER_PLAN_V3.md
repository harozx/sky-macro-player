# Kế hoạch cải tiến toàn diện — Sky Macro Player v3

Ngày: 17/10/2026. Tài liệu này kế thừa `IMPROVEMENT_PLAN.md` và
`REVIEW_PLAN_V2.md` (đã xử lý xong phần ổn định lõi) và đặt hướng cho v3:
**dọn kiến trúc, bổ sung tính năng tiện lợi, phát hành dạng .exe dùng ngay**.
`UI_DESIGN.md` vẫn là nguồn thiết kế; các hạng mục UI phải qua skill
`frontend-design` trước khi làm.

---

## 1. Hiện trạng đã kiểm chứng

| Hạng mục | Kết quả |
| --- | --- |
| Test suite | **85 passed** (Qt offscreen, `.venv`, 16 s) |
| Thư viện | 118 sheet (≈110 file `.txt` UTF‑16 LE, 8 file JSON UTF‑8); 112 phát được, 6 bị chặn vì `2Key*`/`3Key*` |
| Engine phát | `macro_core.py` tốt: lập lịch monotonic tuyệt đối, nhả phím chắc chắn, guard focus trong đường gửi phím, không replay hợp âm |
| Dữ liệu | Ghi JSON nguyên tử, backup file hỏng, schema version 3 |
| Git | **Toàn bộ v2 chưa được commit**: 7 file sửa + 22 file/thư mục mới. Đây là rủi ro mất dữ liệu lớn nhất hiện nay |

### 1.1 Nợ kỹ thuật chính

1. **Chuỗi kế thừa UI 4 tầng**: `sky_ui_window.MainWindow` →
   `sky_ui_integrated` → `sky_ui_polish` → `sky_ui_final`, cộng
   `sky_ui_core`/`sky_ui_shell`. Mỗi tầng thay widget, nối lại signal, ghi đè
   `_state_changed`/`play_song`/`closeEvent`. Khó đọc, dễ hồi quy.
2. **Code trùng lặp**: hai `PlaybackWorker` + hai `PlaybackController`
   (`sky_ui_core.py:193,220` và `sky_ui_integrated.py:129,201`); hai kho yêu
   thích (`JsonFavoritesStore` và `RepositoryFavoritesStore`); `NoteRunway` và
   `StaffNoteRunway`.
3. **Hai bộ phân tích sheet**: `SheetRepository._parse` (chấp nhận `key` là
   list) và `MacroPlayer._validated_notes` (chỉ chấp nhận chuỗi). Engine nhận
   dict thô thay vì `SongSheet` đã kiểm tra → cùng một file có thể "hợp lệ" ở
   thư viện nhưng lỗi khi phát.
4. **Dịch vá sau render**: `sky_ui_polish._translate_dynamic_controls` sửa chữ
   sau khi widget đã tạo; `sky_ui_core.py` còn `import sys` lặp.
5. **`gui.py` (Tkinter, 1273 dòng)** vẫn nằm ở gốc dù launcher không dùng.
6. **Đường dẫn dữ liệu phụ thuộc chế độ chạy**: chạy từ source thì cấu hình
   nằm cạnh mã nguồn; chạy bản cài thì nằm trong `%LOCALAPPDATA%`.

### 1.2 Khoảng trống trải nghiệm người dùng

- **Mất tính năng so với bản Tkinter cũ**: không còn *Phát tất cả*, *Trộn
  bài*, *Phát tất cả yêu thích* (grep `shuffle|play_all|repeat` trong
  `sky_ui_*.py` = 0 kết quả).
- **Tìm kiếm không bỏ dấu**: `LibraryPage.apply_filter` chỉ `casefold()`, nên
  gõ `bang khuang` không ra *Bâng khuâng*. Với 100+ tên tiếng Việt, đây là ma
  sát lớn nhất khi tìm bài.
- Trạng thái "không có kết quả" chỉ hiện bằng tooltip, không có empty state.
- Không có tốc độ phát, lặp bài, lặp đoạn, tua/bắt đầu từ giữa bài.
- Không có cách thêm sheet trong app: phải tự chép file vào `sheets/`.
- Không xem trước được bài (người dùng phải vào game mới biết bài ra sao).
- Không có thời lượng / số nốt / độ khó trong danh sách.
- 6 bài `2Key/3Key` bị chặn mà không có lối ra cho người dùng.
- README nhắc Heartopia nhưng khóa focus chỉ nhận `Sky.exe`; không có profile
  theo game.
- Cài đặt yêu cầu Python + `setup.bat`; người chơi phổ thông cần **.exe**.
- Chưa có LICENSE, chưa có kiểm tra cập nhật, chưa có khay hệ thống.

---

## 2. Mục tiêu v3

1. **An toàn trước hết**: mọi tính năng mới đi qua cùng một engine, cùng guard
   focus và cùng đường Stop; không giảm chất lượng đã đạt ở v2.
2. **Một kiến trúc**: một `MainWindow`, một `PlaybackController`, một parser
   sheet, state machine tường minh.
3. **Tiện lợi**: tìm bài trong 2 giây, thêm bài bằng kéo‑thả, nghe/xem trước
   không cần vào game, điều khiển đầy đủ từ hotkey/khay/mini.
4. **Cài một lần, chạy ngay**: bộ cài .exe, không cần Python.

---

## 3. Lộ trình theo giai đoạn

Mỗi giai đoạn kết thúc bằng: full test suite xanh, dataset audit đạt, cập nhật
README/UI_DESIGN nếu hành vi thay đổi.

### Giai đoạn 0 — Bảo toàn công việc (ngay, ~0.5 ngày)

- [ ] Commit toàn bộ v2 lên một nhánh `v2-stabilization` (có review diff), rồi
      merge vào `main`.
- [ ] Bổ sung `.gitignore`: `.test-tmp/`, `sky_macro_player.egg-info/` (đã có
      pattern), `build/artifact-smoke`, `build/release-smoke`.
- [ ] Gắn tag `v2.0.0` để có mốc rollback.
- [ ] Chọn và thêm `LICENSE` (người dùng quyết định loại giấy phép).

**Nghiệm thu**: `git status` sạch trừ file runtime; CI remote chạy xanh trên
4 phiên bản Python.

### Giai đoạn 1 — Hợp nhất kiến trúc (~4–6 ngày)

Không viết lại một lần. Di chuyển từng phần sau khi đã có test khóa hành vi.

Cấu trúc đích:

```text
macro_player/
  app.py                 # entry point (thay gui_qt.py, giữ shim tương thích)
  paths.py               # một nguồn cho user data / bundled sheets / logs
  domain.py              # Settings, SongSheet, NoteEvent, PlaybackState
  sheets/
    parser.py            # parser DUY NHẤT: txt UTF-16/8, json, list-key
    audit.py             # tương thích theo layout, fingerprint cache
    library.py           # quét thư mục, metadata, tìm kiếm bỏ dấu
  playback/
    engine.py            # macro_core.MacroPlayer, nhận SongSheet
    controller.py        # một PlaybackController + state machine + session id
    clock.py             # snapshot elapsed/duration cho UI
  services/
    hotkeys.py           # GlobalHotkeyService + lifecycle starting/active/failed
    focus.py             # window_focus + profile mục tiêu
    persistence.py       # repositories hiện tại
  ui/
    main_window.py
    mini_overlay.py
    tray.py
    pages/ library.py queue.py shortcuts.py settings.py
    widgets/ note_runway.py key_grid.py dock.py
    theme.py             # Tokens + QSS
legacy/gui.py            # chuyển Tkinter vào đây, không đóng gói
```

Việc cụ thể:

1. `paths.py`: luôn lưu dữ liệu người dùng ở `%LOCALAPPDATA%\SkyMacroPlayer`
   (cho phép override bằng biến môi trường cho dev/test); migration từ thư mục
   source chỉ copy, không ghi đè, có backup.
2. Engine nhận `SongSheet`; xóa `_validated_notes` trùng lặp, mapping kiểm tra
   tại một chỗ (`audit.py`).
3. Gộp hai Worker/Controller thành một; state machine với các trạng thái
   `idle, loading, countdown, playing, paused, focus_paused, stopping,
   completed, error, closing` và bảng chuyển trạng thái có test.
4. Viết lại `MainWindow` thành một lớp lắp ghép các page/widget (composition),
   mọi chuỗi tiếng Việt đặt tại nơi tạo widget; xóa `sky_ui_polish`.
5. Xóa `sky_ui_*.py` khi test UI đã chuyển sang `ui/`; giữ `gui_qt.py` là shim
   gọi `macro_player.app:main` trong một phiên bản.
6. Thêm `ruff` (lint + format) và `mypy --strict` cho `macro_player/` vào CI.

**Nghiệm thu**: không còn kế thừa MainWindow nhiều tầng; một lớp controller;
grep không còn `sky_ui_`; 85 test cũ (đã chuyển đường dẫn) + test state
machine đều đạt; start/stop/close smoke test đạt.

### Giai đoạn 2 — Tính năng tiện lợi cốt lõi (~5–7 ngày)

Sắp theo giá trị cho người dùng / chi phí.

| # | Tính năng | Mô tả | Tiêu chí nghiệm thu |
| --- | --- | --- | --- |
| F1 | **Tìm kiếm bỏ dấu + mờ** | Chuẩn hóa NFD bỏ dấu, `đ→d`; khớp từng từ, xếp hạng theo đầu từ; tìm cả tên file | `bang khuang`, `bkhuang`, `BÂNG` đều ra *Bâng khuâng*; gõ phím không làm phát nhạc |
| F2 | **Phát tất cả / Trộn / Lặp** | Khôi phục tính năng bản cũ: phát tất cả, trộn (không lặp lại bài cho đến khi hết vòng), lặp 1 bài / lặp hàng chờ | Stop luôn dừng cả chuỗi; trộn có seed để test; không tự phát lại sau Stop |
| F3 | **Tốc độ phát 0.5×–1.5×** | Hệ số tốc độ áp vào đồng hồ engine và runway; có thể đổi khi đang tạm dừng | Drift < 20 ms/phút trong test clock giả; runway/thời gian khớp engine |
| F4 | **Bắt đầu từ vị trí / lặp đoạn A–B** | Click runway để chọn điểm bắt đầu (khi chưa phát hoặc đang tạm dừng); A–B để luyện đoạn | Nhả hết phím ở ranh giới; luôn có countdown trước khi phát lại |
| F5 | **Thêm sheet trong app** | Kéo‑thả file/thư mục vào cửa sổ hoặc nút *Nhập sheet*; xem trước kết quả kiểm tra (hợp lệ / không hỗ trợ / lỗi dòng nào); xử lý trùng tên (đổi tên, ghi đè có xác nhận, bỏ qua) | Không chỉnh file gốc; file lỗi không khóa thư viện; có hoàn tác |
| F6 | **Theo dõi thư mục** | `QFileSystemWatcher` làm mới thư viện khi file thêm/sửa/xóa; invalidate audit theo fingerprint | Sửa sheet bên ngoài → thư viện cập nhật trong < 2 s, không phát nhầm bài |
| F7 | **Thông tin bài** | Thời lượng, số nốt, mật độ nốt/giây (gợi ý độ khó), layout tương thích, ngày thêm | Hiển thị trong danh sách + panel chi tiết; tính trong worker, không chặn UI |
| F8 | **Sắp xếp & lọc** | Theo tên, thời lượng, mới thêm, nghe nhiều, gần đây; lọc *Yêu thích*, *Phát được*, *Không hỗ trợ* | Giữ lựa chọn khi đổi bộ lọc; empty state thật thay vì tooltip |
| F9 | **Lịch sử & đếm lượt** | *Gần đây* (20 bài), số lần phát; lưu ở user data | Chỉ ghi khi bài thực sự bắt đầu phát; dữ liệu hỏng không chặn khởi động |
| F10 | **Playlist đặt tên** | Lưu hàng chờ thành playlist; mở lại chỉ khôi phục danh sách, **không tự phát** | Bài bị xóa khỏi đĩa được đánh dấu thiếu, không bị thay bằng bài khác |

### Giai đoạn 3 — Tính năng nâng cao (~5–8 ngày)

| # | Tính năng | Mô tả | Ghi chú an toàn |
| --- | --- | --- | --- |
| F11 | **Chế độ xem trước (Dry‑run)** | Phát vào bàn phím ảo 15 phím (lưới 3×5 như trong Sky) **không gửi phím ra hệ thống**; có thể kèm âm thanh tổng hợp đơn giản (QtMultimedia/sine) | Engine dùng `controller` giả; nút chuyển chế độ rõ ràng, mặc định tắt âm |
| F12 | **Lưới phím trực quan khi phát thật** | Widget `key_grid` sáng phím đang nhấn, giúp người dùng biết app đang làm gì | Tôn trọng reduced motion |
| F13 | **Chính sách 2Key/3Key** | Với 6 bài bị chặn: cho người dùng chọn *gộp lớp về 15 phím*, *chỉ phát lớp 1*, hoặc giữ chặn; xem trước số nốt bị ảnh hưởng; lưu lựa chọn theo từng bài | Không âm thầm bỏ tiền tố — đúng nguyên tắc ở `IMPROVEMENT_PLAN.md` P1‑01 |
| F14 | **Profile game** | Sky (PC/Steam), Heartopia: tên tiến trình, tiêu đề cửa sổ, layout, timing hold riêng; chọn cửa sổ mục tiêu thủ công khi có nhiều ứng viên | Mỗi profile phải được xác minh bằng phiên game thật trước khi bật mặc định |
| F15 | **Trình chỉnh mapping phím** | Tạo layout tùy chỉnh (15 ô), import/export; phát hiện trùng phím với hotkey | Layout lỗi không được lưu |
| F16 | **Ghi phím tắt bằng cách nhấn** | Ô "Nhấn tổ hợp phím…" thay cho gõ chuỗi; báo xung đột trước khi lưu | Phím nhạc của layout hiện tại bị cấm làm hotkey |
| F17 | **Khay hệ thống & thông báo** | Icon khay với Phát/Tạm dừng/Tiếp/Dừng/Mini/Thoát; toast khi hết hàng chờ hoặc mất focus Sky; tùy chọn thu xuống khay khi đóng | Đóng hẳn vẫn qua shutdown an toàn |
| F18 | **Thiết lập lần đầu** | Wizard 3 bước: chọn layout trong game → kiểm tra cửa sổ Sky → thử hotkey Dừng | Có thể bỏ qua; chạy lại được từ Cài đặt |
| F19 | **Cài đặt theo bài** | Nhớ tốc độ, layout, policy 2Key cho từng bài | Ghi đè được trong phiên |
| F20 | **Xuất báo cáo chẩn đoán** | Zip version, cấu hình (đã redacted hotkey), log gần đây, audit thư viện | Không chứa nội dung phím người dùng gõ |

### Giai đoạn 4 — Chau chuốt UI/UX (~3–4 ngày, song song một phần với GĐ 2–3)

Theo `UI_DESIGN.md`, làm sau khi giai đoạn 1 xong để không sửa hai lần.

- Đủ các trạng thái bắt buộc: empty library, no results, loading, validating,
  countdown, playing, paused, focus‑paused, stopping, completed, queue
  complete, hotkey conflict, missing file, unsupported sheet.
- Mini overlay hai hàng, nút chính ≥ 44 px, nhớ vị trí và kéo về màn hình còn
  tồn tại khi tháo màn hình phụ.
- Bảng lệnh nhanh `Ctrl+K` (tìm bài + lệnh), phím tắt nội bộ hiển thị trong
  tooltip; `Enter` phát, `Ctrl+Enter` thêm vào hàng chờ, `F` yêu thích.
- Hàng chờ: xóa có hoàn tác, xóa tất cả, kéo bài từ thư viện vào hàng chờ.
- Song ngữ VI/EN qua `QTranslator` (chuẩn bị chuỗi từ giai đoạn 1).
- Kiểm tra: tab order, focus nhìn thấy, tương phản 4.5:1, reduced motion,
  DPI 100/125/150/200% trên Windows thật, ảnh chụp kiểm chứng.

### Giai đoạn 5 — Đóng gói & phát hành (~3–4 ngày)

- **PyInstaller one‑folder** (đã có `build/` thử nghiệm) + **Inno Setup**
  tạo `SkyMacroPlayer-Setup-3.x.exe`: cài theo user, không cần quyền Admin,
  shortcut Start Menu/Desktop, gỡ cài đặt giữ dữ liệu người dùng.
- Bản portable `.zip` cho người không muốn cài.
- Phiên bản lấy từ một nguồn (`pyproject.toml` → `importlib.metadata`).
- Kiểm tra cập nhật **tùy chọn** qua GitHub Releases (chỉ thông báo, không tự
  tải/cài).
- CI: build exe trên `windows-latest`, smoke test khởi động/thoát offscreen,
  đính kèm artifact vào release khi push tag.
- Giữ `setup.bat`/`start.vbs` cho người chạy từ source.

**Nghiệm thu**: cài trên máy Windows sạch (không Python) → tìm bài, phát,
dừng bằng hotkey, thoát; dữ liệu v2 được migrate; gỡ cài đặt sạch.

---

## 4. Chất lượng xuyên suốt

- Test mới cho mỗi tính năng: parser (kể cả property‑based với `hypothesis`
  cho dữ liệu sheet ngẫu nhiên), state machine, tốc độ/lặp đoạn bằng clock giả,
  tìm kiếm bỏ dấu, import/trùng tên trong thư mục tạm.
- Không dùng bàn phím thật trong test tự động; engine luôn nhận controller giả.
- Không bao giờ ghi `hotkeys.json`/`favorites.json` thật trong test.
- Mục tiêu coverage `macro_player/` ≥ 85 % (đo, không ép bằng test rỗng).
- CI thêm: ruff, mypy, dataset audit toàn bộ `sheets/`, build exe.

---

## 5. Thứ tự và phụ thuộc

| Giai đoạn | Phụ thuộc | Có thể song song |
| --- | --- | --- |
| 0 Bảo toàn | — | — |
| 1 Kiến trúc | 0 | Parser/paths tách được khỏi UI |
| 2 Tiện lợi cốt lõi | 1 (F1, F7, F8 chỉ cần `sheets/`) | F1/F5/F6/F7 độc lập nhau |
| 3 Nâng cao | 1, F3 cho F19 | F11/F12, F15/F16, F17, F20 độc lập |
| 4 UI/UX | 1 | Song song với 2–3 theo từng page |
| 5 Phát hành | 1; nên sau 2 | Pipeline CI có thể dựng sớm |

Đề xuất mốc phát hành:

- **v2.1** (sau GĐ 0 + F1, F2, F8 trên mã hiện tại nếu cần bản nhanh): tìm
  kiếm bỏ dấu, phát tất cả/trộn/lặp.
- **v3.0**: GĐ 1 + 2 + 4 + 5.
- **v3.1+**: GĐ 3.

---

## 6. Rủi ro và điều cần người dùng quyết định

1. **Điều khoản game**: tự động hóa phím có thể vi phạm điều khoản của Sky /
   Heartopia. README nên có cảnh báo; app không vượt qua chống gian lận,
   không gửi input vào cửa sổ nền.
2. **Giấy phép** cho mã nguồn và **quyền phân phối sheet** (nhiều bài là nhạc
   có bản quyền do cộng đồng chép) — cân nhắc tách sheet khỏi bộ cài hoặc ghi
   nguồn.
3. **Chính sách 2Key/3Key**: cần nghe thử trong game để chọn mặc định.
4. **Heartopia**: cần tên tiến trình/tiêu đề cửa sổ thật trước khi hỗ trợ khóa
   focus.
5. Giới hạn của Windows: kiểm tra foreground rồi gửi phím không nguyên tử; không
   cam kết tuyệt đối "không lọt phím" khi Alt+Tab.
6. Ước lượng thời gian trên là cho một người làm toàn thời gian; chưa tính thời
   gian kiểm thử trong game thật.
