# Kế hoạch xử lý sau rà soát lần 2

Ngày: 17/09/2026. Phạm vi: review và triển khai các đợt A–D.
Tài liệu này thay thế kết luận ưu tiên/hoàn tất trong IMPROVEMENT_PLAN.md.

## 1. Mốc kiểm chứng

- Chạy lại toàn suite bằng `.venv`: **70 passed in 18.39s**.
- Ba probe không hook bàn phím, không ghi cấu hình thật đã tái hiện: chọn nhầm
  executable khi title đúng Sky; bật khóa giữa phiên không cài guard; slider 17
  giây nhưng nhãn 3 giây.
- Review thứ hai độc lập về dữ liệu/hotkey/artifact đã được lead đọc lại mã.
- Gemini `gemini-3.8-flash-high` phản biện các đoạn hành vi cung cấp trong prompt,
  không chạy test hoặc review toàn repository ở lượt này. Lead không chấp nhận
  suy luận “zombie playback” là lỗi đã chứng minh; stop event vẫn được kiểm tra.
- 70 test đạt không chứng minh các trường hợp chưa có test là đúng. Không có
  kết quả Sky thực, DPI thật hay cài artifact máy sạch mới trong lượt này.

## 2. Danh sách ưu tiên có căn cứ

P1: cần xử lý trước khi gọi bản này ổn định. P2: cần hoàn thiện trải nghiệm hoặc
chẩn đoán. “Tái hiện” là đã chạy probe/test; “mã” là nhánh lỗi thấy rõ trong mã;
“nguy cơ” cần thêm lịch callback có kiểm soát để kết luận hành vi thực tế.

### R01 — P1: bật khóa giữa phiên chưa bảo vệ worker (tái hiện)

- Bằng chứng: `sky_ui_final.py:208`, `sky_ui_integrated.py:220,238`.
  Worker chụp guard lúc tạo; bật khóa chỉ lưu setting. Probe: enabled=True,
  guard_calls=0, input_guard=None. Timer UI vẫn có thể pause nhưng không có
  kiểm tra trước từng phím trong phiên bắt đầu khi khóa tắt.
- Xử lý: trước mắt yêu cầu stop/drain trước khi đổi chế độ khóa trong phiên;
  sau đó thiết kế trạng thái guard thread-safe dùng chung, không đọc widget.
  Không hiển thị “đã bảo vệ” trước khi ràng buộc mục tiêu có hiệu lực.
- Nghiệm thu: bật/tắt/bật lúc countdown, playing, paused, focus-paused;
  không phát nốt mới trong lúc chưa xác minh mục tiêu, Stop luôn hoạt động.

### R02 — P1: chọn mục tiêu ban đầu vẫn dựa vào title (tái hiện)

- Bằng chứng: `macro_player/window_focus.py:43`. Probe WindowInfo có title Sky
  và path C:\Other\editor.exe vẫn được chọn. So PID/path sau lựa chọn chỉ bảo vệ
  tính liên tục của cửa sổ, chưa chứng minh đó là game ở lần chọn đầu tiên.
- Xử lý: xác minh executable từ cấu hình tin cậy hoặc lựa chọn game rõ ràng của
  người dùng; thiếu process path phải báo không xác minh được. Nhiều ứng viên
  cần chọn tường minh. Giữ kiểm tra HWND/PID/path trong phiên.
- Nghiệm thu: exact-title impostor, thiếu quyền đọc path, nhiều ứng viên, game
  restart, tái sử dụng HWND. Không tự chọn ứng dụng khác chỉ vì title giống.
- Giới hạn: kiểm tra foreground rồi gửi input Windows không nguyên tử;
  phải mô tả đúng giới hạn và thử Alt+Tab thật, không cam kết tuyệt đối zero leak.

### R03 — P1: dữ liệu đọc lỗi có thể bị ghi đè ở thao tác sau (mã)

- Bằng chứng: `sky_ui_integrated.py:63,455,530,572`: fallback mặc định/rỗng,
  nhưng đường save tiếp theo vẫn ghi đè file gốc.
