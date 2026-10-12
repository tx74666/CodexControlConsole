# Console 桌面管理入口：固定產品規則

用戶於 2026-10-10 明確要求永久遵守：

- 電腦端全域標頭、全域更多選單及 Console 以外的模組，不得新增 Update、版本更新捷徑或齒輪設定入口。舊三個入口 `consoleDeveloperModeTop`、`consoleDeveloperSettingsTop`、`consoleUpdateTop` 必須從 DOM 移除，不可用隱藏、版本狀態、語言或 edition 條件恢復。
- 安裝更新、開發者更新及其設定只從 Console 標籤頁（`data-module-panel="workspace"`）進入。保留 Console 內的功能和資料；不要把管理入口搬回 Music、Wallpaper、工具列或全域更多選單。
- 新增管理入口時加上 `data-console-management`，沿用 `enforceDesktopConsoleControls`。保留語言、主題、模組導覽及收納入口；本規則針對上述更新／設定捷徑。
- 修改桌面 UI 或發布時必須通過 `node tools/check-console-header-controls.mjs`。正式打包後再以 `--app-dir` 檢查實際安裝資源；禁止跳過這項檢查發布帶有舊入口的套件。測試需覆蓋所有桌面 HTML、共用模組路由、動態插入、Console 內外歸屬及頁面恢復。
- 修改完成後依上層 AGENTS.md 自主校驗、更新本機正式安裝，保留原安裝身分、任務、音樂、分類和草稿。發布成功不等於本機已更新。

## 歌詞來源與句界編輯（用戶 2026-10-12 要求）

- 歌詞同步先查本機已有、仍與實際錄音版本匹配的 LRC／字幕及來源紀錄。沒有合適資料時，優先找同版本的同步 LRC（例如 LRCLIB）或同一官方影片的字幕，再評估需要局部語音對齊的片段；不例行重算已滿意的整首歌曲。
- 保存來源 URL／ID、原始資料 hash、實際音訊版本和時間基準。時長接近只能篩選候選；片頭裁剪、字幕偏移須有證據，已對應剪輯版本的時間不可再次減去片頭。
- 保留用戶原文、換行、重複副歌次序、翻譯對應、既有人工點與詞／聲學資料。LRC 原有行起點與下一行推導的換句點，不能當成已測得的唱聲終點；時間軸需區分起點、句末及其来源。
- Music 的句界編輯以已有點位和可放大的時間軸為主，預設約 10 秒視窗。拖點先預覽，支持撤回／取消，Save 才保存拖動修正；不把顯示已有 LRC 點當成新增人工校準。保留 Insert 句末打點即時應用、推進下一句及整行同步高亮。
- 日常界面保持簡潔，精確時間输入、删除等低頻操作按需展開。保存失敗、切歌／語言與重載保留對應草稿；遲到回覆不能覆蓋別曲，保存只能提交本次改動且核對原時間，不能捎帶未确认的其他詞點。
- 已驗證來源示例：My Ordinary Life 實際使用 LRCLIB `https://lrclib.net/api/get/37329108` 的時間軸，映射原有 57 行文字，再以同官方 MV `9Zj0JOHJR-s` 字幕核對；來源及套用證據位於 `D:/Codex/Artifacts/my-ordinary-life-lyrics-20261011/lyrics-install-proof.json`。這不代表全歌已實聽或逐詞確認。
- 詳細版本／偏移核對沿用 `C:/Users/Randy/.codex/skills/console-lyrics-timing/references/line-sources.md`。格式核對、模型分析、播放顯示與實際聽驗分開記錄，不能由靜音或合成測試宣稱唱聲已準確對齊。
