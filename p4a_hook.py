"""
p4a hook script for CelSuite / Scrcpy Heartbeat.

Injects custom components into AndroidManifest.xml before APK packaging,
specifically the Quick Settings TileService (ScrcpyTileService) so it
appears in Samsung One UI / Android Quick Panel.
"""

from __future__ import annotations

import os
from pathlib import Path

TILE_SERVICE_XML = """
        <!-- Quick Settings Tile for Scrcpy Heartbeat -->
        <service android:name="henryjayz.celsuite.scrcpyheartbeat.ScrcpyTileService"
                 android:label="Scrcpy Heartbeat"
                 android:permission="android.permission.BIND_QUICK_SETTINGS_TILE"
                 android:exported="true">
            <intent-filter>
                <action android:name="android.service.quicksettings.action.QS_TILE" />
            </intent-filter>
        </service>
"""


def _patch_manifest_file(manifest_path: Path) -> None:
    """Inject ScrcpyTileService into AndroidManifest.xml if missing."""
    if not manifest_path.exists():
        return
    try:
        content = manifest_path.read_text(encoding="utf-8")
        if "ScrcpyTileService" not in content and "</application>" in content:
            print(f"[p4a_hook] Injecting ScrcpyTileService into: {manifest_path}")
            new_content = content.replace("</application>", f"{TILE_SERVICE_XML}\n    </application>")
            manifest_path.write_text(new_content, encoding="utf-8")
            print(f"[p4a_hook] Successfully injected ScrcpyTileService!")
    except Exception as exc:
        print(f"[p4a_hook] Warning: Failed to patch {manifest_path}: {exc}")


def before_apk_build(toolchain=None, *args, **kwargs) -> None:
    """Hook called before Gradle packaging."""
    targets = []
    if toolchain and hasattr(toolchain, "_dist") and hasattr(toolchain._dist, "dist_dir"):
        dist_dir = Path(toolchain._dist.dist_dir)
        targets.append(dist_dir / "src" / "main" / "AndroidManifest.xml")
        targets.append(dist_dir / "AndroidManifest.xml")

    # Also search .buildozer folder
    for path in Path(".buildozer").rglob("AndroidManifest.xml"):
        targets.append(path)

    for target in targets:
        _patch_manifest_file(target)


def after_apk_build(toolchain=None, *args, **kwargs) -> None:
    """Hook called after APK compilation."""
    before_apk_build(toolchain, *args, **kwargs)
