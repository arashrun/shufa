package io.github.xingkai.recall;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/**
 * 应用内更新：检查 GitHub Release、下载 APK、校验 SHA-256，并调用系统安装器。
 *
 * 更新包与已安装应用的签名一致性由 Android 系统安装器强制校验：使用不同密钥
 * 签名的更新包会被系统拒绝覆盖安装，因此这里不需要解析 APK 签名块。
 */
@CapacitorPlugin(name = "AppUpdater")
public class AppUpdaterPlugin extends Plugin {
    private static final String APK_PREFIX = "xingkai-recall-";
    private static final int CONNECT_TIMEOUT = 15000;
    private static final int READ_TIMEOUT = 30000;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile boolean cancelled = false;

    // ---- Plugin API ---------------------------------------------------------

    @PluginMethod
    public void getInfo(PluginCall call) {
        Context context = bridge.getContext();
        JSObject data = new JSObject();
        try {
            PackageInfo info = context.getPackageManager()
                .getPackageInfo(context.getPackageName(), 0);
            long versionCode = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? info.getLongVersionCode()
                : info.versionCode;
            data.put("versionCode", versionCode);
            data.put("versionName", info.versionName == null ? "" : info.versionName);
        } catch (PackageManager.NameNotFoundException e) {
            call.reject("无法读取当前应用信息");
            return;
        }
        call.resolve(data);
    }

    @PluginMethod
    public void getPendingUpdate(PluginCall call) {
        File pending = pendingApk();
        JSObject data = new JSObject();
        data.put("available", pending != null);
        if (pending != null) {
            data.put("versionCode", parseVersionCode(pending.getName()));
            data.put("size", pending.length());
        }
        call.resolve(data);
    }

    @PluginMethod
    public void fetchRelease(PluginCall call) {
        String repository = call.getString("repository", "");
        executor.execute(() -> {
            try {
                URL url = new URL("https://api.github.com/repos/"
                    + UpdatePolicy.repository(repository) + "/releases/latest");
                HttpURLConnection connection = openFollowing(url);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                int status = connection.getResponseCode();
                String body = readBody(connection, status);
                if (status == 404) {
                    rejectOnUi(call, "更新仓库中还没有发布任何版本");
                    return;
                }
                if (status != 200) {
                    rejectOnUi(call, "GitHub 接口返回 " + status);
                    return;
                }
                // Validate that this JSON is a usable release object before returning it.
                new JSONObject(body);
                resolveOnUi(call, new JSObject().put("release", body));
            } catch (Exception e) {
                rejectOnUi(call, userMessage(e));
            }
        });
    }

    @PluginMethod
    public void downloadUpdate(PluginCall call) {
        String repository = call.getString("repository", "");
        String url = call.getString("url", "");
        String checksumUrl = call.getString("checksumUrl", "");
        int versionCode = call.getInt("versionCode", 0);
        if (versionCode <= 0) {
            call.reject("更新版本号无效");
            return;
        }
        cancelled = false;
        executor.execute(() -> {
            File dir = new File(bridge.getContext().getCacheDir(), "updates");
            File apk = new File(dir, APK_PREFIX + versionCode + ".apk");
            File temp = new File(dir, apk.getName() + ".part");
            try {
                UpdatePolicy.asset(url, repository);
                UpdatePolicy.asset(checksumUrl, repository);
                if (!dir.exists() && !dir.mkdirs()) throw new IOException("无法创建更新缓存目录");

                // 1. Fetch the expected checksum published next to the APK.
                String expected = UpdatePolicy.checksum(readAll(new URL(checksumUrl)));

                // 2. Stream the APK to a .part file while hashing it.
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                // GitHub Release 下载会 302 跳转到 CDN，必须跟随重定向
                HttpURLConnection connection = openFollowing(new URL(url));
                long total = connection.getContentLengthLong();
                long read = 0;
                int lastPercent = -1;
                byte[] buffer = new byte[65536];
                try (InputStream in = connection.getInputStream();
                     FileOutputStream out = new FileOutputStream(temp)) {
                    int n;
                    while ((n = in.read(buffer)) != -1) {
                        if (cancelled) throw new IOException("下载已取消");
                        digest.update(buffer, 0, n);
                        out.write(buffer, 0, n);
                        read += n;
                        if (total > 0) {
                            int percent = (int) (read * 100 / total);
                            if (percent != lastPercent) {
                                lastPercent = percent;
                                emitProgress(percent);
                            }
                        }
                    }
                } finally {
                    connection.disconnect();
                }

                // 3. Verify the hash, then publish the file under its final name.
                String actual = hex(digest.digest());
                if (!actual.equals(expected)) {
                    temp.delete();
                    throw new IOException("SHA-256 校验失败，已丢弃下载内容"
                        + "（下载 " + (read / 1024) + " KB，期望 "
                        + expected.substring(0, 8) + "…，实际 "
                        + actual.substring(0, 8) + "…）");
                }
                if (apk.exists() && !apk.delete()) throw new IOException("无法替换旧的更新文件");
                if (!temp.renameTo(apk)) throw new IOException("无法保存更新文件");
                clearOtherPending(apk);
                JSObject data = new JSObject();
                data.put("saved", true);
                data.put("path", apk.getAbsolutePath());
                data.put("size", apk.length());
                resolveOnUi(call, data);
            } catch (Exception e) {
                temp.delete();
                rejectOnUi(call, userMessage(e));
            }
        });
    }

