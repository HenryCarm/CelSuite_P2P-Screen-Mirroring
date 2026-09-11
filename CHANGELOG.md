# Changelog

## [269.11.0] - 2026-09-03

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
