# 普通 Chat 事件转发准备包

这个目录是待审查的自有 Chrome Manifest V3 扩展源码，默认停用。准备代码与隔离测试不代表已安装、已启用或完成真实 ChatGPT 往返；不会继承 ChatGPT 桌面 App 的登录凭据，也不是 OpenAI 官方扩展提供的常驻调用接口。

目标链路是 Console 明确确认后提交现有 outbox，提交事件唤醒本机原生接收端，经 Chrome Native Messaging 常连端口送入扩展自己创建的普通 Chat 页面，再按实际原问题、来源与结束证据回传同一任务。没有定期队列扫描、模型 API、API key 或 Work/Cloud 替代。

## 权限与启用

当前 manifest 只申请 `nativeMessaging`、`storage` 和 `https://chatgpt.com/*`，没有读取 cookies、浏览历史、剪贴板、调试器或其他站点的权限。内容脚本仅注册消息接收器，不能凭网页正文或网页 `postMessage` 自行开始工作。它应只在原生端授予的专用 tab、匹配的 request/attempt、审核过的 DOM 契约内读取或操作。

启用前必须审查并冻结扩展包、本机接收端、指定扩展 ID allowlist、权限范围以及 DOM 自动化方式。用户须明确批准这项自有扩展读取专用 ChatGPT 页面、处理本机已确认请求的访问范围。浏览器扩展安装须在执行时确认；权限和安全设置由用户接手。本次准备不安装扩展、不注册 native host、不启动生产接收端、不修改浏览器设置、不发送生产问题。

当前只有 App 内浏览器的有界结构观察，没有经真实 Chrome 核对的生产 DOM 契约。已观察的 Instant 页面标签只表明 UI 设置，不能验证底层推理能力。不能将 IAB 或隔离测试里的页面选择器带入生产，也不能把“高”或“Pro”提示词当成实际档位。找不到请求档位、前后观测不一致或不能核对完整输入时停止并保留原请求。

## 发送与回收原则

- 同时最多处理一个现有 outbox 请求。只有真实 `userConfirmedAt` 和准确冻结 prompt 构成发送授权；草稿、保存、导入与缓存不构成授权。
- 创建自己独立的空白普通 Chat tab，核对登录、空输入、Chat 模式及实际档位；不覆盖用户已有草稿或使用旧聊天。
- 原生端在发送前持久保存唯一 send intent。扩展在唯一点击前也持久记录已尝试；失败、断线、重载与结果不明保持 `needs_review`，不自动重发。
- 只回收同一真实对话、完整冻结 prompt、实际来源消息及唯一主回答。页面新增另一用户输入、多个候选回答、缺少实际来源或结束证据时拒绝猜测。
- DOM 证据与 App Tools `read_thread` 证据要分别注明来源。DOM 未返回真实服务端 turn ID 时，不伪造 turn ID 或把 assistant message ID 冒充 turn ID。
- 后续清空讨论或编辑草稿不改变已冻结请求。回答只能回原任务与原讨论，不能插入新讨论。

## 官方接口依据与限制

Chrome 的 [Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) 支持扩展与指定 allowlist 的本机 stdio host 双向通信。`runtime.connectNative()` 建立常连端口；[MV3 生命周期](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle) 文档说明原生连接能维持 service worker 生命周期。网页端采用 [isolated-world content script](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts) 中的可见 DOM；不访问内部 React 状态、未公开 IPC 或 ChatGPT 推理接口。

OpenAI 的 [官方浏览器扩展说明](https://learn.chatgpt.com/docs/chrome-extension) 提供当前 Chat 中的浏览器控制，没有给出可由 Console 常驻调用的普通新 Chat 接口。这个自有准备包不能被描述为官方端到端支持或已接通。

Computer Use 技能禁止自动操作 ChatGPT 桌面 App UI，也不允许通过 shell、另一个 helper 或隐藏 CDP 代替受支持的 CUA GUI 操作。代码与隔离 fixture 可以准备，但实际浏览器安装、授权和验收须遵循该边界；用户尚未明确批准的自有技术不能作为现有 CUA 限制的绕过方式。

隔离验收只使用假 DOM、假 Chrome API 与临时存储，不能访问真实浏览器、生产 SQLite、已登录账号或执行外部发送。真实普通 Chat 新会话、实际三档和 iPhone 回传仍须分别验收。

## 包身份与隔离检查

固定扩展 ID 为 `ggjlmdfnbknlicnibfngaenlakeabkfk`，由 manifest 中公开 SPKI key 的 SHA-256 前 16 字节按 Chrome ID 规则派生；没有保存私钥。原生 host 名为 `com.tx74666.codex_console_chat_relay`，协议为 `console_chat_relay/v1`。运行时文件为 manifest、worker、content script、popup 的 HTML/CSS/JS 与 `lib/protocol.js`；README 与 tests 仅供审查，不需要作为运行资源。

在源码根目录运行 `node extensions/console-chat-relay/tests/check-relay.mjs`。测试验证默认关闭、只读握手、持久单次发送、断线与重载保留核对、原问题与答案准确归属、档位不降级，以及固定 ID 和最小权限。假 DOM 通过不能验证真实 Chrome 编辑器是否接受 synthetic InputEvent；这一点须在明确批准启用后的实际界面验收。
