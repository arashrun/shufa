# 行楷忆写

一个无依赖的本地汉字行楷练习工具。它会从 `level-1.txt` 这类文本中依次读取汉字，先只给出待回忆的字，手动点击揭晓后才显示大号荆霄鹏 JXP 行楷。

## 启动

```bash
python3 serve.py
```

脚本会自动打开浏览器。若不想自动打开：

```bash
python3 serve.py --no-browser
```

然后访问终端中显示的本地地址。

同一用户重复运行 `serve.py` 时，后续启动会检测到已有实例并直接退出。

## 使用

- 先看页面上方的“今日汉字”，在纸上回忆并写出它的行楷形态。
- 点击“揭晓 JXP 行楷”或按空格键查看字形。
- 揭晓后按自己的情况选择“忘了”“有点模糊”或“记住了”，工具会自动进入下一字。
- 可用方向键切换汉字，右上角可切换顺序/随机学习。
- 点击“查字”或按 `Ctrl/Cmd + K` 可搜索任意汉字并直接预览 JXP 行楷；当前词表中的字还能一键定位并揭晓。
- 可点击“导入词表”或把 `.txt` 文件拖进页面。每行可只放一个汉字，也会自动从词频行中提取汉字并去重。
- 学习标记和学习位置会自动保存在浏览器本地。

## 字体

页面使用系统中已安装的 `绿木屐JXP行楷` 字体。为了确保浏览器使用正确字形，请不要在系统中卸载该字体。如果字体名称不同，可在 `styles.css` 的 `--jxp-font` 中修改。

## 创建 Linux 应用启动器

可以用 GTK3 工具快速创建并安装当前用户的 `.desktop` 文件：

```bash
python3 desktop_launcher_creator.py
```

填写应用名称和启动命令，工作目录、注释和图标文件均可选。工具会显示预览，并把启动器安装到 `~/.local/share/applications/`。未选择图标时，会在 `~/.local/share/icons/desktop-launchers/` 生成一个以内置 SVG 绘制的应用名称首字符图标。安装后，桌面环境通常会自动刷新应用菜单；若没有刷新，可重新登录或手动刷新应用缓存。
 
## 工具页架构（多页面 + 共享导航）

应用采用「首页 + 工具页」多页面架构，方便扩展任意多的单页小工具：

```
tools/<name>/        每个工具一个自包含目录（HTML + 字体 + 图片资源）
tools/<name>/tool.json   工具清单：{"title", "entry", "desc"}
```

- 构建时自动把每个工具拷到 `dist/tools/<name>/`，并向其 HTML 注入
  共享导航（`src/tools-nav.js|css`），同时生成 `dist/tools.json` 注册表
- 导航 UI：底部栏（首页 / 工具），点「工具」弹出工具箱抽屉列出全部工具
- 新增工具只需：生成 HTML 到 `tools/<name>/index.html` + 写 `tool.json`，重新构建即可
- 页面跳转用相对路径（`data-root` 处理子目录深度），file:// 与 Capacitor 均可用

现有工具：字形结构（`tools/structure/`，三词表 8103 字 IDS 网格，点击汉字
弹窗看欧体/规范楷体实时渲染与 wikichina 帖拓集字）。

## Android 应用（Capacitor 封装）

项目同时支持打包为 Android 应用，完全离线运行，不依赖电脑开机或局域网。

### 本机环境要求

- Node.js 22+
- JDK 21（Temurin）与 Android SDK（本机暂未安装时可完全依赖 CI 构建）
- 若在本机构建：`sdkmanager "platforms;android-36" "build-tools;36.0.0"` 并设置 `ANDROID_HOME`

### 签名密钥（一次性）

```bash
npm run android:keystore        # 生成 .signing/release.jks 和 Secrets 配置说明
```

按 `.signing/ci-secrets.txt` 中的说明，在 GitHub 仓库的 Settings → Secrets → Actions 中配置：

- `ANDROID_KEYSTORE_BASE64`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD`
- 可选 `APP_FONT_BASE64`：JXP 行楷字体的 Base64，用于打包离线字体（需自行确认字体授权）

覆盖安装要求前后版本使用同一密钥签名；更换密钥需要先卸载旧版（学习记录会丢失，请先导出）。

### 构建与发布

CI（`.github/workflows/release.yml`）在推送到 `main`/`master` 或 `v*` 标签时自动构建签名 APK，并发布到 GitHub Releases，文件名为 `xingkai-recall-<versionCode>.apk`，同时附 `sha256` 校验文件。也可以在电脑上手动触发：

```bash
npm run android:apk             # 构建离线资源并编译 release APK（需本机 SDK）
```

### 手机端使用

1. 从 GitHub Releases 下载并安装第一个 APK。
2. 首次启动在应用内"应用与离线设置"中填写更新仓库（owner/repository），与 Release 所在仓库一致。
3. 之后每次推送代码，CI 自动构建新版本；应用启动时自动检查更新，也可以手动点击"检查更新"。
4. 发现更新后下载（可开启自动下载），下载完成点击"安装已下载更新"，在系统安装界面确认即可；学习记录保留。
5. 如果没有打包内置字体，可在应用内点击"离线行楷字体"导入手机上的 JXP 字体文件，导入后离线可用。

### 更新包来源校验

应用只接受 `https://github.com/<配置仓库>/releases/download/` 地址（含 CDN 跳转），并逐字节计算 SHA-256 与 Release 附带的 `.sha256` 文件比对；签名一致性由 Android 系统安装器强制校验。

### 字体授权

构建时只会打包你有权分发的字体。默认字体文件被 `.gitignore` 忽略，避免把本地字体误公开发布。

### 楷书集字图爬取（scripts/fetch-calligraphy.py）

从 [wikichina 书法字典](https://tool.wikichina.com/shufa/) 批量下载历代楷书大家（欧阳询、颜真卿、柳公权、褚遂良等 11 位）的集字图，作为弹窗图片来源的补充方案：

```bash
# 从词表批量下载（默认限速 1.5s + 随机抖动，礼貌爬取）
python3 scripts/fetch-calligraphy.py --file level-1.txt --out data/calligraphy

# 同时下载 WMF 矢量图并转成 512px PNG（需 sudo apt install libwmf-bin）
python3 scripts/fetch-calligraphy.py --file level-1.txt --wmf --convert

# 只测试几个字，加 --limit；指定书家用 --authors 歐陽詢,顏真卿（繁体）
python3 scripts/fetch-calligraphy.py 明 --limit 3
```

- 楷书筛选：站点无书体参数，脚本按条目"作者"字段匹配楷书大家名单（`DEFAULT_MASTERS`）
- 输出结构：`data/calligraphy/<字>/<书家>-<序号>.jpg|.wmf|.png`，`manifest.json` 记录进度
- 断点续传：已存在的文件自动跳过，重跑安全
- JPG 预览约 74px（小）；WMF 为矢量原图，经 `wmf2gd --maxpect` 可渲染任意尺寸高清 PNG


