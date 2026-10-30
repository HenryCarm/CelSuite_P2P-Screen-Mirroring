package henryjayz.celsuite.scrcpyheartbeat;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.util.Log;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

public class ScrcpyTileService extends TileService {
    private static final String TAG = "CelSuiteTile";
    private static final String PREFS_NAME = "celsuite_tile_prefs";
    private static final String KEY_ACTIVE = "tile_mirror_active";
    
    private static volatile boolean isServiceRunning = false;
    private static Thread headlessHeartbeatThread = null;
    private static volatile boolean heartbeatLoopRunning = false;

    @Override
    public void onTileAdded() {
        super.onTileAdded();
        Log.d(TAG, "Quick Settings Tile added to panel.");
        updateTileState();
    }

    @Override
    public void onTileRemoved() {
        super.onTileRemoved();
        Log.d(TAG, "Quick Settings Tile removed from panel.");
        stopHeadlessHeartbeat();
    }

    @Override
    public void onStartListening() {
        super.onStartListening();
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        isServiceRunning = prefs.getBoolean(KEY_ACTIVE, false);
        updateTileState();
    }

    @Override
    public void onClick() {
        super.onClick();
        Log.d(TAG, "Quick Settings Tile tapped!");

        Tile tile = getQsTile();
        if (tile == null) return;

        isServiceRunning = !isServiceRunning;

        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putBoolean(KEY_ACTIVE, isServiceRunning).apply();

        Intent intent = new Intent("henryjayz.celsuite.scrcpyheartbeat.TOGGLE_HEARTBEAT");
        intent.setPackage(getPackageName());
        intent.putExtra("active", isServiceRunning);
        sendBroadcast(intent);

        if (isServiceRunning) {
            startHeadlessHeartbeat();
        } else {
            stopHeadlessHeartbeat();
            System.gc();
        }

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

    private synchronized void startHeadlessHeartbeat() {
        if (heartbeatLoopRunning) return;
        heartbeatLoopRunning = true;

        headlessHeartbeatThread = new Thread(new Runnable() {
            @Override
            public void run() {
                DatagramSocket socket = null;
                try {
                    socket = new DatagramSocket();
                    socket.setBroadcast(true);
                    byte[] payload = "HELLO_USER|127.0.0.1|5555".getBytes("UTF-8");
                    InetAddress broadcastAddr = InetAddress.getByName("255.255.255.255");
                    DatagramPacket packet = new DatagramPacket(payload, payload.length, broadcastAddr, 5556);

                    int count = 0;
                    while (heartbeatLoopRunning && count < 60) {
                        try {
                            socket.send(packet);
                        } catch (Exception sendErr) {
                            Log.e(TAG, "Heartbeat packet error: " + sendErr.getMessage());
                        }
                        count++;
                        Thread.sleep(2500);
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Headless heartbeat socket error: " + e.getMessage());
                } finally {
                    if (socket != null && !socket.isClosed()) {
                        socket.close();
                    }
                    heartbeatLoopRunning = false;
                }
            }
        }, "CelSuite-HeadlessHeartbeat");
        headlessHeartbeatThread.setDaemon(true);
        headlessHeartbeatThread.start();
    }

    private synchronized void stopHeadlessHeartbeat() {
        heartbeatLoopRunning = false;
        if (headlessHeartbeatThread != null) {
            headlessHeartbeatThread.interrupt();
            headlessHeartbeatThread = null;
        }
    }
}
