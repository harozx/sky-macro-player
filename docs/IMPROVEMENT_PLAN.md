# Kế hoạch hoàn thiện Sky Instrument Console

> Cập nhật sau rà soát lần 2: xem [REVIEW_PLAN_V2.md](REVIEW_PLAN_V2.md).
> Các mục dưới đây là lịch sử của đợt triển khai trước. Nhận định “ổn định lõi
> đã hoàn tất” không còn là kết luận nghiệm thu hiện hành: review lần 2 phát hiện
> thêm lỗi chuyển trạng thái, bảo vệ mục tiêu và bảo toàn dữ liệu chưa được test.

Ngày đánh giá: 17/09/2026. Trạng thái: đợt ổn định lõi đã hoàn tất; các mục còn lại
được phân loại rõ là xác minh thực địa hoặc roadmap sau phát hành.

## Tiến độ triển khai ngày 17/09/2026

Đã hoàn thành và có regression test: P0-01 đến P0-04; P1-01 đến
P1-05; đồng hồ Note Runway trong P1-07; một controller và dependency injection
service trong P1-06; khóa một instance; shortcut không chiếm phím khi đang nhập;
trang Cài đặt/Phím tắt có cuộn; hàng chờ mở lại được ở cửa sổ hẹp. Audit hiện
cho kết quả 118 sheet hợp lệ cấu trúc, 112 phát được và 6 bị chặn trước countdown.

Nghiệm thu độc lập bằng Gemini 3.8 High đã được Codex lead đối chiếu lại với mã
và test. Các cảnh báo về countdown/runway, ghi file, truyền `input_guard`, dừng khi
đóng và sàng lọc sheet là false positive hoặc đã được xử lý. Hai khoản P2 còn hợp
lệ là kích hoạt lại cửa sổ của instance đang chạy và giảm dần các tầng kế thừa UI.

Còn cần xác minh ngoài môi trường test: DPI 100–200% trên màn hình Windows thật,
Alt+Tab trong phiên Sky thực, artifact đóng gói trên máy sạch và hành vi nhiều
màn hình. Các nâng cấp ở mục 7 là roadmap sau bản ổn định, không phải tính năng
đã bàn giao.

## 1. Mục tiêu và mốc hiện tại

Ứng dụng phải chọn đúng game, phát đúng sheet, dừng đáng tin cậy, lưu cấu hình không mất dữ liệu và dùng thuận tiện ở cả cửa sổ đầy đủ lẫn mini.

Kết quả kiểm tra tại workspace:

- Bộ kiểm thử hiện tại: **70 passed**, chạy Qt offscreen trên Windows.
- **118/118 sheet đọc và kiểm tra cấu trúc thành công**.
- Với cả hai layout `old` và `new`: **112 sheet có phím được hỗ trợ, 6 sheet có phím chưa hỗ trợ**. Đây là kiểm tra mapping, chưa phải nghe thử chất lượng 112 bài trong game.
- Nhận diện Sky hiện yêu cầu đúng title và xác minh HWND/PID/process path; cửa sổ trình duyệt có chữ Sky bị loại.
- Chuẩn hóa phím tắt đã sắp modifier theo thứ tự cố định; `Ctrl+Shift+A` và `Shift+Ctrl+A` được coi là cùng tổ hợp.
- Nhiều tệp đang có thay đổi chưa commit. Phải giữ nguyên thay đổi của người dùng và cấu hình runtime.
- Đã có close smoke test xác nhận worker dừng và không còn busy. Vẫn chưa kiểm thử trực tiếp phiên Sky, DPI trên màn hình thật hoặc bản cài trên máy sạch; không dùng kết quả offscreen để khẳng định các phần này đã đạt.

## 2. Danh sách vấn đề có căn cứ

P0: chặn bản phát hành do có thể gửi phím sai hoặc dừng không đúng. P1: cần hoàn tất để dùng ổn định. P2: hoàn thiện và phát triển sau nền tảng.

### P0-01 — Nhận diện nhầm cửa sổ Sky

- Bằng chứng: `macro_player/window_focus.py:19`, chọn theo tiêu đề chứa `sky`; đã tái hiện với trình duyệt.
- Xử lý: xác định executable/PID và cửa sổ thuộc tiến trình game; cho người dùng chọn mục tiêu khi có nhiều ứng viên; xác minh lại PID khi tái sử dụng handle.
- Không tự coi cửa sổ có chữ Sky là game. Tên executable phải lấy từ phiên game thực tế, không đoán.
- Nghiệm thu: trình duyệt/tài liệu không được tự chọn; game đóng/mở lại hoặc handle được tái sử dụng không dẫn đến phát sai mục tiêu.

