# Console Work Agent 接通与验收

本轮来源：用户 2026-10-06 明确要求研究和测试 Work；手机能查看 Agent 1／2 的进度、取消其中一个并同步电脑；保留极速／高／Pro 三个档位。沿用原 Console 工作记录与资料库。

## 已核对的现状

- 正式 Console 1.0.65 的订阅图文 Chat 已完成一次真实手机往返。Chat 回答没有本机执行工具；不能从其文字判断电脑已执行修改。
- `workflow_native_work.py` 保存审核后的执行稿、实际 Workspace、授权范围及冻结来源；外部 App Tools 执行并回填成果。它没有自动启动 Codex、进度订阅或运行中取消。
- `app-work/end` 仅结束已回收、但成果核验失败的报告；手机的 cancel-pending 仅取消尚未领取的请求。两者都不是正在执行的 Agent 中断。
- 手机对话页缺少直接的 Work 入口。入口可以通向现有审核、作业历史与 Output；新增入口本身不证明自动执行接通。

## 本机协议试验

- 本机可执行程序报告 `codex-cli 0.160.0`，由该版本实际导出稳定 JSON schema。
- 默认 daemon/proxy 客户端均未完成连接，报告 `os error 10050`。未重启既有服务，不能据此推断原因、服务归属或声称连接了当前桌面 App。
- 自有 stdio app-server 在全新隔离目录中完成 initialize/initialized 与 model/list；只使用本机模拟 Responses 服务和非账号测试标识。
- 单任务试验收到真实 CLI 的进度事件，发送精确 threadId/turnId 的 turn/interrupt 后收到 turn/completed、status=interrupted；再关闭本次 stdin，程序正常退出 0。
- 第一份试验证据：`work/chat-relay-preparation/codex-work-probe-20261006T0739591198551Z/proof.json`，SHA256 `898e2e86f3c9d25848c41cc39fa55ae9c6b5e2a4ef1050d022fed57c7d2b4fc2`。
- 两任务第一轮保留原失败记录：使用 ephemeral 线程时，thread/read(includeTurns) 返回 -32600；只证明收到进度和单个中断，不能证明另一任务继续运行。
- 新的隔离持久线程试验通过：两个任务各收到真实 CLI 的流式进度；精确中断 Agent 1 后，thread/read 证实 Agent 2 仍为 inProgress。再单独中断 Agent 2，收到 interrupted，关闭本次 stdin 后退出 0。本机模拟服务只收到两次请求，没有账号调用。
- 两任务试验证据：`work/chat-relay-preparation/codex-work-probe-20261006T0744599545526Z/proof.json`，SHA256 `b8f9c943fe9cab00baa852acc7fb0078f32c1d30cf0d10790bfd5daa90ca2757`。这是协议研究验收，不是手机实际执行验收。
- 上述试验没有调用真实模型、使用账号凭据或连接桌面既有 Agent，尚未构成手机真实 Work 或取消验收。

## 接通方案

采用 Console 自有的本机 Codex app-server 控制器。手机仍留在 Console，电脑 Console 与手机显示同一任务。已有桌面 App 线程继续作为独立能力：没有真实连接和中断接口证据时，不自动纳入可控范围。

1. 用户在同一记录选择 Work，核对本轮执行稿、选图、实际 Workspace 和允许目录，再明确发送。切换模式只选择模式，不发送或执行。
2. 数据库先冻结本轮来源并提交，提交事件只通知这条新确认任务。控制器不得在启动时扫描、领取或重发旧任务，也不用定时模型检查队列。
3. 一个 Work 作业保存确切的电脑、Workspace、jobId、threadId、turnId 与本轮来源。Agent 1／2 仅为这些真实任务的显示名称；不能按标题猜测线程或子代理关系。
4. 模型只从本账号正式目录选取，再核对当前 app-server 实际支持的 effort。使用已有 Console 订阅授权，由产品在子进程环境中提供连接，凭据不进入命令行、日志、进度或手机。
5. 只运行在明确允许目录内；子进程使用独立配置，避免继承未审核的其他项目工具。写入范围由实际 sandbox 与 Workspace 校验共同约束。两任务涉及相同文件时串行，低内存时不新增重型并行工作。
6. 进度通过真实 thread/turn/item 事件回存，并通知对应手机讨论。旧任务的迟到事件回到旧任务，不能覆盖新讨论或其他 Agent。
7. 取消单独确认当前 jobId/threadId/turnId，持久保存请求后调用 turn/interrupt。界面先显示“正在取消”；只有准确 interrupted 终态才显示“已取消”。请求应答或关闭进程不能代替取消完成证据。
8. 取消保留任务、底稿、聊天和已经发生的文件修改，记录部分成果，不自动回滚。未知送达、断线和应用重启保留核对状态，不自动重新运行。
9. 完成须同时满足真实 completed 终态、非空报告及原 Workspace 文件证据；沿用现有成果核验回到同一 Output。取消、失败、方案或固定检查不得称实际修改完成。

## 三档合同

1.0.66 源码中的 Chat 订阅请求设置为：极速＝standard/low，高＝standard/high，Pro＝pro/high。`reasoning.mode` 与 `reasoning.effort` 独立，不能用 max 代替 Pro。目录、请求值与实际完成回执分别核对；不支持的模型或缺少准确回执时保留草稿和原请求，不暗中降档。

旧四字段订阅绑定保留原语义；新版显式档位绑定冻结 requestedProfile 与 reasoning。选择、保存、刷新连接均不发送。未经真实完成回执验证，不把可请求的设置显示成账号已验证的能力。

本轮 116 项订阅隔离检查和 137 项手机界面检查通过。手机增加每张本轮选图的常显 44px 移除按钮，只取消本轮引用，保留原图、文字和其他选图；更多菜单通向既有 Work 作业与 Output。旧选择恢复不会自动绑定新档位；须由用户明确重选档位或模型。档位映射及模拟回执检查不代替本账号真实三档验收，入口也不代表 Agent 控制器已经接通。

本机 app-server 0.160.0 的稳定 turn/start schema 目前没有 reasoning.mode 参数，模型目录也没有该能力字段。因此 Work 的 Pro 不能直接沿用 Chat 的 Pro 实现，须取得官方受支持入口及真实回执后开放；不借提示词或更高 effort 冒充。

## 接入后的验收

先在明确选定的测试 Workspace 串行验证真实订阅执行：一次手机确认→实际文件变化→事件进度→成果回到原记录。然后从手机取消第二轮，核对电脑 interrupted 终态和部分成果。最后验证两个自有任务的独立状态：取消 Agent 1，Agent 2 的 thread/turn 不变且继续运行。每项保存请求、来源、实际模型、终态与文件证据。

界面 fixture 和本机模拟协议试验不能代替上述真实验收。每次正式源码修改、验证和发布完成后，沿用既有安全更新流程，自主校验并更新本机，保护原安装身分、资料和未发送草稿。

## 官方依据

- [App Server：真实模型目录、进度、turn/interrupt 与终态](https://learn.chatgpt.com/docs/app-server)
- [已有 ChatGPT 订阅授权接入 Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [订阅预览限制及本机工具执行](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [Pro 与 effort 独立设置](https://developers.openai.com/api/docs/guides/reasoning#reasoning-mode)
