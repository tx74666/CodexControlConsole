# 手机改版接口契约

契约版本：mobile-refresh-contract/1.3；唯一更新方：Codex Console 原会话。基于 `D:/codex/ControlConsole` 的 `dcf2aebe2008b55e68e6ca70baef78350e7ce095`，追加交付的可选 UI 接线声明。HTTP / 存储协议保持原值，这是现有协议的交接，不新增服务、数据迁移、权限或发送目标。Mod 只提交变更建议；同名 worktree 文档不是同步契约。

## 当前集成边界（2026-10-07）

正式源码为 `main` / `b6cccc9bd105c986152b8a45cca4135d770aae29`，运行版本 **1.0.78**（06:27 UTC+08 只读核对）。第一阶段、宿主安全 Markdown 第二阶段、第三阶段及迟到正文窄补均已集成；准确原提交与安装后验见 `backend-handoff.md` / 6 和本文“1.0.78 最终集成边界”。早期基线与历史声明保留，不代表这些阶段仍待交付。

版本 1.2 把最新续接状态移到首页；本次 1.3 补充文末两个存量能力审计，既有字段、路由、可选 UI 回调及写入权不变。用户原文、复制、保存来源仍保持原字节；相对链接、资料图片及 reader 上下文不借用到消息。iPhone 真机、外部实时控制、Work Pro 等限制保持。后续新 UI 阶段独立交付，由原会话协调共享协议、版本及正式安装。

## 身份、来源和状态

| 字段 | 含义 / 必须保留的区别 |
|---|---|
| clientId / sessionId | 本浏览器身份和一次真实讨论身份；清空产生新 session，旧身份不能写新讨论 |
| recordId | 原电脑工作记录，消息、图片、作业和 Output 的回存目标；不根据当前页面猜目标 |
| ideaId / ideaRevision | 长期想法及其版本；讨论底稿与之后编辑分开，不覆盖冻结来源 |
| requestId | 明确操作的 UUID 幂等标识；同请求须同正文。超时保留原标识，不换 UUID 自动再派工 |
| expectedRevision / expectedIdeaRevision | 对应讨论 / 想法修订；与数据库全局 revision、目录 catalogRevision 各有用途 |
| reviewId / sourceSha256 / reviewSha256 | Work 审核及冻结内容校验，不能换内容继续用旧审核 |
| jobId / threadId / turnId | 真正作业、原执行线程、准确轮次；Agent 1 / 2 是显示名，不是控制身份 |
| attachmentIds / sha256 | 本轮明确选图及原始内容证明；未选图片不发送，上传失败不能悄悄只发文字 |
| createdAt / updatedAt / submissionTime | 实际来源时间及提交时间；与本页读取时间、连接时间分开 |
| fetchedAt / partial / coverage | 外部会话快取的来源时间和覆盖范围，不能当作实时状态 |
| requested* / actual* / terminalEventObserved | 请求选择、真实回执、准确终态分别表示；连接 / 接收 / 文本片段不能代替完成 |

`revision` 不是所有场景通用的数字：沿用宿主返回类型与现有比较，不自行把不同版本字段归一。原始状态和错误码保留在可展开详情，前端可简化名称但不能丢失含义。

## 访问和基础地址

- 电脑同源基础地址：`/api/workflow`；已配对手机：`/api/phone/workflow`。手机请求沿用 HttpOnly 配对 cookie、same-origin credentials、`X-Codex-Phone: 1`、现有 Origin / Host / 会话校验。
- 401 / 403 失效时清除私有显示并进入原配对流程，保留可安全恢复的本机草稿；不能继续显示旧私有任务或绕过认证。
- 订阅登录 / 模型刷新 / 断开、Work 权限配置仅电脑明确操作。手机 GET 状态不触发登录、刷新网络、模型推理或派工。
- 公开离线 PhoneStore 与配对电脑数据库是不同来源；复用 `phone/dialogue-local.js` 和已有明确交接 `mobile-handoff.js` / `.console-idea`，不要让普通连接暗中迁移或发送内容。

## 当前讨论、草稿、附件和长期想法

