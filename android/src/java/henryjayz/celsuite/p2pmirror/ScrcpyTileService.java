package henryjayz.celsuite.p2pmirror;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.wifi.WifiManager;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.util.Log;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

/**
 * Production Quick Settings Tile for CelSuite Screen Mirroring.
 *
 * Appears in Android / Samsung One UI Quick Panel.
 * Supports:
 * - Instant toggle while gaming without requiring Kivy UI foregrounding.
 * - Full lifecycle: onTileAdded, onTileRemoved, onStartListening, onStopListening.
 * - Persistent state across process death via SharedPreferences.
 * - Explicit broadcast IPC targeting current package.
 * - Graceful teardown of network sockets and background workers to free device RAM immediately.
 */
public class ScrcpyTileService extends TileService {
    private static final String TAG = "CelSuiteTile";
    private static final String PREFS_NAME = "celsuite_tile_prefs";
    private static final String PREF_ACTIVE = "tile_active";
    private static final String ACTION_TOGGLE = "henryjayz.celsuite.p2pmirror.TOGGLE_HEARTBEAT";

    private static volatile boolean isServiceRunning = false;
    private static Thread headlessHeartbeatThread = null;
    private static volatile boolean headlessRunning = false;

    @Override
    public void onTileAdded() {
        super.onTileAdded();
        Log.d(TAG, "Quick Settings Tile added to active panel");
        updateTileState();
    }

    @Override
    public void onTileRemoved() {
        super.onTileRemoved();
        Log.d(TAG, "Quick Settings Tile removed from active panel");
        stopHeadlessHeartbeat();
    }

    @Override
    public void onStartListening() {
        super.onStartListening();
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        isServiceRunning = prefs.getBoolean(PREF_ACTIVE, false);
        updateTileState();
    }

    @Override
    public void onStopListening() {
        super.onStopListening();
    }

    @Override
    public void onClick() {
        super.onClick();
        isServiceRunning = !isServiceRunning;
        Log.d(TAG, "Quick Settings Tile tapped! New state: " + isServiceRunning);

        // 1. Persist state
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putBoolean(PREF_ACTIVE, isServiceRunning).apply();

        // 2. Send Explicit Broadcast to active Python Kivy receiver
        Intent intent = new Intent(ACTION_TOGGLE);
        intent.setPackage(getPackageName());
        intent.putExtra("active", isServiceRunning);
        sendBroadcast(intent);

        // 3. In-Game Headless Mirroring Support
        if (isServiceRunning) {
            startHeadlessHeartbeat();
        } else {
            stopHeadlessHeartbeat();
        }

        // 4. Update UI
        updateTileState();
    }

    private void updateTileState() {
        Tile tile = getQsTile();
        if (tile != null) {
            if (isServiceRunning) {
                tile.setState(Tile.STATE_ACTIVE);
                tile.setLabel("CelSuite: ON");
                tile.setContentDescription("CelSuite Mirror Active - Tap to disconnect");
            } else {
                tile.setState(Tile.STATE_INACTIVE);
                tile.setLabel("CelSuite: OFF");
                tile.setContentDescription("CelSuite Mirror Inactive - Tap to connect");
            }
            tile.updateTile();
        }
    }

    private synchronized void startHeadlessHeartbeat() {
        if (headlessRunning) return;
        headlessRunning = true;
        headlessHeartbeatThread = new Thread(new Runnable() {
            @Override
            public void run() {
                DatagramSocket socket = null;
                try {
                    socket = new DatagramSocket();
                    socket.setBroadcast(true);
                    String phoneIp = getDeviceIpAddress();

                    Log.d(TAG, "Headless Heartbeat thread started for IP: " + phoneIp);
                    while (headlessRunning) {
                        try {
                            String msg = "HELLO_USER|" + phoneIp + "|5555";
                            byte[] data = msg.getBytes("UTF-8");
                            InetAddress bcast = InetAddress.getByName("255.255.255.255");
                            DatagramPacket packet = new DatagramPacket(data, data.length, bcast, 5556);
                            socket.send(packet);
                        } catch (Exception e) {
                            Log.d(TAG, "Headless packet error: " + e.getMessage());
                        }
                        Thread.sleep(4000);
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Headless Heartbeat exception: " + e.getMessage());
                } finally {
                    if (socket != null && !socket.isClosed()) {
                        socket.close();
                    }
                    Log.d(TAG, "Headless Heartbeat thread cleanly terminated");
                }
            }
        }, "CelSuiteHeadlessHeartbeat");
        headlessHeartbeatThread.setDaemon(true);
        headlessHeartbeatThread.start();
    }

    private synchronized void stopHeadlessHeartbeat() {
        headlessRunning = false;
        if (headlessHeartbeatThread != null) {
            headlessHeartbeatThread.interrupt();
            headlessHeartbeatThread = null;
        }
    }

    private String getDeviceIpAddress() {
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null) {
                int ip = wm.getConnectionInfo().getIpAddress();
                if (ip != 0) {
                    return String.format("%d.%d.%d.%d",
                            (ip & 0xff),
                            (ip >> 8 & 0xff),
                            (ip >> 16 & 0xff),
                            (ip >> 24 & 0xff));
                }
            }
        } catch (Exception ignored) {}
        return "127.0.0.1";
    }
}
