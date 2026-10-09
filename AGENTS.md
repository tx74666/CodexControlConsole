# Console 桌面管理入口：固定產品規則

用戶於 2026-10-10 明確要求永久遵守：

- 電腦端全域標頭、全域更多選單及 Console 以外的模組，不得新增 Update、版本更新捷徑或齒輪設定入口。舊三個入口 `consoleDeveloperModeTop`、`consoleDeveloperSettingsTop`、`consoleUpdateTop` 必須從 DOM 移除，不可用隱藏、版本狀態、語言或 edition 條件恢復。
- 安裝更新、開發者更新及其設定只從 Console 標籤頁（`data-module-panel="workspace"`）進入。保留 Console 內的功能和資料；不要把管理入口搬回 Music、Wallpaper、工具列或全域更多選單。
- 新增管理入口時加上 `data-console-management`，沿用 `enforceDesktopConsoleControls`。保留語言、主題、模組導覽及收納入口；本規則針對上述更新／設定捷徑。
- 修改桌面 UI 或發布時必須通過 `node tools/check-console-header-controls.mjs`。正式打包後再以 `--app-dir` 檢查實際安裝資源；禁止跳過這項檢查發布帶有舊入口的套件。測試需覆蓋所有桌面 HTML、共用模組路由、動態插入、Console 內外歸屬及頁面恢復。
- 修改完成後依上層 AGENTS.md 自主校驗、更新本機正式安裝，保留原安裝身分、任務、音樂、分類和草稿。發布成功不等於本機已更新。