- Xử lý: đánh dấu recovery-required; bảo toàn byte gốc, tạo backup có kiểm chứng
  trước phục hồi. Không âm thầm downgrade schema mới hơn.
- Nghiệm thu: JSON hỏng, sai kiểu và schema mới; khởi động rồi đổi cài đặt hoặc
  đánh dấu favorite vẫn giữ bản gốc cho tới khi chọn phục hồi. Dùng temp fixtures.

### R04 — P1: hook có thể chết sau khi báo áp dụng thành công (nguy cơ có căn cứ)

- Bằng chứng: `sky_ui_integrated.py:342`: chỉ kiểm tra candidate.start().
  `pynput/_util/win32.py:347` cài SystemHook trong thread; _mark_ready còn đứng
  trước bước cài hook. Test start() ném lỗi đồng bộ chưa phủ tình huống này.
- Xử lý: trạng thái starting/active/failed, xác minh kết quả hook và theo dõi
  thread chết; rollback có xác nhận listener cũ đã dừng. Không chỉ thêm wait()
  rồi mặc định hook thành công. Chặn xung đột global/local/phím nhạc.
- Nghiệm thu: start trả về rồi thread chết; lỗi rollback; đổi liên tục;
  global Stop hoặc fallback Stop hiển thị đúng khả năng hiện có.

### R05 — P1: callback tới muộn có thể ghi đè state/lệnh Stop (nguy cơ)

- Bằng chứng: `sky_ui_integrated.py:227` gán playing vô điều kiện;
  `sky_ui_window.py:223` singleShot giữ song trong closure sau khi xóa pending.
  Stop tới giữa việc lên lịch và thực thi không hủy closure đã tạo. Close có
  _closing guard nên không suy rộng thành lỗi shutdown đã tái hiện.
- Xử lý: transition table, session ID và generation cho lệnh đã lên lịch;
  Stop tăng generation và vô hiệu callback. Receiver Qt có slot/context rõ ràng.
- Nghiệm thu: điều khiển thứ tự started → stop → delivered-started; focus pause
  trước started; finished → schedule-next → stop → callback; không đổi stopping
  về playing, không tự bắt đầu bài sau Stop. Kiểm tra receiver chạy main thread.

### R06 — P1: phát lại phím đã gửi trong hợp âm khi quay lại focus (mã + test hiện có)

- Bằng chứng: `macro_core.py:74`; test_focus_loss_inside_chord... hiện mong đợi
  y ở thời điểm 0 rồi y lần nữa ở .05. Đây là lựa chọn hành vi có thể tạo nốt lặp,
  không nên loại khỏi review bằng nhãn false positive.
- Xử lý: chốt quy tắc mỗi key-down của một sự kiện tối đa một lần; hợp âm bị
  ngắt được nhả an toàn và đánh dấu bỏ dở, không replay toàn bộ tự động.
- Nghiệm thu: mất focus giữa key-down và trong hold, pause thủ công giữa hợp âm;
  không lặp key-down đã gửi, mọi key đã giữ được release kể cả backend ném lỗi.

### R07 — P1: tiến độ chưa lấy từ thời gian playback thực (mã)

- Bằng chứng: `sky_ui_core.py:269` có QElapsedTimer riêng; worker có thời gian
  pause của input_guard riêng. UI nhận focus-pause qua timer 250 ms nên có thể
  lệch tích lũy. `sky_ui_integrated.py:389` override paintEvent không gọi
  _sync_elapsed; reduced motion tắt timer nên runway thật không tiếp tục cập nhật.
- Xử lý: worker xuất snapshot elapsed/duration/session qua signal, UI nội suy;
  reduced motion vẫn cập nhật thời gian bằng chữ. Countdown đã tách khỏi playback,
  không khôi phục cảnh báo cũ “luôn chạy sớm 3 giây”.
- Nghiệm thu: nhiều lần mất focus ngắn hơn chu kỳ UI, UI bận, pause/resume,
  reduced motion từ đầu/giữa phiên; sai số mốc UI với engine <=100 ms sau đồng bộ.

