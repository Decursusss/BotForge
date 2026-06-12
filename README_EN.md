# BotForge V0.01 (EN)
 
**A visual automation builder for games and programs — without a single line of code.**
 
You assemble a bot from ready-made blocks: "if this appears on screen, click here", "wait until a sound plays", "hold a key for 2 seconds". BotForge watches the screen, listens to audio, and performs actions according to your scenario.
 
Runs on Windows.

---

## 📋 Contents
 
- [How it works](#-how-it-works)
- [Quick start](#-quick-start)
- [Triggers](#triggers)
- [Scenario blocks](#scenario-blocks-bot-logic)
- [Project structure](#-project-structure)
- [Micro-documentation](#-micro-documentation)
---
 
## 🧠 How it works
 
The idea is simple — a bot consists of three things:
 
```
TRIGGERS (what to look for)  →  SCENARIO (blocks in order)  →  ACTIONS (what to do)
```
 
1. **Trigger** — the bot's "eye". It looks at its own region of the screen (or listens to audio) and answers one question: *did it fire or not?* For example: "a red HP bar appeared in this corner" or "the fishing-bite sound played in the game".
2. **Scenario** — a list of blocks executed top to bottom. Blocks can be simple ("do an action", "wait") or conditional ("IF trigger fired — do this", "WHILE trigger is active — repeat this", "WAIT until trigger fires").
3. **Action** — the bot's "hands": clicks, key presses, text input, drag-and-drops, pauses.
When you hit ▶, the engine starts running the scenario in a loop: it goes through all blocks in order, reaches the end, and starts over (if looping is enabled). The interface shows which step is currently running, and triggers light up when they fire.
 
**Important:** each trigger scans **only its selected screen region**, not the whole screen. This is faster and more accurate — make the region as small as possible.
 
---
 
## 🚀 Quick start
 
Requires **Python** and **Windows**.
 
```bash
# 1. Clone the repository
git clone https://github.com/Decursusss/BotForge.git
cd BotForge
 
# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate
 
# 3. Install dependencies
pip install -r requirements.txt
 
# 4. Run
python main.py
```
 
The main window opens with three panels:
 
```
┌─────────────┬──────────────────┬─────────────────────┐
│  TRIGGERS   │     SCENARIO     │  PREVIEW + SETTINGS │
│             │                  │                     │
│ list of     │ blocks top to    │ live video of region│
│ triggers    │ bottom, drag&drop│ + property editor   │
│             │                  │   of selected block │
└─────────────┴──────────────────┴─────────────────────┘
```
 
---
 
### Triggers
 
| Type | Icon | What it does | When to use |
|---|---|---|---|
| **HSV mask** | `H` | Searches for a color in a region (a range of hues). Has an eyedropper — click the preview and the color is picked automatically | HP/mana bars, colored indicators, buttons |
| **Image** | `T` | Searches for a template image on screen (template matching). The sample is cropped right inside the app | Buttons, icons, any UI elements |
| **Pixel** | `P` | Watches the color of a single pixel | The fastest method: "pixel changed color = something happened" |
| **Change** | `Δ` | Detects any motion/change in a region | "Something appeared/moved" when it doesn't matter what exactly |
| **Sound** | `S` | Listens to system audio. Two modes: match against a recorded sample, or just volume level | Fishing-bite sound, an alarm signal, any in-game sounds |
 
Each trigger has a **"Test" button** — an instant check without running the bot, with a green marker showing where it was found on the preview.
 
A sound trigger can be **recorded right in the program** (it records system audio), trimmed of silence, and played back.
 
### Scenario blocks (bot logic)
 
| Block | Icon | What it does |
|---|---|---|
| **Action** | ⚡ | Simply performs one action |
| **Wait** | ⏱ | Pause for N milliseconds |
| **IF trigger** | ❓ | Trigger fired → run a **chain of actions** (several in a row allowed) |
| **Wait for trigger** | ⏳ | Stands and waits until the trigger fires (with a timeout or indefinitely) |
| **WHILE trigger** | 🔁 | Repeats a chain of actions while the trigger is active (or the opposite — while it's NOT active; there's an inversion) |
 
Blocks can be **dragged** with the mouse, **duplicated**, and **deleted** (the ✕ button, right-click, or Del).
 
### Other
 
- ▶ **Live visualization**: highlight of the current step, an "Iteration N · Step i/k" counter, an event log
- 🖼 **Live preview** of any screen region with a color-mask overlay and find markers
- 💾 **Save/load** projects as plain JSON (old projects open — the format is backward-compatible)
- 🛑 **F12 emergency stop** from anywhere, even when the game is in focus
- 🎮 **Two input modes**: `pydirectinput` (seen by DirectInput games) and `pyautogui` (regular programs)
- 🔄 Scenario loop: infinite or N iterations, with a configurable delay
---
 
## 📁 Project structure
 
```
BotCrafter/
├── main.py                      # entry point (+ DPI-awareness for Windows)
├── requirements.txt
└── botforge/
    ├── core/                    # logic, knows nothing about the UI
    │   ├── models.py            # data: Trigger, Action, Block, BotConfig
    │   ├── engine.py            # BotEngine (QThread) — scenario execution loop
    │   ├── capture.py           # screen capture (mss)
    │   ├── vision.py            # computer vision: HSV mask, image search,
    │   │                        #   pixel, change detector (OpenCV)
    │   ├── audio.py             # audio: system audio recording (loopback),
    │   │                        #   spectrograms, comparison with a sample
    │   ├── input_backend.py     # input: pydirectinput / pyautogui + WinAPI fallback
    │   ├── recorder.py          # recording user actions (pynput)
    │   └── storage.py           # saving/loading a project as JSON
    └── ui/                      # interface (PySide6)
        ├── main_window.py       # main window, ties everything together
        ├── preview_widget.py    # live region preview + find markers
        ├── region_overlay.py    # semi-transparent overlay for region/point selection
        ├── block_list.py        # scenario block list (drag&drop, highlight)
        ├── block_editor.py      # inspector: block/trigger/action settings
        ├── trigger_list.py      # trigger cards with indicators
        └── color_picker.py      # eyedropper + HSV sliders
```
 
Core principle: `core/` is pure logic, `ui/` is interface only. The engine runs in a separate thread (QThread) and communicates with the interface only through Qt signals — that's why the window doesn't freeze while the bot is running.
 
The program stores its working files in `~/.botforge/`:
- `templates/` — cropped template images
- `sounds/` — recorded sound samples
---
 
## 📖 Micro-documentation
 
### Project format (.json)
 
A project is plain JSON; you can edit it by hand or generate it with a script:
 
```json
{
  "name": "My bot",
  "loop": true,
  "loop_delay_ms": 50,
  "max_iterations": 0,
  "triggers": [
    {
      "id": "a1b2c3d4",
      "name": "OK button",
      "type": "template",
      "region": [100, 200, 300, 150],
      "template_path": "C:/Users/.../.botforge/templates/a1b2c3d4.png",
      "template_threshold": 0.8
    }
  ],
  "blocks": [
    {
      "id": "e5f6a7b8",
      "type": "if_trigger",
      "trigger_id": "a1b2c3d4",
      "actions": [
        { "type": "click_on_trigger" },
        { "type": "wait", "ms": 500 },
        { "type": "key_press", "key": "enter" }
      ]
    }
  ]
}
```
 
A quick rundown of the fields:
 
- `region` is always `[x, y, width, height]` in **physical** screen pixels
- `max_iterations: 0` — an infinite loop; a number — stop after N passes
- the `if_trigger` and `while_trigger` blocks hold a **list** of `actions` — they run one after another
- `while_trigger` has `invert: true` ("while the trigger is NOT present"), `repeat_delay_ms` (pause between repeats), and `max_repeats` (protection against an infinite loop)
- `wait_trigger` has `wait_timeout_ms` (0 = wait indefinitely)
### Trigger types (fields)
 
| Type         | Key fields |
|--------------|---|
| `color_mask` | `hsv_lower`, `hsv_upper` — HSV range; `min_match_ratio` — what fraction of the region must be this color |
| `template`   | `template_path` — path to the image; `template_threshold` — similarity threshold 0..1 (usually 0.8) |
| `pixel`      | `pixel_x`, `pixel_y`, `pixel_rgb` — expected color; `pixel_tolerance` — tolerance |
| `change`     | `min_match_ratio` — fraction of changed pixels needed to count motion as present |
| `sound`      | `sound_path` — WAV sample; `sound_mode` — `match` (similar to the sample) or `level` (just loud); thresholds `sound_threshold` / `sound_level` |
 
### Action types
 
`click_xy`, `double_click`, `click_on_trigger`, `mouse_hold`, `drag`, `move_mouse`, `scroll`, `key_press`, `key_hold`, `text_type`, `wait`, `random_wait`, `beep`, `stop_bot`, `restart_scenario`
 
### Keys
 
In the key field you can write single keys and combinations via `+`:
 
```
enter   esc   f5   space   ctrl+s   ctrl+shift+a   win+d   alt+tab
```
 
### Hotkeys
 
| Key | Action |
|---|---|
| **F12** | Emergency stop of the bot (global, even from inside a game) |
| **Del** | Delete the selected block |
| Drag&Drop | Reorder blocks in the scenario |
 
---
 
## ⚠️ Disclaimer
 
BotForge is a general-purpose automation tool. Using bots in online games may violate the game's rules and lead to an account ban. Use at your own risk.
