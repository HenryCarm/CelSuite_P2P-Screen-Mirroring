package henryjayz.celsuite.scrcpyheartbeat;

import android.content.Context;
import android.hardware.DummySensorManager;
import android.util.Log;
import org.kivy.android.PythonActivity;

public class ScrcpyActivity extends PythonActivity {
    private static final String TAG = "ScrcpyActivity";
    private static DummySensorManager mDummySensor = null;

    @Override
    public Object getSystemService(String name) {
        if (Context.SENSOR_SERVICE.equals(name)) {
            Log.w(TAG, "Providing DummySensorManager on Samsung device to prevent JNI Modified UTF-8 crash");
            if (mDummySensor == null) {
                mDummySensor = new DummySensorManager();
            }
            return mDummySensor;
        }
        return super.getSystemService(name);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        try {
            super.onWindowFocusChanged(hasFocus);
        } catch (Throwable t) {
            Log.w(TAG, "Safely caught onWindowFocusChanged exception: " + t.getMessage());
        }
    }
}