### P0-02 — Khóa focus chỉ kiểm tra ở giao diện

- Bằng chứng: `sky_ui_final.py:161` dùng timer 250 ms; `macro_core.py` không kiểm tra cửa sổ trước khi gửi phím.
- Hệ quả: có khoảng trễ phát hiện khi Alt+Tab; nếu luồng UI bận, khoảng trễ có thể dài hơn. Không thể cam kết tuyệt đối rằng không có phím lọt.
- Xử lý: thêm điều kiện kiểm tra mục tiêu ngay ở đường gửi phím và giữa các phím của hợp âm; khi mất focus, ngừng nốt mới, nhả phím đang giữ và giữ thời gian bài ở trạng thái chờ.
- Nghiệm thu: mô phỏng mất focus trước nốt, giữa hợp âm, lúc đếm ngược và khi UI bị chậm; không phát nốt mới sau khi phát hiện mất focus. Đo hành vi Alt+Tab thực tế và ghi rõ giới hạn của input Windows.

### P0-03 — Đóng ứng dụng có thể xung đột với chuyển bài

- Bằng chứng mã: `sky_ui_final.py:301` gọi xử lý finished của lớp cha trước khi xử lý `close_pending`; `sky_ui_window.py:182` có thể lên lịch phát `pending_song` hoặc bài kế tiếp.
- Đây là nguy cơ thứ tự callback, cần kiểm thử tái hiện trước khi kết luận mức ảnh hưởng thực tế.
- Xử lý: một trạng thái shutdown có ưu tiên cao nhất; hủy pending/autoplay, chặn lệnh mới và hotkey, yêu cầu dừng, đợi nhả phím và worker kết thúc rồi đóng.
- Nghiệm thu: đóng lúc idle/countdown/playing/paused/focus-paused/stopping và lúc đã yêu cầu Next; không bắt đầu bài mới, không còn worker/listener/tiến trình sau khi thoát bình thường. Đo thời gian thoát, không dùng cưỡng bức kill làm hành vi mặc định.

### P0-04 — Phím Esc có thể nối vào controller cũ

- Bằng chứng mã: `sky_ui_window.py:107` tạo QAction với `self.controller.stop`; sau đó `sky_ui_integrated.py` thay controller và chỉ nối lại một số nút.
- Xử lý: tạo controller đúng ngay từ đầu; tất cả lệnh Stop đi qua cùng một phương thức điều phối, gồm nút chính, mini, Esc và global hotkey.
- Nghiệm thu: từng đường Stop đều dừng đúng phiên đang chạy, kể cả khi pause hoặc countdown; kiểm thử trên MainWindow thật với đầu ra bàn phím giả.

## 3. P1 — Độ ổn định, dữ liệu và kiến trúc

### P1-01 — Sheet đọc được nhưng không phát được

- `SheetRepository` kiểm tra cấu trúc nhưng mapping chỉ được kiểm tra khi phát; hiện có 6 sheet chứa `2Key/3Key`.
- Thêm kết quả kiểm tra tương thích theo layout: hợp lệ, không hỗ trợ, lỗi dữ liệu; hiển thị lý do trước khi countdown.
- Bài nhiều phần phải có quy tắc chọn phần/track rõ ràng. Không bỏ tiền tố 2/3 hay âm thầm bỏ nốt để ép phát.
- Nghiệm thu: cả 118 sheet có kết quả xác định; 6 bài không tương thích được đánh dấu và chặn phát cho đến khi có mapping/track hợp lệ. CI kiểm tra toàn bộ dataset và phát hiện thay đổi mới.

### P1-02 — Phím tắt áp dụng lỗi làm mất cấu hình hoạt động

- Bằng chứng: `_save_hotkeys` lưu trước khi bật listener; `GlobalHotkeyService.start` dừng listener hiện có trước khi kiểm tra đầy đủ cấu hình mới.
- Chuẩn hóa thứ tự modifier và alias; kiểm tra bằng parser thực tế; phát hiện trùng với shortcut nội bộ và phím nhạc.
- Áp dụng có rollback: nếu không bật được listener mới, phục hồi listener/cấu hình cũ và báo đúng trạng thái. Tránh hai listener hoạt động đồng thời trong quá trình chuyển đổi.
- Nghiệm thu: cấu hình sai hoặc hook lỗi không làm mất phím Dừng đang hoạt động; hai tổ hợp khác thứ tự modifier được coi là trùng.

