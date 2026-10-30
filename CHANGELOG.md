# Changelog

## [2610.30.0] - 2026-10-30

### Scrcpy v5.0 & v5.0.1 Integration
- **Hardware Video Decoding:** Added `--video-decoder` flag support (`auto`, `disabled`, `vaapi`, `d3d11va`, `videotoolbox`) in Mirror quick row and Settings.
- **Flex Display:** Added `--flex-display` (`-x`) support for dynamic resizing of virtual displays with the host window.
- **Window Aspect Ratio Control:** Added `--no-window-aspect-ratio-lock` toggle for freeform window resizing under SDL3.
- **Virtual Display System Decorations:** Added `--no-vd-system-decorations` flag toggle.
- **Render Fit:** Added `--render-fit` selection (`contain`, `cover`, `fill`, `square-contain`, `square-cover`, `square-fill`).
- **Camera Torch & Zoom:** Added `--camera-torch` toggle and `--camera-zoom` multiplier controls.
- **Background Color:** Added `--background-color` hex picker in Settings.
- **Diagnostic Commands:** Added `--list-cameras` button to Settings diagnostics list.
- **Audio Latency Optimization:** Reduced default `--audio-output-buffer` from 50ms to 10ms matching upstream v5.0 standard.

### Mobile App (Kivy) Complete GUI Overhaul & Polish
- **Unified Liquid Glass Engine:** Built `GlassScreen` base class giving all 7 views the authentic CelWeave wallpaper texture and responsive geometry synchronization.
- **Instant 0ms Transitions:** Replaced `FadeTransition` with `NoTransition()`, completely eliminating frame blending, lag, and ghosting artifacts.
- **Tofu Glyph Elimination:** Replaced all missing Unicode geometric symbols (`▲`/`▼`) with clean ASCII labels (`Scroll (Up)`, `Scroll (Down)`, `[..] Up`, `< Prev`, `Next >`).
- **Live Reactive & Persistent Sliders:** Dragging Liquid Glass Opacity and Wallpaper Dark Tint sliders now updates cards and canvas in real time while persisting cleanly to JSON.
- **Centered Empty States:** Implemented clean, centered visual placeholders in Downloaded Vault and WiFi File Hub when directories are empty.
- **Storage & Synchronization:** High-speed paginated file browsing, batch multi-file sending, and intact directory archive streaming to PC over TCP.
- **Version Alignment:** Fully synchronized `buildozer.spec`, `src/constants.py`, `build_nuitka.py`, and `android/main.py` to `2610.30.0` (with 32-bit safe `android.numeric_version = 26103000`).

## [2610.9.1] - 2026-10-09

### First-run scrcpy setup (for users without scrcpy)
- New `src/scrcpy_manager.py`: live asset resolution via GitHub API with
  static fallback URLs, background download with progress, archive install
  (extracts user-supplied .zip/.tar.gz, finds scrcpy+adb, wires config).
- Settings "Binary Paths" gains status line + Open Download Page, Direct
  Download, Install Downloaded Archive buttons.
- Startup check: if scrcpy is missing the app offers all three options
  instead of failing silently at connect time.

### Auto-connect + cable-first connect
- Entering the app automatically tries to connect to the phone once
  (heartbeat + discovery + subnet scan, same as One-Tap Connect).
- New "Connect First With Cable (USB)" card: replicates the classic cable
  script (disconnect, `adb tcpip 5555`, poll `wlan0` IP, wireless connect,
  launch mirror) with a Stop button. New `adb.enable_tcpip()` /
  `adb.get_wlan_ip()` helpers.
- Fixed subnet-scanner teardown race (`RuntimeError` on app exit).

### Icons: SVG everywhere, tofu gone
- New `src/resources/icons/` (30 line-style SVGs) + `src/ui/icons.py` helper.
- Emoji stripped from desktop labels/buttons/sidebar (tofu on systems
  without color-emoji fonts); sidebar tabs, hero and action buttons use real
  SVG `QIcon`s. `PySide6.QtSvg` un-excluded from Nuitka/CI and icons bundled.
- File-type badges are text (`[VID]`, `[IMG]`, ...) instead of emoji.
- Android (Kivy has no emoji font either): grid cards + buttons use plain
  ASCII labels; UI/log emoji removed.

### Control PC vs Mirror PC (unmixed)
- Old "Mirror PC" tab never showed PC video on the phone (input-only) — now
  honestly named **Control PC** and runs the input bridge without the dead
  H.264 encoder (`enable_video=False` + `bind_input_only()`; missing ffmpeg
  no longer breaks input control).
- NEW **Mirror PC** tab (`PCScreenTab` + `mirror_server.PCMirrorServer`):
  real live PC screen on the phone over TCP MJPEG (port 5563, Pillow JPEG,
  local preview, fps/quality controls, viewer status). Phone "Watch PC"
  card connects, renders frames, touch-controls the PC via input port.
- Hold-to-click fixed: phone Left/Right send DOWN on press, UP on release
  (tap = click, hold = drag/select); PC injector already handled DOWN/UP.
- Deps: `mss` + `Pillow` added to requirements and CI pip installs.

