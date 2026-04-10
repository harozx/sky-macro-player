# 🎵 Macro Player

A powerful auto-play music macro for rhythm games like **Sky: Children of the Light** and **Heartopia**. Features a sleek transparent GUI, customizable hotkeys, and always-on-top overlay.

---

## ✨ Features

- **Transparent Overlay** — Adjustable opacity (20%–100%), doesn't block your game view
- **Mini Mode** — Collapse to a compact floating toolbar
- **Custom Hotkeys** — Assign any key to any slot (no more F-key conflicts with Steam/OBS)
- **Pause & Resume** — Instantly pause mid-song and continue from the exact position
- **Favorites Album** — Save your go-to songs for quick access
- **Auto-Save Config** — All settings (hotkeys, layout, opacity) persist between sessions
- **1-Click Setup** — Auto-installs Python & dependencies if not found

---

## 🚀 Getting Started

### Option 1: Run from Source (Recommended)

**Prerequisites:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/harozx/macro_project.git
cd macro_project

# Install dependencies
pip install -r requirements.txt

# Run
python gui.py
```

### Option 2: Use the Launcher

Double-click `start.vbs` — it auto-detects Python and installs dependencies if needed.

---

## 🎮 Usage

### Tab: Songs 📂
- Browse sheet music files from the `sheets/` folder
- Search by name with the 🔍 filter
- Click **Play** to preview, or **❤** to add to favorites

### Tab: Hotkeys ⌨️
1. Select a song in the **Songs** tab
2. Go to **Hotkeys** tab → click **Assign** on any slot
3. Click the key label (e.g. `F1`) to rebind to a custom key
4. Press `ESC` to cancel rebinding

### Tab: Settings ⚙️
- **Key Layout** — Switch between `Old (YUIOP...)` and `New (ASDFG...)` mappings
- **Opacity** — Slide to make the window transparent
- **Pause Key** — Default `F9`, click to rebind

### In-Game Controls

| Key | Action |
|---|---|
| **Slot Hotkeys** | Play assigned song |
| **F9** (or custom) | Pause / Resume |
| **F10** | Stop song completely |
| **ESC** | Emergency stop |

---

## 📁 Project Structure

```
macro_project/
├── gui.py              # Main GUI application (Tkinter)
├── macro_core.py       # Music playback engine
├── start.vbs           # Windows launcher (auto-setup)
├── setup.bat           # Auto-install Python & pynput
├── requirements.txt    # Python dependencies
├── sheets/             # Sheet music files (JSON format)
└── hotkeys.json        # Auto-generated config (gitignored)
```

## 🛠 Tech Stack

- **Python 3** — Core language
- **Tkinter** — GUI framework (built-in)
- **pynput** — Global keyboard hooks & key simulation

---

## 📄 License

This project is open source and available for personal use.
