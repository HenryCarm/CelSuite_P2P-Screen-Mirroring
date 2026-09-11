package android.hardware;

import java.util.Collections;
import java.util.List;
import android.os.Handler;

/**
 * DummySensorManager
 * Intercepts Android SensorManager requests on Samsung devices
 * to avoid Samsung's proprietary HAL Modified UTF-8 JNI crash.
 */
public class DummySensorManager extends SensorManager {

    public DummySensorManager() {
        super();
    }

    @Override
    public List<Sensor> getSensorList(int type) {
        return Collections.emptyList();
    }

    @Override
    public List<Sensor> getDynamicSensorList(int type) {
        return Collections.emptyList();
    }

    @Override
    public Sensor getDefaultSensor(int type) {
        return null;
    }

    @Override
    public Sensor getDefaultSensor(int type, boolean wakeUp) {
        return null;
    }

    @Override
    public int getSensors() {
        return 0;
    }

    @Override
    public boolean registerListener(SensorEventListener listener, Sensor sensor, int samplingPeriodUs) {
        return false;
    }

    @Override
    public boolean registerListener(SensorEventListener listener, Sensor sensor, int samplingPeriodUs, Handler handler) {
        return false;
    }

    @Override
    public boolean registerListener(SensorEventListener listener, Sensor sensor, int samplingPeriodUs, int maxReportLatencyUs) {
        return false;
    }

    @Override
    public boolean registerListener(SensorEventListener listener, Sensor sensor, int samplingPeriodUs, int maxReportLatencyUs, Handler handler) {
        return false;
    }

    @Override
    public void unregisterListener(SensorEventListener listener) {
    }

    @Override
    public void unregisterListener(SensorEventListener listener, Sensor sensor) {
    }

    @Override
    public boolean flush(SensorEventListener listener) {
        return false;
    }
}