| 方法 / 路径（相对基础地址） | 用途 / 关键绑定 |
|---|---|
| GET `mobile/dialogue?clientId=…` | 当前 session、detail、eligibleAttachments、preferences、execution、resultCursor、resultStatus、clearReceipts、cancellationReceipts、revision |
| POST `mobile/dialogue/open` | requestId、clientId；可选 ideaId + expectedIdeaRevision。读取 / 恢复讨论，不发送 |
| POST `mobile/dialogue/draft` | requestId、clientId、sessionId、expectedRevision、text、attachmentIds、requestedProfile、chatTransport；订阅另带 subscription。只保存草稿 |
| POST `mobile/dialogue/save` | 同上述来源字段保存想法，保留原文字与图；不讨论、不执行 |
| POST `mobile/dialogue/send` | 同上述来源字段，新的一轮明确讨论；冻结正文、上下文、选图、通道和模型 / 档位；不授权项目修改 |
| POST `mobile/dialogue/clear` | requestId、clientId、sessionId、expectedRevision；返回新的 session / record 与准确 clearReceipt。保留长期想法、旧消息、附件和作业 |
| multipart POST `mobile/dialogue/upload` | requestId、recordId、text；text 为准确 `{clientId, sessionId, expectedRevision}` JSON，加原文件。核对字节 / 类型 / 来源，返回准确附件引用；不发送 |
| GET `mobile/ideas` / `mobile/idea` | 沿用既有项目筛选、归档、想法详情、版本和原记录 |
| POST `mobile/dialogue/remember`、`mobile/idea/update` / `archive` / `split` / `merge` | 沿用既有来源 / 修订校验，保存要点、正文 / 执行稿及来源，不自动派工 |
| POST `mobile/dialogue/cancel-pending` | requestId、clientId、sessionId、recordId、expectedRevision、dispatchId；仅取消尚未领取且服务明确 `canCancelPending=true` 的 Chat 请求，不是运行中 Work 中断 |

准确的请求允许字段在 `workflow_mobile_dialogue.py` 的各操作及 `_mobile_dialogue_write`；不要根据表格另造更宽松的 DTO。重复上传、保存、清空和发送沿用服务器持久回执；重连恢复状态，不重新执行旧操作。服务器 409 如 revision_conflict / dialogue_changed / task_source_mismatch，保留编辑并重新核对，不盲重试。

session.revision 是讨论草稿 / 来源 CAS；顶层 revision 是全局数据修订，不能互换。detail.messages 使用实际 id、role、text、createdAt、attachmentIds、options；Output 按 job.resultMessageId 关联同 record 的 assistant 消息，不以手机当前时间伪造发送时间。上传最多 4 张、每张 8 MiB、请求总量 24 MiB；uploadedAttachmentIds 只证明保存，选中和发送另行确认。未发送取消回覆 / cancellationReceipts 必须匹配原六字段及准确 job，不能按 failed 或前端点击推测成功；取消保留草稿、选图和档位。

`GET mobile/dialogue/events?clientId=…&sessionId=…&cursor=…` 是认证的 SSE 结果订阅：`dialogue.ready` / `dialogue.result` 仅包含身份、cursor、jobId、status 等变更元数据，**不直接包含回答全文**。事件后按原身份读取原记录。cursor 是内容摘要，不是连续序号；订阅先注册再读，重连补当前已提交状态。keepalive 注释只维持传输，不扫描队列、不唤醒模型、不派工。页面隐藏 / 切换 / 失效时关闭旧订阅，迟到结果回旧 record。

## 订阅 Chat 和档位

`GET subscription/status` 返回 cached connected、connectionId、catalogRevision、models、profileMappings、busy、error 等；模型选择冻结 `provider: chatgpt_subscription`、connectionId、catalogRevision、modelSlug。显式档位还冻结 requestedProfile 与 reasoning；旧四字段选择保持原语义，不能自动补入新授权。

| 选择 | Chat 请求 reasoning | Work 请求 effort |
|---|---|---|
| fast / 极速 | mode=standard，effort=low | low |
| high / 高 | mode=standard，effort=high | high |
| pro / Pro | mode=pro，effort=high，须当前目录支持 | 不支持；codex_work_pro_unsupported |