### P1-03 — Khôi phục cấu hình có thể phát sinh ghi ngoài ý muốn

- Bằng chứng: `_apply_settings` đặt giá trị widget sau khi signal lưu đã được nối; slider chỉ hỗ trợ 0–10 trong khi repository chấp nhận 0–30.
- `_save_settings` thay đổi bộ nhớ trước khi ghi thành công; `reduced_motion` chưa có trong Settings; `window_opacity` có trong dữ liệu nhưng chưa được áp dụng ở luồng restore đang đọc.
- Chặn signal khi restore, thống nhất miền giá trị, chỉ cập nhật trạng thái đã lưu sau thành công; phân biệt thay đổi chưa lưu và đã áp dụng.
- Cấu hình hỏng cần thông báo phục hồi rõ ràng và giữ bản gốc, không tự ghi đè bằng mặc định.
- Nghiệm thu: mở/đóng ứng dụng không làm thay đổi cấu hình; lỗi ghi không khiến UI báo đã lưu; tùy chọn được khôi phục đúng.

### P1-04 — Yêu thích lỗi có thể làm hỏng khởi động hoặc báo sai

- Bằng chứng: library đọc favorites đồng bộ khi khởi tạo; lỗi repository chưa được xử lý cục bộ. `toggle_favorite` bắt `OSError`, trong khi repository thường bọc thành `RepositoryError`.
- Xử lý: vẫn mở được thư viện khi favorites hỏng; báo lỗi có hành động khôi phục; rollback dấu yêu thích nếu lưu thất bại.
- Nghiệm thu: JSON hỏng, file chỉ đọc và thư mục không ghi được đều có phản hồi rõ; không mất sheet và không báo lưu thành công giả.

### P1-05 — Định danh bài theo tên file gây nhập nhằng

- Bằng chứng: `_play_slot` và danh sách gán hotkey dùng basename, trong khi repository tìm sheet đệ quy.
- Dùng ID/đường dẫn tương đối đầy đủ trong toàn bộ thư viện, hàng chờ, yêu thích và slot; migration cấu hình cũ chỉ tự chuyển khi tên là duy nhất.
- Nghiệm thu: `a/song.txt` và `b/song.txt` được gán/phát độc lập; tham chiếu thiếu có thông báo, không chọn bài khác.

### P1-06 — Quản lý trạng thái phân tán

- Hiện có MainWindow qua các lớp window → integrated → polish → final, controller nguyên mẫu và controller tích hợp, thay factory bằng biến module, nhiều lần thay widget/nối signal.
- Mục tiêu: một PlaybackController, một MainWindow, service được truyền trực tiếp; UI chỉ trình bày state và phát lệnh.
- Có session ID cho callback; trạng thái tách rõ loading, countdown, playing, manual-paused, focus-paused, stopping, completed, error, closing.
- Tách theo trách nhiệm: `playback/`, `services/`, `ui/pages/`, `ui/widgets/`, `repositories/`; di chuyển từng phần sau khi có test khóa hành vi, không rewrite cùng lúc.
- Nghiệm thu: không còn monkey-patch factory hoặc controller thay giữa constructor; callback phiên cũ không đổi state phiên mới; mọi widget chỉ cập nhật trên Qt main thread.

### P1-07 — Tiến độ hiển thị không dùng đồng hồ của bộ phát

- Bằng chứng: `NoteRunway._tick` cộng cố định interval, giảm chuyển động dừng timer.
- Lấy elapsed/duration từ một đồng hồ playback monotonic; animation chỉ nội suy hình ảnh. Giảm chuyển động vẫn cập nhật thời gian bằng chữ.
- Nghiệm thu: pause/resume nhiều lần, UI bị trễ và bật/tắt giảm chuyển động không làm tiến độ sai so với phiên phát; hoàn tất/reset chỉ xảy ra đúng lúc.

## 4. P1/P2 — Chau chuốt trải nghiệm

Nguồn thiết kế: `docs/UI_DESIGN.md`, đối chiếu skill frontend-design. Giữ bản sắc bàn điều khiển nhạc Sky với Note Runway; ưu tiên tính chính xác và khả năng đọc.

### UX-01 — Cửa sổ chính