    @PluginMethod
    public void cancelDownload(PluginCall call) {
        cancelled = true;
        call.resolve();
    }

    @PluginMethod
    public void installUpdate(PluginCall call) {
        Activity activity = bridge.getActivity();
        Context context = bridge.getContext();
        File apk = pendingApk();
        if (apk == null) {
            call.reject("没有已下载并通过校验的更新");
            return;
        }
        // Android 8+ requires the user to allow installs from this app once;
        // older versions install unknown sources without this permission.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            && !context.getPackageManager().canRequestPackageInstalls()) {
            try {
                activity.startActivity(new Intent(
                    android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + context.getPackageName())));
            } catch (ActivityNotFoundException e) {
                call.reject("请在系统设置中允许此应用安装未知来源应用");
                return;
            }
            call.resolve(new JSObject().put("permissionRequired", true));
            return;
        }
        try {
            Uri uri = FileProvider.getUriForFile(context,
                context.getPackageName() + ".fileprovider", apk);
            Intent install = new Intent(Intent.ACTION_INSTALL_PACKAGE)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(install);
            call.resolve(new JSObject().put("permissionRequired", false));
        } catch (ActivityNotFoundException e) {
            call.reject("系统未提供 APK 安装器");
        }
    }

    // ---- Helpers ------------------------------------------------------------

    private HttpURLConnection open(URL url) throws IOException {
        try {
            UpdatePolicy.assertAllowed(url.toURI());
        } catch (URISyntaxException e) {
            throw new IOException("更新地址无效", e);
        }
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(CONNECT_TIMEOUT);
        connection.setReadTimeout(READ_TIMEOUT);
        connection.setInstanceFollowRedirects(false);
        return connection;
    }

    /** Fetch a connection following redirects only within the policy allowlist. */
    private HttpURLConnection openFollowing(URL url) throws IOException {
        HttpURLConnection connection = open(url);
        int redirects = 0;
        while (true) {
            int status = connection.getResponseCode();
            if (status == HttpURLConnection.HTTP_MOVED_PERM
                || status == HttpURLConnection.HTTP_MOVED_TEMP
                || status == 307 || status == 308) {
                if (++redirects > 5) throw new IOException("重定向次数过多");
                String location = connection.getHeaderField("Location");
                if (location == null) throw new IOException("重定向缺少目标地址");
                URL previous = connection.getURL();
                connection.disconnect();
                // Revalidate each hop so CDN targets stay allowlisted.
                connection = open(new URL(previous, location));
                continue;
            }
            return connection;
        }
    }

    /** Fetch a text body, following redirects only within the policy allowlist. */
    private String readAll(URL url) throws IOException {
        HttpURLConnection connection = openFollowing(url);
        try {
            int status = connection.getResponseCode();
            return readBody(connection, status);
        } finally {
            connection.disconnect();
        }
    }

    /** Read the body of an already-opened connection (status already fetched). */
    private String readBody(HttpURLConnection connection, int status) throws IOException {
        try {
            java.io.InputStream stream = status >= 400
                ? connection.getErrorStream()
                : connection.getInputStream();
            String body;
            if (stream == null) {
                body = "";
            } else {
                // InputStream.readAllBytes() 需 API 33+，手动读取兼容低版本
                java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
                byte[] chunk = new byte[8192];
                int n;
                while ((n = stream.read(chunk)) != -1) buffer.write(chunk, 0, n);
                stream.close();
                body = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
            }
            if (status >= 400) throw new IOException("HTTP " + status);
            return body;
        } finally {
            connection.disconnect();
        }
    }

    private File pendingApk() {
        File dir = new File(bridge.getContext().getCacheDir(), "updates");
        File best = null;
        int bestCode = 0;
        File[] files = dir.listFiles();
        if (files == null) return null;
        for (File file : files) {
            String name = file.getName();
            if (!name.startsWith(APK_PREFIX) || !name.endsWith(".apk")) {
                // Remove partial downloads so they never look installable.
                if (name.endsWith(".part")) file.delete();
                continue;
            }
            int code = parseVersionCode(name);
            if (code > bestCode) {
                bestCode = code;
                best = file;
            }
        }
        return best;
    }

    private void clearOtherPending(File keep) {
        File[] files = keep.getParentFile() == null ? null : keep.getParentFile().listFiles();
        if (files == null) return;
        for (File file : files) {
            if (!file.equals(keep) && file.getName().endsWith(".apk")) file.delete();
        }
    }

    private static int parseVersionCode(String name) {
        try {
            String withoutPrefix = name.substring(APK_PREFIX.length());
            return Integer.parseInt(withoutPrefix.substring(0, withoutPrefix.indexOf(".apk")));
        } catch (Exception e) {
            return 0;
        }
    }

    private void emitProgress(int percent) {
        Activity activity = bridge.getActivity();
        if (activity == null) return;
        activity.runOnUiThread(() -> {
            JSObject data = new JSObject();
            data.put("percent", percent);
            notifyListeners("downloadProgress", data);
        });
    }

    private void resolveOnUi(PluginCall call, JSObject data) {
        bridge.getActivity().runOnUiThread(() -> call.resolve(data));
    }

    private void rejectOnUi(PluginCall call, String message) {
        bridge.getActivity().runOnUiThread(() -> call.reject(message));
    }

    private static String userMessage(Exception e) {
        String message = e.getMessage();
        return message == null || message.isBlank() ? e.getClass().getSimpleName() : message;
    }

    private static String hex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) builder.append(String.format("%02x", b));
        return builder.toString();
    }
}