目录可用和请求映射不等于真实推理能力。Chat 完成要求准确 `response.completed`、completed 终态、非空完成文字、正确模型 / 来源 / 请求；显式档位还需实际 reasoning 匹配。收到片段、HTTP 200 或读取目录不能提前标完成。不得静默换通道、模型、档位或新会话。

## Console 自有 Work

复用 `codex-work-panel.js` 及 `workflow_codex_work_service.py`；普通输入框不新造执行入口。选择 Work / 模型 / 工作区不执行，review 也不执行。

| 方法 / 路径 | 现有合同 |
|---|---|
| GET `codex-work/config` | 工作区授权、配置修订、控制器 / setup / 模型目录；状态读取不推理 |
| POST `codex-work/review` | 准确字段：requestId、recordId、expectedRevision、text、attachmentIds、workspaceId、workspaceAuthorizationSha256、requestedProfile、subscription；手机额外 clientId、sessionId。冻结真实来源、工作区、范围、上下文和选图 |
| POST `codex-work/submit` | **准确** `{requestId, reviewId, sourceSha256, confirmed:true}`；持久提交后仅通知这条新任务，不扫描旧队列。返回 recordId、job、duplicate、revision |
| GET `codex-work/runs` | 电脑 recordId；手机准确 recordId + clientId + sessionId；仅返回本来源可见 runs 和 scope |
| POST `codex-work/cancel` | 准确 requestId、jobId、threadId、turnId、sourceSha256；手机额外 clientId、sessionId。冻结准确中断意图；不能按 Agent 名、最新任务或当前页面猜身份 |

public job 保留 status、createdAt、updatedAt、requestId、recordId、workspace、mobileDialogue、subscription、requestedProfile、result、resultMessageId 和 codexWork。codexWork 公开准确 thread / turn、progress、plan、requested / actual 模型和 effort、terminalEventObserved、terminalStatus、executionVerified、reportOnly、cancellationVerified、sendIntentRecorded、cancelRequested、retryAllowed=false 等现有字段。

| 原状态 | 可显示名称 / 事实限制 |
|---|---|
| starting | 启动中；提交不等于模型已接收 |
| running | 执行中；仅依据准确事件和活动时间 |
| cancelling | 正在取消；不能提前称已取消 |
| completed | 终态已完成；仍按 reportOnly / executionVerified 区分报告与实改 |
| interrupted | 已中断；取消成功还核对 cancellationVerified |
| failed | 本轮失败；保留错误、原稿及已经发生的成果 |
| needs_review | 送达 / 状态待核对；不重发、不重跑、不显示还在确定执行 |

取消保留原文件改动和记录，不回滚。重启中的 starting / running / cancelling 转 needs_review，不重播。相同或重叠 allowedRoot 被服务拒绝并行；新 UI 可以展示多个实际任务，不自行启动多个任务填界面。

当前路线仅提供 Console 自有受限文件工具，不能承诺 shell / 编译；Workspace 路径校验不等于独立 OS 沙箱证明。运行中补充指令 / steer / 下一轮排队、暂停 / 恢复、用户审批回覆尚无本次已验证的 Console 接口；在原任务继续查看 / 讨论与向正在运行的 turn 注入指令分开显示。新接口由原会话研究协调，Mod 不以新普通 Chat 代替原任务控制。

## 电脑已有外部会话

- GET `conversations`：projects、threads、fetchedAt、partial、requests、revision；可带 revision 返回 unchanged。
- GET `conversations/thread?id=…`：原 thread、消息快取、覆盖 / 截断 / 页游标 / 抓取时间 / 读取请求。消息保留 role、phase、状态、turnId、来源消息 ID 和来源时间。
- POST `conversations/request`：原 requestId / threadId / mode（refresh / older）及既有游标校验，只建立读取请求。pending / completed / failed 是读取状态，不是任务执行状态。
- App Tools 写回快取和读取结果属于既有电脑桥接；手机 GET 只读已保存数据。Console 的侧栏入口、本助手可调用的 App Tools、缓存目录里有线程，均不能证明产品桥接已常驻或已取得控制权限。
- `fetchedAt` 缺失显示尚未抓取；旧活动状态显示“上次进行中 / 待更新”。当前组件以 5 分钟判断过期；重新 GET 快取不改变来源更新时间。手机断线、电脑离线、数据过期和任务失败分别表示。
- “使用这个会话”仅选择原目标；真正发送仍另行明确确认、核对原来源能力和准确目标。无法实时续聊 / 中断的来源只能准确展示现有快取 / 原会话入口，不暗中开新线程。