- Giữ bảng màu Cloud Ink `#101722`, Deep Slate `#192536`, Lifted Slate `#24344A`, Moon Mist `#E7EFF7`, Sky Blue `#82CFFF`, Sunset Apricot `#FFB287`.
- Tiêu đề Bahnschrift có fallback hỗ trợ tiếng Việt; nội dung Segoe UI; thời gian/phím tắt Cascadia Mono có fallback.
- Thư viện là trọng tâm, thanh phát luôn thấy; hàng chờ có nút mở riêng khi cửa sổ hẹp, thay vì chỉ bị ẩn dưới 980 px.
- Trang cài đặt/phím tắt có cuộn khi thiếu chiều cao. Tên bài dài rút gọn có tooltip, không đẩy mất nút Stop.
- Bỏ nhãn `UI PREVIEW · 0.2` và lấy version từ một nguồn; thống nhất tiếng Việt tại nơi tạo widget, bỏ dịch vá sau render.
- Nghiệm thu: đầy đủ/narrow, tên dài, không sheet, không kết quả tìm kiếm, loading, lỗi; mọi điều khiển thiết yếu truy cập được bằng chuột và bàn phím.

### UX-02 — Mini player

- Hiện kích thước cố định 430×82; thiếu hiển thị trạng thái chi tiết, countdown/progress và nút mở rộng theo tài liệu thiết kế.
- Đề xuất hai hàng: tên bài + trạng thái Sky; thời gian + Phát/Tạm dừng + Tiếp + Dừng + Mở rộng. Pin rõ trạng thái, nhớ vị trí và giới hạn trong vùng màn hình còn tồn tại.
- Dùng cùng state/view-model với cửa sổ chính. Không để nhãn “Phát” khi thực tế đang dừng hoặc chờ Sky.
- Nghiệm thu: 100%, 125%, 150%, 200% DPI; nhiều màn hình và tháo màn hình phụ; tên tiếng Việt dài không che Stop.

### UX-03 — Hành vi điều khiển và lỗi

- Chặn hành động không phù hợp trong loading/stopping/closing; xử lý bấm Play/Next liên tục có quy tắc xác định.
- Kiểm tra Space/Esc trong ô nhập liệu, không để việc gõ tìm kiếm gây phát nhạc ngoài ý muốn.
- Lỗi phải phân biệt phát nhạc, lưu cấu hình, sheet hỏng, hotkey và không tìm thấy game; không dùng chung tiền tố “Không thể phát” cho mọi lỗi.
- Cửa sổ chính và mini dùng thông báo trạng thái nhất quán; có trạng thái “Chờ Sky”, “Đã dừng”, “Đã phát xong”, “Hết hàng chờ”.
- Nghiệm thu: tab order, focus nhìn thấy, độ tương phản, nhãn truy cập, reduced motion và chuỗi thao tác nhanh.

### UX-04 — Thư viện và hàng chờ

- Ưu tiên: làm mới thư viện, báo số bài tương thích/lỗi, tìm kiếm tên tiếng Việt, giữ lựa chọn khi đổi yêu thích; chi tiết bài gồm thời lượng, số nốt và layout.
- Tiếp theo: nhập sheet có xem trước kiểm tra, xử lý trùng tên, sắp xếp và xóa hàng chờ có hoàn tác; không xóa file gốc khi bỏ bài khỏi hàng chờ.
- Lưu playlist/hàng chờ là tùy chọn. Khi mở lại chỉ phục hồi danh sách, không tự phát.
- Nghiệm thu: lỗi một file không khóa cả thư viện, không phát nhầm bài sau khi refresh hoặc filter.

## 5. P1 — Đóng gói, vận hành và kiểm thử

- Tách dữ liệu đóng gói khỏi cấu hình người dùng; hiện đường dẫn phụ thuộc thư mục source. Migration dữ liệu có backup và không ghi đè config runtime trong development/test.
- Chọn phương thức phát hành Windows nhất quán; cấu hình build phải đưa đủ sheet/assets và kiểm thử trên môi trường sạch. Hiện pyproject khai báo module/package nhưng chưa có cấu hình bundle sheet hoặc entry point ứng dụng.
- Chống mở nhiều instance gây trùng hook/phím; instance thứ hai đưa cửa sổ hiện có lên trước.
- Thông báo lỗi khởi động và đường dẫn log; launcher hiện chạy bất đồng bộ nên không phản ánh đầy đủ crash sau khi Python đã được tạo.
- CI hiện có Windows Python 3.10–3.13 và pytest; thêm kiểm tra dataset, package artifact và khởi động/thoát artifact. Chỉ ghi hỗ trợ phiên bản khi job tương ứng thực sự đạt.
- Không thu thập nội dung người dùng gõ; log vòng đời phiên, lỗi và chẩn đoán cần thiết.

## 6. Trình tự thực hiện và tiêu chí qua từng đợt

