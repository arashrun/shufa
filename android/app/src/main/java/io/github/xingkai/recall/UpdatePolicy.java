package io.github.xingkai.recall;

import java.net.URI;
import java.util.Locale;

/** Guards every network target used by the in-app updater. */
final class UpdatePolicy {
    private static final String[] ALLOWED_HOSTS = {
        "github.com", "api.github.com", "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    };

    private UpdatePolicy() {}

    static String repository(String value) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("更新仓库格式应为 owner/repository");
        }
        return value;
    }

    /** Only HTTPS Release download URLs of the configured repository are accepted. */
    static URI asset(String value, String repository) {
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("无效的更新地址");
        }
        if (!"https".equals(uri.getScheme())
            || uri.getUserInfo() != null
            || (uri.getPort() != -1 && uri.getPort() != 443)
            || uri.getRawQuery() != null
            || uri.getRawFragment() != null
            || uri.getRawPath() == null
            || !uri.getRawPath().startsWith("/" + repository(repository) + "/releases/download/")
            || uri.getRawPath().contains("%")
            || !uri.normalize().equals(uri)) {
            throw new IllegalArgumentException("更新资源必须来自所配置 GitHub 仓库的 Release");
        }
        return uri;
    }

    /** Redirect targets may move between allowlisted GitHub hosts. */
    static void assertAllowed(URI uri) {
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        boolean hostAllowed = false;
        for (String allowed : ALLOWED_HOSTS) {
            if (host.equals(allowed)) {
                hostAllowed = true;
                break;
            }
        }
        if (!"https".equals(uri.getScheme()) || !hostAllowed || uri.getUserInfo() != null) {
            throw new IllegalArgumentException("更新下载仅允许 GitHub 官方地址");
        }
    }

    static String checksum(String text) {
        if (text == null) throw new IllegalArgumentException("SHA-256 校验文件为空");
        String[] parts = text.trim().split("\\s+", 2);
        String hash = parts[0].toLowerCase(Locale.ROOT);
        if (!hash.matches("[a-f0-9]{64}")) {
            throw new IllegalArgumentException("SHA-256 校验文件格式错误");
        }
        return hash;
    }
}