## 组件接线、测试与变更

Mod 第一阶段新增的 UI 接线只为可选 `options.getConnectionStatus()` → `{text, connected}` 和实例 `setConnectionStatus(text, connected)`，来自宿主原连接回执，无后端字段变更。状态未知时隐藏或明确未知；不得显示为任务运行状态。

第二阶段可选纯本地 `options.renderMessage(text, container)` 只排版 assistant 显示；复制、存为想法、附件来源和实际提交继续使用原消息文字 / 身份。两个宿主复用自己的 DOM Markdown 解析器，不注入原始 HTML，不借文档路径 / 目录 / 图片库解析消息，渲染失败完整回退原文。接口仅扩展 UI 选项，没有新增后端字段、权限、依赖或版本；以交付提交和相应 UI 回归核对。

侧栏复用现有模块导航：当前讨论、想法、电脑会话、Work 进度及更多。打开侧栏不读取其他私人记录、不发送、不取消、不聚焦输入；关闭恢复阅读位置。纯视图切换不换讨论身份，清空走现有身份操作。附件、IME / 中文选词、语音听写、本机草稿、认证失效和页代际隔离均保留。

优先采用临时数据 / 假传输 / 静态白名单 fixture；`--no-browser` 不证明完整实例已隔离。隔离和版本 / 写入权规则见 backend-handoff.md。回归必须区分源码检查、模拟协议、浏览器手机视口、真实模型、真实 iPhone。遇到契约缺口先交原会话协调，继续不冲突的 UI 工作；不得编造成功、权限、进度百分比、剩余时间或模型思考内容。

## 1.0.78 最终集成边界

最终 source b6cccc9bd105c986152b8a45cca4135d770aae29，前三阶段及迟到正文窄补已按提交集成；版本与缓存仅由原会话统一。具体想法快捷入口只列出当前已加载范围内最多六条真实想法，打开侧栏不发读取；点击仍只读原 ID 的详情，不执行、不自动开讨论。旧详情控件在新身份正文核对前清除，未保存草稿及阅读位置保留。

原生 response.json、adapter 回执、调用方微任务及延迟滚动继续核对 generation/active/实际讨论来源；清空或切出后的迟到读取不能回填正文、想法列表或连接徽章。已确认保存的 POST 回执不因为 inactive 一概丢弃。此轮无后端字段、权限、存储或依赖变化，订阅/Work/外部会话能力保持上述证据口径。

项目检查、Pages/Windows 发行、正式安装和资料保留的分层证据及时间点追加在 backend-handoff.md，实际私有证据目录 work/mobile-refresh-20261007。界面发行不新增模型或 iPhone 真机验收。

## 保存修订与旧正文：存量能力审计（2026-10-07）

审计基于主目录 b6cccc9 的源码及已有测试源码，未读取正式数据库、用户历史或凭据，未运行应用、模型、测试或进行中的任务。下面说明实际存储及现有读取能力，不承诺本机私人库里某份历史材料一定存在。

**完整保存版本历史尚未接入。** `ideas` 对每个 ID 只保存当前 title/body/revision，普通编辑原位 UPDATE；revision 用于并发核对，不是每个版本都可读取的承诺。metadata 的要点、执行稿也原位替换；provenance 记录来源、版本及操作时间，不包含完整旧正文。联机 requests 仅保存 fingerprint 和操作响应身份，不能从 hash 恢复正文。

