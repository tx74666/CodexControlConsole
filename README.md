# Codex Console

A Windows control console for music, wallpaper, Blender, Unity, Steamwork, RandomRealm, and workspace tools.

## Download / 下载

Recommended: [CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe), the Windows installer with the simplest update path. Check the release's stated signing status.

Alternative: [CodexControlConsole-Windows-x64.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Windows-x64.zip). Extract the `Codex Console` folder and run `Codex Console.exe`; it does not install shortcuts.

推荐下载：[CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe)，后续更新最方便；签名状态以该版本的发布说明为准。

免安装备用：[CodexControlConsole-Windows-x64.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Windows-x64.zip)。解压 `Codex Console` 文件夹后运行 `Codex Console.exe`，不会自动创建快捷方式。

Latest release: [github.com/tx74666/CodexControlConsole/releases/latest](https://github.com/tx74666/CodexControlConsole/releases/latest)

## Install / 安装

1. Double-click `CodexControlConsole-Setup-x64.exe`.
2. Choose **简体中文** or **English**.
3. Choose the install drive and folder on the destination page.
4. Finish Setup and launch Codex Console from the desktop or Start menu.

1. 双击 `CodexControlConsole-Setup-x64.exe`。
2. 选择 **简体中文** 或 **English**。
3. 在安装位置页面选择磁盘和目录。
4. 完成安装，从桌面或开始菜单启动 Codex Console。

The installer contains the x64 application runtime. Users do not need to install Python.

## Updates

Codex Console checks the latest GitHub Releases for both Codex Console and Codex World. When an update is available, the update control downloads the verified Windows x64 Setup and opens the same bilingual installation guide. Updates are never installed silently.

### Reopening Console

Opening the launcher again focuses the existing Console app window. Rapid repeated launches share one startup gate, and a failed foreground request does not open another window. Instances identify the same data directory and installation before reusing a backend; a newer running version takes precedence. A newer launcher can ask a compatible older backend to exit normally, then bind its original port so browser settings and to-dos keep the same origin.

After a successful update, the launcher normally closes its registered old Console window and opens the new build. It never terminates the shared Edge/Chrome process. An older unregistered window is focus-only: if its ownership cannot be confirmed, replacement is blocked instead of closing it or opening a duplicate. Close that legacy Console window once and reopen the normal launcher to establish a registered window. A refused close also blocks replacement. Releases predating the version handoff must use the normal installer update.

Submitted to-dos retain their existing storage key. An unfinished to-do input is saved locally as a draft and restored when the new window opens. A page that observes a newer backend refreshes its versioned assets; this does not change report read status.

## Per-device Data

Each Windows account keeps its own settings, indexes, cookies, desktop layouts, downloaded music, and update files under:

```text
%LOCALAPPDATA%\CodexControlConsole
```

No personal desktop layout or local media is included in the source repository or release installer.

## Device Documents / 電腦與工作環境資料庫

The desktop/Start menu launcher opens **Common** with the current task board, even if the previous session used another module. Console tabs are ordered **Common → Document → Collaboration**; explicit Document links and `--document-root` still open Document. Document provides a compact device overview and reading list. A small **Library** entry opens a separate dialog with **Reading highlights** for concise, curated human summaries and **AI records** for the full technical archive. The file browser and document body stay closed on startup; opening the library starts with highlights, and the original file tree loads only when requested. Closing the dialog returns to the uncluttered overview.

The overview reads current Windows physical memory once when opened or refreshed; it does not start background monitoring. Saved hardware details and sample metrics retain their own collection time. Folder selection and sampling tools are inside the library dialog. Choose **Open folder** or paste a local folder path to browse UTF-8 Markdown, JSON and text. The selected folder persists in per-device settings; a missing folder prompts reselection without deleting its files. Document reads relative links inside the selected folder and never executes document content.

The compact device overview highlights total, used and available RAM; CPU and graphics models; graphics memory; and installed memory modules. It combines storage capacity and usage into one summary instead of listing drive letters. Current readings and saved hardware facts display their own times, and unavailable values stay unknown. Optional purchase details remain in the selected local document library and are excluded from public releases. The overview keeps these key facts together for future device comparisons without adding comparison controls.

`GET /api/documents/guide?expectedRoot=<selected-root>` reads the optional `.document-guide.json` in the selected library and returns `{root, items}`. Its version-1 schema is `{ "version": 1, "items": [{ "path": "阅读重点/设备.md", "title": "设备重点", "summary": "一句话结论", "highlights": ["需要关注的重点"] }] }`. Each entry points to an existing document inside the same library. Keep these summaries short, emphasize conclusions and actions, date historical findings, and link detailed evidence separately. Logs, raw snapshots, implementation details and acceptance records remain in the technical archive. A library without curated highlights shows an empty state; it does not substitute a long README automatically.

Use **New sample** for an on-demand Windows device snapshot. The fixed collector writes timestamped JSON under `snapshots/`, Chinese reports under `reports/`, and updates the device profile and latest/history indexes. The overview always identifies the last collection time: saved snapshots are not live monitoring. Collection is cancellable, has a 45-second deadline, prevents overlapping runs in one library, and reports unavailable metrics as unknown. **Compare** saves a report for two snapshots and flags differences in test conditions.

資料保存在你選擇的普通本機資料夾，可整個複製或搬移。採樣不會修改系統設定、清理記憶體或啟動其他工作軟體。物理記憶體、提交量、進程私有駐留及獨立／共享顯存分開顯示；不同條件的讀數下降不等於優化收益。手動入口：

```powershell
python device_library.py collect --root "D:\Your documents\電腦與工作環境" --scenario "日常開發；相同專案與工作階段"
python device_library.py status --root "D:\Your documents\電腦與工作環境"
python device_library.py compare --root "D:\Your documents\電腦與工作環境" --before "<snapshot-id>" --after "<snapshot-id>"
```

### Local reading inbox

Document groups local reports into a compact **To read / Later / Archive** tab bar below the device overview. Opening a report does not change its state. Checking **Read** moves it to Archive; unchecking returns it to To read. A small bookmark button moves a report to Later, or back to To read if it is already in Later. Later holds reports for follow-up without adding to the Document attention badge. Each category shows its own count and stays accessible when empty.

Archive offers **Clear All** with **Undo**. It removes only archived items from the visible report lists, preserving every original document and leaving To read and Later unchanged. Cleared records remain hidden in the local registry so repeated delivery of the same stable ID does not resurrect them; only the matching undo batch can restore them. The registry is saved as `.document-inbox.json` in the selected document library, so categorization survives restarts. This is separate from the Cloudflare feedback service.

Click a report title to open a focused reading window with adjustable font size, light/dark themes and an explicit **Read** checkbox. The same reading window is reused for subsequent reports. Files in the embedded browser also offer **Read in separate window**. If the browser blocks the popup, Console keeps the embedded reader available. A reader has its own window session so it can remain open after the main Console closes. Switching the selected library disables writes in an older reader and asks you to reopen the document from the main window.

点击报告标题会打开独立阅读窗口，支持调整字号、明暗模式及手动勾选已读；同一阅读窗口可继续打开其他报告。普通文件也可点击「独立窗口阅读」。字号与主题会保留，打开正文不会自动标为已读。

Local integrations can use `GET /api/documents/inbox`, `POST /api/documents/inbox/register` and `POST /api/documents/inbox/read`. Registration accepts `id`, `path`, `title`, `summary`, `source` and optional ISO `createdAt`; `path` must identify an existing UTF-8 Markdown file under the selected library's `reports/`. Reusing an ID returns its existing entry without resetting read state. The read endpoint accepts `{ "id": "stable-report-id", "read": true }`. All document endpoints are restricted to trusted requests on this PC.

Readers should send the selected absolute `expectedRoot` with `GET /api/documents/read`, `GET /api/documents/inbox`, and in the JSON body of `POST /api/documents/inbox/read`. A mismatched root returns HTTP 400 without reading or modifying the newly selected library; this argument never selects a library.

`POST /api/documents/inbox/move` accepts `{id, status, expectedRoot}` with `status` set to `inbox`, `later`, or `archive`. `POST /api/documents/inbox/archive/clear` accepts `{expectedRoot}` and returns `clearedCount` plus `undoToken`; `POST /api/documents/inbox/archive/restore` accepts `{undoToken, expectedRoot}`. All return the updated visible entries and counts. The legacy `read` fields remain compatible: Inbox and Later are unread, Archive is read. `unreadCount` includes Later for existing API clients, while `inboxCount`, `laterCount` and `archiveCount` describe the three tabs. Legacy entries without `status` are interpreted from `read` without rewriting the registry during a GET.

Common puts the task board first. **Desktop Layout** and **Built-in Resources** start collapsed below it.

A private `workspace-plan.json` in the per-device Console data directory can seed exactly four task groups. It is never included in the application bundle. The read-only `/api/workspace-plan` and `/api/workspace-plan.js` endpoints validate version 1, a revision ID, four groups with unique IDs, and globally unique task IDs. Each group has a title, optional summary and items (`id`, `text`, boolean `done`). The first personal plan replaces generic defaults after backing up the browser task list and draft. Later revisions compare the new seed with the previous cached seed and merge only seed changes into the current list: unchanged tasks retain user progress and deletions, custom tasks and their order are kept, new seed tasks are added, and retired seed tasks are removed. An invalid previous cache or saved list leaves the original state intact. Every migration backs up the list and draft before committing; eligible unfinished drafts survive revision changes. For the same revision, checkbox changes, additions, deletions and empty groups are retained. A cached valid plan keeps the four categories available if the local seed cannot load. Reset uses the personal plan when present; other installations without a personal plan retain generic defaults.

The actual desktop task list is saved separately in the per-device `workspace-plan-state.json`; the seed file remains unchanged. Trusted local `GET/POST /api/workspace-plan/state` requests use a canonical content hash to prevent an old window overwriting newer changes. Failed saves retain the browser's edits and retry; a conflict offers a small recovery action that backs up those edits before loading the saved computer plan. Mobile snapshots contain only validated actual tasks, a content hash, save time and opaque computer ID.

## Blender document references

**Blender → Document** lists references from the same selected document library. Each reference is one card with its available languages; opening it reuses the separate reader, whose language controls switch between the paired documents. These durable references have no inbox Read/Later actions and do not change existing report or archive states.

The optional, local `.document-references.json` uses `version: 1` and an `items` array. Each item has a stable `id`, a module such as `blender`, a `defaultLanguage`, and a `variants` array for `zh-CN` and/or `en`. A variant has `language`, `label`, `title`, optional `summary`, and a relative Markdown `path`. Files remain inside the existing selected root. The read-only `/api/documents/references?module=blender&expectedRoot=...` returns one entry per reference with language availability; missing or unreadable variants are shown as unavailable without rewriting their files. Invalid indices or escaping paths are rejected. The index is local data and is not bundled with the application.

Reference readers use `/reader.html?reference=<id>&lang=<language>&root=<selected-root>`, verify the selected root, then load the registered language path. Ordinary report reader URLs and their reading states remain compatible.

## Desktop Layouts

Console can save, import, and manually restore Windows desktop icon layouts. Every plan is local to the current device. Saving a plan creates a timestamped backup first.

## Feedback

Users can send a category, short description, and optional PNG/JPEG/WebP screenshot from the Console tab. Reports pass through a Cloudflare Worker; the owner's PC does not expose an inbound port. The default limit is 10 reports per installation per UTC day, with Turnstile and an additional hashed network limit.

Report text is stored in D1 and screenshots are private in R2. Raw IP addresses are not stored. The inbox token is encrypted for the current Windows account and never returned to the browser.

Deployment files are under `services/feedback-relay`. The public installer reads the Worker URL and Turnstile site key from release repository variables.

## Requirements

### iPhone offline app

The phone app is **offline first**. After its first HTTPS installation, plans, imported documents, reading states and saved songs live on the phone. The desktop top bar has no iPhone button. **Common → Built-in Resources → 手机离线资料 → 导出资料** downloads a private JSON package for importing from the phone's Files picker; it is not added to GitHub or the public app build. Offline device information is labelled with its export and sample times.

Build the public app with `python tools/build-phone-static.py --output-dir dist-phone/site --zip`. Only phone application assets and the 16 existing public music tracks and their lyrics enter this package. **Download all** saves the entire catalog sequentially and resumes missing tracks after an interruption. Songs are not all downloaded on first opening. Private music can also be imported from Files. App updates preserve local data and saved music.

The iPhone app is available at [https://tx74666.github.io/CodexControlConsole/](https://tx74666.github.io/CodexControlConsole/). Windows and iPhone releases share one version; release checks require `phone/version.json` to match `app-manifest.json`. After the Windows release passes, run the Pages workflow manually from `main` to publish the matching phone app. Open this address in iPhone Safari, choose **Add to Home Screen**, then import private data and download the existing music from the home-screen app. **Check for updates** refreshes the program online and preserves local data and saved music. No App Store / TestFlight binary is produced by the Windows build.

手机首次安装：

1. 用 iPhone Safari 打开 [安装地址](https://tx74666.github.io/CodexControlConsole/)，选 **分享 → 添加到主屏幕**，再从主屏幕图标打开。
2. 进入 **音乐 → 全部下载**，完成后即可离线播放原有音乐及歌词；下载按钮完成后收起。曲库分为 **1st / 2nd / 3rd**，沿用电脑的金色、银色、薄荷色；分类不会限制全部下载的范围，中断后可继续下载。手机音乐页只保留分类和歌曲，不提供搜索或歌曲数量。
3. 在电脑 **常用 → 内置资源 → 手机离线资料 → 导出资料**，把导出文件送到 iPhone，再在 **资料与更新 → 导入电脑资料** 导入计划、设备资料与文档。
4. 日常离线使用；联网后点 **检查程序更新**。程序更新保留手机资料与音乐，设备页显示上次导入的采样。

手机 **1.0.22** 将主屏幕图标改回白底，原云形图案从66%稍放大到画布宽度约72%，保留四周留白及180、192、512三种尺寸。联网打开、恢复前台或重新联网时自动检查程序更新；新版完整保存后自动切换，正在播放音乐、下载或保存资料时延后重开。旧版1.0.16的页面没有自动重开处理，新程序提供一次兼容重开，已保存的资料与音乐继续使用。离线时保留已保存版本；「检查程序更新」也继续可用。桌面图标不变。**1.0.20** 的离线查看模式和 **1.0.19** 精简的音乐页继续保留：任务同步入口收起，不会恢复旧的电脑连接。电脑修改不会自动更新手机资料；私人计划与设备资料仍通过「资料与更新」保存在手机，不会上传到公开 GitHub。iOS 主屏幕的既有图标可能仍显示旧图案，程序更新不保证系统立即替换它；不要为换图标删除包含离线资料的主屏幕 App。

`dist-phone/CodexConsole-iPhone-1.0.25.zip` 是用于部署的网页包，不能直接在 iPhone 上当作安装包打开。手机资料备份不包含音频，请保留音乐原文件。

### 电脑 → 手机任务同步（后续功能，当前手机版不启用）

依用户要求，1.0.20 的手机版隐藏此入口并关闭自动连接。下面保留实现记录，作为后续恢复同步时的参考；当前日常查看不需要配对或电脑开机。

1. 在电脑 **常用 → 内置资源 → 手机任务同步 → 连接设置** 开启同 Wi-Fi 入口，取得手机地址及六位配对码。电脑任务与勾选会先保存到这台电脑的实际计划文件。
2. 在手机 App 的 **任务 → 任务同步** 输入这个地址和配对码。支持浏览器会在允许本地网络访问后直接同步。
3. 如果 iPhone 提示浏览器不支持 App 内同步，点击 **打开实时计划**，在局域网页面输入配对码。这个页面在前台每五秒自动读取电脑已保存的任务与勾选，手机只查看。它不依赖 GitHub 发布计划。
4. 断网时保留最后一次计划及其保存时间。局域网页面的 **保存计划快照** 可下载仅含任务的文件；回到原离线 App 导入后，任务更新，音乐、文档及阅读状态保留。

Safari 当前未普遍启用让 HTTPS 网页直接访问 HTTP 局域网电脑的 Local Network Access 能力，所以不能保证原主屏幕 App 内直接更新。上面的同源局域网页面是兼容入口；它与原 App 使用不同的储存区，不能自动修改原 App 的离线副本。后台或锁屏时轮询暂停，回到前台立即重读。电脑需开机、保持 Console 运行，两端接入同一可信 Wi-Fi。每个用户配对自己的电脑；个人任务、配对码与会话凭证不会上传 GitHub。电脑重启、网络地址变化、配对过期或切换资料库后需重新连接。

### 文字与图片互传（电脑与手机统一 1.0.25）

电脑打开 **互传 → 连接手机**，首次开启同 Wi-Fi 入口。手机 Console 打开 **互传 → 扫码连接电脑**，扫描电脑二维码，即可完成配对并记住手机；之后点击已保存电脑的 **打开互传**。扫码只在手机本地识别，也可选择二维码图片。手填地址与六位配对码收在备用入口。

电脑通过 Bonjour/mDNS 提供固定的 `codex-….local` 名称。开启入口后，Console 重启会在已设置的物理网络恢复连接；同一网络的 IP 变化会在下一次网络检查时重新绑定，通常一分钟内。记住设备的凭据有效 90 天，电脑 **已记住的手机** 可移除设备，手机退出连接也会撤销该设备。电脑关闭入口会停止访问并取消自动开启；再次手动开启同一网络后，未撤销的设备仍可使用。切换资料库、网络或浏览器清除凭据后需要重新扫码。

网络匹配使用物理网卡、Windows 网络名称及网关；缺少这些信息时，只允许手动开启。路由器隔离设备或阻断 mDNS 时，电脑可切换 **改用 IP 入口** 二维码；这种备用地址在电脑 IP 变化后需要重新扫码。直接使用系统相机扫码可以连接；要在原手机 Console 保存电脑快捷入口，使用 App 内的扫码按钮。

两端可以输入文字、选择最多四张图片并发送，查看同一份收发记录。电脑可直接打开收到的原图，手机可查看及保存附件。发送成功后才清空输入；失败时保留文字和所选图片。原图按原始字节保存，HEIC 可以收发与下载，不保证电脑浏览器能预览。每张图片最多 12 MiB，每次请求最多 24 MiB，文字最多 20,000 字。

原图保存在当前电脑资料库的 `互传`，历史索引与预览在 `互传/.console-transfer`；未选资料库时使用应用本地数据目录。这些内容不会进入公开 GitHub、手机发布包或反馈服务。任务同步仍保持关闭。原 HTTPS 离线 App 通过打开电脑的局域网页面使用互传；两者储存区独立，手机原有文档、音乐和阅读进度继续保留。电脑须保持开机并运行 Console，首次连接仅在可信 Wi-Fi 使用。后台与锁屏期间停止收发列表轮询，回到前台再刷新。

### Optional local companion (same Wi-Fi)

The earlier limited Wi-Fi companion remains available through the local `/api/phone-companion/*` interfaces for compatibility, with a one-time pairing code and a physical LAN address. It is not the offline app and has no desktop top-bar entry. Its local HTTP page requires the computer to remain awake.

The mobile companion has **Tasks / Music / Device / Documents / Transfer** tabs: saved task groups and actual desktop progress, direct phone playback of the computer's local music library, a compact computer overview, document highlights and registered references, a focused reader, and bidirectional text/image transfer. **Read / Later / Archive** uses the existing desktop document registry. Task snapshots are read-only on the phone and refresh every five seconds in the foreground; other tabs are not sampled by the task poll.

Music loads on demand and plays through the phone's own audio output after tapping a track or Play. Search, previous/next, seeking, repeat modes, and existing local lyrics with available language variants are supported. It uses authenticated byte-range streaming from registered tracks, without downloading new songs, modifying the desktop playlist, or controlling computer speakers. Playback stops and private media is cleared on logout or a detected lost connection. Safari format support and background playback must be checked on the user's actual iPhone; no offline download is provided.

Phone access is initially off. Enabling it starts a separate limited server on the selected physical LAN IPv4 address, port **8899**, with a stable mDNS hostname where available. The explicitly configured network is remembered for later restarts and DHCP changes; other networks do not automatically open an entrance. Stopping the entrance disables automatic restoration. It serves only mobile assets and the bounded phone APIs; it does not expose desktop program controls, arbitrary files, folder selection, sampling, or the full desktop API. Pairing codes and QR invitations expire after five minutes and one successful use; temporary sessions expire after eight hours or when the entrance is closed. Remembered phones receive a 90-day HttpOnly cookie; only its hash is stored in the computer's private application data, bound to the selected library and network. QR invitations use a fragment that the phone removes before making requests. Changing the selected library requires a new pairing. Task snapshots are saved locally; personal documents are not cached for offline use. The separate cross-origin pairing token has only task-read permission and is never exported with phone backups.

This first version uses **unencrypted local HTTP** and is intended only for a trusted home Wi-Fi. Do not forward its port through the router. Windows Firewall may need the user to allow the installed Console on their trusted network. The computer must remain awake with Console running. This is a home-screen web app; no iOS App Store / TestFlight binary is produced by the Windows build.

- Windows 10 or Windows 11, 64-bit
- Microsoft Edge or Google Chrome

## Build Locally

Install Python 3.12 x64 and Inno Setup 7, install the locked Windows build dependencies, then run:

```powershell
python -m pip install --only-binary=:all: -r .\tools\windows-release-requirements.txt
.\tools\build-windows.ps1 -OutputDir dist
```

`app-manifest.json` is the single build-version source. `-Version` may be omitted; when supplied for release automation it must match the manifest exactly (an optional leading `v` is accepted).

The result is `dist\CodexControlConsole-Setup-x64.exe`. A local build is unsigned and is only for development and security testing.

## Publish A Release

The release helper retries intermittent GitHub connections, pushes `main`, creates the version tag, waits until both Windows x64 downloads are available, verifies the Setup digest, and synchronizes the publisher's local installation to the released version:

```powershell
.\tools\publish-release.ps1 -Version 1.0.6
```

Use `-CheckConnection` to verify GitHub access without uploading anything.

Publisher synchronization is what prevents the computer that performed the release from immediately advertising its own release as an update. The helper also records the exact repository, tag, commit, and local installation ID in `%LOCALAPPDATA%\CodexControlConsole\publisher-state.json`; this suppresses only that release's top-bar notification on that Windows user profile. A newer tag published elsewhere is still announced normally. Use `-SkipPublisherSync` only when intentionally publishing from a machine that must not install Codex Console.

The release workflow prefers trusted Authenticode signing whenever all Artifact Signing settings are available. When none are configured, it can still publish an explicitly labeled unsigned build after all quality, package, and Microsoft Defender checks pass. A partially configured signing identity blocks publishing. The emergency direct-publisher helper remains signed-only.

Public releases are fail-closed for quality, packaging, and malware scanning. GitHub Actions requires the requested tag version to match `app-manifest.json`, runs the shared quality checks, builds the application and Setup, creates the ZIP, and scans the main executable, native drag helper, Setup, and ZIP with Microsoft Defender. With a complete Artifact Signing configuration it also signs and verifies every packaged `exe`, `dll`, and `pyd` plus Setup. With no signing configuration it publishes an unsigned release with a clear SmartScreen warning; a partial configuration fails instead of silently downgrading.

The manual `Audit Windows x64 Setup` workflow reproduces the build and Defender scan without signing, uploading, or publishing its temporary installer. Use it to compare a candidate with an earlier release while trusted signing is being configured.

Required repository variables are `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_ACCOUNT`, and `ARTIFACT_SIGNING_PROFILE`. Required secrets are `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`. The certificate profile must use a publicly trusted signing identity; self-signed and test profiles are not release identities.

## Checks

The same lightweight, non-building check entry point is used by pull requests, pushes to `main`, and public releases:

```powershell
.\tools\check-quality.ps1
```

It covers Python syntax and core services, desktop layouts, external application launching, Blender collaboration, feedback Worker tests, and static Node syntax checks for the UI. For the full local browser regression, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check-console-ui-local.ps1` separately. That runner isolates all desktop-layout paths under a temporary directory and uses a non-destructive capture helper, so it never reads, restores, or overwrites the user's real desktop layout.

Blender > Helper > GitHub Coop lists repositories from `github-coop.json`. GitHub Desktop handles authentication, clone, commits, pull, and push.

Blender > Builder > Reference View Set accepts Front, Back, Left, Right, Top, and Bottom images for any kind of object. Temporary uploads are decoded and copied into the selected project's `References/CDesigner/<set-name>--<set-id>/images` folder. Create/Update submits configuration, replacements, and removals as one transaction; all images are validated before the versioned `reference-views.json` manifest is atomically replaced, so a failed request leaves the previous set usable. The manifest stores only POSIX paths relative to itself so the C designer Blender add-on can rebuild the set after either application restarts.

Codex Console checks the selected repository against GitHub when Blender Helper opens and whenever Refresh is pressed. A cloud card guides first-time users into Clone; a local card reports remote updates, uncommitted work, pending pushes, or a synchronized state. Before editing a `.blend`, pull the latest version and make sure nobody else is editing that same binary file. When finished, save and close Blender, then commit and push through GitHub Desktop. External textures and references must be packed into the `.blend` or intentionally included in the repository.

The release workflow requires Microsoft Artifact Signing and cannot publish an unsigned Setup. `NativeFileDrag.exe` is compiled from `NativeFileDrag.cs` during every clean application build instead of packaging the repository's precompiled helper. Self-signing is intentionally not used because it does not establish public Windows trust.
