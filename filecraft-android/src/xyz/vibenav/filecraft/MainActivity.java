package xyz.vibenav.filecraft;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.PorterDuff;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.net.URL;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * FileCraft 网页版的原生壳：全屏 WebView 加载已部署站点，
 * 处理手机上网页做不到的事——文件上传选择器、blob 导出落盘、断网重试、切换服务器。
 */
public class MainActivity extends Activity {

    private static final String DEFAULT_URL = "https://filecraft.vibenav.xyz/";
    private static final String PREFS = "filecraft";
    private static final String KEY_BASE_URL = "base_url";
    private static final int REQ_FILE_CHOOSER = 1001;

    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorView;
    private TextView errorMessage;
    private View fabMenu;

    private ValueCallback<Uri[]> fileCallback;
    private String injectJs;
    private SaverBridge saverBridge;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        injectJs = readRaw(R.raw.inject);
        saverBridge = new SaverBridge(this);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFFF3F4F6);

        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        configureWeb();

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.getProgressDrawable().setColorFilter(0xFF2563EB, PorterDuff.Mode.SRC_ATOP);
        root.addView(progress, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3), Gravity.TOP));

        root.addView(buildErrorView(), new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        fabMenu = buildFab();
        FrameLayout.LayoutParams fp =
                new FrameLayout.LayoutParams(dp(44), dp(44), Gravity.BOTTOM | Gravity.END);
        fp.rightMargin = dp(18);
        fp.bottomMargin = dp(24);
        root.addView(fabMenu, fp);

        setContentView(root);
        web.loadUrl(currentUrl());
    }

    private void configureWeb() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setSupportMultipleWindows(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, true);

        web.setBackgroundColor(0xFFF3F4F6);
        web.addJavascriptInterface(saverBridge, "AndroidSaver");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                String scheme = Uri.parse(url).getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                hideError();
                progress.setVisibility(View.VISIBLE);
                view.evaluateJavascript(injectJs, null);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
                view.evaluateJavascript(injectJs, null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                if (!request.isForMainFrame()) return;
                progress.setVisibility(View.GONE);
                showError(error.getDescription() + "\n\n"
                        + getString(R.string.err_server_line) + " " + currentUrl());
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                String[] mimes = mapAcceptTypes(params.getAcceptTypes());
                if (mimes.length > 0) {
                    intent.putExtra(Intent.EXTRA_MIME_TYPES, mimes);
                }
                if (params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                }
                try {
                    startActivityForResult(
                            Intent.createChooser(intent, getString(R.string.pick_file)),
                            REQ_FILE_CHOOSER);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        web.setDownloadListener(new android.webkit.DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent,
                                        String contentDisposition, String mimeType,
                                        long contentLength) {
                // 兜底：仅处理非 blob 的直链下载；blob 导出由 AndroidSaver 桥处理
                try {
                    DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                    req.setMimeType(mimeType);
                    String cookie = CookieManager.getInstance().getCookie(url);
                    if (cookie != null && !cookie.isEmpty()) req.addRequestHeader("cookie", cookie);
                    req.addRequestHeader("User-Agent", userAgent);
                    String name = URLUtil.guessFileName(url, contentDisposition, mimeType);
                    req.setTitle(name);
                    req.setNotificationVisibility(
                            DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
                    DownloadManager dm =
                            (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    dm.enqueue(req);
                    Toast.makeText(MainActivity.this,
                            getString(R.string.download_started) + name,
                            Toast.LENGTH_SHORT).show();
                } catch (Exception e) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Exception ignored) {
                    }
                }
            }
        });
    }

    /** 网页 accept 属性里的扩展名映射成 MIME，供系统文件选择器过滤 */
    private String[] mapAcceptTypes(String[] acceptTypes) {
        Map<String, String> ext = new HashMap<String, String>();
        ext.put("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        ext.put("doc", "application/msword");
        ext.put("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation");
        ext.put("ppt", "application/vnd.ms-powerpoint");
        ext.put("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        ext.put("xls", "application/vnd.ms-excel");
        ext.put("pdf", "application/pdf");
        ext.put("md", "text/markdown");
        List<String> out = new ArrayList<String>();
        if (acceptTypes != null) {
            for (String raw : acceptTypes) {
                if (raw == null) continue;
                String t = raw.trim();
                if (t.isEmpty()) continue;
                if (t.contains("/")) {
                    if (!out.contains(t)) out.add(t);
                    continue;
                }
                String e = t.startsWith(".") ? t.substring(1) : t;
                String m = ext.get(e.toLowerCase());
                if (m != null && !out.contains(m)) out.add(m);
            }
        }
        return out.toArray(new String[0]);
    }

    private View buildErrorView() {
        errorView = new LinearLayout(this);
        errorView.setOrientation(LinearLayout.VERTICAL);
        errorView.setGravity(Gravity.CENTER);
        errorView.setBackgroundColor(0xFFF3F4F6);
        errorView.setVisibility(View.GONE);
        errorView.setPadding(dp(32), dp(32), dp(32), dp(32));

        TextView title = new TextView(this);
        title.setText(R.string.err_title);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(0xFF111827);
        title.setGravity(Gravity.CENTER);

        errorMessage = new TextView(this);
        errorMessage.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        errorMessage.setTextColor(0xFF6B7280);
        errorMessage.setGravity(Gravity.CENTER);
        errorMessage.setPadding(0, dp(12), 0, dp(24));

        LinearLayout btnRow = new LinearLayout(this);
        btnRow.setOrientation(LinearLayout.HORIZONTAL);
        btnRow.setGravity(Gravity.CENTER);

        Button retry = new Button(this);
        retry.setText(R.string.err_retry);
        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                hideError();
                web.reload();
            }
        });
        btnRow.addView(retry);

        Button change = new Button(this);
        change.setText(R.string.err_change_server);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.leftMargin = dp(12);
        change.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showServerDialog();
            }
        });
        btnRow.addView(change, lp);

        errorView.addView(title);
        errorView.addView(errorMessage);
        errorView.addView(btnRow);
        return errorView;
    }

    private View buildFab() {
        TextView fab = new TextView(this);
        fab.setText("⋮");
        fab.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        fab.setTextColor(0xFFFFFFFF);
        fab.setGravity(Gravity.CENTER);
        GradientDrawable bg = new GradientDrawable();
        bg.setShape(GradientDrawable.OVAL);
        bg.setColor(0x66111827);
        fab.setBackground(bg);
        fab.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openMenu();
            }
        });
        return fab;
    }

    private void openMenu() {
        String[] items = new String[]{
                getString(R.string.menu_refresh),
                getString(R.string.menu_home),
                getString(R.string.menu_change),
                getString(R.string.menu_clear_cookies)
        };
        new AlertDialog.Builder(this)
                .setTitle(getString(R.string.menu_title_fmt, currentUrl()))
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        if (which == 0) web.reload();
                        else if (which == 1) web.loadUrl(currentUrl());
                        else if (which == 2) showServerDialog();
                        else confirmClearCookies();
                    }
                })
                .show();
    }

    private void showServerDialog() {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setSingleLine(true);
        input.setText(currentUrl());
        new AlertDialog.Builder(this)
                .setTitle(R.string.server_dialog_title)
                .setMessage(R.string.server_dialog_msg)
                .setView(input)
                .setPositiveButton(R.string.ok, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        applyBaseUrl(input.getText().toString());
                    }
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }

    private void applyBaseUrl(String raw) {
        String url = raw == null ? "" : raw.trim();
        if (url.isEmpty()) {
            toast(R.string.url_empty);
            return;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://" + url;
        try {
            new URL(url).toURI();
        } catch (Exception e) {
            toast(R.string.invalid_url);
            return;
        }
        getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit().putString(KEY_BASE_URL, url).apply();
        hideError();
        web.loadUrl(url);
    }

    private void confirmClearCookies() {
        new AlertDialog.Builder(this)
                .setMessage(R.string.clear_confirm)
                .setPositiveButton(R.string.ok, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        CookieManager.getInstance().removeAllCookies(null);
                        toast(R.string.cookies_cleared);
                        web.reload();
                    }
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }

    private void showError(CharSequence message) {
        errorMessage.setText(message);
        errorView.setVisibility(View.VISIBLE);
    }

    private void hideError() {
        errorView.setVisibility(View.GONE);
    }

    private String currentUrl() {
        return getSharedPreferences(PREFS, MODE_PRIVATE)
                .getString(KEY_BASE_URL, DEFAULT_URL);
    }

    private String readRaw(int resId) {
        try {
            java.io.InputStream in = getResources().openRawResource(resId);
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            in.close();
            return bos.toString("UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    private void toast(int resId) {
        Toast.makeText(this, resId, Toast.LENGTH_SHORT).show();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
                                           int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (saverBridge != null) saverBridge.onPermissionResult(requestCode, permissions, grantResults);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