| 保存或来源 | 实际保留范围 | 现有读取限制 |
|---|---|---|
| 当前长期想法 | 当前正文、要点、执行稿、附件引用、provenance | GET `mobile/ideas` 仅支持 search/projectId/archived；GET `mobile/idea?id=…` 只返回当前 idea/detail/provenance，没有旧 revision 参数 |
| sourceTask / 原消息 | `_source_task` 返回当前 `{ideaId,revision,title,body}`；已提交 job 的冻结 sourceTask 及真实已存消息能保留特定旧底稿 | GET `record?id=…` 顶层 sourceTask 是当前稿；job.sourceTask 如有则属于对应已提交轮次，不保证每种 job 都公开该字段。普通保存/编辑不都写 messages，不能由消息还原所有修订 |
| 拆分 / 合并 | 内部 `mobile-idea-op-source:<新想法ID>` 留完整源 body/metadata、来源 revision/record；仅明确选中图片有独立副本与源/目的 ID、sha256/size/mimeType | 内部快照只有写入，没有 GET 暴露；未选图不能视为已独立冻结的完整旧附件集合 |
| 手机包导入 | `mobile-import:<clientId>:<ideaId>:revision:<来源版本>:snapshot` 留完整导入 manifest、附件 ID、图证明及目标 revision；字节存于独立 UUID 文件 | 这是实际导入过的版本子集，没有历史 GET；POST import-status 需原请求和冻结 manifest，返回原导入身份/hash及当前 idea/detail，不返回旧快照 |
| 孵化器 / Chat / Work 派发 | 保存已派发的 snapshot；普通派发保存 title/body/stage/priority/revision，其他路线另留已选图/来源及部分上下文 | 只能称派发底稿，不覆盖未派发编辑、不代表每次保存的完整附件和执行稿快照 |

`GET app-work-review?recordId=…&ideaId=…&revision=…` 只允许准确当前版本，旧版本返回冲突；不能作为旧版读取接口。附件 GET 按 ID 读现存文件/预览，没有想法 revision 参数，普通读取也不自动核对旧版本 hash。

公开离线 PhoneStore 与联机库分开：某些 mobile 幂等 receipts 的完整 response 确实留有旧 idea 正文/metadata/attachmentIds；图片 Blob 仍在共享 media 中，不随每个修订独立冻结。准备过的 handoffs[ideaId][revision] 会留冻结 manifestText 和 imageIds，交接时核对共享 Blob；旧 phone incubator 路径的 receipts 只留 signature/ideaId。底层 store get/all/keys 可读原始对象，但没有专用的修订枚举、历史 adapter GET 或 UI；这些子集不能合称完整保存历史。

UI 继续使用准确当前想法详情及已有来源入口。旧底稿只能标为其真实来源（已提交轮次、导入、消息），不能从 provenance 拼造旧正文，不能把旧附件 ID 冒充完整冻结字节。完整“列版本 → 读旧版 → 从旧版继续整理”需要后端另行定义保存覆盖、附件证明和只读接口，本轮未新增或授予该能力。

源码证据：workflow_service.py:120/584/1641（存储与编辑）；workflow_mobile_dialogue.py:854/925/943/990/1003/1075/1136/1154；workflow_native_work.py:201/244；workflow_mobile_handoff.py:275/340/394/430；phone/dialogue-local.js:40/143/248/272/316、phone/store.js:58、phone/app.js:134。已有拆分/导入/派发冻结测试只覆盖上述子集，本次未重跑或提升为真机验收。

## 任务目录：存量能力审计（2026-10-07）

**工作记录和分项作业读取已经存在；统一的全局任务状态目录尚未接入。** 下列 GET 在电脑 `/api/workflow/` 和已配对手机 `/api/phone/workflow/` 共用路由；公开离线页/plan-sync 授权不能据此访问 workflow。