### Scrcpy docs audit (v5.0.1, every doc page)
- Central `adb.build_scrcpy_args()` merges preset + quick row + Settings
  advanced flags; only non-default values are emitted (scrcpy >= 2.0 safe).
- Settings "Scrcpy Advanced": view-only, gamepad, clipboard autosync,
  keep-active, show-touches, always-on-top, keyboard/mouse mode, record,
  push-target, window title, start-app, new display, video buffer, plus
  List-Apps/Displays/Encoders buttons logging device output.

## [269.3.1] - 2026-09-03

### Ecosystem & Rebranding
- Rebranded official suite to **CelSuite - Scrcpy Heartbeat** (`HenryJayZ.CelSuite.ScrcpyHeartbeat`)
- Created clean, unified branding with high-resolution iconography (`icon.png`, `icon.ico`)

### Windows 10/11 Native Support
- Added dedicated GitHub Actions Windows CI runner compiling both Portable (`.exe`) and Standalone (`.zip`) releases
- Suppressed all background console windows (`CREATE_NO_WINDOW`) for silent, flicker-free ADB execution
- Added automatic `--assume-yes-for-downloads` and `--windows-console-mode=disable` for Nuitka packaging

### Android Client
- Added Samsung One UI / Android Quick Settings Tile (`ScrcpyTileService`) for one-tap mirroring toggles
- Implemented `p4a.hook` build pipeline injecting `<service>` definitions directly before `</application>`
- Added bi-directional clipboard sync listener via broadcast receiver
- Added custom Mobile CelWeave wallpaper with adjustable stretch/zoom scaling

### Desktop GUI (PySide6)
- Implemented strictly-typed Qt Queued Signals (`_sig_telemetry_ready`) for cross-thread telemetry updates
- Fixed stat card hardware dashboard values (Battery, Temperature, Latency, Resolution, Model)
- Added dedicated Send Clipboard action in both Mirroring and Transfer tabs
- Cleaned and modernized GitHub Actions cloud build pipeline with Beauty Releases page

## [268.03.17] - 2026-08-03

### Architecture
- Complete restructure from flat monolith files into a proper Python package (`src/`)
- Split 669-line `main.py` into 15+ focused modules under `src/`
- Created dedicated sub-packages: `networking/`, `transfer/`, `ui/`, `ui/widgets/`
- Single source of truth for all constants, ports, and protocol identifiers
- Unified thread-safe configuration system with atomic writes and schema versioning
- Centralized logging with `RotatingFileHandler` and Qt signal bridge

### Networking
- Added connection state machine: DISCONNECTED → DISCOVERING → CONNECTING → CONNECTED → MIRRORING
- Heartbeat debouncing prevents rapid re-connection attempts
- ADB device cache (2-second TTL) reduces subprocess overhead
- Batched hardware queries: single ADB shell call instead of 4 sequential ones
- Subnet scanner uses `ThreadPoolExecutor(50)` instead of 254 raw threads
- Early termination on subnet scan when first device is found
- Graceful shutdown for all network listeners with socket cleanup

### File Transfer
- Filename sanitization prevents path traversal attacks
- Filesize validation and disk space checking before receive
- Transfer cancellation support
- Increased chunk size from 64KB to 256KB for better throughput
- Server accepts concurrent connections via ThreadPoolExecutor
- Partial file cleanup on failed transfers
- Fixed zero-division in ETA calculation

### Desktop GUI (PyQt6)
- New "Midnight Emerald" dark theme with centralized QSS stylesheet
- Custom-styled scrollbars, tooltips, menus, and progress bars
- Connection duration timer ("Connected for 2h 15m")
- Custom keycode input for sending arbitrary Android keycodes
- "Open URL on Phone" feature exposed in the GUI
- Disconnect button for intentional disconnection
- Collapsible log panel with copy/clear buttons
- Window position/size persistence across sessions
- Menu bar with keyboard shortcuts (Ctrl+Q, F5)
- Status bar with live connection state indicator
- Exit confirmation when device is connected
- Fixed PullScreen signal stacking bug (itemClicked reconnected on every refresh)

### Android App (Kivy)
- Fixed socket leak in heartbeat loop (was creating a new socket every 4 seconds)
- Fixed socket leak in discovery listener (missing cleanup on exit)
- Fixed stale `_active_transfer_screen` global reference
- Replaced all bare `except: pass` blocks with specific exception types and logging
- Added Android back button navigation handling
- Added screen slide transitions
- Improved log rotation (size-based truncation instead of line counting)

### Build System
- Removed unused `requests` dependency
- Fixed CI: removed Android-only `pyjnius` from PC build
- `compile_nuitka.py` auto-detects Python instead of hardcoded venv path
- Comprehensive `.gitignore` with proper artifact exclusions
- Phone simulator now uses argparse with `--ip`, `--port`, `--continuous` flags

### Code Quality
- Type hints on all function signatures
- Docstrings on all public classes and methods
- Eliminated 20+ bare `except: pass` blocks
- Removed global mutable state (`global _log_panel`, etc.)
- All imports at module top level (no mid-function imports except platform-specific)
- Consistent error handling with specific exception types
- Global crash handler via `sys.excepthook`
