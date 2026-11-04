package org.ballistica.community;

import android.content.res.AssetManager;
import android.util.Log;
import org.libsdl.app.SDLActivity;
import java.io.*;
import java.nio.charset.StandardCharsets;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.Locale;

/** SDL owns the Surface, EGL context, native event thread and IME bridge. */
public final class CommunityActivity extends SDLActivity {
    public static String communityApiUrl() { return BuildConfig.COMMUNITY_API_URL; }
    public static String communityAllowHttp() { return BuildConfig.COMMUNITY_ALLOW_HTTP; }
    private static javax.crypto.SecretKey refreshKey() throws Exception {
        java.security.KeyStore store = java.security.KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias("community-refresh-v1")) {
            javax.crypto.KeyGenerator generator = javax.crypto.KeyGenerator.getInstance("AES", "AndroidKeyStore");
            generator.init(new android.security.keystore.KeyGenParameterSpec.Builder("community-refresh-v1",
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT | android.security.keystore.KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes("GCM").setEncryptionPaddings("NoPadding").build());
            generator.generateKey();
        }
        return (javax.crypto.SecretKey)store.getKey("community-refresh-v1", null);
    }
    public static synchronized void storeRefresh(String value) {
        try {
            android.content.SharedPreferences prefs = getContext().getSharedPreferences("community-auth", MODE_PRIVATE);
            if (value == null) {
                if (!prefs.edit().clear().commit()) throw new IOException("Cannot clear refresh token");
                return;
            }
            javax.crypto.Cipher cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, refreshKey());
            String iv = android.util.Base64.encodeToString(cipher.getIV(), android.util.Base64.NO_WRAP);
            String data = android.util.Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), android.util.Base64.NO_WRAP);
            if (!prefs.edit().putString("iv", iv).putString("data", data).commit()) throw new IOException("Cannot store refresh token");
        } catch (Exception e) { throw new IllegalStateException("Secure credential storage failed", e); }
    }
    public static synchronized String loadRefresh() {
        try {
            android.content.SharedPreferences prefs = getContext().getSharedPreferences("community-auth", MODE_PRIVATE);
            String data = prefs.getString("data", null);
            if (data == null) return null;
            javax.crypto.Cipher cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(javax.crypto.Cipher.DECRYPT_MODE, refreshKey(), new javax.crypto.spec.GCMParameterSpec(128,
                android.util.Base64.decode(prefs.getString("iv", ""), android.util.Base64.NO_WRAP)));
            return new String(cipher.doFinal(android.util.Base64.decode(data, android.util.Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) {
            storeRefresh(null);
            return null;
        }
    }
    private static native void nativeAudioFocus(boolean focused);
    private volatile boolean nativeReady;
    private volatile boolean audioFocusGranted;
    private final android.media.AudioManager.OnAudioFocusChangeListener focusListener = change -> {
        audioFocusGranted = change == android.media.AudioManager.AUDIOFOCUS_GAIN;
        if (nativeReady) nativeAudioFocus(audioFocusGranted);
    };
    @Override public void onResume() {
        super.onResume();
        getWindow().getDecorView().post(this::restoreImmersiveMode);
        setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        android.media.AudioManager audio = (android.media.AudioManager)getSystemService(AUDIO_SERVICE);
        audioFocusGranted = audio.requestAudioFocus(focusListener, android.media.AudioManager.STREAM_MUSIC,
            android.media.AudioManager.AUDIOFOCUS_GAIN) == android.media.AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
        if (nativeReady) nativeAudioFocus(audioFocusGranted);
    }
    @Override public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) restoreImmersiveMode();
    }
    private void restoreImmersiveMode() {
        // SDL also requests fullscreen; restore it when Android returns focus
        // after the IME, permission dialogs, app switching or the system shade.
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            android.view.WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.setSystemBarsBehavior(android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                controller.hide(android.view.WindowInsets.Type.systemBars());
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
                | android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | android.view.View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | android.view.View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | android.view.View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }
    @Override public void onPause() {
        if (nativeReady) nativeAudioFocus(false);
        ((android.media.AudioManager)getSystemService(AUDIO_SERVICE)).abandonAudioFocus(focusListener);
        super.onPause();
    }
    private static native void nativeConfigure(String data, String cache, String installation, boolean focused, int smallestWidthDp);
    public static String localeTag() { return Locale.getDefault().toLanguageTag(); }
    private static Paint textPaint(float scale) {
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.SUBPIXEL_TEXT_FLAG);
        paint.setColor(Color.WHITE);
        paint.setTextSize(26.0f * scale);
        return paint;
    }
    public static float[] measureText(String text) {
        Paint paint = textPaint(1.0f);
        Rect bounds = new Rect();
        paint.getTextBounds(text, 0, text.length(), bounds);
        return new float[]{bounds.left, -bounds.bottom, bounds.right, -bounds.top, paint.measureText(text)};
    }
    public static int[] lineBreaks(String text) {
        BreakIterator breaks = BreakIterator.getLineInstance(Locale.getDefault());
        breaks.setText(text);
        ArrayList<Integer> offsets = new ArrayList<>();
        for (int p = breaks.first(); p != BreakIterator.DONE; p = breaks.next()) {
            if (p > 0) offsets.add(text.substring(0, p).getBytes(StandardCharsets.UTF_8).length);
        }
        int[] result = new int[offsets.size()];
        for (int i = 0; i < result.length; i++) result[i] = offsets.get(i);
        return result;
    }
    public static int[] renderText(int width, int height, String[] strings, float[] positions, float scale) {
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint paint = textPaint(scale);
        for (int i = 0; i < strings.length; i++) canvas.drawText(strings[i], positions[i * 2], positions[i * 2 + 1], paint);
        int[] pixels = new int[width * height];
        bitmap.getPixels(pixels, 0, width, 0, 0, width, height);
        bitmap.recycle();
        return pixels;
    }
    @Override protected String[] getLibraries() { return new String[]{"SDL3", "main"}; }
    @Override protected String getMainFunction() { return "SDL_main"; }

    @Override protected String[] getArguments() {
        // SDL calls this on its engine thread, before SDL_main/Python startup.
        File game = new File(getFilesDir(), "game-23079");
        try {
            game.mkdirs();
            File marker = new File(game, ".content-version");
            String expected;
            try (InputStream in = getAssets().open("content-version.txt")) {
                expected = readText(in);
            }
            String installed = "";
            if (marker.isFile()) {
                try (InputStream in = new FileInputStream(marker)) { installed = readText(in); }
            }
            if (!expected.equals(installed)) {
                copyTree(getAssets(), "ba_data", new File(game, "ba_data"));
                copyTree(getAssets(), "pylib", new File(game, "pylib"));
                try (FileOutputStream out = new FileOutputStream(marker)) {
                    out.write(expected.getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                }
            }
            android.content.SharedPreferences preferences = getPreferences(MODE_PRIVATE);
            String installation = preferences.getString("installation-id", null);
            if (installation == null) {
                installation = java.util.UUID.randomUUID().toString();
                if (!preferences.edit().putString("installation-id", installation).commit()) {
                    throw new IOException("Cannot persist installation id");
                }
            }
            android.util.DisplayMetrics metrics = getResources().getDisplayMetrics();
            int smallestDp = getResources().getConfiguration().smallestScreenWidthDp;
            if (smallestDp <= 0) {
                smallestDp = Math.round(Math.min(metrics.widthPixels, metrics.heightPixels) / metrics.density);
            }
            Log.i("BallisticaCommunity", "Display pixels=" + metrics.widthPixels + "x" + metrics.heightPixels
                + " density=" + metrics.density + " densityDpi=" + metrics.densityDpi
                + " xdpi=" + metrics.xdpi + " ydpi=" + metrics.ydpi + " smallestWidthDp=" + smallestDp
                + " uiScale=" + (smallestDp >= 600 ? "medium" : "small"));
            nativeConfigure(game.getAbsolutePath(), getCacheDir().getAbsolutePath(), installation, audioFocusGranted, smallestDp);
            nativeReady = true;
            Log.i("BallisticaCommunity", "Starting engine 1.8.5 build 23079, offline community Plus");
            return new String[0];
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot install packaged Ballistica data", ex);
        }
    }

    private static String readText(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int n;
        while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private static void copyTree(AssetManager assets, String from, File to) throws IOException {
        String[] children = assets.list(from);
        if (children != null && children.length > 0) {
            if (!to.isDirectory() && !to.mkdirs()) throw new IOException("mkdir " + to);
            for (String child : children) copyTree(assets, from + "/" + child, new File(to, child));
        } else {
            File temporary = new File(to.getPath() + ".part");
            try (InputStream in = assets.open(from); FileOutputStream out = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536];
                int n;
                while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
            }
            if (!temporary.renameTo(to)) throw new IOException("rename " + to);
        }
    }
}