### R08 — P2: thông tin và mini chưa khớp hành vi (mã + probe)

- Countdown: `_apply_settings` chặn signal slider nhưng không cập nhật nhãn;
  tái hiện value=17, label=3 giây. Cập nhật nhãn trong render settings.
- `sky_ui_window.py:247`: kiểm tra isVisible sau setWindowFlag có thể khiến mini
  đang mở bị ẩn; ghi nhận visibility trước đổi cờ và thử offscreen/Windows.
- `_show_error` dùng “Không thể phát” cho cả lỗi lưu/hotkey; phân loại thông báo.
- Mini theo UI_DESIGN còn cần thời gian, pin/mở rộng, vị trí theo màn hình;
  kiểm tra chiều cao Stop thực tế vì integration đặt lại minimumHeight=36.
- Nghiệm thu: settings restore/failure, state full/mini đồng nhất; DPI
  100/125/150/200%, tên dài, bàn phím, tháo màn hình phụ, reduced motion.

### R09 — P2: queue và kiểm tra sheet có thể dùng trạng thái cũ (mã)

- `sky_ui_window.py:175,223` lấy khỏi queue trước khi play được chấp nhận;
  không tìm thấy Sky có thể làm mất mục chưa phát khỏi queue.
- `sky_ui_integrated.py:96` dùng compatibility cache không kiểm tra file đổi;
  sửa sheet sau startup có thể khiến bài sửa đúng vẫn bị chặn hoặc báo lỗi muộn.
- Xử lý: peek/reserve rồi commit queue khi bắt đầu được; giữ mục lỗi kèm lý do;
  invalidate audit theo fingerprint và xác minh ngay trước countdown.
- Nghiệm thu: lỗi focus, file bị đổi/xóa, Next liên tục, mục trùng và double-click;
  không mất âm thầm, không phát hai lần ngoài chính sách queue đã công bố.

### R10 — P2: lỗi tạo thư mục không được bọc (mã)

- `macro_player/repositories.py:65`: mkdir nằm ngoài try, raw OSError vượt qua
  các nhánh UI chỉ bắt RepositoryError. Đưa tất cả filesystem save vào một
  ranh giới lỗi thống nhất và kiểm tra rollback.
- Nghiệm thu: parent không ghi được/parent là file; UI có thông báo, trạng thái
  không nhận là đã lưu. File đích cũ còn nguyên byte.

### R11 — P1 trước phát hành: artifact và dữ liệu người dùng

- `pyproject.toml:16`, `sky_ui_core.py:29`, `.github/workflows/ci.yml`:
  thiếu entrypoint/bundle sheets và CI chưa cài artifact. Cấu hình đang ở source.
- Chọn bản Windows one-folder làm artifact ứng viên; tách bundled resources
  khỏi user data, migration có backup/idempotence. Xác minh phương án build và
  license/dependency trước chọn công cụ; không cài thêm dependency ở lượt plan.
- Nghiệm thu: build/install nơi không có source; đủ 118 sheet với báo cáo từng
  layout (mốc trước:112 hỗ trợ,6 không); startup/shutdown và log lỗi đạt trên máy
  sạch. CI chạy artifact smoke. Không suy ra CI remote đạt từ test local.

## 3. Trình tự triển khai và cổng nghiệm thu

| Đợt | Việc chính | Kết quả phải bàn giao trước đợt sau |
| --- | --- | --- |
| A | R01,R02,R03,R10 | Test tái hiện trước sửa; guard đúng, file gốc được giữ, lỗi save được xử lý |
| B | R04,R05,R06 | Listener/state có lifecycle xác định; callback cũ vô hiệu; hợp âm không lặp |
| C | R07,R08,R09 | Snapshot playback dùng chung; UI/queue đúng trong chuỗi thao tác và lỗi |
| D | R11, IPC instance, thu gọn UI | Artifact độc lập, migration và smoke CI; test Windows/Sky thực có bằng chứng |

