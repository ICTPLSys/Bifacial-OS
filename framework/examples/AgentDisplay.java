package org.bifacial.example;

import android.content.Context;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Display;
import java.io.File;
import java.lang.reflect.Method;

/** Minimal display owner adapted from the project's virtual-display experiments.
 * Run with app_process on a privileged development build. See README.md.
 * Consumes buffers without capturing screenshots; does not call a model or MCP.
 */
public final class AgentDisplay {
    public static void main(String[] args) {
        try {
            run(args);
            System.exit(0);
        } catch (Exception error) {
            error.printStackTrace();
            System.exit(1);
        }
    }

    private static void run(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException("Usage: AgentDisplay COMPONENT STOP_FILE SECONDS");
        }
        long seconds = Long.parseLong(args[2]);
        if (seconds < 1 || seconds > 86400) {
            throw new IllegalArgumentException("SECONDS must be between 1 and 86400");
        }
        File stop = new File(args[1]);
        if (!stop.isAbsolute() || stop.exists()) {
            throw new IllegalArgumentException("STOP_FILE must be an unused absolute path");
        }
        Looper.prepareMainLooper();
        Class<?> activityThread = Class.forName("android.app.ActivityThread");
        Context context = (Context) activityThread.getMethod("getSystemContext").invoke(
                activityThread.getMethod("systemMain").invoke(null));
        HandlerThread consumer = new HandlerThread("bifacial-image-consumer");
        consumer.start();
        ImageReader reader = null;
        VirtualDisplay virtualDisplay = null;
        try {
            reader = ImageReader.newInstance(1080, 1920, PixelFormat.RGBA_8888, 4);
            reader.setOnImageAvailableListener(r -> {
                try (Image image = r.acquireLatestImage()) {
                    // Drain pixel buffers to keep the normal rendering path usable.
                }
            }, new Handler(consumer.getLooper()));
            int flags = DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC
                    | DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY;
            for (String flag : new String[]{"OWN_DISPLAY_GROUP", "TRUSTED", "SUPPORTS_TOUCH",
                    "OWN_FOCUS", "STEAL_TOP_FOCUS_DISABLED"}) {
                flags |= DisplayManager.class.getField("VIRTUAL_DISPLAY_FLAG_" + flag).getInt(null);
            }
            DisplayManager manager = (DisplayManager) context.getSystemService(Context.DISPLAY_SERVICE);
            virtualDisplay = manager.createVirtualDisplay("BifacialAgentDisplay", 1080, 1920, 320,
                    reader.getSurface(), flags);
            if (virtualDisplay == null) throw new IllegalStateException("Display creation failed");
            Display display = virtualDisplay.getDisplay();
            int displayId = display.getDisplayId();
            int layerStack = (Integer) Display.class.getMethod("getLayerStack").invoke(display);
            if (displayId <= 0 || layerStack <= 0) {
                throw new IllegalStateException("Expected a non-default agent display/layer stack");
            }
            Object binder = Class.forName("android.os.ServiceManager")
                    .getMethod("getService", String.class).invoke(null, "display");
            Object service = Class.forName("android.hardware.display.IDisplayManager$Stub")
                    .getMethod("asInterface", android.os.IBinder.class).invoke(null, binder);
            Method power = service.getClass().getMethod("requestDisplayPower", int.class, int.class);
            power.invoke(service, displayId, Display.STATE_ON);
            virtualDisplay.setSurface(reader.getSurface());
            Process launch = new ProcessBuilder("am", "start", "--display", String.valueOf(displayId),
                    "-n", args[0]).redirectErrorStream(true).start();
            System.out.write(launch.getInputStream().readAllBytes());
            if (launch.waitFor() != 0) throw new IllegalStateException("am start failed");
            System.out.println("READY displayId=" + displayId + " layerStack=" + layerStack);
            System.out.flush();
            long deadline = SystemClock.elapsedRealtime() + seconds * 1000;
            while (!stop.exists() && SystemClock.elapsedRealtime() < deadline) {
                Thread.sleep(100);
            }
        } finally {
            if (virtualDisplay != null) virtualDisplay.release();
            if (reader != null) {
                reader.setOnImageAvailableListener(null, null);
                consumer.quitSafely();
                consumer.join();
                reader.close();
            } else {
                consumer.quitSafely();
            }
        }
    }
}