| GET 路径 | 准确参数与返回 | 范围及缺口 |
|---|---|---|
| `records` | limit 默认30、1–50；before 为原 record ID；revision 可返回 unchanged。返回 records/hasMore/revision，每条为 id/title/projectId/createdAt/updatedAt/context/附件摘要 | 当前 Console 库的记录列表，无 job/status/sessionId/lastActivity/stale；按创建时间降序，不按最近作业活动。before 使用 created_at 严格小于，同时间跨页不能保证覆盖完整；无状态/项目/搜索过滤 |
| `record?id=…` | record/sourceTask/messages/attachments/jobs/revision | 指定记录完整详情及其全部真实 jobs，无分页；含正文/结果/日志，不能作为仅元数据目录或在打开侧栏时批量遍历 |
| `codex-work/runs` | 电脑 recordId；手机精确 recordId/clientId/sessionId。返回 recordId/runs/revision，手机另有 scope | 仅本 record 的 codex_agent；手机校验当前 session、来源及版本并过滤不符作业。getScope 是当前讨论身份，不是全局目录或历史任务控制授权 |
| `mobile/dialogue?clientId=…` | 当前 session/detail、cursor/resultStatus 等 | 无全局 session 目录；resultStatus 取本 session 最近 Chat job，不能当全部 Work 统一状态 |
| `incubator/dispatches` | 不接受 query；dispatches/revision，含 snapshot/result/error/目标及时间；部分有 recordId/jobId | 实际全局派发列表，非全部 jobs，非仅元数据，无分页；不覆盖仅存 jobs 的 codex_agent Work，dispatch 状态不能代替 job 状态 |
| `conversations` / `conversations/thread?id=…` | 现有外部会话快取、fetchedAt/coverage/partial及读取请求 | 外部来源，与 Console record/job/session 分开；不是实时执行状态、续聊或控制接口 |

手机业务 GET 在 LAN、允许 Host、同源、enabled 及配对 cookie/session 校验之后调用，并在返回前重新校验。records/record/conversations 没有额外的 per-record/client/session 过滤，访问范围为现有配对设备的 Console 数据库边界，不能称按 Workspace 授权过滤的目录。Work 查看/取消另有严格当前讨论和 source 版本边界；阅读历史详情不产生当前 session，也不能从 job 字段制造可取消 scope。

状态必须落在实际 job/dispatch 上，不能猜一个 record 总状态：

- job.needs_review，或 Chat/旧 native Work 的 job.waiting 且 appDispatch.needs_review，显示需核对。
- codex_agent 的 starting/running/cancelling 分别保留准备、运行、等待取消回执；App pending/claimed/waiting 是接收/送达/待回答阶段，不能单凭它们断言真实 Workspace 在执行。
- codex_agent 完成为 completed；普通/Chat job 为 succeeded，有 App dispatch 时另核对其 completed。Work 终态仍按 reportOnly/executionVerified 区分报告与文件实改。
- failed 与 interrupted 分开；旧 native Work 的 failed + appDispatch.completed + result.resolvedByUser=true 表示用户结束这一轮，不是执行成功。无 job 的记录不猜已完成。

公共 job 有 createdAt/updatedAt，没有 server lastActivity/stale。record.updatedAt 随消息写入更新，Work 进度仅更新 job，不能当全任务最近活动；内部 lastObservedAt 未暴露。外部会话五分钟过期仅是 conversations UI 对 fetchedAt 的判断，不移植成 Work 停滞/失败规则。重新读取时间与来源活动时间分别表示，不能通过重新 GET 把旧状态改成实时。

此阶段侧栏继续复用宿主已加载的有限想法及当前 getScope/runs；完整记录和派发来源可从既有明确入口查看。打开侧栏不全库抓正文、不创建读取请求、不派工。conversations 原组件在空缓存时可能 POST conversations/request；新只读目录不能把该副作用当 GET，不能用本助手跨聊能力证明产品桥接成立。

全局“需核对/运行/失败/完成”列表仍缺统一的元数据投影、来源覆盖、分页/状态过滤、作业活动时间及失效含义；本轮只记录缺口，不新增队列、监控、路由或授权。未来共享字段/协议由原会话唯一协调，Mod 在明确接口和 UI 接线边界后接入。外部 steer、暂停/恢复、审批和实时续聊维持未接入。

源码证据：workflow_http.py:68/77/91/99/112/116；workflow_service.py:349/359/409/438/481/1142/1656；workflow_codex_work_service.py:258/272/301/480/633/848；phone_companion.py:157/258/304；mobile-dialogue.js:910、codex-work-panel.js:40/70、conversations-panel.js:84/116、workflow-panel.js:132。普通 `_db()` 仍执行初始化语句，GET 是业务读取而非严格 SQLite mode=ro 保证；本轮只审源码，未触碰正式库或在途任务。
