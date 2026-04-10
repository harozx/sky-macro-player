import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pynput import keyboard as pynput_keyboard
from macro_core import MacroPlayer

# ==========================================
#  CÀI ĐẶT
# ==========================================
SHEETS_DIR = "sheets"
FAVORITES_FILE = "favorites.json"
NUM_HOTKEY_SLOTS = 8
HOTKEY_CONFIG_FILE = "hotkeys.json"

# Phím mặc định cho mỗi slot (tránh xung đột Steam)
DEFAULT_HOTKEYS = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]

COLORS = {
    "bg":          "#1a1a2e",
    "panel":       "#16213e",
    "card":        "#0f3460",
    "accent":      "#e94560",
    "accent2":     "#533483",
    "text":        "#eaeaea",
    "text_dim":    "#8888aa",
    "text_dark":   "#555577",
    "success":     "#4ecca3",
    "warning":     "#f5a623",
    "list_sel":    "#e94560",
}

MINI_W, MINI_H   = 300, 44   # Kích thước mini bar
FULL_W, FULL_H   = 480, 640  # Kích thước đầy đủ


# ==========================================
#  CỬA SỔ CHÍNH
# ==========================================
class MacroGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Macro Player")

        # ── Ẩn frame Windows gốc (không dùng thanh tiêu đề hệ thống) ──
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLORS["bg"])

        # Độ trong suốt mặc định
        self._alpha = 0.95
        self._saved_layout = "old"  # Sẽ ghi đè nếu có config cũ
        self.root.attributes("-alpha", self._alpha)

        # --- ENGINE ---
        self.player = MacroPlayer()
        self.STOP_EVENT = threading.Event()
        self.PAUSE_EVENT = threading.Event()
        self.play_thread: threading.Thread | None = None

        # --- DỮ LIỆU ---
        self.song_files: list[str] = []
        self.hotkey_slots: list[str | None] = [None] * NUM_HOTKEY_SLOTS
        # hotkey_keys[i] = tên phím (str pynput) cho slot i
        self.hotkey_keys: list[str] = list(DEFAULT_HOTKEYS)
        self.favorites: list[dict] = []

        # --- TRẠNG THÁI ---
        self.is_playing     = False
        self._is_mini       = False
        self._binding_slot  = -1    # Slot đang chờ bind (-1 = không)
        self._drag_x        = 0
        self._drag_y        = 0

        # --- KHỞI TẠO ---
        self._load_favorites()
        self._load_song_list()
        self._load_hotkey_config()
        self._build_ui()
        self._start_global_listener()

        # Căn giữa màn hình
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{FULL_W}x{FULL_H}+{(sw-FULL_W)//2}+{(sh-FULL_H)//2}")

    # ==========================================
    #  XÂY DỰNG GIAO DIỆN
    # ==========================================
    def _build_ui(self):
        self._build_titlebar()
        self._main_content = tk.Frame(self.root, bg=COLORS["bg"])
        self._main_content.pack(fill="both", expand=True)
        self._build_tabs(self._main_content)
        self._build_statusbar()

    # --- TITLEBAR ---
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=COLORS["card"], height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._titlebar = bar

        # Icon + Tên
        tk.Label(
            bar, text="🎵  MACRO PLAYER",
            bg=COLORS["card"], fg=COLORS["accent"],
            font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=12, pady=8)

        # Nút Đóng ✕
        btn_close = tk.Label(
            bar, text=" ✕ ", bg=COLORS["card"], fg=COLORS["text_dim"],
            font=("Segoe UI", 11), cursor="hand2"
        )
        btn_close.pack(side="right", padx=6)
        btn_close.bind("<Button-1>", lambda e: self._on_close())
        btn_close.bind("<Enter>", lambda e: btn_close.config(fg=COLORS["accent"]))
        btn_close.bind("<Leave>", lambda e: btn_close.config(fg=COLORS["text_dim"]))

        # Nút Thu nhỏ xuống Taskbar ↓
        btn_taskbar = tk.Label(
            bar, text=" — ", bg=COLORS["card"], fg=COLORS["text_dim"],
            font=("Segoe UI", 11), cursor="hand2"
        )
        btn_taskbar.pack(side="right")
        btn_taskbar.bind("<Button-1>", lambda e: self._minimize_to_taskbar())
        btn_taskbar.bind("<Enter>", lambda e: btn_taskbar.config(fg=COLORS["warning"]))
        btn_taskbar.bind("<Leave>", lambda e: btn_taskbar.config(fg=COLORS["text_dim"]))

        # Nút Mini Mode ⊟ (thu thành thanh nhỏ nổi)
        self._mini_btn = tk.Label(
            bar, text=" ⊟ ", bg=COLORS["card"], fg=COLORS["text_dim"],
            font=("Segoe UI", 11), cursor="hand2"
        )
        self._mini_btn.pack(side="right")
        self._mini_btn.bind("<Button-1>", lambda e: self._toggle_mini())
        self._mini_btn.bind("<Enter>", lambda e: self._mini_btn.config(fg=COLORS["success"]))
        self._mini_btn.bind("<Leave>", lambda e: self._mini_btn.config(fg=COLORS["text_dim"]))

        # Drag
        bar.bind("<ButtonPress-1>", self._on_drag_start)
        bar.bind("<B1-Motion>",     self._on_drag_motion)

    # --- TABS ---
    def _build_tabs(self, parent):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["panel"], foreground=COLORS["text_dim"],
            padding=[14, 6], font=("Segoe UI", 9, "bold"), borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["card"])],
            foreground=[("selected", COLORS["accent"])],
        )

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        tab1 = tk.Frame(nb, bg=COLORS["bg"])
        nb.add(tab1, text="  📂 Nhạc  ")
        self._build_tab_songs(tab1)

        tab2 = tk.Frame(nb, bg=COLORS["bg"])
        nb.add(tab2, text="  ⌨️ Hotkey  ")
        self._build_tab_hotkeys(tab2)

        tab3 = tk.Frame(nb, bg=COLORS["bg"])
        nb.add(tab3, text="  ❤️ Album  ")
        self._build_tab_album(tab3)

        tab4 = tk.Frame(nb, bg=COLORS["bg"])
        nb.add(tab4, text="  ⚙️ Cài đặt  ")
        self._build_tab_settings(tab4)

    # --- TAB NHẠC ---
    def _build_tab_songs(self, parent):
        search_frame = tk.Frame(parent, bg=COLORS["panel"], pady=4)
        search_frame.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(search_frame, text="🔍", bg=COLORS["panel"], fg=COLORS["text_dim"]).pack(side="left", padx=(8, 2))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._filter_songs())
        tk.Entry(
            search_frame, textvariable=self._search_var,
            bg=COLORS["panel"], fg=COLORS["text"], insertbackground=COLORS["text"],
            relief="flat", font=("Segoe UI", 10), bd=0
        ).pack(side="left", fill="x", expand=True, padx=4, ipady=4)

        list_frame = tk.Frame(parent, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=6)
        scrollbar = tk.Scrollbar(list_frame, bg=COLORS["panel"], troughcolor=COLORS["bg"], relief="flat")
        scrollbar.pack(side="right", fill="y")
        self._song_listbox = tk.Listbox(
            list_frame,
            bg=COLORS["panel"], fg=COLORS["text"],
            selectbackground=COLORS["list_sel"], selectforeground="white",
            activestyle="none", relief="flat", bd=0,
            font=("Segoe UI", 9), yscrollcommand=scrollbar.set,
            highlightthickness=0
        )
        self._song_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._song_listbox.yview)
        self._refresh_song_listbox()

        btn_frame = tk.Frame(parent, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._make_button(btn_frame, "▶  Phát", self._play_selected, COLORS["accent"]).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        self._make_button(btn_frame, "■  Dừng", self._stop_playback, COLORS["accent2"]).pack(
            side="left", fill="x", expand=True)

        self._make_button(parent, "❤  Thêm vào Album Yêu Thích", self._add_selected_to_fav, COLORS["card"]).pack(
            fill="x", padx=8, pady=(0, 6))

    # --- TAB HOTKEY ---
    def _build_tab_hotkeys(self, parent):
        self._bind_status_lbl = tk.Label(
            parent,
            text="Gán bài hát + phím tắt tùy chỉnh cho mỗi slot.",
            bg=COLORS["bg"], fg=COLORS["text_dim"],
            font=("Segoe UI", 9), justify="center"
        )
        self._bind_status_lbl.pack(pady=(10, 6))

        self._hotkey_labels = []   # Label tên bài
        self._hotkey_key_btns = [] # Label phím (click để đổi)
        slots_frame = tk.Frame(parent, bg=COLORS["bg"])
        slots_frame.pack(fill="both", expand=True, padx=12)

        for i in range(NUM_HOTKEY_SLOTS):
            row = tk.Frame(slots_frame, bg=COLORS["panel"], pady=2)
            row.pack(fill="x", pady=3)

            # --- Nút PHÍM (click để rebind) ---
            key_btn = tk.Label(
                row, text=f"  {self.hotkey_keys[i].upper()}  ",
                bg=COLORS["card"], fg=COLORS["accent"],
                font=("Consolas", 9, "bold"), cursor="hand2", width=6
            )
            key_btn.pack(side="left", ipady=6)
            key_btn.bind("<Button-1>", lambda e, idx=i: self._start_rebind(idx))
            key_btn.bind("<Enter>", lambda e, b=key_btn: b.config(bg=COLORS["accent2"]))
            key_btn.bind("<Leave>", lambda e, b=key_btn: b.config(
                bg=COLORS["card"] if self._binding_slot != self._hotkey_key_btns.index(b) else COLORS["warning"]
            ))
            self._hotkey_key_btns.append(key_btn)

            # --- Label tên bài ---
            lbl = tk.Label(
                row, text=self._get_slot_display(i),
                bg=COLORS["panel"], fg=COLORS["text"],
                font=("Segoe UI", 9), anchor="w"
            )
            lbl.pack(side="left", fill="x", expand=True, padx=8)
            self._hotkey_labels.append(lbl)

            # --- Nút Gán bài ---
            tk.Button(
                row, text="Gán",
                bg=COLORS["accent2"], fg="white",
                relief="flat", cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                command=lambda idx=i: self._assign_hotkey(idx)
            ).pack(side="right", padx=4, pady=4)

            # --- Nút Xóa bài ---
            tk.Button(
                row, text="✕",
                bg=COLORS["bg"], fg=COLORS["text_dim"],
                relief="flat", cursor="hand2",
                font=("Segoe UI", 9),
                command=lambda idx=i: self._clear_hotkey(idx)
            ).pack(side="right", padx=(0, 2))

        tk.Label(
            parent, text="Click vào tên phím để đổi  |  ESC trong hộp bind = huỷ",
            bg=COLORS["bg"], fg=COLORS["text_dark"],
            font=("Segoe UI", 8)
        ).pack(pady=8)

    # --- TAB ALBUM ---
    def _build_tab_album(self, parent):
        tk.Label(parent, text="Album Yêu Thích", bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Segoe UI", 10, "bold")).pack(pady=(12, 4))
        list_frame = tk.Frame(parent, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        scrollbar = tk.Scrollbar(list_frame, bg=COLORS["panel"], troughcolor=COLORS["bg"], relief="flat")
        scrollbar.pack(side="right", fill="y")
        self._fav_listbox = tk.Listbox(
            list_frame,
            bg=COLORS["panel"], fg=COLORS["text"],
            selectbackground=COLORS["list_sel"], selectforeground="white",
            activestyle="none", relief="flat", bd=0,
            font=("Segoe UI", 9), yscrollcommand=scrollbar.set,
            highlightthickness=0
        )
        self._fav_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._fav_listbox.yview)
        self._refresh_fav_listbox()
        btn_frame = tk.Frame(parent, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._make_button(btn_frame, "▶  Phát", self._play_fav_selected, COLORS["accent"]).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        self._make_button(btn_frame, "🗑  Xóa", self._remove_fav_selected, COLORS["accent2"]).pack(
            side="left", fill="x", expand=True)

    # --- TAB CÀI ĐẶT ---
    def _build_tab_settings(self, parent):
        tk.Label(parent, text="⚙️  Cài đặt", bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Segoe UI", 11, "bold")).pack(pady=(16, 4))

        # Bộ phím
        layout_frame = tk.Frame(parent, bg=COLORS["panel"])
        layout_frame.pack(fill="x", padx=16, pady=8)
        tk.Label(layout_frame, text="🎹  Bộ phím:", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=12, pady=10)
        self._layout_var = tk.StringVar(value=getattr(self, "_saved_layout", "old"))
        for key in MacroPlayer.KEY_LAYOUTS:
            name = MacroPlayer.KEY_LAYOUTS[key]["name"]
            tk.Radiobutton(
                layout_frame, text=name,
                variable=self._layout_var, value=key,
                bg=COLORS["panel"], fg=COLORS["text"],
                selectcolor=COLORS["card"],
                activebackground=COLORS["panel"], activeforeground=COLORS["accent"],
                command=self._change_layout, font=("Segoe UI", 9)
            ).pack(side="left", padx=8, pady=10)

        # Độ trong suốt
        alpha_frame = tk.Frame(parent, bg=COLORS["panel"])
        alpha_frame.pack(fill="x", padx=16, pady=8)
        tk.Label(alpha_frame, text="🔆  Trong suốt:", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=12, pady=10)
        self._alpha_var = tk.DoubleVar(value=self._alpha)
        alpha_slider = tk.Scale(
            alpha_frame,
            from_=0.2, to=1.0, resolution=0.05,
            orient="horizontal", variable=self._alpha_var,
            command=self._on_alpha_change,
            bg=COLORS["panel"], fg=COLORS["text"],
            troughcolor=COLORS["card"], highlightthickness=0,
            activebackground=COLORS["accent"], sliderlength=16,
            length=160, showvalue=False
        )
        alpha_slider.pack(side="left", padx=8, pady=6)
        self._alpha_lbl = tk.Label(alpha_frame, text=f"{int(self._alpha*100)}%",
                                   bg=COLORS["panel"], fg=COLORS["text_dim"],
                                   font=("Segoe UI", 9))
        self._alpha_lbl.pack(side="left", padx=4)
        # Áp dụng alpha đã lưu
        self.root.attributes("-alpha", self._alpha)

        # Phím tắt
        info_frame = tk.Frame(parent, bg=COLORS["panel"])
        info_frame.pack(fill="x", padx=16, pady=8)
        tk.Label(info_frame, text="⌨️  Phím chức năng:",
                 bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
                 
        # Nút đổi phím Tạm dừng
        pause_row = tk.Frame(info_frame, bg=COLORS["panel"])
        pause_row.pack(fill="x", padx=12, pady=4)
        tk.Label(pause_row, text="Tạm dừng / Tiếp tục:", bg=COLORS["panel"], fg=COLORS["text_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._btn_pause_bind = tk.Label(pause_row, text=f"  {self.pause_hotkey.upper()}  ", 
                                       bg=COLORS["card"], fg=COLORS["warning"], font=("Consolas", 9, "bold"), cursor="hand2")
        self._btn_pause_bind.pack(side="left", padx=8, ipady=4, ipadx=4)
        self._btn_pause_bind.bind("<Button-1>", lambda e: self._start_rebind_pause())
        self._btn_pause_bind.bind("<Enter>", lambda e, b=self._btn_pause_bind: b.config(bg=COLORS["accent2"]))
        self._btn_pause_bind.bind("<Leave>", lambda e, b=self._btn_pause_bind: b.config(
            bg=COLORS["card"] if not getattr(self, "_binding_pause", False) else COLORS["warning"]
        ))
        tk.Label(pause_row, text="(Click để đổi)", bg=COLORS["panel"], fg=COLORS["text_dark"],
                 font=("Segoe UI", 8)).pack(side="left")

        # Info cố định
        for key, desc in [("F10", "Dừng hẳn bài (hủy)"), ("ESC", "Dừng khẩn cấp")]:
            row = tk.Frame(info_frame, bg=COLORS["panel"])
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=key, bg=COLORS["card"], fg=COLORS["accent"],
                     font=("Consolas", 9, "bold"), width=8).pack(side="left", padx=(0, 8))
            tk.Label(row, text=desc, bg=COLORS["panel"], fg=COLORS["text_dim"],
                     font=("Segoe UI", 9)).pack(side="left")
        
        tk.Frame(info_frame, bg=COLORS["panel"], height=8).pack()

        tk.Frame(parent, bg=COLORS["bg"]).pack(fill="both", expand=True)
        self._make_button(parent, "✕  Thoát chương trình", self._on_close, COLORS["accent"]).pack(
            fill="x", padx=16, pady=16)

    # --- STATUS BAR ---
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=COLORS["card"], height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._statusbar = bar

        self._status_dot = tk.Label(bar, text="●", bg=COLORS["card"], fg=COLORS["text_dark"],
                                    font=("Segoe UI", 9))
        self._status_dot.pack(side="left", padx=(8, 2), pady=5)
        self._status_lbl = tk.Label(bar, text="Sẵn sàng", bg=COLORS["card"], fg=COLORS["text_dim"],
                                    font=("Segoe UI", 8))
        self._status_lbl.pack(side="left", pady=5)
        tk.Label(bar, text=f"Bộ phím: {self.player.get_layout_name()}",
                 bg=COLORS["card"], fg=COLORS["text_dark"],
                 font=("Segoe UI", 8)).pack(side="right", padx=10)

    # ==========================================
    #  MINI MODE
    # ==========================================
    def _toggle_mini(self):
        if self._is_mini:
            self._expand()
        else:
            self._collapse()

    def _collapse(self):
        """Thu thành thanh nhỏ ngang."""
        self._is_mini = True
        self._save_full_pos()

        # Ẩn nội dung + statusbar
        self._main_content.pack_forget()
        self._statusbar.pack_forget()

        # Đổi icon nút mini thành ⊞ (mở rộng)
        self._mini_btn.config(text=" ⊞ ")

        # Titlebar mini hơn
        self._titlebar.config(height=MINI_H)
        self.root.geometry(f"{MINI_W}x{MINI_H}")

    def _expand(self):
        """Trở lại giao diện đầy đủ."""
        self._is_mini = False

        self._main_content.pack(fill="both", expand=True)
        self._statusbar.pack(fill="x", side="bottom")

        self._mini_btn.config(text=" ⊟ ")
        self._titlebar.config(height=40)

        x, y = self._full_x, self._full_y
        self.root.geometry(f"{FULL_W}x{FULL_H}+{x}+{y}")

    def _save_full_pos(self):
        self._full_x = self.root.winfo_x()
        self._full_y = self.root.winfo_y()

    def _minimize_to_taskbar(self):
        """Thu nhỏ xuống taskbar (iconify). Cần bật lại overrideredirect tạm thời."""
        self.root.overrideredirect(False)
        self.root.iconify()
        # Khi restore, bật lại overrideredirect
        self.root.bind("<Map>", self._on_restore)

    def _on_restore(self, event=None):
        self.root.overrideredirect(True)
        self.root.unbind("<Map>")

    # ==========================================
    #  HELPER UI
    # ==========================================
    def _make_button(self, parent, text, command, bg_color):
        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg_color, fg="white",
            relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            pady=8, bd=0, activeforeground="white",
            activebackground=self._darken(bg_color)
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=self._darken(bg_color)))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg_color))
        return btn

    @staticmethod
    def _darken(hex_color):
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{max(0,r-25):02x}{max(0,g-25):02x}{max(0,b-25):02x}"

    def _set_status(self, text, playing=False):
        color = COLORS["success"] if playing else COLORS["text_dim"]
        self._status_dot.config(fg=color)
        self._status_lbl.config(text=text, fg=color)

    def _on_alpha_change(self, val):
        v = float(val)
        self._alpha = v
        self.root.attributes("-alpha", v)
        self._alpha_lbl.config(text=f"{int(v*100)}%")
        self._save_hotkey_config()

    # ==========================================
    #  DRAG
    # ==========================================
    def _on_drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ==========================================
    #  DỮ LIỆU NHẠC
    # ==========================================
    def _load_song_list(self):
        os.makedirs(SHEETS_DIR, exist_ok=True)
        try:
            self.song_files = sorted(
                [f for f in os.listdir(SHEETS_DIR) if f.endswith((".json", ".txt"))],
                key=str.lower
            )
        except FileNotFoundError:
            self.song_files = []

    def _refresh_song_listbox(self):
        if not hasattr(self, "_song_listbox"):
            return
        q = self._search_var.get().lower() if hasattr(self, "_search_var") else ""
        self._song_listbox.delete(0, "end")
        self._filtered_songs = [s for s in self.song_files if q in s.lower()]
        for name in self._filtered_songs:
            self._song_listbox.insert("end", f"  {name}")

    def _filter_songs(self):
        self._refresh_song_listbox()

    # ==========================================
    #  FAVORITES
    # ==========================================
    def _load_favorites(self):
        if not os.path.exists(FAVORITES_FILE):
            self.favorites = []
            return
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                self.favorites = json.load(f)
        except Exception:
            self.favorites = []

    def _save_favorites(self):
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.favorites, f, indent=4, ensure_ascii=False)

    def _refresh_fav_listbox(self):
        if not hasattr(self, "_fav_listbox"):
            return
        self._fav_listbox.delete(0, "end")
        for song in self.favorites:
            self._fav_listbox.insert("end", f"  {song['name']}")

    def _add_selected_to_fav(self):
        sel = self._song_listbox.curselection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn bài hát trước!", parent=self.root)
            return
        filename = self._filtered_songs[sel[0]]
        full_path = os.path.join(SHEETS_DIR, filename)
        if any(s["path"] == full_path for s in self.favorites):
            messagebox.showinfo("Thông báo", "Bài này đã có trong Album!", parent=self.root)
            return
        self.favorites.append({"name": filename, "type": "JSON", "path": full_path})
        self._save_favorites()
        self._refresh_fav_listbox()
        self._set_status(f"Đã thêm '{filename}' vào Album ❤")

    def _remove_fav_selected(self):
        sel = self._fav_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        name = self.favorites[idx]["name"]
        self.favorites.pop(idx)
        self._save_favorites()
        self._refresh_fav_listbox()
        self._set_status(f"Đã xóa '{name}' khỏi Album")

    # ==========================================
    #  HOTKEY SLOTS
    # ==========================================
    def _get_slot_display(self, idx):
        return self.hotkey_slots[idx] if self.hotkey_slots[idx] else "(Chưa gán)"

    def _assign_hotkey(self, idx):
        sel = self._song_listbox.curselection()
        if not sel:
            messagebox.showinfo("Thông báo", "Hãy chọn bài hát trong tab 'Nhạc' trước!", parent=self.root)
            return
        filename = self._filtered_songs[sel[0]]
        self.hotkey_slots[idx] = filename
        self._hotkey_labels[idx].config(text=filename, fg=COLORS["success"])
        self._set_status(f"{self.hotkey_keys[idx].upper()} → {filename}")
        self._save_hotkey_config()

    def _clear_hotkey(self, idx):
        self.hotkey_slots[idx] = None
        self._hotkey_labels[idx].config(text="(Chưa gán)", fg=COLORS["text_dim"])
        self._save_hotkey_config()

    # ==========================================
    #  PHÁT NHẠC
    # ==========================================
    def _load_song_data(self, filepath):
        for enc in ("utf-16", "utf-8"):
            try:
                with open(filepath, "r", encoding=enc) as f:
                    return json.load(f)
            except (UnicodeError, UnicodeDecodeError):
                continue
            except Exception as e:
                self._set_status(f"Lỗi đọc file: {e}")
                return None
        return None

    def _play_song_file(self, filepath, song_name):
        self.is_playing = True
        self.root.after(0, lambda: self._set_status(f"▶  Đang phát: {song_name}", playing=True))
        song_data = self._load_song_data(filepath)
        if song_data is None:
            self.is_playing = False
            return
        self.player.play_json_sheet(song_data, self.STOP_EVENT, self.PAUSE_EVENT)
        self.is_playing = False
        if self.STOP_EVENT.is_set():
            self.root.after(0, lambda: self._set_status("■  Đã dừng"))
        else:
            self.root.after(0, lambda: self._set_status(f"✓  Xong: {song_name}"))

    def _start_play(self, filepath, song_name):
        if self.is_playing:
            self.STOP_EVENT.set()
            if self.play_thread and self.play_thread.is_alive():
                self.play_thread.join(timeout=1.5)
        self.STOP_EVENT.clear()
        self.PAUSE_EVENT.clear()
        self._current_song_name = song_name
        self.play_thread = threading.Thread(
            target=self._play_song_file, args=(filepath, song_name), daemon=True
        )
        self.play_thread.start()

    def _stop_playback(self):
        if self.is_playing or (self.play_thread and self.play_thread.is_alive()):
            self.STOP_EVENT.set()
            self.PAUSE_EVENT.clear()
            self._set_status("■  Đang dừng...")

    def _toggle_pause(self):
        if not self.is_playing:
            return
        if self.PAUSE_EVENT.is_set():
            # Đang pause -> Resume
            self.PAUSE_EVENT.clear()
            self.root.after(0, lambda: self._set_status(f"▶  Đang phát: {getattr(self, '_current_song_name', '...')}", playing=True))
        else:
            # Đang play -> Pause
            self.PAUSE_EVENT.set()
            self.root.after(0, lambda: self._set_status(f"⏸  Tạm dừng: {getattr(self, '_current_song_name', '...')}", playing=False))
            # Đổi màu vàng cho nút pause
            self.root.after(0, lambda: self._status_dot.config(fg=COLORS["warning"]))
            self.root.after(0, lambda: self._status_lbl.config(fg=COLORS["warning"]))

    def _play_selected(self):
        sel = self._song_listbox.curselection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn bài hát!", parent=self.root)
            return
        filename = self._filtered_songs[sel[0]]
        self._start_play(os.path.join(SHEETS_DIR, filename), filename)

    def _play_fav_selected(self):
        sel = self._fav_listbox.curselection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn bài hát!", parent=self.root)
            return
        song = self.favorites[sel[0]]
        self._start_play(song["path"], song["name"])

    def _play_hotkey_slot(self, idx):
        filename = self.hotkey_slots[idx]
        if not filename:
            return
        filepath = os.path.join(SHEETS_DIR, filename)
        if not os.path.exists(filepath):
            self._set_status(f"Lỗi: Không tìm thấy '{filename}'")
            return
        self._start_play(filepath, filename)

    # ==========================================
    #  REBIND HOTKEY
    # ==========================================
    def _start_rebind(self, slot_idx):
        """Chuyển slot_idx vào chế độ chờ nhấn phím mới."""
        self._binding_slot = slot_idx
        self._hotkey_key_btns[slot_idx].config(
            bg=COLORS["warning"], fg="#1a1a2e", text=" ??? "
        )
        self._bind_status_lbl.config(
            text=f"⌨  Slot {slot_idx+1}: Nhấn phím mới... (ESC = huỷ)",
            fg=COLORS["warning"]
        )

    def _cancel_rebind(self):
        if self._binding_slot < 0:
            return
        idx = self._binding_slot
        self._binding_slot = -1
        self._hotkey_key_btns[idx].config(
            bg=COLORS["card"], fg=COLORS["accent"],
            text=f"  {self.hotkey_keys[idx].upper()}  "
        )
        self._bind_status_lbl.config(
            text="Gán bài hát + phím tắt tùy chỉnh cho mỗi slot.",
            fg=COLORS["text_dim"]
        )

    def _finish_rebind(self, slot_idx, key_name: str):
        """Hoàn tất rebind, lưu config."""
        self._binding_slot = -1
        self.hotkey_keys[slot_idx] = key_name
        self._hotkey_key_btns[slot_idx].config(
            bg=COLORS["card"], fg=COLORS["accent"],
            text=f"  {key_name.upper()}  "
        )
        self._bind_status_lbl.config(
            text=f"✓  Slot {slot_idx+1} → {key_name.upper()}",
            fg=COLORS["success"]
        )
        self._save_hotkey_config()
        self.root.after(2000, lambda: self._bind_status_lbl.config(
            text="Gán bài hát + phím tắt tùy chỉnh cho mỗi slot.",
            fg=COLORS["text_dim"]
        ))

    def _start_rebind_pause(self):
        self._binding_pause = True
        self._btn_pause_bind.config(bg=COLORS["warning"], fg="#1a1a2e", text=" ??? ")

    def _cancel_rebind_pause(self):
        if not getattr(self, "_binding_pause", False): return
        self._binding_pause = False
        self._btn_pause_bind.config(bg=COLORS["card"], fg=COLORS["warning"], text=f"  {self.pause_hotkey.upper()}  ")

    def _finish_rebind_pause(self, key_name: str):
        self._binding_pause = False
        self.pause_hotkey = key_name
        self._btn_pause_bind.config(bg=COLORS["card"], fg=COLORS["warning"], text=f"  {key_name.upper()}  ")
        self._save_hotkey_config()

    # ==========================================
    #  GLOBAL HOTKEY LISTENER
    # ==========================================
    @staticmethod
    def _key_to_name(key) -> str | None:
        """Chuyển pynput Key object thành tên string nhỏ thường."""
        try:
            # Phím ký tự thường (a, b, 1, 2...)
            return key.char.lower() if key.char else None
        except AttributeError:
            pass
        try:
            # Phím đặc biệt (f1, esc, space...)
            return key.name.lower()
        except AttributeError:
            return None

    def _on_press_global(self, key):
        try:
            key_name = self._key_to_name(key)
            if key_name is None:
                return

            # --- Đang trong chế độ bind ---
            if self._binding_slot >= 0:
                if key_name == "esc":
                    self.root.after(0, self._cancel_rebind)
                else:
                    idx = self._binding_slot
                    self.root.after(0, lambda n=key_name, i=idx: self._finish_rebind(i, n))
                return   # Không xử lý nút này như hotkey

            # --- Đang trong chế độ bind nút PAUSE ---
            if getattr(self, "_binding_pause", False):
                if key_name == "esc":
                    self.root.after(0, self._cancel_rebind_pause)
                else:
                    self.root.after(0, lambda n=key_name: self._finish_rebind_pause(n))
                return

            # --- Phím dừng cố định (ESC, F10) ---
            if key_name in ("esc", "f10"):
                self._stop_playback()
                return
                
            # --- Phím Tạm dừng/Tiếp tục ---
            if key_name == self.pause_hotkey:
                self._toggle_pause()
                return

            # --- Kiểm tra từng slot ---
            for i, bound_key in enumerate(self.hotkey_keys):
                if key_name == bound_key:
                    self.root.after(0, lambda idx=i: self._play_hotkey_slot(idx))
                    return
        except Exception:
            pass

    def _start_global_listener(self):
        listener = pynput_keyboard.Listener(on_press=self._on_press_global)
        listener.daemon = True
        listener.start()

    # ==========================================
    #  LƯU / TẢI HOTKEY CONFIG
    # ==========================================
    def _save_hotkey_config(self):
        """Lưu toàn bộ cấu hình ra file JSON."""
        try:
            data = {
                "keys":   self.hotkey_keys,
                "songs":  self.hotkey_slots,
                "layout": self.player.current_layout,
                "alpha":  self._alpha,
                "pause_hotkey": getattr(self, "pause_hotkey", "f9"),
            }
            with open(HOTKEY_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_hotkey_config(self):
        """Tải cấu hình cũ khi khởi động."""
        self.pause_hotkey = "f9"  # Giá trị mặc định
        if not os.path.exists(HOTKEY_CONFIG_FILE):
            return
        try:
            with open(HOTKEY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Phím hotkey
            keys  = data.get("keys",  DEFAULT_HOTKEYS)
            songs = data.get("songs", [None] * NUM_HOTKEY_SLOTS)
            self.hotkey_keys  = (keys  + list(DEFAULT_HOTKEYS))[:NUM_HOTKEY_SLOTS]
            self.hotkey_slots = (songs + [None] * NUM_HOTKEY_SLOTS)[:NUM_HOTKEY_SLOTS]
            self.pause_hotkey = data.get("pause_hotkey", "f9")

            # Bộ phím nhạc cụ (old/new)
            layout = data.get("layout", "old")
            if layout in MacroPlayer.KEY_LAYOUTS:
                self.player.set_key_layout(layout)
                # _layout_var chưa tạo lúc này, đặt cờ để _build_tab_settings dùng
                self._saved_layout = layout
            else:
                self._saved_layout = "old"

            # Độ trong suốt
            alpha = data.get("alpha", 0.95)
            self._alpha = float(alpha)
        except Exception:
            self.pause_hotkey = "f9"
            pass

    # ==========================================
    #  CÀI ĐẶT
    # ==========================================
    def _change_layout(self):
        self.player.set_key_layout(self._layout_var.get())
        self._set_status(f"Đã đổi sang: {self.player.get_layout_name()}")
        self._save_hotkey_config()

    # ==========================================
    #  ĐÓNG
    # ==========================================
    def _on_close(self):
        self._stop_playback()
        self.root.destroy()
        sys.exit(0)


# ==========================================
#  ENTRY POINT
# ==========================================
def main():
    root = tk.Tk()
    root.withdraw()
    app = MacroGUI(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
