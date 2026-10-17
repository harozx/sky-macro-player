"""English catalog: Vietnamese source string -> English.

Keep placeholders (``{name}``, ``{0}``) identical to the source string.
tests/test_i18n.py checks that every tr()/N_() string has an entry here.
"""

EN: dict[str, str] = {
    # --- app, paths, updates
    "Ứng dụng đang chạy nhưng Windows chưa thể đưa cửa sổ đó lên trước.":
        "The app is already running, but Windows could not bring its window to the front.",
    "Không thể mở kênh instance: {0}": "Could not open the instance channel: {0}",
    "Không thể chuyển dữ liệu người dùng: {exc}": "Could not move user data: {exc}",
    "Phản hồi từ GitHub không hợp lệ.": "GitHub returned an invalid response.",

    # --- engine
    "Bộ cũ (yuiophjkl;nm,./)": "Old layout (yuiophjkl;nm,./)",
    "Bộ mới (asdfghjqwertyui)": "New layout (asdfghjqwertyui)",
    "Bộ tùy chỉnh": "Custom layout",
    "Bộ phím tùy chỉnh cần đúng 15 phím, mỗi ô một ký tự.":
        "A custom layout needs exactly 15 keys, one character each.",
    "Bộ phím tùy chỉnh có phím bị trùng.": "The custom layout has duplicate keys.",
    "Sheet phải là object hoặc danh sách chứa object.":
        "A sheet must be an object or a list containing an object.",
    "Trường 'songNotes' phải là một danh sách.": "The 'songNotes' field must be a list.",
    "countdown_sec phải là một số không âm.": "countdown_sec must be a non-negative number.",
    "Sheet rỗng; không tìm thấy 'songNotes'.": "The sheet is empty; 'songNotes' was not found.",
    "Không tìm thấy bộ phím '{layout_name}'.": "Key layout '{layout_name}' was not found.",
    "Nốt #{index} phải là object.": "Note #{index} must be an object.",
    "Nốt #{index} có 'time' không hợp lệ.": "Note #{index} has an invalid 'time'.",
    "Nốt #{index} có 'time' âm hoặc không hữu hạn.":
        "Note #{index} has a negative or non-finite 'time'.",
    "Nốt #{index} có 'key' không hợp lệ.": "Note #{index} has an invalid 'key'.",
    "Nốt #{index} dùng key chưa hỗ trợ '{code}'. "
    "Sheet 2Key/3Key cần mapping rõ ràng trước khi phát.":
        "Note #{index} uses unsupported key '{code}'. "
        "2Key/3Key sheets need an explicit mapping before playing.",

    # --- hotkeys
    "Global hotkeys bị trùng; cấu hình đang dùng được giữ nguyên.":
        "Global hotkeys conflict; the current configuration was kept.",
    "Một global hotkey được Windows giữ riêng; cấu hình đang dùng được giữ nguyên.":
        "A global hotkey is reserved by Windows; the current configuration was kept.",
    "Global hotkeys đã dừng ngoài dự kiến. Dùng nút Dừng trong ứng dụng "
    "và mở lại ứng dụng để khôi phục hook.":
        "Global hotkeys stopped unexpectedly. Use the Stop button in the app "
        "and restart the app to restore the hook.",
    "listener đã dừng trong lúc khởi tạo hook": "the listener stopped while installing the hook",
    "Cấu hình cũ đã được khôi phục.": "The previous configuration was restored.",
    "Chưa có listener nào được bật.": "No listener was running.",
    "Không thể áp dụng global hotkeys: {exc}": "Could not apply global hotkeys: {exc}",
    "Không thể bật global hotkeys mới: {exc}. {suffix}":
        "Could not enable the new global hotkeys: {exc}. {suffix}",
    "Không thể bật global hotkeys mới ({exc}); "
    "khôi phục cấu hình cũ cũng thất bại ({rollback_exc}).":
        "Could not enable the new global hotkeys ({exc}); "
        "restoring the previous configuration also failed ({rollback_exc}).",

    # --- library
    "Chặn (mặc định)": "Block (default)",
    "Gộp mọi lớp về 15 phím": "Merge all layers into 15 keys",
    "Chỉ phát lớp 1": "Play layer 1 only",
    "Dễ": "Easy",
    "Vừa": "Medium",
    "Khó": "Hard",
    " Chọn cách xử lý lớp 2Key/3Key trong chi tiết bài.":
        " Choose how to handle 2Key/3Key layers in the song details.",
    "Sheet không có nốt nào để phát.": "The sheet has no notes to play.",
    "Chỉ nhận file .txt hoặc .json.": "Only .txt or .json files are accepted.",
    "Sheet không có nốt nào.": "The sheet has no notes.",
    "Sheet không hợp lệ.": "The sheet is invalid.",
    "Sheet dùng phím chưa hỗ trợ: {0}.{hint}": "The sheet uses unsupported keys: {0}.{hint}",
    "File lớn hơn 5 MB.": "The file is larger than 5 MB.",
    "Không tìm thấy sheet '{relative}'.": "Sheet '{relative}' was not found.",
    "Không thể chép '{name}': {exc}": "Could not copy '{name}': {exc}",

    # --- dialogs
    "Đổi tên bài mới": "Rename the new song",
    "Ghi đè bài cũ": "Overwrite the existing song",
    "Bỏ qua bài trùng": "Skip duplicates",
    "Nhập sheet": "Import sheets",
    "Cách xử lý file trùng tên": "How to handle files with the same name",
    "Hủy": "Cancel",
    "Thiết lập Sky Macro Player": "Set up Sky Macro Player",
    "Bộ phím trong game": "In-game key layout",
    "Trong Sky, mở Cài đặt → Điều khiển để xem đàn đang dùng bộ phím nào. "
    "Chọn đúng bộ phím để các nốt rơi vào đúng phím đàn.":
        "In Sky, open Settings → Controls to see which key layout the instrument uses. "
        "Pick the matching layout so notes land on the right keys.",
    "Giữ phím trong game": "Keep keys in the game",
    "Nên bật: nếu bạn chuyển sang cửa sổ khác, bản nhạc tự tạm dừng và không gõ nhầm "
    "phím vào ứng dụng đó. Mở Sky rồi nhấn kiểm tra.":
        "Recommended: if you switch to another window, the song pauses by itself and never "
        "types keys into that app. Open Sky, then press Check.",
    "Bật chế độ khóa vào cửa sổ game": "Lock playback to the game window",
    "Kiểm tra cửa sổ Sky": "Check the Sky window",
    "Những phím cần nhớ": "Keys to remember",
    "Bỏ qua": "Skip",
    "Quay lại": "Back",
    "Tiếp": "Next",
    "Bảng lệnh": "Command palette",
    "Gõ tên bài hoặc lệnh… (Enter để chạy, Esc để đóng)":
        "Type a song or command… (Enter to run, Esc to close)",
    "Tìm bài hoặc lệnh": "Search songs or commands",
    "Kết quả": "Results",
    "Chọn cửa sổ game": "Choose the game window",
    "Mở game trước, rồi chọn cửa sổ của nó. Ứng dụng sẽ nhận diện game theo tên file "
    "chạy (.exe) mỗi lần phát.":
        "Open the game first, then choose its window. The app recognizes the game by its "
        "executable name (.exe) every time it plays.",
    "Các cửa sổ đang mở": "Open windows",
    "Chọn": "Choose",
    "Kết quả kiểm tra": "Check result",
    "Nốt": "Notes",
    "Thời lượng": "Duration",
    "Nếu trùng tên:": "If the name exists:",
    "Hoàn tất": "Finish",
    "Không tìm thấy cửa sổ nào có thể chọn.": "No selectable windows were found.",
    "{0}/{1} file hợp lệ sẽ được chép vào thư viện. File gốc không bị thay đổi.":
        "{0}/{1} valid files will be copied into the library. The originals are not changed.",
    "Hợp lệ · trùng tên với bài đã có": "Valid · same name as an existing song",
    "Nhập {0} bài": "Import {0} songs",
    "• Dừng khẩn cấp: {0}\n• Tạm dừng / tiếp tục: {1}\n• Bài tiếp theo: {2}\n\n"
    "Sau khi nhấn Phát, bạn có vài giây đếm ngược để click vào game. Muốn nghe thử trước? "
    "Bật “Xem trước” ở thanh phát: ứng dụng chỉ chơi trên bàn phím ảo, không gửi phím ra "
    "ngoài. Có thể đổi phím tắt ở trang Phím tắt.":
        "• Emergency stop: {0}\n• Pause / resume: {1}\n• Next song: {2}\n\n"
        "After you press Play, a short countdown gives you time to click into the game. "
        "Want to listen first? Turn on “Preview” in the playback bar: the app plays only on "
        "the on-screen keyboard and sends no keys. You can change hotkeys on the Hotkeys page.",
    "BƯỚC {0}/{1}": "STEP {0}/{1}",
    "  ·  Không hỗ trợ": "  ·  Unsupported",
    "Lỗi: {error}": "Error: {error}",
    "Hợp lệ · có lớp 2Key/3Key (chọn cách xử lý sau khi nhập)":
        "Valid · has 2Key/3Key layers (choose how to handle them after importing)",
    "Hợp lệ": "Valid",
    "Lệnh · {label}": "Command · {label}",
    "Phát · {title}{suffix}": "Play · {title}{suffix}",

    # --- dock
    "ĐANG PHÁT": "NOW PLAYING",
    "Chọn một bài để bắt đầu": "Choose a song to start",
    "Sẵn sàng": "Ready",
    "Tốc độ": "Speed",
    "Tốc độ phát": "Playback speed",
    "Bỏ A–B": "Clear A–B",
    "Đặt điểm A của đoạn lặp tại vị trí hiện tại": "Set loop point A at the current position",
    "Đặt điểm B; khi có cả A và B, bài lặp đoạn A–B cho tới khi Dừng":
        "Set point B; with both A and B set, the song loops A–B until you press Stop",
    "Đặt điểm A": "Set point A",
    "Đặt điểm B": "Set point B",
    "Xem trước": "Preview",
    "Phát trên bàn phím ảo trong ứng dụng, không gửi phím nào ra game.":
        "Play on the in-app keyboard without sending any keys to the game.",
    "Bàn phím": "Keyboard",
    "Hiện lưới 15 phím sáng theo nốt đang phát": "Show the 15-key grid lighting up with each note",
    "Phát hoặc tạm dừng (Space)": "Play or pause (Space)",
    "Bài tiếp theo (Ctrl+Phải)": "Next song (Ctrl+Right)",
    "Dừng (Esc)": "Stop (Esc)",
    "Phát": "Play",
    "Dừng": "Stop",
    "Thu nhỏ": "Mini",

    # --- hotkeys page
    "ĐIỀU KHIỂN": "CONTROLS",
    "Phím tắt": "Hotkeys",
    "Bấm vào một ô rồi nhấn tổ hợp phím muốn dùng. Phím tắt toàn cục hoạt động cả khi "
    "đang ở trong game. Nhấn “Lưu và áp dụng” để bật.":
        "Click a field, then press the key combination you want. Global hotkeys work even "
        "while you are in the game. Press “Save and apply” to turn them on.",
    "Phím tắt trong ứng dụng: Space phát/tạm dừng · Esc dừng · Ctrl+→ bài tiếp · Ctrl+M mini "
    "· Ctrl+F tìm · Ctrl+K bảng lệnh · Enter phát bài chọn · Ctrl+Enter thêm hàng chờ "
    "· Ctrl+O nhập sheet":
        "In-app shortcuts: Space play/pause · Esc stop · Ctrl+→ next song · Ctrl+M mini "
        "· Ctrl+F search · Ctrl+K command palette · Enter play selected · Ctrl+Enter add to "
        "queue · Ctrl+O import sheets",
    "Lưu và áp dụng": "Save and apply",
    "Chưa gán": "Not assigned",
    "Tạm dừng / tiếp tục": "Pause / resume",
    "Bài tiếp theo": "Next song",
    "Mỗi hành động và ô bài cần một phím tắt.": "Every action and song slot needs a hotkey.",
    "Một phím đang được dùng cho nhiều hành động.": "One key is used for several actions.",
    "Một phím được Windows giữ riêng. Hãy chọn tổ hợp khác.":
        "A key is reserved by Windows. Choose another combination.",
    "Phím tắt {label}": "Hotkey for {label}",
    "Phím tắt ô bài {0}": "Hotkey for song slot {0}",
    "Bài cho ô {0}": "Song for slot {0}",
    "Ô bài {0}": "Song slot {0}",
    "Phím {0} là phím chơi nhạc trong game; dùng nó làm phím tắt sẽ bị kích hoạt khi bài "
    "đang phát.":
        "{0} is an in-game music key; as a hotkey it would trigger while a song is playing.",

    # --- library page
    "Tên A–Z": "Name A–Z",
    "Tên Z–A": "Name Z–A",
    "Ngắn nhất": "Shortest",
    "Dài nhất": "Longest",
    "Mới thêm": "Recently added",
    "Nghe nhiều": "Most played",
    "Nghe gần đây": "Recently played",
    "Tất cả": "All",
    "Yêu thích": "Favorites",
    "Phát được": "Playable",
    "Gần đây": "Recent",
    "THƯ VIỆN BÀI HÁT": "SONG LIBRARY",
    "Thư viện": "Library",
    "Nhập sheet…": "Import sheets…",
    "Chọn file .txt/.json hoặc kéo-thả file vào cửa sổ":
        "Choose .txt/.json files or drag and drop them onto the window",
    "Tìm theo tên bài, không cần gõ dấu… (Ctrl+F)":
        "Search by song name, accents optional… (Ctrl+F)",
    "Tìm bài hát": "Search songs",
    "Sắp xếp danh sách bài": "Sort the song list",
    "Danh sách bài hát. Enter để phát, Ctrl+Enter để thêm hàng chờ":
        "Song list. Enter to play, Ctrl+Enter to add to the queue",
    "Bài có lớp 2Key/3Key:": "Song has 2Key/3Key layers:",
    "Cách xử lý lớp 2Key/3Key": "How to handle 2Key/3Key layers",
    "Phát bài đã chọn": "Play the selected song",
    "Phát tất cả": "Play all",
    "Trộn bài": "Shuffle",
    "Thay hàng chờ bằng các bài đang hiển thị rồi phát từ đầu.":
        "Replace the queue with the songs shown and play from the first one.",
    "Thay hàng chờ bằng các bài đang hiển thị theo thứ tự ngẫu nhiên.":
        "Replace the queue with the songs shown in random order.",
    "Thư viện đang trống. Nhấn “Nhập sheet…” hoặc kéo-thả file .txt/.json vào cửa sổ để "
    "thêm bài.":
        "The library is empty. Press “Import sheets…” or drag .txt/.json files onto the "
        "window to add songs.",
    "Thêm hàng chờ": "Add to queue",
    "Đổi trạng thái yêu thích": "Toggle favorite",
    "Không hỗ trợ": "Unsupported",
    "chưa phát được với bộ phím/lựa chọn hiện tại":
        "not playable with the current key layout/options",
    "Sheet chưa đọc được.": "The sheet could not be read.",
    "Lọc: {text}": "Filter: {text}",
    "{0} bài · {playable} phát được. Tìm bài, đánh dấu yêu thích hoặc đưa vào hàng chờ.":
        "{0} songs · {playable} playable. Search, mark favorites or add songs to the queue.",
    "Hiển thị {visible}/{total}": "Showing {visible}/{total}",
    "Không có bài nào khớp “{query}”. Hãy thử từ khóa ngắn hơn hoặc chọn bộ lọc Tất cả.":
        "No songs match “{query}”. Try a shorter search or choose the All filter.",
    "Không có bài phù hợp với bộ lọc này.": "No songs match this filter.",
    "{note_count} nốt": "{note_count} notes",
    "{density:.1f} nốt/giây · {difficulty}": "{density:.1f} notes/s · {difficulty}",
    "đã phát {play_count} lần": "played {play_count} times",
    "Chưa có bài yêu thích. Chọn một bài rồi nhấn “Đổi trạng thái yêu thích”.":
        "No favorites yet. Select a song, then press “Toggle favorite”.",
    "Chưa phát bài nào. Các bài đã phát sẽ hiện ở đây.":
        "Nothing played yet. Songs you play will appear here.",

    # --- main window
    "Hàng chờ": "Queue",
    "Hiện hoặc ẩn hàng chờ": "Show or hide the queue",
    "Ctrl+K: tìm bài và chạy lệnh nhanh": "Ctrl+K: find songs and run commands quickly",
    "Ẩn hàng chờ": "Hide queue",
    "Hiện hàng chờ": "Show queue",
    "Cài đặt": "Settings",
    " — hãy click vào cửa sổ game": " — click into the game window",
    "Cần xử lý — mở cửa sổ chính": "Needs attention — open the main window",
    "Đã bỏ đoạn lặp và vị trí bắt đầu.": "Cleared the loop and start position.",
    "Sheet nhạc (*.txt *.json)": "Music sheets (*.txt *.json)",
    "Đã lưu và áp dụng global hotkeys.": "Saved and applied global hotkeys.",
    "Có bản mới": "Update available",
    "Đã chọn · nhấn Phát hoặc bấm Note Runway để chọn vị trí":
        "Selected · press Play or click the Note Runway to choose a position",
    "Không có bài phát được trong danh sách đang hiển thị.":
        "No playable songs in the list shown.",
    "Hàng chờ đang trống.": "The queue is empty.",
    "Chọn bài rồi bấm vào Note Runway để chọn vị trí trước.":
        "Select a song, then click the Note Runway to choose a position first.",
    " Áp dụng từ lần phát tới.": " Applies from the next play.",
    " Nhấn Phát để luyện.": " Press Play to practice.",
    "Hãy dừng bài trước khi đổi chế độ Xem trước.": "Stop the song before changing Preview mode.",
    "Xem trước: phát trên bàn phím ảo, không gửi phím ra game.":
        "Preview: plays on the on-screen keyboard and sends no keys to the game.",
    "Đã tắt Xem trước. Lần phát tới sẽ gửi phím vào game.":
        "Preview is off. The next play will send keys to the game.",
    "Không có file .txt/.json nào để nhập.": "There are no .txt/.json files to import.",
    "Đã nhập {0} bài": "Imported {0} songs",
    ", bỏ qua {skipped}": ", skipped {skipped}",
    "; {0} lỗi: {1}": "; {0} errors: {1}",
    "Hàng chờ đang trống; không có gì để lưu.": "The queue is empty; there is nothing to save.",
    "Lưu playlist": "Save playlist",
    "Tên playlist:": "Playlist name:",
    "Tên playlist không được để trống.": "The playlist name cannot be empty.",
    "Không tìm thấy cửa sổ game. Hãy mở game rồi thử lại.":
        "Game window not found. Open the game and try again.",
    "Hãy dừng bài trước khi đổi chế độ khóa vào game.":
        "Stop the song before changing the game lock.",
    "Hãy dừng bài trước khi đổi cửa sổ mục tiêu.":
        "Stop the song before changing the target window.",
    "Nhập 15 phím vào ô Phím tùy chỉnh rồi nhấn Lưu bộ tùy chỉnh.":
        "Enter 15 keys in the Custom keys field, then press Save layout.",
    "Đã lưu và dùng bộ phím tùy chỉnh.": "Saved and switched to the custom layout.",
    "Không thể áp dụng; cấu hình và phím tắt đang dùng được giữ nguyên.":
        "Could not apply; the current configuration and hotkeys were kept.",
    "Phát / Tạm dừng": "Play / Pause",
    "Phát tất cả bài đang hiển thị": "Play all songs shown",
    "Trộn bài đang hiển thị": "Shuffle songs shown",
    "Đổi chế độ lặp": "Change repeat mode",
    "Bật/tắt Xem trước": "Toggle Preview",
    "Bật/tắt bàn phím": "Toggle keyboard",
    "Mở Thư viện": "Open Library",
    "Mở Phím tắt": "Open Hotkeys",
    "Mở Cài đặt": "Open Settings",
    "Xuất báo cáo chẩn đoán": "Export diagnostic report",
    "Hướng dẫn thiết lập": "Setup guide",
    "Lưu báo cáo chẩn đoán": "Save diagnostic report",
    "Đang dừng an toàn trước khi đóng": "Stopping safely before closing",
    "Không thể đọc danh sách yêu thích; thư viện vẫn được mở. ":
        "Could not read favorites; the library is still open. ",
    "PHIÊN BẢN {__version__}": "VERSION {__version__}",
    "Phiên bản {__version__} · Dữ liệu: {0}": "Version {__version__} · Data: {0}",
    "Hãy mở và chọn cửa sổ game trước khi tiếp tục.":
        "Open and select the game window before resuming.",
    "Xem trước · {0}": "Preview · {0}",
    "Bắt đầu sau {remaining} giây{tail}": "Starting in {remaining} s{tail}",
    "Bắt đầu sau {remaining} giây": "Starting in {remaining} s",
    "Đã phát xong · hết hàng chờ": "Finished · queue complete",
    "Cần xử lý: {message}": "Needs attention: {message}",
    "Sẽ phát từ {0} · nhấn Phát": "Will play from {0} · press Play",
    "Đoạn A–B cần dài ít nhất 0,5 giây.": "The A–B section must be at least 0.5 seconds long.",
    "Đã tìm thấy: {title}": "Found: {title}",
    "Game mất focus · bản nhạc đã tạm dừng": "Game lost focus · song paused",
    "Đã khôi phục phím tắt cũ.": "Restored the previous hotkeys.",
    "Không thể khôi phục listener cũ; hãy mở lại ứng dụng.":
        "Could not restore the previous listener; please restart the app.",
    "Có bản mới {tag}. Mở Cài đặt → Hỗ trợ hoặc trang Releases để tải.":
        "Version {tag} is available. Open Settings → Support or the Releases page to download it.",
    "Sky Macro Player {tag} đã phát hành. Mở trang tải về?":
        "Sky Macro Player {tag} has been released. Open the download page?",
    "Sky Macro Player {tag} đã phát hành.": "Sky Macro Player {tag} has been released.",
    "Đã lưu báo cáo chẩn đoán: {name}": "Saved diagnostic report: {name}",
    "Vẫn đang chạy": "Still running",
    "Ứng dụng ở khay hệ thống. Chọn Thoát để tắt.":
        "The app is in the system tray. Choose Quit to exit.",
    "Không đọc được lịch sử nghe; dữ liệu cũ được giữ nguyên. {state_error}":
        "Could not read listening history; the old data was kept. {state_error}",
    "Mở {label}": "Open {label}",
    "Bài “{title}” chưa thể phát: {error}": "“{title}” cannot be played yet: {error}",
    "Không tìm thấy cửa sổ game. Hãy mở game rồi nhấn Phát lại.":
        "Game window not found. Open the game, then press Play again.",
    "Windows chưa cho phép chuyển focus sang game. Hãy click vào game rồi nhấn Phát.":
        "Windows did not allow switching focus to the game. Click into the game, then press Play.",
    "Đang chuẩn bị": "Getting ready",
    "Trở lại game": "Back to game",
    "Đã phát xong": "Finished",
    "Đã dừng": "Stopped",
    "Lặp đoạn {0}–{1}.{tail}": "Looping {0}–{1}.{tail}",
    "Đã đặt {0} tại {1}.": "Set {0} at {1}.",
    "Đã lưu playlist “{name}” ({0} bài).": "Saved playlist “{name}” ({0} songs).",
    "Playlist “{name}”: {missing} bài không còn trong thư viện và đã được bỏ qua.":
        "Playlist “{name}”: {missing} songs are no longer in the library and were skipped.",
    "Đã mở playlist “{name}” vào hàng chờ. Nhấn Tiếp để phát.":
        "Loaded playlist “{name}” into the queue. Press Next to play.",
    "Đã xóa playlist “{name}”.": "Deleted playlist “{name}”.",
    "Đã quay lại game · đang tiếp tục": "Back in the game · resuming",
    "Mục tiêu khóa focus: {0}.": "Focus lock target: {0}.",
    "{countdown_seconds} giây": "{countdown_seconds} s",
    "Đang dùng bản mới nhất ({__version__}).": "You have the latest version ({__version__}).",
    "Không kiểm tra được cập nhật: {message}": "Could not check for updates: {message}",
    "Lỗi phát nhạc: {message}": "Playback error: {message}",
    "Đã tạm dừng": "Paused",
    "Game mất focus. Click vào game để tiếp tục.":
        "The game lost focus. Click into the game to resume.",
    "Không thể lưu lịch sử/tùy chọn bài: {exc}": "Could not save history/song options: {exc}",
    "Không thể lưu danh sách yêu thích: {exc}": "Could not save favorites: {exc}",
    "Không thể lưu cài đặt: {exc}": "Could not save settings: {exc}",
    "Không thể lưu cấu hình: {exc}. {recovery}":
        "Could not save the configuration: {exc}. {recovery}",
    "Tên bài cũ bị trùng cho phím {0}: {selected}. Hãy gán lại bài bằng đường dẫn đầy đủ.":
        "The old song name for key {0} is ambiguous: {selected}. "
        "Reassign the song using its full path.",
    "Không tìm thấy bài đã gán cho phím {0}: {selected}":
        "Could not find the song assigned to key {0}: {selected}",
    "Không thể tạo báo cáo: {exc}": "Could not create the report: {exc}",
    "Không thể chép sheet mẫu: {exc}": "Could not copy the sample sheets: {exc}",
    "Đã sao lưu cấu hình lỗi tại {name} và lưu cấu hình mới.":
        "Backed up the broken configuration as {name} and saved a new one.",
    "Hết hàng chờ": "Queue complete",
    "Đã phát xong tất cả bài trong hàng chờ.": "Finished every song in the queue.",
    "đã phát được": "now playable",
    "vẫn bị chặn": "still blocked",
    "“{title}”: {result}.": "“{title}”: {result}.",
    "Đã đổi ngôn ngữ. Mở lại ứng dụng để áp dụng.":
        "Language changed. Restart the app to apply it.",

    # --- mini
    "Đang đếm ngược": "Counting down",
    "Đang phát": "Playing",
    "Đang chờ cửa sổ Sky": "Waiting for the Sky window",
    "Đang dừng an toàn": "Stopping safely",
    "Có lỗi phát nhạc": "Playback error",
    "Tiếp tục": "Resume",
    "Tạm dừng": "Pause",
    "Chưa chọn bài": "No song selected",
    "Sky Macro Player — Mini": "Sky Macro Player — Mini",
    "Phát hoặc tạm dừng": "Play or pause",
    "Phát bài tiếp theo": "Play the next song",
    "Dừng phát nhạc": "Stop playback",
    "Ghim mini player trên cùng": "Pin the mini player on top",
    "Mở cửa sổ đầy đủ": "Open the full window",
    "Mở rộng": "Expand",
    "Ghim": "Pin",

    # --- queue panel
    "Hàng chờ đang trống. Chọn một bài trong thư viện và nhấn “Thêm hàng chờ”.":
        "The queue is empty. Select a song in the library and press “Add to queue”.",
    "Lặp: Tắt": "Repeat: Off",
    "Lặp: Hàng chờ": "Repeat: Queue",
    "Lặp: Một bài": "Repeat: One",
    "PHÁT TIẾP": "UP NEXT",
    "Hàng chờ phát nhạc": "Playback queue",
    "Tắt → Lặp hàng chờ → Lặp một bài. Dừng luôn kết thúc việc lặp.":
        "Off → Repeat queue → Repeat one. Stop always ends repeating.",
    "Trộn": "Shuffle",
    "Xáo trộn thứ tự các bài đang chờ.": "Shuffle the order of queued songs.",
    "Xóa hết": "Clear all",
    "Hoàn tác": "Undo",
    "Hoàn tác thay đổi hàng chờ": "Undo the queue change",
    "Bỏ bài đã chọn": "Remove selected song",
    "Lưu hàng chờ thành playlist…": "Save queue as playlist…",
    "Xóa playlist": "Delete playlist",
    "Chưa có playlist": "No playlists yet",
    "Chế độ lặp không hợp lệ: {mode}": "Invalid repeat mode: {mode}",
    "Mở “{name}”": "Open “{name}”",
    "{count} bài đang chờ": "{count} songs queued",

    # --- settings page
    "TÙY CHỌN": "PREFERENCES",
    "Phát nhạc": "Playback",
    "15 phím, hàng 1 → hàng 3": "15 keys, row 1 → row 3",
    "Ví dụ bộ cũ: yuiophjkl;nm,./": "Old layout example: yuiophjkl;nm,./",
    "15 phím của bộ tùy chỉnh": "The 15 keys of the custom layout",
    "Lưu bộ phím": "Save layout",
    "Thời gian đếm ngược": "Countdown duration",
    "3 giây": "3 s",
    "Phím tùy chỉnh": "Custom keys",
    "Đếm ngược": "Countdown",
    "Giao diện": "Appearance",
    "Ngôn ngữ": "Language",
    "Ngôn ngữ giao diện": "Interface language",
    "Áp dụng sau khi mở lại ứng dụng.": "Applies after restarting the app.",
    "Giảm chuyển động của Note Runway": "Reduce Note Runway motion",
    "Giữ mini player trên cùng": "Keep the mini player on top",
    "Đóng cửa sổ thì thu xuống khay hệ thống": "Minimize to the system tray when closing",
    "Phát âm thanh khi dùng chế độ Xem trước": "Play sound in Preview mode",
    "Khi game mất focus, bản nhạc tự tạm dừng để không gõ nhầm vào ứng dụng khác. "
    "Mặc định nhận cửa sổ Sky (Sky.exe); có thể chọn game khác như Heartopia.":
        "When the game loses focus, the song pauses so no keys go to another app. "
        "Sky (Sky.exe) is the default target; you can choose another game such as Heartopia.",
    "Tự tiếp tục khi quay lại game": "Resume automatically when back in the game",
    "Mục tiêu: Sky (Sky.exe)": "Target: Sky (Sky.exe)",
    "Kiểm tra cửa sổ": "Check window",
    "Chọn cửa sổ game khác…": "Choose another game window…",
    "Dùng lại Sky": "Use Sky again",
    "Hỗ trợ": "Support",
    "Tự kiểm tra bản mới trên GitHub khi mở ứng dụng": "Check GitHub for updates on start-up",
    "Mở hướng dẫn thiết lập": "Open the setup guide",
    "Xuất báo cáo chẩn đoán…": "Export diagnostic report…",
    "Mở thư mục dữ liệu": "Open data folder",
    "Kiểm tra cập nhật": "Check for updates",
    "{value} giây": "{value} s",
    "Mục tiêu: {exe_name} (do bạn chọn)": "Target: {exe_name} (your choice)",

    # --- tray and widgets
    "Mở cửa sổ": "Open window",
    "Thoát": "Quit",
    "Sky Macro Player — {state_label}": "Sky Macro Player — {state_label}",
    "Tiến trình nốt nhạc": "Note progress",
    "Bàn phím 15 nốt": "15-note keyboard",
    "Nhấn tổ hợp phím…": "Press a key combination…",
    "Nhấn tổ hợp phím muốn dùng. Backspace để xóa, Tab để chuyển ô.":
        "Press the key combination to use. Backspace clears, Tab moves to the next field.",

    # --- sheet editor
    '{step} ms · {ratio} khớp':
        '{step} ms · {ratio} fit',
    '1 phách':
        '1 beat',
    '1/{parts} phách':
        '1/{parts} beat',
    'Chỉnh sheet — {title}':
        'Edit sheet — {title}',
    'Chỉnh sheet':
        'Edit sheet',
    'Nguồn: {title}':
        'Source: {title}',
    '{count} nốt':
        '{count} notes',
    'lưới {grid}':
        'grid {grid}',
    'Bản gốc không bao giờ bị sửa. Kết quả được lưu thành một sheet mới trong thư viện.':
        'The original is never modified. The result is saved as a new sheet in the library.',
    'Gộp lớp 2Key/3Key về 15 phím':
        'Merge 2Key/3Key layers onto the 15 keys',
    'Sheet này chỉ có một lớp.':
        'This sheet has a single layer.',
    'Lớp':
        'Layers',
    ' giây':
        ' s',
    'Cả bài':
        'Whole song',
    'Từ':
        'From',
    'đến':
        'to',
    'Cắt đoạn':
        'Section',
    'Chỉnh nhịp theo lưới':
        'Snap to grid',
    'Chọn lưới nhịp':
        'Choose the beat grid',
    'Bước lưới tùy chỉnh':
        'Custom grid step',
    'Nhịp':
        'Timing',
    'Sheet đã khớp lưới; chỉ cần chỉnh nhịp khi đổi sang lưới thô hơn.':
        'This sheet already fits a grid; snapping only matters for a coarser grid.',
    "Sheet chưa khớp lưới nào rõ ràng (thường là bản ghi tay). Hãy thử từng lưới "
    "và nghe thử trước khi lưu.":
        "This sheet fits no clear grid (usually a hand recording). Try each grid and "
        "listen before saving.",
    ' bậc':
        ' steps',
    "1 bậc = sang phím kế bên; 7 bậc = một quãng tám. "
    "Nốt vượt 15 phím được gập quãng tám.":
        "1 step = the neighbouring key; 7 steps = one octave. "
        "Notes beyond the 15 keys fold by an octave.",
    'Dịch tông':
        'Transpose',
    '120% nhanh hơn 20%; thay đổi được lưu vào bản mới.':
        '120% is 20% faster; the change is saved into the new sheet.',
    'Nghe thử':
        'Listen',
    'Phát bản đã chỉnh trên bàn phím ảo, không gửi phím ra game.':
        'Play the edited sheet on the virtual keyboard without sending keys to the game.',
    'Dừng nghe':
        'Stop listening',
    'Tên bản mới':
        'New sheet name',
    '{title} (chỉnh)':
        '{title} (edited)',
    'Tên sheet mới':
        'New sheet name',
    'Lưu thành bản mới':
        'Save as new sheet',
    'Điểm bắt đầu phải nhỏ hơn điểm kết thúc.':
        'The start must be before the end.',
    'Nốt: {before} → {after} · Thời lượng: {length_before} → {length_after} · Khớp lưới: {grid}':
        'Notes: {before} → {after} · Length: {length_before} → {length_after} · Grid fit: {grid}',
    ' · Đã dời {count} nhịp':
        ' · Moved {count} beats',
    'Hãy đặt tên cho bản mới.':
        'Give the new sheet a name.',
    'Đã lưu “{name}” vào thư viện. Bạn có thể chỉnh tiếp và lưu thêm bản khác.':
        'Saved “{name}” to the library. You can keep editing and save another version.',
    'Đoạn đã chọn không còn nốt nào.':
        'The selected section has no notes.',
    'Bản mới vẫn còn lớp 2Key/3Key; bật “Gộp lớp” để phát được.':
        'The new sheet still has 2Key/3Key layers; turn on “Merge layers” to make it playable.',
    '{count} nốt vượt 15 phím đã được gập quãng tám.':
        '{count} notes beyond the 15 keys were folded by an octave.',
    '{count} nốt trùng thời điểm và phím đã được gộp.':
        '{count} notes with the same time and key were merged.',
    'Chỉnh sheet…':
        'Edit sheet…',
    'Gộp lớp, cắt đoạn, chỉnh nhịp, dịch tông, đổi tempo; lưu thành bản mới':
        'Merge layers, cut, snap timing, transpose, change tempo; save as a new sheet',
    'Hãy chọn một bài trong thư viện để chỉnh.':
        'Select a song in the library to edit.',
    'Không đọc được sheet để chỉnh: {exc}':
        'Could not read the sheet to edit: {exc}',
    'Hãy dừng bài đang phát trước khi nghe thử.':
        'Stop the current song before listening.',
    'Bản chỉnh còn phím chưa hỗ trợ: {keys}.':
        'The edited sheet still has unsupported keys: {keys}.',
    'Bản chỉnh':
        'Edited sheet',
    'Không thể lưu bản chỉnh: {exc}':
        'Could not save the edited sheet: {exc}',
    'Đã lưu bản chỉnh “{name}”.':
        'Saved the edited sheet “{name}”.',
    'Chỉnh sheet bài đang chọn':
        'Edit the selected sheet',
    'Đóng':
        'Close',
    '{before} → {after}':
        '{before} → {after}',
    'chưa rõ':
        'unknown',
}
