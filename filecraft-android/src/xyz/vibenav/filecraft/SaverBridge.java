package xyz.vibenav.filecraft;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * 注入页面的 window.AndroidSaver。网页导出的 blob 经分块 base64 传过来，
 * 先落临时文件，结束时写入系统「下载」目录：
 * API 29+ 走 MediaStore.Downloads（无需权限），API 24-28 需要运行时存储权限，
 * 拒绝后退化到应用私有目录并提示位置。
 */
public class SaverBridge {

    static final int REQ_STORAGE = 2001;

    private final Activity activity;
    private final Map<String, Session> sessions = new HashMap<String, Session>();
    private int counter = 0;
    private Session pendingPermissionSession;

    private static class Session {
        String name;
        File temp;
        FileOutputStream out;
    }

    SaverBridge(Activity activity) {
        this.activity = activity;
    }

    @JavascriptInterface
    public String begin(String name) {
        synchronized (sessions) {
            counter++;
            String id = String.valueOf(counter);
            Session s = new Session();
            s.name = sanitize(name);
            try {
                s.temp = File.createTempFile("fcexport_", ".bin", activity.getCacheDir());
                s.out = new FileOutputStream(s.temp);
            } catch (IOException e) {
                return null;
            }
            sessions.put(id, s);
            return id;
        }
    }

    @JavascriptInterface
    public void chunk(String id, String base64) {
        Session s = sessions.get(id);
        if (s == null || base64 == null) return;
        try {
            byte[] data = android.util.Base64.decode(base64, android.util.Base64.DEFAULT);
            synchronized (s) {
                s.out.write(data);
            }
        } catch (Exception ignored) {
        }
    }

    @JavascriptInterface
    public void end(String id) {
        Session s = sessions.remove(id);
        if (s == null) return;
        try {
            s.out.close();
        } catch (IOException ignored) {
        }
        finalizeSave(s, true);
    }

    @JavascriptInterface
    public void abort(String id) {
        Session s = sessions.remove(id);
        if (s == null) return;
        try {
            s.out.close();
        } catch (IOException ignored) {
        }
        //noinspection ResultOfMethodCallIgnored
        s.temp.delete();
    }

    private void finalizeSave(Session s, boolean canAskPermission) {
        if (Build.VERSION.SDK_INT >= 29) {
            saveViaMediaStore(s);
        } else if (activity.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED) {
            saveViaFileApi(s);
        } else if (canAskPermission) {
            pendingPermissionSession = s;
            activity.requestPermissions(
                    new String[]{android.Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
        } else {
            saveViaAppDir(s);
        }
    }

    void onPermissionResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode != REQ_STORAGE || pendingPermissionSession == null) return;
        Session s = pendingPermissionSession;
        pendingPermissionSession = null;
        boolean granted = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
        if (granted) {
            saveViaFileApi(s);
        } else {
            saveViaAppDir(s);
        }
    }

    private void saveViaMediaStore(Session s) {
        try {
            ContentResolver cr = activity.getContentResolver();
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.MediaColumns.DISPLAY_NAME, s.name);
            cv.put(MediaStore.MediaColumns.MIME_TYPE, mimeFor(s.name));
            cv.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new IOException("MediaStore insert failed");
            InputStream in = new FileInputStream(s.temp);
            OutputStream out = cr.openOutputStream(uri);
            copy(in, out);
            cv.clear();
            cv.put(MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(uri, cv, null, null);
            //noinspection ResultOfMethodCallIgnored
            s.temp.delete();
            done(s.name, "下载");
        } catch (Exception e) {
            saveViaAppDir(s);
        }
    }

    @SuppressWarnings("deprecation")
    private void saveViaFileApi(Session s) {
        try {
            File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
            File target = uniqueIn(dir, s.name);
            copy(new FileInputStream(s.temp), new FileOutputStream(target));
            //noinspection ResultOfMethodCallIgnored
            s.temp.delete();
            MediaScannerConnection.scanFile(activity,
                    new String[]{target.getAbsolutePath()}, null, null);
            done(target.getName(), "下载");
        } catch (Exception e) {
            saveViaAppDir(s);
        }
    }

    private void saveViaAppDir(Session s) {
        try {
            File dir = activity.getExternalFilesDir(null);
            if (dir == null) dir = activity.getFilesDir();
            File target = uniqueIn(dir, s.name);
            copy(new FileInputStream(s.temp), new FileOutputStream(target));
            //noinspection ResultOfMethodCallIgnored
            s.temp.delete();
            done(target.getName(), target.getAbsolutePath());
        } catch (Exception e) {
            toast("保存失败");
        }
    }

    private void done(final String name, final String where) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Toast.makeText(activity, "已保存：" + name + "（" + where + "）",
                        Toast.LENGTH_LONG).show();
            }
        });
    }

    private void toast(final String msg) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Toast.makeText(activity, msg, Toast.LENGTH_SHORT).show();
            }
        });
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[65536];
        try {
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        } finally {
            try {
                in.close();
            } catch (IOException ignored) {
            }
            try {
                out.close();
            } catch (IOException ignored) {
            }
        }
    }

    private static File uniqueIn(File dir, String name) {
        File f = new File(dir, name);
        if (!f.exists()) return f;
        String base = name, ext = "";
        int dot = name.lastIndexOf('.');
        if (dot >= 0) {
            base = name.substring(0, dot);
            ext = name.substring(dot);
        }
        for (int i = 1; i < 1000; i++) {
            f = new File(dir, base + " (" + i + ")" + ext);
            if (!f.exists()) return f;
        }
        return new File(dir, System.currentTimeMillis() + "_" + name);
    }

    private static String sanitize(String name) {
        if (name == null) return "filecraft-export";
        String n = name.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        if (n.isEmpty() || n.equals("_")) n = "filecraft-export";
        return n;
    }

    private static String mimeFor(String name) {
        int dot = name.lastIndexOf('.');
        String ext = (dot >= 0 && dot < name.length() - 1)
                ? name.substring(dot + 1).toLowerCase() : "";
        if (ext.equals("pdf")) return "application/pdf";
        if (ext.equals("md")) return "text/markdown";
        if (ext.equals("zip")) return "application/zip";
        if (ext.equals("html") || ext.equals("htm")) return "text/html";
        return "application/octet-stream";
    }
}
