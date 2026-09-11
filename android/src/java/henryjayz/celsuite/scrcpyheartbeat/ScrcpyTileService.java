package henryjayz.celsuite.scrcpyheartbeat;

import android.content.Intent;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.util.Log;

public class ScrcpyTileService extends TileService {
    private static final String TAG = "ScrcpyTile";
    public static boolean isServiceRunning = false;

    @Override
    public void onStartListening() {
        super.onStartListening();
        updateTileState();
    }

    @Override
    public void onClick() {
        super.onClick();
        Log.d(TAG, "Quick Settings Tile tapped!");

        Tile tile = getQsTile();
        if (tile == null) return;

        isServiceRunning = !isServiceRunning;

        Intent intent = new Intent("henryjayz.celsuite.scrcpyheartbeat.TOGGLE_HEARTBEAT");
        intent.putExtra("active", isServiceRunning);
        sendBroadcast(intent);

        updateTileState();
    }

    private void updateTileState() {
        Tile tile = getQsTile();
        if (tile != null) {
            if (isServiceRunning) {
                tile.setState(Tile.STATE_ACTIVE);
                tile.setLabel("Scrcpy: ON");
            } else {
                tile.setState(Tile.STATE_INACTIVE);
                tile.setLabel("Scrcpy: OFF");
            }
            tile.updateTile();
        }
    }
}
