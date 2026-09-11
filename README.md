<div align="center">

<img src="icon.webp" alt="CelSuite Logo" width="130" height="130" />

# CelSuite — Scrcpy Heartbeat

**Seamless, zero-friction wireless Android mirroring, hardware telemetry, bi-directional clipboard sync & high-speed file transfers.**

[![Release](https://img.shields.io/github/v/release/HenryCarm/CelSuite_Scrcpy-Heartbeat?style=for-the-badge&color=2ecc71)](https://github.com/HenryCarm/CelSuite_Scrcpy-Heartbeat/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Android%20%7C%20Windows%20%7C%20Linux-blue?style=for-the-badge)](#-downloads--releases)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20LGPL-success?style=for-the-badge)](https://www.qt.io/qt-for-python)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

<br/><br/>

<img src="banner.webp" alt="CelSuite Banner Logo" width="100%" style="border-radius: 14px; max-width: 820px;" />

<br/>

</div>

---

## 🌟 Overview

**CelSuite - Scrcpy Heartbeat** eliminates the hassle of cables, manual IP typing, and failed connections when using [scrcpy](https://github.com/Genymobile/scrcpy). Simply unlock your phone, tap the Quick Settings tile or let the automated UDP heartbeat link your device, and enjoy low-latency wireless screen mirroring, real-time hardware vitals, and one-tap clipboard sharing.

---

## 📦 Downloads & Releases

All desktop executables and mobile packages are built automatically in the cloud via GitHub Actions.

👉 **[Download the Latest Release (v269.11.0)](https://github.com/HenryCarm/CelSuite_Scrcpy-Heartbeat/releases/latest)**

| Platform | Download Asset | Type | Description |
| :--- | :--- | :--- | :--- |
| 📱 **Android** | `ScrcpyHeartbeat-*.apk` | Mobile Client | Quick Settings Tile, heartbeat service & clipboard bridge |
| 🪟 **Windows** | `CelSuite-Windows-Portable.exe` | Single File | Portable executable (zero install, double-click to run) |
| 🪟 **Windows** | `CelSuite-Windows-Standalone.zip` | Standalone Folder | Unzip and run `main.exe` for instant cold-boot startup |
| 🐧 **Linux** | `CelSuite-Linux-Portable.bin` | Single Binary | `chmod +x` and launch directly |
| 🐧 **Linux** | `CelSuite-Linux-Standalone.zip` | Standalone Folder | Pre-packaged folder with all native Qt libraries |

---

## ✨ Key Features

- ⚡ **Zero-Cable Wireless Mirroring:** Automatically pairs your phone and PC over WiFi/Hotspot using UDP heartbeat packets.
- 🎛️ **Quick Settings Tile:** Toggle wireless mirroring directly from your Android / Samsung One UI Quick Panel.
- 📊 **Real-Time Hardware Telemetry:** Displays live battery %, temperature, device model, resolution, and wireless latency without lag.
- 📋 **Bi-Directional Clipboard Sync:** Instant one-click clipboard transfer between Phone and PC.
- 📁 **High-Speed File Transfer:** Drag-and-drop file transfers over local TCP socket (`port 5558`) with integrity verification.
- 🪟 **Native Windows 10/11 Support:** Fully suppressed background subprocesses (`CREATE_NO_WINDOW`) — no flashing black command prompt windows!
- 🛡️ **LGPL Compliance:** Built on PySide6 (The Qt Company's official LGPL framework).

---

## 🚀 How It Works

```
Phone (Android Client)                         PC (CelSuite Desktop)
       │                                                 │
       ├──── UDP Heartbeat (Port 5556) ─────────────────>│  (Auto-Discovery)
       │                                                 │
       │<─── ADB Connect (Port 5555) ────────────────────┤  (Wireless Bridge)
       │                                                 │
       │<─── Scrcpy Video Stream ────────────────────────┤  (Ultra-Low Latency Mirroring)
       │                                                 │
       ├──── TCP File & Clipboard Transfer (Port 5558) ─>│  (Bi-Directional Sync)
```

---

## 🛠️ Quick Setup

### 📱 Android Setup:
1. Download and install `ScrcpyHeartbeat-*.apk`.
2. Enable **Wireless Debugging** in Android Developer Options.
3. *(Optional)* Add the **Scrcpy Tile** to your notification bar quick panel for instant toggling!

### 💻 PC Setup:
1. Ensure `scrcpy` and `adb` are installed on your system (or in PATH).
2. Launch `CelSuite-Windows-Portable.exe` (Windows) or `./CelSuite-Linux-Portable.bin` (Linux).
3. Connect both devices to the same WiFi network or PC Mobile Hotspot — mirroring launches automatically!

---

## 📜 Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history and release notes.

---

## 📄 License

Distributed under the MIT License.

---

<div align="center">

<img src="banner_green.webp" alt="Cel Banner" width="100%" style="border-radius: 14px; max-width: 820px;" />

</div>