| Đợt | Phạm vi | Phụ thuộc | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| 1 — Chặn lỗi nghiêm trọng | P0-01..04; regression bằng fake input; kiểm tra 6 sheet không hỗ trợ | Hiện trạng đã ghi nhận | Đúng mục tiêu, các đường Stop hoạt động, shutdown không phát bài mới, bài lỗi bị chặn sớm |
| 2 — Dữ liệu và điều khiển ổn định | P1-01..05, rollback hotkey/config/favorites | Đợt 1 | Lỗi ghi/đọc có phục hồi; cấu hình không bị thay khi chỉ khởi động; ID bài không nhập nhằng |
| 3 — Thu gọn kiến trúc | P1-06..07, gom command/state/session và đồng hồ playback | Test bảo vệ đợt 1–2 | Một controller; không callback cũ; không thay factory toàn cục; full regression đạt |
| 4 — Hoàn thiện UI | UX-01..03; phần cơ bản UX-04 | Đợt 3; duy trì UI_DESIGN.md | Chính/mini đủ trạng thái, bàn phím và DPI đạt; ảnh kiểm chứng trên Windows thật |
| 5 — Phát hành ổn định | Package, startup/shutdown, một instance, CI artifact | Đợt 1–4 | Cài trên môi trường sạch, phát/dừng/thoát trong Sky thực tế, dữ liệu cũ được giữ |
| 6 — Nâng cấp | Playlist, import có preview, tốc độ/lặp đoạn, profile game | Bản ổn định đợt 5 | Mỗi tính năng có tiêu chí riêng, không làm giảm độ an toàn đã đạt |

Ưu tiên tiến hành tuần tự các đợt có phụ thuộc. Có thể giao độc lập việc kiểm tra dataset, UI component và test fixture khi ranh giới file rõ ràng. Không ấn định ngày phát hành trước khi biết kết quả kiểm thử Sky thực tế và đóng gói.

## 7. Nâng cấp sau bản ổn định

1. Playlist và lịch sử gần đây: lưu tên/danh sách; phục hồi không tự phát.
2. Điều chỉnh tốc độ: thay đổi cùng đồng hồ phát và hiển thị, kiểm tra drift và pause/resume.
3. Lặp bài/lặp đoạn: nhả hết phím ở ranh giới, đếm vòng và luôn có Stop.
4. Profile theo game/nhạc cụ: target, mapping, timing và hotkey tách riêng; xác minh từng profile bằng dữ liệu thật.
5. Nhập và kiểm tra sheet: xem lỗi theo dòng/nốt, chọn track khi định dạng thực sự hỗ trợ, không chỉnh file gốc ngầm.
6. Báo cáo chẩn đoán người dùng chủ động xuất: version, lỗi gần đây và trạng thái dịch vụ, tránh nội dung phím gõ.

## 8. Checklist nghiệm thu bản hoàn thiện

- [ ] Không còn P0 mở; mỗi lỗi có test tái hiện hoặc kịch bản thực tế và bằng chứng đã sửa.
- [ ] Tất cả sheet được kiểm tra cấu trúc lẫn mapping; không quảng cáo 118 bài đều phát được khi còn bài chưa hỗ trợ.
- [ ] Stop từ mọi nơi và đóng trong mọi trạng thái hoạt động đúng; không tự phát tiếp khi closing.
- [ ] Kiểm tra Alt+Tab, game đóng/mở lại, minimize, nhiều cửa sổ và UI bận.
- [ ] Không thay đổi config/favorites khi chỉ mở ứng dụng; test lỗi dữ liệu dùng thư mục tạm.
- [ ] Phím tắt lỗi không làm mất bộ phím đang hoạt động.
- [ ] Main/mini thống nhất trạng thái; đủ keyboard navigation, focus, reduced motion và DPI.
- [ ] Test suite, dataset audit và artifact smoke test đạt; không coi số lượng test là thay thế cho độ bao phủ hành vi.
- [ ] Bản Windows sạch khởi động, phát, dừng và thoát được; ghi nhận cả giới hạn còn tồn tại.
- [ ] README, UI_DESIGN và hướng dẫn sử dụng phản ánh đúng tính năng đã triển khai.

## 9. Phạm vi bàn giao lần đánh giá này

Đã đọc các luồng chính, chạy suite, kiểm tra toàn bộ sheet và tái hiện hai vấn đề nhận diện/chuẩn hóa. Tài liệu này là backlog có thứ tự và tiêu chí nghiệm thu. Chưa sửa runtime hoặc triển khai các hạng mục nêu trên trong lần lập kế hoạch này.