Không rewrite toàn giao diện cùng lúc với sửa playback. Dùng frontend-design
trước thay UI, giữ UI_DESIGN làm nguồn thiết kế. Gom các tầng kế thừa từng bước
sau khi test hành vi tương ứng đạt; chưa cần đưa tốc độ/lặp đoạn/import vào đợt A–C.

## 4. Phân công và quy tắc nghiệm thu

- Codex lead: state/guard contract, phạm vi file, phân loại phát hiện, review diff,
  kiểm thử hồi quy tổng và quyết định nghiệm thu. Không chấp nhận severity do
  model phụ gán nếu không có bằng chứng tương ứng.
- Gemini high: giao phiên nhỏ cho persistence (R03,R10), listener (R04), queue
  (R09), rồi artifact (R11); mỗi gói gồm file scope, test phải qua và giới hạn
  không chạm cấu hình runtime. Gói state/playback cần hợp đồng lead trước.
- Báo cáo mỗi gói: changed files, hành vi trước/sau, test, vấn đề chưa xử lý.
- Đợt A/B phải có fake input; test thực Sky chỉ làm khi đã sẵn sàng thao tác
  game có kiểm soát. Không dùng keyboard thật trong regression tự động.
- Mỗi đợt chạy full suite; kết quả được ghi theo phiên bản mã đang kiểm thử.

## 5. Kết quả triển khai và nghiệm thu

Plan này đã được triển khai trên các nhóm việc chính:

- Củng cố an toàn playback: chống phát lặp phím khi mất focus giữa một chord,
  quản lý session phát, loại bỏ callback trễ, và bảo đảm Stop vô hiệu hóa mọi
  lệnh phát đã lên lịch.
- Khóa vào Sky: chỉ nhận cửa sổ có tiêu đề Sky và tiến trình Sky.exe, chặn thay
  đổi khóa focus khi đang phát, đồng thời giữ trạng thái pause/resume đúng.
- Vòng đời ứng dụng: shutdown dừng worker/hotkey sạch, phát hiện listener hotkey
  chết, khóa một instance và chuyển focus sang cửa sổ đang chạy khi mở lần hai.
- Dữ liệu và cấu hình: ghi JSON nguyên tử, sao lưu file hỏng trước khi khôi phục,
  di chuyển dữ liệu người dùng cũ mà không ghi đè, và kiểm tra lại sheet mỗi lần phát.
- Giao diện: mini player có thời gian, ghim và mở rộng; queue chỉ lấy bài khi lệnh
  phát được chấp nhận; runway nhận tiến độ từ engine; các trạng thái chính được
  đồng bộ tốt hơn.
- Phát hành: khai báo entry point, đóng gói toàn bộ sheet vào wheel và bổ sung
  bước kiểm tra artifact trong CI.

Kết quả tự động cuối cùng:

- 85 bài kiểm thử đều đạt.
- Kiểm tra biên dịch Python và dependency đều đạt.
- Wheel sky_macro_player-2.0.0-py3-none-any.whl được dựng thành công, có entry
  point và đủ 118 sheet.
- Smoke test từ thư mục cài đặt cô lập xác nhận ứng dụng tìm đúng sheet đóng gói.

Các mục còn cần nghiệm thu vật lý trước một bản phát hành chính thức:

- Chạy thử Alt+Tab/focus-lock với bản Sky thực tế và đường dẫn Sky.exe trên máy
  người dùng.
- Kiểm tra DPI 100%, 125%, 150%, 200% và nhiều màn hình thật.
- Cài wheel trên một máy Windows sạch và chạy đủ hotkey/playback/shutdown.
- Xác nhận pipeline CI trên remote.

Kiến trúc kế thừa của các lớp cửa sổ vẫn có thể được hợp nhất trong một đợt
refactor riêng. Hiện tại các lỗi hành vi ưu tiên cao đã được xử lý và có test
hồi quy; không nên gộp refactor đó vào bản sửa ổn định này khi chưa có vòng
kiểm thử giao diện vật lý đầy đủ.
