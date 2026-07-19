const storageKeys = {
  language: "codexControl.language.v1",
  theme: "codexControl.theme.v1",
  selectedWallpaper: "codexControl.selectedWallpaper.v1",
  wallpaperOrder: "codexControl.wallpaperOrder.v1",
  selectedTrack: "codexControl.selectedTrack.v1",
  musicTiers: "codexControl.musicTiers.v1",
  musicOrder: "codexControl.musicOrder.v1",
  musicTierVisibility: "codexControl.musicTierVisibility.v1",
  promotedLibraryTracks: "codexControl.promotedLibraryTracks.v1",
  volume: "codexControl.volume.v1",
  playbackMode: "codexControl.playbackMode.v1",
  moduleOrder: "codexControl.moduleOrder.v1",
  moduleArchive: "codexControl.moduleArchive.v1",
  moduleDeepArchive: "codexControl.moduleDeepArchive.v1",
  moduleDeleted: "codexControl.moduleDeleted.v1",
  publicLayoutInitialized: "codexControl.publicLayoutInitialized.v1",
  lastModule: "codexControl.lastModule.v1",
  downloadIntake: "codexControl.downloadIntake.v1",
  workspaceTodos: "codexControl.workspaceTodos.v1",
  tutorialMode: "codexControl.tutorialMode.v1",
  updateProduct: "codexControl.updateProduct.v1",
  randomRealmArtContext: "codexControl.randomRealmArtContext.v1",
  consoleView: "codexControl.consoleView.v1",
  blenderView: "codexControl.blenderView.v1",
  blenderPromptConfig: "codexControl.blenderPromptConfig.v1",
  lyricsHeight: "codexControl.lyricsHeight.v1"
};

const modules = [
  { id: "manager", labelKey: "managerNav", titleKey: "managerPageTitle", href: "manager.html" },
  { id: "workspace", labelKey: "workspaceNav", titleKey: "workspacePageTitle", href: "workspace.html" },
  { id: "blender", labelKey: "blenderNav", titleKey: "blenderPageTitle", href: "blender.html" },
  { id: "unity", labelKey: "unityNav", titleKey: "unityPageTitle", href: "unity.html" },
  { id: "steamwork", labelKey: "steamworkNav", titleKey: "steamworkPageTitle", href: "steamwork.html" },
  { id: "randomrealm", labelKey: "randomRealmNav", titleKey: "randomRealmPageTitle", href: "randomrealm.html" },
  { id: "music", labelKey: "musicNav", titleKey: "musicPageTitle", href: "music.html" },
  { id: "wallpaper", labelKey: "wallpaperNav", titleKey: "wallpaperPageTitle", href: "index.html" }
];

const editionModules = {
  developer: modules.map(item => item.id),
  public: modules.map(item => item.id),
  lite: ["wallpaper", "music"]
};
const moduleMap = new Map(modules.map(item => [item.id, item]));
const initialEditionParams = new URLSearchParams(window.location.search);
const initialEditionQuery = initialEditionParams.get("edition");
const hasEditionQuery = initialEditionParams.has("edition");

function normalizeEdition(value) {
  const clean = String(value || "").trim().toLowerCase();
  return ["public", "lite"].includes(clean) ? clean : "developer";
}

let consoleEdition = normalizeEdition(hasEditionQuery ? initialEditionQuery : "developer");

const playbackModes = ["repeatAll", "repeatOne", "playOnce"];
const steamworksAppId = "3983670";
const steamworksAppUrl = `https://partner.steamgames.com/apps/landing/${steamworksAppId}`;
const steamworksBuildsUrl = `https://partner.steamgames.com/apps/builds/${steamworksAppId}`;
const defaultRandomRealmArtTypes = ["MESH", "CURVE", "LIGHT", "CAMERA", "VOLUME", "FONT", "EMPTY"];
const randomRealmArtTypeLabels = {
  MESH: "Mesh",
  CURVE: "Curve",
  LIGHT: "Light",
  CAMERA: "Camera",
  VOLUME: "Volume",
  FONT: "Font",
  EMPTY: "Empty"
};
const defaultBlenderPromptConfig = {
  format: "Write the prompt in English. Use sections: Goal, Subject, Style, Image Requirements, Blender Context, Output Constraints, Negative Requirements.",
  image: "Use a single clean reference image if available. The object should be fully visible, centered, well lit, no watermark, no UI, no text, simple background, suitable for game asset / PBR material work.",
  style: "stylized realistic, readable silhouette, game-ready, clean material separation",
  basics: "Target use: RandomRealm / Unity. Preserve scale readability and make the result easy to understand from the selected Blender object.",
  resolution: "2k",
  customResolution: "",
  customWidth: "",
  customLength: ""
};
const musicStateVersion = 3;
const musicReorderCommitRatio = 1 / 3;
const musicReorderReturnRatio = 1 - musicReorderCommitRatio;
const musicPlaceholderLayoutPath = "__music_placeholder__";
const musicReflowAnimationMinDuration = 240;
const musicReflowAnimationMaxDuration = 480;
const musicSettleAnimationMinDuration = 210;
const musicSettleAnimationMaxDuration = 430;
const musicReflowAnimationEasing = "cubic-bezier(0.22, 0.52, 0.18, 1)";
const musicReflowContinueEasing = "cubic-bezier(0.22, 0.52, 0.18, 1)";
const musicSettleSpringFrequency = 6.7;
const musicSettleMaxStepMs = 28;
const musicSettleMaxDurationMs = 720;
const musicSettleVelocitySnap = 12;
const musicSettleMaxVelocityBase = 360;
const musicSettleMaxVelocityDistanceScale = 10;
const musicFloatingTrackScale = 1;
const musicReflowAnimationId = "music-reflow";
const musicDragStartThreshold = 4;
const musicDragSpringFrequency = 9.8;
const musicDragTakeoffSpringFrequency = 7.2;
const musicDragTakeoffDurationMs = 66;
const musicDragVisualSnapDistance = 0.55;
const musicDragVisualTargetSmoothingMs = 30;
const musicDragTakeoffTargetSmoothingMs = 22;
const musicDragVisualTargetSnapDistance = 0.8;
const musicDragSpringSnapSpeed = 8;
const musicDragIntentProbeLead = 0.74;
const musicDragFrameMs = 1000 / 60;
const musicDragMinStepMs = 5;
const musicDragTakeoffMinStepMs = 3;
const musicDragMaxStepMs = 24;
const musicDragMaxVisualStep = 60;
const musicDragTakeoffMaxVisualStep = 48;
const musicDragMaxVisualStepSqrtFactor = 0.95;
const musicDragMaxVisualStepRatio = 0.48;
const musicDragTakeoffMaxVisualStepRatio = 0.48;
const musicDragMinVisualStep = 16;
const musicDragSoftStepOverflowRatio = 0.28;
const musicDragLimitedVelocityBlend = 0.42;
const musicDragOpposingVelocityDamping = 0.48;
const musicDragSettledAxisDistance = 1.25;
const musicDragSettledAxisVelocityDamping = 0.48;
const musicReflowSnapDistance = 1.8;
const musicReflowContinueSnapDistance = 1.1;
const musicReflowContinueDurationScale = 1.12;
const musicSettleSnapDistance = 0.7;
const musicPlaceholderTargetSettleMs = 34;
const musicPlaceholderReflowMinIntervalMs = 24;
const musicKeyboardSeekSeconds = 5;
const wallpaperReorderCommitRatio = 1 / 3;
const wallpaperReorderReturnRatio = 1 - wallpaperReorderCommitRatio;
const wallpaperPlaceholderLayoutPath = "__wallpaper_placeholder__";
const wallpaperPlaceholderTargetSettleMs = 34;
const wallpaperPlaceholderReflowMinIntervalMs = 24;
const repeatLoopPath = "M14.6 22.5h-4.1a4 4 0 0 1-4-4v-6.25a4 4 0 0 1 4-4h10.5a4 4 0 0 1 4 4v6.25a4 4 0 0 1-4 4h-6.4zM17.8 19.3l-3.2 3.2 3.2 3.2";

// Player control icons: inline SVG, currentColor stroke, no bitmap assets.
// Keep the loop shape as a single path so the arrow cannot leave stray strokes.
const musicPlayerIcons = {
  repeatAll: `
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
      <path class="repeat-loop-icon" d="${repeatLoopPath}" />
    </svg>
  `,
  repeatOne: `
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
      <path class="repeat-loop-icon" d="${repeatLoopPath}" />
      <text class="repeat-one-number" x="16" y="15.7">1</text>
    </svg>
  `,
  playOnce: `
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
      <text class="repeat-one-number play-once-number" x="16" y="16">1</text>
    </svg>
  `
};

const i18n = {
  zh: {
    appTitle: "电脑总控台",
    managerPageTitle: "管理",
    workspacePageTitle: "Console",
    blenderPageTitle: "Blender",
    unityPageTitle: "Unity",
    steamworkPageTitle: "Steamwork",
    randomRealmPageTitle: "随机领域",
    wallpaperPageTitle: "桌布",
    managerNav: "管理",
    managerSectionLabel: "管理",
    workspaceNav: "Console",
    blenderNav: "Blender",
    unityNav: "Unity",
    steamworkNav: "Steamwork",
    randomRealmNav: "随机领域",
    musicPageTitle: "音乐",
    wallpaperNav: "桌布",
    musicNav: "音乐",
    archiveToggleTitle: "Archive",
    archiveTitle: "Archive",
    archiveEmpty: "这里先空着",
    archiveRestoreTitle: name => `打开 ${name}，双击恢复`,
    managerTitle: "布局管理",
    managerStatus: "记忆中",
    managerTabOrderLabel: "Tab 顺序",
    managerArchiveLabel: "Archive",
    managerDesktopLayoutLabel: "Windows 布局",
    managerDesktopLayoutValue: "待接入桌面图标快照",
    managerCurrentLayoutTitle: "当前控制台布局",
    managerLayoutSlotOne: "当前 Tab 排列",
    managerLayoutSlotTwo: "收纳箱",
    managerLayoutSlotThree: "桌面快照",
    managerLayoutHint: "拖动 tab 改变顺序，拖到 Archive 只会收纳，不会删除。",
    tutorialModeToggle: "教程模式",
    tutorialModeOn: "教程模式已打开：显示说明和辅助入口",
    tutorialModeOff: "教程模式已关闭：只保留关键入口",
    consoleCommonTab: "\u5e38\u7528",
    consoleCollaborationTab: "\u534f\u4f5c",
    feedbackReviewTitle: "\u6536\u5230\u7684\u56de\u62a5",
    desktopLayoutTitle: "\u684c\u9762\u5e03\u5c40",
    desktopLayoutLocalOnly: "\u4ec5\u672c\u673a",
    desktopLayoutPlanLabel: "\u684c\u9762\u5e03\u5c40\u65b9\u6848",
    desktopLayoutRememberedPlan: "\u5f53\u524d\u6b63\u5f0f\u5e03\u5c40",
    desktopLayoutDevicePlan: "\u672c\u673a\u5f53\u524d\u684c\u9762",
    desktopLayoutRestore: "\u6062\u590d",
    desktopLayoutSave: "\u4fdd\u5b58\u5f53\u524d\u7248",
    desktopLayoutImport: "\u5bfc\u5165",
    desktopLayoutLoading: "\u6b63\u5728\u8bfb\u53d6\u672c\u673a\u65b9\u6848",
    desktopLayoutEmpty: "\u8fd8\u6ca1\u6709\u5e03\u5c40\u65b9\u6848",
    desktopLayoutMeta: (icons, plans) => `${icons} \u4e2a\u56fe\u6807 \u00b7 ${plans} \u4e2a\u65b9\u6848`,
    desktopLayoutReady: "\u5c31\u7eea",
    desktopLayoutNotSaved: "\u5c1a\u672a\u4fdd\u5b58",
    desktopLayoutInvalid: "JSON \u4e0d\u53ef\u7528",
    desktopLayoutToolMissing: "\u672a\u627e\u5230\u5e03\u5c40\u5de5\u5177",
    desktopLayoutImporting: "\u6b63\u5728\u5bfc\u5165",
    desktopLayoutImported: count => `\u5df2\u5bfc\u5165 ${count} \u4e2a\u65b9\u6848`,
    desktopLayoutRestoring: "\u6b63\u5728\u6062\u590d\u5e76\u68c0\u67e5",
    desktopLayoutRestored: "\u5df2\u6062\u590d\uff0c\u68c0\u67e5\u901a\u8fc7",
    desktopLayoutRestoreIssues: (missing, mismatches, overlaps) => `\u5df2\u6062\u590d \u00b7 \u7f3a\u5931 ${missing} \u00b7 \u504f\u5dee ${mismatches} \u00b7 \u91cd\u53e0 ${overlaps}`,
    desktopLayoutSaving: "\u6b63\u5728\u5907\u4efd\u5e76\u4fdd\u5b58",
    desktopLayoutSaved: "\u5df2\u5907\u4efd\u5e76\u4fdd\u5b58",
    desktopLayoutFailed: message => `\u684c\u9762\u5e03\u5c40\u5931\u8d25\uff1a${message}`,
    desktopLayoutConfirmRestore: name => `\u4f7f\u7528\u201c${name}\u201d\u6062\u590d\u684c\u9762\u56fe\u6807\u4f4d\u7f6e\uff1f`,
    desktopLayoutConfirmSave: name => `\u5148\u5907\u4efd\u539f JSON\uff0c\u518d\u7528\u5f53\u524d\u684c\u9762\u8986\u76d6\u201c${name}\u201d\uff1f`,
    desktopLayoutGuide: "\u6062\u590d\u540e\u4f1a\u81ea\u52a8\u68c0\u67e5\u91cd\u53e0\u3001\u7f3a\u5931\u548c\u4f4d\u7f6e\u504f\u5dee\u3002\u4fdd\u5b58\u5f53\u524d\u7248\u4f1a\u5148\u5907\u4efd\u539f JSON\uff1b\u65b9\u6848\u4e0e\u5907\u4efd\u4e0d\u4f1a\u4e0a\u4f20\u3002",
    feedbackTop: "回报",
    feedbackTitle: "问题回报",
    feedbackCategoryLabel: "问题类型",
    feedbackCategoryBug: "错误",
    feedbackCategoryLayout: "排版",
    feedbackCategoryMusic: "音乐",
    feedbackCategoryUpdate: "更新",
    feedbackCategoryOther: "其他",
    feedbackDescriptionPlaceholder: "描述你遇到的问题",
    feedbackScreenshot: "截图",
    feedbackRemoveImage: "移除截图",
    feedbackSend: "发送",
    feedbackQuota: limit => `${limit}/天`,
    feedbackConnecting: "正在连接",
    feedbackReady: "可以发送",
    feedbackNotConfigured: "回报服务尚未连接",
    feedbackSending: "正在发送",
    feedbackSent: remaining => `已发送 · 今天还可发送 ${remaining} 条`,
    feedbackFailed: message => `发送失败：${message}`,
    feedbackDescriptionShort: "请至少写 10 个字。",
    feedbackImageTooLarge: "截图不能超过 5 MB。",
    feedbackImageType: "截图只支持 PNG、JPEG 或 WebP。",
    feedbackImageReadFailed: "无法读取这张截图。",
    feedbackInboxTitle: "收件箱",
    feedbackInboxRefresh: "刷新收件箱",
    feedbackInboxEmpty: "没有新回报",
    feedbackInboxResolve: "完成",
    feedbackInboxResolved: "已完成",
    feedbackOpenImage: "查看截图",
    feedbackInboxMeta: (category, version, date) => `${category} · ${version || "--"} · ${date}`,
    feedbackAdminSetup: "收件箱连接",
    feedbackAdminEndpoint: "Cloudflare Worker URL",
    feedbackAdminToken: "Admin token",
    feedbackAdminSave: "连接",
    feedbackAdminSaved: "收件箱已连接",
    blenderSectionLabel: "Blender",
    blenderBuilderTab: "Builder",
    blenderHelperTab: "Helper",
    blenderHelperTitle: "Blender Hub",
    blenderHelperBadge: "\u5730\u56fe",
    blenderHubReady: "\u53ef\u7528",
    blenderHubNext: "\u9884\u7559",
    blenderHubBuilderTitle: "Builder \u5de5\u4f5c\u53f0",
    blenderHubBuilderBody: "\u8d34\u56fe\u3001Prompt\u3001\u5f53\u524d\u7269\u4f53",
    blenderHubBuildingTitle: "Building \u9879\u76ee",
    blenderHubBuildingBody: "\u5efa\u7b51\u5757\u3001\u6a21\u5757\u3001\u6446\u653e\u89c4\u5219",
    blenderHubCharacterTitle: "\u89d2\u8272 / X",
    blenderHubCharacterBody: "\u4eba\u7269\u3001\u88c5\u5907\u3001\u6750\u8d28\u68c0\u67e5",
    blenderHubAnimationTitle: "Animation",
    blenderHubAnimationBody: "\u52a8\u4f5c\u3001\u65f6\u95f4\u8f74\u3001\u5bfc\u51fa\u8282\u594f",
    blenderHubTextureTitle: "Texture Lab",
    blenderHubTextureBody: "PBR\u3001\u5c3a\u5bf8\u3001\u66ff\u6362\u5305",
    blenderHubBridgeTitle: "Unity Bridge",
    blenderHubBridgeBody: "\u5bfc\u51fa\u3001Temp\u3001\u5bfc\u5165\u68c0\u67e5",
    blenderGithubHubTitle: "GitHub Coop",
    blenderGithubHubBody: "Blender 项目入口",
    blenderGithubTitle: "GitHub Coop",
    blenderGithubToggleTitle: "双击收起或展开 GitHub Coop",
    blenderGithubAddTitle: "添加已发布的 Blender GitHub 项目",
    blenderGithubBlendFilesLabel: "GitHub 仓库",
    blenderGithubLinksLabel: "项目入口",
    blenderGithubDesktop: "GitHub Desktop",
    blenderGithubCloud: "\u4e91\u7aef",
    blenderGithubCardLocalTitle: name => `\u5355\u51fb\u9009\u62e9\uff0c\u53cc\u51fb\u5728 GitHub Desktop \u6253\u5f00\uff1a${name}`,
    blenderGithubCardCloudTitle: name => `\u5355\u51fb\u9009\u62e9\uff0c\u53cc\u51fb\u7528 GitHub Desktop \u514b\u9686\uff1a${name}`,
    blenderGithubDesktopOpenTitle: "\u5728 GitHub Desktop \u6253\u5f00\u672c\u5730\u4ed3\u5e93",
    blenderGithubDesktopCloneTitle: "\u7528 GitHub Desktop \u514b\u9686\u8fd9\u4e2a\u4ed3\u5e93",
    blenderGithubGuide: "\u672a\u4e0b\u8f7d\uff1a\u53cc\u51fb\u5361\u7247\u5b8c\u6210 Clone\uff0c\u7136\u540e\u70b9 + \u9009\u62e9 .blend\u3002\u4fee\u6539\u524d\u5148 Fetch/Pull\uff0c\u5b8c\u6210\u540e Commit + Push\u3002",
    blenderGithubStateCloud: "\u4e91\u7aef\uff0c\u5c1a\u672a\u4e0b\u8f7d",
    blenderGithubFolder: "文件",
    blenderGithubOpenShort: "GitHub",
    blenderGithubNoBlendFiles: "还没有加入已发布的 GitHub 仓库",
    blenderGithubCardTitle: name => `单击选择，双击打开 GitHub：${name}`,
    blenderGithubLoading: "读取中",
    blenderGithubReady: "就绪",
    blenderGithubProjectLabel: "GitHub 仓库",
    blenderGithubRefreshTitle: "刷新 Git 状态",
    blenderGithubBlendFileLabel: "Blend 文件",
    blenderGithubBranchLabel: "分支",
    blenderGithubRemoteLabel: "Remote",
    blenderGithubLastVersionLabel: "最近版本",
    blenderGithubRepositoryLabel: "GitHub 仓库",
    blenderGithubRepositoryPlaceholder: "https://github.com/owner/repository.git",
    blenderGithubVisibilityLabel: "可见性",
    blenderGithubPrivate: "Private",
    blenderGithubPublic: "Public",
    blenderGithubVersionLabel: "版本号",
    blenderGithubMessageLabel: "本次版本说明",
    blenderGithubMessagePlaceholder: "这个版本改了什么",
    blenderGithubScopeLabel: "共享范围",
    blenderGithubScopeCurrent: "仅当前 .blend",
    blenderGithubScopeProject: "整个项目目录",
    blenderGithubScopeCustom: "自定义",
    blenderGithubIncludeLabel: "包含文件",
    blenderGithubExcludeLabel: "排除文件",
    blenderGithubChangesLabel: "Git 变更",
    blenderGithubInitialize: "初始化仓库",
    blenderGithubCommit: "提交版本",
    blenderGithubPush: "推送",
    blenderGithubOpen: "打开 GitHub",
    blenderGithubStateUninitialized: "未初始化",
    blenderGithubStateInitialized: "已初始化",
    blenderGithubStateDirty: "存在未提交修改",
    blenderGithubStateCommitted: "已提交",
    blenderGithubStatePendingPush: "待推送",
    blenderGithubStateBehind: "远端有更新",
    blenderGithubStateSynced: "已同步",
    blenderGithubStateGitUnavailable: "Git 不可用",
    blenderGithubToolsReady: "Git · LFS 已就绪",
    blenderGithubLfsMissing: "需要安装 Git LFS",
    blenderGithubGhReady: "GitHub CLI 已登录",
    blenderGithubGhFallback: "GitHub CLI 未安装或未登录；可填写空仓库 URL",
    blenderGithubWorkingTreeClean: "工作区干净",
    blenderGithubMoreChanges: count => `还有 ${count} 项变更`,
    blenderGithubLastCommit: (hash, subject) => `${hash} · ${subject}`,
    blenderGithubNoCommit: "还没有提交",
    blenderGithubSaving: "正在保存项目配置",
    blenderGithubSaved: "项目配置已保存",
    blenderGithubInitializedReady: "仓库和 Git LFS 已就绪",
    blenderGithubInitializedNoRemote: "本地仓库已就绪；填写空 GitHub 仓库 URL 后即可推送",
    blenderGithubCommitComplete: version => `版本 ${version} 已提交`,
    blenderGithubPushComplete: "已推送到 GitHub",
    blenderGithubOpenComplete: "已打开 GitHub 仓库",
    blenderGithubInitializing: "正在初始化 Git 和 Git LFS",
    blenderGithubCommitting: "正在提交版本",
    blenderGithubPushing: "正在推送到 GitHub",
    blenderGithubOpening: "正在打开 GitHub 仓库",
    blenderGithubFailed: message => `处理失败：${message}`,
    blenderGithubPublicConfirm: "Public 仓库所有人都可以访问。确认切换为 Public？",
    blenderGithubCreateConfirm: name => `没有填写仓库 URL。要使用 GitHub CLI 创建 ${name} 吗？`,
    blenderGithubReplaceRemoteConfirm: "当前 origin 指向另一个仓库。确认替换它？",
    blenderGithubSelectProject: "选择 Blender 项目",
    blenderGithubAddingProject: "正在选择 GitHub 项目",
    blenderGithubProjectAdded: "GitHub 仓库已加入",
    blenderGithubOrderFailed: message => `排序保存失败：${message}`,
    unitySectionLabel: "Unity",
    unityControlTitle: "Unity Control",
    unityControlBody: "RandomRealm2 工程入口、素材入口和 Unity 侧发布前检查。",
    unityBridgeLabel: "桥接状态",
    unityBridgeTempLabel: "临时导入",
    unityBridgeReady: "等待 Blender 发送",
    unityBridgeBody: "Blender 导出到 Unity temp 后，RandomRealm 导入器再把 temp 内容归类到 Builder 生成资产、Prefab 和清单里。",
    steamworkTitle: "Steamwork",
    steamworkReady: "\u5c31\u7eea",
    steamworkBody: "\u7ba1\u7406 Steamworks\u3001SteamPipe GUI\u3001ContentBuilder/content \u548c\u5ba3\u4f20\u66f4\u65b0\u7d20\u6750\u3002",
    steamworkDashboard: "Steamworks",
    steamworkPublishRoot: "ContentBuilder",
    steamworkGameContent: "Content",
    steamworkPublishTool: "SteamPipe GUI",
    steamworkArtAssets: "\u7d20\u6750",
    steamworkGameContentLabel: "Content",
    steamworkGameContentTitle: "\u5bfc\u5165\u6e38\u620f\u5185\u5bb9",
    steamworkGameContentReady: "\u628a\u6e38\u620f\u6784\u5efa\u6587\u4ef6\u62d6\u5230 ContentBuilder/content\u3002",
    steamworkPublishToolLabel: "SteamPipe GUI",
    steamworkPublishToolTitle: "\u5bfc\u5165 SteamPipe GUI \u5de5\u5177",
    steamworkPublishToolReady: "\u628a SteamPipeGUI.exe \u6216\u76f8\u5173\u6587\u4ef6\u62d6\u5230\u8fd9\u91cc\u3002",
    steamworkTipsLabel: "\u53d1\u5e03\u6d41\u7a0b Tips",
    steamworkStepsSection: "\u6b65\u9aa4",
    steamworkAppInfoSection: "App \u4fe1\u606f",
    steamworkStepColumn: "\u6b65\u9aa4",
    steamworkActionColumn: "\u64cd\u4f5c",
    steamworkNoteColumn: "\u63d0\u9192",
    steamworkFieldColumn: "\u5b57\u6bb5",
    steamworkValueColumn: "\u503c",
    steamworkStepBuild: "1. \u6253\u5305",
    steamworkStepUpload: "2. \u4e0a\u4f20",
    steamworkStepRenewDepot: "3. Renew Depot",
    steamworkStepPublish: "4. \u53d1\u5e03",
    steamworkTipBuild: "\u5148\u5728 Unity / PC \u6253\u5305\u6e38\u620f\u3002",
    steamworkBuildNote: "\u53ea\u7528 PC\u3002",
    steamworkTipConfig: "SteamPipe GUI \u5efa\u8bae\u586b\u5199\uff1aApp ID 3983670\uff0cDepot ID 3983671\uff0cBuild Description \u53ef\u7528 1.5.31\u3002",
    steamworkTipPaths: "\u8def\u5f84\uff1aBuild Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\\content\uff0cContentBuilder Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\u3002",
    steamworkTipLogin: "Steam Login = pixel_roblez\uff1b\u5bc6\u7801\u4e0d\u5199\u8fdb Console\u3002",
    steamworkTipContent: "\u628a\u6253\u5305\u7ed3\u679c\u653e\u5230 ContentBuilder/content\u3002",
    steamworkTipOpenPrefix: "\u7528 ",
    steamworkTipPipe: "\u586b\u5b57\u6bb5\u5e76\u4e0a\u4f20\u3002",
    steamworkPublishToolLocate: "\u5b9a\u4f4d .exe",
    steamworkPublishToolChoose: "\u9009\u62e9 SteamPipeGUI.exe",
    steamworkPublishToolMissing: "\u6ca1\u6709\u627e\u5230 SteamPipeGUI.exe\uff1b\u8bf7\u5148\u5b9a\u4f4d / \u5bfc\u5165\u8fd9\u4e2a exe\u3002",
    steamworkUploadNote: "PC + Mobile \u786e\u8ba4\u3002",
    steamworkBuildsLink: "Steamworks Builds",
    steamworkTipRenewDepot: "\u628a\u4e0a\u4f20\u7684 build \u8bbe\u4e3a\u4e0a\u7ebf\u3002",
    steamworkRenewDepotNote: "PC + Mobile \u786e\u8ba4\u3002",
    steamworkTipPublish: "\u6700\u540e\u786e\u8ba4\u5e76\u53d1\u5e03\u66f4\u6539\uff1b\u53ef\u80fd\u9700\u8981 Steam Guard / \u624b\u673a\u786e\u8ba4\u3002",
    steamworkPublishNote: "Pc only",
    steamworkPasswordNote: "\uff08\u5bc6\u7801\u4e0d\u5b58 Console\uff09",
    steamworkImportDragging: "\u677e\u624b\u540e\u5bfc\u5165\u3002",
    steamworkImporting: (count, target) => `\u6b63\u5728\u5bfc\u5165 ${count} \u4e2a\u6587\u4ef6\u5230 ${target}\u3002`,
    steamworkImported: (count, target) => `\u5df2\u5bfc\u5165 ${count} \u4e2a\u6587\u4ef6\u5230 ${target}\u3002`,
    steamworkImportFailed: message => `Steamwork \u5bfc\u5165\u5931\u8d25\uff1a${message}`,
    steamworkAssetsLabel: "\u7d20\u6750\u53f0\u8d26",
    steamworkAssetsTitle: "Steam \u7d20\u6750\u6e05\u5355",
    steamworkAssetLoading: "\u8bfb\u53d6\u4e2d",
    steamworkAssetLoadFailed: message => `\u7d20\u6750\u8bfb\u53d6\u5931\u8d25\uff1a${message}`,
    steamworkAssetSummary: (ready, total, review, missing, optional, files) => `${ready}/${total} \u5df2\u5c31\u7eea\u3000${review} \u5f85\u68c0\u67e5\u3000${missing} \u7f3a\u5931\u3000${optional} \u53ef\u9009\u3000${files} \u6587\u4ef6`,
    steamworkAssetSummaryReady: (ready, total) => `${ready}/${total} \u5df2\u5c31\u7eea`,
    steamworkAssetSummaryReview: count => `${count} \u5f85\u68c0\u67e5`,
    steamworkAssetSummaryMissing: count => `${count} \u7f3a\u5931`,
    steamworkAssetSummaryOptional: count => `${count} \u53ef\u9009`,
    steamworkAssetSummaryFiles: count => `${count} \u6587\u4ef6`,
    steamworkAssetColumn: "\u7d20\u6750",
    steamworkStatusColumn: "\u72b6\u6001",
    steamworkSpecColumn: "\u89c4\u683c",
    steamworkCurrentColumn: "\u5f53\u524d\u6587\u4ef6",
    steamworkTargetColumn: "\u4f4d\u7f6e",
    steamworkAssetReady: "\u5c31\u7eea",
    steamworkAssetReview: "\u5f85\u68c0\u67e5",
    steamworkAssetMissing: "\u7f3a\u5931",
    steamworkAssetOptional: "\u53ef\u9009",
    steamworkAssetRequired: "\u5fc5\u9700",
    steamworkAssetOptionalLabel: "\u53ef\u9009",
    steamworkAssetNoFile: "\u6ca1\u6709\u5339\u914d\u6587\u4ef6",
    steamworkAssetNeedSpec: spec => `\u9700\u8981\uff1a${spec}`,
    steamworkAssetWhereToUse: target => `\u4f4d\u7f6e\uff1a${target}`,
    steamworkAssetMissingAction: "\u628a\u7b26\u5408\u89c4\u683c\u7684\u6587\u4ef6\u62d6\u5230\u4e0b\u65b9\u201c\u51c6\u5907\u66ff\u6362\u201d\u3002",
    steamworkAssetMissingGuideTitle: "\u8865\u6587\u4ef6",
    steamworkAssetMissingGuideSpec: spec => `\u89c4\u683c ${spec}`,
    steamworkAssetMissingGuideDrop: "\u62d6\u5230\u51c6\u5907\u66ff\u6362",
    steamworkAssetMissingGuideTarget: target => `Steam \u4f4d\u7f6e ${target}`,
    steamworkAssetOptionalGuideTitle: "\u53ef\u9009\u7d20\u6750",
    steamworkAssetOptionalGuideNote: "\u4e0d\u963b\u585e\u53d1\u5e03",
    steamworkAssetOptionalGuideSpec: spec => `\u5efa\u8bae ${spec}`,
    steamworkAssetOptionalGuideTarget: target => `Steam \u4f4d\u7f6e ${target}`,
    steamworkAssetFitOk: "\u89c4\u683c\u5339\u914d",
    steamworkAssetFitFormat: "\u683c\u5f0f\u4e0d\u7b26",
    steamworkAssetFitSize: "\u5c3a\u5bf8\u4e0d\u7b26",
    steamworkAssetFitFormatSize: "\u683c\u5f0f / \u5c3a\u5bf8\u4e0d\u7b26",
    steamworkAssetFitType: "\u7c7b\u578b\u4e0d\u7b26",
    steamworkAssetFitCheck: "\u9700\u68c0\u67e5",
    steamworkAssetOpen: "\u6253\u5f00",
    steamworkAssetOpenFailed: message => `\u6253\u5f00\u7d20\u6750\u5931\u8d25\uff1a${message}`,
    steamworkAssetSource: root => `\u7d20\u6750\u5e93\uff1a${root}`,
    steamworkAssetMatched: "\u5f53\u524d\u5339\u914d",
    steamworkAssetCandidates: "\u5019\u9009\u7d20\u6750",
    steamworkAssetReferenceCandidates: "\u53c2\u8003\u5019\u9009",
    steamworkAssetReferenceHint: "\u6ca1\u6709\u4e25\u683c\u5339\u914d\uff1b\u4e0b\u9762\u662f\u53ef\u53c2\u8003\u6587\u4ef6\u3002",
    steamworkAssetOptionalCandidates: "\u53ef\u53c2\u8003\u7d20\u6750",
    steamworkAssetOptionalReferenceHint: "\u53ef\u9009\u9879\u76ee\uff1b\u4e0b\u9762\u662f\u76f8\u5173\u53c2\u8003\u6587\u4ef6\u3002",
    steamworkAssetStageTitle: "\u51c6\u5907\u66ff\u6362",
    steamworkAssetStageHint: "\u628a\u65b0\u7d20\u6750\u62d6\u5230\u8fd9\u91cc\uff0c\u5148\u6536\u8fdb D:\\ArtAsset\u3002",
    steamworkAssetStageDragging: "\u677e\u624b\u540e\u6536\u8fdb\u7d20\u6750\u5e93",
    steamworkAssetStaging: (count, slot) => `\u6b63\u5728\u4e3a ${slot} \u6536\u5165 ${count} \u4e2a\u6587\u4ef6\u3002`,
    steamworkAssetStaged: (count, folder) => `\u5df2\u6536\u5165 ${count} \u4e2a\u6587\u4ef6\u5230 ${folder}\u3002`,
    steamworkAssetStageFailed: message => `\u7d20\u6750\u6536\u5165\u5931\u8d25\uff1a${message}`,
    steamworkAssetFileCount: count => `${count} \u4e2a\u6587\u4ef6`,
    steamworkAssetFolderStore: "\u5546\u5e97\u7d20\u6750",
    steamworkAssetFolderScreenshots: "\u622a\u56fe",
    steamworkAssetFolderVideo: "\u89c6\u9891",
    steamworkAssetFolderStaged: "\u5f85\u66ff\u6362",
    steamworkIssueMissingRequired: "\u7f3a\u5c11\u5fc5\u9700\u7d20\u6750",
    steamworkIssueOptional: "\u53ef\u9009",
    steamworkIssueNeedFiles: count => `\u9700\u8981 ${count} \u4e2a\u6587\u4ef6`,
    steamworkIssueCheckFile: "\u5df2\u627e\u5230\u6587\u4ef6\uff0c\u9700\u68c0\u67e5\u5c3a\u5bf8 / \u683c\u5f0f",
    steamworkAttentionTitle: "\u5f85\u5904\u7406",
    steamworkAttentionCount: count => `${count} \u9879`,
    steamworkAttentionHint: "\u70b9\u51fb\u8df3\u5230\u5bf9\u5e94\u7d20\u6750",
    steamworkAttentionFixMissing: "\u8865\u6587\u4ef6",
    steamworkAttentionReview: "\u68c0\u67e5",
    steamworkAssetNoCandidates: "\u6ca1\u6709\u76f8\u5173\u5019\u9009",
    steamworkAssetShowCandidates: count => `\u67e5\u770b ${count} \u4e2a\u5019\u9009`,
    steamworkAssetMoreCandidates: count => `\u8fd8\u6709 ${count} \u4e2a\u5019\u9009`,
    steamworkAssetShowFiles: count => `\u67e5\u770b ${count} \u4e2a\u6587\u4ef6`,
    steamworkAssetMoreFiles: count => `\u8fd8\u6709 ${count} \u4e2a\u6587\u4ef6`,
    steamworkAssetExpand: "\u5c55\u5f00\u7ba1\u7406",
    steamworkCategoryStore: "\u5546\u5e97\u9875",
    steamworkCategoryLibrary: "\u8d44\u6599\u5e93",
    steamworkCategoryCommunity: "\u793e\u533a",
    steamworkCategoryVideo: "\u89c6\u9891",
    steamworkCategoryMissing: count => `${count} \u7f3a\u5931`,
    steamworkCategoryReview: count => `${count} \u5f85\u68c0\u67e5`,
    steamworkCategoryOptional: count => `${count} \u53ef\u9009`,
    steamworkTargetGraphicalAssets: "\u5546\u5e97\u9875 > \u56fe\u5f62\u8d44\u4ea7",
    steamworkTargetScreenshots: "\u5546\u5e97\u9875 > \u622a\u56fe",
    steamworkTargetCommunityIcons: "\u5546\u5e97\u9875 > \u793e\u533a\u4e0e\u5ba2\u6237\u7aef\u56fe\u6807",
    steamworkTargetLibraryAssets: "Steamworks > \u8d44\u6599\u5e93\u7d20\u6750",
    steamworkTargetTrailers: "\u5546\u5e97\u9875 > \u9884\u544a\u7247",
    activeProjectValue: "随机领域 / Blender Assets",
    timeLabel: "Time",
    wallpaperSectionLabel: "预览",
    wallpaperTitle: "预览",
    add: "+ 加入",
    emptyTitle: "等待候选图片",
    emptyBody: "支持 jpg、png、bmp、webp。",
    selectedLabel: "当前候选",
    sizeLabel: "大小",
    themeDark: "暗色",
    themeLight: "亮色",
    readyStatus: "就绪",
    candidatesSectionLabel: "图库",
    candidatesTitle: "候选",
    notSelected: "未选择",
    noSize: "--",
    count: count => `${count} 张`,
    noCandidates: "还没有候选",
    addHint: "支持 jpg / png / bmp / webp。",
    cardTitle: name => `${name}\n单击选择，双击应用`,
    deleteButtonLabel: name => `删除 ${name}`,
    deletePrompt: "删除？",
    confirmDeleteAction: "删除",
    cancelDeleteAction: "取消",
    added: count => `已加入 ${count} 张桌布。`,
    applied: name => `已应用：${name}`,
    deleted: name => `已删除：${name}`,
    loadFailed: message => `读取桌布失败：${message}`,
    uploadFailed: message => `加入失败：${message}`,
    applyFailed: message => `应用失败：${message}`,
    deleteFailed: message => `删除失败：${message}`,
    musicTitle: "音乐播放器",
    nowPlayingLabel: "当前播放",
    musicEmptyBody: "加入 mp3、wav、m4a、flac、ogg、opus。",
    lyricsSectionLabel: "Lyrics",
    lyricsTitle: "歌词",
    lyricsHide: "收起",
    lyricsShow: "展开歌词",
    lyricsEmpty: "这首歌还没有歌词文件。",
    lyricsLoading: "正在读取歌词。",
    lyricsInstrumental: "没有可显示的歌词。",
    lyricsUnsynced: "歌词没有时间轴，作为全文显示。",
    lyricsLoadFailed: message => `歌词读取失败：${message}`,
    lyricsButtonLabel: name => `歌词：${name}`,
    lyricsFindLabel: name => `查找歌词：${name}`,
    lyricsSeekLabel: line => `跳到歌词：${line}`,
    lyricsMarkArmed: "已选中，直接填开始/结束时间",
    lyricsMarkSaved: time => `已标记 ${time}`,
    lyricsEndMarkSaved: time => `结束点 ${time}`,
    lyricsStartMarkSaved: time => `开始点 ${time}`,
    lyricsMarkCancelled: "已撤销这个词缝本次标记",
    lyricsMarkFailed: message => `标记失败：${message}`,
    lyricsTimingPick: "同一句歌词右键三下才打开时间编辑（施工中）。",
    lyricsTimingClose: "关闭时间设置",
    lyricsTimingStartLabel: "开始变白",
    lyricsTimingEndLabel: "完全变白",
    lyricsTimingTimePlaceholder: "分:秒.毫秒",
    lyricsTimingUseNowStart: "当前作开始",
    lyricsTimingUseNowEnd: "当前作结束",
    lyricsTimingSave: "保存",
    lyricsTimingClear: "撤销本次",
    lyricsTimingTarget: (word, line) => `正在调：${word || "这一格"} · 第 ${line} 行`,
    lyricsTimingLineTitle: (line, count) => `第 ${line} 行 · ${count} 个字/词`,
    lyricsTimingPreviewLabel: "原句",
    lyricsTimingRowsLabel: "逐字时间",
    lyricsTimingTokenHeader: "字/词",
    lyricsTimingStartHeader: "开始",
    lyricsTimingEndHeader: "结束",
    lyricsTimingDurationHeader: "时长",
    lyricsTimingDetailTitle: word => `精调：${word || "这一格"}`,
    lyricsTimingRangeTitle: (start, end) => start === end ? `精调：${start}` : `精调：${start} 到 ${end}`,
    lyricsTimingWaveLabel: "声音波形",
    lyricsTimingSelectLine: "选整句",
    lyricsTimingRangeDuration: duration => `选区 ${duration}`,
    lyricsTimingSaveSelected: "保存选中",
    lyricsTimingSaveLine: "保存本句",
    lyricsTimingClearLine: "撤销本句本次",
    lyricsTimingSaved: (start, end) => `已暂存：${start} 到 ${end}`,
    lyricsTimingRangeSaved: count => `已暂存选中的 ${count} 个字/词`,
    lyricsTimingLineSaved: count => `已暂存 ${count} 个字/词`,
    lyricsTimingCleared: "已撤销这个字/词本次设置",
    lyricsTimingLineCleared: "已撤销这一句本次设置",
    lyricsTimingLineEmpty: "这一句还没有填完整的时间",
    lyricsTimingIncomplete: "开始和结束都要填",
    lyricsTimingInvalid: "时间格式不对，用 1:23.450 或 83.45",
    lyricsTimingRangeInvalid: "结束时间要晚于开始时间",
    lyricsTimingOrderInvalid: "后一个词不能压到前一个词里",
    lyricsTimingOrderCorrected: count => `已按顺序纠正 ${count} 个词`,
    lyricsTimingWordMoved: word => `已移动 ${word}`,
    lyricsTimingHoldLabel: "静止区",
    lyricsTimingHoldHint: "Alt 拖动会保留空隙，空隙不读条。",
    lyricsTimingHoldInserted: "已加静止区",
    lyricsTimingHoldRemoved: "已删除静止区",
    lyricsTimingHoldInsertedBetween: (previous, next) => `已在 ${previous} / ${next} 之间加静止区`,
    lyricsTimingHoldRemovedBetween: (previous, next) => `已删除 ${previous} / ${next} 之间的静止区`,
    lyricsTimingHoldTooShort: "这里空间太短，换个位置",
    lyricsNotFound: name => `没找到歌词：${name}`,
    lyricsSearchFailed: message => `歌词查找失败：${message}`,
    previousTrack: "上一首",
    playTrack: "播放",
    pauseTrack: "暂停",
    nextTrack: "下一首",
    playbackModeSequential: "顺序",
    playbackModeRepeatAll: "循环",
    playbackModeRepeatOne: "单曲",
    playbackModePlayOnce: "一次",
    playbackModeTitle: label => `播放模式：${label}`,
    volumeLabel: "音量",
    musicListTitle: "本地音乐",
    musicNotSelected: "未选择",
    trackCount: count => `${count} 首`,
    noTracks: "还没有音乐",
    musicLocalEmpty: "从 Library 拖入音乐",
    musicLocalDropActive: "松开加入本地音乐",
    musicTierFirst: "1st",
    musicTierSecond: "2nd",
    musicTierThird: "3rd",
    musicTierDropHint: "拖到这里分级",
    musicAddHint: "支持 mp3 / wav / m4a / flac / ogg / opus。",
    musicAddDropTitle: "加入音乐",
    musicAddDropBody: "粘贴链接",
    musicPickLocal: "本地文件",
    musicAddMenuQuestion: "加入音乐",
    musicAddViaUrl: "YouTube 链接",
    musicAddViaFile: "MP3 文件",
    musicAddViaLibrary: "Playlist / 其他",
    musicPlaylistPlaceholder: "Playlist 链接",
    musicLinkPlaceholder: "YouTube 链接",
    musicLinkDownload: "下载",
    musicUseBrowserCookies: "使用 Edge 登录状态",
    musicCookieFile: "cookies.txt",
    musicCookieReady: "cookies OK",
    musicCookieUploaded: "已导入 YouTube cookies.txt。",
    musicCookieUploadFailed: message => `导入 cookies 失败：${message}`,
    musicLibraryTitle: "Library",
    musicLibraryDropTitle: "Add playlist",
    musicLibraryDropBody: "拖入 YouTube playlist。",
    musicLibraryReady: "等待 playlist 链接。",
    musicLibraryEmpty: "Library 还没有音乐",
    musicLibraryImporting: provider => `正在准备 ${provider} playlist。`,
    musicLibraryStarted: name => `已开始抓取：${name}`,
    musicLibraryFailed: message => `Library 导入失败：${message}`,
    musicLibraryStatusQueued: "等待中",
    musicLibraryStatusGrabbing: "抓取中",
    musicLibraryStatusReady: "已完成",
    musicLibraryStatusFailed: "失败",
    musicLibraryMeta: (count, expected) => expected ? `${count}/${expected} 首` : `${count} 首`,
    trackTitle: name => `${name}\n点击播放，右键唤出删除`,
    deleteTrackLabel: name => `删除 ${name}`,
    trackMeta: (type, size) => `${type.toUpperCase()} · ${size}`,
    musicAdded: count => `已加入 ${count} 首音乐。`,
    musicLyricsAdded: count => `已加入 ${count} 个歌词文件。`,
    musicDeleted: name => `已删除：${name}`,
    musicLoadFailed: message => `读取音乐失败：${message}`,
    musicUploadFailed: message => `加入音乐失败：${message}`,
    musicPlayFailed: message => `播放失败：${message}`,
    musicLinkEmpty: "没有读到 URL。",
    musicLinkChecking: provider => `下载中：${provider}`,
    musicLinkPrepared: provider => `已识别：${provider}`,
    musicLinkImported: name => `完成：${name}`,
    musicPromoted: name => `已加入本地：${name}`,
    musicPromoteFailed: message => `加入本地失败：${message}`,
    musicLinkFailed: message => `链接导入失败：${message}`,
    workspaceTitle: "当前工作",
    workspaceStatus: "准备中",
    randomRealmSectionLabel: "随机领域",
    randomRealmTitle: "随机领域管理",
    randomRealmStatus: "项目中",
    randomRealmProjectLabel: "项目",
    randomRealmUnityLabel: "Unity 工程",
    randomRealmBuilderLabel: "Builder 系统",
    randomRealmGroundLabel: "地面页面",
    randomRealmPipelineLabel: "资产流程",
    randomRealmCommunityLabel: "社群",
    randomRealmSurfaceTitle: "地面与场景",
    randomRealmSurfaceStatus: "预留中",
    randomRealmSurfaceBody: "这里先给地面页面、建筑放置、场景检查和导出入口留位置。",
    randomRealmReleaseTitle: "发布控制",
    randomRealmReleaseBody: "Steamworks、发布包、宣传素材和工程入口。",
    randomRealmOpenReady: "就绪",
    randomRealmSteamworks: "Steamworks 后台",
    randomRealmPublishFolder: "Publish 文件夹",
    randomRealmProjectFolder: "Unity 工程",
    randomRealmPromoFolder: "宣传素材",
    randomRealmOpening: name => `正在打开：${name}`,
    randomRealmOpened: name => `已打开：${name}`,
    randomRealmOpenFailed: message => `打开失败：${message}`,
    randomRealmArtTitle: "Art Supporter",
    randomRealmBlenderProjectLabel: "Blender 项目",
    randomRealmProjectSearchLabel: "项目搜索",
    randomRealmProjectSearchPlaceholder: "输入项目名或路径后搜索",
    randomRealmArtTypeLabel: "对象类型",
    randomRealmObjectSearchPlaceholder: "搜索物体",
    randomRealmSyncLiveSelection: "同步选中",
    randomRealmLiveSynced: name => `已同步 Blender 选中物体：${name}`,
    randomRealmLiveUnavailable: "没有检测到实时 Blender 选中状态",
    randomRealmLiveProjectMismatch: "当前 Blender 打开的不是这个项目",
    randomRealmLiveObjectMissing: name => `Blender 选中的物体不在当前列表：${name}`,
    randomRealmUsedTexturesLabel: "用到的贴图",
    randomRealmTextureManagerTitle: "\u8d34\u56fe\u7ba1\u7406\u5668",
    randomRealmTextureManagerCount: (visible, total) => `${visible}/${total} \u5f20`,
    randomRealmTextureInspectorLabel: "\u9009\u4e2d\u8d34\u56fe",
    randomRealmTextureDetailMaterial: "\u6750\u8d28",
    randomRealmTextureDetailRole: "\u7c7b\u578b",
    randomRealmTextureDetailNode: "\u8282\u70b9",
    randomRealmTextureDetailState: "\u72b6\u6001",
    randomRealmTextureDetailFile: "\u6587\u4ef6",
    randomRealmTextureDetailPath: "\u8def\u5f84",
    randomRealmTextureStateReady: "\u53ef\u7528",
    randomRealmTextureStateMissing: "\u7f3a\u5931",
    randomRealmTextureStatePending: "\u5f85\u5e94\u7528",
    randomRealmTexturesRefreshed: (name, count) => `已刷新 ${name}：${count} 张贴图`,
    randomRealmAllMaterials: "All",
    randomRealmOldTextureLabel: "Old",
    randomRealmNewTextureLabel: "New",
    randomRealmTextureNotSelected: "未选择",
    randomRealmNewTextureSlot: "新 Map 槽",
    randomRealmDropNewTexture: "把新贴图或一组 PBR 拖到这里",
    randomRealmTexturePreviewEmpty: "暂无预览",
    randomRealmTexturePreviewUnsupported: "无法预览",
    randomRealmTextureDragHint: "双击打开原文件；拖到 Photoshop 时会尽量按文件投递。路径：",
    randomRealmNativeDragStarted: "正在用 Windows 原生文件拖拽",
    randomRealmTextureOpened: (name, app) => `已打开贴图：${name}${app ? `（${app}）` : ""}`,
    randomRealmTextureOpenFailed: message => `打开贴图失败：${message}`,
    randomRealmTexturePacked: (name, location) => `已装入 ${location || "textures"}：${name}`,
    randomRealmTexturePackedMany: (count, location) => `已装箱 ${count} 个贴图包到 ${location || "textures"}。`,
    randomRealmTextureAutoPackedMany: (count, location) => `已自动装箱 ${count} 个贴图包到 ${location || "textures"}，等 Blender Apply 后会清空 New。`,
    randomRealmTextureAppliedCleared: count => `Blender 已 Apply，已清空 ${count} 个 New 贴图。`,
    randomRealmStageBlankTexture: "+ Map",
    randomRealmBlankTextureStaged: name => `已加入空贴图槽：${name}`,
    randomRealmTextureStagedRemoved: name => `已移出待装箱贴图：${name}`,
    randomRealmTextureRemovalPackaged: (name, packageName) => `已装箱删除指令：${name}${packageName ? `（${packageName}）` : ""}`,
    randomRealmTexturePackReady: "把新贴图拖进来后会自动装入 Blender textures；Apply 前不会直接修改 Blender。",
    randomRealmTextureDimensionsUnknown: "尺寸未知",
    randomRealmTextureDimensionCancelled: "已取消：贴图尺寸没有通过确认",
    randomRealmTextureSizeMismatchConfirm: (oldSize, newSize) => `贴图尺寸不一致。\n\nOld: ${oldSize}\nNew: ${newSize}\n\n仍然要自动装箱吗？`,
    randomRealmTextureSizeUnknownConfirm: (oldSize, newSize) => `有贴图尺寸无法确认。\n\nOld: ${oldSize}\nNew: ${newSize}\n\n仍然要自动装箱吗？`,
    randomRealmArtReady: "就绪",
    randomRealmBlenderLoading: "正在读取 Blender 项目",
    randomRealmBlenderProjectLoaded: count => `已找到 ${count} 个 Blender 项目`,
    randomRealmBlenderNoProject: "没有找到 Blender 项目",
    randomRealmBlenderNoObject: "没有找到物体",
    randomRealmBlenderNoTexture: "这个物体还没有贴图",
    randomRealmMaterialNoTexture: "这个材质没有 image texture",
    randomRealmMaterialNoTextureHint: "切到 All 或其他材质可以查看已有贴图",
    randomRealmBlenderObjectLoaded: count => `已读取 ${count} 个物体`,
    randomRealmTextureUploaded: name => `新贴图已预览：${name}`,
    randomRealmTextureUploadedMany: (count, kinds) => `已导入 ${count} 张贴图：${kinds}`,
    randomRealmBlenderActionFailed: message => `处理失败：${message}`,
    randomRealmCodexObjectLabel: "当前物体",
    blenderPromptTitle: "Prompt 生成器",
    blenderPromptFormatLabel: "格式",
    blenderPromptFormatPlaceholder: "输出结构、语言、段落规则",
    blenderPromptImageLabel: "图片要求",
    blenderPromptImagePlaceholder: "参考图、构图、清晰度、背景、水印、材质要求",
    blenderPromptResolutionLabel: "分辨率",
    blenderPromptCustomResolutionPlaceholder: "自定义，例如 1536px / 4K / 2048x2048",
    blenderPromptCustomWidthPlaceholder: "宽度",
    blenderPromptCustomLengthPlaceholder: "长度",
    blenderPromptStyleLabel: "风格",
    blenderPromptStylePlaceholder: "例如：stylized realistic / low poly / hand-painted",
    blenderPromptBasicsLabel: "基础信息",
    blenderPromptBasicsPlaceholder: "项目用途、目标平台、比例、性能、限制",
    blenderPromptOutputLabel: "生成结果",
    blenderPromptGenerate: "生成 Prompt",
    blenderPromptCopy: "复制",
    blenderPromptClear: "清空",
    blenderPromptCopied: "Prompt 已复制",
    blenderPromptCleared: "Prompt 已清空",
    blenderPromptCopyFailed: "复制失败，请手动选中复制",
    randomRealmSlotsTitle: "随机领域区块",
    randomRealmSlotBuilder: "Builder / 建筑",
    randomRealmSlotGround: "Ground / 地面",
    randomRealmSlotAssets: "Assets / 材质",
    randomRealmSlotCommunity: "Community / 社群",
    randomRealmSlotBuilderBody: "建筑、部件、放置规则",
    randomRealmSlotGroundBody: "地面页面、场景层级",
    randomRealmSlotAssetsBody: "Blender、Textures、Unity",
    randomRealmSlotCommunityBody: "发展社群、发布节奏",
    activeProjectLabel: "项目",
    nextToolLabel: "下一工具",
    blenderExportTitle: "Blender 导出工具",
    reservedStatus: "已预留",
    sourceFolderLabel: "来源",
    targetFolderLabel: "目标",
    ruleLabel: "规则",
    pendingRule: "待配置",
    quickSlotsTitle: "快捷区",
    workspaceTodoLabel: "Todo",
    workspaceTodoTitle: "待办清单",
    workspaceTodoProgress: (done, total) => `${done}/${total}`,
    workspaceTodoPlaceholder: "写一个新的待办",
    workspaceTodoCategoryLabel: "待办分类",
    addWorkspaceTodo: "加入",
    resetWorkspaceTodo: "重置为新任务清单",
    githubDownloadsTitle: "GitHub 下载",
    githubDownloadsStatus: "待连接",
    githubDownloadsReady: "已定位",
    githubDownloadsMissing: "未连接",
    githubDownloadsResolving: "正在定位 GitHub Releases...",
    githubDownloadsBody: "打开 Codex World 的 GitHub Releases 下载页。",
    githubDownloadsLink: "Release 页面",
    openGithubDownloads: "打开下载页",
    githubDownloadsFound: url => `下载页：${url}`,
    githubDownloadsNotConfigured: "还没有连接 GitHub 仓库。给 Codex World 添加 origin 以后，这里会自动定位到 Releases。",
    githubDownloadsOpenFailed: message => `打开 GitHub 下载页失败：${message}`,
    consoleUpdateChecking: "正在检查",
    consoleUpdateLatest: "已是最新版",
    consoleUpdateAvailable: version => `可更新到 v${version}`,
    consoleUpdateNoRelease: "尚未找到发布版",
    consoleUpdateAuto: "自动",
    consoleUpdateRefresh: "检查更新",
    consoleUpdateInstall: "更新",
    consoleUpdateDownload: "下载",
    consoleUpdateInstallProduct: "安装",
    consoleUpdateOpen: "打开",
    consoleUpdateRelease: "Release",
    consoleUpdateTop: (name, version) => `更新 ${name} v${version}`,
    consoleUpdateTopCount: count => `${count} 项更新`,
    consoleUpdateNotInstalled: "尚未安装",
    consoleUpdateSource: "源码目录由 GitHub Desktop 管理",
    consoleUpdateInstalling: "正在下载安装程序",
    consoleUpdateRestarting: "安装向导已打开",
    consoleUpdateConfirm: version => `将打开安装向导，把 Codex Console 更新到 v${version}。现在继续？`,
    worldUpdateConfirm: (version, installed) => `将打开安装向导，${installed ? "更新" : "安装"} Codex World v${version}。现在继续？`,
    consoleUninstall: "卸载",
    consoleUninstallConfirm: name => `将卸载 ${name}，并永久删除它在这台电脑上的设置、缓存和本地资源。Blender 项目、GitHub 仓库和外部桌面布局不会被删除。继续？`,
    consoleUninstalling: "卸载程序已打开",
    consoleUninstallFailed: message => `无法打开卸载程序：${message}`,
    consoleUpdateFailed: message => `更新失败：${message}`,
    todoGroupPieces: "Pieces / 部件",
    todoGroupTextures: "Blend -> Unity 贴图",
    todoGroupStory: "Story / 故事",
    todoGroupLevel: "LevelMaker / LevelDesigner",
    todoGroupMiniGame: "MiniGame",
    todoGroupCommunity: "Community / 社群",
    todoPieceStairs: "楼梯 / Stairs",
    todoPieceKit: "整理可复用部件清单",
    todoTexturePipeline: "Downloads 材质先进 Blender，再进 Unity Textures",
    todoTextureFolder: "每套贴图用英文文件夹包装",
    todoStorySynopsis: "写故事简介 / 梗概",
    todoStoryBeats: "整理主线节点",
    todoLevelBlockout: "做关卡白盒和节奏",
    todoLevelDesigner: "整理 LevelDesigner 工作项",
    todoMiniGameSandbox: "保留自由实验位",
    todoCommunityDevelop: "发展社群",
    todoEmptyGroup: "这一组先空着",
    todoDeleteLabel: name => `删除 ${name}`,
    downloadIntakeLabel: "读取 Downloads",
    openDownloads: "打开 Downloads",
    downloadsOpened: "已打开 Downloads。",
    openDownloadsFailed: message => `打开 Downloads 失败：${message}`,
    scanDownloads: "扫描下载",
    importMaterial: "导入材质",
    renderTextureZoneTitle: "Render Textures",
    renderTextureZoneBody: "把导出的贴图、截图或 zip 拖到这里，会自动装进英文文件夹。",
    renderTextureReady: "等待拖入文件。",
    renderTextureDisabled: "先打开读取 Downloads。",
    renderTextureDragging: "松手后导入到 Texture 文件夹。",
    renderTextureImporting: count => `正在整理 ${count} 个文件。`,
    renderTextureImported: (folder, count) => `已导入 ${count} 个贴图：${folder}`,
    renderTextureFailed: message => `Workzone 导入失败：${message}`,
    latestMaterialLabel: "最新候选",
    noMaterialCandidate: "未发现",
    materialReady: "准备导入",
    materialEmpty: "下载文件夹里没有可导入的材质",
    materialCandidateTitle: name => `${name}\n点击选择，双击导入`,
    materialCandidateMeta: (type, size) => `${type === "package" ? "压缩包" : "贴图"} · ${size}`,
    materialLoadFailed: message => `扫描失败：${message}`,
    materialImporting: name => `正在导入：${name}`,
    materialImported: (name, count) => `已导入 ${name}，共 ${count} 个贴图。`,
    materialImportFailed: message => `导入失败：${message}`
  },
  en: {
    appTitle: "PC Console",
    managerPageTitle: "Manager",
    workspacePageTitle: "Console",
    blenderPageTitle: "Blender",
    unityPageTitle: "Unity",
    steamworkPageTitle: "Steamwork",
    randomRealmPageTitle: "RandomRealm",
    wallpaperPageTitle: "Wallpaper",
    managerNav: "Manager",
    managerSectionLabel: "Manager",
    workspaceNav: "Console",
    blenderNav: "Blender",
    unityNav: "Unity",
    steamworkNav: "Steamwork",
    randomRealmNav: "RandomRealm",
    musicPageTitle: "Music",
    wallpaperNav: "Wallpaper",
    musicNav: "Music",
    archiveToggleTitle: "Archive",
    archiveTitle: "Archive",
    archiveEmpty: "Nothing tucked away",
    archiveRestoreTitle: name => `Open ${name}, double-click to restore`,
    managerTitle: "Layout Manager",
    managerStatus: "Remembering",
    managerTabOrderLabel: "Tab order",
    managerArchiveLabel: "Archive",
    managerDesktopLayoutLabel: "Windows layout",
    managerDesktopLayoutValue: "Desktop icon snapshot is reserved",
    managerCurrentLayoutTitle: "Current Console Layout",
    managerLayoutSlotOne: "Current tab order",
    managerLayoutSlotTwo: "Archive bin",
    managerLayoutSlotThree: "Desktop snapshot",
    managerLayoutHint: "Drag tabs to reorder. Drop a tab on Archive to store it without deleting it.",
    tutorialModeToggle: "Tutorial Mode",
    tutorialModeOn: "Tutorial mode is on: showing guidance and helper actions",
    tutorialModeOff: "Tutorial mode is off: showing only key actions",
    consoleCommonTab: "Common",
    consoleCollaborationTab: "Collaboration",
    feedbackReviewTitle: "Received reports",
    desktopLayoutTitle: "Desktop Layout",
    desktopLayoutLocalOnly: "This device",
    desktopLayoutPlanLabel: "Desktop layout plan",
    desktopLayoutRememberedPlan: "Remembered current",
    desktopLayoutDevicePlan: "Current desktop",
    desktopLayoutRestore: "Restore",
    desktopLayoutSave: "Save current",
    desktopLayoutImport: "Import",
    desktopLayoutLoading: "Reading local plans",
    desktopLayoutEmpty: "No desktop layout plans yet",
    desktopLayoutMeta: (icons, plans) => `${icons} icons · ${plans} plans`,
    desktopLayoutReady: "Ready",
    desktopLayoutNotSaved: "Not saved yet",
    desktopLayoutInvalid: "Invalid JSON",
    desktopLayoutToolMissing: "Layout tool not found",
    desktopLayoutImporting: "Importing",
    desktopLayoutImported: count => `Imported ${count} plans`,
    desktopLayoutRestoring: "Restoring and checking",
    desktopLayoutRestored: "Restored; checks passed",
    desktopLayoutRestoreIssues: (missing, mismatches, overlaps) => `Restored · ${missing} missing · ${mismatches} shifted · ${overlaps} overlaps`,
    desktopLayoutSaving: "Backing up and saving",
    desktopLayoutSaved: "Backed up and saved",
    desktopLayoutFailed: message => `Desktop layout failed: ${message}`,
    desktopLayoutConfirmRestore: name => `Restore desktop icon positions from “${name}”?`,
    desktopLayoutConfirmSave: name => `Back up the JSON, then replace “${name}” with the current desktop?`,
    desktopLayoutGuide: "Restore checks overlaps, missing icons, and position drift. Save current always backs up the existing JSON first. Plans and backups are never uploaded.",
    feedbackTop: "Feedback",
    feedbackTitle: "Report a Problem",
    feedbackCategoryLabel: "Problem type",
    feedbackCategoryBug: "Bug",
    feedbackCategoryLayout: "Layout",
    feedbackCategoryMusic: "Music",
    feedbackCategoryUpdate: "Update",
    feedbackCategoryOther: "Other",
    feedbackDescriptionPlaceholder: "Describe the problem",
    feedbackScreenshot: "Screenshot",
    feedbackRemoveImage: "Remove screenshot",
    feedbackSend: "Send",
    feedbackQuota: limit => `${limit}/day`,
    feedbackConnecting: "Connecting",
    feedbackReady: "Ready to send",
    feedbackNotConfigured: "Feedback is not connected yet",
    feedbackSending: "Sending",
    feedbackSent: remaining => `Sent · ${remaining} left today`,
    feedbackFailed: message => `Could not send: ${message}`,
    feedbackDescriptionShort: "Please enter at least 10 characters.",
    feedbackImageTooLarge: "Screenshot must be 5 MB or smaller.",
    feedbackImageType: "Screenshot must be PNG, JPEG, or WebP.",
    feedbackImageReadFailed: "This screenshot could not be read.",
    feedbackInboxTitle: "Inbox",
    feedbackInboxRefresh: "Refresh inbox",
    feedbackInboxEmpty: "No new reports",
    feedbackInboxResolve: "Resolve",
    feedbackInboxResolved: "Resolved",
    feedbackOpenImage: "Screenshot",
    feedbackInboxMeta: (category, version, date) => `${category} · ${version || "--"} · ${date}`,
    feedbackAdminSetup: "Inbox connection",
    feedbackAdminEndpoint: "Cloudflare Worker URL",
    feedbackAdminToken: "Admin token",
    feedbackAdminSave: "Connect",
    feedbackAdminSaved: "Inbox connected",
    blenderSectionLabel: "Blender",
    blenderBuilderTab: "Builder",
    blenderHelperTab: "Helper",
    blenderHelperTitle: "Blender Hub",
    blenderHelperBadge: "Map",
    blenderHubReady: "Ready",
    blenderHubNext: "Next",
    blenderHubBuilderTitle: "Builder Workbench",
    blenderHubBuilderBody: "Textures, prompts, selected object",
    blenderHubBuildingTitle: "Building Projects",
    blenderHubBuildingBody: "Blocks, modules, placement rules",
    blenderHubCharacterTitle: "Character Lab",
    blenderHubCharacterBody: "Characters, outfits, material checks",
    blenderHubAnimationTitle: "Animation",
    blenderHubAnimationBody: "Actions, timeline, export rhythm",
    blenderHubTextureTitle: "Texture Lab",
    blenderHubTextureBody: "PBR, size checks, replacement packs",
    blenderHubBridgeTitle: "Unity Bridge",
    blenderHubBridgeBody: "Export, temp folder, import checks",
    blenderGithubHubTitle: "GitHub Coop",
    blenderGithubHubBody: "Blender project access",
    blenderGithubTitle: "GitHub Coop",
    blenderGithubToggleTitle: "Double-click to collapse or expand GitHub Coop",
    blenderGithubAddTitle: "Add a published Blender GitHub project",
    blenderGithubBlendFilesLabel: "GitHub repositories",
    blenderGithubLinksLabel: "Project links",
    blenderGithubDesktop: "GitHub Desktop",
    blenderGithubCloud: "Cloud",
    blenderGithubCardLocalTitle: name => `Click to select; double-click to open in GitHub Desktop: ${name}`,
    blenderGithubCardCloudTitle: name => `Click to select; double-click to clone with GitHub Desktop: ${name}`,
    blenderGithubDesktopOpenTitle: "Open the local repository in GitHub Desktop",
    blenderGithubDesktopCloneTitle: "Clone this repository with GitHub Desktop",
    blenderGithubGuide: "Not downloaded: double-click the card to Clone, then use + to select the .blend file. Fetch/Pull before editing; Commit + Push when finished.",
    blenderGithubStateCloud: "Cloud, not downloaded",
    blenderGithubFolder: "Files",
    blenderGithubOpenShort: "GitHub",
    blenderGithubNoBlendFiles: "No published GitHub repositories added",
    blenderGithubCardTitle: name => `Click to select; double-click to open GitHub: ${name}`,
    blenderGithubLoading: "Loading",
    blenderGithubReady: "Ready",
    blenderGithubProjectLabel: "GitHub Repository",
    blenderGithubRefreshTitle: "Refresh Git status",
    blenderGithubBlendFileLabel: "Blend File",
    blenderGithubBranchLabel: "Branch",
    blenderGithubRemoteLabel: "Remote",
    blenderGithubLastVersionLabel: "Last Version",
    blenderGithubRepositoryLabel: "GitHub Repository",
    blenderGithubRepositoryPlaceholder: "https://github.com/owner/repository.git",
    blenderGithubVisibilityLabel: "Visibility",
    blenderGithubPrivate: "Private",
    blenderGithubPublic: "Public",
    blenderGithubVersionLabel: "Version",
    blenderGithubMessageLabel: "Version Note",
    blenderGithubMessagePlaceholder: "What changed in this version",
    blenderGithubScopeLabel: "Share Range",
    blenderGithubScopeCurrent: "Current .blend",
    blenderGithubScopeProject: "Project Folder",
    blenderGithubScopeCustom: "Custom",
    blenderGithubIncludeLabel: "Include Patterns",
    blenderGithubExcludeLabel: "Exclude Patterns",
    blenderGithubChangesLabel: "Git Changes",
    blenderGithubInitialize: "Initialize Repository",
    blenderGithubCommit: "Commit Version",
    blenderGithubPush: "Push",
    blenderGithubOpen: "Open GitHub",
    blenderGithubStateUninitialized: "Not Initialized",
    blenderGithubStateInitialized: "Initialized",
    blenderGithubStateDirty: "Uncommitted Changes",
    blenderGithubStateCommitted: "Committed",
    blenderGithubStatePendingPush: "Pending Push",
    blenderGithubStateBehind: "Remote Updated",
    blenderGithubStateSynced: "Synced",
    blenderGithubStateGitUnavailable: "Git Unavailable",
    blenderGithubToolsReady: "Git · LFS ready",
    blenderGithubLfsMissing: "Git LFS is required",
    blenderGithubGhReady: "GitHub CLI signed in",
    blenderGithubGhFallback: "GitHub CLI is unavailable or signed out; paste an empty repository URL",
    blenderGithubWorkingTreeClean: "Working tree clean",
    blenderGithubMoreChanges: count => `${count} more change${count === 1 ? "" : "s"}`,
    blenderGithubLastCommit: (hash, subject) => `${hash} · ${subject}`,
    blenderGithubNoCommit: "No commits yet",
    blenderGithubSaving: "Saving project settings",
    blenderGithubSaved: "Project settings saved",
    blenderGithubInitializedReady: "Repository and Git LFS are ready",
    blenderGithubInitializedNoRemote: "Local repository is ready; add an empty GitHub repository URL before pushing",
    blenderGithubCommitComplete: version => `Version ${version} committed`,
    blenderGithubPushComplete: "Pushed to GitHub",
    blenderGithubOpenComplete: "GitHub repository opened",
    blenderGithubInitializing: "Initializing Git and Git LFS",
    blenderGithubCommitting: "Committing version",
    blenderGithubPushing: "Pushing to GitHub",
    blenderGithubOpening: "Opening GitHub repository",
    blenderGithubFailed: message => `Action failed: ${message}`,
    blenderGithubPublicConfirm: "A Public repository can be accessed by anyone. Switch to Public?",
    blenderGithubCreateConfirm: name => `No repository URL is set. Create ${name} with GitHub CLI?`,
    blenderGithubReplaceRemoteConfirm: "Origin points to another repository. Replace it?",
    blenderGithubSelectProject: "Select Blender project",
    blenderGithubAddingProject: "Selecting a GitHub project",
    blenderGithubProjectAdded: "GitHub repository added",
    blenderGithubOrderFailed: message => `Could not save order: ${message}`,
    unitySectionLabel: "Unity",
    unityControlTitle: "Unity Control",
    unityControlBody: "RandomRealm2 project entry points, promo assets, and Unity-side pre-release checks.",
    unityBridgeLabel: "Bridge",
    unityBridgeTempLabel: "Temp Import",
    unityBridgeReady: "Waiting for Blender",
    unityBridgeBody: "Blender exports into Unity temp; the RandomRealm importer consumes that temp output and categorizes it into Builder assets, prefabs, and inventory.",
    steamworkTitle: "Steamwork",
    steamworkReady: "Ready",
    steamworkBody: "Manage Steamworks, SteamPipe GUI, ContentBuilder/content, and promo/update assets.",
    steamworkDashboard: "Steamworks",
    steamworkPublishRoot: "ContentBuilder",
    steamworkGameContent: "Content",
    steamworkPublishTool: "SteamPipe GUI",
    steamworkArtAssets: "Assets",
    steamworkGameContentLabel: "Content",
    steamworkGameContentTitle: "Import game content",
    steamworkGameContentReady: "Drop game build files into ContentBuilder/content.",
    steamworkPublishToolLabel: "SteamPipe GUI",
    steamworkPublishToolTitle: "Import SteamPipe GUI tools",
    steamworkPublishToolReady: "Drop SteamPipeGUI.exe or related files here.",
    steamworkTipsLabel: "Publish Tips",
    steamworkStepsSection: "Steps",
    steamworkAppInfoSection: "App Info",
    steamworkStepColumn: "Step",
    steamworkActionColumn: "Action",
    steamworkNoteColumn: "Note",
    steamworkFieldColumn: "Field",
    steamworkValueColumn: "Value",
    steamworkStepBuild: "1. Build",
    steamworkStepUpload: "2. Upload",
    steamworkStepRenewDepot: "3. Renew Depot",
    steamworkStepPublish: "4. Publish",
    steamworkTipBuild: "Build the game first from Unity / PC.",
    steamworkBuildNote: "PC only.",
    steamworkTipConfig: "SteamPipe GUI fields: App ID 3983670, Depot ID 3983671, Build Description can use 1.5.31.",
    steamworkTipPaths: "Paths: Build Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\\content, ContentBuilder Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder.",
    steamworkTipLogin: "Steam Login = pixel_roblez. Do not store the password in Console.",
    steamworkTipContent: "Put the build output into ContentBuilder/content.",
    steamworkTipOpenPrefix: "Use ",
    steamworkTipPipe: "to fill fields and upload.",
    steamworkPublishToolLocate: "Locate .exe",
    steamworkPublishToolChoose: "Choose SteamPipeGUI.exe",
    steamworkPublishToolMissing: "SteamPipeGUI.exe was not found; locate / import that exe first.",
    steamworkUploadNote: "PC + Mobile confirmation.",
    steamworkBuildsLink: "Steamworks Builds",
    steamworkTipRenewDepot: "to set the uploaded build live.",
    steamworkRenewDepotNote: "PC + Mobile confirmation.",
    steamworkTipPublish: "Confirm and publish changes; Steam Guard / phone confirmation may be required.",
    steamworkPublishNote: "Pc only",
    steamworkPasswordNote: "(password not stored)",
    steamworkImportDragging: "Release to import.",
    steamworkImporting: (count, target) => `Importing ${count} file${count === 1 ? "" : "s"} to ${target}.`,
    steamworkImported: (count, target) => `Imported ${count} file${count === 1 ? "" : "s"} to ${target}.`,
    steamworkImportFailed: message => `Steamwork import failed: ${message}`,
    steamworkAssetsLabel: "Asset Log",
    steamworkAssetsTitle: "Steam asset checklist",
    steamworkAssetLoading: "Loading assets",
    steamworkAssetLoadFailed: message => `Asset load failed: ${message}`,
    steamworkAssetSummary: (ready, total, review, missing, optional, files) => `${ready}/${total} ready  ${review} review  ${missing} missing  ${optional} optional  ${files} files`,
    steamworkAssetSummaryReady: (ready, total) => `${ready}/${total} ready`,
    steamworkAssetSummaryReview: count => `${count} review`,
    steamworkAssetSummaryMissing: count => `${count} missing`,
    steamworkAssetSummaryOptional: count => `${count} optional`,
    steamworkAssetSummaryFiles: count => `${count} files`,
    steamworkAssetColumn: "Asset",
    steamworkStatusColumn: "Status",
    steamworkSpecColumn: "Spec",
    steamworkCurrentColumn: "Current",
    steamworkTargetColumn: "Where",
    steamworkAssetReady: "Ready",
    steamworkAssetReview: "Review",
    steamworkAssetMissing: "Missing",
    steamworkAssetOptional: "Optional",
    steamworkAssetRequired: "Required",
    steamworkAssetOptionalLabel: "Optional",
    steamworkAssetNoFile: "No matched file",
    steamworkAssetNeedSpec: spec => `Need: ${spec}`,
    steamworkAssetWhereToUse: target => `Where: ${target}`,
    steamworkAssetMissingAction: "Drop a matching file into Prepare replacement below.",
    steamworkAssetMissingGuideTitle: "Add file",
    steamworkAssetMissingGuideSpec: spec => `Spec ${spec}`,
    steamworkAssetMissingGuideDrop: "Drop into Prepare replacement",
    steamworkAssetMissingGuideTarget: target => `Steam target ${target}`,
    steamworkAssetOptionalGuideTitle: "Optional asset",
    steamworkAssetOptionalGuideNote: "Does not block publish",
    steamworkAssetOptionalGuideSpec: spec => `Suggested ${spec}`,
    steamworkAssetOptionalGuideTarget: target => `Steam target ${target}`,
    steamworkAssetFitOk: "Spec OK",
    steamworkAssetFitFormat: "Format mismatch",
    steamworkAssetFitSize: "Size mismatch",
    steamworkAssetFitFormatSize: "Format / size mismatch",
    steamworkAssetFitType: "Type mismatch",
    steamworkAssetFitCheck: "Check",
    steamworkAssetOpen: "Open",
    steamworkAssetOpenFailed: message => `Open asset failed: ${message}`,
    steamworkAssetSource: root => `Asset root: ${root}`,
    steamworkAssetMatched: "Current match",
    steamworkAssetCandidates: "Asset candidates",
    steamworkAssetReferenceCandidates: "Reference candidates",
    steamworkAssetReferenceHint: "No strict match; these files are for reference.",
    steamworkAssetOptionalCandidates: "Reference assets",
    steamworkAssetOptionalReferenceHint: "Optional item; these related files are for reference.",
    steamworkAssetStageTitle: "Prepare replacement",
    steamworkAssetStageHint: "Drop new assets here to stage them into D:\\ArtAsset.",
    steamworkAssetStageDragging: "Release to stage into the asset library",
    steamworkAssetStaging: (count, slot) => `Staging ${count} file${count === 1 ? "" : "s"} for ${slot}.`,
    steamworkAssetStaged: (count, folder) => `Staged ${count} file${count === 1 ? "" : "s"} to ${folder}.`,
    steamworkAssetStageFailed: message => `Asset staging failed: ${message}`,
    steamworkAssetFileCount: count => `${count} file${count === 1 ? "" : "s"}`,
    steamworkAssetFolderStore: "Store Assets",
    steamworkAssetFolderScreenshots: "Screenshots",
    steamworkAssetFolderVideo: "Video",
    steamworkAssetFolderStaged: "Staged",
    steamworkIssueMissingRequired: "Missing required asset",
    steamworkIssueOptional: "Optional",
    steamworkIssueNeedFiles: count => `Need ${count} file${count === 1 ? "" : "s"}`,
    steamworkIssueCheckFile: "File found, check size/format",
    steamworkAttentionTitle: "Needs attention",
    steamworkAttentionCount: count => `${count} item${count === 1 ? "" : "s"}`,
    steamworkAttentionHint: "Click to jump to the asset",
    steamworkAttentionFixMissing: "Add file",
    steamworkAttentionReview: "Review",
    steamworkAssetNoCandidates: "No relevant candidates",
    steamworkAssetShowCandidates: count => `Show ${count} candidate${count === 1 ? "" : "s"}`,
    steamworkAssetMoreCandidates: count => `${count} more candidate${count === 1 ? "" : "s"}`,
    steamworkAssetShowFiles: count => `Show ${count} file${count === 1 ? "" : "s"}`,
    steamworkAssetMoreFiles: count => `${count} more file${count === 1 ? "" : "s"}`,
    steamworkAssetExpand: "Expand",
    steamworkCategoryStore: "Store",
    steamworkCategoryLibrary: "Library",
    steamworkCategoryCommunity: "Community",
    steamworkCategoryVideo: "Video",
    steamworkCategoryMissing: count => `${count} missing`,
    steamworkCategoryReview: count => `${count} review`,
    steamworkCategoryOptional: count => `${count} optional`,
    steamworkTargetGraphicalAssets: "Store Page Admin > Graphical Assets",
    steamworkTargetScreenshots: "Store Page Admin > Screenshots",
    steamworkTargetCommunityIcons: "Store Page Admin > Community & Client Icons",
    steamworkTargetLibraryAssets: "Steamworks > Edit Library Assets",
    steamworkTargetTrailers: "Store Page Admin > Trailers",
    activeProjectValue: "RandomRealm / Blender Assets",
    timeLabel: "Time",
    wallpaperSectionLabel: "Preview",
    wallpaperTitle: "Preview",
    add: "+ Add",
    emptyTitle: "No wallpaper selected",
    emptyBody: "Supports jpg, png, bmp, and webp.",
    selectedLabel: "Selected",
    sizeLabel: "Size",
    themeDark: "Dark",
    themeLight: "Light",
    readyStatus: "Ready",
    candidatesSectionLabel: "Library",
    candidatesTitle: "Candidates",
    notSelected: "Not selected",
    noSize: "--",
    count: count => `${count} images`,
    noCandidates: "No candidates",
    addHint: "Supports jpg / png / bmp / webp.",
    cardTitle: name => `${name}\nClick to select, double-click to apply`,
    deleteButtonLabel: name => `Delete ${name}`,
    deletePrompt: "Delete?",
    confirmDeleteAction: "Delete",
    cancelDeleteAction: "Cancel",
    added: count => `Added ${count} wallpaper${count === 1 ? "" : "s"}.`,
    applied: name => `Applied: ${name}`,
    deleted: name => `Deleted: ${name}`,
    loadFailed: message => `Could not read wallpapers: ${message}`,
    uploadFailed: message => `Add failed: ${message}`,
    applyFailed: message => `Apply failed: ${message}`,
    deleteFailed: message => `Delete failed: ${message}`,
    musicTitle: "Music Player",
    nowPlayingLabel: "Now playing",
    musicEmptyBody: "Add mp3, wav, m4a, flac, ogg, or opus.",
    lyricsSectionLabel: "Lyrics",
    lyricsTitle: "Lyrics",
    lyricsHide: "Collapse",
    lyricsShow: "Show lyrics",
    lyricsEmpty: "No lyrics file for this track.",
    lyricsLoading: "Loading lyrics.",
    lyricsInstrumental: "No displayable lyrics.",
    lyricsUnsynced: "Lyrics have no timeline; showing full text.",
    lyricsLoadFailed: message => `Lyrics failed: ${message}`,
    lyricsButtonLabel: name => `Lyrics: ${name}`,
    lyricsFindLabel: name => `Find lyrics: ${name}`,
    lyricsSeekLabel: line => `Jump to lyric: ${line}`,
    lyricsMarkArmed: "Selected; enter start/end timing",
    lyricsMarkSaved: time => `Marked ${time}`,
    lyricsEndMarkSaved: time => `End pinned at ${time}`,
    lyricsStartMarkSaved: time => `Start pinned at ${time}`,
    lyricsMarkCancelled: "Undid this session mark",
    lyricsMarkFailed: message => `Mark failed: ${message}`,
    lyricsTimingPick: "Triple right-click the same lyric line to open timing editor (WIP).",
    lyricsTimingClose: "Close timing editor",
    lyricsTimingStartLabel: "Starts turning white",
    lyricsTimingEndLabel: "Fully white by",
    lyricsTimingTimePlaceholder: "m:ss.mmm",
    lyricsTimingUseNowStart: "Use now as start",
    lyricsTimingUseNowEnd: "Use now as end",
    lyricsTimingSave: "Save",
    lyricsTimingClear: "Undo this change",
    lyricsTimingTarget: (word, line) => `Editing: ${word || "this slot"} · line ${line}`,
    lyricsTimingLineTitle: (line, count) => `Line ${line} · ${count} words/chars`,
    lyricsTimingPreviewLabel: "Line preview",
    lyricsTimingRowsLabel: "Word timing",
    lyricsTimingTokenHeader: "Word",
    lyricsTimingStartHeader: "Start",
    lyricsTimingEndHeader: "End",
    lyricsTimingDurationHeader: "Duration",
    lyricsTimingDetailTitle: word => `Fine tune: ${word || "this slot"}`,
    lyricsTimingRangeTitle: (start, end) => start === end ? `Fine tune: ${start}` : `Fine tune: ${start} to ${end}`,
    lyricsTimingWaveLabel: "Waveform",
    lyricsTimingSelectLine: "Select line",
    lyricsTimingRangeDuration: duration => `Range ${duration}`,
    lyricsTimingSaveSelected: "Save selected",
    lyricsTimingSaveLine: "Save line",
    lyricsTimingClearLine: "Undo line",
    lyricsTimingSaved: (start, end) => `Staged: ${start} to ${end}`,
    lyricsTimingRangeSaved: count => `Staged ${count} selected word${count === 1 ? "" : "s"}`,
    lyricsTimingLineSaved: count => `Staged ${count} word${count === 1 ? "" : "s"}`,
    lyricsTimingCleared: "Undid this word timing change",
    lyricsTimingLineCleared: "Undid this line timing change",
    lyricsTimingLineEmpty: "No complete timings in this line yet",
    lyricsTimingIncomplete: "Start and end are both required",
    lyricsTimingInvalid: "Use 1:23.450 or 83.45",
    lyricsTimingRangeInvalid: "End time must be after start time",
    lyricsTimingOrderInvalid: "A later word cannot overlap the previous word",
    lyricsTimingOrderCorrected: count => `Corrected ${count} word${count === 1 ? "" : "s"} into order`,
    lyricsTimingWordMoved: word => `Moved ${word}`,
    lyricsTimingHoldLabel: "Hold",
    lyricsTimingHoldHint: "Alt-drag keeps empty gaps; gaps do not advance the lyric.",
    lyricsTimingHoldInserted: "Added hold",
    lyricsTimingHoldRemoved: "Removed hold",
    lyricsTimingHoldInsertedBetween: (previous, next) => `Added hold between ${previous} / ${next}`,
    lyricsTimingHoldRemovedBetween: (previous, next) => `Removed hold between ${previous} / ${next}`,
    lyricsTimingHoldTooShort: "Not enough room here",
    lyricsNotFound: name => `No lyrics found: ${name}`,
    lyricsSearchFailed: message => `Lyrics search failed: ${message}`,
    previousTrack: "Previous track",
    playTrack: "Play",
    pauseTrack: "Pause",
    nextTrack: "Next track",
    playbackModeSequential: "Order",
    playbackModeRepeatAll: "Loop",
    playbackModeRepeatOne: "Single",
    playbackModePlayOnce: "Once",
    playbackModeTitle: label => `Playback mode: ${label}`,
    volumeLabel: "Volume",
    musicListTitle: "Local Music",
    musicNotSelected: "Not selected",
    trackCount: count => `${count} track${count === 1 ? "" : "s"}`,
    noTracks: "No music yet",
    musicLocalEmpty: "Drag from Library",
    musicLocalDropActive: "Drop to add locally",
    musicTierFirst: "1st",
    musicTierSecond: "2nd",
    musicTierThird: "3rd",
    musicTierDropHint: "Drop here to grade",
    musicAddHint: "Supports mp3 / wav / m4a / flac / ogg / opus.",
    musicAddDropTitle: "Add music",
    musicAddDropBody: "Paste URL",
    musicPickLocal: "Local file",
    musicAddMenuQuestion: "Add music",
    musicAddViaUrl: "YouTube Link",
    musicAddViaFile: "MP3 File",
    musicAddViaLibrary: "Playlist / Other",
    musicPlaylistPlaceholder: "Playlist URL",
    musicLinkPlaceholder: "YouTube URL",
    musicLinkDownload: "Download",
    musicUseBrowserCookies: "Use Edge login",
    musicCookieFile: "cookies.txt",
    musicCookieReady: "cookies OK",
    musicCookieUploaded: "YouTube cookies.txt imported.",
    musicCookieUploadFailed: message => `Cookie import failed: ${message}`,
    musicLibraryTitle: "Library",
    musicLibraryDropTitle: "Add playlist",
    musicLibraryDropBody: "Drop a YouTube playlist.",
    musicLibraryReady: "Waiting for a playlist link.",
    musicLibraryEmpty: "No library tracks yet",
    musicLibraryImporting: provider => `Preparing ${provider} playlist.`,
    musicLibraryStarted: name => `Started grabbing: ${name}`,
    musicLibraryFailed: message => `Library import failed: ${message}`,
    musicLibraryStatusQueued: "Queued",
    musicLibraryStatusGrabbing: "Grabbing",
    musicLibraryStatusReady: "Ready",
    musicLibraryStatusFailed: "Failed",
    musicLibraryMeta: (count, expected) => expected ? `${count}/${expected} tracks` : `${count} tracks`,
    trackTitle: name => `${name}\nClick to play, right-click for delete`,
    deleteTrackLabel: name => `Delete ${name}`,
    trackMeta: (type, size) => `${type.toUpperCase()} · ${size}`,
    musicAdded: count => `Added ${count} track${count === 1 ? "" : "s"}.`,
    musicLyricsAdded: count => `Added ${count} lyric file${count === 1 ? "" : "s"}.`,
    musicDeleted: name => `Deleted: ${name}`,
    musicLoadFailed: message => `Could not read music: ${message}`,
    musicUploadFailed: message => `Add music failed: ${message}`,
    musicPlayFailed: message => `Playback failed: ${message}`,
    musicLinkEmpty: "No URL was found.",
    musicLinkChecking: provider => `Downloading: ${provider}`,
    musicLinkPrepared: provider => `Ready: ${provider}`,
    musicLinkImported: name => `Done: ${name}`,
    musicPromoted: name => `Added locally: ${name}`,
    musicPromoteFailed: message => `Local add failed: ${message}`,
    musicLinkFailed: message => `Link import failed: ${message}`,
    workspaceTitle: "Current Work",
    workspaceStatus: "Preparing",
    randomRealmSectionLabel: "RandomRealm",
    randomRealmTitle: "RandomRealm Manager",
    randomRealmStatus: "Active",
    randomRealmProjectLabel: "Project",
    randomRealmUnityLabel: "Unity Project",
    randomRealmBuilderLabel: "Builder System",
    randomRealmGroundLabel: "Ground Page",
    randomRealmPipelineLabel: "Asset Pipeline",
    randomRealmCommunityLabel: "Community",
    randomRealmSurfaceTitle: "Ground and Scene",
    randomRealmSurfaceStatus: "Reserved",
    randomRealmSurfaceBody: "Reserved for ground pages, building placement, scene checks, and export actions.",
    randomRealmReleaseTitle: "Release Control",
    randomRealmReleaseBody: "Steamworks, publish builds, promo assets, and project entry points.",
    randomRealmOpenReady: "Ready",
    randomRealmSteamworks: "Steamworks",
    randomRealmPublishFolder: "Publish Folder",
    randomRealmProjectFolder: "Unity Project",
    randomRealmPromoFolder: "Promo Assets",
    randomRealmOpening: name => `Opening: ${name}`,
    randomRealmOpened: name => `Opened: ${name}`,
    randomRealmOpenFailed: message => `Open failed: ${message}`,
    randomRealmArtTitle: "Art Supporter",
    randomRealmBlenderProjectLabel: "Blender Project",
    randomRealmProjectSearchLabel: "Project Search",
    randomRealmProjectSearchPlaceholder: "Search by project name or path",
    randomRealmArtTypeLabel: "Object Type",
    randomRealmObjectSearchPlaceholder: "Search objects",
    randomRealmSyncLiveSelection: "Sync selected",
    randomRealmLiveSynced: name => `Synced Blender selection: ${name}`,
    randomRealmLiveUnavailable: "No live Blender selection detected",
    randomRealmLiveProjectMismatch: "The open Blender file is not this project",
    randomRealmLiveObjectMissing: name => `Selected Blender object is not in this list: ${name}`,
    randomRealmUsedTexturesLabel: "Used Textures",
    randomRealmTextureManagerTitle: "Texture Manager",
    randomRealmTextureManagerCount: (visible, total) => `${visible}/${total}`,
    randomRealmTextureInspectorLabel: "Selected Texture",
    randomRealmTextureDetailMaterial: "Material",
    randomRealmTextureDetailRole: "Role",
    randomRealmTextureDetailNode: "Node",
    randomRealmTextureDetailState: "State",
    randomRealmTextureDetailFile: "File",
    randomRealmTextureDetailPath: "Path",
    randomRealmTextureStateReady: "Ready",
    randomRealmTextureStateMissing: "Missing",
    randomRealmTextureStatePending: "Pending",
    randomRealmTexturesRefreshed: (name, count) => `Refreshed ${name}: ${count} texture${count === 1 ? "" : "s"}`,
    randomRealmAllMaterials: "All",
    randomRealmOldTextureLabel: "Old",
    randomRealmNewTextureLabel: "New",
    randomRealmTextureNotSelected: "Not selected",
    randomRealmNewTextureSlot: "New map slot",
    randomRealmDropNewTexture: "Drop texture or PBR set here",
    randomRealmTexturePreviewEmpty: "No preview",
    randomRealmTexturePreviewUnsupported: "Preview unavailable",
    randomRealmTextureDragHint: "Double-click to open the source file. Dragging will try to send a real file. Path: ",
    randomRealmNativeDragStarted: "Starting Windows native file drag",
    randomRealmTextureOpened: (name, app) => `Opened texture: ${name}${app ? ` (${app})` : ""}`,
    randomRealmTextureOpenFailed: message => `Open texture failed: ${message}`,
    randomRealmTexturePacked: (name, location) => `Packed into ${location || "textures"}: ${name}`,
    randomRealmTexturePackedMany: (count, location) => `Packed ${count} texture package${count === 1 ? "" : "s"} into ${location || "textures"}.`,
    randomRealmTextureAutoPackedMany: (count, location) => `Auto-packed ${count} texture package${count === 1 ? "" : "s"} into ${location || "textures"}. New clears after Blender Apply.`,
    randomRealmTextureAppliedCleared: count => `Blender Apply completed. Cleared ${count} New texture${count === 1 ? "" : "s"}.`,
    randomRealmStageBlankTexture: "+ Map",
    randomRealmBlankTextureStaged: name => `Staged blank texture slot: ${name}`,
    randomRealmTextureStagedRemoved: name => `Removed staged texture: ${name}`,
    randomRealmTextureRemovalPackaged: (name, packageName) => `Packaged remove request: ${name}${packageName ? ` (${packageName})` : ""}`,
    randomRealmTexturePackReady: "Drop a new texture to auto-stage it in Blender textures. Blender is not modified until Apply.",
    randomRealmTextureDimensionsUnknown: "Unknown size",
    randomRealmTextureDimensionCancelled: "Cancelled: texture dimensions were not approved",
    randomRealmTextureSizeMismatchConfirm: (oldSize, newSize) => `Texture sizes do not match.\n\nOld: ${oldSize}\nNew: ${newSize}\n\nAuto-stage anyway?`,
    randomRealmTextureSizeUnknownConfirm: (oldSize, newSize) => `A texture size could not be checked.\n\nOld: ${oldSize}\nNew: ${newSize}\n\nAuto-stage anyway?`,
    randomRealmArtReady: "Ready",
    randomRealmBlenderLoading: "Reading Blender project",
    randomRealmBlenderProjectLoaded: count => `Found ${count} Blender project${count === 1 ? "" : "s"}`,
    randomRealmBlenderNoProject: "No Blender project found",
    randomRealmBlenderNoObject: "No objects found",
    randomRealmBlenderNoTexture: "This object has no image texture",
    randomRealmMaterialNoTexture: "This material has no image texture",
    randomRealmMaterialNoTextureHint: "Switch to All or another material to view existing textures",
    randomRealmBlenderObjectLoaded: count => `Loaded ${count} objects`,
    randomRealmTextureUploaded: name => `New texture staged: ${name}`,
    randomRealmTextureUploadedMany: (count, kinds) => `Imported ${count} textures: ${kinds}`,
    randomRealmBlenderActionFailed: message => `Action failed: ${message}`,
    randomRealmCodexObjectLabel: "Current Object",
    blenderPromptTitle: "Prompt Builder",
    blenderPromptFormatLabel: "Format",
    blenderPromptFormatPlaceholder: "Output structure, language, and section rules",
    blenderPromptImageLabel: "Image Requirements",
    blenderPromptImagePlaceholder: "Reference image, framing, clarity, background, watermark, material requirements",
    blenderPromptResolutionLabel: "Resolution",
    blenderPromptCustomResolutionPlaceholder: "Custom, e.g. 1536px / 4K / 2048x2048",
    blenderPromptCustomWidthPlaceholder: "Width",
    blenderPromptCustomLengthPlaceholder: "Length",
    blenderPromptStyleLabel: "Style",
    blenderPromptStylePlaceholder: "Stylized realistic / low poly / hand-painted...",
    blenderPromptBasicsLabel: "Base Info",
    blenderPromptBasicsPlaceholder: "Project use, target platform, scale, performance, constraints Codex should remember",
    blenderPromptOutputLabel: "Generated Prompt",
    blenderPromptGenerate: "Generate Prompt",
    blenderPromptCopy: "Copy",
    blenderPromptClear: "Clear",
    blenderPromptCopied: "Prompt copied",
    blenderPromptCleared: "Prompt cleared",
    blenderPromptCopyFailed: "Copy failed; select and copy manually",
    randomRealmSlotsTitle: "Project Areas",
    randomRealmSlotBuilder: "Builder / Buildings",
    randomRealmSlotGround: "Ground / Scene",
    randomRealmSlotAssets: "Assets / Materials",
    randomRealmSlotCommunity: "Community",
    randomRealmSlotBuilderBody: "Buildings, pieces, placement rules",
    randomRealmSlotGroundBody: "Ground pages and scene hierarchy",
    randomRealmSlotAssetsBody: "Blender, Textures, Unity",
    randomRealmSlotCommunityBody: "Community growth and release rhythm",
    activeProjectLabel: "Project",
    nextToolLabel: "Next Tool",
    blenderExportTitle: "Blender Export Tool",
    reservedStatus: "Reserved",
    sourceFolderLabel: "Source",
    targetFolderLabel: "Target",
    ruleLabel: "Rule",
    pendingRule: "Pending",
    quickSlotsTitle: "Quick Slots",
    workspaceTodoLabel: "Todo",
    workspaceTodoTitle: "To-Do List",
    workspaceTodoProgress: (done, total) => `${done}/${total}`,
    workspaceTodoPlaceholder: "Add a task",
    workspaceTodoCategoryLabel: "Todo category",
    addWorkspaceTodo: "Add",
    resetWorkspaceTodo: "Reset new task set",
    githubDownloadsTitle: "GitHub Downloads",
    githubDownloadsStatus: "Not linked",
    githubDownloadsReady: "Ready",
    githubDownloadsMissing: "Not linked",
    githubDownloadsResolving: "Finding GitHub Releases...",
    githubDownloadsBody: "Open the Codex World GitHub Releases download page.",
    githubDownloadsLink: "Release page",
    openGithubDownloads: "Open downloads",
    githubDownloadsFound: url => `Downloads: ${url}`,
    githubDownloadsNotConfigured: "No GitHub repository is linked yet. Add an origin remote to Codex World and this shortcut will target Releases automatically.",
    githubDownloadsOpenFailed: message => `Could not open GitHub downloads: ${message}`,
    consoleUpdateChecking: "Checking",
    consoleUpdateLatest: "Up to date",
    consoleUpdateAvailable: version => `v${version} available`,
    consoleUpdateNoRelease: "No release found",
    consoleUpdateAuto: "Auto",
    consoleUpdateRefresh: "Check for updates",
    consoleUpdateInstall: "Update",
    consoleUpdateDownload: "Download",
    consoleUpdateInstallProduct: "Install",
    consoleUpdateOpen: "Open",
    consoleUpdateRelease: "Release",
    consoleUpdateTop: (name, version) => `Update ${name} v${version}`,
    consoleUpdateTopCount: count => `${count} updates`,
    consoleUpdateNotInstalled: "Not installed",
    consoleUpdateSource: "Source checkout is managed through GitHub Desktop",
    consoleUpdateInstalling: "Downloading installer",
    consoleUpdateRestarting: "Setup is open",
    consoleUpdateConfirm: version => `Setup will open to update Codex Console to v${version}. Continue?`,
    worldUpdateConfirm: (version, installed) => `Setup will open to ${installed ? "update" : "install"} Codex World v${version}. Continue?`,
    consoleUninstall: "Uninstall",
    consoleUninstallConfirm: name => `Uninstall ${name} and permanently remove its settings, cache, and local resources from this PC? Blender projects, GitHub repositories, and external desktop layouts will not be removed.`,
    consoleUninstalling: "Uninstaller opened",
    consoleUninstallFailed: message => `Could not open uninstaller: ${message}`,
    consoleUpdateFailed: message => `Update failed: ${message}`,
    todoGroupPieces: "Pieces",
    todoGroupTextures: "Blend -> Unity Textures",
    todoGroupStory: "Story",
    todoGroupLevel: "LevelMaker / LevelDesigner",
    todoGroupMiniGame: "MiniGame",
    todoGroupCommunity: "Community",
    todoPieceStairs: "Stairs",
    todoPieceKit: "Build a reusable piece checklist",
    todoTexturePipeline: "Send Downloads materials through Blender, then Unity Textures",
    todoTextureFolder: "Wrap each texture set in an English folder",
    todoStorySynopsis: "Write the story intro / synopsis",
    todoStoryBeats: "Collect the main story beats",
    todoLevelBlockout: "Make level blockouts and pacing",
    todoLevelDesigner: "Organize LevelDesigner work items",
    todoMiniGameSandbox: "Keep a free experiment slot",
    todoCommunityDevelop: "Grow the community",
    todoEmptyGroup: "Nothing here yet",
    todoDeleteLabel: name => `Delete ${name}`,
    downloadIntakeLabel: "Read Downloads",
    openDownloads: "Open Downloads",
    downloadsOpened: "Downloads opened.",
    openDownloadsFailed: message => `Could not open Downloads: ${message}`,
    scanDownloads: "Scan Downloads",
    importMaterial: "Import Material",
    renderTextureZoneTitle: "Render Textures",
    renderTextureZoneBody: "Drop exported textures, screenshots, or zip files here. They will be wrapped in an English folder.",
    renderTextureReady: "Waiting for files.",
    renderTextureDisabled: "Turn on Read Downloads first.",
    renderTextureDragging: "Release to import into the Texture folder.",
    renderTextureImporting: count => `Arranging ${count} file${count === 1 ? "" : "s"}.`,
    renderTextureImported: (folder, count) => `Imported ${count} texture${count === 1 ? "" : "s"}: ${folder}`,
    renderTextureFailed: message => `Workzone import failed: ${message}`,
    latestMaterialLabel: "Latest Candidate",
    noMaterialCandidate: "Not found",
    materialReady: "Ready to import",
    materialEmpty: "No importable materials in Downloads",
    materialCandidateTitle: name => `${name}\nClick to select, double-click to import`,
    materialCandidateMeta: (type, size) => `${type === "package" ? "Package" : "Texture"} · ${size}`,
    materialLoadFailed: message => `Scan failed: ${message}`,
    materialImporting: name => `Importing: ${name}`,
    materialImported: (name, count) => `Imported ${name}, ${count} texture${count === 1 ? "" : "s"}.`,
    materialImportFailed: message => `Import failed: ${message}`
  }
};

const defaultWorkspaceTodoGroups = [
  {
    id: "pieces",
    labelKey: "todoGroupPieces",
    items: [
      { id: "pieces-stairs", textKey: "todoPieceStairs", done: false },
      { id: "pieces-kit", textKey: "todoPieceKit", done: false }
    ]
  },
  {
    id: "textures",
    labelKey: "todoGroupTextures",
    items: [
      { id: "textures-pipeline", textKey: "todoTexturePipeline", done: false },
      { id: "textures-folder", textKey: "todoTextureFolder", done: false }
    ]
  },
  {
    id: "story",
    labelKey: "todoGroupStory",
    items: [
      { id: "story-synopsis", textKey: "todoStorySynopsis", done: false },
      { id: "story-beats", textKey: "todoStoryBeats", done: false }
    ]
  },
  {
    id: "level",
    labelKey: "todoGroupLevel",
    items: [
      { id: "level-blockout", textKey: "todoLevelBlockout", done: false },
      { id: "level-designer", textKey: "todoLevelDesigner", done: false }
    ]
  },
  {
    id: "minigame",
    labelKey: "todoGroupMiniGame",
    items: [
      { id: "minigame-sandbox", textKey: "todoMiniGameSandbox", done: false }
    ]
  },
  {
    id: "community",
    labelKey: "todoGroupCommunity",
    items: [
      { id: "community-develop", textKey: "todoCommunityDevelop", done: false }
    ]
  }
];

const els = {
  moduleTitle: document.getElementById("moduleTitle"),
  moduleArchive: document.getElementById("moduleArchive"),
  moduleArchiveDrop: document.getElementById("moduleArchiveDrop"),
  moduleArchiveCount: document.getElementById("moduleArchiveCount"),
  moduleArchiveList: document.getElementById("moduleArchiveList"),
  managerVisibleTabs: document.getElementById("managerVisibleTabs"),
  managerArchivedTabs: document.getElementById("managerArchivedTabs"),
  managerLayoutOrder: document.getElementById("managerLayoutOrder"),
  tutorialModeToggle: document.getElementById("tutorialModeToggle"),
  feedbackTop: document.getElementById("feedbackTop"),
  feedbackPanel: document.getElementById("feedbackPanel"),
  feedbackReviewPanel: document.getElementById("feedbackReviewPanel"),
  feedbackForm: document.getElementById("feedbackForm"),
  feedbackCategory: document.getElementById("feedbackCategory"),
  feedbackDescription: document.getElementById("feedbackDescription"),
  feedbackScreenshotButton: document.getElementById("feedbackScreenshotButton"),
  feedbackScreenshotInput: document.getElementById("feedbackScreenshotInput"),
  feedbackScreenshotName: document.getElementById("feedbackScreenshotName"),
  feedbackSubmit: document.getElementById("feedbackSubmit"),
  feedbackPreview: document.getElementById("feedbackPreview"),
  feedbackPreviewImage: document.getElementById("feedbackPreviewImage"),
  feedbackRemoveImage: document.getElementById("feedbackRemoveImage"),
  feedbackTurnstile: document.getElementById("feedbackTurnstile"),
  feedbackQuota: document.getElementById("feedbackQuota"),
  feedbackStatus: document.getElementById("feedbackStatus"),
  feedbackInbox: document.getElementById("feedbackInbox"),
  feedbackInboxCount: document.getElementById("feedbackInboxCount"),
  feedbackInboxRefresh: document.getElementById("feedbackInboxRefresh"),
  feedbackInboxList: document.getElementById("feedbackInboxList"),
  feedbackAdminSetup: document.getElementById("feedbackAdminSetup"),
  feedbackAdminForm: document.getElementById("feedbackAdminForm"),
  feedbackAdminEndpoint: document.getElementById("feedbackAdminEndpoint"),
  feedbackAdminToken: document.getElementById("feedbackAdminToken"),
  desktopLayoutPlan: document.getElementById("desktopLayoutPlan"),
  desktopLayoutRestore: document.getElementById("desktopLayoutRestore"),
  desktopLayoutSave: document.getElementById("desktopLayoutSave"),
  desktopLayoutImport: document.getElementById("desktopLayoutImport"),
  desktopLayoutFileInput: document.getElementById("desktopLayoutFileInput"),
  desktopLayoutMeta: document.getElementById("desktopLayoutMeta"),
  desktopLayoutStatus: document.getElementById("desktopLayoutStatus"),
  desktopLayoutPath: document.getElementById("desktopLayoutPath"),
  localTime: document.getElementById("localTime"),
  languageToggle: document.getElementById("languageToggle"),
  themeToggle: document.getElementById("themeToggle"),
  wallpaperPreview: document.getElementById("wallpaperPreview"),
  selectedWallpaperName: document.getElementById("selectedWallpaperName"),
  selectedWallpaperSize: document.getElementById("selectedWallpaperSize"),
  statusText: document.getElementById("statusText"),
  addWallpaper: document.getElementById("addWallpaper"),
  wallpaperFileInput: document.getElementById("wallpaperFileInput"),
  wallpaperDock: document.getElementById("wallpaperDock"),
  wallpaperCount: document.getElementById("wallpaperCount"),
  musicFileInput: document.getElementById("musicFileInput"),
  musicCookieFileInput: document.getElementById("musicCookieFileInput"),
  audioPlayer: document.getElementById("audioPlayer"),
  addMusic: document.getElementById("addMusic"),
  musicAddMenu: document.getElementById("musicAddMenu"),
  addMusicByUrl: document.getElementById("addMusicByUrl"),
  addMusicByFile: document.getElementById("addMusicByFile"),
  addMusicByLibrary: document.getElementById("addMusicByLibrary"),
  musicAddUrlForm: document.getElementById("musicAddUrlForm"),
  musicAddUrlInput: document.getElementById("musicAddUrlInput"),
  musicAddLibraryForm: document.getElementById("musicAddLibraryForm"),
  musicAddLibraryInput: document.getElementById("musicAddLibraryInput"),
  musicAddStatus: document.getElementById("musicAddStatus"),
  musicAddCookieButton: document.getElementById("musicAddCookieButton"),
  currentTrackName: document.getElementById("currentTrackName"),
  currentTrackMeta: document.getElementById("currentTrackMeta"),
  previousTrack: document.getElementById("previousTrack"),
  playPauseTrack: document.getElementById("playPauseTrack"),
  nextTrack: document.getElementById("nextTrack"),
  playbackModeToggle: document.getElementById("playbackModeToggle"),
  trackCurrentTime: document.getElementById("trackCurrentTime"),
  trackSeek: document.getElementById("trackSeek"),
  trackSeekArea: document.querySelector(".music-progress"),
  trackDuration: document.getElementById("trackDuration"),
  trackVolume: document.getElementById("trackVolume"),
  musicLibrarySection: document.getElementById("musicLibrarySection"),
  musicLibraryDock: document.getElementById("musicLibraryDock"),
  musicLibraryCount: document.getElementById("musicLibraryCount"),
  musicDock: document.getElementById("musicDock"),
  musicCount: document.getElementById("musicCount"),
  nowPlayingArt: document.getElementById("nowPlayingArt"),
  nowPlayingLyricsPanel: document.getElementById("nowPlayingLyricsPanel"),
  nowPlayingLyricsList: document.getElementById("nowPlayingLyricsList"),
  nowPlayingLyricsStatus: document.getElementById("nowPlayingLyricsStatus"),
  lyricsTimingEditor: document.getElementById("lyricsTimingEditor"),
  lyricsTimingTarget: document.getElementById("lyricsTimingTarget"),
  lyricsTimingStartInput: document.getElementById("lyricsTimingStartInput"),
  lyricsTimingEndInput: document.getElementById("lyricsTimingEndInput"),
  lyricsTimingUseNowStart: document.getElementById("lyricsTimingUseNowStart"),
  lyricsTimingUseNowEnd: document.getElementById("lyricsTimingUseNowEnd"),
  lyricsTimingSave: document.getElementById("lyricsTimingSave"),
  lyricsTimingClear: document.getElementById("lyricsTimingClear"),
  lyricsTimingClose: document.getElementById("lyricsTimingClose"),
  openDownloads: document.getElementById("openDownloads"),
  refreshMaterialCandidates: document.getElementById("refreshMaterialCandidates"),
  importMaterial: document.getElementById("importMaterial"),
  downloadIntakeToggle: document.getElementById("downloadIntakeToggle"),
  renderTextureDropzone: document.getElementById("renderTextureDropzone"),
  renderTextureZoneStatus: document.getElementById("renderTextureZoneStatus"),
  workzoneFileInput: document.getElementById("workzoneFileInput"),
  materialSourcePath: document.getElementById("materialSourcePath"),
  materialTargetPath: document.getElementById("materialTargetPath"),
  latestMaterialName: document.getElementById("latestMaterialName"),
  materialCandidates: document.getElementById("materialCandidates"),
  materialImportStatus: document.getElementById("materialImportStatus"),
  githubDownloadsStatus: document.getElementById("githubDownloadsStatus"),
  openGithubDownloads: document.getElementById("openGithubDownloads"),
  githubDownloadsLink: document.getElementById("githubDownloadsLink"),
  githubDownloadsMeta: document.getElementById("githubDownloadsMeta"),
  updateProductConsole: document.getElementById("updateProductConsole"),
  updateProductWorld: document.getElementById("updateProductWorld"),
  updateProductConsoleBadge: document.getElementById("updateProductConsoleBadge"),
  updateProductWorldBadge: document.getElementById("updateProductWorldBadge"),
  consoleUpdateCurrent: document.getElementById("consoleUpdateCurrent"),
  consoleUpdateStatus: document.getElementById("consoleUpdateStatus"),
  consoleUpdateRelease: document.getElementById("consoleUpdateRelease"),
  consoleUpdateAuto: document.getElementById("consoleUpdateAuto"),
  consoleUpdateRefresh: document.getElementById("consoleUpdateRefresh"),
  consoleUpdateInstall: document.getElementById("consoleUpdateInstall"),
  consoleUninstall: document.getElementById("consoleUninstall"),
  consoleUpdateError: document.getElementById("consoleUpdateError"),
  consoleUpdateTop: document.getElementById("consoleUpdateTop"),
  workspaceTodoCategory: document.getElementById("workspaceTodoCategory"),
  workspaceTodoInput: document.getElementById("workspaceTodoInput"),
  addWorkspaceTodo: document.getElementById("addWorkspaceTodo"),
  resetWorkspaceTodo: document.getElementById("resetWorkspaceTodo"),
  workspaceTodoList: document.getElementById("workspaceTodoList"),
  workspaceTodoCount: document.getElementById("workspaceTodoCount"),
  randomRealmReleaseStatusText: document.getElementById("randomRealmReleaseStatusText"),
  openSteamworks: document.getElementById("openSteamworks"),
  openSteamPublishFolder: document.getElementById("openSteamPublishFolder"),
  openRandomRealmProject: document.getElementById("openRandomRealmProject"),
  openRandomRealmPromo: document.getElementById("openRandomRealmPromo"),
  steamworkStatusText: document.getElementById("steamworkStatusText"),
  openSteamworkDashboard: document.getElementById("openSteamworkDashboard"),
  openSteamworkPublishFolder: document.getElementById("openSteamworkPublishFolder"),
  openSteamworkGameContent: document.getElementById("openSteamworkGameContent"),
  openSteamworkPublishTool: document.getElementById("openSteamworkPublishTool"),
  openSteamworkPublishToolTip: document.getElementById("openSteamworkPublishToolTip"),
  openSteamworkBuildsTip: document.getElementById("openSteamworkBuildsTip"),
  locateSteamworkPublishTool: document.getElementById("locateSteamworkPublishTool"),
  openSteamworkArtAsset: document.getElementById("openSteamworkArtAsset"),
  steamworkGameContentDropzone: document.getElementById("steamworkGameContentDropzone"),
  steamworkPublishToolDropzone: document.getElementById("steamworkPublishToolDropzone"),
  steamworkGameContentStatus: document.getElementById("steamworkGameContentStatus"),
  steamworkPublishToolStatus: document.getElementById("steamworkPublishToolStatus"),
  steamworkGameContentFileInput: document.getElementById("steamworkGameContentFileInput"),
  steamworkPublishToolFileInput: document.getElementById("steamworkPublishToolFileInput"),
  steamworkAssetRoot: document.getElementById("steamworkAssetRoot"),
  steamworkAssetSummary: document.getElementById("steamworkAssetSummary"),
  steamworkAssetList: document.getElementById("steamworkAssetList"),
  steamworkAssetFileInput: document.getElementById("steamworkAssetFileInput"),
  unityStatusText: document.getElementById("unityStatusText"),
  unityBridgeStatus: document.getElementById("unityBridgeStatus"),
  openUnityProjectFolder: document.getElementById("openUnityProjectFolder"),
  openUnityPromoFolder: document.getElementById("openUnityPromoFolder"),
  blenderGithubSharePanel: document.getElementById("blenderGithubSharePanel"),
  blenderGithubToggle: document.getElementById("blenderGithubToggle"),
  blenderGithubBody: document.getElementById("blenderGithubBody"),
  blenderGithubState: document.getElementById("blenderGithubState"),
  blenderGithubAdd: document.getElementById("blenderGithubAdd"),
  blenderGithubProject: document.getElementById("blenderGithubProject"),
  blenderGithubBlendCards: document.getElementById("blenderGithubBlendCards"),
  blenderGithubProjectPath: document.getElementById("blenderGithubProjectPath"),
  blenderGithubRefresh: document.getElementById("blenderGithubRefresh"),
  blenderGithubBlendFile: document.getElementById("blenderGithubBlendFile"),
  blenderGithubBranch: document.getElementById("blenderGithubBranch"),
  blenderGithubRemote: document.getElementById("blenderGithubRemote"),
  blenderGithubLastVersion: document.getElementById("blenderGithubLastVersion"),
  blenderGithubRepository: document.getElementById("blenderGithubRepository"),
  blenderGithubToolStatus: document.getElementById("blenderGithubToolStatus"),
  blenderGithubVersion: document.getElementById("blenderGithubVersion"),
  blenderGithubMessage: document.getElementById("blenderGithubMessage"),
  blenderGithubCommitMeta: document.getElementById("blenderGithubCommitMeta"),
  blenderGithubCustomScope: document.getElementById("blenderGithubCustomScope"),
  blenderGithubIncludes: document.getElementById("blenderGithubIncludes"),
  blenderGithubExcludes: document.getElementById("blenderGithubExcludes"),
  blenderGithubChangesCount: document.getElementById("blenderGithubChangesCount"),
  blenderGithubChanges: document.getElementById("blenderGithubChanges"),
  blenderGithubInitialize: document.getElementById("blenderGithubInitialize"),
  blenderGithubCommit: document.getElementById("blenderGithubCommit"),
  blenderGithubPush: document.getElementById("blenderGithubPush"),
  blenderGithubOpen: document.getElementById("blenderGithubOpen"),
  blenderGithubDesktop: document.getElementById("blenderGithubDesktop"),
  blenderGithubFolder: document.getElementById("blenderGithubFolder"),
  blenderGithubStatus: document.getElementById("blenderGithubStatus"),
  randomRealmBlenderProject: document.getElementById("randomRealmBlenderProject"),
  randomRealmProjectPath: document.getElementById("randomRealmProjectPath"),
  randomRealmProjectSearch: document.getElementById("randomRealmProjectSearch"),
  randomRealmArtType: document.getElementById("randomRealmArtType"),
  randomRealmObjectSearch: document.getElementById("randomRealmObjectSearch"),
  randomRealmSyncLiveSelection: document.getElementById("randomRealmSyncLiveSelection"),
  randomRealmBlenderObject: document.getElementById("randomRealmBlenderObject"),
  randomRealmMaterialTabs: document.getElementById("randomRealmMaterialTabs"),
  randomRealmTextureManagerCount: document.getElementById("randomRealmTextureManagerCount"),
  randomRealmUsedTextures: document.getElementById("randomRealmUsedTextures"),
  randomRealmTextureKind: document.getElementById("randomRealmTextureKind"),
  randomRealmOldTextureName: document.getElementById("randomRealmOldTextureName"),
  randomRealmOldTextureSize: document.getElementById("randomRealmOldTextureSize"),
  randomRealmOldTexturePreview: document.getElementById("randomRealmOldTexturePreview"),
  randomRealmOldTexturePreviewEmpty: document.getElementById("randomRealmOldTexturePreviewEmpty"),
  randomRealmTextureInspectorMaterial: document.getElementById("randomRealmTextureInspectorMaterial"),
  randomRealmTextureInspectorRole: document.getElementById("randomRealmTextureInspectorRole"),
  randomRealmTextureInspectorNode: document.getElementById("randomRealmTextureInspectorNode"),
  randomRealmTextureInspectorState: document.getElementById("randomRealmTextureInspectorState"),
  randomRealmTextureInspectorFile: document.getElementById("randomRealmTextureInspectorFile"),
  randomRealmTextureInspectorPath: document.getElementById("randomRealmTextureInspectorPath"),
  randomRealmNewTextureDrop: document.getElementById("randomRealmNewTextureDrop"),
  randomRealmNewTextureName: document.getElementById("randomRealmNewTextureName"),
  randomRealmNewTextureSize: document.getElementById("randomRealmNewTextureSize"),
  randomRealmNewTexturePreview: document.getElementById("randomRealmNewTexturePreview"),
  randomRealmNewTexturePreviewEmpty: document.getElementById("randomRealmNewTexturePreviewEmpty"),
  randomRealmStagedTextureList: document.getElementById("randomRealmStagedTextureList"),
  randomRealmClearNewTexture: document.getElementById("randomRealmClearNewTexture"),
  randomRealmTextureFileInput: document.getElementById("randomRealmTextureFileInput"),
  randomRealmStageBlankTexture: document.getElementById("randomRealmStageBlankTexture"),
  randomRealmArtStatus: document.getElementById("randomRealmArtStatus"),
  blenderPromptFormat: document.getElementById("blenderPromptFormat"),
  blenderPromptImage: document.getElementById("blenderPromptImage"),
  blenderPromptResolution: document.getElementById("blenderPromptResolution"),
  blenderPromptCustomResolution: document.getElementById("blenderPromptCustomResolution"),
  blenderPromptCustomWidth: document.getElementById("blenderPromptCustomWidth"),
  blenderPromptCustomLength: document.getElementById("blenderPromptCustomLength"),
  blenderPromptStyle: document.getElementById("blenderPromptStyle"),
  blenderPromptBasics: document.getElementById("blenderPromptBasics"),
  blenderPromptOutput: document.getElementById("blenderPromptOutput"),
  generateBlenderPrompt: document.getElementById("generateBlenderPrompt"),
  copyBlenderPrompt: document.getElementById("copyBlenderPrompt"),
  clearBlenderPrompt: document.getElementById("clearBlenderPrompt"),
  blenderPromptStatus: document.getElementById("blenderPromptStatus")
};

let wallpapers = [];
let tracks = [];
let selectedWallpaperPath = localStorage.getItem(storageKeys.selectedWallpaper) || "";
let wallpaperOrder = loadWallpaperOrder();
let selectedTrackPath = localStorage.getItem(storageKeys.selectedTrack) || "";
let language = localStorage.getItem(storageKeys.language) || "zh";
let theme = normalizeTheme(localStorage.getItem(storageKeys.theme));
let pendingDeletePath = "";
let draggedWallpaperPath = "";
let suppressWallpaperClickUntil = 0;
let lastWallpaperClickPath = "";
let lastWallpaperClickAt = 0;
const wallpaperDoubleClickMs = 520;
let pendingDeleteTrackPath = "";
let userSeeking = false;
let pendingSeekRatio = null;
let activeSeekPointerId = null;
let seekHistoryStartRatio = null;
let volumeHistoryStart = null;
let musicTierAssignments = {};
let musicTierOrder = [];
let musicTierVisibility = loadMusicTierVisibility();
let musicNotice = "";
let musicLinkNotice = "";
let musicLibraryNotice = "";
let musicCookieState = { available: false };
let musicLibraries = [];
let libraryTracks = [];
let musicLyricsTrackPath = "";
let musicLyricsLines = [];
let musicLyricsStatus = "";
let musicLyricsActiveIndex = -1;
let musicLyricsSynced = false;
let musicLyricsAnalysis = null;
let musicLyricsLoadToken = 0;
let musicLyricsLookupPath = "";
let musicLyricsPreloadTimer = 0;
let musicLyricsPlaybackPreloadKey = "";
const musicLyricsCache = new Map();
const musicLyricsTextPromises = new Map();
const musicLyricsAnalysisPromises = new Map();
let musicLyricsAnimationFrame = 0;
let musicLyricsPanelHeight = Number(localStorage.getItem(storageKeys.lyricsHeight)) || 0;
let musicLyricsPanelResizing = false;
let musicLyricsResizeStartY = 0;
let musicLyricsResizeStartHeight = 0;
let musicLyricsResizePointerId = null;
let suppressLyricsLineClickUntil = 0;
let heldLyricsActiveIndex = -1;
let heldLyricsActiveUntil = 0;
let lyricsTimingContextLineIndex = -1;
let lyricsTimingContextClickCount = 0;
let lyricsTimingContextLastAt = 0;
let activeLyricsTimingTarget = null;
let activeLyricsTimingRangeStart = 0;
let activeLyricsTimingRangeEnd = 0;
let activeLyricsTimingRangeMode = "word";
let lyricsTimingWaveDrag = null;
let suppressLyricsTimingClickUntil = 0;
let suppressLyricsTimingContextMenuUntil = 0;
let lyricsTimingAutoSaveTimer = null;
const lyricsTimingMinBoundaryGap = 0.03;
const lyricsTimingWaveMinEdgePadSeconds = 0.18;
const lyricsTimingWaveMaxEdgePadSeconds = 0.7;
const lyricsTimingWaveEdgePadRatio = 0.24;
let pendingMusicLyricMarks = new Map();
let sessionMusicLyricMarks = new Map();
let musicLyricMarksFlushPromise = null;
let promotedLibraryTracks = loadPromotedLibraryTracks();
let musicLibraryPollTimer = null;
let musicStatePersistTimer = null;
let playbackMode = normalizePlaybackMode(localStorage.getItem(storageKeys.playbackMode));
let draggedModuleId = "";
let draggedTrackPath = "";
let currentMusicDropTargetKey = "";
let suppressTrackClickUntil = 0;
let lastTrackPointerStart = 0;
let lastPersistedModuleId = "";
let suppressModuleClickUntil = 0;
let lastModulePointerStart = 0;
let lastArchivePointerStart = 0;
let lastWallpaperPointerStart = 0;
let archiveExpanded = false;
let archiveView = "main";
let archiveRightReleaseCount = 0;
let archiveRightReleaseTimer = null;
let materialCandidates = [];
let selectedMaterialPath = "";
let materialNotice = "";
let renderTextureNotice = "";
let downloadIntakeEnabled = localStorage.getItem(storageKeys.downloadIntake) === "true";
let tutorialMode = localStorage.getItem(storageKeys.tutorialMode) === "true";
let activeConsoleView = normalizeConsoleWorkspaceView(localStorage.getItem(storageKeys.consoleView));
let activeBlenderView = normalizeBlenderWorkspaceView(localStorage.getItem(storageKeys.blenderView));
let blenderViewTransitionTimer = 0;
let blenderViewTransitionFrame = 0;
let blenderViewTransitionAnimations = [];
let blenderGithubShareState = null;
let blenderGithubBusy = false;
let blenderGithubPublicConfirmed = false;
let blenderGithubSaveRequested = false;
let blenderGithubLoadSequence = 0;
let blenderGithubCardClickTimer = null;
let blenderGithubDraggedPath = "";
let blenderGithubDropCommitted = false;
let githubDownloadsInfo = null;
const initialConsoleVersion = String(els.consoleUpdateCurrent?.textContent || "").replace(/^v/i, "").trim();
let productUpdateStates = {
  console: initialConsoleVersion ? {
    currentVersion: initialConsoleVersion,
    latestVersion: "",
    installed: true,
    autoCheck: true
  } : null,
  world: null
};
let productUpdateBusy = false;
let selectedUpdateProduct = localStorage.getItem(storageKeys.updateProduct) === "world" ? "world" : "console";
let desktopLayoutState = null;
let desktopLayoutBusy = false;
let desktopLayoutNotice = "";
let desktopLayoutNoticeTone = "";
let desktopLayoutDetail = "";
let feedbackConfig = null;
let feedbackConfigBusy = false;
let feedbackBusy = false;
let feedbackNotice = "";
let feedbackNoticeTone = "";
let feedbackImage = null;
let feedbackImageUrl = "";
let feedbackReports = [];
let feedbackNewCount = 0;
let feedbackInboxBusy = false;
let feedbackInboxTimer = 0;
let feedbackTurnstileWidgetId = null;
let feedbackTurnstileLoading = null;
let pendingSteamworkAssetSlot = "";
let steamworkThumbsEnabled = false;
let workspaceTodoGroups = loadWorkspaceTodos();
let randomRealmArtContext = loadRandomRealmArtContext();
let blenderPromptConfig = loadBlenderPromptConfig();
let randomRealmBlenderProjects = [];
let randomRealmBlenderObjects = [];
let randomRealmLoadedObjectsProject = "";
let randomRealmSelectedOldTexture = null;
let randomRealmSelectedMaterial = "";
let randomRealmNewTexture = null;
let randomRealmStagedTextures = [];
let randomRealmAddMapMode = false;
let randomRealmArtNotice = "";
let randomRealmTextureActionBusy = false;
let randomRealmTextureAutoPackTimer = null;
let randomRealmTextureApplyPollTimer = null;
let randomRealmTextureApplyPollInFlight = false;
let randomRealmProjectSearchTimer = null;
let randomRealmObjectPickerOpen = false;
let randomRealmLiveSelectionTimer = null;
let randomRealmLastLiveObject = "";
let randomRealmLiveSelectedObjects = [];
const randomRealmPreviewableTextureExtensions = [".png", ".jpg", ".jpeg", ".bmp", ".webp"];
const randomRealmTextureDragFileCache = new Map();
const consoleUndoStack = [];
const consoleRedoStack = [];
const consoleHistoryLimit = 80;
const smoothValueAnimations = new Map();
let consoleHistoryApplying = false;
let clockTickTimer = 0;
let runtimeActivityReady = false;
const loadedModuleData = new Set();
const loadingModuleData = new Map();
const shouldRestoreLastModuleOnLoad = currentPageName() === "index.html" && lastModuleId();
let activeModuleId = initialModuleId();
const hasWallpaper = Boolean(els.wallpaperDock);
const hasMusic = Boolean(els.musicDock);
const hasWorkspace = Boolean(els.workspaceTodoList || els.materialCandidates);
const hasMaterialWorkspace = Boolean(els.materialCandidates);
const hasSteamwork = Boolean(
  els.openSteamworkDashboard ||
  els.openSteamworkGameContent ||
  els.openSteamworkPublishTool ||
  els.openSteamworkArtAsset ||
  els.steamworkAssetList
);
const musicTierGroups = [
  { id: "first", labelKey: "musicTierFirst" },
  { id: "second", labelKey: "musicTierSecond" },
  { id: "third", labelKey: "musicTierThird" }
];
musicTierAssignments = loadMusicTierAssignments();
musicTierOrder = loadMusicTierOrder();

function disableBrowserWheelZoom() {
  window.addEventListener("wheel", event => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
    }
  }, { capture: true, passive: false });
}

disableBrowserWheelZoom();

function historyValueKey(value) {
  return JSON.stringify(value ?? null);
}

function historyValuesEqual(first, second) {
  return historyValueKey(first) === historyValueKey(second);
}

function pushConsoleHistory(action) {
  if (consoleHistoryApplying || !action || historyValuesEqual(action.before, action.after) || typeof action.apply !== "function") return;
  const previous = consoleUndoStack[consoleUndoStack.length - 1];
  if (previous && previous.type === action.type && historyValuesEqual(previous.before, action.before) && historyValuesEqual(previous.after, action.after)) {
    return;
  }
  consoleUndoStack.push(action);
  if (consoleUndoStack.length > consoleHistoryLimit) {
    consoleUndoStack.shift();
  }
  consoleRedoStack.length = 0;
}

function cancelSmoothValueAnimation(key) {
  const animation = smoothValueAnimations.get(key);
  if (!animation) return;
  window.cancelAnimationFrame(animation.frame);
  smoothValueAnimations.delete(key);
  animation.cancel?.();
}

function cancelSmoothValueAnimations() {
  for (const key of Array.from(smoothValueAnimations.keys())) {
    cancelSmoothValueAnimation(key);
  }
}

function runConsoleHistoryAction(action, value, direction) {
  cancelSmoothValueAnimations();
  consoleHistoryApplying = true;
  try {
    action.apply(value, direction);
  } finally {
    window.requestAnimationFrame(() => {
      consoleHistoryApplying = false;
    });
  }
}

function undoConsoleAction() {
  const action = consoleUndoStack.pop();
  if (!action) return false;
  consoleRedoStack.push(action);
  runConsoleHistoryAction(action, action.before, "undo");
  return true;
}

function redoConsoleAction() {
  const action = consoleRedoStack.pop();
  if (!action) return false;
  consoleUndoStack.push(action);
  runConsoleHistoryAction(action, action.after, "redo");
  return true;
}

function isTextUndoTarget(target) {
  const node = target?.closest?.("input, textarea, select, [contenteditable='true'], [contenteditable='']");
  if (!node) return false;
  if (node.matches?.("textarea, select, [contenteditable='true'], [contenteditable='']")) return true;
  const type = String(node.getAttribute("type") || "text").toLowerCase();
  return !["button", "checkbox", "color", "file", "image", "radio", "range", "reset", "submit"].includes(type);
}

function handleConsoleUndoRedoKeydown(event) {
  const key = String(event.key || "").toLowerCase();
  const isModifier = event.ctrlKey || event.metaKey;
  if (!isModifier || event.altKey || isTextUndoTarget(event.target)) return false;
  const wantsUndo = key === "z" && !event.shiftKey;
  const wantsRedo = key === "y" || key === "z" && event.shiftKey;
  if (!wantsUndo && !wantsRedo) return false;
  const handled = wantsRedo ? redoConsoleAction() : undoConsoleAction();
  if (handled) {
    event.preventDefault();
    event.stopPropagation();
  }
  return handled;
}

function currentPageName() {
  return window.location.pathname.split("/").pop() || "index.html";
}

function isModuleForeground(id) {
  return !document.hidden && activeModuleId === id;
}

function moduleUrl(href) {
  const params = new URLSearchParams(window.location.search);
  if (consoleEdition === "developer") params.delete("edition");
  else params.set("edition", consoleEdition);
  const search = params.toString();
  return `${href}${search ? `?${search}` : ""}${window.location.hash}`;
}

function editionModuleIds() {
  return editionModules[consoleEdition] || editionModules.developer;
}

function editionModuleSet() {
  return new Set(editionModuleIds());
}

function availableModules() {
  return editionModuleIds()
    .map(id => moduleMap.get(id))
    .filter(Boolean);
}

function firstAvailableModule() {
  return availableModules()[0] || modules[0];
}

function isKnownModuleId(id) {
  return modules.some(item => item.id === id);
}

function isModuleAvailable(id) {
  return editionModuleSet().has(id);
}

function moduleIdFromPage(pageName) {
  const item = modules.find(module => module.href === pageName);
  return item && isModuleAvailable(item.id) ? item.id : firstAvailableModule().id;
}

function isModuleId(id) {
  return isKnownModuleId(id) && isModuleAvailable(id);
}

function moduleById(id) {
  return isModuleAvailable(id) ? moduleMap.get(id) || firstAvailableModule() : firstAvailableModule();
}

function canActivateModuleInPlace(id) {
  return Boolean(document.querySelector(`[data-module-panel="${id}"]`));
}

function lastModuleId() {
  const saved = localStorage.getItem(storageKeys.lastModule) || "";
  return isModuleId(saved) ? saved : "";
}

function initialModuleId() {
  ensureEditionModuleLayout();
  const pageName = currentPageName();
  const unavailable = new Set([...allArchivedModuleIds(), ...deletedModuleIds()]);
  if (pageName === "index.html") {
    const saved = lastModuleId();
    if (saved && !unavailable.has(saved)) {
      return saved;
    }
  }
  const pageModule = moduleIdFromPage(pageName);
  return unavailable.has(pageModule) ? visibleModuleOrder()[0] : pageModule;
}

function rememberActiveModule(id) {
  if (isModuleId(id)) {
    if (localStorage.getItem(storageKeys.lastModule) !== id) {
      localStorage.setItem(storageKeys.lastModule, id);
    }
    persistConsoleState(id);
  }
}

function persistConsoleState(id) {
  if (!isModuleId(id) || id === lastPersistedModuleId) return;
  lastPersistedModuleId = id;
  fetch("/api/console/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lastModule: id }),
    keepalive: true
  }).catch(() => {});
}

function restoreInitialModuleUrl() {
  if (!shouldRestoreLastModuleOnLoad) return;
  const current = moduleById(activeModuleId);
  if (currentPageName() !== current.href) {
    history.replaceState({ moduleId: current.id }, "", moduleUrl(current.href));
  }
}

async function loadModuleData(id) {
  switch (id) {
    case "wallpaper":
      if (hasWallpaper) await loadWallpapers();
      break;
    case "music":
      if (hasMusic) await loadMusic();
      break;
    case "workspace":
      if (hasWorkspace) await loadGithubDownloadsInfo();
      if (els.consoleUpdateStatus && !productUpdateStates.console && !productUpdateStates.world) {
        await loadProductUpdateStatuses({ check: true, quiet: true });
      }
      if (els.desktopLayoutPlan && !desktopLayoutState) await loadDesktopLayout({ quiet: true });
      if (els.feedbackForm && !feedbackConfig) await loadFeedbackConfig({ quiet: true });
      if (hasMaterialWorkspace && downloadIntakeEnabled) await loadMaterialCandidates();
      break;
    case "blender":
      if (hasRandomRealmArtTools()) {
        await loadRandomRealmBlenderProjects({ limit: 40, loadObjects: activeBlenderView === "builder" });
      }
      if (hasBlenderGithubShare() && !blenderGithubShareState && !blenderGithubBusy) {
        await loadBlenderGithubShare({ detect: true });
      }
      break;
    case "unity":
      await loadUnityBridgeStatus();
      break;
    case "steamwork":
      if (hasSteamwork) await loadSteamworkAssets();
      break;
    default:
      break;
  }
}

function ensureModuleDataLoaded(id = activeModuleId) {
  const moduleId = moduleById(id).id;
  if (loadedModuleData.has(moduleId)) return Promise.resolve();
  if (loadingModuleData.has(moduleId)) return loadingModuleData.get(moduleId);

  const request = loadModuleData(moduleId)
    .catch(() => {})
    .finally(() => {
      loadingModuleData.delete(moduleId);
      loadedModuleData.add(moduleId);
    });
  loadingModuleData.set(moduleId, request);
  return request;
}

function syncRuntimeActivity(options = {}) {
  if (!runtimeActivityReady) return;

  if (!document.hidden) {
    ensureModuleDataLoaded(activeModuleId);
  }

  syncLyricsAnimationLoop();

  if (isModuleForeground("music")) {
    if (hasActiveMusicLibraryGrab() && !musicLibraryPollTimer) {
      scheduleMusicLibraryPoll(options.resume || options.moduleChanged ? 250 : 4000);
    }
  } else {
    stopMusicLibraryPoll();
  }

  if (isModuleForeground("blender")) {
    startRandomRealmLiveSelectionPolling({ immediate: Boolean(options.resume || options.moduleChanged) });
    if (randomRealmPackedPackagePaths().length && !randomRealmTextureApplyPollTimer && !randomRealmTextureApplyPollInFlight) {
      scheduleRandomRealmTextureApplyPoll(options.resume || options.moduleChanged ? 250 : 2600);
    }
  } else {
    stopRandomRealmLiveSelectionPolling();
    stopRandomRealmTextureApplyPolling();
  }

  if (isModuleForeground("workspace") && feedbackConfig?.adminEnabled) {
    scheduleFeedbackInboxPolling(options.resume || options.moduleChanged ? 250 : 30000);
  } else {
    stopFeedbackInboxPolling();
  }
}

function activateModule(id, push = false, options = {}) {
  const previousActiveModuleId = activeModuleId;
  const archived = new Set(allArchivedModuleIds());
  const deleted = new Set(deletedModuleIds());
  let next = moduleById(id);
  if (deleted.has(next.id)) {
    next = moduleById(visibleModuleOrder()[0]);
  } else if (archived.has(next.id) && !options.allowArchived) {
    next = moduleById(visibleModuleOrder()[0]);
  }
  activeModuleId = next.id;
  rememberActiveModule(activeModuleId);

  for (const panel of document.querySelectorAll("[data-module-panel]")) {
    panel.hidden = panel.dataset.modulePanel !== activeModuleId;
  }

  if (els.moduleTitle) {
    els.moduleTitle.textContent = text(next.titleKey);
    els.moduleTitle.dataset.i18n = next.titleKey;
  }

  document.title = `Codex Console - ${text(next.titleKey)}`;

  if (push && currentPageName() !== next.href) {
    history.pushState({ moduleId: next.id }, "", moduleUrl(next.href));
  } else if (options.replaceUrl && currentPageName() !== next.href) {
    history.replaceState({ moduleId: next.id }, "", moduleUrl(next.href));
  }

  renderModuleNavs();
  syncRuntimeActivity({ moduleChanged: previousActiveModuleId !== activeModuleId });
}

function applyModuleHistory(id) {
  activateModule(id, false, { allowArchived: true, replaceUrl: true });
}

function normalizeConsoleWorkspaceView(value) {
  return value === "collaboration" ? "collaboration" : "common";
}

function setConsoleWorkspaceView(value, options = {}) {
  activeConsoleView = normalizeConsoleWorkspaceView(value);
  if (options.persist !== false) {
    localStorage.setItem(storageKeys.consoleView, activeConsoleView);
  }

  const buttons = Array.from(document.querySelectorAll("[data-console-view-target]"));
  const activeButtonIndex = Math.max(0, buttons.findIndex(button => button.dataset.consoleViewTarget === activeConsoleView));
  document.querySelector(".console-subnav")?.style.setProperty("--blender-subtab-index", String(activeButtonIndex));
  for (const button of buttons) {
    const active = button.dataset.consoleViewTarget === activeConsoleView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  }

  for (const view of document.querySelectorAll("[data-console-view]")) {
    const active = view.dataset.consoleView === activeConsoleView;
    view.hidden = !active;
    view.classList.toggle("active", active);
  }

  if (activeConsoleView === "collaboration") {
    if (!feedbackConfig && !feedbackConfigBusy) {
      loadFeedbackConfig({ quiet: true });
    } else if (feedbackConfig?.adminEnabled && !feedbackInboxBusy) {
      loadFeedbackInbox({ quiet: true });
    }
  }
}

function normalizeBlenderWorkspaceView(value) {
  return value === "builder" ? "builder" : "helper";
}

function setBlenderWorkspaceView(value, options = {}) {
  const previousView = activeBlenderView;
  activeBlenderView = normalizeBlenderWorkspaceView(value);
  if (options.persist !== false) {
    localStorage.setItem(storageKeys.blenderView, activeBlenderView);
  }
  const buttons = Array.from(document.querySelectorAll("[data-blender-view-target]"));
  const activeButtonIndex = Math.max(0, buttons.findIndex(button => button.dataset.blenderViewTarget === activeBlenderView));
  document.querySelector(".blender-subnav")?.style.setProperty("--blender-subtab-index", String(activeButtonIndex));
  for (const button of buttons) {
    const active = button.dataset.blenderViewTarget === activeBlenderView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  }

  if (runtimeActivityReady && isModuleForeground("blender")) {
    if (activeBlenderView === "builder") {
      const project = els.randomRealmBlenderProject?.value || "";
      if (project && randomRealmLoadedObjectsProject !== project) {
        loadRandomRealmBlenderObjects();
      }
    } else if (!blenderGithubShareState && !blenderGithubBusy) {
      loadBlenderGithubShare({ detect: true });
    }
  }

  const views = Array.from(document.querySelectorAll("[data-blender-view]"));
  const nextView = views.find(view => view.dataset.blenderView === activeBlenderView);
  const oldView = views.find(view => view.dataset.blenderView === previousView);
  const stage = document.querySelector(".blender-view-stage");
  const shouldAnimate = options.animate !== false
    && previousView !== activeBlenderView
    && stage
    && nextView
    && oldView
    && !oldView.hidden
    && !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

  window.clearTimeout(blenderViewTransitionTimer);
  window.cancelAnimationFrame(blenderViewTransitionFrame);
  blenderViewTransitionFrame = 0;
  for (const animation of blenderViewTransitionAnimations) {
    animation.cancel();
  }
  blenderViewTransitionAnimations = [];
  for (const view of views) {
    view.classList.remove("entering", "leaving");
    view.style.transform = "";
  }
  stage?.classList.remove("switching", "to-helper", "to-builder");

  if (!shouldAnimate) {
    for (const view of views) {
      const active = view.dataset.blenderView === activeBlenderView;
      view.hidden = !active;
      view.classList.toggle("active", active);
    }
    if (stage) stage.style.height = "";
    return;
  }

  const stageStyle = getComputedStyle(stage);
  const stageVerticalChrome = (parseFloat(stageStyle.paddingTop) || 0)
    + (parseFloat(stageStyle.paddingBottom) || 0)
    + (parseFloat(stageStyle.borderTopWidth) || 0)
    + (parseFloat(stageStyle.borderBottomWidth) || 0);
  const targetViewName = activeBlenderView;
  const direction = activeBlenderView === "builder" ? 1 : -1;
  const slideDistance = Math.ceil(stage.getBoundingClientRect().width + 8);
  const nextStart = `translate3d(${direction * slideDistance}px, 0, 0)`;
  const oldEnd = `translate3d(${-direction * slideDistance}px, 0, 0)`;
  const neutral = "translate3d(0, 0, 0)";
  nextView.hidden = false;
  nextView.classList.add("entering");
  nextView.classList.add("active");
  oldView.classList.add("active");
  oldView.classList.add("leaving");
  const targetHeight = Math.max(nextView.getBoundingClientRect().height + stageVerticalChrome, 1);

  stage.style.height = `${targetHeight}px`;
  stage.classList.add("switching", activeBlenderView === "builder" ? "to-builder" : "to-helper");
  nextView.style.transform = nextStart;
  oldView.style.transform = neutral;
  stage.getBoundingClientRect();

  const cleanup = () => {
    if (activeBlenderView !== targetViewName) return;
    window.clearTimeout(blenderViewTransitionTimer);
    window.cancelAnimationFrame(blenderViewTransitionFrame);
    blenderViewTransitionFrame = 0;
    blenderViewTransitionAnimations = [];
    for (const view of views) {
      const active = view.dataset.blenderView === activeBlenderView;
      view.hidden = !active;
      view.classList.toggle("active", active);
      view.classList.remove("entering", "leaving");
      view.style.transform = "";
    }
    stage.classList.remove("switching", "to-helper", "to-builder");
    stage.style.height = "";
  };

  const cleanupAfterFinalPaint = () => {
    if (activeBlenderView !== targetViewName) return;
    window.cancelAnimationFrame(blenderViewTransitionFrame);
    blenderViewTransitionFrame = window.requestAnimationFrame(() => {
      blenderViewTransitionFrame = window.requestAnimationFrame(() => {
        blenderViewTransitionFrame = 0;
        cleanup();
      });
    });
  };

  if (typeof nextView.animate !== "function" || typeof oldView.animate !== "function") {
    oldView.style.transform = oldEnd;
    nextView.style.transform = neutral;
    blenderViewTransitionTimer = window.setTimeout(cleanupAfterFinalPaint, 420);
    return;
  }

  const timing = {
    duration: 420,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    fill: "forwards"
  };
  const oldAnimation = oldView.animate([
    { transform: neutral },
    { transform: oldEnd }
  ], timing);
  const nextAnimation = nextView.animate([
    { transform: nextStart },
    { transform: neutral }
  ], timing);
  blenderViewTransitionAnimations = [oldAnimation, nextAnimation];
  Promise.allSettled(blenderViewTransitionAnimations.map(animation => animation.finished)).then(cleanupAfterFinalPaint);
  blenderViewTransitionTimer = window.setTimeout(cleanup, 560);
}

function recordModuleChange(beforeId, afterId) {
  if (!isModuleId(beforeId) || !isModuleId(afterId) || beforeId === afterId) return;
  pushConsoleHistory({
    type: "module",
    before: beforeId,
    after: afterId,
    apply: applyModuleHistory
  });
}

function activateModuleFromUser(id, push = true, options = {}) {
  const beforeId = activeModuleId;
  activateModule(id, push, options);
  recordModuleChange(beforeId, activeModuleId);
}

function openArchivedModule(id) {
  if (!allArchivedModuleIds().includes(id)) return;
  const beforeId = activeModuleId;
  setArchiveExpanded(false);
  activateModule(id, true, { allowArchived: true });
  recordModuleChange(beforeId, activeModuleId);
}

function moduleOrder() {
  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem(storageKeys.moduleOrder) || "[]");
  } catch {
    saved = [];
  }
  const currentModules = availableModules();
  const validIds = editionModuleSet();
  const deleted = new Set(deletedModuleIds());
  const ordered = [];
  for (const id of saved) {
    if (validIds.has(id) && !deleted.has(id) && !ordered.includes(id)) {
      ordered.push(id);
    }
  }
  for (const item of currentModules) {
    if (deleted.has(item.id)) continue;
    if (!ordered.includes(item.id)) {
      if (item.id === "manager") {
        ordered.unshift(item.id);
      } else {
        const moduleIndex = currentModules.findIndex(module => module.id === item.id);
        const previousVisible = currentModules
          .slice(0, moduleIndex)
          .map(module => module.id)
          .reverse()
          .find(id => ordered.includes(id));
        if (previousVisible) {
          ordered.splice(ordered.indexOf(previousVisible) + 1, 0, item.id);
        } else {
          ordered.push(item.id);
        }
      }
    }
  }
  const fallback = currentModules.find(item => !deleted.has(item.id)) || firstAvailableModule();
  return ordered.length ? ordered : [fallback.id];
}

function ensureEditionModuleLayout() {
  if (consoleEdition !== "public") return;
  if (localStorage.getItem(storageKeys.publicLayoutInitialized) === "true") return;

  const visible = ["workspace", "music", "wallpaper"];
  const archived = ["blender"];
  const deepArchived = ["manager", "unity", "steamwork", "randomrealm"];
  localStorage.setItem(storageKeys.moduleOrder, JSON.stringify([...visible, ...archived, ...deepArchived]));
  localStorage.setItem(storageKeys.moduleArchive, JSON.stringify(archived));
  localStorage.setItem(storageKeys.moduleDeepArchive, JSON.stringify(deepArchived));
  localStorage.setItem(storageKeys.moduleDeleted, "[]");
  const saved = localStorage.getItem(storageKeys.lastModule) || "";
  if (!visible.includes(saved)) localStorage.setItem(storageKeys.lastModule, "workspace");
  localStorage.setItem(storageKeys.publicLayoutInitialized, "true");
}

function saveModuleOrder(order) {
  const validIds = editionModuleSet();
  const deleted = new Set(deletedModuleIds());
  localStorage.setItem(storageKeys.moduleOrder, JSON.stringify(order.filter(id => validIds.has(id) && !deleted.has(id))));
}

function archivedModuleIds() {
  if (consoleEdition === "lite") return [];
  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem(storageKeys.moduleArchive) || "[]");
  } catch {
    saved = [];
  }
  const validIds = editionModuleSet();
  const deleted = new Set(deletedModuleIds());
  return saved.filter(id => validIds.has(id) && !deleted.has(id));
}

function deepArchivedModuleIds() {
  if (consoleEdition === "lite") return [];
  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem(storageKeys.moduleDeepArchive) || "[]");
  } catch {
    saved = [];
  }
  const validIds = editionModuleSet();
  const deleted = new Set(deletedModuleIds());
  return saved.filter(id => validIds.has(id) && !deleted.has(id));
}

function deletedModuleIds() {
  if (consoleEdition === "lite") return [];
  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem(storageKeys.moduleDeleted) || "[]");
  } catch {
    saved = [];
  }
  const validIds = editionModuleSet();
  return saved.filter(id => validIds.has(id));
}

function allArchivedModuleIds() {
  return [...new Set([...archivedModuleIds(), ...deepArchivedModuleIds()])];
}

function saveArchivedModuleIds(ids) {
  if (consoleEdition === "lite") return;
  const validIds = editionModuleSet();
  const deepSet = new Set(deepArchivedModuleIds());
  const deleted = new Set(deletedModuleIds());
  localStorage.setItem(storageKeys.moduleArchive, JSON.stringify(ids.filter(id => validIds.has(id) && !deepSet.has(id) && !deleted.has(id))));
}

function saveDeepArchivedModuleIds(ids) {
  if (consoleEdition === "lite") return;
  const validIds = editionModuleSet();
  const deleted = new Set(deletedModuleIds());
  localStorage.setItem(storageKeys.moduleDeepArchive, JSON.stringify(ids.filter(id => validIds.has(id) && !deleted.has(id))));
}

function saveDeletedModuleIds(ids) {
  if (consoleEdition === "lite") return;
  const validIds = editionModuleSet();
  localStorage.setItem(storageKeys.moduleDeleted, JSON.stringify(ids.filter(id => validIds.has(id))));
}

function visibleModuleOrder() {
  const unavailable = new Set([...allArchivedModuleIds(), ...deletedModuleIds()]);
  const visible = moduleOrder().filter(id => !unavailable.has(id));
  const currentModules = availableModules();
  const fallback = currentModules.find(item => !unavailable.has(item.id)) || currentModules.find(item => !deletedModuleIds().includes(item.id)) || firstAvailableModule();
  return visible.length ? visible : [fallback.id];
}

function saveVisibleModuleOrder(visibleIds) {
  const visibleSet = new Set(visibleIds);
  const archived = moduleOrder().filter(id => !visibleSet.has(id));
  saveModuleOrder([...visibleIds, ...archived]);
}

function moduleLabel(id) {
  return text(moduleById(id).labelKey);
}

function setArchiveExpanded(expanded) {
  archiveExpanded = expanded;
  if (!els.moduleArchive) return;
  els.moduleArchive.classList.toggle("expanded", archiveExpanded);
  els.moduleArchive.classList.toggle("deep", archiveView === "deep");
  if (els.moduleArchiveDrop) {
    els.moduleArchiveDrop.setAttribute("aria-expanded", String(archiveExpanded));
  }
}

function renderManagerLayout() {
  const visibleLabel = visibleModuleOrder().map(moduleLabel).join(" / ");
  if (els.managerVisibleTabs) {
    els.managerVisibleTabs.textContent = visibleLabel;
  }
  if (els.managerLayoutOrder) {
    els.managerLayoutOrder.textContent = visibleLabel;
  }
  if (els.managerArchivedTabs) {
    const archived = archivedModuleIds();
    const deepArchived = deepArchivedModuleIds();
    const visibleArchive = archived.length ? archived.map(moduleLabel).join(" / ") : text("archiveEmpty");
    els.managerArchivedTabs.textContent = deepArchived.length
      ? `${visibleArchive} / Deep: ${deepArchived.length}`
      : visibleArchive;
  }
}

function renderModuleArchive() {
  if (!els.moduleArchiveList) {
    renderManagerLayout();
    return;
  }

  const archived = archiveView === "deep" ? deepArchivedModuleIds() : archivedModuleIds();
  els.moduleArchiveList.innerHTML = "";
  if (els.moduleArchiveCount) {
    els.moduleArchiveCount.textContent = String(archived.length);
  }

  if (!archived.length) {
    const empty = document.createElement("div");
    empty.className = "archive-empty";
    empty.textContent = text("archiveEmpty");
    els.moduleArchiveList.appendChild(empty);
    renderManagerLayout();
    return;
  }

  for (const id of archived) {
    const item = document.createElement("button");
    let archiveOpenTimer = null;
    item.className = "archive-item";
    item.type = "button";
    item.draggable = false;
    item.dataset.moduleId = id;
    item.dataset.archiveDepth = archiveView;
    item.textContent = moduleLabel(id);
    item.title = text("archiveRestoreTitle", moduleLabel(id));
    item.addEventListener("click", event => {
      event.preventDefault();
      if (Date.now() < suppressModuleClickUntil) {
        return;
      }
      if (event.detail > 1) return;
      if (archiveOpenTimer) {
        window.clearTimeout(archiveOpenTimer);
      }
      archiveOpenTimer = window.setTimeout(() => {
        archiveOpenTimer = null;
        openArchivedModule(id);
      }, 220);
    });
    item.addEventListener("dblclick", event => {
      event.preventDefault();
      if (archiveOpenTimer) {
        window.clearTimeout(archiveOpenTimer);
        archiveOpenTimer = null;
      }
      restoreModule(id);
    });
    item.addEventListener("dragstart", event => event.preventDefault());
    item.addEventListener("pointerdown", event => beginArchivePointerDrag(event, item));
    item.addEventListener("mousedown", event => beginArchiveMouseDrag(event, item));
    els.moduleArchiveList.appendChild(item);
  }

  renderManagerLayout();
}

function moduleLayoutSnapshot() {
  return {
    order: moduleOrder(),
    archived: archivedModuleIds(),
    deepArchived: deepArchivedModuleIds(),
    deleted: deletedModuleIds(),
    active: activeModuleId
  };
}

function applyModuleLayoutHistory(state) {
  const validIds = editionModuleSet();
  const deleted = (Array.isArray(state?.deleted) ? state.deleted : []).filter(id => validIds.has(id));
  const deletedSet = new Set(deleted);
  const deepArchived = (Array.isArray(state?.deepArchived) ? state.deepArchived : [])
    .filter(id => validIds.has(id) && !deletedSet.has(id));
  const deepSet = new Set(deepArchived);
  const archived = (Array.isArray(state?.archived) ? state.archived : [])
    .filter(id => validIds.has(id) && !deletedSet.has(id) && !deepSet.has(id));
  const seen = new Set();
  const order = (Array.isArray(state?.order) ? state.order : [])
    .filter(id => {
      if (!validIds.has(id) || deletedSet.has(id) || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  for (const item of availableModules()) {
    if (!deletedSet.has(item.id) && !seen.has(item.id)) {
      order.push(item.id);
      seen.add(item.id);
    }
  }

  saveDeletedModuleIds(deleted);
  saveDeepArchivedModuleIds(deepArchived);
  saveArchivedModuleIds(archived);
  saveModuleOrder(order);
  archiveView = "main";
  setArchiveExpanded(false);
  const active = validIds.has(state?.active) && !deletedSet.has(state.active)
    ? state.active
    : visibleModuleOrder()[0];
  activateModule(active, false, { allowArchived: true, replaceUrl: true });
  renderModuleNavs();
  renderModuleArchive();
}

function recordModuleLayoutChange(beforeState, afterState = moduleLayoutSnapshot()) {
  if (historyValuesEqual(beforeState, afterState)) return;
  pushConsoleHistory({
    type: "module-layout",
    before: beforeState,
    after: afterState,
    apply: applyModuleLayoutHistory
  });
}

function archiveModule(id, options = {}) {
  if (deletedModuleIds().includes(id)) return;
  const beforeState = options.beforeState || moduleLayoutSnapshot();
  const visible = visibleModuleOrder().filter(item => item !== id);
  if (!visible.length) return;

  const archived = archivedModuleIds();
  const deepArchived = deepArchivedModuleIds().filter(item => item !== id);
  saveDeepArchivedModuleIds(deepArchived);
  if (!archived.includes(id)) {
    saveArchivedModuleIds([...archived, id]);
  }

  saveVisibleModuleOrder(visible);
  archiveView = "main";
  setArchiveExpanded(true);

  if (activeModuleId === id) {
    activateModule(visible[0], true);
  } else {
    renderModuleNavs();
    renderModuleArchive();
  }
  if (options.record !== false) {
    recordModuleLayoutChange(beforeState);
  }
}

function restoreModule(id, options = {}) {
  const beforeState = options.beforeState || moduleLayoutSnapshot();
  const archived = archivedModuleIds().filter(item => item !== id);
  const deepArchived = deepArchivedModuleIds().filter(item => item !== id);
  const visible = visibleModuleOrder().filter(item => item !== id);
  const remainingArchived = moduleOrder().filter(item => archived.includes(item) || deepArchived.includes(item));
  saveArchivedModuleIds(archived);
  saveDeepArchivedModuleIds(deepArchived);
  saveModuleOrder([...visible, id, ...remainingArchived]);
  setArchiveExpanded(false);
  activateModule(id, true);
  if (options.record !== false) {
    recordModuleLayoutChange(beforeState);
  }
}

function deepArchiveModule(id, options = {}) {
  if (deletedModuleIds().includes(id)) return;
  const beforeState = options.beforeState || moduleLayoutSnapshot();
  const archived = archivedModuleIds().filter(item => item !== id);
  const deepArchived = deepArchivedModuleIds();
  saveArchivedModuleIds(archived);
  if (!deepArchived.includes(id)) {
    saveDeepArchivedModuleIds([...deepArchived, id]);
  }
  archiveView = "main";
  renderModuleNavs();
  renderModuleArchive();
  if (options.record !== false) {
    recordModuleLayoutChange(beforeState);
  }
}

function permanentlyDeleteModule(id, options = {}) {
  if (!isModuleId(id)) return false;
  const beforeState = options.beforeState || moduleLayoutSnapshot();
  const deleted = deletedModuleIds();
  if (deleted.includes(id)) return false;
  const remaining = modules.map(item => item.id).filter(item => item !== id && !deleted.includes(item));
  if (!remaining.length) return false;

  saveDeletedModuleIds([...deleted, id]);
  saveArchivedModuleIds(archivedModuleIds().filter(item => item !== id));
  saveDeepArchivedModuleIds(deepArchivedModuleIds().filter(item => item !== id));
  saveModuleOrder(moduleOrder().filter(item => item !== id));
  if (lastModuleId() === id) {
    localStorage.removeItem(storageKeys.lastModule);
  }
  if (activeModuleId === id) {
    activateModule(visibleModuleOrder()[0], true);
  } else {
    renderModuleNavs();
    renderModuleArchive();
  }
  if (options.record !== false) {
    recordModuleLayoutChange(beforeState);
  }
  return true;
}

function restoreAllArchivedModules(options = {}) {
  const archived = archivedModuleIds();
  if (!archived.length) {
    setArchiveExpanded(false);
    return;
  }
  const beforeState = options.beforeState || moduleLayoutSnapshot();

  const deepArchived = deepArchivedModuleIds();
  const visible = visibleModuleOrder().filter(id => !archived.includes(id));
  saveArchivedModuleIds([]);
  saveModuleOrder([...visible, ...archived, ...deepArchived]);
  setArchiveExpanded(false);
  activateModule(activeModuleId, false);
  if (options.record !== false) {
    recordModuleLayoutChange(beforeState);
  }
}

function resetArchiveRightRelease() {
  archiveRightReleaseCount = 0;
  if (archiveRightReleaseTimer) {
    window.clearTimeout(archiveRightReleaseTimer);
    archiveRightReleaseTimer = null;
  }
}

function handleArchiveRightRelease(event) {
  if (event.button !== 2) return;
  event.preventDefault();
  event.stopPropagation();

  archiveRightReleaseCount += 1;
  if (archiveRightReleaseCount >= 2) {
    resetArchiveRightRelease();
    restoreAllArchivedModules();
    return;
  }

  if (archiveRightReleaseTimer) {
    window.clearTimeout(archiveRightReleaseTimer);
  }
  archiveRightReleaseTimer = window.setTimeout(resetArchiveRightRelease, 520);
}

function moduleIdsFromNavWithPlaceholder(nav, placeholder, insertedId) {
  const ids = [];
  for (const child of nav.children) {
    if (child === placeholder) {
      ids.push(insertedId);
      continue;
    }
    if (child.classList.contains("module-link") && !child.classList.contains("module-drag-placeholder")) {
      const id = child.dataset.moduleId;
      if (id) ids.push(id);
    }
  }
  return ids;
}

function moduleIdsFromNav(nav) {
  return Array.from(nav.querySelectorAll(".module-link:not(.module-drag-placeholder)"))
    .map(link => link.dataset.moduleId)
    .filter(Boolean);
}

function moduleNavLinks(nav) {
  return Array.from(nav.querySelectorAll(".module-link:not(.dragging):not(.module-drag-placeholder)"));
}

function animateModuleNav(nav, mutate) {
  const links = moduleNavLinks(nav);
  const first = new Map(
    links.map(link => [link.dataset.moduleId, link.getBoundingClientRect()])
  );
  for (const link of links) {
    link.getAnimations().forEach(animation => animation.cancel());
  }
  mutate();

  for (const link of moduleNavLinks(nav)) {
    const before = first.get(link.dataset.moduleId);
    if (!before) continue;
    const after = link.getBoundingClientRect();
    const dx = before.left - after.left;
    const dy = before.top - after.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    link.animate(
      [
        { transform: `translate(${dx}px, ${dy}px)` },
        { transform: "translate(0, 0)" }
      ],
      {
        duration: 260,
        easing: "cubic-bezier(0.25, 0.1, 0.25, 1)"
      }
    );
  }
}

function settleDraggedModule(nav, link, placeholder, animate = true) {
  const startRect = link.getBoundingClientRect();
  const targetRect = placeholder.getBoundingClientRect();
  let settled = false;

  const cleanup = () => {
    if (settled) return;
    settled = true;
    nav.insertBefore(link, placeholder);
    placeholder.remove();
    link.getAnimations().forEach(animation => animation.cancel());
    link.classList.remove("dragging", "settling");
    nav.classList.remove("drag-active");
    link.style.removeProperty("width");
    link.style.removeProperty("height");
    link.style.removeProperty("left");
    link.style.removeProperty("top");
  };

  if (!animate || Math.abs(startRect.left - targetRect.left) < 1 && Math.abs(startRect.top - targetRect.top) < 1) {
    cleanup();
    return Promise.resolve();
  }

  link.classList.add("settling");
  link.style.width = `${startRect.width}px`;
  link.style.height = `${startRect.height}px`;
  link.style.left = `${startRect.left}px`;
  link.style.top = `${startRect.top}px`;

  const animation = link.animate(
    [
      {
        left: `${startRect.left}px`,
        top: `${startRect.top}px`,
        width: `${startRect.width}px`,
        height: `${startRect.height}px`,
        transform: "scale(1.04)"
      },
      {
        left: `${targetRect.left}px`,
        top: `${targetRect.top}px`,
        width: `${targetRect.width}px`,
        height: `${targetRect.height}px`,
        transform: "scale(1)"
      }
    ],
    {
      duration: 340,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      fill: "forwards"
    }
  );

  return animation.finished.catch(() => {}).then(cleanup);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function clampDragPosition(clientX, clientY, offsetX, offsetY, width, height) {
  const page = document.documentElement;
  const margin = 4;
  const maxLeft = Math.max(margin, page.clientWidth - width - margin);
  const maxTop = Math.max(margin, page.clientHeight - height - margin);
  return {
    left: clamp(clientX - offsetX, margin, maxLeft),
    top: clamp(clientY - offsetY, margin, maxTop)
  };
}

function createDragDirectionTracker(startX) {
  let anchorX = startX;
  let directionX = 0;
  return clientX => {
    const dx = clientX - anchorX;
    if (Math.abs(dx) >= 8) {
      directionX = Math.sign(dx);
      anchorX = clientX;
    }
    return directionX;
  };
}

function createMusicDragDirectionTracker(startValue) {
  let anchorValue = startValue;
  let direction = 0;
  return value => {
    const delta = value - anchorValue;
    const distance = Math.abs(delta);
    const nextDirection = Math.sign(delta);
    if (!nextDirection) return direction;
    const isReverse = direction !== 0 && nextDirection !== direction;
    const threshold = direction === 0 ? 6 : isReverse ? 18 : 8;
    if (distance >= threshold) {
      direction = nextDirection;
      anchorValue = value;
    }
    return direction;
  };
}

function dragInsertionProbeX(probeX, draggedRect = null, directionX = 0) {
  if (draggedRect && directionX > 0 && Number.isFinite(draggedRect.right)) {
    return draggedRect.right;
  }
  if (draggedRect && directionX < 0 && Number.isFinite(draggedRect.left)) {
    return draggedRect.left;
  }
  return probeX;
}

function updateArchiveDragState(clientX, clientY) {
  if (!els.moduleArchive) return false;

  const dropRect = (els.moduleArchiveDrop || els.moduleArchive).getBoundingClientRect();
  const drawer = els.moduleArchive.querySelector(".archive-drawer");
  const drawerRect = drawer ? drawer.getBoundingClientRect() : null;
  const pointInRect = rect =>
    clientX >= rect.left &&
    clientX <= rect.right &&
    clientY >= rect.top &&
    clientY <= rect.bottom;
  const overArchive = pointInRect(dropRect) || (archiveExpanded && drawerRect && pointInRect(drawerRect));

  els.moduleArchive.classList.toggle("drag-over", overArchive);
  if (overArchive) {
    setArchiveExpanded(true);
  }
  return overArchive;
}

function clearArchiveDragState() {
  if (els.moduleArchive) {
    els.moduleArchive.classList.remove("drag-over");
  }
}

function setModuleDraggingCursor(isDragging) {
  document.body.classList.toggle("module-dragging", Boolean(isDragging));
}

function isPointInsideArchive(clientX, clientY) {
  if (!els.moduleArchive) return false;

  const dropRect = (els.moduleArchiveDrop || els.moduleArchive).getBoundingClientRect();
  const drawer = els.moduleArchive.querySelector(".archive-drawer");
  const drawerRect = drawer ? drawer.getBoundingClientRect() : null;
  const pointInRect = rect =>
    clientX >= rect.left &&
    clientX <= rect.right &&
    clientY >= rect.top &&
    clientY <= rect.bottom;

  return pointInRect(dropRect) || (drawerRect && pointInRect(drawerRect));
}

function isPointOnArchiveDrop(clientX, clientY) {
  if (!els.moduleArchive) return false;
  const rect = (els.moduleArchiveDrop || els.moduleArchive).getBoundingClientRect();
  return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom;
}

function insertionTargetForDrag(nav, placeholder, draggedRect, directionX = 0) {
  const children = Array.from(nav.children);
  const placeholderIndex = children.indexOf(placeholder);
  const draggedMidY = draggedRect.top + draggedRect.height / 2;
  let before = placeholder.nextElementSibling;
  const links = moduleNavLinks(nav);

  if (directionX > 0) {
    for (const link of links) {
      const linkIndex = children.indexOf(link);
      if (linkIndex <= placeholderIndex) continue;
      const rect = link.getBoundingClientRect();
      const sameRow = draggedMidY >= rect.top - 8 && draggedMidY <= rect.bottom + 8;
      if (!sameRow) continue;

      const threshold = rect.left + rect.width * 2 / 3;
      if (draggedRect.right > threshold) {
        before = link.nextElementSibling;
      }
    }
  }

  if (directionX < 0) {
    for (const link of links.slice().reverse()) {
      const linkIndex = children.indexOf(link);
      if (linkIndex >= placeholderIndex) continue;
      const rect = link.getBoundingClientRect();
      const sameRow = draggedMidY >= rect.top - 8 && draggedMidY <= rect.bottom + 8;
      if (!sameRow) continue;

      const threshold = rect.left + rect.width / 3;
      if (draggedRect.left < threshold) {
        before = link;
      }
    }
  }

  return before;
}

function moveDraggedModule(nav, placeholder, draggedRect, directionX = 0) {
  const before = insertionTargetForDrag(nav, placeholder, draggedRect, directionX);
  if (before === placeholder || before === placeholder.nextElementSibling) return;
  animateModuleNav(nav, () => {
    nav.insertBefore(placeholder, before);
  });
}

function isPointNearModuleNav(nav, clientX, clientY) {
  if (!nav) return false;
  const rect = nav.getBoundingClientRect();
  return (
    clientX >= rect.left - 18 &&
    clientX <= rect.right + 96 &&
    clientY >= rect.top - 18 &&
    clientY <= rect.bottom + 18
  );
}

function createArchiveReturnSession(source, startX, startY) {
  const id = source.dataset.moduleId;
  const sourceDepth = source.dataset.archiveDepth || "main";
  const beforeState = moduleLayoutSnapshot();
  const nav = document.querySelector("[data-module-nav]");
  const rect = source.getBoundingClientRect();
  const placeholder = document.createElement("span");
  const ghost = document.createElement("button");
  const label = moduleLabel(id);
  let placeholderPlaced = false;
  let outsideArchive = false;
  let overArchiveDrop = false;

  placeholder.className = "module-link module-drag-placeholder";
  placeholder.style.width = `${Math.max(rect.width, 64)}px`;
  placeholder.style.height = "32px";
  placeholder.setAttribute("aria-hidden", "true");

  ghost.className = "module-link archive-return-ghost dragging";
  ghost.type = "button";
  ghost.textContent = label;
  ghost.style.width = `${Math.max(rect.width, 64)}px`;
  ghost.style.height = "32px";
  document.body.appendChild(ghost);
  source.classList.add("archive-source-dragging");
  setModuleDraggingCursor(true);

  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  const trackDirectionX = createDragDirectionTracker(startX);

  const move = (clientX, clientY) => {
    const page = document.documentElement;
    const width = Math.max(rect.width, 64);
    const height = 32;
    const clamped = clampDragPosition(clientX, clientY, offsetX, offsetY, width, height);
    const directionX = trackDirectionX(clientX);
    ghost.style.left = `${clamped.left}px`;
    ghost.style.top = `${clamped.top}px`;
    outsideArchive = !isPointInsideArchive(clientX, clientY);
    overArchiveDrop = isPointOnArchiveDrop(clientX, clientY);
    els.moduleArchive?.classList.toggle("drag-over", overArchiveDrop);

    const overNav = isPointNearModuleNav(nav, clientX, clientY);
    nav.classList.toggle("drag-active", overNav);
    if (!overNav) {
      placeholder.remove();
      placeholderPlaced = false;
      return;
    }

    if (!placeholderPlaced) {
      nav.appendChild(placeholder);
      placeholderPlaced = true;
    }
    moveDraggedModule(
      nav,
      placeholder,
      {
        left: clamp(clamped.left, 0, page.clientWidth),
        right: clamp(clamped.left + width, 0, page.clientWidth),
        top: clamp(clamped.top, 0, page.clientHeight),
        bottom: clamp(clamped.top + height, 0, page.clientHeight),
        width,
        height
      },
      directionX
    );
  };

  const finish = () => {
    const restored = placeholderPlaced && placeholder.parentNode === nav;
    let nextOrder = [];
    if (restored) {
      nextOrder = moduleIdsFromNavWithPlaceholder(nav, placeholder, id);
    } else if (outsideArchive) {
      nextOrder = [...visibleModuleOrder().filter(item => item !== id), id];
    }

    placeholder.remove();
    ghost.remove();
    source.classList.remove("archive-source-dragging");
    nav.classList.remove("drag-active");
    els.moduleArchive?.classList.remove("drag-over");
    setModuleDraggingCursor(false);

    if (!restored && !outsideArchive) {
      if (sourceDepth === "main" && overArchiveDrop) {
        deepArchiveModule(id, { beforeState });
        return true;
      }
      if (sourceDepth === "deep" && overArchiveDrop) {
        return permanentlyDeleteModule(id, { beforeState });
      }
      return false;
    }

    const archived = archivedModuleIds().filter(item => item !== id);
    const deepArchived = deepArchivedModuleIds().filter(item => item !== id);
    const remainingArchived = moduleOrder().filter(item => archived.includes(item) || deepArchived.includes(item));
    saveArchivedModuleIds(archived);
    saveDeepArchivedModuleIds(deepArchived);
    saveModuleOrder([...nextOrder, ...remainingArchived]);
    setArchiveExpanded(false);
    activateModule(id, true);
    recordModuleLayoutChange(beforeState);
    return true;
  };

  move(startX, startY);
  return { finish, move };
}

function createModuleDragSession(nav, link, startX, startY) {
  const rect = link.getBoundingClientRect();
  const placeholder = document.createElement("span");
  placeholder.className = "module-link module-drag-placeholder";
  placeholder.style.width = `${rect.width}px`;
  placeholder.style.height = `${rect.height}px`;
  placeholder.setAttribute("aria-hidden", "true");

  link.parentNode.insertBefore(placeholder, link);
  document.body.appendChild(link);

  link.classList.add("dragging");
  nav.classList.add("drag-active");
  setModuleDraggingCursor(true);
  link.style.width = `${rect.width}px`;
  link.style.height = `${rect.height}px`;
  link.style.left = `${rect.left}px`;
  link.style.top = `${rect.top}px`;

  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  const trackDirectionX = createDragDirectionTracker(startX);
  let overArchive = false;

  const move = (clientX, clientY) => {
    const page = document.documentElement;
    const clamped = clampDragPosition(clientX, clientY, offsetX, offsetY, rect.width, rect.height);
    const directionX = trackDirectionX(clientX);
    link.style.left = `${clamped.left}px`;
    link.style.top = `${clamped.top}px`;
    overArchive = updateArchiveDragState(clientX, clientY);
    if (!overArchive) {
      moveDraggedModule(
        nav,
        placeholder,
        {
          left: clamp(clamped.left, 0, page.clientWidth),
          right: clamp(clamped.left + rect.width, 0, page.clientWidth),
          top: clamp(clamped.top, 0, page.clientHeight),
          bottom: clamp(clamped.top + rect.height, 0, page.clientHeight),
          width: rect.width,
          height: rect.height
        },
        directionX
      );
    }
  };

  const finish = ({ animate = true } = {}) => {
    setModuleDraggingCursor(false);
    return settleDraggedModule(nav, link, placeholder, animate);
  };

  move(startX, startY);
  return { finish, isOverArchive: () => overArchive, move };
}

function beginModulePointerDrag(event, nav, link) {
  if (event.button !== 0 || event.pointerType === "mouse") return;

  lastModulePointerStart = Date.now();
  const startX = event.clientX;
  const startY = event.clientY;
  let dragging = false;
  let dragSession = null;
  let finished = false;
  let lastClientX = startX;
  let lastClientY = startY;

  link.setPointerCapture(event.pointerId);

  const finish = () => {
    if (finished) return;
    finished = true;
    link.removeEventListener("pointermove", move);
    link.removeEventListener("pointerup", up);
    link.removeEventListener("pointercancel", up);
    if (!dragging) return;

    const beforeState = moduleLayoutSnapshot();
    const moduleId = link.dataset.moduleId || draggedModuleId;
    const shouldArchive = dragSession.isOverArchive() || isPointInsideArchive(lastClientX, lastClientY);
    clearArchiveDragState();
    draggedModuleId = "";
    suppressModuleClickUntil = Date.now() + 350;
    dragSession.finish({ animate: !shouldArchive }).then(() => {
      if (shouldArchive) {
        archiveModule(moduleId, { beforeState });
      } else {
        const nextVisibleOrder = moduleIdsFromNav(nav);
        if (!nextVisibleOrder.includes(moduleId)) {
          archiveModule(moduleId, { beforeState });
          return;
        }
        saveVisibleModuleOrder(nextVisibleOrder);
        renderModuleNavs();
        renderModuleArchive();
        recordModuleLayoutChange(beforeState);
      }
    });
  };

  const move = moveEvent => {
    lastClientX = moveEvent.clientX;
    lastClientY = moveEvent.clientY;
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 5) return;

    if (!dragging) {
      dragging = true;
      draggedModuleId = link.dataset.moduleId || "";
      dragSession = createModuleDragSession(nav, link, startX, startY);
    }

    moveEvent.preventDefault();
    dragSession.move(moveEvent.clientX, moveEvent.clientY);
  };

  const up = upEvent => {
    lastClientX = upEvent.clientX;
    lastClientY = upEvent.clientY;
    if (link.hasPointerCapture(upEvent.pointerId)) {
      link.releasePointerCapture(upEvent.pointerId);
    }
    finish();
  };

  link.addEventListener("pointermove", move);
  link.addEventListener("pointerup", up);
  link.addEventListener("pointercancel", up);
}

function beginModuleMouseDrag(event, nav, link) {
  if (event.button !== 0 || Date.now() - lastModulePointerStart < 80) return;

  const startX = event.clientX;
  const startY = event.clientY;
  let dragging = false;
  let dragSession = null;
  let finished = false;
  let lastClientX = startX;
  let lastClientY = startY;

  const finish = () => {
    if (finished) return;
    finished = true;
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    if (!dragging) return;

    const beforeState = moduleLayoutSnapshot();
    const moduleId = link.dataset.moduleId || draggedModuleId;
    const shouldArchive = dragSession.isOverArchive() || isPointInsideArchive(lastClientX, lastClientY);
    clearArchiveDragState();
    draggedModuleId = "";
    suppressModuleClickUntil = Date.now() + 350;
    dragSession.finish({ animate: !shouldArchive }).then(() => {
      if (shouldArchive) {
        archiveModule(moduleId, { beforeState });
      } else {
        const nextVisibleOrder = moduleIdsFromNav(nav);
        if (!nextVisibleOrder.includes(moduleId)) {
          archiveModule(moduleId, { beforeState });
          return;
        }
        saveVisibleModuleOrder(nextVisibleOrder);
        renderModuleNavs();
        renderModuleArchive();
        recordModuleLayoutChange(beforeState);
      }
    });
  };

  const move = moveEvent => {
    lastClientX = moveEvent.clientX;
    lastClientY = moveEvent.clientY;
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 5) return;

    if (!dragging) {
      dragging = true;
      draggedModuleId = link.dataset.moduleId || "";
      dragSession = createModuleDragSession(nav, link, startX, startY);
    }

    moveEvent.preventDefault();
    dragSession.move(moveEvent.clientX, moveEvent.clientY);
  };

  const up = upEvent => {
    lastClientX = upEvent.clientX;
    lastClientY = upEvent.clientY;
    finish();
  };

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function beginArchivePointerDrag(event, item) {
  if (event.button !== 0 || event.pointerType === "mouse") return;

  lastArchivePointerStart = Date.now();
  const startX = event.clientX;
  const startY = event.clientY;
  let dragging = false;
  let dragSession = null;

  item.setPointerCapture(event.pointerId);

  const finish = () => {
    item.removeEventListener("pointermove", move);
    item.removeEventListener("pointerup", up);
    item.removeEventListener("pointercancel", up);
    if (!dragging) return;

    dragSession.finish();
    suppressModuleClickUntil = Date.now() + 350;
  };

  const move = moveEvent => {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 5) return;

    if (!dragging) {
      dragging = true;
      dragSession = createArchiveReturnSession(item, startX, startY);
    }

    moveEvent.preventDefault();
    dragSession.move(moveEvent.clientX, moveEvent.clientY);
  };

  const up = upEvent => {
    if (item.hasPointerCapture(upEvent.pointerId)) {
      item.releasePointerCapture(upEvent.pointerId);
    }
    finish();
  };

  item.addEventListener("pointermove", move);
  item.addEventListener("pointerup", up);
  item.addEventListener("pointercancel", up);
}

function beginArchiveMouseDrag(event, item) {
  if (event.button !== 0 || Date.now() - lastArchivePointerStart < 80) return;

  const startX = event.clientX;
  const startY = event.clientY;
  let dragging = false;
  let dragSession = null;

  const finish = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    if (!dragging) return;

    dragSession.finish();
    suppressModuleClickUntil = Date.now() + 350;
  };

  const move = moveEvent => {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 5) return;

    if (!dragging) {
      dragging = true;
      dragSession = createArchiveReturnSession(item, startX, startY);
    }

    moveEvent.preventDefault();
    dragSession.move(moveEvent.clientX, moveEvent.clientY);
  };

  const up = () => finish();

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function renderModuleNavs() {
  const navs = document.querySelectorAll("[data-module-nav]");
  if (!navs.length) return;

  const order = visibleModuleOrder();
  const byId = new Map(modules.map(item => [item.id, item]));
  const items = order.map(id => byId.get(id)).filter(Boolean);

  for (const nav of navs) {
    const currentLinks = Array.from(nav.querySelectorAll(":scope > .module-link"));
    const canReuse = currentLinks.length === items.length
      && currentLinks.every((link, index) => link.dataset.moduleId === items[index].id);
    if (canReuse) {
      currentLinks.forEach((link, index) => {
        const item = items[index];
        link.classList.toggle("active", item.id === activeModuleId);
        link.href = item.href;
        link.textContent = text(item.labelKey);
      });
      continue;
    }

    nav.innerHTML = "";
    for (const item of items) {
      const link = document.createElement("a");
      link.className = `module-link ${item.id === activeModuleId ? "active" : ""}`;
      link.href = item.href;
      link.draggable = false;
      link.dataset.moduleId = item.id;
      link.textContent = text(item.labelKey);
      link.addEventListener("click", event => {
        if (Date.now() < suppressModuleClickUntil) {
          event.preventDefault();
          return;
        }
        if (!canActivateModuleInPlace(item.id)) {
          rememberActiveModule(item.id);
          return;
        }
        event.preventDefault();
        activateModuleFromUser(item.id, true);
      });
      link.addEventListener("dragstart", event => event.preventDefault());
      link.addEventListener("pointerdown", event => beginModulePointerDrag(event, nav, link));
      link.addEventListener("mousedown", event => beginModuleMouseDrag(event, nav, link));
      nav.appendChild(link);
    }
  }
  renderModuleArchive();
}

function text(key, ...args) {
  const value = i18n[language][key];
  return typeof value === "function" ? value(...args) : value;
}

function formatClock(date) {
  return date.toLocaleTimeString(language === "zh" ? "zh-CN" : "en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return text("noSize");
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function cleanTrackName(name) {
  return String(name || "")
    .replace(/_/g, " ")
    .replace(/^\d{3,4}[-\s]+/, "")
    .replace(/[-\s]+[A-Za-z0-9_-]{11}$/, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[\s-]+|[\s-]+$/g, "");
}

const trackDisplayAliases = new Map([
  ["a touch of class - around the world la la la la la official video", "A Touch Of Class - All Around the World"],
  ["daft punk - get lucky official audio ft. pharrell williams nile rodgers", "Daft Punk - Get Lucky"],
  ["aaron smith - dancin krono remix - lyrics", "Aaron Smith - Dancin (KRONO Remix)"],
  ["horizon blue-vf isvy7mua", "Horizon Blue"],
  ["lanota overrapid wacca arcaea phigros stasis - maozon", "Maozon"],
  ["muse dash cytus ii phigros arcaea maimai final step - lime", "Lime - Final Step"],
  ["phigros cytus ii luminescence - fomiki cloudie music", "Fomiki - Luminescence"]
]);

function displayTrackName(name) {
  const cleanName = cleanTrackName(name);
  const alias = trackDisplayAliases.get(cleanName.toLocaleLowerCase());
  if (alias) return alias;

  const existingA8 = cleanName.match(/^a8\s*-\s*(.*)$/i);
  if (existingA8) {
    const suffix = existingA8[1].trim().replace(/^[\s-]+|[\s-]+$/g, "");
    return suffix ? `A8 - ${suffix}` : "A8";
  }

  if (!/(asphalt\s*8|airborne)/i.test(cleanName)) return cleanName;

  let song = cleanName
    .replace(/^asphalt\s*8\s*(?:new\s+song\s*)?/i, "")
    .replace(/\s+asphalt\s*8\b.*$/i, "")
    .replace(/\s*-\s*by\b.*$/i, "")
    .replace(/\s*-\s*dj\b.*$/i, "")
    .replace(/\s+-\s+.*$/, "")
    .replace(/\b(?:official|video|audio|ost|soundtrack)\b.*$/i, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[\s-]+|[\s-]+$/g, "");

  return `A8 - ${song || cleanName}`;
}

function trackIdentityKey(name) {
  return displayTrackName(name)
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, "");
}

function setStatus(message) {
  if (!els.statusText) return;
  els.statusText.textContent = message || text("readyStatus");
}

function activeMusicAddMode() {
  return els.musicAddMenu?.dataset.mode || "";
}

function setMusicAddStatus(message) {
  if (els.musicAddStatus) {
    els.musicAddStatus.textContent = message || "";
  }
}

function setMusicLinkStatus(message) {
  musicLinkNotice = message || "";
  const node = document.getElementById("musicLinkStatus");
  if (node) {
    node.textContent = musicLinkNotice;
  }
  if (activeMusicAddMode() === "url") {
    setMusicAddStatus(musicLinkNotice);
  }
}

function setMusicLibraryStatus(message) {
  musicLibraryNotice = message || "";
  const node = document.getElementById("musicLibraryStatus");
  if (node) {
    node.textContent = musicLibraryNotice;
  }
  if (activeMusicAddMode() === "library") {
    setMusicAddStatus(musicLibraryNotice);
  }
}

function applyTheme() {
  theme = normalizeTheme(theme);
  document.documentElement.dataset.theme = theme;
  if (els.themeToggle) {
    els.themeToggle.textContent = text(themeLabelKey(nextTheme(theme)));
  }
}

function applyThemeHistory(nextMode) {
  setTheme(nextMode, { record: false });
}

function recordThemeChange(beforeMode, afterMode) {
  const before = normalizeTheme(beforeMode);
  const after = normalizeTheme(afterMode);
  if (before === after) return;
  pushConsoleHistory({
    type: "theme",
    before,
    after,
    apply: applyThemeHistory
  });
}

function setTheme(nextMode, options = {}) {
  const before = theme;
  theme = normalizeTheme(nextMode);
  localStorage.setItem(storageKeys.theme, theme);
  applyTheme();
  if (options.record !== false) {
    recordThemeChange(before, theme);
  }
}

function applyTutorialMode(options = {}) {
  tutorialMode = Boolean(tutorialMode);
  document.documentElement.classList.toggle("tutorial-mode", tutorialMode);
  if (document.body) {
    document.body.classList.toggle("tutorial-mode", tutorialMode);
  }
  if (els.tutorialModeToggle) {
    els.tutorialModeToggle.classList.toggle("active", tutorialMode);
    els.tutorialModeToggle.setAttribute("aria-pressed", String(tutorialMode));
    const label = text(tutorialMode ? "tutorialModeOn" : "tutorialModeOff");
    els.tutorialModeToggle.title = label;
    els.tutorialModeToggle.setAttribute("aria-label", label);
  }
  if (options.persist) {
    localStorage.setItem(storageKeys.tutorialMode, tutorialMode ? "true" : "false");
  }
}

function toggleTutorialMode() {
  tutorialMode = !tutorialMode;
  applyTutorialMode({ persist: true });
}

function applyConsoleEdition(nextEdition, options = {}) {
  const previousEdition = consoleEdition;
  consoleEdition = normalizeEdition(nextEdition);
  document.documentElement.dataset.edition = consoleEdition;
  if (document.body) {
    document.body.dataset.consoleEdition = consoleEdition;
  }
  ensureEditionModuleLayout();

  if (!isModuleAvailable(activeModuleId) || allArchivedModuleIds().includes(activeModuleId) || deletedModuleIds().includes(activeModuleId)) {
    activeModuleId = visibleModuleOrder()[0] || firstAvailableModule().id;
  }

  const active = moduleById(activeModuleId);
  for (const panel of document.querySelectorAll("[data-module-panel]")) {
    const moduleId = panel.dataset.modulePanel;
    panel.hidden = !isModuleAvailable(moduleId) || moduleId !== active.id;
  }

  if (currentPageName() !== active.href) {
    history.replaceState({ moduleId: active.id }, "", moduleUrl(active.href));
  }

  if (previousEdition !== consoleEdition || options.forceRender) {
    renderModuleNavs();
  }

  if (options.activate !== false) {
    activateModule(active.id, false);
  }
}

async function loadConsoleConfig() {
  if (hasEditionQuery) return;
  try {
    const response = await fetch("/api/console/config");
    if (!response.ok) return;
    const payload = await response.json();
    if (payload?.edition) {
      applyConsoleEdition(payload.edition);
    }
  } catch {
    // Static file previews default to the developer edition.
  }
}

function applyLanguage() {
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = text(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-aria]")) {
    node.setAttribute("aria-label", text(node.dataset.i18nAria));
    node.title = text(node.dataset.i18nAria);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", text(node.dataset.i18nPlaceholder));
  }
  if (els.languageToggle) {
    els.languageToggle.textContent = language === "zh" ? "CN" : "EN";
  }
  applyTheme();
  applyTutorialMode();
  activateModule(activeModuleId, false);
  if (hasWallpaper) renderWallpapers();
  if (hasMusic) {
    updateMusicAddCookieLabel();
    renderMusic();
    renderMusicLibraries();
  }
  if (hasMaterialWorkspace) {
    renderDownloadIntake();
    renderMaterialImport();
  }
  if (hasWorkspace) {
    renderGithubDownloads();
    renderConsoleUpdate();
    renderDesktopLayout();
    renderFeedback();
    renderWorkspaceTodos();
  }
  if (hasRandomRealmArtTools()) {
    renderRandomRealmUsedTextures();
    setRandomRealmArtStatus(randomRealmArtNotice);
  }
  if (blenderGithubShareState) {
    renderBlenderGithubShare(blenderGithubShareState, { preserveForm: true });
  }
  tick();
}

function loadWallpaperOrder() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKeys.wallpaperOrder) || "[]");
    return sanitizeMusicTierOrder(raw);
  } catch {
    return [];
  }
}

function saveWallpaperOrderLocal() {
  localStorage.setItem(storageKeys.wallpaperOrder, JSON.stringify(wallpaperOrder));
}

function orderedWallpapers() {
  const orderIndex = new Map(wallpaperOrder.map((path, index) => [path, index]));
  return wallpapers
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const aOrder = orderIndex.has(a.item.path) ? orderIndex.get(a.item.path) : Number.MAX_SAFE_INTEGER + a.index;
      const bOrder = orderIndex.has(b.item.path) ? orderIndex.get(b.item.path) : Number.MAX_SAFE_INTEGER + b.index;
      return aOrder - bOrder;
    })
    .map(entry => entry.item);
}

function syncWallpaperOrder(serverOrder = null) {
  const existingPaths = new Set(wallpapers.map(item => item.path));
  const sourceOrder = Array.isArray(serverOrder) ? serverOrder : wallpaperOrder;
  const nextOrder = sanitizeMusicTierOrder(sourceOrder).filter(path => existingPaths.has(path));
  for (const item of wallpapers) {
    if (!nextOrder.includes(item.path)) {
      nextOrder.push(item.path);
    }
  }
  const changed = nextOrder.length !== wallpaperOrder.length || nextOrder.some((path, index) => path !== wallpaperOrder[index]);
  wallpaperOrder = nextOrder;
  if (changed) {
    saveWallpaperOrderLocal();
    if (!Array.isArray(serverOrder)) persistWallpaperOrderNow();
  }
}

function persistWallpaperOrderNow() {
  saveWallpaperOrderLocal();
  if (!hasWallpaper) return;
  fetch("/api/wallpapers/order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order: wallpaperOrder }),
    keepalive: true
  }).catch(() => {});
}

function wallpaperOrderSnapshot() {
  return orderedWallpapers().map(item => item.path);
}

function wallpaperCardsForAnimation() {
  if (!els.wallpaperDock) return [];
  return Array.from(els.wallpaperDock.querySelectorAll(".wallpaper-card:not(.dragging):not(.wallpaper-placeholder)"));
}

function animateWallpaperReflow(mutate) {
  const cards = wallpaperCardsForAnimation();
  const first = new Map(cards.map(card => [card.dataset.wallpaperPath, card.getBoundingClientRect()]));
  for (const card of cards) {
    card.getAnimations().forEach(animation => animation.cancel());
  }

  mutate();

  for (const card of wallpaperCardsForAnimation()) {
    const before = first.get(card.dataset.wallpaperPath);
    if (!before) continue;
    const after = card.getBoundingClientRect();
    const dx = before.left - after.left;
    const dy = before.top - after.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    card.animate(
      [
        { transform: `translate(${dx}px, ${dy}px)` },
        { transform: "translate(0, 0)" }
      ],
      {
        duration: 180,
        easing: "cubic-bezier(0.25, 0.1, 0.25, 1)"
      }
    );
  }
}

function cleanWallpaperOrder(order) {
  const existingPaths = new Set(wallpapers.map(item => item.path));
  const seen = new Set();
  const clean = [];
  for (const path of sanitizeMusicTierOrder(order)) {
    if (!existingPaths.has(path) || seen.has(path)) continue;
    seen.add(path);
    clean.push(path);
  }
  for (const item of wallpapers) {
    if (!seen.has(item.path)) {
      clean.push(item.path);
    }
  }
  return clean;
}

function setWallpaperOrder(nextOrder, options = {}) {
  const cleanOrder = cleanWallpaperOrder(nextOrder);
  const apply = () => {
    wallpaperOrder = cleanOrder;
    if (options.persist !== false) {
      persistWallpaperOrderNow();
    } else {
      saveWallpaperOrderLocal();
    }
    renderWallpapers();
  };
  if (options.animate === false) {
    apply();
  } else {
    animateWallpaperReflow(apply);
  }
}

function orderWithMovedPath(order, path, beforePath = "") {
  const currentOrder = cleanWallpaperOrder(order).filter(itemPath => itemPath !== path);
  const insertIndex = beforePath && beforePath !== path ? currentOrder.indexOf(beforePath) : -1;
  if (insertIndex >= 0) {
    currentOrder.splice(insertIndex, 0, path);
  } else {
    currentOrder.push(path);
  }
  return currentOrder;
}

function recordWallpaperOrderChange(beforeOrder, afterOrder) {
  if (historyValuesEqual(beforeOrder, afterOrder)) return;
  pushConsoleHistory({
    type: "wallpaper-order",
    before: beforeOrder,
    after: afterOrder,
    apply: order => setWallpaperOrder(order, { animate: true })
  });
}

function recordWallpaperSelection(beforePath, afterPath) {
  if (beforePath === afterPath) return;
  pushConsoleHistory({
    type: "wallpaper-selection",
    before: beforePath || "",
    after: afterPath || "",
    apply: path => setSelectedWallpaper(path, { record: false })
  });
}

function selectedWallpaper() {
  return wallpapers.find(item => item.path === selectedWallpaperPath) || orderedWallpapers()[0] || null;
}

function setSelectedWallpaper(path, options = {}) {
  const beforePath = selectedWallpaperPath;
  pendingDeletePath = "";
  selectedWallpaperPath = path || "";
  if (selectedWallpaperPath) {
    localStorage.setItem(storageKeys.selectedWallpaper, selectedWallpaperPath);
  } else {
    localStorage.removeItem(storageKeys.selectedWallpaper);
  }
  renderWallpapers();
  if (options.record !== false) {
    recordWallpaperSelection(beforePath, selectedWallpaperPath);
  }
}

function requestDeleteWallpaper(item) {
  pendingDeletePath = item.path;
  renderWallpapers();
}

function cancelDeleteWallpaper() {
  if (!pendingDeletePath) return;
  pendingDeletePath = "";
  renderWallpapers();
}

function wallpaperAnimationNow() {
  return window.performance?.now?.() || Date.now();
}

function wallpaperGridColumnCount(grid) {
  const columns = window.getComputedStyle(grid).gridTemplateColumns
    .split(" ")
    .filter(Boolean);
  return Math.max(1, columns.length || 1);
}

function wallpaperGridColumnWidths(grid) {
  const computed = window.getComputedStyle(grid);
  const widths = computed.gridTemplateColumns
    .split(" ")
    .map(value => Number.parseFloat(value))
    .filter(Number.isFinite);
  if (widths.length) return widths;
  const fallbackWidth = grid.getBoundingClientRect().width || 1;
  return [fallbackWidth];
}

function wallpaperGridGapSize(grid, property) {
  const value = Number.parseFloat(window.getComputedStyle(grid)[property]);
  return Number.isFinite(value) ? value : 0;
}

function wallpaperRectSnapshot(rect) {
  return {
    left: rect.left,
    right: rect.right,
    top: rect.top,
    bottom: rect.bottom,
    width: rect.width,
    height: rect.height
  };
}

function wallpaperDragProbePoint(clientX, clientY, draggedRect = null) {
  const fallbackX = draggedRect
    ? draggedRect.left + draggedRect.width / 2
    : clientX;
  const fallbackY = draggedRect
    ? draggedRect.top + draggedRect.height / 2
    : clientY;
  const rawX = Number.isFinite(clientX) ? clientX : fallbackX;
  const rawY = Number.isFinite(clientY) ? clientY : fallbackY;
  return {
    x: Number.isFinite(rawX) ? rawX : fallbackX,
    y: Number.isFinite(rawY) ? rawY : fallbackY
  };
}

function wallpaperCardsInGrid(grid) {
  return Array.from(grid?.querySelectorAll?.(".wallpaper-card:not(.dragging):not(.wallpaper-placeholder)") || [])
    .filter(card => card.dataset.wallpaperPath);
}

function wallpaperLayoutItemsFromCards(cards) {
  return cards.map(card => ({
    card,
    path: card.dataset.wallpaperPath || "",
    rect: wallpaperRectSnapshot(card.getBoundingClientRect())
  })).filter(item => item.path);
}

function wallpaperLayoutItemsFromGridSlots(grid, placeholder) {
  return Array.from(grid?.querySelectorAll?.(".wallpaper-card:not(.dragging)") || [])
    .map(card => {
      const isPlaceholder = card === placeholder || card.classList.contains("wallpaper-placeholder");
      const path = isPlaceholder ? wallpaperPlaceholderLayoutPath : card.dataset.wallpaperPath || "";
      if (!path) return null;
      return {
        card: isPlaceholder ? null : card,
        isPlaceholder,
        path,
        rect: wallpaperRectSnapshot(card.getBoundingClientRect())
      };
    })
    .filter(Boolean);
}

function wallpaperRowsFromLayoutItems(items) {
  const rows = [];
  for (const item of items) {
    let row = rows.find(rowItem => Math.abs(rowItem.top - item.rect.top) < 12);
    if (!row) {
      row = { top: item.rect.top, bottom: item.rect.bottom, cards: [] };
      rows.push(row);
    }
    row.top = Math.min(row.top, item.rect.top);
    row.bottom = Math.max(row.bottom, item.rect.bottom);
    row.cards.push(item);
  }
  rows.sort((a, b) => a.top - b.top);
  for (const row of rows) {
    row.cards.sort((a, b) => a.rect.left - b.rect.left);
  }
  return rows;
}

function wallpaperVirtualLayoutItems(items, gridRect, columnWidths, columnGap, rowGap, rowHeight) {
  const columnCount = Math.max(1, columnWidths.length || 1);
  const columnLefts = [];
  let columnLeft = gridRect.left;
  for (let index = 0; index < columnCount; index += 1) {
    columnLefts.push(columnLeft);
    columnLeft += (columnWidths[index] || gridRect.width || 1) + columnGap;
  }

  return items.map((item, index) => {
    const columnIndex = index % columnCount;
    const rowIndex = Math.floor(index / columnCount);
    const width = columnWidths[columnIndex] || item.rect.width || gridRect.width || 1;
    const height = rowHeight || item.rect.height || 88;
    const left = columnLefts[columnIndex] ?? gridRect.left;
    const top = gridRect.top + rowIndex * (height + rowGap);
    return {
      ...item,
      rect: {
        left,
        right: left + width,
        top,
        bottom: top + height,
        width,
        height
      }
    };
  });
}

function wallpaperGridLayoutForItems(grid, items, draggedRect = null) {
  const gridRect = wallpaperRectSnapshot(grid.getBoundingClientRect());
  const columnWidths = wallpaperGridColumnWidths(grid);
  const columnGap = wallpaperGridGapSize(grid, "columnGap");
  const rowGap = wallpaperGridGapSize(grid, "rowGap");
  const heights = [
    ...items.map(item => item.rect.height),
    draggedRect?.height || 0
  ].filter(height => height > 0);
  const rowHeight = heights.length ? Math.max(...heights) : 88;
  const virtualItems = wallpaperVirtualLayoutItems(items, gridRect, columnWidths, columnGap, rowGap, rowHeight);
  const rows = wallpaperRowsFromLayoutItems(virtualItems);
  return {
    cards: virtualItems,
    rows,
    gridRect,
    columnWidths,
    columnCount: Math.max(1, columnWidths.length || wallpaperGridColumnCount(grid)),
    columnGap,
    rowGap,
    rowHeight
  };
}

function wallpaperRowIndexForLayoutProbe(layout, probeY) {
  const rows = layout.rows || [];
  if (!rows.length) return 0;
  if (probeY <= rows[0].top) return 0;

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const nextRow = rows[index + 1] || null;
    if (probeY <= row.bottom) return index;
    if (nextRow && probeY < nextRow.top) {
      const gapMid = row.bottom + (nextRow.top - row.bottom) / 2;
      return probeY < gapMid ? index : index + 1;
    }
  }

  const lastRow = rows[rows.length - 1];
  const newRowThreshold = lastRow.bottom + Math.max(6, layout.rowGap / 2);
  if (probeY <= newRowThreshold) return rows.length - 1;
  const rowStep = Math.max(1, layout.rowHeight + layout.rowGap);
  return rows.length + Math.floor(Math.max(0, probeY - newRowThreshold) / rowStep);
}

function wallpaperInsertIndexFromGridLayout(layout, probeX, probeY, draggedRect = null, directionX = 0) {
  if (!layout?.cards?.length) return 0;
  const rowIndex = Math.max(0, wallpaperRowIndexForLayoutProbe(layout, probeY));
  const rows = layout.rows || [];
  if (rowIndex >= rows.length) return layout.cards.length;
  const row = rows[rowIndex];
  const thresholdRatio = directionX < 0
    ? wallpaperReorderReturnRatio
    : directionX > 0
      ? wallpaperReorderCommitRatio
      : 1 / 2;
  const comparisonX = dragInsertionProbeX(probeX, draggedRect, directionX);
  const beforeItem = row.cards.find(item => comparisonX <= item.rect.left + item.rect.width * thresholdRatio);
  if (beforeItem) {
    const beforeIndex = layout.cards.indexOf(beforeItem);
    return beforeIndex >= 0 ? beforeIndex : layout.cards.length;
  }
  const nextRowFirst = rows[rowIndex + 1]?.cards?.[0] || null;
  if (nextRowFirst) {
    const nextRowIndex = layout.cards.indexOf(nextRowFirst);
    return nextRowIndex >= 0 ? nextRowIndex : layout.cards.length;
  }
  return layout.cards.length;
}

function wallpaperBeforePathFromLiveGrid(grid, cards, clientX, clientY, draggedRect = null, directionX = 0) {
  if (!grid || !cards?.length) return "";
  const probe = wallpaperDragProbePoint(clientX, clientY, draggedRect);
  const layout = wallpaperGridLayoutForItems(grid, wallpaperLayoutItemsFromCards(cards), draggedRect);
  const insertIndex = wallpaperInsertIndexFromGridLayout(layout, probe.x, probe.y, draggedRect, directionX);
  return layout.cards[insertIndex]?.path || "";
}

function wallpaperDropBeforePath(clientX, clientY, directionX = 0, draggedRect = null) {
  const grid = els.wallpaperDock;
  const cards = wallpaperCardsInGrid(grid);
  return wallpaperBeforePathFromLiveGrid(grid, cards, clientX, clientY, draggedRect, directionX);
}

function clearWallpaperDropMarkers() {
  els.wallpaperDock?.querySelectorAll(".wallpaper-drop-before").forEach(node => node.classList.remove("wallpaper-drop-before"));
  els.wallpaperDock?.classList.remove("wallpaper-drop-end");
}

function showWallpaperDropMarker(beforePath) {
  clearWallpaperDropMarkers();
  if (!draggedWallpaperPath) return;
  if (beforePath) {
    Array.from(els.wallpaperDock.querySelectorAll(".wallpaper-card"))
      .find(card => card.dataset.wallpaperPath === beforePath)
      ?.classList.add("wallpaper-drop-before");
  } else {
    els.wallpaperDock?.classList.add("wallpaper-drop-end");
  }
}

function reorderWallpaper(path, beforePath = "", options = {}) {
  if (!path || path === beforePath) return;
  const beforeOrder = options.beforeOrder || wallpaperOrderSnapshot();
  const nextOrder = orderWithMovedPath(beforeOrder, path, beforePath);
  if (historyValuesEqual(beforeOrder, nextOrder)) {
    return;
  }
  setWallpaperOrder(nextOrder, { animate: options.animate !== false });
  if (options.record !== false) {
    recordWallpaperOrderChange(beforeOrder, nextOrder);
  }
}

function wallpaperBeforeCardFromPoint(clientX, clientY, directionX = 0, draggedRect = null) {
  const beforePath = wallpaperDropBeforePath(clientX, clientY, directionX, draggedRect);
  if (!beforePath) return null;
  return wallpaperCardsInGrid(els.wallpaperDock)
    .find(card => card.dataset.wallpaperPath === beforePath) || null;
}

function wallpaperBeforeCardFromPlaceholderGrid(grid, placeholder, clientX, clientY, directionX = 0, draggedRect = null) {
  if (!grid || !placeholder || placeholder.parentNode !== grid) {
    return wallpaperBeforeCardFromPoint(clientX, clientY, directionX, draggedRect);
  }
  const items = wallpaperLayoutItemsFromGridSlots(grid, placeholder);
  if (!items.length) return null;
  const probe = wallpaperDragProbePoint(clientX, clientY, draggedRect);
  const layout = wallpaperGridLayoutForItems(grid, items, draggedRect);
  const insertIndex = wallpaperInsertIndexFromGridLayout(layout, probe.x, probe.y, draggedRect, directionX);
  return layout.cards
    .slice(insertIndex)
    .find(item => !item.isPlaceholder && item.card)
    ?.card || null;
}

function placeWallpaperPlaceholder(placeholder, grid, insertBefore, animate = true) {
  const mutate = () => {
    grid.insertBefore(placeholder, insertBefore);
    placeholder.dataset.lastReflowAt = String(wallpaperAnimationNow());
  };
  if (animate) {
    animateWallpaperReflow(mutate);
  } else {
    for (const card of wallpaperCardsForAnimation()) {
      card.getAnimations().forEach(animation => animation.cancel());
    }
    mutate();
  }
}

function moveWallpaperPlaceholder(placeholder, clientX, clientY, directionX = 0, directionY = 0, draggedRect = null, options = {}) {
  const { force = false } = options;
  const grid = els.wallpaperDock;
  if (!grid) return "none";
  const stableX = draggedRect ? draggedRect.left + draggedRect.width / 2 : clientX;
  const rowY = draggedRect ? draggedRect.top + draggedRect.height / 2 : clientY;
  const before = wallpaperBeforeCardFromPlaceholderGrid(grid, placeholder, stableX, rowY, directionX, draggedRect);
  const insertBefore = before || null;
  const targetKey = before?.dataset?.wallpaperPath || "__end__";
  if (placeholder.parentNode === grid && (insertBefore === placeholder || insertBefore === placeholder.nextElementSibling)) {
    placeholder.dataset.targetKey = targetKey;
    placeholder.dataset.pendingTargetKey = "";
    placeholder.dataset.pendingTargetAt = "0";
    return "unchanged";
  }

  const now = wallpaperAnimationNow();
  const lastReflowAt = Number.parseFloat(placeholder.dataset.lastReflowAt || "0");
  const recentlyReflowed = Number.isFinite(lastReflowAt) && lastReflowAt > 0 && now - lastReflowAt < wallpaperPlaceholderReflowMinIntervalMs;
  if (!force && recentlyReflowed && placeholder.dataset.targetKey && placeholder.dataset.targetKey !== targetKey) {
    placeholder.dataset.pendingTargetKey = targetKey;
    placeholder.dataset.pendingTargetAt = String(now);
    return "deferred";
  }

  const shouldSettleTarget = !force && Math.abs(directionX) < 1 && Math.abs(directionY) < 1;
  if (shouldSettleTarget && placeholder.dataset.targetKey && placeholder.dataset.targetKey !== targetKey) {
    const pendingKey = placeholder.dataset.pendingTargetKey || "";
    const pendingAt = pendingKey === targetKey
      ? Number.parseFloat(placeholder.dataset.pendingTargetAt || "0")
      : now;
    placeholder.dataset.pendingTargetKey = targetKey;
    placeholder.dataset.pendingTargetAt = String(Number.isFinite(pendingAt) ? pendingAt : now);
    if (now - pendingAt < wallpaperPlaceholderTargetSettleMs) return "deferred";
  }

  placeholder.dataset.targetKey = targetKey;
  placeholder.dataset.pendingTargetKey = "";
  placeholder.dataset.pendingTargetAt = "0";
  placeWallpaperPlaceholder(placeholder, grid, insertBefore, true);
  return "moved";
}

function wallpaperBeforePathFromPlaceholder(placeholder) {
  let sibling = placeholder.nextElementSibling;
  while (sibling) {
    if (sibling.classList.contains("wallpaper-card") && !sibling.classList.contains("wallpaper-placeholder")) {
      return sibling.dataset.wallpaperPath || "";
    }
    sibling = sibling.nextElementSibling;
  }
  return "";
}

function settleDraggedWallpaperCard(card, placeholder, animate = true) {
  const startRect = card.getBoundingClientRect();
  const targetRect = placeholder.getBoundingClientRect();
  const dock = placeholder.parentNode;
  let settled = false;
  let fallbackTimer = null;

  const cleanup = () => {
    if (settled) return;
    settled = true;
    if (fallbackTimer) {
      window.clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    dock.insertBefore(card, placeholder);
    placeholder.remove();
    card.getAnimations().forEach(animation => animation.cancel());
    card.classList.remove("dragging", "wallpaper-floating");
    card.style.removeProperty("width");
    card.style.removeProperty("height");
    card.style.removeProperty("left");
    card.style.removeProperty("top");
    card.style.removeProperty("transform");
  };

  if (!animate || Math.abs(startRect.left - targetRect.left) < 1 && Math.abs(startRect.top - targetRect.top) < 1) {
    cleanup();
    return Promise.resolve();
  }

  return new Promise(resolve => {
    const finishCleanup = () => {
      cleanup();
      resolve();
    };
    card.style.left = `${startRect.left}px`;
    card.style.top = `${startRect.top}px`;
    const animation = card.animate(
      [
        { left: `${startRect.left}px`, top: `${startRect.top}px`, transform: "scale(1.02)" },
        { left: `${targetRect.left}px`, top: `${targetRect.top}px`, transform: "scale(1)" }
      ],
      {
        duration: 240,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        fill: "forwards"
      }
    );
    fallbackTimer = window.setTimeout(finishCleanup, 320);
    animation.finished.catch(() => {}).then(finishCleanup);
  });
}

function createWallpaperDragSession(card, item, startX, startY) {
  const rect = card.getBoundingClientRect();
  const placeholder = document.createElement("div");
  placeholder.className = "wallpaper-card wallpaper-placeholder";
  placeholder.style.minHeight = `${rect.height}px`;
  placeholder.setAttribute("aria-hidden", "true");
  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  const sourceOrder = wallpaperOrderSnapshot();
  const sourceBeforePath = card.nextElementSibling?.dataset?.wallpaperPath || "";
  placeholder.dataset.targetKey = sourceBeforePath || "__end__";
  placeholder.dataset.pendingTargetKey = "";
  placeholder.dataset.pendingTargetAt = "0";
  const trackWallpaperDirectionX = createMusicDragDirectionTracker(startX);
  const trackWallpaperDirectionY = createMusicDragDirectionTracker(startY);
  let dragging = false;
  let lastDirectionX = 0;
  let lastDirectionY = 0;

  const moveCardToPoint = (clientX, clientY) => {
    const clamped = clampDragPosition(clientX, clientY, offsetX, offsetY, rect.width, rect.height);
    card.style.left = `${clamped.left}px`;
    card.style.top = `${clamped.top}px`;
  };

  const restorePlaceholderToSource = () => {
    const sourceBefore = sourceBeforePath
      ? Array.from(els.wallpaperDock.querySelectorAll(".wallpaper-card:not(.dragging):not(.wallpaper-placeholder)"))
        .find(node => node.dataset.wallpaperPath === sourceBeforePath)
      : null;
    animateWallpaperReflow(() => {
      els.wallpaperDock.insertBefore(placeholder, sourceBefore);
    });
  };

  const finish = shouldCommit => {
    if (!dragging) return false;
    suppressWallpaperClickUntil = Date.now() + 240;
    draggedWallpaperPath = "";
    document.body.classList.remove("wallpaper-dragging");
    clearWallpaperDropMarkers();

    if (!shouldCommit) {
      restorePlaceholderToSource();
      return settleDraggedWallpaperCard(card, placeholder, true).then(() => false);
    }

    const draggedRect = card.getBoundingClientRect();
    moveWallpaperPlaceholder(
      placeholder,
      draggedRect.left + draggedRect.width / 2,
      draggedRect.top + draggedRect.height / 2,
      lastDirectionX,
      lastDirectionY,
      draggedRect,
      { force: true }
    );
    const beforePath = wallpaperBeforePathFromPlaceholder(placeholder);
    const nextOrder = orderWithMovedPath(sourceOrder, item.path, beforePath);
    wallpaperOrder = nextOrder;
    persistWallpaperOrderNow();
    return settleDraggedWallpaperCard(card, placeholder, true).then(() => {
      renderWallpapers();
      recordWallpaperOrderChange(sourceOrder, nextOrder);
      return true;
    });
  };

  const move = moveEvent => {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 6) return false;
    if (!dragging) {
      dragging = true;
      draggedWallpaperPath = item.path;
      els.wallpaperDock.insertBefore(placeholder, card);
      document.body.appendChild(card);
      card.classList.add("dragging", "wallpaper-floating");
      card.style.width = `${rect.width}px`;
      card.style.height = `${rect.height}px`;
      document.body.classList.add("wallpaper-dragging");
    }
    moveEvent.preventDefault();
    lastDirectionX = trackWallpaperDirectionX(moveEvent.clientX);
    lastDirectionY = trackWallpaperDirectionY(moveEvent.clientY);
    moveCardToPoint(moveEvent.clientX, moveEvent.clientY);
    const draggedRect = card.getBoundingClientRect();
    moveWallpaperPlaceholder(
      placeholder,
      draggedRect.left + draggedRect.width / 2,
      draggedRect.top + draggedRect.height / 2,
      lastDirectionX,
      lastDirectionY,
      draggedRect
    );
    return true;
  };

  return {
    finish,
    isDragging: () => dragging,
    move
  };
}

function beginWallpaperPointerDrag(event, card, item) {
  if (event.button !== 0 || event.pointerType === "mouse" || event.target?.closest?.(".delete-wallpaper-button, .delete-popover")) return;
  lastWallpaperPointerStart = Date.now();
  const dragSession = createWallpaperDragSession(card, item, event.clientX, event.clientY);

  const cleanup = () => {
    card.removeEventListener("pointermove", move);
    card.removeEventListener("pointerup", up);
    card.removeEventListener("pointercancel", cancel);
  };

  const finish = shouldCommit => {
    cleanup();
    dragSession.finish(shouldCommit);
  };

  const move = moveEvent => {
    dragSession.move(moveEvent);
  };

  const up = upEvent => {
    if (card.hasPointerCapture(upEvent.pointerId)) {
      try {
        card.releasePointerCapture(upEvent.pointerId);
      } catch {}
    }
    if (dragSession.isDragging()) upEvent.preventDefault();
    finish(true);
  };

  const cancel = () => finish(false);

  card.setPointerCapture(event.pointerId);
  card.addEventListener("pointermove", move);
  card.addEventListener("pointerup", up);
  card.addEventListener("pointercancel", cancel);
}

function beginWallpaperMouseDrag(event, card, item) {
  if (event.button !== 0 || Date.now() - lastWallpaperPointerStart < 80 || event.target?.closest?.(".delete-wallpaper-button, .delete-popover")) return;
  const dragSession = createWallpaperDragSession(card, item, event.clientX, event.clientY);

  const cleanup = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
  };

  const finish = shouldCommit => {
    cleanup();
    dragSession.finish(shouldCommit);
  };

  const move = moveEvent => {
    dragSession.move(moveEvent);
  };

  const up = () => finish(true);

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function renderWallpapers() {
  if (!hasWallpaper) return;
  syncWallpaperOrder();
  const selected = selectedWallpaper();
  const ordered = orderedWallpapers();
  els.wallpaperDock.innerHTML = "";
  els.wallpaperCount.textContent = text("count", wallpapers.length);

  if (!wallpapers.length) {
    selectedWallpaperPath = "";
    els.selectedWallpaperName.textContent = text("notSelected");
    els.selectedWallpaperSize.textContent = text("noSize");
    els.wallpaperPreview.classList.remove("has-image");
    els.wallpaperPreview.style.removeProperty("--preview-aspect");
    els.wallpaperPreview.innerHTML = `
      <div class="preview-empty">
        <strong>${text("emptyTitle")}</strong>
        <span>${text("emptyBody")}</span>
      </div>
    `;

    const empty = document.createElement("div");
    empty.className = "dock-empty";
    empty.innerHTML = `<strong>${text("noCandidates")}</strong><span>${text("addHint")}</span>`;
    els.wallpaperDock.appendChild(empty);
    setStatus(text("readyStatus"));
    return;
  }

  if (!selectedWallpaperPath && selected) {
    selectedWallpaperPath = selected.path;
  }

  if (selected) {
    els.selectedWallpaperName.textContent = selected.name;
    els.selectedWallpaperSize.textContent = formatBytes(selected.size);
    els.wallpaperPreview.classList.add("has-image");
    els.wallpaperPreview.innerHTML = "";
    const previewImage = document.createElement("img");
    previewImage.className = "preview-image";
    previewImage.src = selected.url;
    previewImage.alt = selected.name;
    previewImage.decoding = "async";
    previewImage.fetchPriority = "high";
    previewImage.addEventListener("load", () => {
      if (previewImage.naturalWidth > 0 && previewImage.naturalHeight > 0) {
        els.wallpaperPreview.style.setProperty("--preview-aspect", `${previewImage.naturalWidth} / ${previewImage.naturalHeight}`);
      }
    });
    els.wallpaperPreview.appendChild(previewImage);
  }

  for (const item of ordered) {
    const card = document.createElement("div");
    card.className = `wallpaper-card ${item.path === selectedWallpaperPath ? "active" : ""} ${item.path === pendingDeletePath ? "pending-delete" : ""} ${item.path === draggedWallpaperPath ? "dragging" : ""}`;
    card.dataset.wallpaperPath = item.path;
    card.tabIndex = 0;
    card.title = text("cardTitle", item.name);
    card.setAttribute("role", "button");
    card.draggable = false;
    card.addEventListener("selectstart", event => event.preventDefault());
    card.addEventListener("pointerdown", event => beginWallpaperPointerDrag(event, card, item));
    card.addEventListener("mousedown", event => beginWallpaperMouseDrag(event, card, item));
    card.addEventListener("click", () => {
      if (Date.now() < suppressWallpaperClickUntil) return;
      const now = Date.now();
      const isSecondClick = lastWallpaperClickPath === item.path && now - lastWallpaperClickAt <= wallpaperDoubleClickMs;
      lastWallpaperClickPath = item.path;
      lastWallpaperClickAt = now;
      if (isSecondClick) {
        lastWallpaperClickPath = "";
        lastWallpaperClickAt = 0;
        applyWallpaper(item);
        return;
      }
      setSelectedWallpaper(item.path);
    });
    card.addEventListener("dblclick", () => applyWallpaper(item));
    card.addEventListener("dragstart", event => event.preventDefault());
    card.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        applyWallpaper(item);
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        requestDeleteWallpaper(item);
      } else if (event.key === "Escape") {
        cancelDeleteWallpaper();
      }
    });
    card.addEventListener("contextmenu", event => {
      event.preventDefault();
      requestDeleteWallpaper(item);
    });

    const image = document.createElement("img");
    image.src = item.url;
    image.alt = item.name;
    image.draggable = false;
    image.loading = "lazy";
    image.decoding = "async";
    image.fetchPriority = item.path === selectedWallpaperPath ? "high" : "low";
    card.appendChild(image);

    const label = document.createElement("span");
    label.textContent = `${item.name} · ${formatBytes(item.size)}`;
    card.appendChild(label);

    const deleteButton = document.createElement("button");
    deleteButton.className = "delete-wallpaper-button";
    deleteButton.type = "button";
    deleteButton.textContent = "×";
    deleteButton.title = text("deleteButtonLabel", item.name);
    deleteButton.setAttribute("aria-label", text("deleteButtonLabel", item.name));
    deleteButton.addEventListener("click", event => {
      event.stopPropagation();
      requestDeleteWallpaper(item);
    });
    card.appendChild(deleteButton);

    if (item.path === pendingDeletePath) {
      const confirm = document.createElement("div");
      confirm.className = "delete-popover";
      confirm.addEventListener("click", event => event.stopPropagation());

      const prompt = document.createElement("strong");
      prompt.textContent = text("deletePrompt");
      confirm.appendChild(prompt);

      const confirmButton = document.createElement("button");
      confirmButton.className = "confirm-delete";
      confirmButton.type = "button";
      confirmButton.textContent = text("confirmDeleteAction");
      confirmButton.addEventListener("click", () => deleteWallpaper(item));
      confirm.appendChild(confirmButton);

      const cancelButton = document.createElement("button");
      cancelButton.className = "cancel-delete";
      cancelButton.type = "button";
      cancelButton.textContent = text("cancelDeleteAction");
      cancelButton.addEventListener("click", cancelDeleteWallpaper);
      confirm.appendChild(cancelButton);

      card.appendChild(confirm);
    }

    els.wallpaperDock.appendChild(card);
  }
}

function selectedTrack() {
  const playable = allMusicTracks();
  return playable.find(item => item.path === selectedTrackPath) || playable[0] || null;
}

function normalizeMusicTrackPathValue(path) {
  return String(path || "").replace(/\\/g, "/").replace(/^\/+/, "").trim();
}

function musicTrackPathExists(path) {
  const cleanPath = normalizeMusicTrackPathValue(path);
  return Boolean(cleanPath && allMusicTracks().some(item => item.path === cleanPath));
}

function firstExistingMusicTrackPath(...paths) {
  for (const path of paths) {
    const cleanPath = normalizeMusicTrackPathValue(path);
    if (cleanPath && musicTrackPathExists(cleanPath)) return cleanPath;
  }
  return "";
}

function activeLyricsTimingTrackPath() {
  const root = els.lyricsTimingEditor || document.getElementById("lyricsTimingEditor");
  if (!root || root.hidden) return "";
  const candidate = normalizeMusicTrackPathValue(activeLyricsTimingTarget?.path || musicLyricsTrackPath);
  return musicTrackPathExists(candidate) ? candidate : "";
}

function musicStateSelectedTrackPath() {
  return normalizeMusicTrackPathValue(selectedTrackPath);
}

function setSelectedTrackPath(path, options = {}) {
  selectedTrackPath = normalizeMusicTrackPathValue(path);
  if (selectedTrackPath) {
    localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
  } else {
    localStorage.removeItem(storageKeys.selectedTrack);
  }
  if (options.preload !== false) scheduleSelectedLyricsPreload();
  if (options.persist === "now") persistMusicStateNow();
  else if (options.persist === "soon") persistMusicStateSoon();
}

function normalizePlaybackMode(mode) {
  return playbackModes.includes(mode) ? mode : "repeatAll";
}

function normalizeTheme(mode) {
  return mode === "dark" ? "dark" : "light";
}

function nextTheme(mode = theme) {
  return normalizeTheme(mode) === "light" ? "dark" : "light";
}

function themeLabelKey(mode = theme) {
  return normalizeTheme(mode) === "dark" ? "themeDark" : "themeLight";
}

function playbackModeLabelKey(mode = playbackMode) {
  if (mode === "playOnce") return "playbackModePlayOnce";
  if (mode === "repeatOne") return "playbackModeRepeatOne";
  return "playbackModeRepeatAll";
}

function playbackModeLabel(mode = playbackMode) {
  return text(playbackModeLabelKey(mode));
}

function renderPlaybackMode() {
  if (!els.playbackModeToggle) return;
  playbackMode = normalizePlaybackMode(playbackMode);
  const label = playbackModeLabel(playbackMode);
  els.playbackModeToggle.dataset.mode = playbackMode;
  els.playbackModeToggle.innerHTML = `<span class="mode-icon" aria-hidden="true">${musicPlayerIcons[playbackMode]}</span>`;
  els.playbackModeToggle.setAttribute("aria-label", text("playbackModeTitle", label));
  els.playbackModeToggle.title = text("playbackModeTitle", label);
}

function cyclePlaybackMode() {
  const currentIndex = playbackModes.indexOf(playbackMode);
  playbackMode = playbackModes[(currentIndex + 1) % playbackModes.length];
  localStorage.setItem(storageKeys.playbackMode, playbackMode);
  renderPlaybackMode();
}

function currentTrackIndex() {
  const playable = allMusicTracks();
  if (!playable.length) return -1;
  const index = playable.findIndex(item => item.path === selectedTrackPath);
  return index >= 0 ? index : 0;
}

function audioIsTrack(item) {
  if (!item || !els.audioPlayer?.src) return false;
  return els.audioPlayer.src === new URL(item.url, window.location.href).href;
}

function nextTrackPathAfterDelete(path) {
  const playable = allMusicTracks();
  if (!playable.length) return "";
  const index = playable.findIndex(item => item.path === path);
  if (index < 0) return playable[0]?.path || "";
  const remaining = playable.filter(item => item.path !== path);
  if (!remaining.length) return "";
  return remaining[index % remaining.length]?.path || remaining[0]?.path || "";
}

function allMusicTracks() {
  return [...orderedLocalTracks(), ...libraryTracks];
}

function localTrackExists(path) {
  return tracks.some(item => item.path === path);
}

function orderedLocalTracks() {
  const orderIndex = new Map(musicTierOrder.map((path, index) => [path, index]));
  return tracks
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const aOrder = orderIndex.has(a.item.path) ? orderIndex.get(a.item.path) : Number.MAX_SAFE_INTEGER + a.index;
      const bOrder = orderIndex.has(b.item.path) ? orderIndex.get(b.item.path) : Number.MAX_SAFE_INTEGER + b.index;
      return aOrder - bOrder;
    })
    .map(entry => entry.item);
}

function isValidMusicTier(tierId) {
  return musicTierGroups.some(group => group.id === tierId);
}

function migrateMusicTier(tierId) {
  const cleanTier = String(tierId || "").trim();
  if (cleanTier === "s") return "first";
  if (cleanTier === "unranked") return "third";
  return cleanTier;
}

function normalizeMusicTier(tierId) {
  const migratedTier = migrateMusicTier(tierId);
  return isValidMusicTier(migratedTier) ? migratedTier : "third";
}

function loadMusicTierAssignments() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKeys.musicTiers) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    return Object.fromEntries(
      Object.entries(raw)
        .map(([path, tierId]) => [String(path), normalizeMusicTier(String(tierId || ""))])
        .filter(([path, tierId]) => path && tierId !== "third")
    );
  } catch {
    return {};
  }
}

function loadMusicTierOrder() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKeys.musicOrder) || "[]");
    if (!Array.isArray(raw)) return [];
    return sanitizeMusicTierOrder(raw);
  } catch {
    return [];
  }
}

function loadMusicTierVisibility() {
  try {
    const saved = localStorage.getItem(storageKeys.musicTierVisibility);
    if (!saved) return { second: true, third: true };
    const raw = JSON.parse(saved);
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return { second: true, third: true };
    }
    const second = Boolean(raw.second);
    return {
      second,
      third: second && Boolean(raw.third)
    };
  } catch {
    return { second: true, third: true };
  }
}

function saveMusicTierVisibility() {
  localStorage.setItem(storageKeys.musicTierVisibility, JSON.stringify({
    second: Boolean(musicTierVisibility.second),
    third: Boolean(musicTierVisibility.second && musicTierVisibility.third)
  }));
}

function isMusicTierVisible(tierId) {
  if (tierId === "first") return true;
  if (tierId === "second") return Boolean(musicTierVisibility.second);
  if (tierId === "third") return Boolean(musicTierVisibility.second && musicTierVisibility.third);
  return false;
}

function lastVisibleMusicTier() {
  const visibleGroups = musicTierGroups.filter(group => isMusicTierVisible(group.id));
  return visibleGroups[visibleGroups.length - 1]?.id || "first";
}

function toggleMusicTierExpansion(tierId) {
  if (tierId === "first") {
    musicTierVisibility.second = !musicTierVisibility.second;
    if (!musicTierVisibility.second) {
      musicTierVisibility.third = false;
    }
  } else if (tierId === "second" && musicTierVisibility.second) {
    musicTierVisibility.third = !musicTierVisibility.third;
  } else if (tierId === "third") {
    musicTierVisibility.third = false;
  }
  saveMusicTierVisibility();
  renderMusic();
}

function sanitizeMusicTierOrder(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  return value
    .map(path => String(path || "").replace(/\\/g, "/").replace(/^\/+/, "").trim())
    .filter(path => {
      if (!path || seen.has(path)) return false;
      seen.add(path);
      return true;
    });
}

function saveMusicStateLocal() {
  localStorage.setItem(storageKeys.musicTiers, JSON.stringify(musicTierAssignments));
  localStorage.setItem(storageKeys.musicOrder, JSON.stringify(musicTierOrder));
  localStorage.setItem(storageKeys.promotedLibraryTracks, JSON.stringify(promotedLibraryTracks));
  const cleanSelectedTrackPath = musicStateSelectedTrackPath();
  if (cleanSelectedTrackPath) {
    localStorage.setItem(storageKeys.selectedTrack, cleanSelectedTrackPath);
  } else {
    localStorage.removeItem(storageKeys.selectedTrack);
  }
}

function musicStatePayload() {
  return {
    stateVersion: musicStateVersion,
    tiers: { ...musicTierAssignments },
    order: [...musicTierOrder],
    promotedLibraryTracks: { ...promotedLibraryTracks },
    selectedTrackPath: musicStateSelectedTrackPath()
  };
}

function persistMusicStateNow() {
  saveMusicStateLocal();
  if (!hasMusic) return;
  if (musicStatePersistTimer) {
    window.clearTimeout(musicStatePersistTimer);
    musicStatePersistTimer = null;
  }
  fetch("/api/music/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(musicStatePayload()),
    keepalive: true
  }).catch(() => {});
}

function persistMusicStateSoon() {
  saveMusicStateLocal();
  if (!hasMusic) return;
  if (musicStatePersistTimer) {
    window.clearTimeout(musicStatePersistTimer);
  }
  musicStatePersistTimer = window.setTimeout(() => {
    persistMusicStateNow();
  }, 80);
}

function flushMusicStateBeforeUnload() {
  if (!hasMusic) return;
  saveMusicStateLocal();
  const body = JSON.stringify(musicStatePayload());
  if (navigator.sendBeacon) {
    try {
      navigator.sendBeacon("/api/music/state", new Blob([body], { type: "application/json" }));
      return;
    } catch {}
  }
  fetch("/api/music/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true
  }).catch(() => {});
}

function applyMusicState(state, options = {}) {
  if (!state || typeof state !== "object") return;
  const hasServerTiers = Object.prototype.hasOwnProperty.call(state, "tiers");
  const hasServerOrder = Object.prototype.hasOwnProperty.call(state, "order");
  const hasServerPromoted = Object.prototype.hasOwnProperty.call(state, "promotedLibraryTracks");
  const hasServerSelected = Object.prototype.hasOwnProperty.call(state, "selectedTrackPath");
  const preferredSelectedTrackPath = normalizeMusicTrackPathValue(options.preferredSelectedTrackPath || "");
  const currentSelectedTrackPath = normalizeMusicTrackPathValue(selectedTrackPath);
  const serverTiers = state.tiers && typeof state.tiers === "object" && !Array.isArray(state.tiers) ? state.tiers : {};
  const serverPromoted = state.promotedLibraryTracks && typeof state.promotedLibraryTracks === "object" && !Array.isArray(state.promotedLibraryTracks)
    ? state.promotedLibraryTracks
    : {};
  const serverOrder = sanitizeMusicTierOrder(state.order || []);
  const serverSelectedTrackPath = normalizeMusicTrackPathValue(state.selectedTrackPath);
  const cleanServerTiers = Object.fromEntries(
    Object.entries(serverTiers)
      .map(([path, tierId]) => [String(path), normalizeMusicTier(String(tierId || ""))])
      .filter(([path, tierId]) => path && tierId !== "third")
  );
  const cleanServerPromoted = Object.fromEntries(
    Object.entries(serverPromoted)
      .map(([libraryPath, localPath]) => [String(libraryPath), String(localPath)])
      .filter(([libraryPath, localPath]) => libraryPath && localPath)
  );

  if (hasServerTiers) {
    musicTierAssignments = cleanServerTiers;
  } else {
    musicTierAssignments = { ...musicTierAssignments, ...cleanServerTiers };
  }
  if (hasServerPromoted) {
    promotedLibraryTracks = cleanServerPromoted;
  } else {
    promotedLibraryTracks = { ...promotedLibraryTracks, ...cleanServerPromoted };
  }
  libraryTracks = flattenLibraryTracks(musicLibraries);
  if (hasServerOrder) {
    musicTierOrder = serverOrder;
  } else if (serverOrder.length) {
    musicTierOrder = sanitizeMusicTierOrder([...serverOrder, ...musicTierOrder]);
  }
  const restoredSelectedTrackPath = firstExistingMusicTrackPath(
    preferredSelectedTrackPath,
    serverSelectedTrackPath,
    currentSelectedTrackPath
  );
  if (restoredSelectedTrackPath) {
    setSelectedTrackPath(restoredSelectedTrackPath);
    if (restoredSelectedTrackPath !== serverSelectedTrackPath) {
      persistMusicStateSoon();
    }
  } else if (hasServerSelected || currentSelectedTrackPath) {
    setSelectedTrackPath("");
  }
  if (!hasServerSelected && selectedTrackPath) {
    persistMusicStateSoon();
  }
  saveMusicStateLocal();
}

function saveMusicTierAssignments() {
  persistMusicStateNow();
}

function syncMusicTierAssignments() {
  const localPaths = new Set(tracks.map(item => item.path));
  let changed = false;
  for (const path of Object.keys(musicTierAssignments)) {
    if (!localPaths.has(path)) {
      delete musicTierAssignments[path];
      changed = true;
      continue;
    }
    const normalizedTier = normalizeMusicTier(musicTierAssignments[path]);
    if (normalizedTier === "third") {
      delete musicTierAssignments[path];
      changed = true;
    } else if (normalizedTier !== musicTierAssignments[path]) {
      musicTierAssignments[path] = normalizedTier;
      changed = true;
    }
  }
  const nextOrder = musicTierOrder.filter(path => localPaths.has(path));
  for (const item of tracks) {
    if (!nextOrder.includes(item.path)) {
      nextOrder.push(item.path);
    }
  }
  if (nextOrder.length !== musicTierOrder.length || nextOrder.some((path, index) => path !== musicTierOrder[index])) {
    musicTierOrder = nextOrder;
    changed = true;
  }
  if (changed) persistMusicStateNow();
}

function tierForTrack(item) {
  return normalizeMusicTier(musicTierAssignments[item?.path] || "third");
}

function localTrackPathFromTransfer(dataTransfer) {
  if (!dataTransfer) return "";
  return dataTransfer.getData("application/x-control-local-track") || "";
}

function transferHasLocalTrack(dataTransfer) {
  return Array.from(dataTransfer?.types || []).includes("application/x-control-local-track");
}

function transferHasTierTrack(dataTransfer) {
  return transferHasLocalTrack(dataTransfer) || transferHasLibraryTrack(dataTransfer);
}

function clearMusicDropMarkers(root = els.musicDock || document) {
  root.querySelectorAll(".track-drop-before").forEach(node => node.classList.remove("track-drop-before"));
  root.querySelectorAll(".music-tier-drop-end").forEach(node => node.classList.remove("music-tier-drop-end"));
}

function clearMusicTierDragState() {
  clearMusicDropMarkers();
  document.querySelectorAll(".music-tier-section.drag-over").forEach(node => node.classList.remove("drag-over"));
  currentMusicDropTargetKey = "";
}

function musicDropBeforePath(section, event) {
  return musicDropBeforePathFromPoint(section, event.clientX, event.clientY);
}

function musicDropBeforePathFromPoint(section, clientX, clientY, directionX = 0, draggedRect = null, directionY = 0) {
  const grid = musicGridForSection(section);
  if (!grid) return "";
  const cards = musicTrackCardsInGrid(grid);
  if (!cards.length) return "";
  return musicBeforePathFromLiveRows(grid, cards, clientX, clientY, draggedRect, directionX);
}

function musicProjectedTierReach(section, draggedRect = null) {
  const grid = musicGridForSection(section);
  const rowGap = grid ? musicGridGapSize(grid, "rowGap") : 0;
  const extraBottom = draggedRect?.height
    ? Math.max(36, draggedRect.height + rowGap)
    : 30;
  return {
    top: 30,
    bottom: extraBottom
  };
}

function musicTierStableRect(section) {
  const sectionRect = musicRectSnapshot(section.getBoundingClientRect());
  const headRect = section.querySelector(".music-tier-head")?.getBoundingClientRect();
  const grid = musicGridForSection(section);
  const gridRect = grid?.getBoundingClientRect();
  const contentBottoms = [
    sectionRect.top + 44,
    headRect?.bottom || 0,
    gridRect ? gridRect.bottom : 0
  ];

  for (const node of grid?.querySelectorAll?.(".track-card:not(.dragging), .music-tier-empty") || []) {
    const rect = node.getBoundingClientRect();
    if (rect.height > 0) {
      contentBottoms.push(rect.bottom);
    }
  }

  const bottom = Math.max(...contentBottoms.filter(Number.isFinite));
  return {
    ...sectionRect,
    bottom,
    height: Math.max(1, bottom - sectionRect.top)
  };
}

function musicTierHitMetrics(clientX) {
  const horizontalPad = 20;
  return Array.from(els.musicDock?.querySelectorAll(".music-tier-section") || [])
    .map(section => ({ section, rect: musicTierStableRect(section) }))
    .filter(item => clientX >= item.rect.left - horizontalPad && clientX <= item.rect.right + horizontalPad)
    .sort((a, b) => a.rect.top - b.rect.top);
}

function musicProjectedMetricBottom(metric, draggedRect = null) {
  const reach = musicProjectedTierReach(metric.section, draggedRect);
  return metric.rect.bottom + Math.max(0, reach.bottom || 0);
}

function musicTierMetricAtY(metrics, clientY, draggedRect = null, directionY = 0) {
  if (!metrics.length) return null;
  const edgeReach = draggedRect?.height
    ? clamp(draggedRect.height * 0.72, 42, 92)
    : 48;

  for (let index = 1; index < metrics.length; index += 1) {
    const previous = metrics[index - 1];
    const current = metrics[index];
    const overlapTop = current.rect.top - 4;
    const overlapBottom = musicProjectedMetricBottom(previous, draggedRect);
    if (overlapBottom > overlapTop && clientY >= overlapTop && clientY <= overlapBottom) {
      const overlapRatio = clamp((clientY - overlapTop) / Math.max(1, overlapBottom - overlapTop), 0, 1);
      const switchRatio = directionY > 0
        ? 0.64
        : directionY < 0
          ? 0.58
          : 0.61;
      return overlapRatio <= switchRatio ? previous : current;
    }
  }

  for (let index = 0; index < metrics.length; index += 1) {
    const item = metrics[index];
    const next = metrics[index + 1] || null;
    const topBoundary = index === 0 ? item.rect.top - edgeReach : item.rect.top;
    const bottomBoundary = next ? next.rect.top : item.rect.bottom + edgeReach;
    if (clientY >= topBoundary && clientY < bottomBoundary) {
      return item;
    }
  }

  return metrics.reduce((best, item) => {
    const distance = clientY < item.rect.top
      ? item.rect.top - clientY
      : clientY > item.rect.bottom
        ? clientY - item.rect.bottom
        : 0;
    return !best || distance < best.distance ? { item, distance } : best;
  }, null)?.item || metrics[0];
}

function musicTierSwitchMargin(draggedRect = null, movingToward = false) {
  const base = draggedRect?.height
    ? clamp(draggedRect.height * 0.08, 6, 12)
    : 8;
  return movingToward ? Math.max(4, base * 0.55) : base;
}

function musicTierAtPoint(clientX, clientY, preferredSection = null, draggedRect = null, directionY = 0) {
  const metrics = musicTierHitMetrics(clientX);
  if (!metrics.length) return preferredSection || null;
  const candidate = musicTierMetricAtY(metrics, clientY, draggedRect, directionY);
  if (!candidate) return preferredSection || null;
  const preferred = preferredSection
    ? metrics.find(item => item.section === preferredSection)
    : null;
  if (preferred && preferred.section !== candidate.section) {
    const preferredIndex = metrics.indexOf(preferred);
    const candidateIndex = metrics.indexOf(candidate);
    const sectionDirection = Math.sign(candidateIndex - preferredIndex);
    const movingToward = sectionDirection !== 0 && Math.sign(directionY) === sectionDirection;
    const margin = musicTierSwitchMargin(draggedRect, movingToward);
    if (sectionDirection > 0 && clientY < candidate.rect.top + margin) return preferred.section;
    if (sectionDirection < 0 && clientY > preferred.rect.top - margin) return preferred.section;
  }
  return candidate.section;
}

function musicDropTargetAtPoint(clientX, clientY, preferredSection = null, directionX = 0, directionY = 0, draggedRect = null) {
  const section = musicTierAtPoint(clientX, clientY, preferredSection, draggedRect, directionY);
  if (!section) return { section: null, tierId: "", beforePath: "" };
  return {
    section,
    tierId: section.dataset.tier || "",
    beforePath: musicDropBeforePathFromPoint(section, clientX, clientY, directionX, draggedRect, directionY)
  };
}

function showMusicPointerDropTarget(target) {
  const targetKey = target?.section && isValidMusicTier(target.tierId)
    ? `${target.tierId}|${target.beforePath || ""}`
    : "";
  if (!targetKey && !currentMusicDropTargetKey) return;
  if (targetKey && targetKey === currentMusicDropTargetKey) return;
  clearMusicTierDragState();
  if (!target?.section || !isValidMusicTier(target.tierId)) return;
  currentMusicDropTargetKey = targetKey;
  target.section.classList.add("drag-over");
  if (target.beforePath) {
    Array.from(target.section.querySelectorAll(".track-card"))
      .find(card => card.dataset.trackPath === target.beforePath)
      ?.classList.add("track-drop-before");
  } else {
    target.section.classList.add("music-tier-drop-end");
  }
}

function updateMusicDropMarker(section, event) {
  const beforePath = musicDropBeforePath(section, event);
  showMusicPointerDropTarget({
    section,
    tierId: section.dataset.tier || "",
    beforePath
  });
  return beforePath;
}

function isBlockedMusicTrackDragEvent(event, item) {
  return item.libraryId || event.button !== 0 || event.target?.closest?.(".delete-track-button, .delete-popover");
}

function musicAnimationKey(card) {
  if (card.classList.contains("music-track-placeholder")) return musicPlaceholderLayoutPath;
  return card.dataset.trackPath || "";
}

function musicTrackCardsForAnimation({ includePlaceholder = false } = {}) {
  if (!els.musicDock) return [];
  const selector = includePlaceholder
    ? ".track-card:not(.dragging)"
    : ".track-card:not(.dragging):not(.music-track-placeholder)";
  return Array.from(els.musicDock.querySelectorAll(selector))
    .filter(card => Boolean(musicAnimationKey(card)));
}

function musicReflowAnimationDurationFor(dx, dy) {
  const distance = Math.hypot(dx, dy);
  return clamp(Math.round(205 + Math.sqrt(distance) * 8.8), musicReflowAnimationMinDuration, musicReflowAnimationMaxDuration);
}

function musicSettleAnimationDurationFor(dx, dy) {
  const distance = Math.hypot(dx, dy);
  return clamp(Math.round(188 + Math.sqrt(distance) * 9), musicSettleAnimationMinDuration, musicSettleAnimationMaxDuration);
}

function musicDampedSpringStep(current, target, velocity, deltaSeconds, frequency) {
  const omega = Math.max(1, frequency) * Math.PI * 2;
  const delta = current - target;
  const spring = velocity + omega * delta;
  const decay = Math.exp(-omega * deltaSeconds);
  return {
    value: target + (delta + spring * deltaSeconds) * decay,
    velocity: (velocity - omega * spring * deltaSeconds) * decay
  };
}

function musicFrameAdjustedDamping(baseDamping, deltaSeconds = musicDragFrameMs / 1000) {
  const frameSeconds = musicDragFrameMs / 1000;
  const frames = Number.isFinite(deltaSeconds) && deltaSeconds > 0
    ? Math.max(1, deltaSeconds / frameSeconds)
    : 1;
  return Math.pow(baseDamping, clamp(frames, 1, 2));
}

function musicDampSettledAxisVelocity(delta, velocity, deltaSeconds = musicDragFrameMs / 1000) {
  if (!Number.isFinite(velocity)) {
    return 0;
  }
  return Math.abs(delta) <= musicDragSettledAxisDistance
    ? velocity * musicFrameAdjustedDamping(musicDragSettledAxisVelocityDamping, deltaSeconds)
    : velocity;
}

function musicSettleVelocityFor(offset, velocity) {
  if (!Number.isFinite(velocity)) {
    return 0;
  }
  const maxVelocity = musicSettleMaxVelocityBase + Math.abs(offset) * musicSettleMaxVelocityDistanceScale;
  const limited = clamp(velocity, -maxVelocity, maxVelocity);
  return offset * limited > 0
    ? limited * musicDragOpposingVelocityDamping
    : limited;
}

function musicSoftLimitedVisualDistance(distance, maxDistance) {
  const softRange = Math.max(1, maxDistance * musicDragSoftStepOverflowRatio);
  const overflow = Math.max(0, distance - maxDistance);
  return maxDistance + softRange * (1 - Math.exp(-overflow / softRange));
}

function musicLimitVisualStep(currentLeft, currentTop, nextLeft, nextTop, nextVelocityX, nextVelocityY, deltaSeconds, maxDistance) {
  const dx = nextLeft - currentLeft;
  const dy = nextTop - currentTop;
  const distance = Math.hypot(dx, dy);
  if (!Number.isFinite(distance) || distance <= maxDistance) {
    return {
      left: nextLeft,
      top: nextTop,
      velocityX: nextVelocityX,
      velocityY: nextVelocityY
    };
  }
  const limitedDistance = musicSoftLimitedVisualDistance(distance, maxDistance);
  const ratio = limitedDistance / distance;
  const left = currentLeft + dx * ratio;
  const top = currentTop + dy * ratio;
  const seconds = Math.max(deltaSeconds, 0.001);
  const actualVelocityX = (left - currentLeft) / seconds;
  const actualVelocityY = (top - currentTop) / seconds;
  const scaledVelocityX = nextVelocityX * ratio;
  const scaledVelocityY = nextVelocityY * ratio;
  return {
    left,
    top,
    velocityX: actualVelocityX * (1 - musicDragLimitedVelocityBlend) + scaledVelocityX * musicDragLimitedVelocityBlend,
    velocityY: actualVelocityY * (1 - musicDragLimitedVelocityBlend) + scaledVelocityY * musicDragLimitedVelocityBlend
  };
}

function musicDragPx(value) {
  return Number.isFinite(value) ? Math.round(value * 1000) / 1000 : 0;
}

function musicFloatingTrackTransform(dx = 0, dy = 0, scale = musicFloatingTrackScale) {
  const translate = `translate3d(${musicDragPx(dx)}px, ${musicDragPx(dy)}px, 0)`;
  return scale === 1 ? translate : `${translate} scale(${scale})`;
}

function musicReflowTrackTransform(dx = 0, dy = 0) {
  return `translate3d(${musicDragPx(dx)}px, ${musicDragPx(dy)}px, 0)`;
}

function musicAnimationNow() {
  return window.performance?.now?.() || Date.now();
}

function afterMusicAnimationFrame() {
  return new Promise(resolve => window.requestAnimationFrame(resolve));
}

function cancelMusicReflowAnimations(card) {
  for (const animation of card.getAnimations()) {
    if (animation.id === musicReflowAnimationId) {
      animation.cancel();
    }
  }
}

function hasActiveMusicReflowAnimation(card) {
  return card.getAnimations().some(animation => (
    animation.id === musicReflowAnimationId &&
    (animation.playState === "running" || animation.playState === "pending")
  ));
}

function cleanupFinishedMusicAnimation(animation) {
  animation.finished
    .catch(() => {})
    .then(() => {
      if (animation.playState !== "idle") {
        animation.cancel();
      }
    });
}

function musicRectFromPosition(left, top, width, height) {
  return {
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height
  };
}

function animateMusicPlaceholderIntro(placeholder) {
  if (!placeholder?.animate) return;
  const animation = placeholder.animate(
    [
      {
        opacity: 0,
        scale: "0.985",
        backgroundColor: "rgba(15, 143, 98, 0)",
        borderColor: "rgba(15, 143, 98, 0)"
      },
      {
        opacity: 0.24,
        scale: "1",
        backgroundColor: "rgba(15, 143, 98, 0.035)",
        borderColor: "rgba(15, 143, 98, 0.22)"
      }
    ],
    {
      duration: 220,
      easing: musicReflowAnimationEasing,
      fill: "both"
    }
  );
  cleanupFinishedMusicAnimation(animation);
}

function animateMusicTrackReflow(mutate, options = {}) {
  const cards = musicTrackCardsForAnimation(options);
  const first = new Map(cards.map(card => [musicAnimationKey(card), card.getBoundingClientRect()]));
  const continuing = new Set(
    cards
      .filter(card => hasActiveMusicReflowAnimation(card))
      .map(card => musicAnimationKey(card))
  );
  for (const card of cards) {
    cancelMusicReflowAnimations(card);
  }

  mutate();

  for (const card of musicTrackCardsForAnimation(options)) {
    const before = first.get(musicAnimationKey(card));
    if (!before) continue;
    const after = card.getBoundingClientRect();
    const dx = before.left - after.left;
    const dy = before.top - after.top;
    const isContinuing = continuing.has(musicAnimationKey(card));
    const distance = Math.hypot(dx, dy);
    const snapDistance = isContinuing ? musicReflowContinueSnapDistance : musicReflowSnapDistance;
    if (distance <= snapDistance) continue;
    const duration = musicReflowAnimationDurationFor(dx, dy) * (isContinuing ? musicReflowContinueDurationScale : 1);
    const animation = card.animate(
      [
        { transform: musicReflowTrackTransform(dx, dy) },
        { transform: musicReflowTrackTransform() }
      ],
      {
        duration,
        easing: isContinuing ? musicReflowContinueEasing : musicReflowAnimationEasing,
        fill: "both"
      }
    );
    animation.id = musicReflowAnimationId;
    cleanupFinishedMusicAnimation(animation);
  }
}

function musicGridForSection(section) {
  return section?.querySelector?.(".music-tier-track-grid") || null;
}

function musicTrackCardsInGrid(grid) {
  return Array.from(grid?.querySelectorAll?.(".track-card:not(.dragging):not(.music-track-placeholder)") || [])
    .filter(card => card.dataset.trackPath);
}

function musicBeforeCardFromPoint(grid, clientX, clientY, directionX = 0, draggedRect = null, directionY = 0) {
  const section = grid?.closest?.(".music-tier-section");
  const beforePath = section ? musicDropBeforePathFromPoint(section, clientX, clientY, directionX, draggedRect, directionY) : "";
  if (!beforePath) return null;
  return musicTrackCardsInGrid(grid)
    .find(card => card.dataset.trackPath === beforePath) || null;
}

function musicBeforeCardFromPlaceholderGrid(grid, placeholder, clientX, clientY, directionX = 0, draggedRect = null, directionY = 0) {
  if (!grid || !placeholder || placeholder.parentNode !== grid) {
    return musicBeforeCardFromPoint(grid, clientX, clientY, directionX, draggedRect);
  }
  const items = musicLayoutItemsFromGridSlots(grid, placeholder);
  if (!items.length) return null;
  const probe = musicDragProbePoint(clientX, clientY, draggedRect);
  const layout = musicGridLayoutForItems(grid, items, draggedRect);
  const insertIndex = musicInsertIndexFromGridLayout(layout, probe.x, probe.y, draggedRect, directionX);
  return layout.cards
    .slice(insertIndex)
    .find(item => !item.isPlaceholder && item.card)
    ?.card || null;
}

function musicGridColumnCount(grid) {
  const columns = window.getComputedStyle(grid).gridTemplateColumns
    .split(" ")
    .filter(Boolean);
  return Math.max(1, columns.length || 1);
}

function musicGridColumnWidths(grid) {
  const computed = window.getComputedStyle(grid);
  const widths = computed.gridTemplateColumns
    .split(" ")
    .map(value => Number.parseFloat(value))
    .filter(Number.isFinite);
  if (widths.length) return widths;
  const fallbackWidth = grid.getBoundingClientRect().width || 1;
  return [fallbackWidth];
}

function musicGridGapSize(grid, property) {
  const value = Number.parseFloat(window.getComputedStyle(grid)[property]);
  return Number.isFinite(value) ? value : 0;
}

function musicTypicalCardHeight(cards, draggedRect = null) {
  if (draggedRect?.height) return draggedRect.height;
  const heights = cards
    .map(card => card.getBoundingClientRect().height)
    .filter(height => height > 0);
  return heights.length ? Math.max(...heights) : 88;
}

function musicDragProbePoint(clientX, clientY, draggedRect = null) {
  const fallbackX = draggedRect
    ? draggedRect.left + draggedRect.width / 2
    : clientX;
  const fallbackY = draggedRect
    ? draggedRect.top + draggedRect.height / 2
    : clientY;
  const rawX = Number.isFinite(clientX) ? clientX : fallbackX;
  const rawY = Number.isFinite(clientY) ? clientY : fallbackY;
  return {
    x: Number.isFinite(rawX) ? rawX : fallbackX,
    y: Number.isFinite(rawY) ? rawY : fallbackY
  };
}

function musicBeforePathFromLiveRows(grid, cards, clientX, clientY, draggedRect = null, directionX = 0) {
  if (!grid || !cards?.length) return "";
  const probe = musicDragProbePoint(clientX, clientY, draggedRect);
  const layout = musicGridLayoutForItems(grid, musicLayoutItemsFromCards(cards), draggedRect);
  const insertIndex = musicInsertIndexFromGridLayout(layout, probe.x, probe.y, draggedRect, directionX);
  return layout.cards[insertIndex]?.path || "";
}

function musicLayoutItemsFromCards(cards) {
  return cards.map(card => ({
    card,
    path: card.dataset.trackPath || "",
    rect: musicRectSnapshot(card.getBoundingClientRect())
  })).filter(item => item.path);
}

function musicLayoutItemsFromGridSlots(grid, placeholder) {
  return Array.from(grid?.querySelectorAll?.(".track-card:not(.dragging)") || [])
    .map(card => {
      const isPlaceholder = card === placeholder || card.classList.contains("music-track-placeholder");
      const path = isPlaceholder ? musicPlaceholderLayoutPath : card.dataset.trackPath || "";
      if (!path) return null;
      return {
        card: isPlaceholder ? null : card,
        isPlaceholder,
        path,
        rect: musicRectSnapshot(card.getBoundingClientRect())
      };
    })
    .filter(Boolean);
}

function musicRowsFromLayoutItems(items) {
  const rows = [];
  for (const item of items) {
    let row = rows.find(rowItem => Math.abs(rowItem.top - item.rect.top) < 12);
    if (!row) {
      row = { top: item.rect.top, bottom: item.rect.bottom, cards: [] };
      rows.push(row);
    }
    row.top = Math.min(row.top, item.rect.top);
    row.bottom = Math.max(row.bottom, item.rect.bottom);
    row.cards.push(item);
  }
  rows.sort((a, b) => a.top - b.top);
  for (const row of rows) {
    row.cards.sort((a, b) => a.rect.left - b.rect.left);
  }
  return rows;
}

function musicVirtualLayoutItems(items, gridRect, columnWidths, columnGap, rowGap, rowHeight) {
  const columnCount = Math.max(1, columnWidths.length || 1);
  const columnLefts = [];
  let columnLeft = gridRect.left;
  for (let index = 0; index < columnCount; index += 1) {
    columnLefts.push(columnLeft);
    columnLeft += (columnWidths[index] || gridRect.width || 1) + columnGap;
  }

  return items.map((item, index) => {
    const columnIndex = index % columnCount;
    const rowIndex = Math.floor(index / columnCount);
    const width = columnWidths[columnIndex] || item.rect.width || gridRect.width || 1;
    const height = rowHeight || item.rect.height || 88;
    const left = columnLefts[columnIndex] ?? gridRect.left;
    const top = gridRect.top + rowIndex * (height + rowGap);
    return {
      ...item,
      rect: {
        left,
        right: left + width,
        top,
        bottom: top + height,
        width,
        height
      }
    };
  });
}

function musicGridLayoutForItems(grid, items, draggedRect = null) {
  const gridRect = musicRectSnapshot(grid.getBoundingClientRect());
  const columnWidths = musicGridColumnWidths(grid);
  const columnGap = musicGridGapSize(grid, "columnGap");
  const rowGap = musicGridGapSize(grid, "rowGap");
  const heights = [
    ...items.map(item => item.rect.height),
    draggedRect?.height || 0
  ].filter(height => height > 0);
  const rowHeight = heights.length ? Math.max(...heights) : 88;
  const virtualItems = musicVirtualLayoutItems(items, gridRect, columnWidths, columnGap, rowGap, rowHeight);
  const rows = musicRowsFromLayoutItems(virtualItems);
  return {
    cards: virtualItems,
    rows,
    gridRect,
    columnWidths,
    columnCount: Math.max(1, columnWidths.length || musicGridColumnCount(grid)),
    columnGap,
    rowGap,
    rowHeight
  };
}

function musicRowIndexForLayoutProbe(layout, probeY) {
  const rows = layout.rows || [];
  if (!rows.length) return 0;
  if (probeY <= rows[0].top) return 0;

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const nextRow = rows[index + 1] || null;
    if (probeY <= row.bottom) return index;
    if (nextRow && probeY < nextRow.top) {
      const gapMid = row.bottom + (nextRow.top - row.bottom) / 2;
      return probeY < gapMid ? index : index + 1;
    }
  }

  const lastRow = rows[rows.length - 1];
  const newRowThreshold = lastRow.bottom + Math.max(6, layout.rowGap / 2);
  if (probeY <= newRowThreshold) return rows.length - 1;
  const rowStep = Math.max(1, layout.rowHeight + layout.rowGap);
  return rows.length + Math.floor(Math.max(0, probeY - newRowThreshold) / rowStep);
}

function musicRowIndexForDraggedLayout(layout, probeY, draggedRect = null) {
  const rows = layout?.rows || [];
  if (!rows.length) return 0;
  return musicRowIndexForLayoutProbe(layout, probeY);
}

function musicInsertIndexFromGridLayout(layout, probeX, probeY, draggedRect = null, directionX = 0) {
  if (!layout?.cards?.length) return 0;
  const rowIndex = Math.max(0, musicRowIndexForDraggedLayout(layout, probeY, draggedRect));
  const rows = layout.rows || [];
  if (rowIndex >= rows.length) return layout.cards.length;
  const row = rows[rowIndex];
  const thresholdRatio = directionX < 0
    ? musicReorderReturnRatio
    : directionX > 0
      ? musicReorderCommitRatio
      : 1 / 2;
  const comparisonX = dragInsertionProbeX(probeX, draggedRect, directionX);
  const beforeItem = row.cards.find(item => comparisonX <= item.rect.left + item.rect.width * thresholdRatio);
  if (beforeItem) {
    const beforeIndex = layout.cards.indexOf(beforeItem);
    return beforeIndex >= 0 ? beforeIndex : layout.cards.length;
  }
  const nextRowFirst = rows[rowIndex + 1]?.cards?.[0] || null;
  if (nextRowFirst) {
    const nextRowIndex = layout.cards.indexOf(nextRowFirst);
    return nextRowIndex >= 0 ? nextRowIndex : layout.cards.length;
  }
  return layout.cards.length;
}

function musicRectSnapshot(rect) {
  return {
    left: rect.left,
    right: rect.right,
    top: rect.top,
    bottom: rect.bottom,
    width: rect.width,
    height: rect.height
  };
}

function nextMusicCardAfterPlaceholder(placeholder) {
  let sibling = placeholder.nextElementSibling;
  while (sibling) {
    if (sibling.classList.contains("track-card") && !sibling.classList.contains("music-track-placeholder")) {
      return sibling;
    }
    sibling = sibling.nextElementSibling;
  }
  return null;
}

function placeMusicPlaceholder(placeholder, grid, insertBefore, animate = true) {
  const mutate = () => {
    placeholder.parentNode?.classList?.remove("drag-has-placeholder");
    grid.insertBefore(placeholder, insertBefore);
    grid.classList.add("drag-has-placeholder");
    placeholder.dataset.lastReflowAt = String(musicAnimationNow());
  };
  if (animate) {
    animateMusicTrackReflow(mutate, { includePlaceholder: true });
  } else {
    for (const card of musicTrackCardsForAnimation()) {
      cancelMusicReflowAnimations(card);
    }
    mutate();
  }
}

function moveMusicPlaceholder(placeholder, section, clientX, clientY, directionX = 0, directionY = 0, draggedRect = null, options = {}) {
  const { force = false } = options;
  const grid = musicGridForSection(section);
  if (!grid) return "none";
  const currentSection = placeholder.closest(".music-tier-section");
  const currentTierId = currentSection?.dataset.tier || "";
  const targetTierId = section.dataset.tier || "";
  const stableX = draggedRect ? draggedRect.left + draggedRect.width / 2 : clientX;
  const rowY = draggedRect ? draggedRect.top + draggedRect.height / 2 : clientY;
  const before = musicBeforeCardFromPlaceholderGrid(grid, placeholder, stableX, rowY, directionX, draggedRect, directionY);
  const empty = grid.querySelector(".music-tier-empty");
  const insertBefore = before || empty || null;
  const targetKey = `${targetTierId}|${before?.dataset?.trackPath || ""}|${insertBefore === empty ? "__empty__" : ""}`;
  if (placeholder.parentNode === grid && (insertBefore === placeholder || insertBefore === placeholder.nextElementSibling)) {
    placeholder.dataset.targetKey = targetKey;
    placeholder.dataset.pendingTargetKey = "";
    placeholder.dataset.pendingTargetAt = "0";
    return "unchanged";
  }

  const now = musicAnimationNow();
  const lastReflowAt = Number.parseFloat(placeholder.dataset.lastReflowAt || "0");
  const recentlyReflowed = Number.isFinite(lastReflowAt) && lastReflowAt > 0 && now - lastReflowAt < musicPlaceholderReflowMinIntervalMs;
  if (!force && recentlyReflowed && placeholder.dataset.targetKey && placeholder.dataset.targetKey !== targetKey) {
    placeholder.dataset.pendingTargetKey = targetKey;
    placeholder.dataset.pendingTargetAt = String(now);
    return "deferred";
  }

  const shouldSettleTarget = !force && Math.abs(directionX) < 1 && Math.abs(directionY) < 1;
  if (shouldSettleTarget && currentTierId && currentTierId === targetTierId && placeholder.dataset.targetKey && placeholder.dataset.targetKey !== targetKey) {
    const pendingKey = placeholder.dataset.pendingTargetKey || "";
    const pendingAt = pendingKey === targetKey
      ? Number.parseFloat(placeholder.dataset.pendingTargetAt || "0")
      : now;
    placeholder.dataset.pendingTargetKey = targetKey;
    placeholder.dataset.pendingTargetAt = String(Number.isFinite(pendingAt) ? pendingAt : now);
    if (now - pendingAt < musicPlaceholderTargetSettleMs) return "deferred";
  }

  placeholder.dataset.targetKey = targetKey;
  placeholder.dataset.pendingTargetKey = "";
  placeholder.dataset.pendingTargetAt = "0";
  placeMusicPlaceholder(placeholder, grid, insertBefore, true);
  return "moved";
}

function musicBeforePathFromPlaceholder(placeholder) {
  let sibling = placeholder.nextElementSibling;
  while (sibling) {
    if (sibling.classList.contains("track-card") && !sibling.classList.contains("music-track-placeholder")) {
      return sibling.dataset.trackPath || "";
    }
    sibling = sibling.nextElementSibling;
  }
  return "";
}

function settleDraggedMusicTrack(card, placeholder, animate = true, motion = {}) {
  const startRect = card.getBoundingClientRect();
  cancelMusicReflowAnimations(placeholder);
  const targetRect = placeholder.getBoundingClientRect();
  const grid = placeholder.parentNode;
  let settled = false;
  let fallbackTimer = null;
  let cleanupFrame = 0;
  let settleFrame = 0;

  const cleanup = () => {
    if (settled) return;
    settled = true;
    if (fallbackTimer) {
      window.clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    if (cleanupFrame) {
      window.cancelAnimationFrame(cleanupFrame);
      cleanupFrame = 0;
    }
    if (settleFrame) {
      window.cancelAnimationFrame(settleFrame);
      settleFrame = 0;
    }
    grid.insertBefore(card, placeholder);
    placeholder.remove();
    grid.classList.remove("drag-has-placeholder");
    card.getAnimations().forEach(animation => animation.cancel());
    card.classList.remove("dragging", "music-track-floating");
    card.style.removeProperty("width");
    card.style.removeProperty("height");
    card.style.removeProperty("left");
    card.style.removeProperty("top");
    card.style.removeProperty("transform");
  };

  if (!animate) {
    cleanup();
    return Promise.resolve();
  }

  if (Math.hypot(startRect.left - targetRect.left, startRect.top - targetRect.top) <= musicSettleSnapDistance) {
    return new Promise(resolve => {
      cleanupFrame = window.requestAnimationFrame(() => {
        cleanupFrame = 0;
        cleanup();
        resolve();
      });
    });
  }

  return new Promise(resolve => {
    const finishCleanup = () => {
      if (cleanupFrame) return;
      if (settleFrame) {
        window.cancelAnimationFrame(settleFrame);
        settleFrame = 0;
      }
      cleanupFrame = window.requestAnimationFrame(() => {
        cleanupFrame = 0;
        cleanup();
        resolve();
      });
    };
    const dx = startRect.left - targetRect.left;
    const dy = startRect.top - targetRect.top;
    const maxDuration = Math.max(
      musicSettleMaxDurationMs,
      musicSettleAnimationDurationFor(dx, dy) + 180
    );
    let offsetX = dx;
    let offsetY = dy;
    let velocityX = musicSettleVelocityFor(offsetX, motion.velocityX);
    let velocityY = musicSettleVelocityFor(offsetY, motion.velocityY);
    let lastTime = musicAnimationNow();
    const startTime = lastTime;
    card.style.left = `${targetRect.left}px`;
    card.style.top = `${targetRect.top}px`;
    card.style.transform = musicFloatingTrackTransform(offsetX, offsetY);
    const tick = timestamp => {
      const now = timestamp || musicAnimationNow();
      const elapsed = lastTime
        ? clamp(now - lastTime, musicDragMinStepMs, musicSettleMaxStepMs)
        : musicDragFrameMs;
      const deltaSeconds = elapsed / 1000;
      const nextX = musicDampedSpringStep(offsetX, 0, velocityX, deltaSeconds, musicSettleSpringFrequency);
      const nextY = musicDampedSpringStep(offsetY, 0, velocityY, deltaSeconds, musicSettleSpringFrequency);
      offsetX = nextX.value;
      offsetY = nextY.value;
      velocityX = musicDampSettledAxisVelocity(offsetX, nextX.velocity, deltaSeconds);
      velocityY = musicDampSettledAxisVelocity(offsetY, nextY.velocity, deltaSeconds);
      lastTime = now;
      card.style.transform = musicFloatingTrackTransform(offsetX, offsetY);
      const isSettled = Math.hypot(offsetX, offsetY) <= musicSettleSnapDistance &&
        Math.hypot(velocityX, velocityY) <= musicSettleVelocitySnap;
      if (isSettled || now - startTime >= maxDuration) {
        finishCleanup();
        return;
      }
      settleFrame = window.requestAnimationFrame(tick);
    };
    fallbackTimer = window.setTimeout(finishCleanup, maxDuration + 160);
    settleFrame = window.requestAnimationFrame(tick);
  });
}

function createMusicTrackDragSession(card, item, startX, startY) {
  const sourceSection = card.closest(".music-tier-section");
  const sourceGrid = musicGridForSection(sourceSection);
  const rect = card.getBoundingClientRect();
  const placeholder = document.createElement("div");
  placeholder.className = "track-card music-track-placeholder";
  placeholder.style.minHeight = `${rect.height}px`;
  placeholder.style.height = `${rect.height}px`;
  placeholder.setAttribute("aria-hidden", "true");
  let dragging = false;
  let lastTarget = { section: sourceSection, tierId: sourceSection?.dataset.tier || tierForTrack(item), beforePath: "" };
  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  const draggedVisualWidth = rect.width * musicFloatingTrackScale;
  const draggedVisualHeight = rect.height * musicFloatingTrackScale;
  const sourceBeforePath = card.nextElementSibling?.dataset?.trackPath || "";
  const trackDirectionX = createMusicDragDirectionTracker(startX);
  const trackDirectionY = createMusicDragDirectionTracker(startY);
  let pendingMovePoint = null;
  let moveFrame = 0;
  let visualFrame = 0;
  let visualLeft = rect.left;
  let visualTop = rect.top;
  let visualVelocityX = 0;
  let visualVelocityY = 0;
  let targetLeft = rect.left;
  let targetTop = rect.top;
  let visualTargetLeft = rect.left;
  let visualTargetTop = rect.top;
  let takeoffUntilTime = 0;
  let lastVisualFrameTime = 0;
  let lastDirectionX = 0;
  let lastDirectionY = 0;

  const paintDraggedCard = () => {
    card.style.transform = musicFloatingTrackTransform(visualLeft - rect.left, visualTop - rect.top);
  };

  const advanceVisualFollow = timestamp => {
    const now = timestamp || musicAnimationNow();
    const isTakingOff = now < takeoffUntilTime;
    const minStep = isTakingOff ? musicDragTakeoffMinStepMs : musicDragMinStepMs;
    const elapsed = lastVisualFrameTime
      ? clamp(now - lastVisualFrameTime, minStep, musicDragMaxStepMs)
      : musicDragFrameMs;
    const smoothingMs = isTakingOff ? musicDragTakeoffTargetSmoothingMs : musicDragVisualTargetSmoothingMs;
    const targetBlend = 1 - Math.exp(-elapsed / Math.max(1, smoothingMs));
    visualTargetLeft += (targetLeft - visualTargetLeft) * targetBlend;
    visualTargetTop += (targetTop - visualTargetTop) * targetBlend;
    if (Math.hypot(targetLeft - visualTargetLeft, targetTop - visualTargetTop) <= musicDragVisualTargetSnapDistance) {
      visualTargetLeft = targetLeft;
      visualTargetTop = targetTop;
    }
    const targetSettled = visualTargetLeft === targetLeft && visualTargetTop === targetTop;
    const dx = visualTargetLeft - visualLeft;
    const dy = visualTargetTop - visualTop;
    if (
      targetSettled &&
      Math.hypot(dx, dy) <= musicDragVisualSnapDistance &&
      Math.hypot(visualVelocityX, visualVelocityY) <= musicDragSpringSnapSpeed
    ) {
      visualLeft = visualTargetLeft;
      visualTop = visualTargetTop;
      visualVelocityX = 0;
      visualVelocityY = 0;
      lastVisualFrameTime = now;
      paintDraggedCard();
      return false;
    }
    const frequency = isTakingOff ? musicDragTakeoffSpringFrequency : musicDragSpringFrequency;
    const deltaSeconds = elapsed / 1000;
    if (dx * visualVelocityX + dy * visualVelocityY < 0) {
      const damping = musicFrameAdjustedDamping(musicDragOpposingVelocityDamping, deltaSeconds);
      visualVelocityX *= damping;
      visualVelocityY *= damping;
    }
    visualVelocityX = musicDampSettledAxisVelocity(dx, visualVelocityX, deltaSeconds);
    visualVelocityY = musicDampSettledAxisVelocity(dy, visualVelocityY, deltaSeconds);
    const nextX = musicDampedSpringStep(visualLeft, visualTargetLeft, visualVelocityX, deltaSeconds, frequency);
    const nextY = musicDampedSpringStep(visualTop, visualTargetTop, visualVelocityY, deltaSeconds, frequency);
    const baseMaxVisualStep = isTakingOff ? musicDragTakeoffMaxVisualStep : musicDragMaxVisualStep;
    const maxVisualStepRatio = isTakingOff ? musicDragTakeoffMaxVisualStepRatio : musicDragMaxVisualStepRatio;
    const targetDistance = Math.hypot(visualTargetLeft - visualLeft, visualTargetTop - visualTop);
    const softMaxVisualStep = isTakingOff
      ? baseMaxVisualStep
      : baseMaxVisualStep + Math.sqrt(targetDistance) * musicDragMaxVisualStepSqrtFactor;
    const maxVisualStep = Math.min(
      softMaxVisualStep,
      Math.max(musicDragMinVisualStep, targetDistance * maxVisualStepRatio)
    );
    const limited = musicLimitVisualStep(
      visualLeft,
      visualTop,
      nextX.value,
      nextY.value,
      nextX.velocity,
      nextY.velocity,
      deltaSeconds,
      maxVisualStep
    );
    visualLeft = limited.left;
    visualTop = limited.top;
    visualVelocityX = limited.velocityX;
    visualVelocityY = limited.velocityY;
    lastVisualFrameTime = now;
    if (
      targetSettled &&
      Math.hypot(visualTargetLeft - visualLeft, visualTargetTop - visualTop) <= musicDragVisualSnapDistance &&
      Math.hypot(visualVelocityX, visualVelocityY) <= musicDragSpringSnapSpeed
    ) {
      visualLeft = visualTargetLeft;
      visualTop = visualTargetTop;
      visualVelocityX = 0;
      visualVelocityY = 0;
    }
    paintDraggedCard();
    return true;
  };

  const currentDraggedRect = (mode = "visual") => musicRectFromPosition(
    mode === "target"
      ? targetLeft
      : mode === "intent"
        ? visualLeft + (targetLeft - visualLeft) * musicDragIntentProbeLead
        : visualLeft,
    mode === "target"
      ? targetTop
      : mode === "intent"
        ? visualTop + (targetTop - visualTop) * musicDragIntentProbeLead
        : visualTop,
    draggedVisualWidth,
    draggedVisualHeight
  );

  const syncPlaceholderToDraggedRect = (draggedRect, { force = false } = {}) => {
    const probeX = draggedRect.left + draggedRect.width / 2;
    const probeY = draggedRect.top + draggedRect.height / 2;
    lastTarget = musicDropTargetAtPoint(
      probeX,
      probeY,
      lastTarget.section || sourceSection,
      lastDirectionX,
      lastDirectionY,
      draggedRect
    );
    if (lastTarget.section && isValidMusicTier(lastTarget.tierId)) {
      const placeholderMoveState = moveMusicPlaceholder(
        placeholder,
        lastTarget.section,
        probeX,
        probeY,
        lastDirectionX,
        lastDirectionY,
        draggedRect,
        { force }
      );
      return placeholderMoveState;
    }
    return "none";
  };

  const runVisualFollow = timestamp => {
    visualFrame = 0;
    if (!dragging) return;
    const shouldContinue = advanceVisualFollow(timestamp);
    const placeholderMoveState = syncPlaceholderToDraggedRect(currentDraggedRect("intent"));
    if (shouldContinue || placeholderMoveState === "deferred") {
      scheduleVisualFollow();
    }
  };

  const scheduleVisualFollow = () => {
    if (!visualFrame) {
      visualFrame = window.requestAnimationFrame(runVisualFollow);
    }
  };

  const stopVisualFollow = () => {
    if (visualFrame) {
      window.cancelAnimationFrame(visualFrame);
      visualFrame = 0;
    }
  };

  const moveCardToPoint = (clientX, clientY, { paint = true, useTargetRect = false } = {}) => {
    const clamped = clampDragPosition(clientX, clientY, offsetX, offsetY, rect.width, rect.height);
    targetLeft = clamped.left;
    targetTop = clamped.top;
    if (paint && advanceVisualFollow()) {
      scheduleVisualFollow();
    }
    return currentDraggedRect(useTargetRect ? "target" : "intent");
  };

  const startDragging = () => {
    dragging = true;
    draggedTrackPath = item.path;
    sourceGrid.insertBefore(placeholder, card);
    sourceGrid.classList.add("drag-has-placeholder");
    animateMusicPlaceholderIntro(placeholder);
    document.body.appendChild(card);
    card.classList.add("dragging", "music-track-floating");
    card.style.width = `${rect.width}px`;
    card.style.height = `${rect.height}px`;
    card.style.left = `${rect.left}px`;
    card.style.top = `${rect.top}px`;
    visualLeft = rect.left;
    visualTop = rect.top;
    visualVelocityX = 0;
    visualVelocityY = 0;
    targetLeft = rect.left;
    targetTop = rect.top;
    visualTargetLeft = rect.left;
    visualTargetTop = rect.top;
    lastVisualFrameTime = musicAnimationNow();
    takeoffUntilTime = lastVisualFrameTime + musicDragTakeoffDurationMs;
    paintDraggedCard();
    document.body.classList.add("music-track-dragging");
  };

  const processMove = (clientX, clientY, options = {}) => {
    const { allowStart = true, forcePlaceholder = false } = options;
    const dx = clientX - startX;
    const dy = clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < musicDragStartThreshold) return false;
    if (!dragging && !allowStart) return false;
    if (!dragging) {
      startDragging();
    }
    const draggedRect = moveCardToPoint(clientX, clientY, {
      ...options,
      useTargetRect: forcePlaceholder
    });
    lastDirectionX = trackDirectionX(clientX);
    lastDirectionY = trackDirectionY(clientY);
    if (syncPlaceholderToDraggedRect(draggedRect, { force: forcePlaceholder }) === "deferred") {
      scheduleVisualFollow();
    }
    return true;
  };

  const flushPendingMove = (options = {}) => {
    if (moveFrame) {
      window.cancelAnimationFrame(moveFrame);
      moveFrame = 0;
    }
    const point = pendingMovePoint;
    pendingMovePoint = null;
    return point ? processMove(point.clientX, point.clientY, options) : false;
  };

  const finish = shouldCommit => {
    flushPendingMove({ allowStart: dragging, paint: false, forcePlaceholder: true });
    if (!dragging) return false;
    advanceVisualFollow(musicAnimationNow());
    const settleMotion = {
      velocityX: visualVelocityX,
      velocityY: visualVelocityY
    };
    stopVisualFollow();
    suppressTrackClickUntil = Date.now() + 240;
    draggedTrackPath = "";
    clearMusicTierDragState();
    document.body.classList.remove("music-track-dragging");

    if (!shouldCommit || !isValidMusicTier(lastTarget.tierId)) {
      const sourceBefore = sourceBeforePath
        ? Array.from(sourceGrid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"))
          .find(node => node.dataset.trackPath === sourceBeforePath)
        : null;
      placeMusicPlaceholder(placeholder, sourceGrid, sourceBefore, true);
      return settleDraggedMusicTrack(card, placeholder, true, settleMotion).then(() => false);
    }

    const targetSection = placeholder.closest(".music-tier-section");
    const tierId = targetSection?.dataset.tier || lastTarget.tierId;
    const beforePath = musicBeforePathFromPlaceholder(placeholder);
    moveTrackToTier(item.path, tierId, beforePath);
    return settleDraggedMusicTrack(card, placeholder, true, settleMotion).then(afterMusicAnimationFrame).then(() => {
      renderMusic();
      return true;
    });
  };

  const move = moveEvent => {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < musicDragStartThreshold) return false;
    moveEvent.preventDefault();
    pendingMovePoint = { clientX: moveEvent.clientX, clientY: moveEvent.clientY };
    if (!moveFrame) {
      moveFrame = window.requestAnimationFrame(() => {
        moveFrame = 0;
        const point = pendingMovePoint;
        pendingMovePoint = null;
        if (point) processMove(point.clientX, point.clientY);
      });
    }
    return dragging;
  };

  return {
    finish,
    isDragging: () => dragging,
    move
  };
}

function beginMusicTrackPointerDrag(event, card, item) {
  if (isBlockedMusicTrackDragEvent(event, item) || event.pointerType === "mouse") return;
  lastTrackPointerStart = Date.now();
  const dragSession = createMusicTrackDragSession(card, item, event.clientX, event.clientY);

  const cleanup = () => {
    card.removeEventListener("pointermove", move);
    card.removeEventListener("pointerup", up);
    card.removeEventListener("pointercancel", cancel);
  };

  const finish = shouldCommit => {
    cleanup();
    dragSession.finish(shouldCommit);
  };

  const move = moveEvent => {
    dragSession.move(moveEvent);
  };

  const up = upEvent => {
    if (card.hasPointerCapture(upEvent.pointerId)) {
      try {
        card.releasePointerCapture(upEvent.pointerId);
      } catch {}
    }
    if (dragSession.isDragging()) upEvent.preventDefault();
    finish(true);
  };

  const cancel = () => finish(false);

  card.setPointerCapture(event.pointerId);
  card.addEventListener("pointermove", move);
  card.addEventListener("pointerup", up);
  card.addEventListener("pointercancel", cancel);
}

function beginMusicTrackMouseDrag(event, card, item) {
  if (isBlockedMusicTrackDragEvent(event, item) || Date.now() - lastTrackPointerStart < 80) return;
  const dragSession = createMusicTrackDragSession(card, item, event.clientX, event.clientY);

  const cleanup = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
  };

  const finish = shouldCommit => {
    cleanup();
    dragSession.finish(shouldCommit);
  };

  const move = moveEvent => {
    dragSession.move(moveEvent);
  };

  const up = () => finish(true);

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function assignTrackTier(path, tierId, shouldPersist = true) {
  const cleanTier = normalizeMusicTier(tierId);
  if (cleanTier === "third") {
    delete musicTierAssignments[path];
  } else {
    musicTierAssignments[path] = cleanTier;
  }
  if (shouldPersist) saveMusicTierAssignments();
}

function reorderTrackWithinTier(path, tierId, beforePath = "") {
  const movingTrack = tracks.find(item => item.path === path);
  if (!movingTrack) return;

  const cleanTier = normalizeMusicTier(tierId);
  const tracksByTier = Object.fromEntries(musicTierGroups.map(group => [group.id, []]));
  for (const item of orderedLocalTracks()) {
    if (item.path !== path) {
      tracksByTier[tierForTrack(item)].push(item);
    }
  }

  const targetList = tracksByTier[cleanTier];
  const insertIndex = beforePath && beforePath !== path
    ? targetList.findIndex(item => item.path === beforePath)
    : -1;
  if (insertIndex >= 0) {
    targetList.splice(insertIndex, 0, movingTrack);
  } else {
    targetList.push(movingTrack);
  }

  musicTierOrder = musicTierGroups.flatMap(group => tracksByTier[group.id].map(item => item.path));
}

function cleanMusicArrangementState(state) {
  const localPaths = new Set(tracks.map(item => item.path));
  const rawTiers = state?.tiers && typeof state.tiers === "object" && !Array.isArray(state.tiers) ? state.tiers : {};
  const tiers = Object.fromEntries(
    Object.entries(rawTiers)
      .map(([path, tierId]) => [String(path), normalizeMusicTier(String(tierId || ""))])
      .filter(([path, tierId]) => path && localPaths.has(path) && tierId !== "third")
  );
  const seen = new Set();
  const order = sanitizeMusicTierOrder(state?.order || [])
    .filter(path => {
      if (!localPaths.has(path) || seen.has(path)) return false;
      seen.add(path);
      return true;
    });
  for (const item of tracks) {
    if (!seen.has(item.path)) {
      order.push(item.path);
      seen.add(item.path);
    }
  }
  return { tiers, order };
}

function musicArrangementSnapshot() {
  return cleanMusicArrangementState({
    tiers: { ...musicTierAssignments },
    order: [...musicTierOrder]
  });
}

function applyMusicArrangementHistory(state) {
  const nextState = cleanMusicArrangementState(state);
  animateMusicTrackReflow(() => {
    musicTierAssignments = nextState.tiers;
    musicTierOrder = nextState.order;
    persistMusicStateNow();
    renderMusic();
  });
  renderMusicLibraries();
}

function recordMusicArrangementChange(beforeState, afterState) {
  const before = cleanMusicArrangementState(beforeState);
  const after = cleanMusicArrangementState(afterState);
  if (historyValuesEqual(before, after)) return;
  pushConsoleHistory({
    type: "music-arrangement",
    before,
    after,
    apply: applyMusicArrangementHistory
  });
}

function moveTrackToTier(path, tierId, beforePath = "") {
  if (!localTrackExists(path)) return;
  const beforeState = musicArrangementSnapshot();
  assignTrackTier(path, tierId, false);
  reorderTrackWithinTier(path, tierId, beforePath);
  persistMusicStateNow();
  recordMusicArrangementChange(beforeState, musicArrangementSnapshot());
}

function setTrackTier(path, tierId, beforePath = "") {
  if (!localTrackExists(path)) return;
  moveTrackToTier(path, tierId, beforePath);
  renderMusic();
}

function setSelectedTrack(path) {
  pendingDeleteTrackPath = "";
  musicNotice = "";
  setSelectedTrackPath(path, { persist: "now" });
  renderMusic();
  renderMusicLibraries();
}

function requestDeleteTrack(item) {
  pendingDeleteTrackPath = item.path;
  renderMusic();
  renderMusicLibraries();
}

function cancelDeleteTrack() {
  if (!pendingDeleteTrackPath) return;
  pendingDeleteTrackPath = "";
  renderMusic();
  renderMusicLibraries();
}

function trackMeta(item) {
  if (!item) return text("musicEmptyBody");
  return text("trackMeta", item.type || "audio", formatBytes(item.size));
}

function loadPromotedLibraryTracks() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKeys.promotedLibraryTracks) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    return Object.fromEntries(
      Object.entries(raw)
        .map(([libraryPath, localPath]) => [String(libraryPath), String(localPath)])
        .filter(([libraryPath, localPath]) => libraryPath && localPath)
    );
  } catch {
    return {};
  }
}

function savePromotedLibraryTracks() {
  persistMusicStateNow();
}

function markPromotedLibraryTrack(libraryPath, localPath) {
  if (!libraryPath || !localPath) return;
  promotedLibraryTracks[libraryPath] = localPath;
  savePromotedLibraryTracks();
}

function isLibraryTrackPromoted(track) {
  return Boolean(promotedLibraryTracks[track?.path]);
}

function localTrackIdentityKeys() {
  return new Set(tracks.map(item => trackIdentityKey(item.name)).filter(Boolean));
}

function isLibraryTrackDuplicate(track, localKeys = localTrackIdentityKeys()) {
  const key = trackIdentityKey(track?.name);
  return Boolean(key && localKeys.has(key));
}

function flattenLibraryTracks(libraries = musicLibraries) {
  const localKeys = localTrackIdentityKeys();
  return libraries.flatMap(library =>
    Array.isArray(library.tracks)
      ? library.tracks.map(track => ({ ...track, libraryId: library.id, libraryName: library.name || "Library" }))
      : []
  ).filter(item => !isLibraryTrackPromoted(item) && !isLibraryTrackDuplicate(item, localKeys));
}

function renderMusicLibraries() {
  if (!hasMusic || !els.musicLibraryDock) return;

  libraryTracks = flattenLibraryTracks();
  if (els.musicLibrarySection) {
    els.musicLibrarySection.hidden = !libraryTracks.length;
  }
  els.musicLibraryCount.textContent = text("trackCount", libraryTracks.length);
  setMusicLibraryStatus(musicLibraryNotice);
  els.musicLibraryDock.innerHTML = "";

  if (!libraryTracks.length) {
    return;
  }

  for (const item of libraryTracks) {
    els.musicLibraryDock.appendChild(createTrackCard(item));
  }

  els.musicLibraryDock.appendChild(createMusicLibraryAddCard());
}

function setMusicImportBusy(isBusy) {
  for (const node of document.querySelectorAll(".music-add-card")) {
    node.classList.toggle("busy", Boolean(isBusy));
  }
  for (const node of document.querySelectorAll(".music-library-add-card")) {
    node.classList.toggle("busy", Boolean(isBusy));
  }
  for (const node of document.querySelectorAll("#addMusic, #addMusicByUrl, #addMusicByFile, #addMusicByLibrary, #musicAddCookieButton, #musicAddUrlInput, #musicAddLibraryInput, .music-add-file-button, .music-link-input, .music-link-submit, .music-cookie-file-button")) {
    node.disabled = Boolean(isBusy);
  }
  updateMusicAddCookieLabel();
}

function updateMusicAddCookieLabel() {
  if (!els.musicAddCookieButton) return;
  els.musicAddCookieButton.textContent = musicCookieState.available ? text("musicCookieReady") : text("musicCookieFile");
}

function setMusicAddMenuMode(mode = "") {
  if (!els.musicAddMenu) return;
  els.musicAddMenu.dataset.mode = mode;
  if (els.musicAddUrlForm) els.musicAddUrlForm.hidden = mode !== "url";
  if (els.musicAddLibraryForm) els.musicAddLibraryForm.hidden = mode !== "library";
  setMusicAddStatus(mode === "url" ? musicLinkNotice : mode === "library" ? musicLibraryNotice : "");
  const input = mode === "url" ? els.musicAddUrlInput : mode === "library" ? els.musicAddLibraryInput : null;
  if (input) {
    window.requestAnimationFrame(() => input.focus());
  }
}

function setMusicAddMenuOpen(isOpen) {
  if (!els.musicAddMenu || !els.addMusic) return;
  els.musicAddMenu.hidden = !isOpen;
  els.addMusic.setAttribute("aria-expanded", String(Boolean(isOpen)));
  updateMusicAddCookieLabel();
  if (isOpen && !activeMusicAddMode()) {
    setMusicAddMenuMode("url");
  } else if (!isOpen) {
    setMusicAddMenuMode("");
  }
}

function toggleMusicAddMenu(event) {
  event.preventDefault();
  event.stopPropagation();
  const shouldOpen = Boolean(els.musicAddMenu?.hidden);
  setMusicAddMenuOpen(shouldOpen);
}

function showMusicAddUrlForm() {
  setMusicAddMenuOpen(true);
  setMusicAddMenuMode("url");
}

function showMusicAddLibraryForm() {
  setMusicAddMenuOpen(true);
  setMusicAddMenuMode("library");
}

function submitMusicAddUrl(event) {
  event.preventDefault();
  importMusicUrl(els.musicAddUrlInput?.value || "", false);
}

function submitMusicAddLibrary(event) {
  event.preventDefault();
  importMusicLibrary(els.musicAddLibraryInput?.value || "");
}

function createMusicAddCard() {
  const card = document.createElement("div");
  card.className = "music-add-card music-link-card";
  card.title = text("musicLinkPlaceholder");

  const body = document.createElement("div");
  body.className = "music-add-body";

  const form = document.createElement("form");
  form.className = "music-link-form";

  const input = document.createElement("input");
  input.id = "musicLinkInput";
  input.className = "music-link-input";
  input.type = "text";
  input.inputMode = "url";
  input.placeholder = text("musicLinkPlaceholder");
  input.setAttribute("aria-label", text("musicLinkPlaceholder"));
  form.appendChild(input);

  const submit = document.createElement("button");
  submit.className = "music-link-submit";
  submit.type = "submit";
  submit.textContent = text("musicLinkDownload");
  form.appendChild(submit);

  form.addEventListener("submit", event => {
    event.preventDefault();
    importMusicUrl(input.value, false);
  });
  body.appendChild(form);

  const cookieTools = document.createElement("div");
  cookieTools.className = "music-cookie-tools";

  const cookieFileButton = document.createElement("button");
  cookieFileButton.className = "music-cookie-file-button";
  cookieFileButton.type = "button";
  cookieFileButton.textContent = musicCookieState.available ? text("musicCookieReady") : text("musicCookieFile");
  cookieFileButton.addEventListener("click", () => {
    if (els.musicCookieFileInput) els.musicCookieFileInput.click();
  });
  cookieTools.appendChild(cookieFileButton);
  body.appendChild(cookieTools);

  const status = document.createElement("span");
  status.id = "musicLinkStatus";
  status.className = "music-link-status";
  status.textContent = musicLinkNotice || "";
  body.appendChild(status);

  card.appendChild(body);
  card.addEventListener("click", event => {
    if (event.target.closest("button, input")) return;
    input.focus();
  });

  for (const eventName of ["dragenter", "dragover"]) {
    card.addEventListener(eventName, event => {
      event.preventDefault();
      event.stopPropagation();
      card.classList.add("drag-over");
    });
  }
  card.addEventListener("dragleave", event => {
    if (!card.contains(event.relatedTarget)) {
      card.classList.remove("drag-over");
    }
  });
  card.addEventListener("drop", handleMusicUrlDrop);

  return card;
}

function createMusicLibraryAddCard() {
  const card = document.createElement("div");
  card.className = "music-add-card music-link-card music-library-add-card";
  card.title = text("musicLinkPlaceholder");

  const body = document.createElement("div");
  body.className = "music-add-body";

  const form = document.createElement("form");
  form.className = "music-link-form";

  const input = document.createElement("input");
  input.id = "musicLibraryLinkInput";
  input.className = "music-link-input";
  input.type = "text";
  input.inputMode = "url";
  input.placeholder = text("musicLinkPlaceholder");
  input.setAttribute("aria-label", text("musicLinkPlaceholder"));
  form.appendChild(input);

  const submit = document.createElement("button");
  submit.className = "music-link-submit";
  submit.type = "submit";
  submit.textContent = text("musicLinkDownload");
  form.appendChild(submit);

  form.addEventListener("submit", event => {
    event.preventDefault();
    importMusicLibrary(input.value);
  });
  body.appendChild(form);

  const cookieTools = document.createElement("div");
  cookieTools.className = "music-cookie-tools";

  const cookieFileButton = document.createElement("button");
  cookieFileButton.className = "music-cookie-file-button";
  cookieFileButton.type = "button";
  cookieFileButton.textContent = musicCookieState.available ? text("musicCookieReady") : text("musicCookieFile");
  cookieFileButton.addEventListener("click", () => {
    if (els.musicCookieFileInput) els.musicCookieFileInput.click();
  });
  cookieTools.appendChild(cookieFileButton);
  body.appendChild(cookieTools);

  const hint = document.createElement("span");
  hint.id = "musicLibraryStatus";
  hint.className = "music-link-status";
  hint.textContent = musicLibraryNotice || "";
  body.appendChild(hint);
  card.appendChild(body);
  card.addEventListener("click", event => {
    if (event.target.closest("button, input")) return;
    input.focus();
  });

  for (const eventName of ["dragenter", "dragover"]) {
    card.addEventListener(eventName, event => {
      event.preventDefault();
      event.stopPropagation();
      card.classList.add("drag-over");
    });
  }
  card.addEventListener("dragleave", event => {
    if (!card.contains(event.relatedTarget)) {
      card.classList.remove("drag-over");
    }
  });
  card.addEventListener("drop", handleMusicLibraryDrop);

  return card;
}

function hasActiveMusicLibraryGrab() {
  return musicLibraries.some(item => item.status === "queued" || item.status === "grabbing");
}

function stopMusicLibraryPoll() {
  if (musicLibraryPollTimer) {
    window.clearTimeout(musicLibraryPollTimer);
    musicLibraryPollTimer = null;
  }
}

function scheduleMusicLibraryPoll(delay = 4000) {
  stopMusicLibraryPoll();
  if (!hasActiveMusicLibraryGrab() || !isModuleForeground("music")) return;
  musicLibraryPollTimer = window.setTimeout(() => {
    musicLibraryPollTimer = null;
    if (!isModuleForeground("music")) return;
    loadMusic();
  }, delay);
}

function createTrackCard(item) {
  const displayName = displayTrackName(item.name);
  const card = document.createElement("div");
  card.className = `track-card ${item.path === selectedTrackPath ? "active" : ""} ${item.path === pendingDeleteTrackPath ? "pending-delete" : ""}`;
  card.dataset.trackPath = item.path;
  card.tabIndex = 0;
  card.title = text("trackTitle", displayName);
  card.setAttribute("role", "button");
  card.draggable = Boolean(item.libraryId);
  card.addEventListener("selectstart", event => event.preventDefault());
  card.addEventListener("pointerdown", event => beginMusicTrackPointerDrag(event, card, item));
  card.addEventListener("mousedown", event => beginMusicTrackMouseDrag(event, card, item));
  card.addEventListener("dragstart", event => {
    if (event.target.closest(".delete-track-button, .delete-popover")) {
      event.preventDefault();
      return;
    }
    window.getSelection()?.removeAllRanges();
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-control-music-track", item.path);
    event.dataTransfer.setData("text/plain", displayName);
    if (item.libraryId) {
      event.dataTransfer.setData("application/x-control-library-track", item.path);
    } else {
      event.dataTransfer.setData("application/x-control-local-track", item.path);
    }
    if (typeof event.dataTransfer.setDragImage === "function") {
      event.dataTransfer.setDragImage(card, 24, 24);
    }
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    els.musicDock?.classList.remove("drag-over");
    clearMusicDropMarkers();
  });
  if (item.libraryId) {
    card.classList.add("library-track-card");
  }
  card.addEventListener("click", event => {
    if (event.target.closest("button, input, select, textarea, a")) return;
    if (Date.now() < suppressTrackClickUntil) return;
    playTrack(item);
  });
  card.addEventListener("dblclick", event => {
    if (event.target.closest("button, input, select, textarea, a")) return;
    if (Date.now() < suppressTrackClickUntil) return;
    playTrack(item);
  });
  card.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      playTrack(item);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      requestDeleteTrack(item);
    } else if (event.key === "Escape") {
      cancelDeleteTrack();
    }
  });
  card.addEventListener("contextmenu", event => {
    event.preventDefault();
    requestDeleteTrack(item);
  });

  const marker = document.createElement("div");
  marker.className = "track-marker";
  marker.textContent = item.path === selectedTrackPath && !els.audioPlayer.paused ? "♫" : "▶";
  card.appendChild(marker);

  const body = document.createElement("div");
  body.className = "track-body";

  const title = document.createElement("strong");
  title.textContent = displayName;
  body.appendChild(title);

  const meta = document.createElement("span");
  meta.textContent = trackMeta(item);
  body.appendChild(meta);
  card.appendChild(body);

  const deleteButton = document.createElement("button");
  deleteButton.className = "delete-track-button";
  deleteButton.type = "button";
  deleteButton.draggable = false;
  deleteButton.textContent = "\u00d7";
  deleteButton.title = text("deleteTrackLabel", displayName);
  deleteButton.setAttribute("aria-label", text("deleteTrackLabel", displayName));
  deleteButton.addEventListener("click", event => {
    event.stopPropagation();
    requestDeleteTrack(item);
  });
  card.appendChild(deleteButton);

  if (item.path === pendingDeleteTrackPath) {
    const confirm = document.createElement("div");
    confirm.className = "delete-popover";
    confirm.addEventListener("click", event => event.stopPropagation());

    const prompt = document.createElement("strong");
    prompt.textContent = text("deletePrompt");
    confirm.appendChild(prompt);

    const confirmButton = document.createElement("button");
    confirmButton.className = "confirm-delete";
    confirmButton.type = "button";
    confirmButton.textContent = text("confirmDeleteAction");
    confirmButton.addEventListener("click", () => deleteTrack(item));
    confirm.appendChild(confirmButton);

    const cancelButton = document.createElement("button");
    cancelButton.className = "cancel-delete";
    cancelButton.type = "button";
    cancelButton.textContent = text("cancelDeleteAction");
    cancelButton.addEventListener("click", cancelDeleteTrack);
    confirm.appendChild(cancelButton);

    card.appendChild(confirm);
  }

  return card;
}

function createMusicTierSection(group, items) {
  const section = document.createElement("section");
  section.className = `music-tier-section music-tier-${group.id}`;
  section.dataset.tier = group.id;
  section.addEventListener("dblclick", event => {
    if (event.target.closest(".track-card, button, input, select, textarea, a, .delete-popover")) return;
    event.preventDefault();
    toggleMusicTierExpansion(group.id);
  });

  const head = document.createElement("div");
  head.className = "music-tier-head";

  const title = document.createElement("strong");
  title.textContent = text(group.labelKey);
  head.appendChild(title);

  const count = document.createElement("span");
  count.textContent = text("trackCount", items.length);
  head.appendChild(count);
  section.appendChild(head);

  const grid = document.createElement("div");
  grid.className = `music-tier-track-grid ${items.length ? "" : "is-empty"}`.trim();

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "music-tier-empty";
    empty.textContent = text("musicTierDropHint");
    grid.appendChild(empty);
  } else {
    for (const item of items) {
      grid.appendChild(createTrackCard(item));
    }
  }

  for (const eventName of ["dragenter", "dragover"]) {
    section.addEventListener(eventName, event => {
      if (!transferHasTierTrack(event.dataTransfer)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "move";
      section.classList.add("drag-over");
      updateMusicDropMarker(section, event);
    });
  }

  section.addEventListener("dragleave", event => {
    if (!section.contains(event.relatedTarget)) {
      section.classList.remove("drag-over");
      clearMusicDropMarkers(section);
    }
  });

  section.addEventListener("drop", event => {
    if (!transferHasTierTrack(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    const beforePath = musicDropBeforePath(section, event);
    section.classList.remove("drag-over");
    clearMusicDropMarkers(section);
    if (transferHasLibraryTrack(event.dataTransfer)) {
      promoteLibraryTrack(libraryTrackPathFromTransfer(event.dataTransfer), group.id, beforePath);
      return;
    }
    setTrackTier(localTrackPathFromTransfer(event.dataTransfer), group.id, beforePath);
  });

  section.appendChild(grid);
  return section;
}

function parseLyricsTimestamp(raw) {
  const match = String(raw || "").match(/^(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?$/);
  if (!match) return null;
  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  const fraction = match[3] || "0";
  if (!Number.isFinite(minutes) || !Number.isFinite(seconds)) return null;
  const millis = Number(fraction.padEnd(3, "0").slice(0, 3));
  return minutes * 60 + seconds + millis / 1000;
}

function parseLyricsText(rawText, type = "lrc") {
  const rawLines = String(rawText || "").replace(/\r/g, "").split("\n");
  const timed = [];
  const plain = [];

  for (const rawLine of rawLines) {
    const line = rawLine.trim();
    if (!line) continue;
    if (type === "lrc" && /^\[(?:ar|al|ti|by|offset|length|re):/i.test(line)) continue;

    const tags = [...line.matchAll(/\[([0-9]{1,2}:[0-9]{2}(?:[.:][0-9]{1,3})?)\]/g)];
    const lyric = line.replace(/\[[^\]]+\]/g, "").trim();
    if (tags.length) {
      for (const tag of tags) {
        const time = parseLyricsTimestamp(tag[1]);
        if (time != null) timed.push({ time, text: lyric, rest: !lyric });
      }
      continue;
    }
    plain.push(line);
  }

  if (timed.length) {
    return {
      synced: true,
      lines: timed.sort((left, right) => left.time - right.time),
      status: ""
    };
  }

  return {
    synced: false,
    lines: plain.map((textLine, index) => ({ time: index, text: textLine })),
    status: plain.length ? text("lyricsUnsynced") : text("lyricsInstrumental")
  };
}

function clearMusicLyrics(status = text("lyricsEmpty")) {
  stopLyricsAnimationLoop();
  musicLyricsTrackPath = "";
  musicLyricsLines = [];
  musicLyricsStatus = status;
  musicLyricsActiveIndex = -1;
  musicLyricsSynced = false;
  musicLyricsAnalysis = null;
  musicLyricsLookupPath = "";
  renderLyricsPanel();
}

function isCompactLyricCharacter(char) {
  return /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]/u.test(char);
}

function lyricsTextParts(rawText) {
  const parts = [];
  let buffer = "";
  const flush = () => {
    if (!buffer) return;
    parts.push({ text: buffer, word: true });
    buffer = "";
  };
  for (const char of String(rawText || "...")) {
    if (/\s/u.test(char)) {
      flush();
      parts.push({ text: char, word: false });
    } else if (isCompactLyricCharacter(char)) {
      flush();
      parts.push({ text: char, word: true });
    } else {
      buffer += char;
    }
  }
  flush();
  return parts.length ? parts : [{ text: "...", word: true }];
}

function lyricsTimingTokens(rawText) {
  return lyricsTextParts(rawText).filter(part => part.word).map(part => part.text);
}

function renderLyricsWords(node, rawText) {
  node.textContent = "";
  const parts = lyricsTextParts(rawText);
  let wordIndex = 0;
  for (const part of parts) {
    if (!part.text) continue;
    if (!part.word) {
      node.appendChild(document.createTextNode(part.text));
      continue;
    }
    const word = document.createElement("span");
    word.className = "lyric-word";
    word.dataset.wordIndex = String(wordIndex);
    word.style.setProperty("--word-fill", "0");
    word.textContent = part.text;
    node.appendChild(word);
    wordIndex += 1;
  }
  node.dataset.wordCount = String(wordIndex);
}

function lyricsPanelMaxHeight() {
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;
  return Math.max(124, Math.min(560, viewportHeight - 260));
}

function cleanLyricsPanelHeight(value) {
  const height = Number(value);
  if (!Number.isFinite(height) || height <= 0) return 0;
  return Math.round(clamp(height, 124, lyricsPanelMaxHeight()));
}

function applyLyricsPanelHeight() {
  const panel = els.nowPlayingLyricsPanel;
  if (!panel) return;
  const height = cleanLyricsPanelHeight(musicLyricsPanelHeight);
  if (!height) {
    panel.style.height = "";
    panel.style.maxHeight = "";
    return;
  }
  musicLyricsPanelHeight = height;
  panel.style.height = `${height}px`;
  panel.style.maxHeight = `${height}px`;
}

function isLyricsPanelResizeEdge(event) {
  const panel = els.nowPlayingLyricsPanel;
  if (!panel || panel.hidden) return false;
  const rect = panel.getBoundingClientRect();
  return event.clientY >= rect.bottom - 14 && event.clientY <= rect.bottom + 4;
}

function setLyricsPanelResizeHover(event) {
  const panel = els.nowPlayingLyricsPanel;
  if (!panel || musicLyricsPanelResizing) return;
  panel.classList.toggle("can-resize", isLyricsPanelResizeEdge(event));
}

function clearLyricsPanelResizeHover() {
  if (musicLyricsPanelResizing) return;
  els.nowPlayingLyricsPanel?.classList.remove("can-resize");
}

function beginLyricsPanelResize(event) {
  if (event.button !== 0 || !isLyricsPanelResizeEdge(event)) return;
  const panel = els.nowPlayingLyricsPanel;
  if (!panel) return;
  event.preventDefault();
  event.stopPropagation();
  const rect = panel.getBoundingClientRect();
  musicLyricsPanelResizing = true;
  musicLyricsResizePointerId = event.pointerId;
  musicLyricsResizeStartY = event.clientY;
  musicLyricsResizeStartHeight = rect.height;
  panel.classList.add("can-resize", "resizing");
  document.body.classList.add("lyrics-resizing");
  try {
    panel.setPointerCapture(event.pointerId);
  } catch {}
  window.addEventListener("pointermove", moveLyricsPanelResize, { passive: false });
  window.addEventListener("pointerup", finishLyricsPanelResize);
  window.addEventListener("pointercancel", finishLyricsPanelResize);
}

function moveLyricsPanelResize(event) {
  if (!musicLyricsPanelResizing || event.pointerId !== musicLyricsResizePointerId) return;
  event.preventDefault();
  musicLyricsPanelHeight = cleanLyricsPanelHeight(musicLyricsResizeStartHeight + event.clientY - musicLyricsResizeStartY);
  applyLyricsPanelHeight();
}

function finishLyricsPanelResize(event) {
  if (!musicLyricsPanelResizing || event.pointerId !== musicLyricsResizePointerId) return;
  const panel = els.nowPlayingLyricsPanel;
  musicLyricsPanelResizing = false;
  musicLyricsResizePointerId = null;
  window.removeEventListener("pointermove", moveLyricsPanelResize);
  window.removeEventListener("pointerup", finishLyricsPanelResize);
  window.removeEventListener("pointercancel", finishLyricsPanelResize);
  try {
    panel?.releasePointerCapture(event.pointerId);
  } catch {}
  panel?.classList.remove("can-resize", "resizing");
  document.body.classList.remove("lyrics-resizing");
  suppressLyricsLineClickUntil = performance.now() + 260;
  if (musicLyricsPanelHeight) localStorage.setItem(storageKeys.lyricsHeight, String(musicLyricsPanelHeight));
}

function resizeLyricsPanelToViewport() {
  if (!musicLyricsPanelHeight) return;
  const nextHeight = cleanLyricsPanelHeight(musicLyricsPanelHeight);
  if (nextHeight !== musicLyricsPanelHeight) {
    musicLyricsPanelHeight = nextHeight;
    localStorage.setItem(storageKeys.lyricsHeight, String(musicLyricsPanelHeight));
  }
  applyLyricsPanelHeight();
}

function renderLyricsPanel() {
  if (!hasMusic || !els.nowPlayingLyricsPanel || !els.nowPlayingLyricsList || !els.nowPlayingLyricsStatus) return;
  const selected = selectedTrack();
  const selectedPath = selected?.path || "";
  const hasCachedLyrics = Boolean(selected?.lyricsUrl);
  const isPanelTrack = Boolean(selectedPath && musicLyricsTrackPath === selectedPath);
  const canShowLyrics = hasCachedLyrics || isPanelTrack;
  if (!canShowLyrics && musicLyricsTrackPath && !musicLyricsLookupPath) {
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
  }
  const isOpen = canShowLyrics && isPanelTrack;
  els.nowPlayingLyricsPanel.hidden = !isOpen;
  if (isOpen) applyLyricsPanelHeight();
  else {
    els.nowPlayingLyricsPanel.classList.remove("can-resize", "resizing");
    closeLyricsTimingEditor();
  }
  if (els.nowPlayingArt) {
    const label = hasCachedLyrics && selected
      ? text("lyricsButtonLabel", displayTrackName(selected.name))
      : selected
        ? text("lyricsFindLabel", displayTrackName(selected.name))
        : text("nowPlayingLabel");
    els.nowPlayingArt.classList.toggle("has-lyrics", hasCachedLyrics);
    els.nowPlayingArt.classList.toggle("can-find-lyrics", Boolean(selectedPath));
    els.nowPlayingArt.classList.toggle("lyrics-searching", Boolean(selectedPath && musicLyricsLookupPath === selectedPath));
    els.nowPlayingArt.title = selectedPath ? label : "";
    els.nowPlayingArt.setAttribute("aria-label", label);
    els.nowPlayingArt.setAttribute("aria-expanded", String(isOpen));
    els.nowPlayingArt.tabIndex = selectedPath ? 0 : -1;
  }
  detachLyricsTimingEditorFromList();
  els.nowPlayingLyricsList.innerHTML = "";
  els.nowPlayingLyricsPanel.classList.toggle("is-synced", musicLyricsSynced);
  els.nowPlayingLyricsPanel.classList.toggle("is-plain", !musicLyricsSynced && Boolean(musicLyricsLines.length));
  els.nowPlayingLyricsPanel.classList.toggle("has-active-line", musicLyricsActiveIndex >= 0);
  musicLyricsLines.forEach((line, index) => {
    const isRestLine = Boolean(line.rest);
    const canSeek = Boolean(musicLyricsSynced && Number.isFinite(line.time) && !isRestLine);
    const node = document.createElement(canSeek ? "button" : "p");
    node.className = "music-lyrics-line";
    node.dataset.lyricsIndex = String(index);
    const lineText = isRestLine ? "" : line.text || "...";
    node.classList.toggle("rest", isRestLine);
    node.setAttribute("aria-hidden", isRestLine ? "true" : "false");
    if (canSeek && !isRestLine) renderLyricsWords(node, lineText);
    else node.textContent = lineText;
    syncManualLyricMarkClasses(node, index);
    if (canSeek) {
      node.type = "button";
      node.title = text("lyricsSeekLabel", lineText);
      node.setAttribute("aria-label", text("lyricsSeekLabel", lineText));
      node.addEventListener("click", event => {
        if (performance.now() < suppressLyricsLineClickUntil) {
          event.preventDefault();
          return;
        }
        seekToLyricsLine(index);
      });
    }
    els.nowPlayingLyricsList.appendChild(node);
  });
  syncLyricsLineVisualStates(musicLyricsActiveIndex);
  els.nowPlayingLyricsStatus.textContent = musicLyricsStatus;
  els.nowPlayingLyricsStatus.hidden = Boolean(musicLyricsLines.length) && !musicLyricsStatus;
}

const lyricsLineSwitchLeadSeconds = 0.02;
const lyricsFirstLineLeadSeconds = 0.02;
const lyricsWordFillLeadSeconds = 0;
const lyricsMinWordFillSeconds = 0.72;
const lyricsWordFillOutroSeconds = 0.18;
const lyricsLineRestHoldSeconds = 0.34;
const lyricsLineRestFadeMinSeconds = 0.32;
const lyricsLineRestFadeMaxSeconds = 0.78;

function lyricsLineDisplayStartTime(index) {
  const rawStart = Number(musicLyricsLines[index]?.time);
  const analysisStart = lyricsLineAnalysisStartTime(index);
  const manualStart = manualLyricLineStartTime(index);
  if (Number.isFinite(manualStart)) {
    return manualStart - (index <= 0 ? lyricsFirstLineLeadSeconds : lyricsLineSwitchLeadSeconds);
  }
  let start = Number.isFinite(rawStart) ? rawStart : analysisStart;
  if (Number.isFinite(rawStart) && Number.isFinite(analysisStart)) {
    const analysisDelay = analysisStart - rawStart;
    start = analysisDelay > 0
      ? rawStart + Math.min(0.045, analysisDelay * 0.18)
      : analysisStart;
  }
  if (!Number.isFinite(start)) return start;
  return start - (index <= 0 ? lyricsFirstLineLeadSeconds : lyricsLineSwitchLeadSeconds);
}

function activeLyricsIndexAt(time) {
  if (!musicLyricsSynced || !musicLyricsLines.length || !musicLyricsLines[0] || !Number.isFinite(musicLyricsLines[0].time)) return -1;
  let active = -1;
  for (let index = 0; index < musicLyricsLines.length; index += 1) {
    if (time >= lyricsLineDisplayStartTime(index)) active = index;
    else break;
  }
  return active;
}

function easeLyricsValue(value) {
  const clean = clamp(Number(value) || 0, 0, 1);
  return clean * clean * (3 - 2 * clean);
}

function easeLyricsSegmentValue(value, previous = null, next = null, span = null) {
  const clean = clamp(Number(value) || 0, 0, 1);
  const fillDelta = Math.abs((Number(next?.fill) || 0) - (Number(previous?.fill) || 0));
  if (fillDelta <= 0.001) return clean;
  const waveDriven = Boolean(previous?.wave || next?.wave || span?.profile === "gated-cumulative");
  const holdDriven = Boolean(previous?.hold || next?.hold);
  if (waveDriven) {
    return clamp(clean * 0.88 + easeLyricsValue(clean) * 0.12, 0, 1);
  }
  if (holdDriven) {
    const attack = 1 - Math.pow(1 - clean, 1.35);
    return clamp(attack * 0.68 + easeLyricsValue(clean) * 0.32, 0, 1);
  }
  return easeLyricsValue(clean);
}

function easeLyricsWordFill(value, span = null) {
  const clean = clamp(Number(value) || 0, 0, 1);
  const attack = clamp(Number(span?.attack) || 0.5, 0.2, 1);
  const curve = String(span?.curve || "");
  if (curve === "strong") {
    const exponent = 1.75 + attack * 1.2;
    return 1 - Math.pow(1 - clean, exponent);
  }
  if (curve === "punctuated") {
    const head = clean < 0.78
      ? 1 - Math.pow(1 - clean / 0.78, 1.45 + attack)
      : 1;
    const tail = clean < 0.78 ? 0 : easeLyricsValue((clean - 0.78) / 0.22);
    return clamp(head * 0.94 + tail * 0.06, 0, 1);
  }
  const shaped = clean * clean * (3 - 2 * clean);
  return clamp(shaped * (0.82 + attack * 0.18) + clean * (0.18 - attack * 0.08), 0, 1);
}

function lyricsFillFromSpanPoints(elapsed, span = null) {
  const state = lyricsFillStateFromSpanPoints(elapsed, span);
  return state ? state.fill : NaN;
}

function lyricsFillStateFromSpanPoints(elapsed, span = null) {
  const rawPoints = Array.isArray(span?.fillPoints) ? span.fillPoints : [];
  if (rawPoints.length < 2) return null;
  const points = rawPoints
    .map(point => ({
      time: Number(point?.time),
      fill: clamp(Number(point?.fill) || 0, 0, 1),
      hold: Boolean(point?.hold),
      wave: Boolean(point?.wave)
    }))
    .filter(point => Number.isFinite(point.time))
    .sort((a, b) => a.time - b.time);
  if (points.length < 2) return null;
  if (elapsed <= points[0].time) {
    return {
      fill: points[0].fill,
      velocity: 0,
      hold: Boolean(points[0].hold),
      wave: Boolean(points[0].wave),
      progress: 0
    };
  }
  const last = points[points.length - 1];
  const spanEnd = Number(span?.end);
  const visualLimit = Number.isFinite(spanEnd) && spanEnd > last.time
    ? spanEnd
    : last.time + 0.08;
  let visualCursor = points[0].time;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const next = points[index];
    const fillDelta = Math.abs(next.fill - previous.fill);
    const waveDriven = Boolean(previous.wave || next.wave || span?.profile === "gated-cumulative");
    const holdDriven = Boolean((previous.hold && next.hold) || fillDelta <= 0.018);
    const naturalDuration = Math.max(0.008, next.time - previous.time);
    const minVisualDuration = waveDriven || holdDriven
      ? Math.min(0.018, naturalDuration)
      : clamp(fillDelta * 0.078, 0.035, 0.068);
    const desiredDuration = waveDriven || holdDriven
      ? naturalDuration
      : Math.max(minVisualDuration, next.time - previous.time);
    const visualStart = waveDriven || holdDriven
      ? previous.time
      : Math.max(previous.time, visualCursor);
    if (elapsed < visualStart) {
      return {
        fill: previous.fill,
        velocity: 0,
        hold: Boolean(previous.hold),
        wave: Boolean(previous.wave),
        progress: 0
      };
    }
    const remainingSegments = Math.max(0, points.length - index - 1);
    const reserve = remainingSegments * (waveDriven || holdDriven ? 0.006 : 0.024);
    const latestEnd = Math.max(visualStart + (waveDriven || holdDriven ? 0.008 : 0.024), visualLimit - reserve);
    const segmentDuration = waveDriven || holdDriven
      ? desiredDuration
      : Math.max(0.024, Math.min(desiredDuration, latestEnd - visualStart));
    const segmentEnd = visualStart + segmentDuration;
    if (elapsed > segmentEnd) {
      visualCursor = Math.max(visualCursor, segmentEnd);
      continue;
    }
    const raw = clamp((elapsed - visualStart) / segmentDuration, 0, 1);
    const eased = easeLyricsSegmentValue(raw, previous, next, span);
    const velocity = clamp(fillDelta / Math.max(0.035, segmentDuration) * 0.075, 0, 1);
    return {
      fill: clamp(previous.fill + (next.fill - previous.fill) * eased, 0, 1),
      velocity,
      hold: holdDriven,
      wave: waveDriven,
      progress: raw
    };
  }
  return {
    fill: last.fill,
    velocity: 0,
    hold: Boolean(last.hold),
    wave: Boolean(last.wave),
    progress: 1
  };
}

function lyricsLineText(index) {
  return String(musicLyricsLines[index]?.text || "");
}

function lyricsAnalysisLine(index) {
  if (!musicLyricsAnalysis || musicLyricsAnalysis.path !== musicLyricsTrackPath || !Array.isArray(musicLyricsAnalysis.lines)) return null;
  const direct = musicLyricsAnalysis.lines[index];
  if (direct && Number(direct.index) === index) return direct;
  return musicLyricsAnalysis.lines.find(line => Number(line.index) === index) || null;
}

function manualLyricMarksForLine(index) {
  if (!musicLyricsAnalysis || musicLyricsAnalysis.path !== musicLyricsTrackPath || !Array.isArray(musicLyricsAnalysis.manualMarks)) return [];
  return musicLyricsAnalysis.manualMarks.filter(mark => {
    const time = Number(mark?.time);
    return Number(mark?.lineIndex) === index && Number.isFinite(time) && time >= 0;
  });
}

function musicLyricMarkRole(mark) {
  return String(mark?.role || "").toLowerCase() === "start" ? "start" : "end";
}

function musicLyricMarkStorageKey(mark) {
  return [
    mark?.path || musicLyricsTrackPath || "",
    Number(mark?.lineIndex),
    Number(mark?.boundaryIndex),
    musicLyricMarkRole(mark)
  ].join("\u0000");
}

function musicLyricMarkComparable(mark) {
  return [
    Number(mark?.lineIndex) || 0,
    Number(mark?.boundaryIndex) || 0,
    musicLyricMarkRole(mark) === "start" ? 0 : 1,
    Number(mark?.time) || 0
  ];
}

function sortMusicLyricMarks(marks) {
  return [...marks].sort((left, right) => {
    const a = musicLyricMarkComparable(left);
    const b = musicLyricMarkComparable(right);
    return a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3];
  });
}

function mergePendingMusicLyricMarksIntoAnalysis(analysis) {
  if (!analysis?.path) return analysis;
  const pending = Array.from(sessionMusicLyricMarks.values())
    .filter(mark => mark.path === analysis.path);
  if (!pending.length) return analysis;
  const pendingKeys = new Set(pending.map(musicLyricMarkStorageKey));
  const existing = Array.isArray(analysis.manualMarks) ? analysis.manualMarks : [];
  return {
    ...analysis,
    manualMarks: sortMusicLyricMarks([
      ...existing.filter(mark => !pendingKeys.has(musicLyricMarkStorageKey({ ...mark, path: analysis.path }))),
      ...pending
    ])
  };
}

function stagePendingMusicLyricMark(mark) {
  const clean = {
    ...mark,
    kind: "boundary",
    role: musicLyricMarkRole(mark),
    wordIndex: null,
    createdAt: mark.createdAt || new Date().toISOString()
  };
  sessionMusicLyricMarks.set(musicLyricMarkStorageKey(clean), clean);
  pendingMusicLyricMarks.set(musicLyricMarkStorageKey(clean), clean);
  if (!musicLyricsAnalysis || musicLyricsAnalysis.path !== clean.path) {
    musicLyricsAnalysis = { ok: true, path: clean.path, lines: [], manualMarks: [] };
  }
  musicLyricsAnalysis = mergePendingMusicLyricMarksIntoAnalysis({
    ...musicLyricsAnalysis,
    path: clean.path
  });
}

function sessionLyricMarksForLine(index) {
  return Array.from(sessionMusicLyricMarks.values()).filter(mark => (
    mark.path === musicLyricsTrackPath &&
    Number(mark.lineIndex) === index &&
    Number.isFinite(Number(mark.boundaryIndex))
  ));
}

function removePendingMusicLyricMarksForTarget(path, lineIndex, boundaryIndex, roles = ["start", "end"]) {
  const cleanRoles = (Array.isArray(roles) ? roles : [roles]).map(role => role === "start" ? "start" : "end");
  const removedMarks = new Map();
  let removed = false;
  for (const role of cleanRoles) {
    const key = musicLyricMarkStorageKey({ path, lineIndex, boundaryIndex, role });
    const mark = sessionMusicLyricMarks.get(key) || pendingMusicLyricMarks.get(key);
    if (mark) removedMarks.set(key, mark.createdAt || "");
    removed = sessionMusicLyricMarks.delete(key) || removed;
    removed = pendingMusicLyricMarks.delete(key) || removed;
  }
  if (musicLyricsAnalysis?.path === path && Array.isArray(musicLyricsAnalysis.manualMarks)) {
    musicLyricsAnalysis = {
      ...musicLyricsAnalysis,
      manualMarks: musicLyricsAnalysis.manualMarks.filter(mark => {
        const key = musicLyricMarkStorageKey({ ...mark, path });
        if (!removedMarks.has(key)) return true;
        const removedAt = removedMarks.get(key);
        return removedAt && mark?.createdAt !== removedAt;
      })
    };
  }
  return removed;
}

function flushPendingMusicLyricMarks(options = {}) {
  const marks = Array.from(pendingMusicLyricMarks.values());
  if (!marks.length) return Promise.resolve({ ok: true, count: 0 });
  const payload = { marks };
  if (options.beacon && navigator.sendBeacon) {
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    navigator.sendBeacon("/api/music/lyrics/marks/batch", blob);
    pendingMusicLyricMarks.clear();
    return Promise.resolve({ ok: true, count: marks.length });
  }
  const sent = new Map(marks.map(mark => [musicLyricMarkStorageKey(mark), mark.createdAt]));
  musicLyricMarksFlushPromise = postJson("/api/music/lyrics/marks/batch", payload)
    .then(result => {
      sent.forEach((createdAt, key) => {
        if (pendingMusicLyricMarks.get(key)?.createdAt === createdAt) {
          pendingMusicLyricMarks.delete(key);
        }
      });
      if (result?.marksByPath && musicLyricsAnalysis?.path && Array.isArray(result.marksByPath[musicLyricsAnalysis.path])) {
        musicLyricsAnalysis = {
          ...mergePendingMusicLyricMarksIntoAnalysis(musicLyricsAnalysis),
          manualMarks: result.marksByPath[musicLyricsAnalysis.path]
        };
        musicLyricsAnalysis = mergePendingMusicLyricMarksIntoAnalysis(musicLyricsAnalysis);
        const cachedTrack = selectedTrack()?.path === musicLyricsAnalysis.path ? selectedTrack() : musicLyricsAnalysis.path;
        setMusicLyricsCacheEntry(cachedTrack, { analysis: musicLyricsAnalysis, analysisLoadedAt: Date.now() });
        if (activeLyricsTimingTarget?.path === musicLyricsAnalysis.path && !els.lyricsTimingEditor?.hidden) {
          renderLyricsTimingEditor();
          syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
          updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
        }
      }
      return result;
    })
    .catch(error => {
      if (musicLyricsTrackPath && els.nowPlayingLyricsStatus) {
        musicLyricsStatus = text("lyricsMarkFailed", error.message);
        els.nowPlayingLyricsStatus.textContent = musicLyricsStatus;
        els.nowPlayingLyricsStatus.hidden = false;
      }
      return { ok: false, error: error.message };
    })
    .finally(() => {
      musicLyricMarksFlushPromise = null;
    });
  return musicLyricMarksFlushPromise;
}

function latestManualLyricBoundaryMarksForLine(index, preferredRole = "") {
  const result = new Map();
  for (const mark of manualLyricMarksForLine(index)) {
    const boundaryIndex = Number(mark?.boundaryIndex);
    if (!Number.isFinite(boundaryIndex) || boundaryIndex < 0) continue;
    const role = musicLyricMarkRole(mark);
    const key = boundaryIndex;
    const previous = result.get(key);
    const previousStamp = Date.parse(previous?.createdAt || "") || -1;
    const markStamp = Date.parse(mark?.createdAt || "") || -1;
    const previousRole = musicLyricMarkRole(previous);
    const markPriority = preferredRole && role === preferredRole ? 2 : 1;
    const previousPriority = preferredRole && previousRole === preferredRole ? 2 : 1;
    if (!previous || markPriority > previousPriority || (markPriority === previousPriority && markStamp >= previousStamp)) {
      result.set(key, mark);
    }
  }
  return result;
}

function latestManualLyricBoundaryMark(index, boundaryIndex, role) {
  const cleanBoundary = Math.max(0, Math.round(Number(boundaryIndex) || 0));
  const cleanRole = role === "start" ? "start" : "end";
  let latest = null;
  let latestStamp = -1;
  for (const mark of manualLyricMarksForLine(index)) {
    if (Number(mark?.boundaryIndex) !== cleanBoundary || musicLyricMarkRole(mark) !== cleanRole) continue;
    const time = Number(mark?.time);
    if (!Number.isFinite(time)) continue;
    const stamp = Date.parse(mark?.createdAt || "") || 0;
    if (!latest || stamp >= latestStamp) {
      latest = mark;
      latestStamp = stamp;
    }
  }
  return latest;
}

function exactManualLyricBoundaryTime(index, boundaryIndex, role) {
  const mark = latestManualLyricBoundaryMark(index, boundaryIndex, role);
  const time = Number(mark?.time);
  return Number.isFinite(time) ? time : NaN;
}

function lyricsWordCountForLine(index, analysisLine = lyricsAnalysisLine(index)) {
  const words = lyricsTimingTokens(lyricsLineText(index));
  const spanCount = Array.isArray(analysisLine?.wordSpans) ? analysisLine.wordSpans.length : 0;
  return Math.max(words.length, spanCount, 0);
}

function lyricsAutoBoundaryRelativeTime(boundaryIndex, analysisLine = null, wordCount = 0) {
  const index = Math.max(0, Math.min(Math.round(Number(boundaryIndex) || 0), Math.max(0, wordCount)));
  const wordTimes = Array.isArray(analysisLine?.wordTimes) ? analysisLine.wordTimes.map(Number) : [];
  const hasAnalyzedWordTimes = wordTimes.length >= wordCount + 1;
  if (hasAnalyzedWordTimes && Number.isFinite(wordTimes[index])) return Math.max(0, wordTimes[index]);
  const wordSpans = Array.isArray(analysisLine?.wordSpans) ? analysisLine.wordSpans : [];
  const hasAnalyzedWordSpans = wordSpans.length >= wordCount;
  if (index <= 0) return 0;
  if (index >= wordCount) {
    const duration = Number(analysisLine?.duration);
    if (Number.isFinite(duration)) return Math.max(0, duration);
    const last = hasAnalyzedWordSpans ? wordSpans[wordSpans.length - 1] : null;
    const lastEnd = Number(last?.end ?? last?.fillEnd);
    if (Number.isFinite(lastEnd)) return Math.max(0, lastEnd);
  }
  const nextStart = Number(hasAnalyzedWordSpans ? wordSpans[index]?.start : NaN);
  if (Number.isFinite(nextStart)) return Math.max(0, nextStart);
  const previousEnd = Number(hasAnalyzedWordSpans ? wordSpans[index - 1]?.end ?? wordSpans[index - 1]?.fillEnd : NaN);
  if (Number.isFinite(previousEnd)) return Math.max(0, previousEnd);
  const duration = Number(analysisLine?.duration);
  if (Number.isFinite(duration) && wordCount > 0) return Math.max(0, duration * (index / wordCount));
  return index;
}

function manualLyricBoundaryAnchors(index, analysisLine = lyricsAnalysisLine(index), wordCount = 0, preferredRole = "") {
  const anchors = [];
  latestManualLyricBoundaryMarksForLine(index, preferredRole).forEach(mark => {
    const boundaryIndex = Math.max(0, Math.min(Math.round(Number(mark?.boundaryIndex) || 0), wordCount));
    const time = Number(mark?.time);
    if (!Number.isFinite(time)) return;
    anchors.push({
      index: boundaryIndex,
      time,
      role: musicLyricMarkRole(mark)
    });
  });
  anchors.sort((left, right) => left.index - right.index || left.time - right.time);
  const deduped = [];
  for (const anchor of anchors) {
    if (deduped.length && deduped[deduped.length - 1].index === anchor.index) {
      deduped[deduped.length - 1] = anchor;
    } else {
      deduped.push(anchor);
    }
  }
  return deduped;
}

function manualLyricBoundaryTime(index, boundaryIndex, analysisLine = lyricsAnalysisLine(index), wordCount = 0, lineStart = NaN, preferredRole = "") {
  const anchors = manualLyricBoundaryAnchors(index, analysisLine, wordCount, preferredRole);
  if (!anchors.length) return NaN;
  const cleanBoundary = Math.max(0, Math.min(Math.round(Number(boundaryIndex) || 0), wordCount));
  const exact = anchors.find(anchor => anchor.index === cleanBoundary);
  if (exact) return exact.time;
  if (!Number.isFinite(lineStart)) return NaN;

  const targetAuto = lineStart + lyricsAutoBoundaryRelativeTime(cleanBoundary, analysisLine, wordCount);
  const previous = [...anchors].reverse().find(anchor => anchor.index < cleanBoundary);
  const next = anchors.find(anchor => anchor.index > cleanBoundary);
  if (previous && next) {
    const previousAuto = lineStart + lyricsAutoBoundaryRelativeTime(previous.index, analysisLine, wordCount);
    const nextAuto = lineStart + lyricsAutoBoundaryRelativeTime(next.index, analysisLine, wordCount);
    const autoSpan = nextAuto - previousAuto;
    const indexSpan = Math.max(1, next.index - previous.index);
    const ratio = autoSpan > 0.001
      ? clamp((targetAuto - previousAuto) / autoSpan, 0, 1)
      : clamp((cleanBoundary - previous.index) / indexSpan, 0, 1);
    return previous.time + (next.time - previous.time) * ratio;
  }
  if (previous) {
    const previousAuto = lineStart + lyricsAutoBoundaryRelativeTime(previous.index, analysisLine, wordCount);
    return previous.time + (targetAuto - previousAuto);
  }
  if (next) {
    const nextAuto = lineStart + lyricsAutoBoundaryRelativeTime(next.index, analysisLine, wordCount);
    return next.time - (nextAuto - targetAuto);
  }
  return NaN;
}

function manualLyricWordTiming(index, wordIndex, analysisLine = lyricsAnalysisLine(index), wordCount = 0, lineStart = NaN) {
  const start = exactManualLyricBoundaryTime(index, wordIndex, "start");
  if (!Number.isFinite(start)) return null;
  let end = exactManualLyricBoundaryTime(index, wordIndex + 1, "end");
  if (!Number.isFinite(end)) return null;
  if (end <= start) end = start + 0.08;
  return { start, end };
}

function manualLyricLineStartTime(index) {
  return exactManualLyricBoundaryTime(index, 0, "start");
}

function manualLyricLineEndTime(index) {
  const analysisLine = lyricsAnalysisLine(index);
  const wordCount = lyricsWordCountForLine(index, analysisLine);
  if (!wordCount) return NaN;
  return exactManualLyricBoundaryTime(index, wordCount, "end");
}

function toggleSessionLyricBoundaryClass(wordNodes, boundaryIndex, role = "end", enabled = true) {
  if (!wordNodes.length) return;
  const index = Math.max(0, Math.min(wordNodes.length, Math.round(Number(boundaryIndex) || 0)));
  const target = index <= 0 ? wordNodes[0] : wordNodes[index - 1];
  const suffix = index <= 0 ? "before" : "after";
  const cleanRole = role === "start" ? "start" : "end";
  target.classList.toggle(`session-lyric-boundary-${cleanRole}-${suffix}`, Boolean(enabled));
}

function syncManualLyricMarkClasses(node, index) {
  if (!node) return;
  const marks = manualLyricMarksForLine(index);
  node.classList.toggle("has-manual-mark", Boolean(marks.length));
  const sessionMarks = sessionLyricMarksForLine(index);
  const words = Array.from(node.querySelectorAll(".lyric-word"));
  words.forEach(word => {
    word.classList.remove(
      "session-lyric-boundary-before",
      "session-lyric-boundary-after",
      "session-lyric-boundary-start-before",
      "session-lyric-boundary-start-after",
      "session-lyric-boundary-end-before",
      "session-lyric-boundary-end-after"
    );
  });
}

function lyricsLineAnalysisStartTime(index) {
  const start = Number(musicLyricsLines[index]?.time);
  if (!Number.isFinite(start)) return start;
  const analysisLine = lyricsAnalysisLine(index);
  const analysisTime = Number(analysisLine?.analysisTime);
  if (Number.isFinite(analysisTime)) return analysisTime;
  const offset = Number(analysisLine?.startOffset);
  if (Number.isFinite(offset)) return start + clamp(offset, -0.1, 0.16);
  return start;
}

function lyricsLineWordStartTime(index) {
  const manualStart = manualLyricLineStartTime(index);
  if (Number.isFinite(manualStart)) return manualStart;
  const rawStart = Number(musicLyricsLines[index]?.time);
  const analysisStart = lyricsLineAnalysisStartTime(index);
  if (!Number.isFinite(rawStart)) return analysisStart;
  if (!Number.isFinite(analysisStart)) return rawStart;

  const analysisDelay = analysisStart - rawStart;
  if (analysisDelay > 0) {
    return rawStart + Math.min(0.075, analysisDelay * 0.34);
  }
  return analysisStart;
}

function lyricsLineWordStats(index) {
  const textLine = lyricsLineText(index);
  const words = lyricsTimingTokens(textLine);
  const characters = textLine.replace(/\s+/g, "").length;
  return {
    words: Math.max(1, words.length),
    characters: Math.max(1, characters)
  };
}

function lyricsWordEstimateWeight(token) {
  const raw = String(token || "");
  const clean = raw.replace(/[^A-Za-z0-9']/g, "").toLowerCase();
  const letters = clean.replace(/[^A-Za-z]/g, "");
  const syllables = lyricsEstimatedSyllableCount(clean);
  const consonants = (letters.match(/[bcdfghjklmnpqrstvwxz]/g) || []).length;
  const longTail = Math.max(0, letters.length - 6);
  let weight = 0.14 + syllables * 0.26 + Math.min(letters.length, 8) * 0.026 + consonants * 0.012;
  if (clean.includes("'")) {
    weight += 0.04;
  }
  if (/(ing|tion|sion|ly|ness|ment)$/.test(clean)) {
    weight += 0.08;
  }
  if (longTail > 0) {
    weight += Math.min(0.16, longTail * 0.018);
  }
  if (lyricsLightWord(clean)) {
    weight *= 0.62;
  } else if (["you", "your", "me", "my", "our", "us", "he", "she", "they", "that", "this", "with", "for"].includes(clean)) {
    weight *= 0.78;
  }
  if (/[,;:!?)]$/.test(raw)) {
    weight += 0.16;
  }
  return Math.max(0.12, weight);
}

function lyricsLightWord(clean) {
  return ["the", "a", "an", "of", "to", "we", "are", "is", "it", "i", "im", "i'm", "up", "and", "or", "in", "on", "at"].includes(clean);
}

function lyricsEstimatedSyllableCount(token) {
  const clean = String(token || "").replace(/[^A-Za-z]/g, "").toLowerCase();
  if (!clean) return 1;
  let groups = clean.match(/[aeiouy]+/g)?.length || 1;
  if (clean.endsWith("e") && groups > 1 && !clean.endsWith("le") && !clean.endsWith("ye")) {
    groups -= 1;
  }
  return clamp(groups, 1, 4);
}

function lyricsEstimatedTextFillDuration(index, gap = NaN) {
  const textLine = lyricsLineText(index);
  const words = lyricsTimingTokens(textLine);
  const characters = textLine.replace(/\s+/g, "").length;
  const weighted = words.reduce((total, word) => total + lyricsWordEstimateWeight(word), 0) || Math.max(1, words.length) * 0.35;
  const quickEstimate = 0.18 + weighted * 0.58 + characters * 0.006;
  const longEstimate = 0.24 + words.length * 0.26 + characters * 0.014;
  let estimate = quickEstimate;
  if (Number.isFinite(gap) && gap >= 5 && words.length >= 8) {
    estimate = longEstimate * 0.72 + quickEstimate * 0.28;
  } else if (Number.isFinite(gap) && gap >= 3) {
    estimate = quickEstimate * 0.78 + longEstimate * 0.22;
  }
  if (/[.!?]$/.test(textLine.trim())) {
    estimate += 0.1;
  }
  return estimate;
}

function lyricsNextLineTime(index) {
  for (let nextIndex = index + 1; nextIndex < musicLyricsLines.length; nextIndex += 1) {
    const nextTime = Number(musicLyricsLines[nextIndex]?.time);
    if (Number.isFinite(nextTime)) return nextTime;
  }
  return NaN;
}

function lyricsEstimatedWordFillDuration(index) {
  const analysisLine = lyricsAnalysisLine(index);
  const analyzedDuration = Number(analysisLine?.duration);
  if (Number.isFinite(analyzedDuration) && analyzedDuration > 0) {
    return clamp(analyzedDuration, lyricsMinWordFillSeconds, 8);
  }

  const start = Number(musicLyricsLines[index]?.time);
  if (!Number.isFinite(start)) return 2.2;
  const nextTime = lyricsNextLineTime(index);
  const gap = Number.isFinite(nextTime) ? Math.max(0.2, nextTime - start) : NaN;
  const textEstimate = lyricsEstimatedTextFillDuration(index, gap);
  if (!Number.isFinite(gap)) return clamp(textEstimate, lyricsMinWordFillSeconds, 3.8);

  const holdBeforeNext = gap >= 4 ? 1 : gap >= 3 ? 0.72 : 0.24;
  const gapCap = Math.max(lyricsMinWordFillSeconds, gap - holdBeforeNext);
  const ratioCap = Math.max(lyricsMinWordFillSeconds, gap * (gap >= 4 ? 0.56 : gap >= 3 ? 0.66 : 0.86));
  return clamp(Math.min(textEstimate, gapCap, ratioCap), lyricsMinWordFillSeconds, Math.max(lyricsMinWordFillSeconds, gapCap));
}

function lyricsWordFillStartTime(index) {
  const start = lyricsLineWordStartTime(index);
  if (!Number.isFinite(start)) return start;
  return start - lyricsWordFillLeadSeconds;
}

function lyricsLineEndTime(index) {
  const start = lyricsWordFillStartTime(index);
  if (!Number.isFinite(start)) return start;
  const autoEnd = start + lyricsEstimatedWordFillDuration(index);
  const manualEnd = manualLyricLineEndTime(index);
  return Number.isFinite(manualEnd) ? Math.max(autoEnd, manualEnd) : autoEnd;
}

function lyricsLineOutroProgress(index, time = 0) {
  const nextStart = lyricsLineDisplayStartTime(index + 1);
  if (!Number.isFinite(nextStart)) return 0;
  return easeLyricsValue((time - (nextStart - lyricsWordFillOutroSeconds)) / lyricsWordFillOutroSeconds);
}

function lyricsLinePostVocalProgress(index, time = 0) {
  const lineEnd = lyricsLineEndTime(index);
  if (!Number.isFinite(lineEnd)) return 0;
  const nextStart = lyricsLineDisplayStartTime(index + 1);
  const visualEnd = Number.isFinite(nextStart) ? nextStart : lyricsLineVisualHoldEndTime(index);
  if (!Number.isFinite(visualEnd) || visualEnd <= lineEnd) return 0;
  const gap = visualEnd - lineEnd;
  if (gap <= 0.58) return 0;
  const hold = Math.min(lyricsLineRestHoldSeconds, Math.max(0.16, gap * 0.28));
  const fade = clamp(gap * 0.34, lyricsLineRestFadeMinSeconds, lyricsLineRestFadeMaxSeconds);
  return easeLyricsValue((time - lineEnd - hold) / fade);
}

function lyricsLineVisualHoldEndTime(index) {
  const nextStart = lyricsLineDisplayStartTime(index + 1);
  if (Number.isFinite(nextStart)) return nextStart;
  const duration = audioDuration();
  const start = Number(musicLyricsLines[index]?.time);
  if (Number.isFinite(start) && duration > start + 0.5) return duration;
  return lyricsLineEndTime(index) + 0.4;
}

function lyricsLineProgress(index, time) {
  const start = lyricsWordFillStartTime(index);
  const end = lyricsLineEndTime(index);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return 0;
  const raw = clamp((time - start) / (end - start), 0, 1);
  return easeLyricsValue(raw);
}

function updateActiveLyricsWordProgress() {
  const list = els.nowPlayingLyricsList;
  const active = list?.querySelector(".music-lyrics-line.active");
  if (!list || !active || !musicLyricsSynced || musicLyricsActiveIndex < 0) return;
  list.querySelectorAll(".music-lyrics-line:not(.active)").forEach(node => resetLyricsWordProgress(node, 0));
  active.style.setProperty("--line-progress", "1");
  active.style.setProperty("--line-end-soft", "0");
  active.style.setProperty("--line-rest-progress", "0");
  active.style.setProperty("--line-rest-glow", "28%");
  active.classList.remove("ending", "line-resting");
  active.querySelectorAll(".lyric-word").forEach(word => {
    word.style.setProperty("--word-fill", "1");
    word.style.setProperty("--word-strength", "0.72");
    word.style.setProperty("--word-transition", "120ms");
    word.style.removeProperty("--word-current-brightness");
    word.style.removeProperty("--word-current-saturation");
    word.style.removeProperty("--word-valley");
    word.style.removeProperty("--word-motion");
    word.style.removeProperty("--word-break-strength");
    word.style.removeProperty("--word-phrase-rest");
    word.style.removeProperty("--word-valley-shadow");
    word.classList.add("word-sung");
    word.classList.remove("word-current", "word-hold", "word-wave-current", "word-phrase-rest", "word-strong", "word-valley-break", "word-group-break");
  });
}

function resetLyricsWordProgress(node, value = 0) {
  if (!node) return;
  node.style.removeProperty("--line-progress");
  node.style.removeProperty("--line-end-soft");
  node.style.removeProperty("--line-rest-progress");
  node.style.removeProperty("--line-rest-glow");
  node.classList.remove("ending", "line-resting");
  node.querySelectorAll(".lyric-word").forEach(word => {
    word.style.setProperty("--word-fill", String(value));
    word.style.removeProperty("--word-strength");
    word.style.removeProperty("--word-current-brightness");
    word.style.removeProperty("--word-current-saturation");
    word.style.removeProperty("--word-valley");
    word.style.removeProperty("--word-motion");
    word.style.removeProperty("--word-break-strength");
    word.style.removeProperty("--word-phrase-rest");
    word.style.removeProperty("--word-valley-shadow");
    word.style.removeProperty("--word-transition");
    word.classList.toggle("word-sung", value >= 1);
    word.classList.remove("word-current");
    word.classList.remove("word-hold", "word-wave-current", "word-phrase-rest", "word-strong", "word-valley-break", "word-group-break");
  });
}

function lyricsColorMix(fromToken, fromPercent, toToken) {
  return `color-mix(in srgb, var(${fromToken}) ${Math.round(clamp(fromPercent, 0, 1) * 100)}%, var(${toToken}))`;
}

function setLyricsLineTone(node, tone = {}) {
  if (!node) return;
  if (tone.color) node.style.setProperty("--line-color", tone.color);
  if (Number.isFinite(tone.opacity)) node.style.setProperty("--line-opacity", tone.opacity.toFixed(3));
  if (Number.isFinite(tone.brightness)) node.style.setProperty("--line-brightness", tone.brightness.toFixed(3));
  if (Number.isFinite(tone.saturation)) node.style.setProperty("--line-saturation", tone.saturation.toFixed(3));
  if (Number.isFinite(tone.lift)) node.style.setProperty("--line-lift", `${tone.lift.toFixed(2)}px`);
}

function clearLyricsLineTone(node) {
  if (!node) return;
  node.style.removeProperty("--line-color");
  node.style.removeProperty("--line-opacity");
  node.style.removeProperty("--line-brightness");
  node.style.removeProperty("--line-saturation");
  node.style.removeProperty("--line-lift");
}

function updateLyricsLineTone(time = 0) {
  const list = els.nowPlayingLyricsList;
  if (!list) return;
  const lines = list.querySelectorAll(".music-lyrics-line");
  if (!musicLyricsSynced || !musicLyricsLines.length) {
    lines.forEach(clearLyricsLineTone);
    return;
  }
  lines.forEach(node => {
    const index = Number(node.dataset.lyricsIndex);
    const line = musicLyricsLines[index];
    if (!Number.isFinite(index) || !line) {
      clearLyricsLineTone(node);
      return;
    }

    if (musicLyricsActiveIndex < 0) {
      setLyricsLineTone(node, {
        color: "var(--lyrics-upcoming-dim)",
        opacity: 0.54,
        brightness: 0.88,
        saturation: 0.84,
        lift: 0
      });
      return;
    }

    const distance = index - musicLyricsActiveIndex;
    if (distance === 0) {
      setLyricsLineTone(node, {
        color: "var(--lyrics-active-text)",
        opacity: 1,
        brightness: 1.1,
        saturation: 1.12,
        lift: 0
      });
      return;
    }

    setLyricsLineTone(node, {
      color: "var(--lyrics-upcoming-dim)",
      opacity: 0.54,
      brightness: 0.88,
      saturation: 0.84,
      lift: 0
    });
  });
}

function setLyricsLineVisualState(node, index, activeIndex = musicLyricsActiveIndex) {
  if (!node) return;
  node.className = "music-lyrics-line";
  const line = musicLyricsLines[index];
  const canSeek = Boolean(musicLyricsSynced && line && Number.isFinite(line.time));
  node.classList.toggle("can-seek", canSeek);
  syncManualLyricMarkClasses(node, index);
  resetLyricsWordProgress(node, 0);
  if (!musicLyricsSynced) return;

  if (activeIndex < 0) {
    node.classList.add("upcoming");
    node.classList.add(index > 2 ? "distant" : "nearby");
    return;
  }

  const distance = index - activeIndex;
  if (distance === 0) {
    node.classList.add("active");
    return;
  }
  node.classList.add(distance < 0 ? "past" : "upcoming");
  if (distance < 0) resetLyricsWordProgress(node, 0);
  if (Math.abs(distance) === 1) node.classList.add("nearby");
  else if (Math.abs(distance) > 3) node.classList.add("distant");
}

function syncLyricsLineVisualStates(activeIndex = musicLyricsActiveIndex, options = {}) {
  const list = els.nowPlayingLyricsList;
  const panel = els.nowPlayingLyricsPanel;
  if (!list || !panel) return;
  panel.classList.toggle("is-synced", musicLyricsSynced);
  panel.classList.toggle("is-plain", !musicLyricsSynced && Boolean(musicLyricsLines.length));
  panel.classList.toggle("has-active-line", activeIndex >= 0);
  list.querySelectorAll(".music-lyrics-line").forEach(node => {
    setLyricsLineVisualState(node, Number(node.dataset.lyricsIndex), activeIndex);
  });
  if (options.scroll && activeIndex >= 0) {
    const active = list.querySelector(`[data-lyrics-index="${activeIndex}"]`);
    active?.scrollIntoView({ block: "center", behavior: options.instant ? "auto" : "smooth" });
  }
  const currentTime = Number.isFinite(els.audioPlayer?.currentTime) ? els.audioPlayer.currentTime : 0;
  updateActiveLyricsWordProgress(currentTime);
  updateLyricsLineTone(currentTime);
  syncLyricsTimingSelection();
  syncLyricsAnimationLoop();
}

function lyricsAnimationShouldRun() {
  return Boolean(
    hasMusic &&
    isModuleForeground("music") &&
    musicLyricsSynced &&
    musicLyricsLines.length &&
    musicLyricsTrackPath &&
    musicLyricsTrackPath === selectedTrackPath &&
    els.nowPlayingLyricsPanel &&
    !els.nowPlayingLyricsPanel.hidden &&
    els.audioPlayer &&
    !els.audioPlayer.paused &&
    !els.audioPlayer.ended
  );
}

function stopLyricsAnimationLoop() {
  if (!musicLyricsAnimationFrame) return;
  window.cancelAnimationFrame(musicLyricsAnimationFrame);
  musicLyricsAnimationFrame = 0;
}

function syncLyricsAnimationLoop() {
  if (!lyricsAnimationShouldRun()) {
    stopLyricsAnimationLoop();
    return;
  }
  if (musicLyricsAnimationFrame) return;
  const tick = () => {
    musicLyricsAnimationFrame = 0;
    const current = Number.isFinite(els.audioPlayer.currentTime) ? els.audioPlayer.currentTime : 0;
    updateLyricsProgress(current);
    if (lyricsAnimationShouldRun()) {
      musicLyricsAnimationFrame = window.requestAnimationFrame(tick);
    }
  };
  musicLyricsAnimationFrame = window.requestAnimationFrame(tick);
}

function applyAudioCurrentTime(nextTime) {
  try {
    if (typeof els.audioPlayer.fastSeek === "function") {
      els.audioPlayer.fastSeek(nextTime);
    } else {
      els.audioPlayer.currentTime = nextTime;
    }
  } catch {
    try {
      els.audioPlayer.currentTime = nextTime;
    } catch {
      return false;
    }
  }
  return true;
}

function seekToLyricsLine(index) {
  const line = musicLyricsLines[index];
  if (!musicLyricsSynced || !line || !Number.isFinite(line.time)) return;
  const item = selectedTrack();
  if (!item?.url || !item?.path) return;
  const targetUrl = new URL(item.url, window.location.href).href;
  if (selectedTrackPath !== item.path) {
    setSelectedTrackPath(item.path, { persist: "now" });
  }
  if (els.audioPlayer.src !== targetUrl) {
    els.audioPlayer.src = item.url;
    els.audioPlayer.load();
  }

  const beforeRatio = currentAudioSeekRatio();
  let didSeek = false;
  const applySeek = () => {
    if (didSeek) return;
    const duration = audioDuration();
    if (duration <= 0) return;
    didSeek = true;
    const displayStart = lyricsLineDisplayStartTime(index);
    const targetStart = Number.isFinite(displayStart) ? displayStart : line.time;
    const targetTime = clamp(targetStart, 0, Math.max(0, duration - 0.05));
    if (!applyAudioCurrentTime(targetTime)) return;
    pendingSeekRatio = null;
    const targetRatio = clamp(targetTime / duration, 0, 1);
    els.trackSeek.value = String(targetRatio * 100);
    els.trackCurrentTime.textContent = formatDuration(targetTime);
    els.trackDuration.textContent = formatDuration(duration);
    musicLyricsActiveIndex = index;
    heldLyricsActiveIndex = index;
    heldLyricsActiveUntil = performance.now() + 760;
    syncLyricsLineVisualStates(index, { scroll: true });
    updateActiveLyricsWordProgress(targetTime);
    recordTrackSeekChange(beforeRatio, targetRatio);
    updateTrackProgress();
  };

  if (audioDuration() > 0) {
    applySeek();
    return;
  }
  els.audioPlayer.addEventListener("loadedmetadata", applySeek, { once: true });
  els.audioPlayer.addEventListener("canplay", applySeek, { once: true });
}

function lyricsWordIndexAtTime(index, time = 0) {
  const node = Array.from(els.nowPlayingLyricsList?.querySelectorAll(".music-lyrics-line") || [])
    .find(item => Number(item.dataset.lyricsIndex) === index);
  const wordNodes = Array.from(node?.querySelectorAll(".lyric-word") || []);
  const wordCount = wordNodes.length;
  if (!wordCount || !Number.isFinite(time)) return null;
  const analysisLine = lyricsAnalysisLine(index);
  const elapsed = time - lyricsWordFillStartTime(index);
  const wordSpans = Array.isArray(analysisLine?.wordSpans) ? analysisLine.wordSpans : [];
  if (Number.isFinite(elapsed) && wordSpans.length >= wordCount) {
    let nearest = 0;
    for (let wordIndex = 0; wordIndex < wordCount; wordIndex += 1) {
      const start = Number(wordSpans[wordIndex]?.start);
      const end = Number(wordSpans[wordIndex]?.fillEnd ?? wordSpans[wordIndex]?.end);
      if (!Number.isFinite(start)) continue;
      if (elapsed >= start) nearest = wordIndex;
      if (Number.isFinite(end) && elapsed >= start && elapsed <= end) return wordIndex;
      if (elapsed < start) break;
    }
    return clamp(nearest, 0, wordCount - 1);
  }
  const progress = lyricsLineProgress(index, time);
  if (!Number.isFinite(progress)) return null;
  return clamp(Math.ceil(progress * wordCount) - 1, 0, wordCount - 1);
}

function primaryLyricWordRect(word) {
  const rects = Array.from(word?.getClientRects?.() || []).filter(rect => rect.width > 0 && rect.height > 0);
  return rects[0] || word?.getBoundingClientRect?.() || null;
}

function closestLyricsBoundaryTarget(lineNode, clientX, clientY) {
  const words = Array.from(lineNode?.querySelectorAll?.(".lyric-word") || []);
  const wordRects = words
    .map((word, index) => ({ word, index, rect: primaryLyricWordRect(word) }))
    .filter(item => item.rect);
  if (!wordRects.length) return null;

  const candidates = [];
  const addCandidate = (boundaryIndex, x, y) => {
    const previousWord = boundaryIndex > 0 ? words[boundaryIndex - 1] : null;
    const nextWord = boundaryIndex < words.length ? words[boundaryIndex] : null;
    const dx = clientX - x;
    const dy = clientY - y;
    candidates.push({
      boundaryIndex,
      x,
      y,
      score: dx * dx + dy * dy * 0.72,
      previousWord,
      nextWord
    });
  };

  const first = wordRects[0];
  addCandidate(0, first.rect.left, first.rect.top + first.rect.height / 2);
  for (let index = 1; index < wordRects.length; index += 1) {
    const previous = wordRects[index - 1];
    const next = wordRects[index];
    const previousCenterY = previous.rect.top + previous.rect.height / 2;
    const nextCenterY = next.rect.top + next.rect.height / 2;
    const sameVisualRow = Math.abs(previousCenterY - nextCenterY) <= Math.max(previous.rect.height, next.rect.height) * 0.74;
    if (sameVisualRow) {
      addCandidate(index, (previous.rect.right + next.rect.left) / 2, (previousCenterY + nextCenterY) / 2);
    } else {
      addCandidate(index, previous.rect.right, previousCenterY);
      addCandidate(index, next.rect.left, nextCenterY);
    }
  }
  const last = wordRects[wordRects.length - 1];
  addCandidate(words.length, last.rect.right, last.rect.top + last.rect.height / 2);

  const best = candidates.sort((left, right) => left.score - right.score)[0];
  if (!best) return null;
  return {
    boundaryIndex: best.boundaryIndex,
    wordCount: words.length,
    previousWord: best.previousWord?.textContent || "",
    nextWord: best.nextWord?.textContent || "",
    markerWord: best.boundaryIndex <= 0 ? words[0] : words[best.boundaryIndex - 1],
  };
}

function formatLyricsEditorTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const totalMillis = Math.round(seconds * 1000);
  const minutes = Math.floor(totalMillis / 60000);
  const wholeSeconds = Math.floor((totalMillis % 60000) / 1000);
  const millis = totalMillis % 1000;
  return `${minutes}:${String(wholeSeconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function parseLyricsEditorTime(value) {
  let raw = String(value || "").trim();
  if (!raw) return NaN;
  raw = raw
    .replace(/[：]/g, ":")
    .replace(/\s+/g, "")
    .replace(/[\uff1a]/g, ":")
    .replace(/\u5206/gi, ":")
    .replace(/\u79d2/gi, "")
    .replace(/分/gi, ":")
    .replace(/秒/gi, "")
    .replace(/m/gi, ":")
    .replace(/s/gi, "");
  if (/^\d+(?:\.\d+)?$/.test(raw)) return Number(raw);
  const parts = raw.split(":");
  if (parts.length < 2 || parts.some(part => part === "")) return NaN;
  const seconds = Number(parts.pop());
  if (!Number.isFinite(seconds)) return NaN;
  let units = 0;
  for (const part of parts) {
    const valuePart = Number(part);
    if (!Number.isFinite(valuePart)) return NaN;
    units = units * 60 + valuePart;
  }
  return units * 60 + seconds;
}

function lyricsBoundaryReferenceTime(lineIndex, boundaryIndex, role) {
  const exact = latestManualLyricBoundaryMark(lineIndex, boundaryIndex, role);
  const exactTime = Number(exact?.time);
  if (Number.isFinite(exactTime)) return exactTime;
  const analysisLine = lyricsAnalysisLine(lineIndex);
  const wordCount = lyricsWordCountForLine(lineIndex, analysisLine);
  const lineStart = lyricsWordFillStartTime(lineIndex);
  if (Number.isFinite(lineStart)) {
    return lineStart + lyricsAutoBoundaryRelativeTime(boundaryIndex, analysisLine, wordCount);
  }
  const rawStart = Number(musicLyricsLines[lineIndex]?.time);
  if (Number.isFinite(rawStart)) {
    return rawStart + lyricsAutoBoundaryRelativeTime(boundaryIndex, analysisLine, wordCount);
  }
  return NaN;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}

function refreshLyricsTimingEditorRefs() {
  const root = els.lyricsTimingEditor;
  if (!root) return;
  els.lyricsTimingTarget = root.querySelector("#lyricsTimingTarget");
  els.lyricsTimingStartInput = root.querySelector("#lyricsTimingStartInput");
  els.lyricsTimingEndInput = root.querySelector("#lyricsTimingEndInput");
  els.lyricsTimingUseNowStart = root.querySelector("[data-lyrics-action='use-now-start']");
  els.lyricsTimingUseNowEnd = root.querySelector("[data-lyrics-action='use-now-end']");
  els.lyricsTimingSave = root.querySelector("[data-lyrics-action='save-selected']");
  els.lyricsTimingClear = root.querySelector("[data-lyrics-action='clear-selected']");
  els.lyricsTimingClose = root.querySelector("[data-lyrics-action='close']");
}

function bindLyricsTimingEditorEvents(root = els.lyricsTimingEditor) {
  if (!hasMusic || !root || root.dataset.lyricsTimingBound === "true") return;
  root.addEventListener("click", handleLyricsTimingEditorClick);
  root.addEventListener("contextmenu", handleLyricsTimingEditorContextMenu);
  root.addEventListener("dblclick", handleLyricsTimingEditorDoubleClick);
  root.addEventListener("input", handleLyricsTimingEditorInput);
  root.addEventListener("keydown", handleLyricsTimingEditorKeydown);
  root.addEventListener("focusout", handleLyricsTimingEditorFocusOut);
  root.addEventListener("pointerdown", handleLyricsTimingWavePointerDown);
  root.addEventListener("pointermove", handleLyricsTimingWavePointerMove);
  root.addEventListener("pointerup", finishLyricsTimingWaveDrag);
  root.addEventListener("pointercancel", finishLyricsTimingWaveDrag);
  root.dataset.lyricsTimingBound = "true";
}

function ensureLyricsTimingEditorRoot() {
  let root = els.lyricsTimingEditor || document.getElementById("lyricsTimingEditor");
  if (!root || !root.isConnected) {
    root = document.createElement("div");
    root.id = "lyricsTimingEditor";
    root.className = "lyrics-timing-editor";
    root.hidden = true;
  }
  els.lyricsTimingEditor = root;
  root.classList.add("lyrics-timing-editor");
  if (els.nowPlayingLyricsPanel?.parentElement) {
    els.nowPlayingLyricsPanel.insertAdjacentElement("afterend", root);
  } else {
    els.nowPlayingLyricsPanel?.appendChild(root);
  }
  bindLyricsTimingEditorEvents(root);
  refreshLyricsTimingEditorRefs();
  return root;
}

function detachLyricsTimingEditorFromList() {
  ensureLyricsTimingEditorRoot();
}

function mountLyricsTimingEditorForLine(lineIndex) {
  const root = ensureLyricsTimingEditorRoot();
  if (!root) return;
  root.hidden = false;
  window.requestAnimationFrame(() => {
    root.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
}

function lyricsLineTimingTargets(lineIndex) {
  const words = lyricsTimingTokens(lyricsLineText(lineIndex));
  const wordCount = words.length;
  return words.map((wordText, wordIndex) => ({
    path: musicLyricsTrackPath,
    lineIndex,
    wordIndex,
    wordCount,
    wordText,
    previousWord: words[wordIndex - 1] || "",
    nextWord: words[wordIndex + 1] || "",
    startBoundaryIndex: wordIndex,
    endBoundaryIndex: wordIndex + 1,
    lineText: lyricsLineText(lineIndex)
  }));
}

function lyricsTimingTargetForLineWord(lineIndex, wordIndex) {
  const targets = lyricsLineTimingTargets(lineIndex);
  if (!targets.length) return null;
  const cleanIndex = clamp(Math.round(Number(wordIndex) || 0), 0, targets.length - 1);
  return targets[cleanIndex] || null;
}

function lyricsTimingInputState(target, role) {
  const boundaryIndex = role === "start" ? target.startBoundaryIndex : target.endBoundaryIndex;
  const exact = exactManualLyricBoundaryTime(target.lineIndex, boundaryIndex, role);
  const reference = lyricsBoundaryReferenceTime(target.lineIndex, boundaryIndex, role);
  return {
    manual: Number.isFinite(exact),
    value: Number.isFinite(exact) ? formatLyricsEditorTime(exact) : "",
    placeholder: Number.isFinite(reference) ? formatLyricsEditorTime(reference) : ""
  };
}

function lyricsTimingTargetHasManual(target) {
  return lyricsTimingInputState(target, "start").manual || lyricsTimingInputState(target, "end").manual;
}

function normalizeLyricsTimingRange(target = activeLyricsTimingTarget) {
  const wordCount = Math.max(1, Number(target?.wordCount) || 1);
  if (!Number.isFinite(activeLyricsTimingRangeStart) || !Number.isFinite(activeLyricsTimingRangeEnd)) {
    activeLyricsTimingRangeStart = Number(target?.wordIndex) || 0;
    activeLyricsTimingRangeEnd = activeLyricsTimingRangeStart;
  }
  activeLyricsTimingRangeStart = clamp(Math.round(activeLyricsTimingRangeStart), 0, wordCount - 1);
  activeLyricsTimingRangeEnd = clamp(Math.round(activeLyricsTimingRangeEnd), 0, wordCount - 1);
  if (activeLyricsTimingRangeEnd < activeLyricsTimingRangeStart) {
    [activeLyricsTimingRangeStart, activeLyricsTimingRangeEnd] = [activeLyricsTimingRangeEnd, activeLyricsTimingRangeStart];
  }
}

function lyricsTimingWordInRange(wordIndex) {
  return Number(wordIndex) >= activeLyricsTimingRangeStart && Number(wordIndex) <= activeLyricsTimingRangeEnd;
}

function lyricsTimingSelectedTargets() {
  const target = activeLyricsTimingTarget;
  if (!target) return [];
  normalizeLyricsTimingRange(target);
  return lyricsLineTimingTargets(target.lineIndex).filter(item => lyricsTimingWordInRange(item.wordIndex));
}

function lyricsTimingRangeBoundary(role) {
  normalizeLyricsTimingRange(activeLyricsTimingTarget);
  return role === "start" ? activeLyricsTimingRangeStart : activeLyricsTimingRangeEnd + 1;
}

function lyricsTimingRangeSegmentTime(role) {
  const target = activeLyricsTimingTarget;
  if (!target) return NaN;
  normalizeLyricsTimingRange(target);
  const segments = lyricsTimingWordSegments(target.lineIndex);
  const segment = role === "start"
    ? segments[activeLyricsTimingRangeStart]
    : segments[activeLyricsTimingRangeEnd];
  const time = role === "start" ? Number(segment?.start) : Number(segment?.end);
  return Number.isFinite(time) ? time : NaN;
}

function lyricsTimingRangeInputState(role) {
  const target = activeLyricsTimingTarget;
  if (!target) return { manual: false, value: "", placeholder: "", time: NaN };
  const boundaryIndex = lyricsTimingRangeBoundary(role);
  const exact = exactManualLyricBoundaryTime(target.lineIndex, boundaryIndex, role);
  const segmentTime = lyricsTimingRangeSegmentTime(role);
  const reference = Number.isFinite(segmentTime)
    ? segmentTime
    : lyricsBoundaryReferenceTime(target.lineIndex, boundaryIndex, role);
  const time = Number.isFinite(segmentTime) ? segmentTime : Number.isFinite(exact) ? exact : reference;
  return {
    manual: Number.isFinite(exact),
    value: Number.isFinite(exact) ? formatLyricsEditorTime(exact) : "",
    placeholder: Number.isFinite(reference) ? formatLyricsEditorTime(reference) : "",
    time
  };
}

function lyricsTimingDurationTextFromValues(startValue, endValue) {
  const start = parseLyricsEditorTime(startValue);
  const end = parseLyricsEditorTime(endValue);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return "";
  return formatLyricsEditorTime(end - start);
}

function lyricsTimingDurationText(target) {
  const start = lyricsTimingInputState(target, "start").value;
  const end = lyricsTimingInputState(target, "end").value;
  return lyricsTimingDurationTextFromValues(start, end);
}

function lyricsTimingInputHtml(target, role, className) {
  const state = lyricsTimingInputState(target, role);
  return `<input class="${className}" type="text" inputmode="decimal" autocomplete="off" data-role="${role}" data-word-index="${target.wordIndex}" value="${escapeHtml(state.value)}" placeholder="${escapeHtml(state.placeholder)}">`;
}

function lyricsTimingRangeInputHtml(role, className, id = "") {
  const state = lyricsTimingRangeInputState(role);
  const idPart = id ? ` id="${id}"` : "";
  return `<input${idPart} class="${className}" type="text" inputmode="decimal" autocomplete="off" data-role="${role}" value="${escapeHtml(state.value)}" placeholder="${escapeHtml(state.placeholder)}">`;
}

function lyricsWaveformWindow(lineIndex) {
  const analysisLine = lyricsAnalysisLine(lineIndex);
  const waveform = analysisLine?.waveform && typeof analysisLine.waveform === "object" ? analysisLine.waveform : null;
  const samples = Array.isArray(waveform?.samples) ? waveform.samples.map(Number).filter(Number.isFinite) : [];
  const lineStart = Number(waveform?.start);
  const lineEnd = Number(waveform?.end);
  if (samples.length && Number.isFinite(lineStart) && Number.isFinite(lineEnd) && lineEnd > lineStart) {
    return { start: lineStart, end: lineEnd, samples };
  }
  const start = Number(musicLyricsLines[lineIndex]?.time);
  const next = lyricsNextLineTime(lineIndex);
  const fallbackStart = Number.isFinite(start) ? Math.max(0, start - 0.25) : 0;
  const fallbackEnd = Number.isFinite(next) ? next + 0.25 : fallbackStart + Math.max(1.2, lyricsEstimatedWordFillDuration(lineIndex) + 0.5);
  return { start: fallbackStart, end: fallbackEnd, samples: [] };
}

function lyricsWaveformPercent(time, wave) {
  if (!Number.isFinite(time) || !wave || wave.end <= wave.start) return 0;
  return clamp((time - wave.start) / (wave.end - wave.start), 0, 1) * 100;
}

function lyricsWaveformTime(percent, wave) {
  if (!wave || wave.end <= wave.start) return NaN;
  return wave.start + clamp(percent, 0, 1) * (wave.end - wave.start);
}

function lyricsWaveformPolygon(samples, width = 1000, height = 96) {
  const hasSamples = Boolean(samples.length);
  const source = hasSamples
    ? samples
    : Array.from({ length: 48 }, (_, index) => 0.58 + Math.sin(index * 0.6) * 0.08);
  const clean = source.map(value => {
    const normalized = clamp(Number(value) || 0, 0, 1);
    const boosted = Math.pow(normalized, 0.68);
    return Math.max(hasSamples ? 0.22 : 0.46, boosted);
  });
  const middle = height / 2;
  const top = clean.map((value, index) => {
    const x = clean.length <= 1 ? 0 : (index / (clean.length - 1)) * width;
    const amp = clamp(Number(value) || 0, 0, 1) * (height * 0.46);
    return `${x.toFixed(1)},${(middle - amp).toFixed(1)}`;
  });
  const bottom = [...clean].reverse().map((value, reverseIndex) => {
    const index = clean.length - 1 - reverseIndex;
    const x = clean.length <= 1 ? 0 : (index / (clean.length - 1)) * width;
    const amp = clamp(Number(value) || 0, 0, 1) * (height * 0.46);
    return `${x.toFixed(1)},${(middle + amp).toFixed(1)}`;
  });
  return [...top, ...bottom].join(" ");
}

function lyricsTimingWordSegments(lineIndex, wave = lyricsWaveformWindow(lineIndex)) {
  return lyricsTimingWordSegmentPlan(lineIndex, wave).segments;
}

function lyricsTimingWordSegmentPlan(lineIndex, wave = lyricsWaveformWindow(lineIndex)) {
  const targets = lyricsLineTimingTargets(lineIndex);
  const span = Math.max(0.2, (Number(wave?.end) || 0) - (Number(wave?.start) || 0));
  let previousEnd = NaN;
  let correctedCount = 0;
  const segments = targets.map((target, index) => {
    let start = lyricsBoundaryReferenceTime(lineIndex, target.startBoundaryIndex, "start");
    let end = lyricsBoundaryReferenceTime(lineIndex, target.endBoundaryIndex, "end");
    if (!Number.isFinite(start)) {
      start = wave.start + span * (index / Math.max(1, targets.length));
    }
    if (!Number.isFinite(end)) {
      end = wave.start + span * ((index + 1) / Math.max(1, targets.length));
    }
    start = Math.max(0, start);
    end = Math.max(0, end);
    const originalStart = start;
    const originalEnd = end;
    let corrected = false;
    if (Number.isFinite(previousEnd) && start < previousEnd) {
      const shift = previousEnd - start;
      start += shift;
      end += shift;
      corrected = true;
    }
    const minDuration = Math.max(lyricsTimingMinBoundaryGap, Math.min(0.08, span / Math.max(10, targets.length * 6)));
    if (end < start + minDuration) {
      end = start + minDuration;
      corrected = true;
    }
    if (corrected || Math.abs(start - originalStart) > 0.0005 || Math.abs(end - originalEnd) > 0.0005) {
      correctedCount += 1;
    }
    previousEnd = end;
    return {
      ...target,
      originalStart,
      originalEnd,
      start,
      end,
      corrected
    };
  });
  return { segments, correctedCount };
}

function lyricsTimingRangeTimeLimits(target = activeLyricsTimingTarget) {
  if (!target) return { minStart: -Infinity, maxEnd: Infinity };
  normalizeLyricsTimingRange(target);
  const segments = lyricsTimingWordSegments(target.lineIndex);
  const rangeStartBoundary = lyricsTimingRangeBoundary("start");
  const rangeEndBoundary = lyricsTimingRangeBoundary("end");
  const selectedStartSegment = segments[rangeStartBoundary];
  const selectedEndSegment = segments[rangeEndBoundary - 1];
  const wave = lyricsWaveformWindow(target.lineIndex);
  const previousBlock = lyricsTimingRangeSideBlock(target.lineIndex, rangeStartBoundary, "previous", segments);
  const nextBlock = lyricsTimingRangeSideBlock(target.lineIndex, rangeEndBoundary, "next", segments);
  const waveStart = Number(wave?.start);
  const waveEnd = Number(wave?.end);
  const selectedCount = Math.max(1, rangeEndBoundary - rangeStartBoundary);
  const previousSpanStart = Number(segments[previousBlock?.startIndex]?.start);
  const nextSpanEnd = Number(segments[nextBlock?.endIndex]?.end);
  const previousCount = previousBlock ? previousBlock.endIndex - previousBlock.startIndex + 1 : 0;
  const nextCount = nextBlock ? nextBlock.endIndex - nextBlock.startIndex + 1 : 0;
  const minStart = previousBlock
    ? previousSpanStart + previousCount * lyricsTimingMinBoundaryGap
    : rangeStartBoundary <= 0
      ? (Number.isFinite(waveStart) ? waveStart : 0)
      : Number(selectedStartSegment?.start);
  const maxEnd = nextBlock
    ? nextSpanEnd - nextCount * lyricsTimingMinBoundaryGap
    : rangeEndBoundary >= segments.length
      ? (Number.isFinite(waveEnd) ? waveEnd : Number(selectedEndSegment?.end))
      : Number(selectedEndSegment?.end);
  return {
    minStart: Number.isFinite(minStart) ? minStart : 0,
    maxEnd: Number.isFinite(maxEnd) ? maxEnd : Infinity,
    minDuration: selectedCount * lyricsTimingMinBoundaryGap
  };
}

function lyricsTimingTargetTimeLimits(target) {
  if (!target) return { minStart: -Infinity, maxEnd: Infinity };
  const segments = lyricsTimingWordSegments(target.lineIndex);
  const previousEnd = Number(segments[target.wordIndex - 1]?.end);
  const nextStart = Number(segments[target.wordIndex + 1]?.start);
  return {
    minStart: Number.isFinite(previousEnd) ? previousEnd : -Infinity,
    maxEnd: Number.isFinite(nextStart) ? nextStart : Infinity
  };
}

function constrainLyricsTimingTimes(start, end, limits = {}, role = "") {
  let cleanStart = Number(start);
  let cleanEnd = Number(end);
  if (!Number.isFinite(cleanStart) || !Number.isFinite(cleanEnd)) {
    return { ok: false, message: text("lyricsTimingInvalid"), start: cleanStart, end: cleanEnd, corrected: false };
  }
  const minStart = Number.isFinite(limits.minStart) ? limits.minStart : 0;
  const maxEnd = Number.isFinite(limits.maxEnd) ? limits.maxEnd : Infinity;
  const minGap = Number.isFinite(limits.minDuration)
    ? Math.max(lyricsTimingMinBoundaryGap, Number(limits.minDuration))
    : lyricsTimingMinBoundaryGap;
  let corrected = false;
  if (role === "start") {
    const maxStart = Math.min(cleanEnd - minGap, maxEnd - minGap);
    if (maxStart < minStart) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), start: cleanStart, end: cleanEnd, corrected };
    }
    const nextStart = clamp(cleanStart, minStart, maxStart);
    corrected = corrected || Math.abs(nextStart - cleanStart) > 0.0005;
    cleanStart = nextStart;
  } else if (role === "end") {
    const minEnd = Math.max(cleanStart + minGap, minStart + minGap);
    if (maxEnd < minEnd) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), start: cleanStart, end: cleanEnd, corrected };
    }
    const nextEnd = clamp(cleanEnd, minEnd, maxEnd);
    corrected = corrected || Math.abs(nextEnd - cleanEnd) > 0.0005;
    cleanEnd = nextEnd;
  } else {
    const nextStart = Math.max(cleanStart, minStart);
    const nextEnd = Math.min(cleanEnd, maxEnd);
    corrected = corrected || Math.abs(nextStart - cleanStart) > 0.0005 || Math.abs(nextEnd - cleanEnd) > 0.0005;
    cleanStart = nextStart;
    cleanEnd = nextEnd;
    if (cleanEnd <= cleanStart + minGap) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), start: cleanStart, end: cleanEnd, corrected };
    }
  }
  if (cleanEnd <= cleanStart) {
    return { ok: false, message: text("lyricsTimingRangeInvalid"), start: cleanStart, end: cleanEnd, corrected };
  }
  return { ok: true, start: cleanStart, end: cleanEnd, corrected };
}

function lyricsTimingRangeSideBlock(lineIndex, boundaryIndex, side, segments = lyricsTimingWordSegments(lineIndex)) {
  const cleanBoundary = Math.round(Number(boundaryIndex));
  if (!Number.isFinite(cleanBoundary) || !Array.isArray(segments) || !segments.length) return null;
  const holdBoundaries = new Set();
  if (side === "previous") {
    if (cleanBoundary <= 0 || holdBoundaries.has(cleanBoundary)) return null;
    let startIndex = 0;
    for (let index = cleanBoundary - 1; index > 0; index -= 1) {
      if (holdBoundaries.has(index)) {
        startIndex = index;
        break;
      }
    }
    const endIndex = Math.min(cleanBoundary - 1, segments.length - 1);
    return startIndex <= endIndex ? { startIndex, endIndex } : null;
  }
  if (cleanBoundary >= segments.length || holdBoundaries.has(cleanBoundary)) return null;
  let endIndex = segments.length - 1;
  for (let index = cleanBoundary + 1; index < segments.length; index += 1) {
    if (holdBoundaries.has(index)) {
      endIndex = index - 1;
      break;
    }
  }
  const startIndex = Math.max(0, cleanBoundary);
  return startIndex <= endIndex ? { startIndex, endIndex } : null;
}

function updateLyricsTimingSegmentRange(segment, start, end, changed) {
  if (!segment) return false;
  const cleanStart = Number(start);
  const cleanEnd = Number(end);
  if (!Number.isFinite(cleanStart) || !Number.isFinite(cleanEnd) || cleanEnd < cleanStart + lyricsTimingMinBoundaryGap - 0.0005) {
    return false;
  }
  const hasChanged = changed ||
    Math.abs(Number(segment.start) - cleanStart) > 0.0005 ||
    Math.abs(Number(segment.end) - cleanEnd) > 0.0005;
  if (!hasChanged) return true;
  segment.start = cleanStart;
  segment.end = cleanEnd;
  segment.corrected = true;
  return true;
}

function layoutLyricsTimingPreviousNeighborsToBoundary(segments, startIndex, endIndex, boundaryTime) {
  const firstIndex = Math.max(0, Math.round(Number(startIndex)));
  const lastIndex = Math.min(segments.length - 1, Math.round(Number(endIndex)));
  const boundary = Number(boundaryTime);
  if (!Array.isArray(segments) || firstIndex > lastIndex) {
    return { ok: true, segments: [] };
  }
  if (!Number.isFinite(boundary)) {
    return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: [] };
  }
  const changed = [];
  let nextStart = boundary;
  for (let index = lastIndex; index >= firstIndex; index -= 1) {
    const segment = segments[index];
    if (!segment) continue;
    const oldStart = Number(segment.start);
    const oldEnd = Number(segment.end);
    let start = Number.isFinite(oldStart) ? oldStart : nextStart - lyricsTimingMinBoundaryGap;
    const end = nextStart;
    if (end < start + lyricsTimingMinBoundaryGap) {
      start = end - lyricsTimingMinBoundaryGap;
    }
    if (start < -0.0005 || end < start + lyricsTimingMinBoundaryGap - 0.0005) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: changed };
    }
    const didChange = Math.abs(start - oldStart) > 0.0005 || Math.abs(end - oldEnd) > 0.0005;
    if (!updateLyricsTimingSegmentRange(segment, Math.max(0, start), end, didChange)) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: changed };
    }
    if (didChange) changed.push(segment);
    nextStart = segment.start;
  }
  return { ok: true, segments: changed };
}

function layoutLyricsTimingNextNeighborsToBoundary(segments, startIndex, endIndex, boundaryTime) {
  const firstIndex = Math.max(0, Math.round(Number(startIndex)));
  const lastIndex = Math.min(segments.length - 1, Math.round(Number(endIndex)));
  const boundary = Number(boundaryTime);
  if (!Array.isArray(segments) || firstIndex > lastIndex) {
    return { ok: true, segments: [] };
  }
  if (!Number.isFinite(boundary)) {
    return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: [] };
  }
  const changed = [];
  let previousEnd = boundary;
  for (let index = firstIndex; index <= lastIndex; index += 1) {
    const segment = segments[index];
    if (!segment) continue;
    const oldStart = Number(segment.start);
    const oldEnd = Number(segment.end);
    const start = previousEnd;
    let end = Number.isFinite(oldEnd) ? oldEnd : start + lyricsTimingMinBoundaryGap;
    if (end < start + lyricsTimingMinBoundaryGap) {
      end = start + lyricsTimingMinBoundaryGap;
    }
    if (start < -0.0005 || end < start + lyricsTimingMinBoundaryGap - 0.0005) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: changed };
    }
    const didChange = Math.abs(start - oldStart) > 0.0005 || Math.abs(end - oldEnd) > 0.0005;
    if (!updateLyricsTimingSegmentRange(segment, Math.max(0, start), end, didChange)) {
      return { ok: false, message: text("lyricsTimingOrderInvalid"), segments: changed };
    }
    if (didChange) changed.push(segment);
    previousEnd = segment.end;
  }
  return { ok: true, segments: changed };
}

function layoutLyricsTimingWordDrag(drag, desiredStart, options = {}) {
  const segments = Array.isArray(drag?.segments) ? drag.segments.map(segment => ({ ...segment })) : [];
  const index = Number(drag?.wordIndex);
  const current = segments[index];
  if (!current) return { ok: false, message: text("lyricsTimingInvalid"), segments: [] };
  const wave = drag.wave || lyricsTimingWordDragWave(drag.waveNode);
  const duration = Math.max(lyricsTimingMinBoundaryGap, Number(drag.duration) || lyricsTimingMinBoundaryGap);
  const previousBlock = lyricsTimingRangeSideBlock(drag.lineIndex, index, "previous", segments);
  const nextBlock = lyricsTimingRangeSideBlock(drag.lineIndex, index + 1, "next", segments);
  const preserveGap = Boolean(options.preserveGap);
  const movingRight = Number(desiredStart) > Number(drag.startTime) + 0.0005;
  const movingLeft = Number(desiredStart) < Number(drag.startTime) - 0.0005;
  const previousSpanStart = Number(segments[previousBlock?.startIndex]?.start);
  const nextSpanEnd = Number(segments[nextBlock?.endIndex]?.end);
  const previousCount = previousBlock ? previousBlock.endIndex - previousBlock.startIndex + 1 : 0;
  const nextCount = nextBlock ? nextBlock.endIndex - nextBlock.startIndex + 1 : 0;
  const previousEnd = Number(segments[index - 1]?.end);
  const nextStart = Number(segments[index + 1]?.start);
  const minStart = preserveGap && !movingLeft
    ? index <= 0
      ? (Number.isFinite(wave.start) ? wave.start : 0)
      : Number.isFinite(previousEnd)
        ? previousEnd
        : Number(current.start)
    : previousBlock
    ? previousSpanStart + previousCount * lyricsTimingMinBoundaryGap
    : index <= 0
      ? (Number.isFinite(wave.start) ? wave.start : 0)
      : Number(current.start);
  const maxStart = preserveGap && !movingRight
    ? index >= segments.length - 1
      ? (Number.isFinite(wave.end) ? Number(wave.end) - duration : Number(current.start))
      : Number.isFinite(nextStart)
        ? nextStart - duration
        : Number(current.start)
    : nextBlock
    ? nextSpanEnd - nextCount * lyricsTimingMinBoundaryGap - duration
    : index >= segments.length - 1
      ? (Number.isFinite(wave.end) ? Number(wave.end) - duration : Number(current.start))
      : Number(current.start);
  if (!Number.isFinite(maxStart) || maxStart < minStart) {
    return { ok: false, message: text("lyricsTimingOrderInvalid"), segments };
  }
  const start = clamp(Number(desiredStart), minStart, maxStart);
  const end = start + duration;
  current.start = start;
  current.end = end;
  current.corrected = true;
  let compressed = false;
  if (previousBlock && (!preserveGap || movingLeft)) {
    const previousLayout = layoutLyricsTimingPreviousNeighborsToBoundary(
      segments,
      previousBlock.startIndex,
      previousBlock.endIndex,
      start
    );
    if (!previousLayout.ok) return { ...previousLayout, segments };
    compressed = compressed || previousLayout.segments.some(segment => segment.corrected);
  }
  if (nextBlock && (!preserveGap || movingRight)) {
    const nextLayout = layoutLyricsTimingNextNeighborsToBoundary(
      segments,
      nextBlock.startIndex,
      nextBlock.endIndex,
      end
    );
    if (!nextLayout.ok) return { ...nextLayout, segments };
    compressed = compressed || nextLayout.segments.some(segment => segment.corrected);
  }

  return {
    ok: true,
    start,
    end,
    segments,
    compressed
  };
}

function repairLyricsTimingLineOrder(lineIndex) {
  const plan = lyricsTimingWordSegmentPlan(lineIndex);
  if (!plan.correctedCount) return 0;
  let saved = 0;
  for (const segment of plan.segments) {
    if (!segment.corrected) continue;
    const result = stageLyricsTimingTarget(segment, segment.start, segment.end);
    if (result.ok) saved += 1;
  }
  return saved;
}

function lyricsTimingWaveWordsHtml(lineIndex, wave, segments = lyricsTimingWordSegments(lineIndex, wave)) {
  return segments.map(item => {
    const leftPct = lyricsWaveformPercent(item.start, wave);
    const rightPct = lyricsWaveformPercent(item.end, wave);
    const widthPct = Math.max(0.05, rightPct - leftPct);
    const compact = widthPct < 4.2;
    const classes = [
      "lyrics-wave-word",
      lyricsTimingWordInRange(item.wordIndex) ? "selected" : "",
      item.wordIndex === activeLyricsTimingTarget?.wordIndex ? "active" : "",
      lyricsTimingTargetHasManual(item) ? "has-manual" : "",
      compact ? "compact" : ""
    ].filter(Boolean).join(" ");
    return `
      <button class="${classes}" type="button" data-lyrics-action="select-word" data-word-index="${item.wordIndex}" style="left:${leftPct.toFixed(3)}%; width:${widthPct.toFixed(3)}%" title="${escapeHtml(item.wordText)}">
        <span>${escapeHtml(item.wordText)}</span>
      </button>
    `;
  }).join("");
}

function lyricsTimingWaveEdgePadding(firstStart, lastEnd, wave) {
  if (!Number.isFinite(firstStart) || !Number.isFinite(lastEnd) || lastEnd <= firstStart) {
    return lyricsTimingWaveMinEdgePadSeconds;
  }
  const segmentSpan = lastEnd - firstStart;
  const waveSpan = Number(wave?.end) - Number(wave?.start);
  const base = Math.max(segmentSpan * lyricsTimingWaveEdgePadRatio, Number.isFinite(waveSpan) ? waveSpan * 0.08 : 0);
  return clamp(base, lyricsTimingWaveMinEdgePadSeconds, lyricsTimingWaveMaxEdgePadSeconds);
}

function lyricsTimingWaveHtml(lineIndex) {
  let wave = lyricsWaveformWindow(lineIndex);
  const segmentPlan = lyricsTimingWordSegmentPlan(lineIndex, wave);
  const firstStart = Math.min(...segmentPlan.segments.map(item => item.start).filter(Number.isFinite));
  const lastEnd = Math.max(...segmentPlan.segments.map(item => item.end).filter(Number.isFinite));
  const edgePad = lyricsTimingWaveEdgePadding(firstStart, lastEnd, wave);
  if (Number.isFinite(firstStart) && firstStart - edgePad < wave.start) {
    wave = { ...wave, start: Math.max(0, firstStart - edgePad) };
  }
  if (Number.isFinite(lastEnd) && lastEnd + edgePad > wave.end) {
    wave = { ...wave, end: lastEnd + edgePad };
  }
  const startState = lyricsTimingRangeInputState("start");
  const endState = lyricsTimingRangeInputState("end");
  const startTime = Number.isFinite(startState.time) ? startState.time : wave.start;
  const endTime = Number.isFinite(endState.time) ? endState.time : wave.end;
  const startPct = lyricsWaveformPercent(startTime, wave);
  const endPct = lyricsWaveformPercent(endTime, wave);
  const leftPct = Math.min(startPct, endPct);
  const widthPct = Math.max(1, Math.abs(endPct - startPct));
  const duration = Number.isFinite(startTime) && Number.isFinite(endTime) && endTime > startTime
    ? formatLyricsEditorTime(endTime - startTime)
    : "";
  return `
    <div class="lyrics-wave-editor" data-wave-start="${wave.start}" data-wave-end="${wave.end}" aria-label="${escapeHtml(text("lyricsTimingWaveLabel"))}" title="${escapeHtml(text("lyricsTimingHoldHint"))}">
      <svg class="lyrics-wave-svg" viewBox="0 0 1000 96" preserveAspectRatio="none" aria-hidden="true">
        <polygon class="lyrics-wave-fill" points="${lyricsWaveformPolygon(wave.samples)}"></polygon>
        <line class="lyrics-wave-midline" x1="0" y1="48" x2="1000" y2="48"></line>
      </svg>
      <div class="lyrics-wave-selection" style="left:${leftPct.toFixed(3)}%; width:${widthPct.toFixed(3)}%"></div>
      <div class="lyrics-wave-playhead" style="left:${lyricsWaveformPercent(Number(els.audioPlayer?.currentTime) || 0, wave).toFixed(3)}%"></div>
      <div class="lyrics-wave-words">
        ${lyricsTimingWaveWordsHtml(lineIndex, wave, segmentPlan.segments)}
      </div>
      <button class="lyrics-wave-handle start" type="button" data-lyrics-wave-handle="start" style="left:${startPct.toFixed(3)}%" aria-label="${escapeHtml(text("lyricsTimingStartLabel"))}"></button>
      <button class="lyrics-wave-handle end" type="button" data-lyrics-wave-handle="end" style="left:${endPct.toFixed(3)}%" aria-label="${escapeHtml(text("lyricsTimingEndLabel"))}"></button>
      <div class="lyrics-wave-labels">
        <span>${escapeHtml(formatLyricsEditorTime(startTime))}</span>
        <span>${escapeHtml(duration ? text("lyricsTimingRangeDuration", duration) : "")}</span>
        <span>${escapeHtml(formatLyricsEditorTime(endTime))}</span>
      </div>
    </div>
  `;
}

function setLyricsEditorInput(input, seconds) {
  if (input) input.value = formatLyricsEditorTime(seconds);
}

function lyricsTimingDetailTime(role) {
  const input = role === "start" ? els.lyricsTimingStartInput : els.lyricsTimingEndInput;
  const raw = String(input?.value || input?.placeholder || "").trim();
  return parseLyricsEditorTime(raw);
}

function syncLyricsTimingWaveFromDetailInputs() {
  const root = els.lyricsTimingEditor;
  const waveNode = root?.querySelector(".lyrics-wave-editor");
  if (!root || !waveNode) return;
  const wave = {
    start: Number(waveNode.dataset.waveStart),
    end: Number(waveNode.dataset.waveEnd)
  };
  const startTime = lyricsTimingDetailTime("start");
  const endTime = lyricsTimingDetailTime("end");
  const startPct = lyricsWaveformPercent(startTime, wave);
  const endPct = lyricsWaveformPercent(endTime, wave);
  const leftPct = Math.min(startPct, endPct);
  const widthPct = Math.max(1, Math.abs(endPct - startPct));
  const startHandle = waveNode.querySelector(".lyrics-wave-handle.start");
  const endHandle = waveNode.querySelector(".lyrics-wave-handle.end");
  const selection = waveNode.querySelector(".lyrics-wave-selection");
  const labels = waveNode.querySelectorAll(".lyrics-wave-labels span");
  if (startHandle) startHandle.style.left = `${startPct.toFixed(3)}%`;
  if (endHandle) endHandle.style.left = `${endPct.toFixed(3)}%`;
  if (selection) {
    selection.style.left = `${leftPct.toFixed(3)}%`;
    selection.style.width = `${widthPct.toFixed(3)}%`;
  }
  if (labels[0]) labels[0].textContent = formatLyricsEditorTime(startTime);
  if (labels[1]) labels[1].textContent = Number.isFinite(startTime) && Number.isFinite(endTime) && endTime > startTime
    ? text("lyricsTimingRangeDuration", formatLyricsEditorTime(endTime - startTime))
    : "";
  if (labels[2]) labels[2].textContent = formatLyricsEditorTime(endTime);
}

function updateLyricsTimingWavePlayhead(time = Number(els.audioPlayer?.currentTime) || 0) {
  const root = els.lyricsTimingEditor;
  const waveNode = root?.querySelector(".lyrics-wave-editor");
  const playhead = waveNode?.querySelector(".lyrics-wave-playhead");
  if (!waveNode || !playhead) return;
  const wave = {
    start: Number(waveNode.dataset.waveStart),
    end: Number(waveNode.dataset.waveEnd)
  };
  if (!Number.isFinite(wave.start) || !Number.isFinite(wave.end) || wave.end <= wave.start) return;
  const percent = lyricsWaveformPercent(time, wave);
  playhead.style.left = `${percent.toFixed(3)}%`;
  waveNode.classList.toggle("playhead-outside", time < wave.start || time > wave.end);
}

function setLyricsTimingWaveWordRect(waveNode, wave, segment) {
  const node = waveNode?.querySelector(`.lyrics-wave-word[data-word-index="${segment.wordIndex}"]`);
  if (!node) return;
  const leftPct = lyricsWaveformPercent(segment.start, wave);
  const rightPct = lyricsWaveformPercent(segment.end, wave);
  node.style.left = `${leftPct.toFixed(3)}%`;
  node.style.width = `${Math.max(0.05, rightPct - leftPct).toFixed(3)}%`;
}

function lyricsTimingWordDragWave(waveNode) {
  return {
    start: Number(waveNode?.dataset.waveStart),
    end: Number(waveNode?.dataset.waveEnd)
  };
}

function updateLyricsTimingWordDragFromPointer(event) {
  const drag = lyricsTimingWaveDrag;
  const waveNode = drag?.waveNode;
  if (!drag || !waveNode) return;
  const rect = waveNode.getBoundingClientRect();
  if (!rect.width) return;
  const wave = lyricsTimingWordDragWave(waveNode);
  const deltaTime = ((event.clientX - drag.startClientX) / rect.width) * (wave.end - wave.start);
  const preserveGap = Boolean(event.altKey);
  const layout = layoutLyricsTimingWordDrag(drag, drag.startTime + deltaTime, { preserveGap });
  if (!layout.ok) {
    setLyricsMarkStatus(layout.message);
    return;
  }
  drag.currentStart = layout.start;
  drag.currentEnd = layout.end;
  drag.currentSegments = layout.segments;
  drag.compressed = Boolean(layout.compressed);
  drag.preserveGap = preserveGap;
  drag.moved = drag.moved || Math.abs(layout.start - drag.startTime) > 0.006;

  for (const segment of layout.segments) setLyricsTimingWaveWordRect(waveNode, wave, segment);
  setLyricsEditorInput(els.lyricsTimingStartInput, layout.start);
  setLyricsEditorInput(els.lyricsTimingEndInput, layout.end);
  syncLyricsTimingWaveFromDetailInputs();
  updateLyricsTimingDurationForSelectedRange();
}

function previewLyricsTimingSelectedRangeLayout(layout, waveNode) {
  if (!layout?.ok || !waveNode) return;
  const wave = lyricsTimingWordDragWave(waveNode);
  for (const segment of layout.segments || []) setLyricsTimingWaveWordRect(waveNode, wave, segment);
  for (const segment of layout.sideSegments || []) setLyricsTimingWaveWordRect(waveNode, wave, segment);
}

function updateLyricsTimingBoundaryDragFromPointer(event) {
  const drag = lyricsTimingWaveDrag;
  const waveNode = drag?.waveNode;
  if (!drag || !waveNode) return;
  const rect = waveNode.getBoundingClientRect();
  if (!rect.width) return;
  const wave = lyricsTimingWordDragWave(waveNode);
  let time = lyricsWaveformTime((event.clientX - rect.left) / rect.width, wave);
  if (!Number.isFinite(time)) return;
  time = clamp(time, wave.start, wave.end);
  const startTime = drag.role === "start" ? time : lyricsTimingDetailTime("start");
  const endTime = drag.role === "end" ? time : lyricsTimingDetailTime("end");
  const constrained = constrainLyricsTimingTimes(startTime, endTime, lyricsTimingRangeTimeLimits(), drag.role);
  if (!constrained.ok) {
    setLyricsMarkStatus(constrained.message);
    return;
  }
  time = drag.role === "start" ? constrained.start : constrained.end;
  setLyricsEditorInput(drag.role === "start" ? els.lyricsTimingStartInput : els.lyricsTimingEndInput, time);
  syncLyricsTimingWaveFromDetailInputs();
  updateLyricsTimingDurationForSelectedRange();
  const layout = lyricsTimingSelectedRangeLayout(constrained.start, constrained.end);
  if (!layout.ok) {
    setLyricsMarkStatus(layout.message);
    return;
  }
  drag.currentStart = layout.start;
  drag.currentEnd = layout.end;
  drag.currentSegments = layout.segments;
  drag.moved = drag.moved ||
    Math.abs(layout.start - drag.startTime) > 0.0005 ||
    Math.abs(layout.end - drag.endTime) > 0.0005;
  previewLyricsTimingSelectedRangeLayout(layout, waveNode);
}

function updateLyricsTimingWaveFromPointer(event) {
  if (lyricsTimingWaveDrag?.mode === "word") updateLyricsTimingWordDragFromPointer(event);
  else updateLyricsTimingBoundaryDragFromPointer(event);
}

function handleLyricsTimingWavePointerDown(event) {
  if (event.button === 2) {
    const waveNode = event.target.closest?.(".lyrics-wave-editor");
    if (!waveNode || !els.lyricsTimingEditor?.contains(waveNode)) return;
    event.preventDefault();
    event.stopPropagation();
    suppressLyricsTimingContextMenuUntil = performance.now() + 700;
    if (!lyricsTimingWaveDrag) togglePlayback();
    return;
  }
  if (event.button !== 0) return;
  const handle = event.target.closest?.("[data-lyrics-wave-handle]");
  if (handle && els.lyricsTimingEditor?.contains(handle)) {
    event.preventDefault();
    const waveNode = handle.closest(".lyrics-wave-editor");
    lyricsTimingWaveDrag = {
      mode: "boundary",
      role: handle.dataset.lyricsWaveHandle === "start" ? "start" : "end",
      pointerId: event.pointerId,
      waveNode,
      startTime: lyricsTimingDetailTime("start"),
      endTime: lyricsTimingDetailTime("end"),
      moved: false
    };
    try {
      els.lyricsTimingEditor.setPointerCapture(event.pointerId);
    } catch {}
    updateLyricsTimingWaveFromPointer(event);
    return;
  }

  const wordNode = event.target.closest?.(".lyrics-wave-word");
  if (!wordNode || !els.lyricsTimingEditor?.contains(wordNode)) return;
  const target = activeLyricsTimingTarget;
  if (!target) return;
  const wordIndex = Number(wordNode.dataset.wordIndex);
  const wordTarget = lyricsTimingTargetForLineWord(target.lineIndex, wordIndex);
  if (!wordTarget) return;
  const waveNode = wordNode.closest(".lyrics-wave-editor");
  const segments = lyricsTimingWordSegments(target.lineIndex);
  const segment = segments.find(item => item.wordIndex === wordIndex);
  if (!waveNode || !segment) return;
  event.preventDefault();
  activeLyricsTimingTarget = wordTarget;
  activeLyricsTimingRangeStart = wordTarget.wordIndex;
  activeLyricsTimingRangeEnd = wordTarget.wordIndex;
  activeLyricsTimingRangeMode = "word";
  syncLyricsTimingPanelSelection();
  setLyricsEditorInput(els.lyricsTimingStartInput, segment.start);
  setLyricsEditorInput(els.lyricsTimingEndInput, segment.end);
  syncLyricsTimingWaveFromDetailInputs();
  updateLyricsTimingDurationForSelectedRange();
  wordNode.classList.add("dragging");
  lyricsTimingWaveDrag = {
    mode: "word",
    pointerId: event.pointerId,
    waveNode,
    wordNode,
    lineIndex: target.lineIndex,
    wordIndex,
    startClientX: event.clientX,
    startTime: segment.start,
    endTime: segment.end,
    currentStart: segment.start,
    currentEnd: segment.end,
    duration: segment.end - segment.start,
    previousSegment: segments[wordIndex - 1],
    nextSegment: segments[wordIndex + 1],
    segments: segments.map(item => ({ ...item })),
    tailAnchorEnd: Number(segments[segments.length - 1]?.end),
    wave: lyricsTimingWordDragWave(waveNode),
    moved: false
  };
  try {
    els.lyricsTimingEditor.setPointerCapture(event.pointerId);
  } catch {}
}

function handleLyricsTimingWavePointerMove(event) {
  if (!lyricsTimingWaveDrag || lyricsTimingWaveDrag.pointerId !== event.pointerId) return;
  event.preventDefault();
  updateLyricsTimingWaveFromPointer(event);
}

function finishLyricsTimingWordDrag(drag) {
  drag.wordNode?.classList.remove("dragging");
  if (!drag.moved) return;
  const currentTarget = lyricsTimingTargetForLineWord(drag.lineIndex, drag.wordIndex);
  if (!currentTarget) return;
  const originalSegments = Array.isArray(drag.segments) ? drag.segments : [];
  const nextSegments = Array.isArray(drag.currentSegments) ? drag.currentSegments : [];
  let saved = 0;
  for (const segment of nextSegments) {
    const original = originalSegments.find(item => item.wordIndex === segment.wordIndex);
    const changed = !original ||
      Math.abs(Number(original.start) - Number(segment.start)) > 0.0005 ||
      Math.abs(Number(original.end) - Number(segment.end)) > 0.0005;
    if (!changed) continue;
    saved += stageLyricsTimingSegmentBoundaryChanges(segment, original);
  }
  activeLyricsTimingTarget = currentTarget;
  activeLyricsTimingRangeStart = currentTarget.wordIndex;
  activeLyricsTimingRangeEnd = currentTarget.wordIndex;
  activeLyricsTimingRangeMode = "word";
  suppressLyricsTimingClickUntil = performance.now() + 360;
  renderLyricsTimingEditor();
  setLyricsMarkStatus(text("lyricsTimingWordMoved", currentTarget.wordText));
  flushPendingMusicLyricMarks();
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
}

function finishLyricsTimingBoundaryDrag(drag) {
  if (!drag.moved) return;
  const result = stageLyricsTimingSelectedRange(drag.currentStart, drag.currentEnd);
  if (!result.ok) {
    setLyricsMarkStatus(result.message);
    return;
  }
  suppressLyricsTimingClickUntil = performance.now() + 360;
  renderLyricsTimingEditor();
  setLyricsMarkStatus(
    result.corrected
      ? text("lyricsTimingOrderCorrected", result.count)
      : result.count === 1
        ? text("lyricsTimingSaved", formatLyricsEditorTime(result.start), formatLyricsEditorTime(result.end))
        : text("lyricsTimingRangeSaved", result.count)
  );
  flushPendingMusicLyricMarks();
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
}

function finishLyricsTimingWaveDrag(event) {
  if (!lyricsTimingWaveDrag || lyricsTimingWaveDrag.pointerId !== event.pointerId) return;
  event.preventDefault();
  const drag = lyricsTimingWaveDrag;
  try {
    els.lyricsTimingEditor?.releasePointerCapture(event.pointerId);
  } catch {}
  lyricsTimingWaveDrag = null;
  if (drag.mode === "word") finishLyricsTimingWordDrag(drag);
  else if (drag.mode === "boundary") finishLyricsTimingBoundaryDrag(drag);
}

function lyricsTimingWaveTimeFromPointer(event, waveNode) {
  const rect = waveNode?.getBoundingClientRect?.();
  if (!rect?.width) return NaN;
  const wave = {
    start: Number(waveNode.dataset.waveStart),
    end: Number(waveNode.dataset.waveEnd)
  };
  return lyricsWaveformTime((event.clientX - rect.left) / rect.width, wave);
}

function seekLyricsTimingWaveToPointer(event, waveNode) {
  if (!hasMusic || !els.audioPlayer || !waveNode) return false;
  const time = lyricsTimingWaveTimeFromPointer(event, waveNode);
  if (!Number.isFinite(time)) return false;
  const duration = audioDuration();
  const targetTime = duration > 0 ? clamp(time, 0, duration) : Math.max(0, time);
  const beforeRatio = currentAudioSeekRatio();
  if (!applyAudioCurrentTime(targetTime)) return false;
  pendingSeekRatio = null;
  userSeeking = false;
  const nextRatio = duration > 0 ? clamp(targetTime / duration, 0, 1) : 0;
  if (els.trackSeek) els.trackSeek.value = String(nextRatio * 100);
  if (els.trackCurrentTime) els.trackCurrentTime.textContent = formatDuration(targetTime);
  if (els.trackDuration) els.trackDuration.textContent = formatDuration(duration);
  if (duration > 0) recordTrackSeekChange(beforeRatio, nextRatio);
  updateLyricsProgress(targetTime);
  updateTrackProgress();
  return true;
}

function clearLyricsTimingSelection() {
  els.nowPlayingLyricsList?.querySelectorAll(".lyric-word.lyrics-timing-selected").forEach(word => {
    word.classList.remove("lyrics-timing-selected");
  });
}

function syncLyricsTimingSelection() {
  clearLyricsTimingSelection();
}

function closeLyricsTimingEditor() {
  clearLyricsTimingAutoSave();
  activeLyricsTimingTarget = null;
  activeLyricsTimingRangeMode = "word";
  if (els.lyricsTimingEditor) els.lyricsTimingEditor.hidden = true;
  clearLyricsTimingSelection();
}

function syncLyricsTimingPanelSelection() {
  const root = els.lyricsTimingEditor;
  const target = activeLyricsTimingTarget;
  if (!root || !target) return;
  normalizeLyricsTimingRange(target);
  root.querySelectorAll("[data-word-index]").forEach(node => {
    const wordIndex = Number(node.dataset.wordIndex);
    node.classList.toggle("selected", lyricsTimingWordInRange(wordIndex));
    node.classList.toggle("active", wordIndex === target.wordIndex);
  });
  if (els.lyricsTimingTarget) {
    els.lyricsTimingTarget.textContent = text("lyricsTimingTarget", target.wordText, target.lineIndex + 1);
  }
  syncLyricsTimingSelection();
}

function renderLyricsTimingEditor() {
  const root = ensureLyricsTimingEditorRoot();
  const target = activeLyricsTimingTarget;
  if (!root || !target || target.path !== musicLyricsTrackPath) return 0;
  const targets = lyricsLineTimingTargets(target.lineIndex);
  if (!targets.length) {
    closeLyricsTimingEditor();
    return 0;
  }
  const repairedCount = repairLyricsTimingLineOrder(target.lineIndex);
  const selectedIndex = clamp(Math.round(Number(target.wordIndex) || 0), 0, targets.length - 1);
  activeLyricsTimingTarget = targets[selectedIndex];
  const selected = activeLyricsTimingTarget;
  normalizeLyricsTimingRange(selected);
  if (activeLyricsTimingRangeMode !== "range" || !lyricsTimingWordInRange(selected.wordIndex)) {
    activeLyricsTimingRangeStart = selected.wordIndex;
    activeLyricsTimingRangeEnd = selected.wordIndex;
    activeLyricsTimingRangeMode = "word";
  }
  const selectedTargets = lyricsTimingSelectedTargets();
  const rangeFirst = selectedTargets[0] || selected;
  const rangeLast = selectedTargets[selectedTargets.length - 1] || selected;

  root.innerHTML = `
    <div class="lyrics-timing-head">
      <div class="lyrics-timing-title-stack">
        <span id="lyricsTimingTarget" class="lyrics-timing-target">${escapeHtml(text("lyricsTimingTarget", selected.wordText, selected.lineIndex + 1))}</span>
        <span class="lyrics-timing-line-title">${escapeHtml(text("lyricsTimingLineTitle", selected.lineIndex + 1, targets.length))}</span>
      </div>
      <button class="lyrics-timing-close" type="button" data-lyrics-action="close" aria-label="${escapeHtml(text("lyricsTimingClose"))}">x</button>
    </div>
    ${lyricsTimingWaveHtml(selected.lineIndex)}
    <div class="lyrics-timing-detail">
      <strong>${escapeHtml(text("lyricsTimingRangeTitle", rangeFirst.wordText, rangeLast.wordText))}</strong>
      <div class="lyrics-timing-fields">
        <label>
          <span>${escapeHtml(text("lyricsTimingStartLabel"))}</span>
          ${lyricsTimingRangeInputHtml("start", "lyrics-detail-time", "lyricsTimingStartInput")}
        </label>
        <label>
          <span>${escapeHtml(text("lyricsTimingEndLabel"))}</span>
          ${lyricsTimingRangeInputHtml("end", "lyrics-detail-time", "lyricsTimingEndInput")}
        </label>
      </div>
      <div class="lyrics-timing-actions">
        <button type="button" data-lyrics-action="select-line">${escapeHtml(text("lyricsTimingSelectLine"))}</button>
      </div>
    </div>
  `;
  refreshLyricsTimingEditorRefs();
  mountLyricsTimingEditorForLine(selected.lineIndex);
  syncLyricsTimingPanelSelection();
  updateLyricsTimingWavePlayhead(Number(els.audioPlayer?.currentTime) || 0);
  if (repairedCount) setLyricsMarkStatus(text("lyricsTimingOrderCorrected", repairedCount));
  return repairedCount;
}

function selectLyricsTimingWord(lineIndex, wordIndex, options = {}) {
  const target = lyricsTimingTargetForLineWord(lineIndex, wordIndex);
  if (!target) return false;
  if (options.extend && activeLyricsTimingTarget?.lineIndex === lineIndex) {
    activeLyricsTimingRangeStart = Math.min(activeLyricsTimingRangeStart, target.wordIndex);
    activeLyricsTimingRangeEnd = Math.max(activeLyricsTimingRangeEnd, target.wordIndex);
    activeLyricsTimingRangeMode = "range";
  } else {
    activeLyricsTimingRangeStart = target.wordIndex;
    activeLyricsTimingRangeEnd = target.wordIndex;
    activeLyricsTimingRangeMode = "word";
  }
  activeLyricsTimingTarget = target;
  renderLyricsTimingEditor();
  return true;
}

function selectLyricsTimingLine() {
  const target = activeLyricsTimingTarget;
  if (!target) return;
  activeLyricsTimingRangeStart = 0;
  activeLyricsTimingRangeEnd = Math.max(0, target.wordCount - 1);
  activeLyricsTimingRangeMode = "range";
  renderLyricsTimingEditor();
}

function lyricsWordIndexFromLineEvent(lineNode, event) {
  const wordNode = event?.target?.closest?.(".lyric-word");
  if (wordNode && lineNode?.contains(wordNode)) {
    const wordIndex = Number(wordNode.dataset.wordIndex);
    if (Number.isFinite(wordIndex)) return wordIndex;
  }
  if (event) {
    const boundaryTarget = closestLyricsBoundaryTarget(lineNode, event.clientX, event.clientY);
    const markerIndex = Number(boundaryTarget?.markerWord?.dataset?.wordIndex);
    if (Number.isFinite(markerIndex)) return markerIndex;
  }
  const lineIndex = Number(lineNode?.dataset?.lyricsIndex);
  const currentTime = Number(els.audioPlayer?.currentTime);
  const timedIndex = lyricsWordIndexAtTime(lineIndex, currentTime);
  return Number.isFinite(timedIndex) ? timedIndex : 0;
}

function lyricsWordTimingTargetFromEvent(lineNode, event) {
  const lineIndex = Number(lineNode.dataset.lyricsIndex);
  const wordIndex = lyricsWordIndexFromLineEvent(lineNode, event);
  if (!Number.isFinite(lineIndex) || !Number.isFinite(wordIndex)) return null;
  return lyricsTimingTargetForLineWord(lineIndex, wordIndex);
}

function populateLyricsTimingEditor(target) {
  if (!target || !els.lyricsTimingEditor) return;
  preloadLyricsHotspotLine(target.lineIndex);
  activeLyricsTimingTarget = target;
  activeLyricsTimingRangeStart = target.wordIndex;
  activeLyricsTimingRangeEnd = target.wordIndex;
  activeLyricsTimingRangeMode = "word";
  const repairedCount = renderLyricsTimingEditor();
  if (!repairedCount) setLyricsMarkStatus(text("lyricsMarkArmed"));
}

function openLyricsTimingEditorFromContext(event) {
  if (!hasMusic || !musicLyricsSynced || !musicLyricsTrackPath || musicLyricsTrackPath !== selectedTrackPath) return;
  const lineNode = event.target.closest?.(".music-lyrics-line");
  if (!lineNode || !els.nowPlayingLyricsList?.contains(lineNode) || lineNode.classList.contains("rest")) return;
  event.preventDefault();
  suppressLyricsLineClickUntil = performance.now() + 320;
  const lineIndex = Number(lineNode.dataset.lyricsIndex);
  const now = performance.now();
  if (lineIndex === lyricsTimingContextLineIndex && now - lyricsTimingContextLastAt <= 1100) {
    lyricsTimingContextClickCount += 1;
  } else {
    lyricsTimingContextLineIndex = lineIndex;
    lyricsTimingContextClickCount = 1;
  }
  lyricsTimingContextLastAt = now;
  if (lyricsTimingContextClickCount < 3) {
    return;
  }
  lyricsTimingContextClickCount = 0;
  const target = lyricsWordTimingTargetFromEvent(lineNode, event);
  if (!target) return;
  populateLyricsTimingEditor(target);
}

function setLyricsTimingInputToCurrent(role) {
  const currentTime = Number(els.audioPlayer?.currentTime);
  if (!Number.isFinite(currentTime)) return;
  const target = activeLyricsTimingTarget;
  if (!target) return;
  const startTime = role === "start" ? currentTime : lyricsTimingDetailTime("start");
  const endTime = role === "end" ? currentTime : lyricsTimingDetailTime("end");
  const constrained = constrainLyricsTimingTimes(startTime, endTime, lyricsTimingRangeTimeLimits(target), role);
  if (!constrained.ok) {
    setLyricsMarkStatus(constrained.message);
    return;
  }
  const time = role === "start" ? constrained.start : constrained.end;
  const value = formatLyricsEditorTime(time);
  setLyricsEditorInput(role === "start" ? els.lyricsTimingStartInput : els.lyricsTimingEndInput, time);
  if (activeLyricsTimingRangeStart === activeLyricsTimingRangeEnd) {
    const rowInput = els.lyricsTimingEditor?.querySelector(`.lyrics-row-time[data-word-index="${target.wordIndex}"][data-role="${role}"]`);
    if (rowInput) rowInput.value = value;
    updateLyricsTimingDurationForWord(target.wordIndex);
  }
  syncLyricsTimingWaveFromDetailInputs();
  updateLyricsTimingDurationForSelectedRange();
}

function stageLyricsTimingBoundaryMark(target, role, time, note = "") {
  const cleanRole = role === "start" ? "start" : "end";
  const boundaryIndex = cleanRole === "start" ? target.startBoundaryIndex : target.endBoundaryIndex;
  const previousWord = cleanRole === "start" ? target.previousWord : target.wordText;
  const nextWord = cleanRole === "start" ? target.wordText : target.nextWord;
  stagePendingMusicLyricMark({
    path: target.path,
    role: cleanRole,
    time: Math.max(0, Math.round(time * 1000) / 1000),
    lineIndex: target.lineIndex,
    boundaryIndex,
    previousWord,
    nextWord,
    wordCount: target.wordCount,
    word: target.wordText,
    lineText: target.lineText,
    note: note || (cleanRole === "start" ? "manual-editor-start-boundary" : "manual-editor-end-boundary")
  });
}

function stageLyricsTimingTarget(target, start, end, options = {}) {
  if (!target) return { ok: false, message: text("lyricsTimingInvalid") };
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < 0) {
    return { ok: false, message: text("lyricsTimingInvalid") };
  }
  if (end <= start) {
    return { ok: false, message: text("lyricsTimingRangeInvalid") };
  }
  stageLyricsTimingBoundaryMark(target, "start", start, options.startNote);
  stageLyricsTimingBoundaryMark(target, "end", end, options.endNote);
  return { ok: true };
}

function stageLyricsTimingSegmentBoundaryChanges(segment, original = null, force = false) {
  if (!segment) return 0;
  let saved = 0;
  const startChanged = force || !original || Math.abs(Number(original.start) - Number(segment.start)) > 0.0005;
  const endChanged = force || !original || Math.abs(Number(original.end) - Number(segment.end)) > 0.0005;
  if (startChanged) {
    stageLyricsTimingBoundaryMark(segment, "start", segment.start);
    saved += 1;
  }
  if (endChanged) {
    stageLyricsTimingBoundaryMark(segment, "end", segment.end);
    saved += 1;
  }
  return saved;
}

function lyricsTimingSelectedRangeLayout(start, end) {
  const selected = lyricsTimingSelectedTargets();
  const target = activeLyricsTimingTarget;
  if (!selected.length || !target) return { ok: false, message: text("lyricsTimingInvalid"), count: 0 };
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < 0) {
    return { ok: false, message: text("lyricsTimingInvalid"), count: 0 };
  }
  if (end <= start) {
    return { ok: false, message: text("lyricsTimingRangeInvalid"), count: 0 };
  }
  const constrained = constrainLyricsTimingTimes(start, end, lyricsTimingRangeTimeLimits(target));
  if (!constrained.ok) {
    return { ...constrained, count: 0 };
  }
  start = constrained.start;
  end = constrained.end;
  const analysisLine = lyricsAnalysisLine(target.lineIndex);
  const wordCount = lyricsWordCountForLine(target.lineIndex, analysisLine);
  const rangeStartBoundary = lyricsTimingRangeBoundary("start");
  const rangeEndBoundary = lyricsTimingRangeBoundary("end");
  const lineSegments = lyricsTimingWordSegments(target.lineIndex);
  const originalSegments = lineSegments.map(item => ({ ...item }));
  const autoStart = lyricsAutoBoundaryRelativeTime(rangeStartBoundary, analysisLine, wordCount);
  const autoEnd = lyricsAutoBoundaryRelativeTime(rangeEndBoundary, analysisLine, wordCount);
  const autoSpan = autoEnd - autoStart;
  const indexSpan = Math.max(1, rangeEndBoundary - rangeStartBoundary);
  const segments = selected.map(item => {
    const itemStartAuto = lyricsAutoBoundaryRelativeTime(item.startBoundaryIndex, analysisLine, wordCount);
    const itemEndAuto = lyricsAutoBoundaryRelativeTime(item.endBoundaryIndex, analysisLine, wordCount);
    const startRatio = autoSpan > 0.001
      ? clamp((itemStartAuto - autoStart) / autoSpan, 0, 1)
      : clamp((item.startBoundaryIndex - rangeStartBoundary) / indexSpan, 0, 1);
    const endRatio = autoSpan > 0.001
      ? clamp((itemEndAuto - autoStart) / autoSpan, 0, 1)
      : clamp((item.endBoundaryIndex - rangeStartBoundary) / indexSpan, 0, 1);
    return {
      ...item,
      start: start + (end - start) * startRatio,
      end: start + (end - start) * endRatio
    };
  });
  const sideSegments = [];
  const previousBlock = lyricsTimingRangeSideBlock(target.lineIndex, rangeStartBoundary, "previous", lineSegments);
  if (previousBlock) {
    const previousLayout = layoutLyricsTimingPreviousNeighborsToBoundary(
      lineSegments,
      previousBlock.startIndex,
      previousBlock.endIndex,
      start
    );
    if (!previousLayout.ok) return { ...previousLayout, count: 0 };
    sideSegments.push(...previousLayout.segments);
  }
  const nextBlock = lyricsTimingRangeSideBlock(target.lineIndex, rangeEndBoundary, "next", lineSegments);
  if (nextBlock) {
    const nextLayout = layoutLyricsTimingNextNeighborsToBoundary(
      lineSegments,
      nextBlock.startIndex,
      nextBlock.endIndex,
      end
    );
    if (!nextLayout.ok) return { ...nextLayout, count: 0 };
    sideSegments.push(...nextLayout.segments);
  }
  return { ok: true, count: selected.length, corrected: constrained.corrected, start, end, segments, sideSegments, originalSegments };
}

function stageLyricsTimingSelectedRange(start, end) {
  const layout = lyricsTimingSelectedRangeLayout(start, end);
  if (!layout.ok) return layout;
  const originalByWord = new Map((layout.originalSegments || []).map(item => [item.wordIndex, item]));
  for (const item of [...layout.segments, ...(layout.sideSegments || [])]) {
    stageLyricsTimingSegmentBoundaryChanges(item, originalByWord.get(item.wordIndex));
  }
  return layout;
}

function readLyricsTimingInputs(startInput, endInput) {
  const startRaw = String(startInput?.value || "").trim();
  const endRaw = String(endInput?.value || "").trim();
  return {
    startRaw,
    endRaw,
    start: parseLyricsEditorTime(startRaw),
    end: parseLyricsEditorTime(endRaw)
  };
}

function updateLyricsTimingDurationForWord(wordIndex) {
  const row = els.lyricsTimingEditor?.querySelector(`.lyrics-timing-row[data-word-index="${wordIndex}"]`);
  if (!row) return;
  const startInput = row.querySelector(".lyrics-row-time[data-role='start']");
  const endInput = row.querySelector(".lyrics-row-time[data-role='end']");
  const duration = row.querySelector(".lyrics-timing-duration");
  const values = readLyricsTimingInputs(startInput, endInput);
  const partial = Boolean(values.startRaw || values.endRaw);
  const invalid = partial && (!Number.isFinite(values.start) || !Number.isFinite(values.end) || values.end <= values.start);
  row.classList.toggle("invalid", invalid);
  if (duration) duration.textContent = invalid ? "!" : lyricsTimingDurationTextFromValues(values.startRaw, values.endRaw);
}

function updateLyricsTimingDurationForSelectedRange() {
  const values = readLyricsTimingInputs(els.lyricsTimingStartInput, els.lyricsTimingEndInput);
  const invalid = Boolean(values.startRaw || values.endRaw) && (!Number.isFinite(values.start) || !Number.isFinite(values.end) || values.end <= values.start);
  els.lyricsTimingEditor?.classList.toggle("lyrics-range-invalid", invalid);
}

function clearLyricsTimingAutoSave() {
  if (!lyricsTimingAutoSaveTimer) return;
  window.clearTimeout(lyricsTimingAutoSaveTimer);
  lyricsTimingAutoSaveTimer = null;
}

function lyricsTimingInputCompleteAndValid(startInput, endInput) {
  const values = readLyricsTimingInputs(startInput, endInput);
  const complete = Boolean(values.startRaw && values.endRaw);
  return {
    ...values,
    complete,
    valid: complete && Number.isFinite(values.start) && Number.isFinite(values.end) && values.end > values.start
  };
}

function autoSaveLyricsTimingRow(wordIndex, { quiet = true } = {}) {
  const target = activeLyricsTimingTarget;
  if (!target || target.path !== musicLyricsTrackPath) return false;
  const row = els.lyricsTimingEditor?.querySelector(`.lyrics-timing-row[data-word-index="${wordIndex}"]`);
  const rowTarget = lyricsTimingTargetForLineWord(target.lineIndex, wordIndex);
  if (!row || !rowTarget) return false;
  const startInput = row.querySelector(".lyrics-row-time[data-role='start']");
  const endInput = row.querySelector(".lyrics-row-time[data-role='end']");
  const values = lyricsTimingInputCompleteAndValid(startInput, endInput);
  if (!values.startRaw && !values.endRaw) return false;
  if (!values.valid) {
    row.classList.toggle("invalid", Boolean(values.startRaw || values.endRaw));
    if (!quiet) setLyricsMarkStatus(values.complete ? text("lyricsTimingRangeInvalid") : text("lyricsTimingIncomplete"));
    return false;
  }
  const result = stageLyricsTimingTarget(rowTarget, values.start, values.end);
  if (!result.ok) {
    row.classList.add("invalid");
    if (!quiet) setLyricsMarkStatus(result.message);
    return false;
  }
  row.classList.remove("invalid");
  if (activeLyricsTimingTarget?.wordIndex === rowTarget.wordIndex) {
    setLyricsEditorInput(els.lyricsTimingStartInput, values.start);
    setLyricsEditorInput(els.lyricsTimingEndInput, values.end);
  }
  renderLyricsTimingEditor();
  setLyricsMarkStatus(text("lyricsTimingSaved", formatLyricsEditorTime(values.start), formatLyricsEditorTime(values.end)));
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
  flushPendingMusicLyricMarks();
  return true;
}

function autoSaveLyricsTimingInput(input, { quiet = true } = {}) {
  if (!input?.matches?.(".lyrics-row-time, .lyrics-detail-time")) return false;
  if (input.classList.contains("lyrics-row-time")) {
    const wordIndex = Number(input.dataset.wordIndex);
    return Number.isFinite(wordIndex) ? autoSaveLyricsTimingRow(wordIndex, { quiet }) : false;
  }
  const values = lyricsTimingInputCompleteAndValid(els.lyricsTimingStartInput, els.lyricsTimingEndInput);
  if (!values.startRaw && !values.endRaw) return false;
  if (!values.valid) {
    els.lyricsTimingEditor?.classList.toggle("lyrics-range-invalid", Boolean(values.startRaw || values.endRaw));
    if (!quiet) setLyricsMarkStatus(values.complete ? text("lyricsTimingRangeInvalid") : text("lyricsTimingIncomplete"));
    return false;
  }
  return saveLyricsTimingEditor({ quiet });
}

function scheduleLyricsTimingAutoSave(input) {
  clearLyricsTimingAutoSave();
  if (!input?.matches?.(".lyrics-row-time, .lyrics-detail-time")) return;
  lyricsTimingAutoSaveTimer = window.setTimeout(() => {
    lyricsTimingAutoSaveTimer = null;
    autoSaveLyricsTimingInput(input, { quiet: true });
  }, 520);
}

function saveLyricsTimingEditor(options = {}) {
  const target = activeLyricsTimingTarget;
  if (!target || target.path !== musicLyricsTrackPath) return;
  const values = readLyricsTimingInputs(els.lyricsTimingStartInput, els.lyricsTimingEndInput);
  const result = stageLyricsTimingSelectedRange(values.start, values.end);
  if (!result.ok) {
    if (!options.quiet) setLyricsMarkStatus(result.message);
    return;
  }
  setLyricsMarkStatus(
    result.corrected
      ? text("lyricsTimingOrderCorrected", result.count)
      : result.count === 1
        ? text("lyricsTimingSaved", formatLyricsEditorTime(result.start), formatLyricsEditorTime(result.end))
      : text("lyricsTimingRangeSaved", result.count)
  );
  renderLyricsTimingEditor();
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
  flushPendingMusicLyricMarks();
}

function saveLyricsTimingLine() {
  const target = activeLyricsTimingTarget;
  if (!target || target.path !== musicLyricsTrackPath) return;
  const rows = Array.from(els.lyricsTimingEditor?.querySelectorAll(".lyrics-timing-row[data-word-index]") || []);
  let saved = 0;
  for (const row of rows) {
    const wordIndex = Number(row.dataset.wordIndex);
    const rowTarget = lyricsTimingTargetForLineWord(target.lineIndex, wordIndex);
    const startInput = row.querySelector(".lyrics-row-time[data-role='start']");
    const endInput = row.querySelector(".lyrics-row-time[data-role='end']");
    const values = readLyricsTimingInputs(startInput, endInput);
    if (!values.startRaw && !values.endRaw) continue;
    if (!values.startRaw || !values.endRaw) {
      row.classList.add("invalid");
      setLyricsMarkStatus(text("lyricsTimingIncomplete"));
      return;
    }
    const result = stageLyricsTimingTarget(rowTarget, values.start, values.end);
    if (!result.ok) {
      row.classList.add("invalid");
      setLyricsMarkStatus(result.message);
      return;
    }
    saved += 1;
  }
  if (!saved) {
    setLyricsMarkStatus(text("lyricsTimingLineEmpty"));
    return;
  }
  setLyricsMarkStatus(text("lyricsTimingLineSaved", saved));
  renderLyricsTimingEditor();
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
  flushPendingMusicLyricMarks();
}

async function clearLyricsTimingEditorMarks() {
  const target = activeLyricsTimingTarget;
  if (!target || target.path !== musicLyricsTrackPath) return;
  for (const item of lyricsTimingSelectedTargets()) {
    removePendingMusicLyricMarksForTarget(item.path, item.lineIndex, item.startBoundaryIndex, ["start"]);
    removePendingMusicLyricMarksForTarget(item.path, item.lineIndex, item.endBoundaryIndex, ["end"]);
  }
  const selected = selectedTrack();
  if (selected?.path === musicLyricsTrackPath) {
    await loadLyricsAnalysisForTrack(selected, musicLyricsLoadToken);
  }
  activeLyricsTimingTarget = lyricsTimingTargetForLineWord(target.lineIndex, target.wordIndex);
  renderLyricsTimingEditor();
  setLyricsMarkStatus(text("lyricsTimingCleared"));
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
}

async function clearLyricsTimingLineMarks() {
  const target = activeLyricsTimingTarget;
  if (!target || target.path !== musicLyricsTrackPath) return;
  const targets = lyricsLineTimingTargets(target.lineIndex);
  for (const item of targets) {
    removePendingMusicLyricMarksForTarget(item.path, item.lineIndex, item.startBoundaryIndex, ["start"]);
    removePendingMusicLyricMarksForTarget(item.path, item.lineIndex, item.endBoundaryIndex, ["end"]);
  }
  const selected = selectedTrack();
  if (selected?.path === musicLyricsTrackPath) {
    await loadLyricsAnalysisForTrack(selected, musicLyricsLoadToken);
  }
  activeLyricsTimingTarget = lyricsTimingTargetForLineWord(target.lineIndex, target.wordIndex);
  renderLyricsTimingEditor();
  setLyricsMarkStatus(text("lyricsTimingLineCleared"));
  syncLyricsLineVisualStates(musicLyricsActiveIndex, { instant: true });
  updateLyricsProgress(Number(els.audioPlayer?.currentTime) || 0);
}

function handleLyricsTimingEditorDoubleClick(event) {
  if (!els.lyricsTimingEditor?.contains(event.target)) return;
  const waveNode = event.target.closest?.(".lyrics-wave-editor");
  if (!waveNode || !els.lyricsTimingEditor.contains(waveNode)) return;
  event.preventDefault();
  seekLyricsTimingWaveToPointer(event, waveNode);
}

function handleLyricsTimingEditorContextMenu(event) {
  const waveNode = event.target.closest?.(".lyrics-wave-editor");
  if (!waveNode || !els.lyricsTimingEditor?.contains(waveNode)) return;
  event.preventDefault();
  event.stopPropagation();
  if (performance.now() < suppressLyricsTimingContextMenuUntil) return;
  if (lyricsTimingWaveDrag) return;
  togglePlayback();
}

function handleLyricsTimingEditorClick(event) {
  if (performance.now() < suppressLyricsTimingClickUntil) {
    event.preventDefault();
    return;
  }
  const actionNode = event.target.closest?.("[data-lyrics-action]");
  if (!actionNode || !els.lyricsTimingEditor?.contains(actionNode)) {
    const waveNode = event.target.closest?.(".lyrics-wave-editor");
    if (
      waveNode &&
      els.lyricsTimingEditor?.contains(waveNode) &&
      !event.target.closest?.("[data-lyrics-wave-handle]")
    ) {
      event.preventDefault();
      seekLyricsTimingWaveToPointer(event, waveNode);
    }
    return;
  }
  const action = actionNode.dataset.lyricsAction;
  if (action === "select-word") {
    event.preventDefault();
    const lineIndex = activeLyricsTimingTarget?.lineIndex;
    const wordIndex = Number(actionNode.dataset.wordIndex);
    selectLyricsTimingWord(lineIndex, wordIndex, { extend: event.shiftKey });
    return;
  }
  event.preventDefault();
  if (action === "close") closeLyricsTimingEditor();
  else if (action === "select-line") selectLyricsTimingLine();
  else if (action === "use-now-start") setLyricsTimingInputToCurrent("start");
  else if (action === "use-now-end") setLyricsTimingInputToCurrent("end");
  else if (action === "save-selected") saveLyricsTimingEditor();
  else if (action === "save-line") saveLyricsTimingLine();
  else if (action === "clear-selected") clearLyricsTimingEditorMarks();
  else if (action === "clear-line") clearLyricsTimingLineMarks();
}

function handleLyricsTimingEditorInput(event) {
  const input = event.target;
  if (!input?.matches?.(".lyrics-row-time, .lyrics-detail-time")) return;
  const role = input.dataset.role;
  const wordIndex = Number(input.dataset.wordIndex ?? activeLyricsTimingTarget?.wordIndex);
  if (!Number.isFinite(wordIndex)) return;
  if (input.classList.contains("lyrics-detail-time")) {
    if (activeLyricsTimingRangeStart === activeLyricsTimingRangeEnd) {
      const rowInput = els.lyricsTimingEditor?.querySelector(`.lyrics-row-time[data-word-index="${wordIndex}"][data-role="${role}"]`);
      if (rowInput) rowInput.value = input.value;
    }
    syncLyricsTimingWaveFromDetailInputs();
    updateLyricsTimingDurationForSelectedRange();
  } else if (activeLyricsTimingTarget?.wordIndex === wordIndex) {
    const detailInput = role === "start" ? els.lyricsTimingStartInput : els.lyricsTimingEndInput;
    if (detailInput) detailInput.value = input.value;
    syncLyricsTimingWaveFromDetailInputs();
    updateLyricsTimingDurationForSelectedRange();
  }
  updateLyricsTimingDurationForWord(wordIndex);
  scheduleLyricsTimingAutoSave(input);
}

function handleLyricsTimingEditorKeydown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    closeLyricsTimingEditor();
    return;
  }
  if (event.key !== "Enter" || !event.target?.matches?.(".lyrics-row-time, .lyrics-detail-time")) return;
  event.preventDefault();
  clearLyricsTimingAutoSave();
  autoSaveLyricsTimingInput(event.target, { quiet: false });
}

function handleLyricsTimingEditorFocusOut(event) {
  if (!event.target?.matches?.(".lyrics-row-time, .lyrics-detail-time")) return;
  clearLyricsTimingAutoSave();
  autoSaveLyricsTimingInput(event.target, { quiet: true });
}

function setLyricsMarkStatus(message) {
  musicLyricsStatus = message;
  if (els.nowPlayingLyricsStatus) {
    els.nowPlayingLyricsStatus.textContent = musicLyricsStatus;
    els.nowPlayingLyricsStatus.hidden = false;
  }
}

function updateLyricsProgress(time = 0) {
  updateLyricsTimingWavePlayhead(time);
  if (!hasMusic || !musicLyricsLines.length) return;
  const list = els.nowPlayingLyricsList;
  if (!list) return;
  if (musicLyricsTrackPath !== selectedTrackPath) {
    musicLyricsActiveIndex = -1;
    heldLyricsActiveIndex = -1;
    heldLyricsActiveUntil = 0;
    syncLyricsLineVisualStates(-1);
    return;
  }
  let nextIndex = activeLyricsIndexAt(time);
  if (heldLyricsActiveIndex >= 0) {
    if (performance.now() < heldLyricsActiveUntil) {
      nextIndex = heldLyricsActiveIndex;
    } else {
      heldLyricsActiveIndex = -1;
      heldLyricsActiveUntil = 0;
    }
  }
  if (nextIndex === musicLyricsActiveIndex) {
    updateActiveLyricsWordProgress(time);
    updateLyricsLineTone(time);
    return;
  }
  musicLyricsActiveIndex = nextIndex;
  syncLyricsLineVisualStates(nextIndex, { scroll: nextIndex >= 0 });
  updateActiveLyricsWordProgress(time);
}

function musicLyricsCachePath(item) {
  return normalizeMusicTrackPathValue(typeof item === "string" ? item : item?.path);
}

function musicLyricsCacheType(item) {
  return String(item?.lyricsType || "lrc");
}

function getMusicLyricsCacheEntry(item) {
  const path = musicLyricsCachePath(item);
  if (!path) return null;
  const entry = musicLyricsCache.get(path);
  if (!entry) return null;
  if (typeof item === "object" && item) {
    if (entry.lyricsUrl !== item.lyricsUrl || entry.lyricsType !== musicLyricsCacheType(item)) return null;
  }
  return entry;
}

function setMusicLyricsCacheEntry(item, patch = {}) {
  const path = musicLyricsCachePath(item);
  if (!path) return null;
  const current = musicLyricsCache.get(path) || {};
  const entry = {
    ...current,
    path,
    lyricsUrl: typeof item === "object" && item ? item.lyricsUrl : current.lyricsUrl,
    lyricsType: typeof item === "object" && item ? musicLyricsCacheType(item) : current.lyricsType,
    ...patch
  };
  musicLyricsCache.set(path, entry);
  return entry;
}

async function fetchParsedLyricsForTrack(item) {
  const path = musicLyricsCachePath(item);
  if (!item?.lyricsUrl || !path) return null;
  const cached = getMusicLyricsCacheEntry(item);
  if (cached?.lines) return cached;
  const existing = musicLyricsTextPromises.get(path);
  if (existing) return existing;

  const promise = (async () => {
    const response = await fetch(item.lyricsUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const raw = await response.text();
    const parsed = parseLyricsText(raw, item.lyricsType || "lrc");
    return setMusicLyricsCacheEntry(item, {
      lines: parsed.lines,
      status: parsed.status,
      synced: parsed.synced,
      lyricsLoadedAt: Date.now()
    });
  })().finally(() => {
    if (musicLyricsTextPromises.get(path) === promise) musicLyricsTextPromises.delete(path);
  });
  musicLyricsTextPromises.set(path, promise);
  return promise;
}

async function fetchLyricsAnalysisForTrack(item) {
  const path = musicLyricsCachePath(item);
  if (!path) return null;
  const cached = getMusicLyricsCacheEntry(item);
  if (cached?.analysis?.ok) return cached.analysis;
  const existing = musicLyricsAnalysisPromises.get(path);
  if (existing) return existing;

  const promise = (async () => {
    const response = await fetch(`/api/music/lyrics/analysis?path=${encodeURIComponent(path)}`, { cache: "no-store" });
    if (!response.ok) return null;
    const result = await response.json();
    const analysis = result?.ok ? result : null;
    if (analysis) setMusicLyricsCacheEntry(item, { analysis, analysisLoadedAt: Date.now() });
    return analysis;
  })().finally(() => {
    if (musicLyricsAnalysisPromises.get(path) === promise) musicLyricsAnalysisPromises.delete(path);
  });
  musicLyricsAnalysisPromises.set(path, promise);
  return promise;
}

function applyMusicLyricsCacheToPanel(item, entry) {
  const path = musicLyricsCachePath(item);
  if (!path || !entry?.lines) return false;
  musicLyricsTrackPath = path;
  musicLyricsLines = entry.lines;
  musicLyricsStatus = entry.status || "";
  musicLyricsActiveIndex = -1;
  musicLyricsSynced = Boolean(entry.synced);
  musicLyricsAnalysis = entry.analysis?.ok ? mergePendingMusicLyricMarksIntoAnalysis(entry.analysis) : null;
  renderLyricsPanel();
  updateLyricsProgress(Number.isFinite(els.audioPlayer?.currentTime) ? els.audioPlayer.currentTime : 0);
  return true;
}

function applyLyricsAnalysisToActiveTrack(item, analysis) {
  const path = musicLyricsCachePath(item);
  if (!path || !analysis?.ok || selectedTrackPath !== path || musicLyricsTrackPath !== path) return false;
  musicLyricsAnalysis = mergePendingMusicLyricMarksIntoAnalysis(analysis);
  if (activeLyricsTimingTarget?.path === path && !els.lyricsTimingEditor?.hidden) {
    renderLyricsTimingEditor();
  }
  updateLyricsProgress(Number.isFinite(els.audioPlayer?.currentTime) ? els.audioPlayer.currentTime : 0);
  return true;
}

async function ensureLyricsAnalysisWarm(item) {
  if (!hasMusic || !item?.path || !item.lyricsUrl) return null;
  const path = musicLyricsCachePath(item);
  const cached = getMusicLyricsCacheEntry(item);
  if (cached?.analysis?.ok) {
    applyLyricsAnalysisToActiveTrack(item, cached.analysis);
    return cached;
  }
  const entry = cached?.lines ? cached : await fetchParsedLyricsForTrack(item);
  if (!entry?.synced) return entry;
  const analysis = await fetchLyricsAnalysisForTrack(item);
  if (analysis?.ok) {
    setMusicLyricsCacheEntry(item, { analysis, analysisLoadedAt: Date.now() });
    applyLyricsAnalysisToActiveTrack(item, analysis);
  }
  return getMusicLyricsCacheEntry(path);
}

async function preloadLyricsForTrack(item) {
  if (!hasMusic || !item?.path || !item.lyricsUrl) return null;
  try {
    const entry = await fetchParsedLyricsForTrack(item);
    if (entry?.synced) {
      await ensureLyricsAnalysisWarm(item);
    }
    return getMusicLyricsCacheEntry(item);
  } catch {
    return null;
  }
}

function scheduleSelectedLyricsPreload(delay = 80) {
  if (!hasMusic || !selectedTrackPath || typeof window === "undefined") return;
  if (musicLyricsPreloadTimer) window.clearTimeout(musicLyricsPreloadTimer);
  musicLyricsPreloadTimer = window.setTimeout(() => {
    musicLyricsPreloadTimer = 0;
    const item = selectedTrack();
    if (item?.path === selectedTrackPath) preloadLyricsForTrack(item);
  }, delay);
}

function preloadLyricsHotspotLine(lineIndex) {
  if (!hasMusic || !Number.isFinite(Number(lineIndex))) return;
  const item = selectedTrack();
  if (!item?.path || item.path !== selectedTrackPath || !item.lyricsUrl) return;
  ensureLyricsAnalysisWarm(item).catch(() => {});
}

async function loadLyricsAnalysisForTrack(item, token) {
  if (!item?.path || !musicLyricsSynced) return;
  try {
    const result = await fetchLyricsAnalysisForTrack(item);
    if (token !== musicLyricsLoadToken || musicLyricsTrackPath !== item.path) return;
    if (result?.ok) applyLyricsAnalysisToActiveTrack(item, result);
    else musicLyricsAnalysis = null;
  } catch {
    if (token === musicLyricsLoadToken && musicLyricsTrackPath === item.path) {
      musicLyricsAnalysis = null;
    }
  }
}

async function loadLyricsForTrack(item) {
  flushPendingMusicLyricMarks();
  const token = ++musicLyricsLoadToken;
  musicLyricsLookupPath = "";
  if (!item?.lyricsUrl) {
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
    renderLyricsPanel();
    return;
  }
  musicLyricsTrackPath = item?.path || "";
  musicLyricsLines = [];
  musicLyricsStatus = text("lyricsLoading");
  musicLyricsActiveIndex = -1;
  musicLyricsSynced = false;
  musicLyricsAnalysis = null;
  renderLyricsPanel();

  let lyricItem = item;
  if (token !== musicLyricsLoadToken) return;

  if (!lyricItem?.lyricsUrl) {
    musicLyricsLines = [];
    musicLyricsStatus = text("lyricsEmpty");
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
    renderLyricsPanel();
    return;
  }

  const cached = getMusicLyricsCacheEntry(lyricItem);
  if (cached?.lines) {
    applyMusicLyricsCacheToPanel(lyricItem, cached);
    if (cached.synced) {
      loadLyricsAnalysisForTrack(lyricItem, token);
    }
    return;
  }

  try {
    const parsed = await fetchParsedLyricsForTrack(lyricItem);
    if (token !== musicLyricsLoadToken) return;
    applyMusicLyricsCacheToPanel(lyricItem, parsed);
    loadLyricsAnalysisForTrack(lyricItem, token);
  } catch (error) {
    if (token !== musicLyricsLoadToken) return;
    musicLyricsLines = [];
    musicLyricsStatus = text("lyricsLoadFailed", error.message);
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
    renderLyricsPanel();
  }
}

function closeNowPlayingLyrics() {
  flushPendingMusicLyricMarks();
  stopLyricsAnimationLoop();
  musicLyricsLoadToken += 1;
  musicLyricsTrackPath = "";
  musicLyricsLines = [];
  musicLyricsStatus = "";
  musicLyricsActiveIndex = -1;
  musicLyricsSynced = false;
  musicLyricsAnalysis = null;
  musicLyricsLookupPath = "";
  renderLyricsPanel();
}

function replaceMusicTrackRecord(record) {
  if (!record?.path) return null;
  const localIndex = tracks.findIndex(item => item.path === record.path);
  if (localIndex >= 0) {
    tracks = tracks.map((item, index) => index === localIndex ? { ...item, ...record } : item);
    return tracks[localIndex];
  }
  const libraryIndex = libraryTracks.findIndex(item => item.path === record.path);
  if (libraryIndex >= 0) {
    libraryTracks = libraryTracks.map((item, index) => index === libraryIndex ? { ...item, ...record } : item);
    return libraryTracks[libraryIndex];
  }
  return record;
}

async function findLyricsForTrack(item) {
  if (!item?.path) return;
  const token = ++musicLyricsLoadToken;
  musicLyricsTrackPath = "";
  musicLyricsLines = [];
  musicLyricsStatus = "";
  musicLyricsActiveIndex = -1;
  musicLyricsSynced = false;
  musicLyricsAnalysis = null;
  musicLyricsLookupPath = item.path;
  renderLyricsPanel();

  try {
    const result = await postJson("/api/music/lyrics/fetch", { path: item.path, force: false }, { timeoutMs: 14000 });
    if (token !== musicLyricsLoadToken) return;
    musicLyricsLookupPath = "";
    if (Array.isArray(result.tracks)) {
      tracks = result.tracks;
    }
    const refreshed = replaceMusicTrackRecord(result.track) || selectedTrack();
    if (refreshed?.lyricsUrl) {
      musicNotice = "";
      renderMusic();
      loadLyricsForTrack(refreshed);
      return;
    }
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
    musicNotice = text("lyricsNotFound", displayTrackName(item.name));
    renderMusic();
  } catch (error) {
    if (token !== musicLyricsLoadToken) return;
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
    musicLyricsLookupPath = "";
    musicNotice = text("lyricsSearchFailed", error.message);
    renderMusic();
  }
}

function toggleNowPlayingLyrics() {
  const item = selectedTrack();
  if (!hasMusic || !item?.path) return;
  if (musicLyricsTrackPath === item.path) {
    closeNowPlayingLyrics();
    return;
  }
  if (item.lyricsUrl) {
    loadLyricsForTrack(item);
    return;
  }
  findLyricsForTrack(item);
}

function renderMusic() {
  if (!hasMusic) return;
  syncMusicTierAssignments();
  const selected = selectedTrack();
  const playable = allMusicTracks();
  els.musicDock.innerHTML = "";
  els.musicCount.textContent = text("trackCount", tracks.length);

  if (!playable.length) {
    setSelectedTrackPath("");
    els.currentTrackName.textContent = text("musicNotSelected");
    els.currentTrackMeta.textContent = text("musicEmptyBody");
    els.trackCurrentTime.textContent = "0:00";
    els.trackDuration.textContent = "0:00";
    els.trackSeek.value = "0";
    els.playPauseTrack.textContent = "▶";
    els.playPauseTrack.setAttribute("aria-label", text("playTrack"));
    els.playPauseTrack.title = text("playTrack");
    clearMusicLyrics(text("lyricsEmpty"));
  }

  if (musicLyricsTrackPath && !playable.some(item => item.path === musicLyricsTrackPath)) {
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
  }

  if (selected && !selectedTrackPath) {
    setSelectedTrackPath(selected.path, { persist: "soon" });
  }

  if (selected) {
    els.currentTrackName.textContent = displayTrackName(selected.name);
    els.currentTrackMeta.textContent = musicNotice || trackMeta(selected);
  } else {
    els.currentTrackName.textContent = text("musicNotSelected");
    els.currentTrackMeta.textContent = text("musicEmptyBody");
    musicLyricsTrackPath = "";
    musicLyricsLines = [];
    musicLyricsStatus = "";
    musicLyricsActiveIndex = -1;
    musicLyricsSynced = false;
    musicLyricsAnalysis = null;
  }

  els.playPauseTrack.textContent = els.audioPlayer.paused ? "▶" : "❚❚";
  const playLabel = els.audioPlayer.paused ? text("playTrack") : text("pauseTrack");
  els.playPauseTrack.setAttribute("aria-label", playLabel);
  els.playPauseTrack.title = playLabel;
  renderPlaybackMode();
  renderLyricsPanel();

  const tracksByTier = Object.fromEntries(musicTierGroups.map(group => [group.id, []]));
  for (const item of orderedLocalTracks()) {
    tracksByTier[tierForTrack(item)].push(item);
  }

  for (const group of musicTierGroups.filter(group => isMusicTierVisible(group.id))) {
    els.musicDock.appendChild(createMusicTierSection(group, tracksByTier[group.id]));
  }
}

function selectedMaterialCandidate() {
  return materialCandidates.find(item => item.path === selectedMaterialPath) || materialCandidates[0] || null;
}

function setMaterialStatus(message) {
  if (!els.materialImportStatus) return;
  els.materialImportStatus.textContent = message || text("materialReady");
}

function setRenderTextureStatus(message) {
  renderTextureNotice = message || "";
  if (!els.renderTextureZoneStatus) return;
  els.renderTextureZoneStatus.textContent = renderTextureNotice || (downloadIntakeEnabled ? text("renderTextureReady") : text("renderTextureDisabled"));
}

function renderDownloadIntake() {
  if (!hasMaterialWorkspace) return;
  if (els.downloadIntakeToggle) {
    els.downloadIntakeToggle.checked = downloadIntakeEnabled;
  }
  if (els.refreshMaterialCandidates) {
    els.refreshMaterialCandidates.disabled = !downloadIntakeEnabled;
  }
  if (els.renderTextureDropzone) {
    els.renderTextureDropzone.classList.toggle("disabled", !downloadIntakeEnabled);
    els.renderTextureDropzone.setAttribute("aria-disabled", String(!downloadIntakeEnabled));
  }
  setRenderTextureStatus(renderTextureNotice);
}

function renderMaterialImport(payload = {}) {
  if (!hasMaterialWorkspace || !els.materialCandidates) return;
  renderDownloadIntake();

  if (payload.source && els.materialSourcePath) {
    els.materialSourcePath.textContent = payload.source;
  }
  if (payload.target && els.materialTargetPath) {
    els.materialTargetPath.textContent = payload.target;
  }

  const selected = selectedMaterialCandidate();
  els.materialCandidates.innerHTML = "";
  if (els.importMaterial) {
    els.importMaterial.disabled = !selected;
  }

  if (!materialCandidates.length) {
    selectedMaterialPath = "";
    if (els.latestMaterialName) {
      els.latestMaterialName.textContent = text("noMaterialCandidate");
    }
    const empty = document.createElement("div");
    empty.className = "dock-empty material-empty";
    empty.innerHTML = `<strong>${text("noMaterialCandidate")}</strong><span>${text("materialEmpty")}</span>`;
    els.materialCandidates.appendChild(empty);
    setMaterialStatus(materialNotice || text("materialReady"));
    return;
  }

  if (!selectedMaterialPath && selected) {
    selectedMaterialPath = selected.path;
  }

  if (els.latestMaterialName) {
    els.latestMaterialName.textContent = selected ? selected.name : text("noMaterialCandidate");
  }

  for (const item of materialCandidates.slice(0, 8)) {
    const card = document.createElement("button");
    card.className = `material-card ${item.path === selectedMaterialPath ? "active" : ""}`;
    card.type = "button";
    card.title = text("materialCandidateTitle", item.name);
    card.addEventListener("click", () => {
      selectedMaterialPath = item.path;
      materialNotice = "";
      renderMaterialImport(payload);
    });
    card.addEventListener("dblclick", () => importMaterialCandidate(item.path));

    const name = document.createElement("strong");
    name.textContent = item.name;
    card.appendChild(name);

    const meta = document.createElement("span");
    meta.textContent = text("materialCandidateMeta", item.type, formatBytes(item.size));
    card.appendChild(meta);

    els.materialCandidates.appendChild(card);
  }

  setMaterialStatus(materialNotice || text("materialReady"));
}

function cloneDefaultWorkspaceTodos() {
  return defaultWorkspaceTodoGroups.map(group => ({
    id: group.id,
    labelKey: group.labelKey,
    title: group.title || "",
    items: group.items.map(item => ({
      id: item.id,
      textKey: item.textKey || "",
      text: item.text || "",
      done: Boolean(item.done)
    }))
  }));
}

function normalizeWorkspaceTodoItem(item, fallbackId = "") {
  if (!item || typeof item !== "object") return null;
  const text = typeof item.text === "string" ? item.text.trim() : "";
  const textKey = typeof item.textKey === "string" ? item.textKey : "";
  if (!text && !textKey) return null;
  return {
    id: typeof item.id === "string" && item.id ? item.id : fallbackId || createWorkspaceTodoId("todo"),
    text,
    textKey,
    done: Boolean(item.done)
  };
}

function normalizeWorkspaceTodoGroups(groups) {
  const incoming = Array.isArray(groups) ? groups : [];
  const savedById = new Map(
    incoming
      .filter(group => group && typeof group.id === "string")
      .map(group => [group.id, group])
  );

  const normalized = cloneDefaultWorkspaceTodos().map(defaultGroup => {
    const savedGroup = savedById.get(defaultGroup.id);
    if (!savedGroup || !Array.isArray(savedGroup.items)) return defaultGroup;

    const defaultItemsById = new Map(defaultGroup.items.map(item => [item.id, item]));
    const items = [];
    for (const item of savedGroup.items) {
      if (!item) continue;
      const defaultItem = defaultItemsById.get(item.id);
      const normalizedItem = normalizeWorkspaceTodoItem({
        ...defaultItem,
        ...item,
        textKey: item.textKey || defaultItem?.textKey || "",
        text: item.text || defaultItem?.text || ""
      });
      if (normalizedItem) items.push(normalizedItem);
    }

    return {
      ...defaultGroup,
      title: typeof savedGroup.title === "string" ? savedGroup.title : defaultGroup.title,
      items
    };
  });

  const defaultGroupIds = new Set(defaultWorkspaceTodoGroups.map(group => group.id));
  for (const group of incoming) {
    if (!group || defaultGroupIds.has(group.id)) continue;
    const title = typeof group.title === "string" ? group.title.trim() : "";
    const items = Array.isArray(group.items)
      ? group.items.map((item, index) => normalizeWorkspaceTodoItem(item, `${group.id}-${index}`)).filter(Boolean)
      : [];
    if (title || items.length) {
      normalized.push({
        id: typeof group.id === "string" && group.id ? group.id : createWorkspaceTodoId("group"),
        title: title || "Custom",
        labelKey: "",
        items
      });
    }
  }

  return normalized;
}

function loadWorkspaceTodos() {
  try {
    return normalizeWorkspaceTodoGroups(JSON.parse(localStorage.getItem(storageKeys.workspaceTodos) || "[]")).filter(group =>
      Array.isArray(group.items) && group.items.length > 0
    );
  } catch {
    return cloneDefaultWorkspaceTodos();
  }
}

function resetWorkspaceTodoGroups() {
  workspaceTodoGroups = cloneDefaultWorkspaceTodos();
  saveWorkspaceTodos();
}

function saveWorkspaceTodos() {
  localStorage.setItem(storageKeys.workspaceTodos, JSON.stringify(workspaceTodoGroups));
}

function renderGithubDownloads() {
  if (!els.githubDownloadsMeta && !els.githubDownloadsLink && !els.githubDownloadsStatus) return;
  const url = githubDownloadsInfo?.url || "";
  const configured = Boolean(githubDownloadsInfo?.configured && url);
  if (els.githubDownloadsStatus) {
    els.githubDownloadsStatus.textContent = text(configured ? "githubDownloadsReady" : "githubDownloadsMissing");
  }
  if (els.githubDownloadsMeta) {
    els.githubDownloadsMeta.textContent = configured
      ? text("githubDownloadsFound", url)
      : text("githubDownloadsNotConfigured");
  }
  if (els.githubDownloadsLink) {
    els.githubDownloadsLink.href = configured ? url : "#";
    els.githubDownloadsLink.setAttribute("aria-disabled", configured ? "false" : "true");
    els.githubDownloadsLink.classList.toggle("disabled", !configured);
  }
  if (els.openGithubDownloads) {
    els.openGithubDownloads.disabled = !configured;
  }
}

async function loadGithubDownloadsInfo() {
  if (!hasWorkspace || !els.githubDownloadsMeta) return;
  els.githubDownloadsMeta.textContent = text("githubDownloadsResolving");
  try {
    const response = await fetch("/api/workspace/github-downloads", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    githubDownloadsInfo = payload;
  } catch (error) {
    githubDownloadsInfo = { configured: false, url: "", error: error.message };
  }
  renderGithubDownloads();
}

async function openGithubDownloads() {
  if (!hasWorkspace || !els.openGithubDownloads) return;
  els.openGithubDownloads.disabled = true;
  try {
    const result = await postJson("/api/workspace/open-github-downloads");
    githubDownloadsInfo = result;
    renderGithubDownloads();
  } catch (error) {
    if (els.githubDownloadsMeta) {
      els.githubDownloadsMeta.textContent = text("githubDownloadsOpenFailed", error.message);
    }
    renderGithubDownloads();
  } finally {
    if (els.openGithubDownloads && githubDownloadsInfo?.configured) {
      els.openGithubDownloads.disabled = false;
    }
  }
}

const updateProductIds = ["console", "world"];

function updateProductName(product) {
  return product === "world" ? "Codex World" : "Codex Console";
}

function updateProductEndpoint(product) {
  return product === "world" ? "/api/world/update" : "/api/console/update";
}

function selectedProductUpdateState() {
  return productUpdateStates[selectedUpdateProduct] || {};
}

function selectUpdateProduct(product, options = {}) {
  selectedUpdateProduct = product === "world" ? "world" : "console";
  if (options.persist !== false) {
    localStorage.setItem(storageKeys.updateProduct, selectedUpdateProduct);
  }
  renderConsoleUpdate();
}

function renderUpdateProductButton(product, button, badge) {
  if (!button || !badge) return;
  const state = productUpdateStates[product] || {};
  const latest = String(state.latestVersion || "").replace(/^v/i, "");
  const current = String(state.currentVersion || "").replace(/^v/i, "");
  const version = state.available ? latest : current || latest;
  const selected = selectedUpdateProduct === product;
  button.classList.toggle("primary-action", selected);
  button.setAttribute("aria-current", String(selected));
  button.href = state.releaseUrl || (product === "world"
    ? "https://github.com/tx74666/CodexWorldConsole/releases/latest"
    : "https://github.com/tx74666/CodexControlConsole/releases/latest");
  badge.textContent = version ? `v${version}` : "--";
  badge.classList.toggle("available", Boolean(state.available));
}

function availableProductUpdates() {
  return updateProductIds.filter(product => productUpdateStates[product]?.available);
}

function renderConsoleUpdate() {
  if (!els.consoleUpdateStatus) return;
  const state = selectedProductUpdateState();
  const product = selectedUpdateProduct;
  const current = String(state.currentVersion || "").replace(/^v/i, "");
  const latest = String(state.latestVersion || "").replace(/^v/i, "");
  const installed = product !== "world" || state.installed !== false;

  renderUpdateProductButton("console", els.updateProductConsole, els.updateProductConsoleBadge);
  renderUpdateProductButton("world", els.updateProductWorld, els.updateProductWorldBadge);

  if (els.consoleUpdateCurrent) {
    els.consoleUpdateCurrent.textContent = installed && current ? `v${current}` : "--";
  }
  if (els.consoleUpdateStatus) {
    els.consoleUpdateStatus.textContent = state.operationMessage
      ? state.operationMessage
      : productUpdateBusy
      ? text("consoleUpdateChecking")
      : !installed
        ? latest
          ? `${text("consoleUpdateNotInstalled")} / v${latest}`
          : text("consoleUpdateNotInstalled")
        : state.available
          ? text("consoleUpdateAvailable", latest)
          : latest
            ? text("consoleUpdateLatest")
            : text("consoleUpdateNoRelease");
    els.consoleUpdateStatus.title = state.installationMode === "source" ? text("consoleUpdateSource") : "";
  }

  const loadedStates = updateProductIds.map(id => productUpdateStates[id]).filter(Boolean);
  if (els.consoleUpdateAuto) {
    els.consoleUpdateAuto.checked = !loadedStates.some(item => item.autoCheck === false);
    els.consoleUpdateAuto.disabled = productUpdateBusy;
  }
  if (els.consoleUpdateRefresh) {
    els.consoleUpdateRefresh.disabled = productUpdateBusy;
  }
  if (els.consoleUpdateInstall) {
    let action = "";
    if (state.available) {
      action = state.canInstall
        ? installed ? text("consoleUpdateInstall") : text("consoleUpdateInstallProduct")
        : text("consoleUpdateRelease");
    } else if (product === "world" && state.canOpen) {
      action = text("consoleUpdateOpen");
    }
    els.consoleUpdateInstall.hidden = !action;
    els.consoleUpdateInstall.disabled = productUpdateBusy;
    els.consoleUpdateInstall.textContent = action;
  }
  if (els.consoleUninstall) {
    els.consoleUninstall.hidden = !state.canUninstall;
    els.consoleUninstall.disabled = productUpdateBusy;
    els.consoleUninstall.textContent = text("consoleUninstall");
  }
  if (els.consoleUpdateRelease) {
    els.consoleUpdateRelease.href = state.releaseUrl
      || (product === "world"
        ? "https://github.com/tx74666/CodexWorldConsole/releases/latest"
        : "https://github.com/tx74666/CodexControlConsole/releases/latest");
    els.consoleUpdateRelease.hidden = true;
  }

  if (els.consoleUpdateTop) {
    const updates = availableProductUpdates();
    els.consoleUpdateTop.hidden = updates.length === 0;
    els.consoleUpdateTop.disabled = productUpdateBusy;
    els.consoleUpdateTop.dataset.product = updates.length === 1 ? updates[0] : "";
    if (updates.length === 1) {
      const update = productUpdateStates[updates[0]];
      els.consoleUpdateTop.textContent = text(
        "consoleUpdateTop",
        updateProductName(updates[0]),
        String(update.latestVersion || "").replace(/^v/i, "")
      );
    } else {
      els.consoleUpdateTop.textContent = updates.length ? text("consoleUpdateTopCount", updates.length) : "";
    }
    els.consoleUpdateTop.title = updates.map(id => {
      const update = productUpdateStates[id];
      return `${updateProductName(id)} v${String(update.latestVersion || "").replace(/^v/i, "")}`;
    }).join(" / ");
  }
  if (els.consoleUpdateError) {
    const message = String(state.updateError || state.error || "").trim();
    els.consoleUpdateError.textContent = message
      ? state.operation === "uninstall"
        ? text("consoleUninstallFailed", message)
        : text("consoleUpdateFailed", message)
      : "";
    els.consoleUpdateError.hidden = !message;
  }
}

async function fetchProductUpdateStatus(product, options = {}) {
  const params = new URLSearchParams();
  if (options.force) params.set("force", "1");
  else if (options.check) params.set("check", "auto");
  const response = await fetch(`${updateProductEndpoint(product)}${params.size ? `?${params}` : ""}`, {
    cache: "no-store"
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  if (options.quiet && payload.error) payload.error = "";
  return payload;
}

async function loadProductUpdateStatuses(options = {}) {
  if (!els.consoleUpdateStatus || productUpdateBusy) return;
  productUpdateBusy = true;
  renderConsoleUpdate();
  try {
    const results = await Promise.all(updateProductIds.map(async product => {
      try {
        return [product, await fetchProductUpdateStatus(product, options)];
      } catch (error) {
        return [product, {
          ...(productUpdateStates[product] || {}),
          error: options.quiet ? "" : error.message
        }];
      }
    }));
    results.forEach(([product, state]) => {
      productUpdateStates[product] = state;
    });
  } finally {
    productUpdateBusy = false;
    renderConsoleUpdate();
  }
}

async function saveProductUpdatePreference() {
  if (!els.consoleUpdateAuto || productUpdateBusy) return;
  productUpdateBusy = true;
  renderConsoleUpdate();
  const autoCheck = els.consoleUpdateAuto.checked;
  try {
    const results = await Promise.all(updateProductIds.map(async product => {
      const state = await postJson(`${updateProductEndpoint(product)}/config`, { autoCheck });
      return [product, state];
    }));
    results.forEach(([product, state]) => {
      productUpdateStates[product] = state;
    });
  } catch (error) {
    productUpdateStates[selectedUpdateProduct] = {
      ...selectedProductUpdateState(),
      error: error.message
    };
  } finally {
    productUpdateBusy = false;
    renderConsoleUpdate();
  }
}

async function installSelectedProductUpdate(product = selectedUpdateProduct) {
  if (productUpdateBusy) return;
  selectUpdateProduct(product);
  const state = productUpdateStates[product] || {};

  if (!state.available) {
    if (product === "world" && state.canOpen) {
      try {
        await postJson("/api/world/update/open", {});
      } catch (error) {
        productUpdateStates.world = { ...state, error: error.message };
        renderConsoleUpdate();
      }
    }
    return;
  }
  if (!state.canInstall) {
    window.open(state.releaseUrl, "_blank", "noopener,noreferrer");
    return;
  }

  const confirmed = product === "world"
    ? window.confirm(text("worldUpdateConfirm", state.latestVersion, state.installed !== false))
    : window.confirm(text("consoleUpdateConfirm", state.latestVersion));
  if (!confirmed) return;

  productUpdateBusy = true;
  if (els.consoleUpdateStatus) els.consoleUpdateStatus.textContent = text("consoleUpdateInstalling");
  if (els.consoleUpdateError) els.consoleUpdateError.hidden = true;
  try {
    const payload = await postJson(`${updateProductEndpoint(product)}/install`, {});
    productUpdateStates[product] = payload;
    if (product === "console" && payload.restarting) {
      if (els.consoleUpdateStatus) els.consoleUpdateStatus.textContent = text("consoleUpdateRestarting");
      return;
    }
  } catch (error) {
    productUpdateStates[product] = { ...state, error: error.message };
  }
  productUpdateBusy = false;
  renderConsoleUpdate();
}

async function uninstallSelectedProduct(product = selectedUpdateProduct) {
  if (productUpdateBusy) return;
  selectUpdateProduct(product);
  const state = productUpdateStates[product] || {};
  if (!state.canUninstall || !window.confirm(text("consoleUninstallConfirm", updateProductName(product)))) return;

  productUpdateBusy = true;
  renderConsoleUpdate();
  try {
    await postJson(`/api/${product}/uninstall`, {});
    productUpdateStates[product] = { ...state, operationMessage: text("consoleUninstalling"), error: "" };
    productUpdateBusy = false;
    renderConsoleUpdate();
  } catch (error) {
    productUpdateStates[product] = { ...state, operation: "uninstall", error: error.message };
    productUpdateBusy = false;
    renderConsoleUpdate();
  }
}

async function handleProductUpdateTop() {
  const updates = availableProductUpdates();
  if (!updates.length) return;
  if (updates.length === 1) {
    await installSelectedProductUpdate(updates[0]);
    return;
  }
  selectUpdateProduct(updates[0]);
  activateModule("workspace", true);
}

function selectedDesktopLayoutPlan() {
  const plans = Array.isArray(desktopLayoutState?.plans) ? desktopLayoutState.plans : [];
  const selectedId = els.desktopLayoutPlan?.value || desktopLayoutState?.selectedPlan || "";
  return plans.find(plan => plan.id === selectedId) || plans.find(plan => plan.selected) || plans[0] || null;
}

function desktopLayoutPlanName(plan) {
  if (plan?.source === "remembered") return text("desktopLayoutRememberedPlan");
  if (plan?.source === "device") return text("desktopLayoutDevicePlan");
  return plan?.name || "";
}

function renderDesktopLayout() {
  if (!els.desktopLayoutPlan) return;
  const plans = Array.isArray(desktopLayoutState?.plans) ? desktopLayoutState.plans : [];
  const selectedId = desktopLayoutState?.selectedPlan || plans.find(plan => plan.selected)?.id || "";
  const currentIds = Array.from(els.desktopLayoutPlan.options).map(option => option.value).join("\n");
  const nextIds = plans.map(plan => plan.id).join("\n");
  if (currentIds !== nextIds) {
    els.desktopLayoutPlan.replaceChildren(...plans.map(plan => {
      const option = document.createElement("option");
      option.value = plan.id;
      option.textContent = desktopLayoutPlanName(plan);
      return option;
    }));
  } else {
    Array.from(els.desktopLayoutPlan.options).forEach((option, index) => {
      if (plans[index]) option.textContent = desktopLayoutPlanName(plans[index]);
    });
  }
  if (selectedId && plans.some(plan => plan.id === selectedId)) {
    els.desktopLayoutPlan.value = selectedId;
  }

  const selected = selectedDesktopLayoutPlan();
  const toolAvailable = desktopLayoutState?.tool?.available !== false;
  const canRestore = Boolean(selected?.exists && selected?.valid && toolAvailable && !desktopLayoutBusy);
  const canSave = Boolean(selected && toolAvailable && !desktopLayoutBusy);
  els.desktopLayoutPlan.disabled = desktopLayoutBusy || !plans.length;
  if (els.desktopLayoutRestore) els.desktopLayoutRestore.disabled = !canRestore;
  if (els.desktopLayoutSave) els.desktopLayoutSave.disabled = !canSave;
  if (els.desktopLayoutImport) els.desktopLayoutImport.disabled = desktopLayoutBusy;

  if (els.desktopLayoutMeta) {
    els.desktopLayoutMeta.textContent = selected
      ? text("desktopLayoutMeta", selected.iconCount || 0, plans.length)
      : text("desktopLayoutEmpty");
  }
  if (els.desktopLayoutPath) {
    els.desktopLayoutPath.textContent = desktopLayoutDetail || selected?.path || desktopLayoutState?.dataDirectory || "";
    els.desktopLayoutPath.title = els.desktopLayoutPath.textContent;
  }
  if (els.desktopLayoutStatus) {
    let status = desktopLayoutNotice;
    let tone = desktopLayoutNoticeTone;
    if (!status) {
      if (!toolAvailable) {
        status = text("desktopLayoutToolMissing");
        tone = "warning";
      } else if (selected && !selected.exists) {
        status = text("desktopLayoutNotSaved");
      } else if (selected && !selected.valid) {
        status = text("desktopLayoutInvalid");
        tone = "warning";
      } else if (selected) {
        status = text("desktopLayoutReady");
        tone = "success";
      }
    }
    els.desktopLayoutStatus.textContent = status;
    els.desktopLayoutStatus.classList.toggle("success", tone === "success");
    els.desktopLayoutStatus.classList.toggle("warning", tone === "warning");
  }
}

async function loadDesktopLayout(options = {}) {
  if (!els.desktopLayoutPlan || desktopLayoutBusy) return;
  desktopLayoutBusy = true;
  if (!options.quiet) {
    desktopLayoutNotice = text("desktopLayoutLoading");
    desktopLayoutNoticeTone = "";
  }
  renderDesktopLayout();
  try {
    const response = await fetch("/api/console/desktop-layout", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    desktopLayoutState = payload;
    desktopLayoutNotice = "";
    desktopLayoutNoticeTone = "";
  } catch (error) {
    desktopLayoutNotice = text("desktopLayoutFailed", error.message);
    desktopLayoutNoticeTone = "warning";
  } finally {
    desktopLayoutBusy = false;
    renderDesktopLayout();
  }
}

async function selectDesktopLayoutPlan() {
  if (!els.desktopLayoutPlan || desktopLayoutBusy) return;
  desktopLayoutBusy = true;
  desktopLayoutNotice = "";
  renderDesktopLayout();
  try {
    desktopLayoutState = await postJson("/api/console/desktop-layout/select", {
      planId: els.desktopLayoutPlan.value
    });
    desktopLayoutDetail = "";
  } catch (error) {
    desktopLayoutNotice = text("desktopLayoutFailed", error.message);
    desktopLayoutNoticeTone = "warning";
  } finally {
    desktopLayoutBusy = false;
    renderDesktopLayout();
  }
}

async function restoreDesktopLayout() {
  const plan = selectedDesktopLayoutPlan();
  if (!plan || desktopLayoutBusy) return;
  if (!window.confirm(text("desktopLayoutConfirmRestore", desktopLayoutPlanName(plan)))) return;
  desktopLayoutBusy = true;
  desktopLayoutNotice = text("desktopLayoutRestoring");
  desktopLayoutNoticeTone = "";
  desktopLayoutDetail = plan.path;
  renderDesktopLayout();
  try {
    desktopLayoutState = await postJson("/api/console/desktop-layout/restore", {
      planId: plan.id
    }, { timeoutMs: 180000 });
    const verification = desktopLayoutState.verification || {};
    if (verification.healthy) {
      desktopLayoutNotice = text("desktopLayoutRestored");
      desktopLayoutNoticeTone = "success";
    } else {
      desktopLayoutNotice = text(
        "desktopLayoutRestoreIssues",
        verification.missing?.length || 0,
        verification.mismatches?.length || 0,
        verification.overlaps?.length || 0
      );
      desktopLayoutNoticeTone = "warning";
    }
    desktopLayoutDetail = verification.snapshot || plan.path;
  } catch (error) {
    desktopLayoutNotice = text("desktopLayoutFailed", error.message);
    desktopLayoutNoticeTone = "warning";
  } finally {
    desktopLayoutBusy = false;
    renderDesktopLayout();
  }
}

async function saveDesktopLayout() {
  const plan = selectedDesktopLayoutPlan();
  if (!plan || desktopLayoutBusy) return;
  if (!window.confirm(text("desktopLayoutConfirmSave", desktopLayoutPlanName(plan)))) return;
  desktopLayoutBusy = true;
  desktopLayoutNotice = text("desktopLayoutSaving");
  desktopLayoutNoticeTone = "";
  desktopLayoutDetail = plan.path;
  renderDesktopLayout();
  try {
    desktopLayoutState = await postJson("/api/console/desktop-layout/save", {
      planId: plan.id
    }, { timeoutMs: 180000 });
    desktopLayoutNotice = text("desktopLayoutSaved");
    desktopLayoutNoticeTone = "success";
    desktopLayoutDetail = desktopLayoutState.backup || desktopLayoutState.saved || plan.path;
  } catch (error) {
    desktopLayoutNotice = text("desktopLayoutFailed", error.message);
    desktopLayoutNoticeTone = "warning";
  } finally {
    desktopLayoutBusy = false;
    renderDesktopLayout();
  }
}

async function importDesktopLayouts(files) {
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length || desktopLayoutBusy) return;
  desktopLayoutBusy = true;
  desktopLayoutNotice = text("desktopLayoutImporting");
  desktopLayoutNoticeTone = "";
  renderDesktopLayout();
  try {
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append("files", file, file.name));
    const response = await fetch("/api/console/desktop-layout/import", {
      method: "POST",
      body: formData
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    desktopLayoutState = payload;
    desktopLayoutNotice = text("desktopLayoutImported", payload.imported?.length || 0);
    desktopLayoutNoticeTone = "success";
    desktopLayoutDetail = payload.plans?.find(plan => plan.id === payload.selectedPlan)?.path || "";
  } catch (error) {
    desktopLayoutNotice = text("desktopLayoutFailed", error.message);
    desktopLayoutNoticeTone = "warning";
  } finally {
    desktopLayoutBusy = false;
    if (els.desktopLayoutFileInput) els.desktopLayoutFileInput.value = "";
    renderDesktopLayout();
  }
}

function feedbackCategoryLabel(category) {
  const key = {
    bug: "feedbackCategoryBug",
    layout: "feedbackCategoryLayout",
    music: "feedbackCategoryMusic",
    update: "feedbackCategoryUpdate",
    other: "feedbackCategoryOther"
  }[category] || "feedbackCategoryOther";
  return text(key);
}

function renderFeedbackTop() {
  if (!els.feedbackTop) return;
  els.feedbackTop.textContent = feedbackNewCount > 0
    ? `${text("feedbackTop")} ${feedbackNewCount}`
    : text("feedbackTop");
  els.feedbackTop.classList.toggle("has-reports", feedbackNewCount > 0);
}

function renderFeedback() {
  if (!els.feedbackForm) return;
  const configured = Boolean(feedbackConfig?.configured);
  const dailyLimit = Number(feedbackConfig?.dailyLimit || 10);
  if (els.feedbackQuota) els.feedbackQuota.textContent = text("feedbackQuota", dailyLimit);
  if (els.feedbackSubmit) els.feedbackSubmit.disabled = feedbackBusy || !configured;
  if (els.feedbackScreenshotButton) els.feedbackScreenshotButton.disabled = feedbackBusy;
  if (els.feedbackDescription) els.feedbackDescription.disabled = feedbackBusy;
  if (els.feedbackCategory) els.feedbackCategory.disabled = feedbackBusy;
  if (els.feedbackScreenshotName) els.feedbackScreenshotName.textContent = feedbackImage?.name || "";
  if (els.feedbackPreview) els.feedbackPreview.hidden = !feedbackImage;
  if (els.feedbackPreviewImage) {
    els.feedbackPreviewImage.src = feedbackImageUrl || "";
    els.feedbackPreviewImage.alt = feedbackImage?.name || "";
  }

  if (els.feedbackStatus) {
    const status = feedbackNotice || (feedbackConfig
      ? configured ? text("feedbackReady") : text("feedbackNotConfigured")
      : text("feedbackConnecting"));
    els.feedbackStatus.textContent = status;
    els.feedbackStatus.classList.toggle("success", feedbackNoticeTone === "success");
    els.feedbackStatus.classList.toggle("warning", feedbackNoticeTone === "warning" || (feedbackConfig && !configured));
  }

  if (els.feedbackReviewPanel) {
    els.feedbackReviewPanel.hidden = !(feedbackConfig?.adminSetupAvailable || feedbackConfig?.adminEnabled);
  }
  if (els.feedbackAdminSetup) {
    els.feedbackAdminSetup.hidden = !feedbackConfig?.adminSetupAvailable;
  }
  if (els.feedbackAdminEndpoint && document.activeElement !== els.feedbackAdminEndpoint) {
    els.feedbackAdminEndpoint.value = feedbackConfig?.endpoint || els.feedbackAdminEndpoint.value || "";
  }
  if (els.feedbackInbox) els.feedbackInbox.hidden = !feedbackConfig?.adminEnabled;
  renderFeedbackInbox();
  renderFeedbackTop();
}

function clearFeedbackImage() {
  if (feedbackImageUrl) URL.revokeObjectURL(feedbackImageUrl);
  feedbackImage = null;
  feedbackImageUrl = "";
  if (els.feedbackScreenshotInput) els.feedbackScreenshotInput.value = "";
  renderFeedback();
}

function selectFeedbackImage(file) {
  if (!file) return;
  const maximum = Number(feedbackConfig?.maxImageBytes || 5 * 1024 * 1024);
  if (file.size > maximum) {
    feedbackNotice = text("feedbackImageTooLarge");
    feedbackNoticeTone = "warning";
    renderFeedback();
    return;
  }
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    feedbackNotice = text("feedbackImageType");
    feedbackNoticeTone = "warning";
    renderFeedback();
    return;
  }
  if (feedbackImageUrl) URL.revokeObjectURL(feedbackImageUrl);
  feedbackImage = file;
  feedbackImageUrl = URL.createObjectURL(file);
  feedbackNotice = "";
  feedbackNoticeTone = "";
  renderFeedback();
}

function readFeedbackImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")), { once: true });
    reader.addEventListener("error", () => reject(new Error(text("feedbackImageReadFailed"))), { once: true });
    reader.readAsDataURL(file);
  });
}

function loadTurnstileLibrary() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (feedbackTurnstileLoading) return feedbackTurnstileLoading;
  feedbackTurnstileLoading = new Promise((resolve, reject) => {
    const existing = document.getElementById("codexFeedbackTurnstileScript");
    const script = existing || document.createElement("script");
    const finish = () => window.turnstile ? resolve(window.turnstile) : reject(new Error("Turnstile unavailable"));
    script.addEventListener("load", finish, { once: true });
    script.addEventListener("error", () => reject(new Error("Turnstile unavailable")), { once: true });
    if (!existing) {
      script.id = "codexFeedbackTurnstileScript";
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  }).catch(error => {
    feedbackTurnstileLoading = null;
    throw error;
  });
  return feedbackTurnstileLoading;
}

async function renderFeedbackTurnstile() {
  if (!els.feedbackTurnstile) return;
  const siteKey = feedbackConfig?.siteKey || "";
  els.feedbackTurnstile.hidden = !siteKey;
  if (!siteKey || feedbackTurnstileWidgetId !== null) return;
  try {
    const turnstile = await loadTurnstileLibrary();
    feedbackTurnstileWidgetId = turnstile.render(els.feedbackTurnstile, {
      sitekey: siteKey,
      theme: theme === "dark" ? "dark" : "light",
      size: "flexible"
    });
  } catch {
    feedbackNotice = text("feedbackFailed", "verification unavailable");
    feedbackNoticeTone = "warning";
    renderFeedback();
  }
}

function resetFeedbackTurnstile() {
  if (feedbackTurnstileWidgetId === null || !window.turnstile) return;
  window.turnstile.reset(feedbackTurnstileWidgetId);
}

async function loadFeedbackConfig(options = {}) {
  if (!els.feedbackForm || feedbackConfigBusy) return;
  feedbackConfigBusy = true;
  if (!options.quiet) {
    feedbackNotice = text("feedbackConnecting");
    feedbackNoticeTone = "";
  }
  renderFeedback();
  try {
    const response = await fetch(`/api/feedback/config${options.force ? "?force=1" : ""}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    feedbackConfig = payload;
    feedbackNotice = "";
    feedbackNoticeTone = "";
    renderFeedback();
    await renderFeedbackTurnstile();
    if (feedbackConfig.adminEnabled) await loadFeedbackInbox({ quiet: true });
  } catch (error) {
    feedbackConfig = { configured: false, adminEnabled: false, dailyLimit: 10, maxImageBytes: 5 * 1024 * 1024 };
    feedbackNotice = text("feedbackFailed", error.message);
    feedbackNoticeTone = "warning";
    renderFeedback();
  } finally {
    feedbackConfigBusy = false;
  }
}

async function submitFeedback(event) {
  event?.preventDefault();
  if (!feedbackConfig?.configured || feedbackBusy) return;
  const description = String(els.feedbackDescription?.value || "").trim();
  if (description.length < 10) {
    feedbackNotice = text("feedbackDescriptionShort");
    feedbackNoticeTone = "warning";
    renderFeedback();
    els.feedbackDescription?.focus();
    return;
  }

  feedbackBusy = true;
  feedbackNotice = text("feedbackSending");
  feedbackNoticeTone = "";
  renderFeedback();
  try {
    const screenshot = feedbackImage ? {
      data: await readFeedbackImage(feedbackImage),
      type: feedbackImage.type,
      name: feedbackImage.name
    } : null;
    const turnstileToken = feedbackTurnstileWidgetId !== null && window.turnstile
      ? window.turnstile.getResponse(feedbackTurnstileWidgetId)
      : "";
    const response = await fetch("/api/feedback/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: els.feedbackCategory?.value || "bug",
        description,
        screenshot,
        turnstileToken,
        locale: language,
        module: activeModuleId
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    if (els.feedbackDescription) els.feedbackDescription.value = "";
    clearFeedbackImage();
    resetFeedbackTurnstile();
    feedbackNotice = text("feedbackSent", Number(payload.remaining || 0));
    feedbackNoticeTone = "success";
    if (feedbackConfig.adminEnabled) window.setTimeout(() => loadFeedbackInbox({ quiet: true }), 600);
  } catch (error) {
    feedbackNotice = text("feedbackFailed", error.message);
    feedbackNoticeTone = "warning";
    resetFeedbackTurnstile();
  } finally {
    feedbackBusy = false;
    renderFeedback();
  }
}

function feedbackDate(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "--";
  return new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function renderFeedbackInbox() {
  if (!els.feedbackInboxList) return;
  els.feedbackInboxList.replaceChildren();
  if (els.feedbackInboxCount) els.feedbackInboxCount.textContent = String(feedbackNewCount || 0);
  if (els.feedbackInboxRefresh) els.feedbackInboxRefresh.disabled = feedbackInboxBusy;
  if (!feedbackConfig?.adminEnabled) return;
  if (!feedbackReports.length) {
    const empty = document.createElement("p");
    empty.className = "feedback-inbox-empty";
    empty.textContent = text("feedbackInboxEmpty");
    els.feedbackInboxList.appendChild(empty);
    return;
  }

  for (const report of feedbackReports) {
    const row = document.createElement("article");
    row.className = "feedback-report";
    const body = document.createElement("div");
    body.className = "feedback-report-body";
    const meta = document.createElement("span");
    meta.className = "feedback-report-meta";
    meta.textContent = text(
      "feedbackInboxMeta",
      feedbackCategoryLabel(report.category),
      report.appVersion ? `v${String(report.appVersion).replace(/^v/i, "")}` : "",
      feedbackDate(report.createdAt)
    );
    const description = document.createElement("p");
    description.textContent = report.description || "";
    body.append(meta, description);
    if (report.hasImage) {
      const imageLink = document.createElement("a");
      imageLink.className = "ghost-button feedback-report-image";
      imageLink.href = `/api/feedback/image/${encodeURIComponent(report.id)}`;
      imageLink.target = "_blank";
      imageLink.rel = "noreferrer";
      imageLink.textContent = text("feedbackOpenImage");
      row.appendChild(imageLink);
    }
    const resolve = document.createElement("button");
    resolve.className = "ghost-button feedback-resolve";
    resolve.type = "button";
    resolve.textContent = report.status === "resolved" ? text("feedbackInboxResolved") : text("feedbackInboxResolve");
    resolve.disabled = report.status === "resolved";
    resolve.addEventListener("click", () => resolveFeedbackReport(report.id));
    row.append(body, resolve);
    els.feedbackInboxList.appendChild(row);
  }
}

function stopFeedbackInboxPolling() {
  if (feedbackInboxTimer) window.clearTimeout(feedbackInboxTimer);
  feedbackInboxTimer = 0;
}

function scheduleFeedbackInboxPolling(delay = 30000) {
  stopFeedbackInboxPolling();
  if (!feedbackConfig?.adminEnabled || !isModuleForeground("workspace")) return;
  feedbackInboxTimer = window.setTimeout(() => loadFeedbackInbox({ quiet: true }), delay);
}

async function loadFeedbackInbox(options = {}) {
  if (!feedbackConfig?.adminEnabled || feedbackInboxBusy) return;
  feedbackInboxBusy = true;
  renderFeedbackInbox();
  try {
    const response = await fetch("/api/feedback/inbox?status=new&limit=50", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    feedbackReports = Array.isArray(payload.reports) ? payload.reports : [];
    feedbackNewCount = Number(payload.newCount || feedbackReports.length || 0);
  } catch (error) {
    if (!options.quiet) {
      feedbackNotice = text("feedbackFailed", error.message);
      feedbackNoticeTone = "warning";
    }
  } finally {
    feedbackInboxBusy = false;
    renderFeedback();
    scheduleFeedbackInboxPolling();
  }
}

async function resolveFeedbackReport(id) {
  try {
    const response = await fetch("/api/feedback/admin/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, status: "resolved" })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    feedbackReports = feedbackReports.filter(report => report.id !== id);
    feedbackNewCount = Math.max(0, feedbackNewCount - 1);
    renderFeedback();
  } catch (error) {
    feedbackNotice = text("feedbackFailed", error.message);
    feedbackNoticeTone = "warning";
    renderFeedback();
  }
}

async function saveFeedbackAdminConfig(event) {
  event?.preventDefault();
  try {
    const response = await fetch("/api/feedback/admin/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        endpoint: els.feedbackAdminEndpoint?.value || "",
        token: els.feedbackAdminToken?.value || ""
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    feedbackConfig = payload;
    if (els.feedbackAdminToken) els.feedbackAdminToken.value = "";
    feedbackNotice = text("feedbackAdminSaved");
    feedbackNoticeTone = "success";
    renderFeedback();
    await renderFeedbackTurnstile();
    if (feedbackConfig.adminEnabled) await loadFeedbackInbox();
  } catch (error) {
    feedbackNotice = text("feedbackFailed", error.message);
    feedbackNoticeTone = "warning";
    renderFeedback();
  }
}

function openFeedbackPanel() {
  activateModule("workspace", true, { allowArchived: true });
  setConsoleWorkspaceView("collaboration");
  window.requestAnimationFrame(() => {
    els.feedbackPanel?.scrollIntoView({
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "auto" : "smooth",
      block: "start"
    });
    window.setTimeout(() => els.feedbackDescription?.focus({ preventScroll: true }), 260);
  });
}

function parseLegacyCustomResolution(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return { width: "", length: "" };
  const kMatch = raw.match(/^(\d+(?:\.\d+)?)\s*k$/);
  if (kMatch) {
    const pixels = String(Math.round(Number(kMatch[1]) * 1024));
    return { width: pixels, length: pixels };
  }
  const numbers = raw.match(/\d+(?:\.\d+)?/g) || [];
  if (numbers.length >= 2) {
    return { width: String(Math.round(Number(numbers[0]))), length: String(Math.round(Number(numbers[1]))) };
  }
  if (numbers.length === 1) {
    const pixels = String(Math.round(Number(numbers[0])));
    return { width: pixels, length: pixels };
  }
  return { width: "", length: "" };
}

function normalizeResolutionPart(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const number = Math.round(Number(raw));
  return Number.isFinite(number) && number > 0 ? String(number) : "";
}

function normalizeBlenderPromptConfig(value) {
  const source = value && typeof value === "object" ? value : {};
  const resolution = ["1k", "2k", "custom"].includes(source.resolution) ? source.resolution : defaultBlenderPromptConfig.resolution;
  const legacy = parseLegacyCustomResolution(source.customResolution);
  const customWidth = normalizeResolutionPart(source.customWidth) || legacy.width;
  const customLength = normalizeResolutionPart(source.customLength) || legacy.length;
  return {
    format: typeof source.format === "string" ? source.format : defaultBlenderPromptConfig.format,
    image: typeof source.image === "string" ? source.image : defaultBlenderPromptConfig.image,
    style: typeof source.style === "string" ? source.style : defaultBlenderPromptConfig.style,
    basics: typeof source.basics === "string" ? source.basics : defaultBlenderPromptConfig.basics,
    resolution,
    customResolution: customWidth && customLength ? `${customWidth}x${customLength}` : "",
    customWidth,
    customLength
  };
}

function loadBlenderPromptConfig() {
  try {
    const raw = localStorage.getItem(storageKeys.blenderPromptConfig);
    return raw ? normalizeBlenderPromptConfig(JSON.parse(raw)) : normalizeBlenderPromptConfig(defaultBlenderPromptConfig);
  } catch {
    return normalizeBlenderPromptConfig(defaultBlenderPromptConfig);
  }
}

function saveBlenderPromptConfig() {
  localStorage.setItem(storageKeys.blenderPromptConfig, JSON.stringify(blenderPromptConfig));
}

function loadRandomRealmArtContext() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKeys.randomRealmArtContext) || "{}");
    return {
      type: typeof value.type === "string" ? value.type : defaultRandomRealmArtTypes[0],
      project: typeof value.project === "string" ? value.project : "",
      object: typeof value.object === "string" ? value.object : ""
    };
  } catch {
    return { type: defaultRandomRealmArtTypes[0], project: "", object: "" };
  }
}

function saveRandomRealmArtContext() {
  localStorage.setItem(storageKeys.randomRealmArtContext, JSON.stringify(randomRealmArtContext));
}

function renderRandomRealmArtContext() {
  renderRandomRealmArtTypes();
}

function updateRandomRealmArtContext() {
  randomRealmArtContext = {
    type: els.randomRealmArtType?.value || randomRealmArtContext.type || defaultRandomRealmArtTypes[0],
    project: els.randomRealmBlenderProject?.value || randomRealmArtContext.project || "",
    object: els.randomRealmBlenderObject?.value || randomRealmArtContext.object || ""
  };
  saveRandomRealmArtContext();
  updateBlenderPromptOutput();
}

function hasBlenderGithubShare() {
  return Boolean(els.blenderGithubSharePanel && els.blenderGithubProject);
}

function blenderGithubCheckedValue(name, fallback = "") {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || fallback;
}

function setBlenderGithubCheckedValue(name, value) {
  for (const input of document.querySelectorAll(`input[name="${name}"]`)) {
    input.checked = input.value === value;
  }
}

function blenderGithubLines(value) {
  return String(value || "")
    .replace(/\r/g, "")
    .split("\n")
    .map(item => item.trim())
    .filter(Boolean);
}

function blenderGithubRepositorySlug(value) {
  const raw = String(value || "").trim().replace(/\.git\/?$/i, "").replace(/\/$/, "");
  const match = raw.match(/github\.com(?::|\/)([^/\s:]+)\/([^/\s]+)$/i);
  return match ? `${match[1]}/${match[2]}`.toLocaleLowerCase() : "";
}

function blenderGithubStateLabel(state) {
  const keys = {
    cloud: "blenderGithubStateCloud",
    uninitialized: "blenderGithubStateUninitialized",
    initialized: "blenderGithubStateInitialized",
    dirty: "blenderGithubStateDirty",
    committed: "blenderGithubStateCommitted",
    pendingPush: "blenderGithubStatePendingPush",
    behind: "blenderGithubStateBehind",
    synced: "blenderGithubStateSynced",
    gitUnavailable: "blenderGithubStateGitUnavailable"
  };
  return text(keys[state] || "blenderGithubReady");
}

function blenderGithubFormPayload(extra = {}) {
  return {
    project: els.blenderGithubProject?.value || blenderGithubShareState?.project?.path || randomRealmArtContext.project || "",
    repositoryUrl: els.blenderGithubRepository?.value.trim() || "",
    visibility: blenderGithubCheckedValue("blenderGithubVisibility", "private"),
    scope: blenderGithubCheckedValue("blenderGithubScope", "current"),
    includePatterns: blenderGithubLines(els.blenderGithubIncludes?.value),
    excludePatterns: blenderGithubLines(els.blenderGithubExcludes?.value),
    version: els.blenderGithubVersion?.value.trim() || "v0.1.0",
    message: els.blenderGithubMessage?.value.trim() || "",
    confirmPublic: blenderGithubPublicConfirmed,
    ...extra
  };
}

function setBlenderGithubStatus(message) {
  if (els.blenderGithubStatus) {
    const value = String(message || "").trim();
    const passive = !value
      || value === text("blenderGithubReady")
      || value === text("blenderGithubLoading");
    els.blenderGithubStatus.textContent = passive ? "" : value;
    els.blenderGithubStatus.hidden = passive;
  }
}

function renderBlenderGithubProjectOptions(selectedPath = "") {
  if (!els.blenderGithubProject) return;
  const grouped = Array.isArray(blenderGithubShareState?.collection?.projects)
    ? blenderGithubShareState.collection.projects.filter(project => project?.repositoryUrl || project?.path)
    : [];

  els.blenderGithubProject.innerHTML = "";
  if (!grouped.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = text("blenderGithubSelectProject");
    els.blenderGithubProject.appendChild(option);
    return;
  }
  for (const project of grouped) {
    const option = document.createElement("option");
    option.value = project.repositoryUrl || project.path;
    option.textContent = project.name || blenderGithubRepositorySlug(project.repositoryUrl) || project.path;
    option.title = project.downloaded ? project.directory : project.repositoryUrl;
    els.blenderGithubProject.appendChild(option);
  }
  const currentProject = blenderGithubShareState?.project || {};
  const preferred = selectedPath || currentProject.repositoryUrl || currentProject.path || grouped[0].repositoryUrl || grouped[0].path;
  const preferredSlug = blenderGithubRepositorySlug(preferred);
  const selectedGroup = grouped.find(project => preferredSlug && blenderGithubRepositorySlug(project.repositoryUrl) === preferredSlug)
    || grouped.find(project => project.path === preferred)
    || grouped[0];
  els.blenderGithubProject.value = selectedGroup.repositoryUrl || selectedGroup.path;
}

function blenderGithubVersionText(value) {
  const version = String(value || "").trim().replace(/^v/i, "");
  return version ? `V${version}` : "V--";
}

function clearBlenderGithubCardClick() {
  if (blenderGithubCardClickTimer) {
    window.clearTimeout(blenderGithubCardClickTimer);
    blenderGithubCardClickTimer = null;
  }
}

function renderBlenderGithubBlendCards(state) {
  if (!els.blenderGithubBlendCards) return;
  const project = state?.project || {};
  const selectedRepositoryKey = blenderGithubRepositorySlug(project.repositoryUrl || state?.git?.repositoryWebUrl || state?.config?.repositoryUrl);
  const selectedDirectoryKey = String(project.directory || "").replace(/\\/g, "/").toLocaleLowerCase();
  const repositories = Array.isArray(state?.collection?.projects) ? state.collection.projects : [];

  els.blenderGithubBlendCards.innerHTML = "";
  if (!repositories.length) {
    const empty = document.createElement("div");
    empty.className = "blender-github-empty";
    empty.textContent = text("blenderGithubNoBlendFiles");
    els.blenderGithubBlendCards.appendChild(empty);
    return;
  }

  for (const repository of repositories) {
    const path = String(repository.path || "");
    const repositoryUrl = String(repository.repositoryUrl || "");
    const identifier = repositoryUrl || path;
    const downloaded = repository.downloaded !== false && Boolean(path && repository.directory);
    const label = repository.name || path.split(/[\\/]/).pop()?.replace(/\.blend$/i, "") || path;
    const directoryKey = String(repository.directory || "").replace(/\\/g, "/").toLocaleLowerCase();
    const repositoryKey = blenderGithubRepositorySlug(repositoryUrl);
    const active = Boolean(
      (selectedRepositoryKey && repositoryKey === selectedRepositoryKey)
      || (selectedDirectoryKey && directoryKey === selectedDirectoryKey)
    );
    const card = document.createElement("button");
    card.className = "blender-github-blend-card";
    card.classList.toggle("cloud", !downloaded);
    card.type = "button";
    card.draggable = true;
    card.dataset.projectPath = identifier;
    card.dataset.localPath = path;
    card.dataset.repositoryUrl = repositoryUrl;
    card.dataset.downloaded = String(downloaded);
    card.setAttribute("role", "option");
    card.setAttribute("aria-selected", String(active));
    card.title = `${text(downloaded ? "blenderGithubCardLocalTitle" : "blenderGithubCardCloudTitle", label)}\n${repositoryUrl || path}`;

    const mark = document.createElement("span");
    mark.className = "blender-github-file-mark";
    mark.textContent = "GH";
    const copy = document.createElement("span");
    copy.className = "blender-github-file-copy";
    const name = document.createElement("strong");
    name.textContent = label;
    name.title = repositoryUrl || label;
    copy.appendChild(name);
    if (!downloaded) {
      const location = document.createElement("small");
      location.textContent = text("blenderGithubCloud");
      copy.appendChild(location);
    }
    const versionBadge = document.createElement("span");
    versionBadge.className = "blender-github-version";
    versionBadge.textContent = blenderGithubVersionText(repository.version);
    card.append(mark, copy, versionBadge);
    card.addEventListener("click", () => {
      if (blenderGithubDraggedPath || blenderGithubBusy) return;
      clearBlenderGithubCardClick();
      blenderGithubCardClickTimer = window.setTimeout(() => {
        blenderGithubCardClickTimer = null;
        if (active || blenderGithubBusy) return;
        syncBlenderGithubProjectContext(path);
        loadBlenderGithubShare({ project: identifier });
      }, 220);
    });
    card.addEventListener("dblclick", event => {
      event.preventDefault();
      clearBlenderGithubCardClick();
      openBlenderGithubTarget("desktop", identifier, repositoryUrl);
    });
    els.blenderGithubBlendCards.appendChild(card);
  }
}

function blenderGithubCardOrderFromDom() {
  return Array.from(els.blenderGithubBlendCards?.querySelectorAll(".blender-github-blend-card") || [])
    .map(card => card.dataset.projectPath || "")
    .filter(Boolean);
}

async function saveBlenderGithubCardOrder() {
  if (!blenderGithubShareState) return;
  const order = blenderGithubCardOrderFromDom();
  if (!order.length) return;
  try {
    const payload = await postJson("/api/randomrealm/blender/github-share/order", {
      project: blenderGithubShareState.project?.path || els.blenderGithubProject?.value || "",
      order
    });
    renderBlenderGithubShare(payload, { preserveForm: true });
    setBlenderGithubStatus("");
  } catch (error) {
    renderBlenderGithubBlendCards(blenderGithubShareState);
    setBlenderGithubStatus(text("blenderGithubOrderFailed", error.message));
  }
}

function syncBlenderGithubProjectContext(projectPath) {
  if (!projectPath || blenderGithubRepositorySlug(projectPath)) return;
  if (randomRealmArtContext.project !== projectPath) {
    randomRealmLoadedObjectsProject = "";
    randomRealmBlenderObjects = [];
  }
  randomRealmArtContext.project = projectPath;
  saveRandomRealmArtContext();
  if (els.randomRealmBlenderProject && Array.from(els.randomRealmBlenderProject.options).some(option => option.value === projectPath)) {
    els.randomRealmBlenderProject.value = projectPath;
    updateRandomRealmProjectAddress();
  }
}

function renderBlenderGithubTools(state) {
  if (!els.blenderGithubToolStatus) return;
  els.blenderGithubToolStatus.innerHTML = "";
  const tools = state?.tools || {};
  const gitStatus = document.createElement("span");
  if (tools.gitAvailable && tools.lfsAvailable) {
    gitStatus.className = "ready";
    gitStatus.textContent = text("blenderGithubToolsReady");
  } else {
    gitStatus.className = "warning";
    gitStatus.textContent = tools.gitAvailable
      ? text("blenderGithubLfsMissing")
      : text("blenderGithubStateGitUnavailable");
  }
  const ghStatus = document.createElement("span");
  ghStatus.className = tools.ghAuthenticated ? "ready" : "warning";
  ghStatus.textContent = tools.ghAuthenticated
    ? text("blenderGithubGhReady")
    : text("blenderGithubGhFallback");
  els.blenderGithubToolStatus.append(gitStatus, ghStatus);
}

function renderBlenderGithubChanges(state) {
  if (!els.blenderGithubChanges) return;
  const changes = Array.isArray(state?.git?.changes) ? state.git.changes : [];
  const count = Number(state?.git?.changedCount || changes.length || 0);
  if (els.blenderGithubChangesCount) {
    els.blenderGithubChangesCount.textContent = String(count);
  }
  els.blenderGithubChanges.innerHTML = "";
  if (!changes.length) {
    const clean = document.createElement("div");
    clean.className = "blender-github-clean";
    clean.textContent = text("blenderGithubWorkingTreeClean");
    els.blenderGithubChanges.appendChild(clean);
    return;
  }
  for (const change of changes.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "blender-github-change";
    const code = document.createElement("code");
    code.textContent = change.code || "??";
    const path = document.createElement("span");
    path.textContent = change.path || "";
    path.title = change.path || "";
    row.append(code, path);
    els.blenderGithubChanges.appendChild(row);
  }
  if (count > 12) {
    const more = document.createElement("div");
    more.className = "blender-github-clean";
    more.textContent = text("blenderGithubMoreChanges", count - 12);
    els.blenderGithubChanges.appendChild(more);
  }
}

function renderBlenderGithubCustomScope() {
  if (els.blenderGithubCustomScope) {
    els.blenderGithubCustomScope.hidden = blenderGithubCheckedValue("blenderGithubScope", "current") !== "custom";
  }
}

function updateBlenderGithubActionState() {
  if (!hasBlenderGithubShare()) return;
  const state = blenderGithubShareState || {};
  const git = state.git || {};
  const tools = state.tools || {};
  const hasProject = Boolean(els.blenderGithubProject?.value || state.project?.path || state.project?.repositoryUrl);
  const downloaded = state.project?.downloaded !== false && Boolean(state.project?.path && state.project?.directory);

  for (const control of els.blenderGithubSharePanel.querySelectorAll("input, select, textarea")) {
    control.disabled = blenderGithubBusy;
  }
  if (els.blenderGithubAdd) els.blenderGithubAdd.disabled = blenderGithubBusy;
  if (els.blenderGithubRefresh) els.blenderGithubRefresh.disabled = blenderGithubBusy;
  if (els.blenderGithubDesktop) els.blenderGithubDesktop.disabled = blenderGithubBusy || !hasProject;
  if (els.blenderGithubDesktop) {
    const label = text(downloaded ? "blenderGithubDesktopOpenTitle" : "blenderGithubDesktopCloneTitle");
    els.blenderGithubDesktop.title = label;
    els.blenderGithubDesktop.setAttribute("aria-label", label);
  }
  if (els.blenderGithubFolder) els.blenderGithubFolder.disabled = blenderGithubBusy || !downloaded;
  if (els.blenderGithubInitialize) {
    els.blenderGithubInitialize.disabled = blenderGithubBusy || !hasProject || !tools.gitAvailable || !tools.lfsAvailable;
  }
  if (els.blenderGithubCommit) {
    els.blenderGithubCommit.disabled = blenderGithubBusy || !hasProject || !git.initialized;
  }
  if (els.blenderGithubPush) {
    els.blenderGithubPush.disabled = blenderGithubBusy || !hasProject || !git.hasCommit || !git.remoteUrl;
  }
  if (els.blenderGithubOpen) {
    els.blenderGithubOpen.disabled = blenderGithubBusy || !hasProject;
  }
}

function setBlenderGithubExpanded(expanded) {
  const isExpanded = Boolean(expanded);
  if (els.blenderGithubBody) els.blenderGithubBody.hidden = !isExpanded;
  if (els.blenderGithubToggle) els.blenderGithubToggle.setAttribute("aria-expanded", String(isExpanded));
  els.blenderGithubSharePanel?.classList.toggle("collapsed", !isExpanded);
}

function setBlenderGithubBusy(busy, message = "") {
  blenderGithubBusy = Boolean(busy);
  els.blenderGithubSharePanel?.classList.toggle("busy", blenderGithubBusy);
  if (message) setBlenderGithubStatus(message);
  updateBlenderGithubActionState();
}

function renderBlenderGithubShare(state, options = {}) {
  if (!hasBlenderGithubShare() || !state) return;
  blenderGithubShareState = state;
  const project = state.project || {};
  const config = state.config || {};
  const git = state.git || {};
  renderBlenderGithubProjectOptions(project.repositoryUrl || project.path || "");
  syncBlenderGithubProjectContext(project.path || "");

  if (!options.preserveForm) {
    if (els.blenderGithubRepository) els.blenderGithubRepository.value = config.repositoryUrl || git.remoteUrl || "";
    if (els.blenderGithubVersion) els.blenderGithubVersion.value = config.version || "v0.1.0";
    if (els.blenderGithubMessage) els.blenderGithubMessage.value = config.message || "";
    if (els.blenderGithubIncludes) els.blenderGithubIncludes.value = (config.includePatterns || []).join("\n");
    if (els.blenderGithubExcludes) els.blenderGithubExcludes.value = (config.excludePatterns || []).join("\n");
    setBlenderGithubCheckedValue("blenderGithubVisibility", config.visibility || "private");
    setBlenderGithubCheckedValue("blenderGithubScope", config.scope || "current");
  }
  blenderGithubPublicConfirmed = config.visibility === "public";
  renderBlenderGithubCustomScope();

  if (els.blenderGithubProjectPath) {
    els.blenderGithubProjectPath.textContent = project.directory || "";
    els.blenderGithubProjectPath.title = project.directory || "";
  }
  if (els.blenderGithubBlendFile) {
    els.blenderGithubBlendFile.textContent = project.path?.split(/[\\/]/).pop() || "--";
    els.blenderGithubBlendFile.title = project.path || "";
  }
  if (els.blenderGithubBranch) els.blenderGithubBranch.textContent = git.branch || "--";
  if (els.blenderGithubRemote) {
    const remote = git.remoteUrl || config.repositoryUrl || "";
    els.blenderGithubRemote.textContent = remote ? blenderGithubRepositorySlug(remote) || remote : "--";
    els.blenderGithubRemote.title = remote;
  }
  if (els.blenderGithubLastVersion) {
    els.blenderGithubLastVersion.textContent = blenderGithubVersionText(git.lastTag || config.version);
  }
  if (els.blenderGithubCommitMeta) {
    els.blenderGithubCommitMeta.textContent = git.lastCommit
      ? text("blenderGithubLastCommit", git.lastCommit.hash || "", git.lastCommit.subject || "")
      : text("blenderGithubNoCommit");
  }
  if (els.blenderGithubState) {
    els.blenderGithubState.dataset.state = git.state || "uninitialized";
    els.blenderGithubState.title = blenderGithubStateLabel(git.state);
  }
  renderBlenderGithubBlendCards(state);
  updateBlenderGithubActionState();
}

async function loadBlenderGithubShare(options = {}) {
  if (!hasBlenderGithubShare()) return;
  const sequence = ++blenderGithubLoadSequence;
  const selectedProject = options.detect
    ? ""
    : options.project
      ?? els.blenderGithubProject?.value
      ?? blenderGithubShareState?.project?.repositoryUrl
      ?? blenderGithubShareState?.project?.path
      ?? "";
  setBlenderGithubBusy(true, text("blenderGithubLoading"));
  try {
    const query = selectedProject ? `?project=${encodeURIComponent(selectedProject)}` : "";
    const response = await fetch(`/api/randomrealm/blender/github-share/status${query}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    if (sequence !== blenderGithubLoadSequence) return;
    renderBlenderGithubShare(payload);
    setBlenderGithubStatus(text("blenderGithubReady"));
  } catch (error) {
    if (sequence !== blenderGithubLoadSequence) return;
    setBlenderGithubStatus(text("blenderGithubFailed", error.message));
  } finally {
    if (sequence === blenderGithubLoadSequence) {
      setBlenderGithubBusy(false);
    }
  }
}

async function addBlenderGithubProject() {
  if (!hasBlenderGithubShare() || blenderGithubBusy) return;
  setBlenderGithubBusy(true, text("blenderGithubAddingProject"));
  try {
    const payload = await postJson("/api/randomrealm/blender/github-share/add", {});
    if (payload.cancelled) {
      setBlenderGithubStatus("");
      return;
    }
    renderBlenderGithubShare(payload);
    setBlenderGithubStatus(text("blenderGithubProjectAdded"));
  } catch (error) {
    setBlenderGithubStatus(text("blenderGithubFailed", error.message));
  } finally {
    setBlenderGithubBusy(false);
  }
}

async function saveBlenderGithubShare(options = {}) {
  if (!hasBlenderGithubShare() || !blenderGithubShareState) return false;
  if (blenderGithubBusy) {
    blenderGithubSaveRequested = true;
    return false;
  }
  blenderGithubSaveRequested = false;
  setBlenderGithubBusy(true, options.quiet ? "" : text("blenderGithubSaving"));
  try {
    const payload = await postJson("/api/randomrealm/blender/github-share/config", blenderGithubFormPayload());
    renderBlenderGithubShare(payload);
    if (!options.quiet) setBlenderGithubStatus(text("blenderGithubSaved"));
    return true;
  } catch (error) {
    setBlenderGithubStatus(text("blenderGithubFailed", error.message));
    return false;
  } finally {
    setBlenderGithubBusy(false);
    if (blenderGithubSaveRequested) {
      blenderGithubSaveRequested = false;
      window.queueMicrotask(() => saveBlenderGithubShare(options));
    }
  }
}

function blenderGithubActionStatusKey(action) {
  return {
    init: "blenderGithubInitializing",
    commit: "blenderGithubCommitting",
    push: "blenderGithubPushing",
    open: "blenderGithubOpening"
  }[action] || "blenderGithubLoading";
}

async function runBlenderGithubAction(action) {
  if (!hasBlenderGithubShare() || blenderGithubBusy) return;
  const visibility = blenderGithubCheckedValue("blenderGithubVisibility", "private");
  if (visibility === "public" && !blenderGithubPublicConfirmed) {
    if (!window.confirm(text("blenderGithubPublicConfirm"))) {
      setBlenderGithubCheckedValue("blenderGithubVisibility", "private");
      return;
    }
    blenderGithubPublicConfirmed = true;
  }

  const repository = els.blenderGithubRepository?.value.trim() || "";
  const currentRemote = blenderGithubShareState?.git?.remoteUrl || "";
  const changingRemote = repository
    && currentRemote
    && blenderGithubRepositorySlug(repository) !== blenderGithubRepositorySlug(currentRemote);
  let replaceRemote = false;
  if (changingRemote) {
    replaceRemote = window.confirm(text("blenderGithubReplaceRemoteConfirm"));
    if (!replaceRemote) return;
  }

  let createGithub = false;
  if (action === "init" && !repository && blenderGithubShareState?.tools?.ghAuthenticated) {
    createGithub = window.confirm(text("blenderGithubCreateConfirm", blenderGithubShareState.project?.rootName || blenderGithubShareState.project?.name || "repository"));
  }

  setBlenderGithubBusy(true, text(blenderGithubActionStatusKey(action)));
  try {
    const payload = await postJson(
      `/api/randomrealm/blender/github-share/${action}`,
      blenderGithubFormPayload({ replaceRemote, createGithub })
    );
    if (action !== "open") {
      renderBlenderGithubShare(payload);
    }
    const successMessage = action === "init"
      ? text(payload.git?.remoteUrl ? "blenderGithubInitializedReady" : "blenderGithubInitializedNoRemote")
      : action === "commit"
        ? text("blenderGithubCommitComplete", payload.action?.tag || els.blenderGithubVersion?.value || "")
        : action === "push"
          ? text("blenderGithubPushComplete")
          : action === "open"
            ? text("blenderGithubOpenComplete")
            : payload.message || text("blenderGithubReady");
    setBlenderGithubStatus(successMessage);
  } catch (error) {
    setBlenderGithubStatus(text("blenderGithubFailed", error.message));
  } finally {
    setBlenderGithubBusy(false);
  }
}

async function openBlenderGithubTarget(target, projectOverride = "", repositoryOverride = "") {
  if (!hasBlenderGithubShare() || blenderGithubBusy) return;
  const endpoint = {
    desktop: "desktop",
    folder: "folder",
    github: "open"
  }[target];
  if (!endpoint) return;
  const project = projectOverride
    || els.blenderGithubProject?.value
    || blenderGithubShareState?.project?.repositoryUrl
    || blenderGithubShareState?.project?.path
    || "";
  const repositoryUrl = repositoryOverride
    || blenderGithubShareState?.project?.repositoryUrl
    || blenderGithubShareState?.git?.repositoryWebUrl
    || "";
  setBlenderGithubBusy(true, text("blenderGithubLoading"));
  try {
    await postJson(`/api/randomrealm/blender/github-share/${endpoint}`, { project, repositoryUrl });
    setBlenderGithubStatus("");
  } catch (error) {
    setBlenderGithubStatus(text("blenderGithubFailed", error.message));
  } finally {
    setBlenderGithubBusy(false);
  }
}

function readBlenderPromptConfigFromForm() {
  return normalizeBlenderPromptConfig({
    format: els.blenderPromptFormat?.value || "",
    image: els.blenderPromptImage?.value || "",
    resolution: els.blenderPromptResolution?.value || defaultBlenderPromptConfig.resolution,
    customWidth: els.blenderPromptCustomWidth?.value || "",
    customLength: els.blenderPromptCustomLength?.value || "",
    style: els.blenderPromptStyle?.value || "",
    basics: els.blenderPromptBasics?.value || ""
  });
}

function renderBlenderPromptBuilder() {
  if (!els.blenderPromptOutput) return;
  if (els.blenderPromptFormat) els.blenderPromptFormat.value = blenderPromptConfig.format;
  if (els.blenderPromptImage) els.blenderPromptImage.value = blenderPromptConfig.image;
  if (els.blenderPromptResolution) els.blenderPromptResolution.value = blenderPromptConfig.resolution;
  if (els.blenderPromptCustomWidth) els.blenderPromptCustomWidth.value = blenderPromptConfig.customWidth;
  if (els.blenderPromptCustomLength) els.blenderPromptCustomLength.value = blenderPromptConfig.customLength;
  if (els.blenderPromptStyle) els.blenderPromptStyle.value = blenderPromptConfig.style;
  if (els.blenderPromptBasics) els.blenderPromptBasics.value = blenderPromptConfig.basics;
  renderBlenderPromptResolution();
  updateBlenderPromptOutput();
}

function renderBlenderPromptResolution() {
  const isCustom = (els.blenderPromptResolution?.value || blenderPromptConfig.resolution) === "custom";
  if (els.blenderPromptCustomResolution) {
    els.blenderPromptCustomResolution.hidden = !isCustom;
  }
}

function blenderPromptResolutionText(config = blenderPromptConfig) {
  const safeConfig = normalizeBlenderPromptConfig(config);
  if (safeConfig.resolution === "custom") {
    return safeConfig.customWidth && safeConfig.customLength
      ? `${safeConfig.customWidth}x${safeConfig.customLength}`
      : "custom resolution";
  }
  return safeConfig.resolution.toUpperCase();
}

function setBlenderPromptStatus(message) {
  if (els.blenderPromptStatus) {
    els.blenderPromptStatus.textContent = message || text("randomRealmArtReady");
  }
}

function selectedRandomRealmProject() {
  const path = els.randomRealmBlenderProject?.value || randomRealmArtContext.project || "";
  return randomRealmBlenderProjects.find(item => item.path === path) || (path ? { path, name: path.split(/[\\/]/).pop() } : null);
}

function blenderPromptContextLines() {
  const project = selectedRandomRealmProject();
  const object = selectedRandomRealmObject();
  const textures = Array.isArray(object?.textures) ? object.textures : [];
  const materials = Array.isArray(object?.materials) ? object.materials : [];
  const lines = [
    `Project: ${project?.name || "Unknown"}${project?.path ? ` (${project.path})` : ""}`,
    `Art Type: ${randomRealmArtContext.type || els.randomRealmArtType?.value || defaultRandomRealmArtTypes[0]}`,
    `Selected Object: ${object?.name || randomRealmArtContext.object || "Not selected"}`,
    `Object Type: ${object?.type || "Unknown"}`,
    `Materials: ${materials.length ? materials.join(", ") : "None listed"}`,
    `Textures: ${textures.length ? textures.map(item => item.file || item.name || item.path).join(", ") : "None listed"}`,
    `Selected Material: ${randomRealmSelectedMaterial || "Auto"}`,
    `Selected Old Texture: ${randomRealmSelectedOldTexture?.file || randomRealmSelectedOldTexture?.name || "Not selected"}`
  ];
  if (randomRealmNewTexture?.name) {
    lines.push(`Staged Texture Package Input: ${randomRealmNewTexture.name}`);
  }
  return lines;
}

function generateBlenderPromptText(config = blenderPromptConfig) {
  const safeConfig = normalizeBlenderPromptConfig(config);
  return [
    "Generate or revise a Blender/Unity game asset prompt using the context below.",
    "",
    "Goal:",
    `- Prepare clear instructions for a ${randomRealmArtContext.type || defaultRandomRealmArtTypes[0]} asset workflow.`,
    "",
    "Format Requirements:",
    safeConfig.format,
    "",
    "Image Requirements:",
    safeConfig.image,
    `Texture / image resolution requirement: ${blenderPromptResolutionText(safeConfig)}.`,
    "",
    "Style:",
    safeConfig.style,
    "",
    "Base Info:",
    safeConfig.basics,
    "",
    "Blender Context:",
    ...blenderPromptContextLines().map(line => `- ${line}`),
    "",
    "Output Constraints:",
    "- Be concrete and production-oriented.",
    "- Keep names, object references, texture paths, and constraints intact.",
    `- Target texture/reference image resolution: ${blenderPromptResolutionText(safeConfig)}.`,
    "- If something is missing, state the assumption instead of inventing hidden project facts.",
    "",
    "Negative Requirements:",
    "- No watermark, no UI text, no random extra objects, no muddy silhouette, no unrelated decorative clutter."
  ].join("\n");
}

function updateBlenderPromptOutput() {
  if (!els.blenderPromptOutput) return;
  const nextConfig = els.blenderPromptFormat ? readBlenderPromptConfigFromForm() : blenderPromptConfig;
  blenderPromptConfig = nextConfig;
  saveBlenderPromptConfig();
  els.blenderPromptOutput.value = generateBlenderPromptText(nextConfig);
}

function generateBlenderPrompt() {
  updateBlenderPromptOutput();
  setBlenderPromptStatus(text("randomRealmArtReady"));
}

function clearBlenderPrompt() {
  blenderPromptConfig = { format: "", image: "", style: "", basics: "", resolution: "2k", customResolution: "", customWidth: "", customLength: "" };
  if (els.blenderPromptFormat) els.blenderPromptFormat.value = "";
  if (els.blenderPromptImage) els.blenderPromptImage.value = "";
  if (els.blenderPromptResolution) els.blenderPromptResolution.value = "2k";
  if (els.blenderPromptCustomWidth) els.blenderPromptCustomWidth.value = "";
  if (els.blenderPromptCustomLength) els.blenderPromptCustomLength.value = "";
  if (els.blenderPromptStyle) els.blenderPromptStyle.value = "";
  if (els.blenderPromptBasics) els.blenderPromptBasics.value = "";
  if (els.blenderPromptOutput) els.blenderPromptOutput.value = "";
  renderBlenderPromptResolution();
  saveBlenderPromptConfig();
  setBlenderPromptStatus(text("blenderPromptCleared"));
}

async function copyBlenderPrompt() {
  if (!els.blenderPromptOutput) return;
  updateBlenderPromptOutput();
  const value = els.blenderPromptOutput.value;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      els.blenderPromptOutput.focus();
      els.blenderPromptOutput.select();
      document.execCommand("copy");
    }
    setBlenderPromptStatus(text("blenderPromptCopied"));
  } catch {
    els.blenderPromptOutput.focus();
    els.blenderPromptOutput.select();
    setBlenderPromptStatus(text("blenderPromptCopyFailed"));
  }
}

function renderRandomRealmArtTypes() {
  if (!els.randomRealmArtType) return;
  const selected = defaultRandomRealmArtTypes.includes(randomRealmArtContext.type)
    ? randomRealmArtContext.type
    : defaultRandomRealmArtTypes[0];
  els.randomRealmArtType.innerHTML = "";
  for (const type of defaultRandomRealmArtTypes) {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = randomRealmArtTypeLabels[type] || type;
    els.randomRealmArtType.appendChild(option);
  }
  els.randomRealmArtType.value = selected;
  randomRealmArtContext.type = selected;
}

function hasRandomRealmArtTools() {
  return Boolean(els.randomRealmBlenderProject && els.randomRealmBlenderObject);
}

function setRandomRealmArtStatus(message) {
  randomRealmArtNotice = message || "";
  if (els.randomRealmArtStatus) {
    els.randomRealmArtStatus.textContent = randomRealmArtNotice || text("randomRealmArtReady");
  }
}

function setRandomRealmTextureActionBusy(isBusy) {
  randomRealmTextureActionBusy = Boolean(isBusy);
  updateRandomRealmTextureActionState();
}

function updateRandomRealmTextureActionState() {
  if (els.randomRealmStageBlankTexture) {
    els.randomRealmStageBlankTexture.disabled = randomRealmTextureActionBusy || !selectedRandomRealmObject();
  }
}

async function loadUnityBridgeStatus() {
  if (!els.unityBridgeStatus) return;
  try {
    const response = await fetch("/api/randomrealm/unity/bridge-status", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const count = Array.isArray(payload.packages) ? payload.packages.length : 0;
    els.unityBridgeStatus.textContent = payload.message || (count ? `${count} package${count === 1 ? "" : "s"}` : text("unityBridgeReady"));
  } catch (error) {
    els.unityBridgeStatus.textContent = error.message;
  }
}

function selectedRandomRealmObject() {
  const name = els.randomRealmBlenderObject?.value || randomRealmArtContext.object || "";
  return randomRealmBlenderObjects.find(item => item.name === name) || null;
}

function randomRealmObjectLabel(object) {
  if (!object) return "";
  return `${object.name} - ${object.type || "Object"}`;
}

function selectedRandomRealmObjectLabel() {
  const object = selectedRandomRealmObject();
  return object ? randomRealmObjectLabel(object) : randomRealmArtContext.object || "";
}

function setRandomRealmObjectPickerOpen(open) {
  randomRealmObjectPickerOpen = Boolean(open);
  if (els.randomRealmBlenderObject) {
    els.randomRealmBlenderObject.hidden = !randomRealmObjectPickerOpen;
  }
  if (!randomRealmObjectPickerOpen && els.randomRealmObjectSearch) {
    els.randomRealmObjectSearch.value = selectedRandomRealmObjectLabel();
  }
}

function renderRandomRealmBlenderProjects() {
  if (!els.randomRealmBlenderProject) return;
  els.randomRealmBlenderProject.innerHTML = "";
  if (!randomRealmBlenderProjects.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = text("randomRealmBlenderNoProject");
    els.randomRealmBlenderProject.appendChild(option);
    if (els.randomRealmProjectPath) {
      els.randomRealmProjectPath.textContent = "";
    }
    renderBlenderGithubProjectOptions(blenderGithubShareState?.project?.path || "");
    return;
  }
  for (const project of randomRealmBlenderProjects) {
    const option = document.createElement("option");
    option.value = project.path;
    option.textContent = project.name || project.file || project.path;
    els.randomRealmBlenderProject.appendChild(option);
  }
  const saved = randomRealmArtContext.project;
  els.randomRealmBlenderProject.value = randomRealmBlenderProjects.some(item => item.path === saved)
    ? saved
    : randomRealmBlenderProjects[0].path;
  updateRandomRealmProjectAddress();
  renderBlenderGithubProjectOptions(blenderGithubShareState?.project?.path || els.randomRealmBlenderProject.value);
}

function updateRandomRealmProjectAddress() {
  const project = selectedRandomRealmProject();
  const path = project?.path || els.randomRealmBlenderProject?.value || "";
  if (els.randomRealmProjectPath) {
    els.randomRealmProjectPath.textContent = path;
  }
  updateBlenderPromptOutput();
}

function filteredRandomRealmObjects() {
  const rawQuery = (els.randomRealmObjectSearch?.value || "").trim();
  const selectedLabel = selectedRandomRealmObjectLabel();
  const selectedName = selectedRandomRealmObject()?.name || randomRealmArtContext.object || "";
  const query = randomRealmObjectPickerOpen && rawQuery !== selectedLabel && rawQuery !== selectedName
    ? rawQuery.toLocaleLowerCase()
    : "";
  if (!query) return randomRealmBlenderObjects;
  return randomRealmBlenderObjects.filter(item => [
    item.name,
    item.type,
    ...(Array.isArray(item.materials) ? item.materials : []),
    ...(Array.isArray(item.textures) ? item.textures.map(texture => texture.file || texture.name || texture.path) : [])
  ].join(" ").toLocaleLowerCase().includes(query));
}

function renderRandomRealmBlenderObjects() {
  if (!els.randomRealmBlenderObject) return;
  const items = filteredRandomRealmObjects();
  els.randomRealmBlenderObject.innerHTML = "";
  if (!items.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = text("randomRealmBlenderNoObject");
    els.randomRealmBlenderObject.appendChild(option);
  } else {
    for (const item of items) {
      const option = document.createElement("option");
      option.value = item.name;
      option.textContent = randomRealmObjectLabel(item);
      option.textContent = `${item.name} · ${item.type || "Object"}`;
      option.textContent = randomRealmObjectLabel(item);
      option.title = [
        item.name,
        item.type,
        ...(Array.isArray(item.materials) ? item.materials : []),
        ...(Array.isArray(item.textures) ? item.textures.map(texture => texture.path || texture.file || texture.name) : [])
      ].filter(Boolean).join("\n");
      els.randomRealmBlenderObject.appendChild(option);
    }
    const saved = randomRealmArtContext.object || els.randomRealmBlenderObject.value;
    els.randomRealmBlenderObject.value = items.some(item => item.name === saved) ? saved : items[0].name;
  }
  els.randomRealmBlenderObject.hidden = !randomRealmObjectPickerOpen;
  if (!randomRealmObjectPickerOpen && els.randomRealmObjectSearch) {
    els.randomRealmObjectSearch.value = selectedRandomRealmObjectLabel();
  }
  renderRandomRealmUsedTextures();
}

async function syncRandomRealmLiveSelection(options = {}) {
  if (!hasRandomRealmArtTools() || !els.randomRealmBlenderProject?.value) return false;
  if (randomRealmObjectPickerOpen && document.activeElement === els.randomRealmObjectSearch) return false;
  const quiet = options.quiet !== false;
  try {
    const url = `/api/randomrealm/blender/live-selection?project=${encodeURIComponent(els.randomRealmBlenderProject.value)}`;
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    if (!payload.available || payload.stale) {
      randomRealmLiveSelectedObjects = [];
      if (!quiet) setRandomRealmArtStatus(text("randomRealmLiveUnavailable"));
      return false;
    }
    if (!payload.matchingProject) {
      randomRealmLiveSelectedObjects = [];
      if (!quiet) setRandomRealmArtStatus(text("randomRealmLiveProjectMismatch"));
      return false;
    }
    const activeName = payload.activeObject?.name || "";
    if (!activeName) {
      if (!quiet) setRandomRealmArtStatus(text("randomRealmLiveUnavailable"));
      return false;
    }
    const exists = randomRealmBlenderObjects.some(item => item.name === activeName);
    if (!exists) {
      if (!quiet) setRandomRealmArtStatus(text("randomRealmLiveObjectMissing", activeName));
      return false;
    }
    const selectedNames = Array.from(new Set([
      activeName,
      ...(Array.isArray(payload.selectedObjects) ? payload.selectedObjects.map(item => item?.name || "") : [])
    ].filter(name => randomRealmBlenderObjects.some(item => item.name === name))));
    const selectedKey = selectedNames.join("\n");
    if (els.randomRealmBlenderObject.value === activeName && randomRealmLastLiveObject === activeName && randomRealmLiveSelectedObjects.join("\n") === selectedKey) {
      if (!quiet) await refreshRandomRealmSelectedObjectTextures();
      return true;
    }
    els.randomRealmBlenderObject.value = activeName;
    randomRealmArtContext.object = activeName;
    randomRealmSelectedOldTexture = null;
    randomRealmSelectedMaterial = "";
    randomRealmLastLiveObject = activeName;
    randomRealmLiveSelectedObjects = selectedNames;
    setRandomRealmObjectPickerOpen(false);
    renderRandomRealmUsedTextures();
    updateRandomRealmArtContext();
    setRandomRealmArtStatus(text("randomRealmLiveSynced", activeName));
    if (!quiet) await refreshRandomRealmSelectedObjectTextures();
    return true;
  } catch (error) {
    if (!quiet) setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
    return false;
  }
}

function stopRandomRealmLiveSelectionPolling() {
  if (!randomRealmLiveSelectionTimer) return;
  window.clearTimeout(randomRealmLiveSelectionTimer);
  randomRealmLiveSelectionTimer = null;
}

function startRandomRealmLiveSelectionPolling(options = {}) {
  if (!hasRandomRealmArtTools() || !isModuleForeground("blender")) {
    stopRandomRealmLiveSelectionPolling();
    return;
  }
  if (randomRealmLiveSelectionTimer) return;
  randomRealmLiveSelectionTimer = window.setTimeout(async () => {
    randomRealmLiveSelectionTimer = null;
    if (!isModuleForeground("blender")) return;
    await syncRandomRealmLiveSelection({ quiet: true });
    startRandomRealmLiveSelectionPolling();
  }, options.immediate ? 0 : 1600);
}

function isRandomRealmPreviewableTexture(path) {
  const lowered = String(path || "").toLocaleLowerCase();
  return randomRealmPreviewableTextureExtensions.some(extension => lowered.endsWith(extension));
}

function randomRealmTexturePreviewUrl(path) {
  return `/api/randomrealm/blender/texture-preview?path=${encodeURIComponent(path)}`;
}

function randomRealmTextureFilename(texture) {
  const path = texture?.path || "";
  return texture?.file || texture?.name || path.split(/[\\/]/).pop() || "texture.png";
}

function randomRealmTextureDragUrl(texture) {
  const path = texture?.path || "";
  const filename = encodeURIComponent(randomRealmTextureFilename(texture));
  return `/api/randomrealm/blender/texture-file/${filename}?path=${encodeURIComponent(path)}`;
}

function randomRealmTextureMimeType(texture) {
  const filename = randomRealmTextureFilename(texture).toLocaleLowerCase();
  if (filename.endsWith(".jpg") || filename.endsWith(".jpeg")) return "image/jpeg";
  if (filename.endsWith(".webp")) return "image/webp";
  if (filename.endsWith(".bmp")) return "image/bmp";
  return "image/png";
}

function fileUrlFromWindowsPath(path) {
  const normalized = String(path || "").replace(/\\/g, "/");
  const parts = normalized.split("/").map((part, index) => {
    if (index === 0 && /^[a-z]:$/i.test(part)) return part;
    return encodeURIComponent(part);
  });
  return `file:///${parts.join("/")}`;
}

function attachRandomRealmTextureDragData(event, texture) {
  const path = texture?.path || "";
  if (!path || !event.dataTransfer) return;
  const filename = randomRealmTextureFilename(texture);
  const mimeType = randomRealmTextureMimeType(texture);
  const previewUrl = new URL(randomRealmTextureDragUrl(texture), window.location.href).href;
  const fileUrl = fileUrlFromWindowsPath(path);
  const cachedFile = randomRealmTextureDragFileCache.get(path)?.file;
  event.dataTransfer.effectAllowed = "copy";
  if (cachedFile && event.dataTransfer.items?.add) {
    try {
      event.dataTransfer.items.add(cachedFile);
    } catch {
      // Some external targets only accept URLs or native file drops.
    }
  }
  event.dataTransfer.setData("DownloadURL", `${mimeType}:${filename}:${previewUrl}`);
  event.dataTransfer.setData("text/uri-list", `${fileUrl}\n${previewUrl}`);
  event.dataTransfer.setData("text/plain", path);
  event.dataTransfer.setData("text/html", `<img src="${previewUrl}" alt="${filename}">`);
}

function preloadRandomRealmTextureDragFile(texture) {
  const path = texture?.path || "";
  if (!path || randomRealmTextureDragFileCache.has(path)) return;
  const record = { file: null };
  randomRealmTextureDragFileCache.set(path, record);
  fetch(randomRealmTextureDragUrl(texture))
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.blob();
    })
    .then(blob => {
      record.file = new File([blob], randomRealmTextureFilename(texture), {
        type: blob.type || randomRealmTextureMimeType(texture)
      });
    })
    .catch(() => {
      randomRealmTextureDragFileCache.delete(path);
    });
}

async function openRandomRealmTextureFile(texture) {
  const path = texture?.path || "";
  if (!path) return;
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const payload = await postJson("/api/randomrealm/blender/open-texture", { path });
    setRandomRealmArtStatus(text("randomRealmTextureOpened", randomRealmTextureFilename(texture), payload.app || ""));
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmTextureOpenFailed", error.message));
  }
}

function startRandomRealmNativeTextureDrag(texture) {
  const path = texture?.path || "";
  if (!path) return;
  setRandomRealmArtStatus(text("randomRealmNativeDragStarted"));
  fetch("/api/randomrealm/blender/native-drag", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
    keepalive: true
  }).catch(error => {
    setRandomRealmArtStatus(text("randomRealmTextureOpenFailed", error.message));
  });
}

function bindRandomRealmNativeTextureDrag(imageEl, texture) {
  let dragStart = null;
  let launched = false;
  let launchTimer = null;

  const clearLaunchTimer = () => {
    if (launchTimer) {
      window.clearTimeout(launchTimer);
      launchTimer = null;
    }
  };

  const launch = event => {
    if (!dragStart || launched) return;
    launched = true;
    clearLaunchTimer();
    event?.preventDefault?.();
    startRandomRealmNativeTextureDrag(texture);
  };

  const reset = () => {
    clearLaunchTimer();
    dragStart = null;
    launched = false;
  };

  imageEl.onpointerdown = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    dragStart = {
      x: event.clientX,
      y: event.clientY,
      pointerId: event.pointerId
    };
    launched = false;
    try {
      imageEl.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is a nice-to-have here.
    }
    clearLaunchTimer();
    launchTimer = window.setTimeout(() => launch(event), 120);
  };

  imageEl.onpointermove = event => {
    if (!dragStart || launched) return;
    const distance = Math.hypot(event.clientX - dragStart.x, event.clientY - dragStart.y);
    if (distance < 6) return;
    launch(event);
  };

  imageEl.onpointerup = reset;
  imageEl.onpointercancel = reset;
}

function renderRandomRealmTexturePreview(imageEl, emptyEl, texture) {
  if (!imageEl || !emptyEl) return;
  const path = texture?.path || "";
  const canPreview = Boolean(path && texture?.exists !== false && isRandomRealmPreviewableTexture(path));
  if (canPreview) {
    preloadRandomRealmTextureDragFile(texture);
    imageEl.onerror = () => {
      imageEl.hidden = true;
      emptyEl.hidden = false;
      emptyEl.textContent = text("randomRealmTexturePreviewUnsupported");
        emptyEl.title = path;
    };
    imageEl.src = randomRealmTextureDragUrl(texture);
    imageEl.draggable = false;
    imageEl.dataset.texturePath = path;
    imageEl.ondragstart = event => attachRandomRealmTextureDragData(event, texture);
    imageEl.ondblclick = event => {
      event.preventDefault();
      openRandomRealmTextureFile(texture);
    };
    bindRandomRealmNativeTextureDrag(imageEl, texture);
    imageEl.title = `${text("randomRealmTextureDragHint")}${path}`;
    imageEl.hidden = false;
    emptyEl.hidden = true;
    return;
  }
  imageEl.onerror = null;
  imageEl.ondragstart = null;
  imageEl.ondblclick = null;
  imageEl.onpointerdown = null;
  imageEl.onpointermove = null;
  imageEl.onpointerup = null;
  imageEl.onpointercancel = null;
  imageEl.draggable = false;
  delete imageEl.dataset.texturePath;
  imageEl.removeAttribute("src");
  imageEl.title = "";
  imageEl.hidden = true;
  emptyEl.hidden = false;
  emptyEl.textContent = path ? text("randomRealmTexturePreviewUnsupported") : text("randomRealmTexturePreviewEmpty");
  emptyEl.title = path;
}

function randomRealmTextureDimensions(texture) {
  const width = Number(texture?.width || 0);
  const height = Number(texture?.height || 0);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return { width: Math.round(width), height: Math.round(height) };
}

function formatRandomRealmTextureDimensions(texture) {
  const dimensions = randomRealmTextureDimensions(texture);
  return dimensions ? `${dimensions.width}x${dimensions.height}` : text("randomRealmTextureDimensionsUnknown");
}

function middleEllipsis(value, maxLength = 56) {
  const textValue = String(value || "");
  if (textValue.length <= maxLength) return textValue;
  const keep = Math.max(8, Math.floor((maxLength - 1) / 2));
  const tail = Math.max(8, maxLength - keep - 1);
  return `${textValue.slice(0, keep)}...${textValue.slice(-tail)}`;
}

function randomRealmMaterialReadableName(materialName) {
  const readable = String(materialName || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/^BuilderMat[_-]?/i, "")
    .replace(/[_-]?PBR$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\b(image|texture)\s*\d*\b/gi, "")
    .trim();
  return readable || materialName || "";
}

function randomRealmMaterialDisplayName(materialName, maxLength = 42) {
  return middleEllipsis(randomRealmMaterialReadableName(materialName), maxLength);
}

function randomRealmTextureRole(texture) {
  const value = [
    texture?.kind || "",
    texture?.role || "",
    texture?.roleLabel || "",
    texture?.node || "",
    texture?.file || "",
    texture?.name || ""
  ].join(" ").toLowerCase();
  if (value.includes("basecolor") || value.includes("base-color") || value.includes("albedo") || value.includes("diffuse")) return "Base Color";
  if (value.includes("normal")) return "Normal";
  if (value.includes("roughness") || value.includes("rough")) return "Roughness";
  if (value.includes("ambient occlusion") || value.includes("ambient-occlusion") || value.includes("occlusion") || /\bao\b/.test(value)) return "Ambient Occlusion";
  if (value.includes("metallic") || value.includes("metalness")) return "Metallic";
  if (value.includes("height") || value.includes("bump")) return "Height";
  if (value.includes("alpha") || value.includes("opacity")) return "Alpha";
  if (value.includes("emission") || value.includes("emissive")) return "Emission";
  return "Texture";
}

const randomRealmTextureKindLabels = {
  "base-color": "Base Color",
  normal: "Normal",
  roughness: "Roughness",
  "ambient-occlusion": "Ambient Occlusion",
  metallic: "Metallic",
  height: "Height",
  alpha: "Alpha",
  emission: "Emission"
};

function randomRealmTextureKindLabel(kind) {
  return randomRealmTextureKindLabels[kind] || kind || "Texture";
}

function normalizeRandomRealmTextureMatchText(value) {
  return ` ${String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ")} `;
}

function randomRealmTokenSet(value) {
  return new Set(String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .split(/\s+/)
    .filter(Boolean));
}

function inferRandomRealmTextureKindFromName(value) {
  const name = normalizeRandomRealmTextureMatchText(value);
  const compact = String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (/\b(normal|norm|nrm|nor|normal map)\b/.test(name) || /(normalmap|normmap|nrmmap|normaldx|normalgl)/.test(compact)) return "normal";
  if (/\b(roughness|rough|rgh|roughness map)\b/.test(name) || /(roughnessmap|roughmap|rghmap)/.test(compact)) return "roughness";
  if (/\b(ambient occlusion|occlusion|ao|ao map)\b/.test(name) || /(ambientocclusionmap|occlusionmap|aomap)/.test(compact)) return "ambient-occlusion";
  if (/\b(metallic|metalness|metal|metallic map)\b/.test(name) || /(metallicmap|metalnessmap|metalmap)/.test(compact)) return "metallic";
  if (/\b(height|bump|displacement|disp|height map)\b/.test(name) || /(heightmap|bumpmap|displacementmap|dispmap)/.test(compact)) return "height";
  if (/\b(alpha|opacity|mask|alpha map)\b/.test(name) || /(alphamap|opacitymap|maskmap)/.test(compact)) return "alpha";
  if (/\b(emission|emissive|emit|emission map)\b/.test(name) || /(emissionmap|emissivemap|emitmap)/.test(compact)) return "emission";
  if (/\b(base color|basecolor|albedo|diffuse|diff|color|col|color map)\b/.test(name) || /(basecolormap|albedomap|diffusemap|colormap)/.test(compact)) return "base-color";
  return "";
}

function randomRealmMaterialAliasTokens(materialName) {
  const tokens = randomRealmTokenSet(`${materialName || ""} ${randomRealmMaterialReadableName(materialName)}`);
  const aliases = new Set(tokens);
  if (tokens.has("interior")) {
    aliases.add("inner");
    aliases.add("inside");
    aliases.add("int");
  }
  if (tokens.has("exterior")) {
    aliases.add("outside");
    aliases.add("ext");
  }
  return aliases;
}

function randomRealmInferMaterialFromTextureName(object, texture) {
  const materials = uniqueRandomRealmMaterials(object);
  if (!materials.length) return "";
  if (materials.length === 1) return materials[0];

  const textureText = `${texture?.name || ""} ${texture?.file || ""} ${texture?.path || ""} ${texture?.sourcePackage || ""}`;
  const textureTokens = randomRealmTokenSet(textureText);
  const textureCompact = String(textureText || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!textureTokens.size && !textureCompact) return "";

  const materialEntries = materials.map(material => ({
    material,
    tokens: Array.from(randomRealmMaterialAliasTokens(material))
      .filter(token => token.length >= 3 && !["mat", "pbr", "map", "image", "texture"].includes(token))
  }));
  const tokenCounts = new Map();
  for (const entry of materialEntries) {
    for (const token of new Set(entry.tokens)) {
      tokenCounts.set(token, (tokenCounts.get(token) || 0) + 1);
    }
  }

  let best = null;
  let bestScore = 0;
  let tied = false;
  for (const entry of materialEntries) {
    const uniqueTokens = entry.tokens.filter(token => tokenCounts.get(token) === 1);
    let uniqueHits = 0;
    for (const token of uniqueTokens) {
      if (textureTokens.has(token) || (token.length >= 4 && textureCompact.includes(token))) {
        uniqueHits += 1;
      }
    }
    if (!uniqueHits) continue;

    let sharedHits = 0;
    for (const token of new Set(entry.tokens)) {
      if (textureTokens.has(token) || (token.length >= 4 && textureCompact.includes(token))) {
        sharedHits += 1;
      }
    }
    const score = uniqueHits * 100 + sharedHits;
    if (score > bestScore) {
      best = entry.material;
      bestScore = score;
      tied = false;
    } else if (score === bestScore) {
      tied = true;
    }
  }
  return tied ? "" : (best || "");
}

function randomRealmTextureKindFromExisting(texture) {
  const explicitKind = String(texture?.kind || texture?.inferredKind || "").trim();
  if (explicitKind && randomRealmTextureKindLabels[explicitKind]) return explicitKind;
  const inferred = inferRandomRealmTextureKindFromName([
    texture?.kind || "",
    texture?.role || "",
    texture?.roleLabel || "",
    texture?.node || "",
    texture?.file || "",
    texture?.name || ""
  ].join(" "));
  if (inferred) return inferred;
  const role = randomRealmTextureRole(texture);
  return Object.entries(randomRealmTextureKindLabels)
    .find(([, label]) => label === role)?.[0] || "";
}

function randomRealmStagedTextureWithKind(texture, object = selectedRandomRealmObject()) {
  return {
    ...texture,
    inferredKind: inferRandomRealmTextureKindFromName(`${texture?.name || ""} ${texture?.path || ""}`),
    inferredMaterial: texture?.material || randomRealmInferMaterialFromTextureName(object, texture)
  };
}

function selectRandomRealmStagedTextureForKind(kind = els.randomRealmTextureKind?.value || "base-color") {
  if (!randomRealmStagedTextures.length) {
    randomRealmNewTexture = null;
    return false;
  }
  const wantedKind = kind || "base-color";
  const wantedMaterial = randomRealmSelectedOldTexture?.material
    || (randomRealmSelectedMaterial && randomRealmSelectedMaterial !== "all" ? randomRealmSelectedMaterial : "");
  randomRealmNewTexture = randomRealmStagedTextures.find(texture =>
    texture.inferredKind === wantedKind &&
    (!wantedMaterial || texture.inferredMaterial === wantedMaterial || texture.material === wantedMaterial)
  )
    || randomRealmStagedTextures.find(texture => texture.inferredKind === wantedKind)
    || randomRealmStagedTextures.find(texture => !texture.inferredKind)
    || randomRealmStagedTextures[0];
  return Boolean(randomRealmNewTexture);
}

function randomRealmTextureIdentity(texture) {
  if (!texture) return "";
  return [
    texture?.pendingSlot ? "pending" : "",
    texture?.path || "",
    texture?.material || "",
    texture?.node || "",
    texture?.kind || ""
  ].join("\u0001");
}

function addRandomRealmStagedTextures(files, preferredKind = "") {
  const object = selectedRandomRealmObject();
  const rawIncoming = (Array.isArray(files) ? files : [])
    .map(texture => randomRealmStagedTextureWithKind(texture, object))
    .filter(texture => texture.path);
  if (!rawIncoming.length) return 0;

  const oldTextureKind = randomRealmTextureKindFromExisting(randomRealmSelectedOldTexture);
  const singleKind = rawIncoming.length === 1 ? rawIncoming[0].inferredKind : "";
  const nextKind = preferredKind || oldTextureKind || singleKind || els.randomRealmTextureKind?.value || "base-color";
  const useFallbackKind = Boolean(preferredKind || rawIncoming.length === 1);
  const normalizedIncoming = rawIncoming.map(texture => (
    !texture.inferredKind && useFallbackKind
      ? { ...texture, inferredKind: nextKind }
      : texture
  ));
  const inferredIncomingMaterials = new Set(normalizedIncoming.map(texture => texture.inferredMaterial || texture.material || "").filter(Boolean));
  const sharedIncomingMaterial = inferredIncomingMaterials.size === 1 ? Array.from(inferredIncomingMaterials)[0] : "";
  const materializedIncoming = sharedIncomingMaterial
    ? normalizedIncoming.map(texture => (
      texture.inferredMaterial || texture.material
        ? texture
        : { ...texture, inferredMaterial: sharedIncomingMaterial }
    ))
    : normalizedIncoming;
  const byKind = new Map();
  for (const texture of materializedIncoming) {
    const key = texture.inferredKind
      ? `${texture.inferredMaterial || texture.material || ""}\u0001${texture.inferredKind}`
      : `unknown:${texture.path}`;
    byKind.set(key, texture);
  }
  const incoming = Array.from(byKind.values());
  if (!incoming.length) return 0;
  const incomingTargets = new Set(incoming
    .filter(texture => texture.inferredKind)
    .map(texture => `${texture.inferredMaterial || texture.material || ""}\u0001${texture.inferredKind}`));
  const incomingPaths = new Set(incoming.map(texture => texture.path));
  randomRealmStagedTextures = randomRealmStagedTextures.filter(texture => (
    !incomingPaths.has(texture.path) &&
    (!texture.inferredKind || !incomingTargets.has(`${texture.inferredMaterial || texture.material || ""}\u0001${texture.inferredKind}`))
  ));
  const byPath = new Map(randomRealmStagedTextures.map(texture => [texture.path, texture]));
  for (const texture of incoming) {
    byPath.set(texture.path, texture);
  }
  randomRealmStagedTextures = Array.from(byPath.values());
  const incomingMaterials = new Set(incoming.map(texture => texture.inferredMaterial || texture.material || "").filter(Boolean));
  if (incomingMaterials.size === 1) {
    const [material] = Array.from(incomingMaterials);
    if (material && uniqueRandomRealmMaterials(object).includes(material)) {
      randomRealmSelectedMaterial = material;
      randomRealmSelectedOldTexture = null;
    }
  }
  if ((oldTextureKind || singleKind || preferredKind) && els.randomRealmTextureKind) {
    els.randomRealmTextureKind.value = nextKind;
  }
  selectRandomRealmStagedTextureForKind(nextKind);
  return incoming.length;
}

function randomRealmTextureKindRank(kind) {
  const order = ["base-color", "roughness", "normal", "height", "ambient-occlusion", "metallic", "alpha", "emission"];
  const index = order.indexOf(kind);
  return index === -1 ? order.length : index;
}

function randomRealmTextureSortRank(texture, fallbackIndex = 0) {
  const sortOrder = Number(texture?.sortOrder);
  if (Number.isFinite(sortOrder)) return sortOrder;
  const materialIndex = Number(texture?.materialIndex);
  const materialRank = Number.isFinite(materialIndex) ? materialIndex * 10000 : 0;
  return materialRank + randomRealmTextureKindRank(randomRealmTextureKindFromExisting(texture)) * 100 + fallbackIndex;
}

function sortRandomRealmTextures(textures) {
  return (Array.isArray(textures) ? textures : [])
    .map((texture, index) => ({ texture, index }))
    .sort((left, right) => {
      const rankDelta = randomRealmTextureSortRank(left.texture, left.index) - randomRealmTextureSortRank(right.texture, right.index);
      if (rankDelta) return rankDelta;
      return left.index - right.index;
    })
    .map(item => item.texture);
}

function randomRealmTextureMatchesKind(texture, kind) {
  return randomRealmTextureKindFromExisting(texture) === kind;
}

function randomRealmMaterialForNewMap(object) {
  if (randomRealmSelectedMaterial && randomRealmSelectedMaterial !== "all") {
    return randomRealmSelectedMaterial;
  }
  return randomRealmSelectedOldTexture?.material || randomRealmMaterialForAdd(object);
}

function findRandomRealmOldTextureForKind(object, kind, materialName = "", options = {}) {
  if (randomRealmAddMapMode) return null;
  const textures = Array.isArray(object?.textures) ? object.textures : [];
  const material = materialName || randomRealmSelectedOldTexture?.material || randomRealmMaterialForAdd(object);
  const strictMaterial = Boolean(options.strictMaterial);
  if (
    randomRealmSelectedOldTexture &&
    randomRealmTextureMatchesKind(randomRealmSelectedOldTexture, kind) &&
    (!material || randomRealmSelectedOldTexture.material === material)
  ) {
    return randomRealmSelectedOldTexture;
  }
  const exact = textures.find(texture => texture.material === material && randomRealmTextureMatchesKind(texture, kind));
  if (exact || strictMaterial) return exact || null;
  return textures.find(texture => randomRealmTextureMatchesKind(texture, kind)) || null;
}

function randomRealmStagedTextureKind(texture) {
  return texture?.inferredKind || "";
}

function randomRealmTexturePackageDrafts(object = selectedRandomRealmObject()) {
  if (!object) return [];
  const material = randomRealmMaterialForNewMap(object);
  return randomRealmStagedTextures
    .map((texture, index) => {
      const kind = randomRealmStagedTextureKind(texture);
      const targetMaterial = texture.material
        || texture.inferredMaterial
        || randomRealmInferMaterialFromTextureName(object, texture)
        || material;
      const oldTexture = findRandomRealmOldTextureForKind(object, kind, targetMaterial, { strictMaterial: Boolean(targetMaterial) });
      return {
        index,
        texture,
        kind,
        kindLabel: randomRealmTextureKindLabel(kind),
        material: oldTexture?.material || targetMaterial,
        oldTexture
      };
    })
    .filter(draft => draft.kind)
    .sort((left, right) => randomRealmTextureKindRank(left.kind) - randomRealmTextureKindRank(right.kind) || left.index - right.index);
}

function randomRealmStagedDraftForTexture(drafts, texture) {
  if (!texture || !Array.isArray(drafts)) return null;
  const identity = randomRealmTextureIdentity(texture);
  const kind = randomRealmTextureKindFromExisting(texture);
  const material = texture.material || "";
  return drafts.find(draft => randomRealmTextureIdentity(draft.oldTexture) === identity)
    || drafts.find(draft => draft.kind === kind && (!material || draft.material === material))
    || null;
}

function randomRealmStagedTextureKindLabel(texture) {
  return texture?.inferredKind ? randomRealmTextureKindLabel(texture.inferredKind) : (language === "zh" ? "未识别" : "Unknown");
}

function randomRealmStagedKindSummary(textures) {
  const labels = [];
  const seen = new Set();
  for (const texture of (Array.isArray(textures) ? textures : []).map(randomRealmStagedTextureWithKind)) {
    const label = randomRealmStagedTextureKindLabel(texture);
    if (!seen.has(label)) {
      seen.add(label);
      labels.push(label);
    }
  }
  return labels.join(", ");
}

function randomRealmTexturePackagePayload(object, draft) {
  return {
    project: els.randomRealmBlenderProject?.value || "",
    object: object?.name || "",
    material: draft.material,
    kind: draft.kind,
    oldTexture: draft.oldTexture?.path || "",
    oldMaterial: draft.oldTexture?.material || "",
    oldNode: draft.oldTexture?.node || "",
    newTexture: draft.texture.path
  };
}

function randomRealmTexturePackageKey(object, draft) {
  const payload = randomRealmTexturePackagePayload(object, draft);
  return [
    payload.project,
    payload.object,
    payload.material,
    payload.kind,
    payload.oldTexture,
    payload.oldMaterial,
    payload.oldNode,
    payload.newTexture
  ].join("\u0001");
}

function randomRealmPackagePathKey(value) {
  return String(value || "").replace(/\\/g, "/").toLowerCase();
}

function randomRealmDraftNeedsPackage(object, draft) {
  return draft.texture?.packageStatus !== "packed"
    || draft.texture?.packageKey !== randomRealmTexturePackageKey(object, draft);
}

function randomRealmPackedPackagePaths() {
  return Array.from(new Set(randomRealmStagedTextures
    .map(texture => texture.packagePath || "")
    .filter(Boolean)));
}

function scheduleRandomRealmTextureAutoPack(delay = 160) {
  if (!hasRandomRealmArtTools() || !randomRealmStagedTextures.length) return;
  if (randomRealmTextureAutoPackTimer) {
    window.clearTimeout(randomRealmTextureAutoPackTimer);
  }
  randomRealmTextureAutoPackTimer = window.setTimeout(() => {
    randomRealmTextureAutoPackTimer = null;
    autoPackRandomRealmTextures();
  }, delay);
}

function stopRandomRealmTextureApplyPolling() {
  if (!randomRealmTextureApplyPollTimer) return;
  window.clearTimeout(randomRealmTextureApplyPollTimer);
  randomRealmTextureApplyPollTimer = null;
}

function scheduleRandomRealmTextureApplyPoll(delay = 2600) {
  if (!hasRandomRealmArtTools()
    || !isModuleForeground("blender")
    || !randomRealmPackedPackagePaths().length
    || randomRealmTextureApplyPollTimer) return;
  randomRealmTextureApplyPollTimer = window.setTimeout(() => {
    randomRealmTextureApplyPollTimer = null;
    if (!isModuleForeground("blender")) return;
    pollRandomRealmTextureApplyStatus();
  }, delay);
}

function clearRandomRealmAppliedPackages(appliedPackageKeys) {
  const appliedTexturePaths = new Set();
  const beforeCount = randomRealmStagedTextures.length;
  randomRealmStagedTextures = randomRealmStagedTextures.filter(texture => {
    const shouldClear = appliedPackageKeys.has(randomRealmPackagePathKey(texture.packagePath));
    if (shouldClear && texture.path) appliedTexturePaths.add(texture.path);
    return !shouldClear;
  });
  const clearedCount = beforeCount - randomRealmStagedTextures.length;
  if (!clearedCount) return 0;

  const object = selectedRandomRealmObject();
  if (object && Array.isArray(object.textures) && appliedTexturePaths.size) {
    object.textures = object.textures.filter(texture => !(
      texture.pendingSlot && appliedTexturePaths.has(texture.pendingTexturePath || texture.path)
    ));
  }
  if (randomRealmNewTexture?.path && appliedTexturePaths.has(randomRealmNewTexture.path)) {
    randomRealmNewTexture = null;
  }
  if (!randomRealmStagedTextures.length) {
    randomRealmAddMapMode = false;
  }
  selectRandomRealmStagedTextureForKind();
  if (randomRealmNewTexture?.inferredKind && els.randomRealmTextureKind) {
    els.randomRealmTextureKind.value = randomRealmNewTexture.inferredKind;
  }
  renderRandomRealmUsedTextures();
  return clearedCount;
}

async function pollRandomRealmTextureApplyStatus() {
  if (randomRealmTextureApplyPollInFlight) return;
  const packages = randomRealmPackedPackagePaths();
  if (!packages.length) return;

  randomRealmTextureApplyPollInFlight = true;
  try {
    const payload = await postJson("/api/randomrealm/blender/package-status", { packages });
    const appliedKeys = new Set((Array.isArray(payload.packages) ? payload.packages : [])
      .filter(item => item?.applied)
      .map(item => randomRealmPackagePathKey(item.package)));
    const clearedCount = clearRandomRealmAppliedPackages(appliedKeys);
    if (clearedCount) {
      await refreshRandomRealmSelectedObjectTextures();
      setRandomRealmArtStatus(text("randomRealmTextureAppliedCleared", clearedCount));
    }
  } catch {
    // Keep the panel responsive if the status bridge is unavailable.
  } finally {
    randomRealmTextureApplyPollInFlight = false;
    if (randomRealmPackedPackagePaths().length) {
      scheduleRandomRealmTextureApplyPoll();
    }
  }
}

function selectRandomRealmStagedTexture(texture) {
  if (!texture) return;
  randomRealmNewTexture = texture;
  const kind = randomRealmStagedTextureKind(texture);
  if (kind && els.randomRealmTextureKind) {
    els.randomRealmTextureKind.value = kind;
  }
  if (randomRealmAddMapMode) {
    randomRealmSelectedOldTexture = null;
    renderRandomRealmUsedTextures();
    scheduleRandomRealmTextureAutoPack();
    return;
  }
  const object = selectedRandomRealmObject();
  const oldTexture = kind ? findRandomRealmOldTextureForKind(object, kind) : null;
  if (oldTexture) {
    randomRealmSelectedOldTexture = oldTexture;
  } else if (randomRealmAddMapMode) {
    randomRealmSelectedOldTexture = null;
  }
  renderRandomRealmUsedTextures();
  scheduleRandomRealmTextureAutoPack();
}

function renderRandomRealmStagedTextures() {
  const list = els.randomRealmStagedTextureList;
  if (!list) return;
  list.innerHTML = "";
  list.hidden = true;
}

function randomRealmTextureDisplayName(texture, maxLength = 54) {
  const material = randomRealmMaterialReadableName(texture?.material || "");
  const role = randomRealmTextureRole(texture);
  const label = material ? `${material} - ${role}` : (texture?.file || texture?.name || role);
  return middleEllipsis(label, maxLength);
}

function randomRealmTextureCardFileLabel(texture, maxLength = 42) {
  const file = randomRealmTextureFilename(texture);
  const node = texture?.nodeLabel || texture?.node || "";
  if (!file || file === node) return "";
  return middleEllipsis(file, maxLength);
}

function randomRealmTextureNodeLabel(texture, maxLength = 30) {
  const value = texture?.nodeLabel || texture?.node || texture?.socket || "";
  return value ? middleEllipsis(value, maxLength) : "";
}

function renderRandomRealmTextureSize(node, texture) {
  if (!node) return;
  const value = formatRandomRealmTextureDimensions(texture);
  node.textContent = value;
  node.title = value;
}

function randomRealmTextureStateLabel(texture) {
  if (!texture) return "--";
  if (texture.pendingSlot) return text("randomRealmTextureStatePending");
  return texture.exists ? text("randomRealmTextureStateReady") : text("randomRealmTextureStateMissing");
}

function setRandomRealmInspectorValue(node, value) {
  if (!node) return;
  const textValue = value || "--";
  node.textContent = textValue;
  node.title = textValue === "--" ? "" : textValue;
}

function renderRandomRealmTextureInspector(texture) {
  if (els.randomRealmOldTextureName) {
    els.randomRealmOldTextureName.textContent = texture
      ? randomRealmTextureDisplayName(texture, 52)
      : randomRealmAddMapMode
        ? text("randomRealmNewTextureSlot")
        : text("randomRealmTextureNotSelected");
    els.randomRealmOldTextureName.title = texture?.path || "";
  }
  renderRandomRealmTextureSize(els.randomRealmOldTextureSize, texture);
  renderRandomRealmTexturePreview(
    els.randomRealmOldTexturePreview,
    els.randomRealmOldTexturePreviewEmpty,
    texture
  );
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorMaterial, texture ? randomRealmMaterialReadableName(texture.material || "") : "");
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorRole, texture ? randomRealmTextureRole(texture) : "");
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorNode, texture ? randomRealmTextureNodeLabel(texture, 80) : "");
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorState, texture ? randomRealmTextureStateLabel(texture) : "");
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorFile, texture ? randomRealmTextureFilename(texture) : "");
  setRandomRealmInspectorValue(els.randomRealmTextureInspectorPath, texture?.path || "");
}

function createRandomRealmTextureThumbnail(texture) {
  const thumb = document.createElement("div");
  thumb.className = "texture-card-thumb";
  const path = texture?.path || "";
  if (path && texture?.exists !== false && isRandomRealmPreviewableTexture(path)) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.draggable = false;
    image.src = randomRealmTextureDragUrl(texture);
    image.onerror = () => {
      image.remove();
      const fallback = document.createElement("span");
      fallback.textContent = randomRealmTextureRole(texture);
      thumb.appendChild(fallback);
    };
    thumb.appendChild(image);
  } else {
    const fallback = document.createElement("span");
    fallback.textContent = randomRealmTextureRole(texture);
    thumb.appendChild(fallback);
  }
  return thumb;
}

function randomRealmTextureDimensionWarning(oldTexture, newTexture) {
  const oldDimensions = randomRealmTextureDimensions(oldTexture);
  const newDimensions = randomRealmTextureDimensions(newTexture);
  const oldSize = formatRandomRealmTextureDimensions(oldTexture);
  const newSize = formatRandomRealmTextureDimensions(newTexture);
  if (oldDimensions && newDimensions) {
    if (oldDimensions.width === newDimensions.width && oldDimensions.height === newDimensions.height) {
      return "";
    }
    return text("randomRealmTextureSizeMismatchConfirm", oldSize, newSize);
  }
  return text("randomRealmTextureSizeUnknownConfirm", oldSize, newSize);
}

function uniqueRandomRealmMaterials(object) {
  const names = [];
  const seen = new Set();
  for (const name of Array.isArray(object?.materials) ? object.materials : []) {
    const value = String(name || "").trim();
    if (value && !seen.has(value)) {
      seen.add(value);
      names.push(value);
    }
  }
  for (const texture of Array.isArray(object?.textures) ? object.textures : []) {
    const value = String(texture.material || "").trim();
    if (value && !seen.has(value)) {
      seen.add(value);
      names.push(value);
    }
  }
  return names;
}

function randomRealmMaterialTextureCount(object, materialName) {
  const textures = Array.isArray(object?.textures) ? object.textures : [];
  if (materialName === "all") return textures.length;
  return textures.filter(texture => texture.material === materialName).length;
}

function normalizeRandomRealmSelectedMaterial(object) {
  const materials = uniqueRandomRealmMaterials(object);
  if (materials.length <= 1) {
    randomRealmSelectedMaterial = materials[0] || "all";
    return randomRealmSelectedMaterial;
  }
  if (!materials.includes(randomRealmSelectedMaterial) && randomRealmSelectedMaterial !== "all") {
    randomRealmSelectedMaterial = materials[0];
  }
  if (!randomRealmSelectedMaterial) {
    randomRealmSelectedMaterial = materials[0];
  }
  return randomRealmSelectedMaterial;
}

function filteredRandomRealmTextures(object) {
  const textures = Array.isArray(object?.textures) ? object.textures : [];
  const selectedMaterial = normalizeRandomRealmSelectedMaterial(object);
  const visible = selectedMaterial === "all" ? textures : textures.filter(texture => texture.material === selectedMaterial);
  return sortRandomRealmTextures(visible);
}

function randomRealmMaterialForAdd(object) {
  const selectedMaterial = normalizeRandomRealmSelectedMaterial(object);
  if (selectedMaterial && selectedMaterial !== "all") return selectedMaterial;
  return uniqueRandomRealmMaterials(object)[0] || "";
}

function renderRandomRealmMaterialTabs(object) {
  if (!els.randomRealmMaterialTabs) return;
  const materials = uniqueRandomRealmMaterials(object);
  els.randomRealmMaterialTabs.innerHTML = "";
  if (!object || materials.length <= 1) return;
  const activeMaterial = normalizeRandomRealmSelectedMaterial(object);
  for (const materialName of ["all", ...materials]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `blender-material-tab ${activeMaterial === materialName ? "active" : ""}`;
    button.title = materialName === "all" ? text("randomRealmAllMaterials") : materialName;
    button.addEventListener("click", () => {
      randomRealmSelectedMaterial = materialName;
      randomRealmSelectedOldTexture = null;
      randomRealmAddMapMode = false;
      renderRandomRealmUsedTextures();
      scheduleRandomRealmTextureAutoPack();
    });
    const label = document.createElement("strong");
    label.textContent = materialName === "all" ? text("randomRealmAllMaterials") : randomRealmMaterialDisplayName(materialName, 34);
    button.appendChild(label);
    const count = document.createElement("small");
    count.textContent = String(randomRealmMaterialTextureCount(object, materialName));
    button.appendChild(count);
    els.randomRealmMaterialTabs.appendChild(button);
  }
}

function renderRandomRealmUsedTextures() {
  if (!els.randomRealmUsedTextures) return;
  const object = selectedRandomRealmObject();
  const selectedMaterial = normalizeRandomRealmSelectedMaterial(object);
  renderRandomRealmMaterialTabs(object);
  const allTextures = Array.isArray(object?.textures) ? object.textures : [];
  const textures = filteredRandomRealmTextures(object);
  const stagedDrafts = randomRealmTexturePackageDrafts(object);
  if (els.randomRealmTextureManagerCount) {
    els.randomRealmTextureManagerCount.textContent = text("randomRealmTextureManagerCount", textures.length, allTextures.length);
    els.randomRealmTextureManagerCount.title = selectedMaterial === "all" ? "" : selectedMaterial;
  }
  els.randomRealmUsedTextures.innerHTML = "";
  if (!textures.length) {
    const empty = document.createElement("div");
    empty.className = "dock-empty material-empty";
    if (object && allTextures.length && selectedMaterial !== "all") {
      const name = document.createElement("strong");
      name.textContent = selectedMaterial;
      const message = document.createElement("span");
      message.textContent = text("randomRealmMaterialNoTexture");
      const hint = document.createElement("small");
      hint.textContent = text("randomRealmMaterialNoTextureHint");
      empty.append(name, message, hint);
    } else {
      empty.textContent = text("randomRealmBlenderNoTexture");
    }
    els.randomRealmUsedTextures.appendChild(empty);
    randomRealmSelectedOldTexture = null;
  } else {
    const hasSelectedOldTexture = randomRealmSelectedOldTexture && textures.some(item =>
      item.path === randomRealmSelectedOldTexture.path &&
      item.material === randomRealmSelectedOldTexture.material &&
      item.node === randomRealmSelectedOldTexture.node
    );
    if (randomRealmAddMapMode) {
      randomRealmSelectedOldTexture = null;
    } else if (!hasSelectedOldTexture) {
      randomRealmSelectedOldTexture = textures[0];
    }
    for (const texture of textures) {
      const stagedDraft = randomRealmStagedDraftForTexture(stagedDrafts, texture);
      const card = document.createElement("div");
      const isActive = (
        randomRealmSelectedOldTexture?.path === texture.path &&
        randomRealmSelectedOldTexture?.material === texture.material &&
        randomRealmSelectedOldTexture?.node === texture.node
      ) ||
        Boolean(randomRealmAddMapMode && texture.pendingSlot && randomRealmNewTexture?.path && randomRealmNewTexture.path === texture.pendingTexturePath) ||
        Boolean(stagedDraft && randomRealmNewTexture?.path === stagedDraft.texture.path);
      card.className = `blender-texture-card ${isActive ? "active" : ""} ${texture.pendingSlot ? "pending-slot" : ""} ${stagedDraft ? "has-staged-texture" : ""}`;
      card.role = "button";
      card.tabIndex = 0;
      card.title = texture.path || texture.name;
      const selectTexture = event => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        if (texture.pendingSlot) {
          randomRealmAddMapMode = true;
          randomRealmSelectedOldTexture = null;
          const pendingKind = randomRealmTextureKindFromExisting(texture);
          if (pendingKind && els.randomRealmTextureKind) {
            els.randomRealmTextureKind.value = pendingKind;
            selectRandomRealmStagedTextureForKind(pendingKind);
          }
          renderRandomRealmUsedTextures();
          scheduleRandomRealmTextureAutoPack();
          return;
        }
        randomRealmAddMapMode = false;
        randomRealmSelectedOldTexture = texture;
        const textureKind = randomRealmTextureKindFromExisting(texture);
        if (textureKind && els.randomRealmTextureKind) {
          els.randomRealmTextureKind.value = textureKind;
          selectRandomRealmStagedTextureForKind(textureKind);
        }
        if (stagedDraft) {
          randomRealmNewTexture = stagedDraft.texture;
        }
        renderRandomRealmUsedTextures();
        scheduleRandomRealmTextureAutoPack();
      };
      card.addEventListener("click", selectTexture);
      card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectTexture();
        }
      });
      card.appendChild(createRandomRealmTextureThumbnail(texture));
      const body = document.createElement("div");
      body.className = "texture-card-body";
      const name = document.createElement("strong");
      name.textContent = randomRealmTextureDisplayName(texture);
      body.appendChild(name);
      const meta = document.createElement("span");
      meta.textContent = [
        randomRealmMaterialDisplayName(texture.material || "", 42),
        randomRealmTextureCardFileLabel(texture),
        randomRealmTextureNodeLabel(texture),
        formatRandomRealmTextureDimensions(texture),
        randomRealmTextureStateLabel(texture)
      ].filter(Boolean).join(" - ");
      body.appendChild(meta);
      if (stagedDraft) {
        const staged = document.createElement("div");
        staged.className = `texture-inline-staged ${stagedDraft.texture.packageStatus === "packed" ? "packed" : ""}`;
        const stagedLabel = document.createElement("span");
        stagedLabel.className = "texture-inline-staged-label";
        stagedLabel.textContent = "New";
        const stagedName = document.createElement("strong");
        stagedName.className = "texture-inline-staged-name";
        stagedName.textContent = middleEllipsis(stagedDraft.texture.name, 42);
        const stagedStatus = document.createElement("small");
        stagedStatus.className = "texture-inline-staged-status";
        stagedStatus.textContent = stagedDraft.texture.packageStatus === "packed" ? "Apply pending" : "Auto pack";
        staged.append(stagedLabel, stagedName, stagedStatus);
        body.appendChild(staged);
      }
      card.appendChild(body);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "texture-remove-button";
      remove.setAttribute("aria-label", `Remove ${randomRealmTextureDisplayName(texture, 54)}`);
      remove.textContent = "×";
      remove.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        if (texture.pendingSlot) {
          removeRandomRealmPendingMapSlot(texture);
          return;
        }
        packageRandomRealmTextureRemoval(texture);
      });
      card.appendChild(remove);
      els.randomRealmUsedTextures.appendChild(card);
    }
  }

  renderRandomRealmTextureInspector(randomRealmSelectedOldTexture);
  if (els.randomRealmNewTextureName) {
    els.randomRealmNewTextureName.textContent = randomRealmNewTexture ? middleEllipsis(randomRealmNewTexture.name, 52) : text("randomRealmDropNewTexture");
    els.randomRealmNewTextureName.title = randomRealmNewTexture?.path || "";
  }
  if (els.randomRealmNewTextureDrop) {
    els.randomRealmNewTextureDrop.classList.toggle("has-new-texture", Boolean(randomRealmNewTexture));
  }
  if (els.randomRealmClearNewTexture) {
    els.randomRealmClearNewTexture.hidden = !randomRealmNewTexture;
  }
  renderRandomRealmTextureSize(els.randomRealmNewTextureSize, randomRealmNewTexture);
  renderRandomRealmTexturePreview(
    els.randomRealmNewTexturePreview,
    els.randomRealmNewTexturePreviewEmpty,
    randomRealmNewTexture
  );
  renderRandomRealmStagedTextures();
  updateRandomRealmTextureActionState();
  updateRandomRealmArtContext();
}

function openRandomRealmObjectPicker({ selectText = false } = {}) {
  if (!els.randomRealmObjectSearch || !els.randomRealmBlenderObject) return;
  setRandomRealmObjectPickerOpen(true);
  renderRandomRealmBlenderObjects();
  if (selectText) {
    window.setTimeout(() => els.randomRealmObjectSearch.select(), 0);
  }
}

function confirmRandomRealmObjectSelection() {
  const object = selectedRandomRealmObject();
  if (!object) return;
  randomRealmArtContext.object = object.name;
  randomRealmSelectedOldTexture = null;
  randomRealmSelectedMaterial = "";
  randomRealmAddMapMode = false;
  saveRandomRealmArtContext();
  setRandomRealmObjectPickerOpen(false);
  renderRandomRealmUsedTextures();
  scheduleRandomRealmTextureAutoPack();
  updateBlenderPromptOutput();
}

function clearRandomRealmObjectSearch() {
  if (!els.randomRealmObjectSearch) return;
  els.randomRealmObjectSearch.value = "";
  openRandomRealmObjectPicker();
}

function removeRandomRealmStagedTexture(texture) {
  const removedName = texture?.name || "";
  const removedPath = texture?.path || "";
  if (!removedPath) return;
  randomRealmStagedTextures = randomRealmStagedTextures.filter(item => item.path !== removedPath);
  if (randomRealmNewTexture?.path === removedPath) {
    randomRealmNewTexture = null;
    selectRandomRealmStagedTextureForKind();
  }
  if (!randomRealmStagedTextures.length) {
    randomRealmAddMapMode = false;
  }
  setRandomRealmArtStatus(text("randomRealmTextureStagedRemoved", removedName));
  renderRandomRealmUsedTextures();
}

function randomRealmPendingMapSlotNode(kind) {
  return `Codex ${randomRealmTextureKindLabel(kind)}`;
}

function addRandomRealmPendingMapSlot(object, material, kind, texture) {
  if (!object || !material) return null;
  if (!Array.isArray(object.materials)) {
    object.materials = [];
  }
  if (!object.materials.includes(material)) {
    object.materials.push(material);
  }
  if (!Array.isArray(object.textures)) {
    object.textures = [];
  }
  object.textures = object.textures.filter(item => !(
    item.pendingSlot &&
    item.material === material &&
    randomRealmTextureKindFromExisting(item) === kind
  ));
  const slot = {
    name: texture?.name || `${randomRealmTextureKindLabel(kind)} map`,
    file: texture?.name || `${kind}.png`,
    path: texture?.path || "",
    exists: Boolean(texture?.path),
    material,
    node: randomRealmPendingMapSlotNode(kind),
    width: texture?.width || 2048,
    height: texture?.height || 2048,
    kind,
    pendingSlot: true,
    pendingTexturePath: texture?.path || ""
  };
  object.textures.push(slot);
  return slot;
}

function removeRandomRealmPendingMapSlot(texture) {
  const object = selectedRandomRealmObject();
  const identity = randomRealmTextureIdentity(texture);
  if (!object || !identity) return;
  object.textures = (Array.isArray(object.textures) ? object.textures : [])
    .filter(item => randomRealmTextureIdentity(item) !== identity);
  if (texture?.pendingTexturePath || texture?.path) {
    removeRandomRealmStagedTexture({ path: texture.pendingTexturePath || texture.path, name: texture.name });
  } else {
    renderRandomRealmUsedTextures();
  }
}

function removeRandomRealmOldTextureLocally(texture) {
  const object = selectedRandomRealmObject();
  const identity = randomRealmTextureIdentity(texture);
  if (!object || !identity) return;
  object.textures = (Array.isArray(object.textures) ? object.textures : [])
    .filter(item => randomRealmTextureIdentity(item) !== identity);
  if (randomRealmTextureIdentity(randomRealmSelectedOldTexture) === identity) {
    randomRealmSelectedOldTexture = null;
  }
}

async function packageRandomRealmTextureRemoval(texture) {
  if (randomRealmTextureActionBusy || !texture) return;
  const object = selectedRandomRealmObject();
  if (!object) {
    setRandomRealmArtStatus(text("randomRealmBlenderNoObject"));
    return;
  }
  const kind = randomRealmTextureKindFromExisting(texture) || els.randomRealmTextureKind?.value || "base-color";
  setRandomRealmTextureActionBusy(true);
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const payload = await postJson("/api/randomrealm/blender/package-remove-texture", {
      project: els.randomRealmBlenderProject?.value || "",
      object: object.name,
      material: texture.material || randomRealmMaterialForAdd(object),
      kind,
      oldTexture: texture.path || "",
      oldMaterial: texture.material || "",
      oldNode: texture.node || ""
    });
    const displayName = randomRealmTextureDisplayName(texture, 48);
    removeRandomRealmOldTextureLocally(texture);
    renderRandomRealmUsedTextures();
    setRandomRealmArtStatus(text("randomRealmTextureRemovalPackaged", displayName, payload.name || ""));
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  } finally {
    setRandomRealmTextureActionBusy(false);
    renderRandomRealmUsedTextures();
  }
}

function clearRandomRealmNewTexture() {
  const currentPath = randomRealmNewTexture?.path || "";
  if (currentPath) {
    randomRealmStagedTextures = randomRealmStagedTextures.filter(texture => texture.path !== currentPath);
  } else {
    randomRealmStagedTextures = [];
  }
  randomRealmNewTexture = null;
  if (!randomRealmStagedTextures.length) {
    randomRealmAddMapMode = false;
  }
  selectRandomRealmStagedTextureForKind();
  if (randomRealmNewTexture?.inferredKind && els.randomRealmTextureKind) {
    els.randomRealmTextureKind.value = randomRealmNewTexture.inferredKind;
  }
  if (els.randomRealmTextureFileInput) {
    els.randomRealmTextureFileInput.value = "";
  }
  setRandomRealmArtStatus(text("randomRealmArtReady"));
  renderRandomRealmUsedTextures();
}

async function loadRandomRealmBlenderProjects(options = {}) {
  if (!hasRandomRealmArtTools()) return;
  const loadObjects = options.loadObjects !== false;
  const query = (els.randomRealmProjectSearch?.value || "").trim();
  const limit = Math.max(0, Math.min(100, Number(options.limit) || 0));
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (limit) params.set("limit", String(limit));
    const url = `/api/randomrealm/blender/projects${params.size ? `?${params}` : ""}`;
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    randomRealmBlenderProjects = Array.isArray(payload.projects) ? payload.projects : [];
    renderRandomRealmBlenderProjects();
    if (els.randomRealmBlenderProject.value) {
      if (loadObjects) {
        await loadRandomRealmBlenderObjects();
      } else {
        randomRealmBlenderObjects = [];
        renderRandomRealmBlenderObjects();
        setRandomRealmArtStatus(text("randomRealmBlenderProjectLoaded", randomRealmBlenderProjects.length));
      }
    } else {
      renderRandomRealmBlenderObjects();
      setRandomRealmArtStatus(text("randomRealmBlenderNoProject"));
    }
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  }
}

function scheduleRandomRealmProjectSearch() {
  if (randomRealmProjectSearchTimer) {
    window.clearTimeout(randomRealmProjectSearchTimer);
  }
  randomRealmProjectSearchTimer = window.setTimeout(() => {
    randomRealmProjectSearchTimer = null;
    loadRandomRealmBlenderProjects({ loadObjects: false });
  }, 260);
}

async function loadRandomRealmBlenderObjects() {
  if (!hasRandomRealmArtTools()) return;
  const project = els.randomRealmBlenderProject.value;
  if (!project) return;
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  randomRealmSelectedOldTexture = null;
  randomRealmSelectedMaterial = "";
  randomRealmNewTexture = null;
  randomRealmStagedTextures = [];
  randomRealmAddMapMode = false;
  randomRealmLoadedObjectsProject = "";
  try {
    const payload = await postJson("/api/randomrealm/blender/objects", { project });
    randomRealmBlenderObjects = Array.isArray(payload.objects) ? payload.objects : [];
    randomRealmLoadedObjectsProject = project;
    renderRandomRealmBlenderObjects();
    const synced = await syncRandomRealmLiveSelection({ quiet: true });
    if (!synced) {
      setRandomRealmArtStatus(text("randomRealmBlenderObjectLoaded", randomRealmBlenderObjects.length));
    }
  } catch (error) {
    randomRealmBlenderObjects = [];
    randomRealmLoadedObjectsProject = "";
    renderRandomRealmBlenderObjects();
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  }
}

async function refreshRandomRealmSelectedObjectTextures() {
  if (!hasRandomRealmArtTools() || randomRealmTextureActionBusy) return;
  const project = els.randomRealmBlenderProject?.value || "";
  const currentObject = selectedRandomRealmObject();
  const objectName = currentObject?.name || els.randomRealmBlenderObject?.value || randomRealmArtContext.object || "";
  if (!project || !objectName) {
    setRandomRealmArtStatus(text("randomRealmBlenderNoObject"));
    return;
  }

  const previousMaterial = randomRealmSelectedMaterial;
  const previousTextureIdentity = randomRealmTextureIdentity(randomRealmSelectedOldTexture);
  setRandomRealmTextureActionBusy(true);
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const payload = await postJson("/api/randomrealm/blender/objects", { project });
    const nextObjects = Array.isArray(payload.objects) ? payload.objects : [];
    randomRealmBlenderObjects = nextObjects;
    const refreshedObject = nextObjects.find(item => item.name === objectName) || null;
    if (refreshedObject) {
      randomRealmArtContext.object = refreshedObject.name;
      if (els.randomRealmBlenderObject) {
        els.randomRealmBlenderObject.value = refreshedObject.name;
      }
      const materials = uniqueRandomRealmMaterials(refreshedObject);
      randomRealmSelectedMaterial = previousMaterial === "all" || materials.includes(previousMaterial)
        ? previousMaterial
        : "";
      const refreshedTextures = Array.isArray(refreshedObject.textures) ? refreshedObject.textures : [];
      randomRealmSelectedOldTexture = refreshedTextures.find(item => randomRealmTextureIdentity(item) === previousTextureIdentity) || null;
    } else {
      randomRealmSelectedOldTexture = null;
      randomRealmSelectedMaterial = "";
    }
    randomRealmAddMapMode = false;
    saveRandomRealmArtContext();
    renderRandomRealmBlenderObjects();
    const activeObject = selectedRandomRealmObject();
    const count = Array.isArray(activeObject?.textures) ? activeObject.textures.length : 0;
    setRandomRealmArtStatus(text("randomRealmTexturesRefreshed", activeObject?.name || objectName, count));
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  } finally {
    setRandomRealmTextureActionBusy(false);
    renderRandomRealmUsedTextures();
  }
}

async function uploadRandomRealmNewTexture(files) {
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;
  let shouldAutoPack = false;
  const formData = new FormData();
  selectedFiles.forEach(file => formData.append("file", file, file.name));
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const response = await fetch("/api/randomrealm/blender/upload-texture", {
      method: "POST",
      body: formData
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const uploaded = Array.isArray(payload.files) ? payload.files : [];
    const addedCount = addRandomRealmStagedTextures(uploaded);
    shouldAutoPack = addedCount > 0;
    renderRandomRealmUsedTextures();
    if (addedCount > 1) {
      setRandomRealmArtStatus(text(
        "randomRealmTextureUploadedMany",
        addedCount,
        randomRealmStagedKindSummary(uploaded)
      ));
    } else {
      setRandomRealmArtStatus(text("randomRealmTextureUploaded", randomRealmNewTexture?.name || selectedFiles[0].name));
    }
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  } finally {
    if (els.randomRealmTextureFileInput) els.randomRealmTextureFileInput.value = "";
    els.randomRealmNewTextureDrop?.classList.remove("drag-over");
  }
  if (shouldAutoPack) {
    scheduleRandomRealmTextureAutoPack();
  }
}

async function stageRandomRealmBlankTexture() {
  if (randomRealmTextureActionBusy) return;
  const object = selectedRandomRealmObject();
  if (!object) {
    setRandomRealmArtStatus(text("randomRealmBlenderNoObject"));
    return;
  }
  const kind = els.randomRealmTextureKind?.value || "base-color";
  const material = randomRealmMaterialForNewMap(object);
  let shouldAutoPack = false;
  randomRealmAddMapMode = true;
  randomRealmSelectedOldTexture = null;
  setRandomRealmTextureActionBusy(true);
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const payload = await postJson("/api/randomrealm/blender/stage-blank-texture", {
      project: els.randomRealmBlenderProject?.value || "",
      object: object.name,
      material,
      kind,
      size: 2048
    });
    const files = Array.isArray(payload.files) ? payload.files : [payload.texture].filter(Boolean);
    addRandomRealmStagedTextures(files, kind);
    addRandomRealmPendingMapSlot(object, material, kind, randomRealmNewTexture || files[0]);
    shouldAutoPack = files.length > 0;
    renderRandomRealmUsedTextures();
    setRandomRealmArtStatus(text("randomRealmBlankTextureStaged", randomRealmNewTexture?.name || files[0]?.name || kind));
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  } finally {
    setRandomRealmTextureActionBusy(false);
  }
  if (shouldAutoPack) {
    scheduleRandomRealmTextureAutoPack();
  }
}

async function autoPackRandomRealmTextures() {
  if (!hasRandomRealmArtTools() || !randomRealmStagedTextures.length) return;
  if (randomRealmTextureActionBusy) {
    scheduleRandomRealmTextureAutoPack(260);
    return;
  }

  const object = selectedRandomRealmObject();
  const drafts = randomRealmTexturePackageDrafts(object)
    .filter(draft => randomRealmDraftNeedsPackage(object, draft));
  if (!object || !drafts.length) {
    scheduleRandomRealmTextureApplyPoll();
    return;
  }

  setRandomRealmTextureActionBusy(true);
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  const packed = [];
  const failed = [];
  try {
    for (const draft of drafts) {
      const packageKey = randomRealmTexturePackageKey(object, draft);
      try {
        const payload = await postJson(
          "/api/randomrealm/blender/package-texture",
          randomRealmTexturePackagePayload(object, draft)
        );
        Object.assign(draft.texture, {
          packageStatus: "packed",
          packageKey,
          packagePath: payload.package || "",
          manifestPath: payload.manifest || "",
          packageName: payload.name || "",
          packageRootKind: payload.packageRootKind || ""
        });
        packed.push({ draft, payload });
      } catch (error) {
        failed.push(`${draft.kindLabel}: ${error.message}`);
      }
    }
    renderRandomRealmUsedTextures();
    if (packed.length) {
      const location = packed[0]?.payload?.packageRootKind === "project-textures" ? "Blender textures" : "package folder";
      setRandomRealmArtStatus(text("randomRealmTextureAutoPackedMany", packed.length, location));
      scheduleRandomRealmTextureApplyPoll(900);
    }
    if (failed.length) {
      throw new Error(failed.join("; "));
    }
  } catch (error) {
    setRandomRealmArtStatus(text("randomRealmBlenderActionFailed", error.message));
  } finally {
    setRandomRealmTextureActionBusy(false);
    renderRandomRealmUsedTextures();
  }
}

function createWorkspaceTodoId(prefix) {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function workspaceTodoGroupTitle(group) {
  if (group.labelKey) return text(group.labelKey);
  return group.title || "Todo";
}

function workspaceTodoItemText(item) {
  if (item.text) return item.text;
  return item.textKey ? text(item.textKey) : "";
}

function workspaceTodoTotals(group = null) {
  const groups = group ? [group] : workspaceTodoGroups;
  const total = groups.reduce((sum, item) => sum + item.items.length, 0);
  const done = groups.reduce((sum, item) => sum + item.items.filter(todo => todo.done).length, 0);
  return { done, total };
}

function pruneEmptyWorkspaceTodoGroups() {
  const next = workspaceTodoGroups.filter(group =>
    Array.isArray(group.items) &&
    group.items.length > 0
  );
  if (next.length !== workspaceTodoGroups.length) {
    workspaceTodoGroups = next;
    return true;
  }
  return false;
}

function renderWorkspaceTodoCategoryOptions(selectedId = "") {
  if (!els.workspaceTodoCategory) return;
  const activeId = selectedId || els.workspaceTodoCategory.value || workspaceTodoGroups[0]?.id || "";
  els.workspaceTodoCategory.innerHTML = "";
  for (const group of workspaceTodoGroups) {
    const option = document.createElement("option");
    option.value = group.id;
    option.textContent = workspaceTodoGroupTitle(group);
    els.workspaceTodoCategory.appendChild(option);
  }
  if (workspaceTodoGroups.some(group => group.id === activeId)) {
    els.workspaceTodoCategory.value = activeId;
  }
}

function renderWorkspaceTodos() {
  if (!hasWorkspace || !els.workspaceTodoList) return;
  const pruned = pruneEmptyWorkspaceTodoGroups();
  if (pruned) saveWorkspaceTodos();
  renderWorkspaceTodoCategoryOptions();

  const totals = workspaceTodoTotals();
  if (els.workspaceTodoCount) {
    els.workspaceTodoCount.textContent = text("workspaceTodoProgress", totals.done, totals.total);
  }

  els.workspaceTodoList.innerHTML = "";
  for (const group of workspaceTodoGroups) {
    const groupTotals = workspaceTodoTotals(group);
    const card = document.createElement("article");
    card.className = "todo-group";

    const head = document.createElement("div");
    head.className = "todo-group-head";

    const title = document.createElement("strong");
    title.textContent = workspaceTodoGroupTitle(group);
    head.appendChild(title);

    const count = document.createElement("span");
    count.textContent = text("workspaceTodoProgress", groupTotals.done, groupTotals.total);
    head.appendChild(count);
    card.appendChild(head);

    const list = document.createElement("div");
    list.className = "todo-items";

    if (!group.items.length) {
      const empty = document.createElement("div");
      empty.className = "todo-empty";
      empty.textContent = text("todoEmptyGroup");
      list.appendChild(empty);
    }

    for (const item of group.items) {
      const row = document.createElement("div");
      row.className = `todo-item ${item.done ? "done" : ""}`;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = item.done;
      checkbox.addEventListener("change", () => toggleWorkspaceTodo(group.id, item.id, checkbox.checked));
      row.appendChild(checkbox);

      const label = document.createElement("span");
      label.className = "todo-text";
      label.textContent = workspaceTodoItemText(item);
      row.appendChild(label);

      const deleteButton = document.createElement("button");
      deleteButton.className = "todo-delete";
      deleteButton.type = "button";
      deleteButton.textContent = "\u00d7";
      deleteButton.title = text("todoDeleteLabel", workspaceTodoItemText(item));
      deleteButton.setAttribute("aria-label", text("todoDeleteLabel", workspaceTodoItemText(item)));
      deleteButton.addEventListener("click", () => deleteWorkspaceTodo(group.id, item.id));
      row.appendChild(deleteButton);

      list.appendChild(row);
    }

    card.appendChild(list);
    els.workspaceTodoList.appendChild(card);
  }
}

function addWorkspaceTodo() {
  if (!els.workspaceTodoInput || !els.workspaceTodoCategory) return;
  const value = els.workspaceTodoInput.value.trim();
  if (!value) return;

  const groupId = els.workspaceTodoCategory.value || workspaceTodoGroups[0]?.id;
  const group = workspaceTodoGroups.find(item => item.id === groupId);
  if (!group) return;

  group.items.push({
    id: createWorkspaceTodoId("todo"),
    text: value,
    textKey: "",
    done: false
  });
  els.workspaceTodoInput.value = "";
  saveWorkspaceTodos();
  renderWorkspaceTodos();
}

function toggleWorkspaceTodo(groupId, itemId, done) {
  const group = workspaceTodoGroups.find(item => item.id === groupId);
  const todo = group?.items.find(item => item.id === itemId);
  if (!todo) return;
  todo.done = Boolean(done);
  saveWorkspaceTodos();
  renderWorkspaceTodos();
}

function deleteWorkspaceTodo(groupId, itemId) {
  const group = workspaceTodoGroups.find(item => item.id === groupId);
  if (!group) return;
  group.items = group.items.filter(item => item.id !== itemId);
  pruneEmptyWorkspaceTodoGroups();
  saveWorkspaceTodos();
  renderWorkspaceTodos();
}

async function postJson(path, payload = {}, options = {}) {
  const controller = options.timeoutMs ? new AbortController() : null;
  const timer = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs) : null;
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller?.signal
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("request timed out");
    }
    throw error;
  } finally {
    if (timer) window.clearTimeout(timer);
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || `HTTP ${response.status}`);
  }
  return result;
}

async function uploadWallpaperFiles(files) {
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;

  const formData = new FormData();
  for (const file of selectedFiles) {
    formData.append("files", file, file.name);
  }

  els.addWallpaper.disabled = true;
  try {
    const response = await fetch("/api/wallpapers/upload", {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    wallpapers = Array.isArray(result.wallpapers) ? result.wallpapers : wallpapers;
    if (result.files && result.files[0]) {
      selectedWallpaperPath = result.files[0].path;
      localStorage.setItem(storageKeys.selectedWallpaper, selectedWallpaperPath);
    }
    setStatus(text("added", result.files.length));
    renderWallpapers();
  } catch (error) {
    setStatus(text("uploadFailed", error.message));
  } finally {
    els.addWallpaper.disabled = false;
    els.wallpaperFileInput.value = "";
  }
}

function openAddWallpaperPicker() {
  els.wallpaperFileInput.click();
}

async function uploadMusicFiles(files) {
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;

  const formData = new FormData();
  for (const file of selectedFiles) {
    formData.append("files", file, file.name);
  }

  setMusicImportBusy(true);
  try {
    const response = await fetch("/api/music/upload", {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks;
    if (result.files && result.files[0]) {
      setSelectedTrackPath(result.files[0].path, { persist: "now" });
    }
    const audioCount = Array.isArray(result.files) ? result.files.length : 0;
    const lyricsCount = Array.isArray(result.lyrics) ? result.lyrics.length : 0;
    musicNotice = audioCount ? text("musicAdded", audioCount) : text("musicLyricsAdded", lyricsCount);
    if (selectedTrackPath) {
      musicLyricsTrackPath = "";
      musicLyricsAnalysis = null;
    }
    renderMusic();
  } catch (error) {
    musicNotice = text("musicUploadFailed", error.message);
    renderMusic();
  } finally {
    setMusicImportBusy(false);
    els.musicFileInput.value = "";
  }
}

function openAddMusicPicker() {
  setMusicAddMenuOpen(false);
  els.musicFileInput.click();
}

async function uploadMusicCookieFile(files) {
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;

  const formData = new FormData();
  formData.append("file", selectedFiles[0], selectedFiles[0].name);

  setMusicImportBusy(true);
  try {
    const response = await fetch("/api/music/cookies", {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    musicCookieState = result.cookies || { available: false };
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks;
    setMusicLinkStatus(text("musicCookieUploaded"));
    setMusicLibraryStatus(text("musicCookieUploaded"));
    renderMusic();
    renderMusicLibraries();
  } catch (error) {
    setMusicLinkStatus(text("musicCookieUploadFailed", error.message));
    setMusicLibraryStatus(text("musicCookieUploadFailed", error.message));
  } finally {
    setMusicImportBusy(false);
    if (els.musicCookieFileInput) els.musicCookieFileInput.value = "";
  }
}

function textFromDroppedHtml(value) {
  const match = String(value || "").match(/href=["']([^"']+)["']/i);
  if (!match) return "";
  return match[1].replace(/&amp;/g, "&");
}

function firstUrlFromText(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";

  for (const line of raw.split(/\r?\n/)) {
    const item = line.trim();
    if (item && !item.startsWith("#") && /^https?:\/\//i.test(item)) {
      return item;
    }
  }

  const match = raw.match(/https?:\/\/[^\s"'<>]+/i);
  return match ? match[0].replace(/[),.;]+$/, "") : "";
}

function extractDroppedUrl(dataTransfer) {
  if (!dataTransfer) return "";
  const formats = ["text/uri-list", "text/plain", "text", "URL"];
  for (const format of formats) {
    const url = firstUrlFromText(dataTransfer.getData(format));
    if (url) return url;
  }
  return firstUrlFromText(textFromDroppedHtml(dataTransfer.getData("text/html")));
}

function musicProviderForUrl(url) {
  try {
    const host = new URL(url).hostname.replace(/^www\./i, "").toLowerCase();
    if (host === "youtu.be" || host.endsWith("youtube.com")) return "YouTube";
    return host || "URL";
  } catch {
    return "URL";
  }
}

async function importMusicUrl(url, useBrowserCookies = false) {
  const cleanUrl = firstUrlFromText(url);
  if (!cleanUrl) {
    setMusicLinkStatus(text("musicLinkEmpty"));
    return;
  }

  const provider = musicProviderForUrl(cleanUrl);
  setMusicLinkStatus(text("musicLinkChecking", provider));
  setMusicImportBusy(true);

  try {
    const result = await postJson("/api/music/import-url", { url: cleanUrl, useBrowserCookies });
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks;
    musicCookieState = result.cookies || musicCookieState;
    if (result.files && result.files[0]) {
      setSelectedTrackPath(result.files[0].path, { persist: "now" });
      musicNotice = text("musicLinkImported", displayTrackName(result.files[0].name));
    } else {
      musicNotice = text("musicLinkPrepared", provider);
    }
    const input = document.getElementById("musicLinkInput");
    if (input) input.value = "";
    if (els.musicAddUrlInput) els.musicAddUrlInput.value = "";
    setMusicLinkStatus(musicNotice);
    renderMusic();
  } catch (error) {
    setMusicLinkStatus(text("musicLinkFailed", error.message));
  } finally {
    setMusicImportBusy(false);
  }
}

async function importMusicLibrary(url, name = "") {
  const cleanUrl = firstUrlFromText(url);
  if (!cleanUrl) {
    setMusicLibraryStatus(text("musicLinkEmpty"));
    return;
  }

  const provider = musicProviderForUrl(cleanUrl);
  setMusicLibraryStatus(text("musicLibraryImporting", provider));
  setMusicImportBusy(true);

  try {
    const result = await postJson("/api/music/library/import", { url: cleanUrl, name });
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks;
    musicLibraries = Array.isArray(result.libraries) ? result.libraries : musicLibraries;
    libraryTracks = flattenLibraryTracks(musicLibraries);
    const libraryName = result.library?.name || provider;
    setMusicLibraryStatus(text("musicLibraryStarted", libraryName));
    const input = document.getElementById("musicLibraryLinkInput");
    if (input) input.value = "";
    if (els.musicAddLibraryInput) els.musicAddLibraryInput.value = "";
    renderMusic();
    renderMusicLibraries();
    scheduleMusicLibraryPoll();
  } catch (error) {
    setMusicLibraryStatus(text("musicLibraryFailed", error.message));
    renderMusicLibraries();
  } finally {
    setMusicImportBusy(false);
  }
}

function handleMusicUrlDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget?.classList.remove("drag-over");

  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length) {
    if (files.length === 1 && /\.txt$/i.test(files[0].name || "")) {
      uploadMusicCookieFile(files);
      return;
    }
    uploadMusicFiles(files);
    return;
  }

  importMusicUrl(extractDroppedUrl(event.dataTransfer));
}

function handleMusicLibraryDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget?.classList.remove("drag-over");

  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length) {
    if (files.length === 1 && /\.txt$/i.test(files[0].name || "")) {
      uploadMusicCookieFile(files);
    }
    return;
  }

  importMusicLibrary(extractDroppedUrl(event.dataTransfer));
}

function libraryTrackPathFromTransfer(dataTransfer) {
  if (!dataTransfer) return "";
  return dataTransfer.getData("application/x-control-library-track") || "";
}

function transferHasLibraryTrack(dataTransfer) {
  return Array.from(dataTransfer?.types || []).includes("application/x-control-library-track");
}

async function promoteLibraryTrack(path, tierId = "third", beforePath = "") {
  if (!path) return;
  setMusicImportBusy(true);
  try {
    const result = await postJson("/api/music/promote", { path });
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks;
    musicLibraries = Array.isArray(result.libraries) ? result.libraries : musicLibraries;
    if (result.file?.path) {
      markPromotedLibraryTrack(path, result.file.path);
      moveTrackToTier(result.file.path, tierId, beforePath);
      setSelectedTrackPath(result.file.path, { persist: "now" });
      musicNotice = text("musicPromoted", displayTrackName(result.file.name));
    }
    libraryTracks = flattenLibraryTracks(musicLibraries);
    renderMusic();
    renderMusicLibraries();
  } catch (error) {
    musicNotice = text("musicPromoteFailed", error.message);
    renderMusic();
  } finally {
    setMusicImportBusy(false);
  }
}

function handleLocalMusicDragOver(event) {
  if (!transferHasLibraryTrack(event.dataTransfer)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  els.musicDock.classList.add("drag-over");
}

function handleLocalMusicDragLeave(event) {
  if (!els.musicDock.contains(event.relatedTarget)) {
    els.musicDock.classList.remove("drag-over");
  }
}

function handleLocalMusicDrop(event) {
  if (!transferHasLibraryTrack(event.dataTransfer)) return;
  event.preventDefault();
  event.stopPropagation();
  els.musicDock.classList.remove("drag-over");
  promoteLibraryTrack(libraryTrackPathFromTransfer(event.dataTransfer), lastVisibleMusicTier());
}

async function deleteWallpaper(item) {
  if (!item) return;

  try {
    const result = await postJson("/api/wallpapers/delete", { path: item.path });
    wallpapers = Array.isArray(result.wallpapers) ? result.wallpapers : wallpapers.filter(wallpaper => wallpaper.path !== item.path);
    pendingDeletePath = "";
    if (selectedWallpaperPath === item.path) {
      selectedWallpaperPath = "";
      localStorage.removeItem(storageKeys.selectedWallpaper);
    }
    setStatus(text("deleted", item.name));
    renderWallpapers();
  } catch (error) {
    setStatus(text("deleteFailed", error.message));
  }
}

async function deleteTrack(item) {
  if (!item) return;
  const wasCurrentTrack = selectedTrackPath === item.path || audioIsTrack(item);
  const wasPlaying = wasCurrentTrack && !els.audioPlayer.paused && !els.audioPlayer.ended;
  const nextPath = wasCurrentTrack ? nextTrackPathAfterDelete(item.path) : "";

  try {
    const result = await postJson("/api/music/delete", { path: item.path });
    tracks = Array.isArray(result.tracks) ? result.tracks : tracks.filter(track => track.path !== item.path);
    musicLibraries = Array.isArray(result.libraries) ? result.libraries : musicLibraries;
    libraryTracks = flattenLibraryTracks(musicLibraries);
    const hadTier = Boolean(musicTierAssignments[item.path]);
    if (hadTier) {
      delete musicTierAssignments[item.path];
    }
    const nextOrder = musicTierOrder.filter(path => path !== item.path);
    const orderChanged = nextOrder.length !== musicTierOrder.length;
    if (orderChanged) {
      musicTierOrder = nextOrder;
    }
    if (hadTier || orderChanged) saveMusicTierAssignments();
    pendingDeleteTrackPath = "";
    if (wasCurrentTrack) {
      const nextTrack = allMusicTracks().find(track => track.path === nextPath) || null;
      if (els.audioPlayer.src) {
        els.audioPlayer.pause();
        els.audioPlayer.removeAttribute("src");
        els.audioPlayer.load();
      }
      if (nextTrack) {
        setSelectedTrackPath(nextTrack.path, { persist: "now" });
      } else {
        setSelectedTrackPath("", { persist: "now" });
      }
    }
    musicNotice = text("musicDeleted", displayTrackName(item.name));
    renderMusic();
    renderMusicLibraries();
    if (wasPlaying) {
      const nextTrack = allMusicTracks().find(track => track.path === selectedTrackPath) || null;
      if (nextTrack) {
        await playTrack(nextTrack);
      }
    }
  } catch (error) {
    musicNotice = text("deleteFailed", error.message);
    renderMusic();
    renderMusicLibraries();
  }
}

async function applyWallpaper(item = selectedWallpaper()) {
  if (!item) return;
  try {
    const result = await postJson("/api/wallpapers/apply", { path: item.path });
    setSelectedWallpaper(item.path);
    setStatus(text("applied", item.name));
    if (result.original) {
      // The service still protects the original wallpaper; the UI stays intentionally minimal.
    }
  } catch (error) {
    setStatus(text("applyFailed", error.message));
  }
}

async function playTrack(item = selectedTrack()) {
  if (!item) return;
  const shouldRefreshLyrics = Boolean(musicLyricsTrackPath);
  setSelectedTrackPath(item.path, { persist: "now" });

  const nextUrl = new URL(item.url, window.location.href).href;
  if (els.audioPlayer.src !== nextUrl) {
    els.audioPlayer.src = item.url;
    els.audioPlayer.load();
  }

  try {
    await els.audioPlayer.play();
    musicNotice = "";
    renderMusic();
    if (shouldRefreshLyrics) {
      loadLyricsForTrack(item);
    }
  } catch (error) {
    musicNotice = text("musicPlayFailed", error.message);
    renderMusic();
    if (shouldRefreshLyrics) {
      loadLyricsForTrack(item);
    }
  }
}

async function togglePlayback() {
  const item = selectedTrack();
  if (!item) return;

  if (!els.audioPlayer.src || els.audioPlayer.src !== new URL(item.url, window.location.href).href) {
    await playTrack(item);
    return;
  }

  if (els.audioPlayer.paused) {
    await playTrack(item);
  } else {
    els.audioPlayer.pause();
    renderMusic();
  }
}

function relativeTrack(offset, wrap = true) {
  const playable = allMusicTracks();
  if (!playable.length) return null;
  const baseIndex = currentTrackIndex();
  const rawIndex = baseIndex + offset;
  if (!wrap && (rawIndex < 0 || rawIndex >= playable.length)) return null;
  const nextIndex = (rawIndex + playable.length) % playable.length;
  return playable[nextIndex] || null;
}

function playRelativeTrack(offset, { wrap = true } = {}) {
  const next = relativeTrack(offset, wrap);
  if (next) playTrack(next);
}

function resetEndedTrackToStart() {
  if (!els.audioPlayer) return;
  pendingSeekRatio = null;
  try {
    els.audioPlayer.currentTime = 0;
  } catch {
    return;
  }
  setTrackSeekVisualRatio(0);
  updateLyricsProgress(0);
}

function handleTrackEnded() {
  const item = selectedTrack();
  if (playbackMode === "playOnce") {
    resetEndedTrackToStart();
    renderMusic();
    updateTrackProgress();
    return;
  }
  if (playbackMode === "repeatOne" && item) {
    els.audioPlayer.currentTime = 0;
    playTrack(item);
    return;
  }
  const next = relativeTrack(1, playbackMode === "repeatAll");
  if (next) {
    playTrack(next);
    return;
  }
  renderMusic();
  updateTrackProgress();
}

function audioDuration() {
  const duration = els.audioPlayer.duration;
  return Number.isFinite(duration) && duration > 0 ? duration : 0;
}

function currentAudioSeekRatio() {
  const duration = audioDuration();
  if (duration <= 0) return trackSeekRatio();
  const current = Number.isFinite(els.audioPlayer.currentTime) ? els.audioPlayer.currentTime : 0;
  return clamp(current / duration, 0, 1);
}

function trackSeekRatio() {
  return clamp(Number(els.trackSeek.value) || 0, 0, 100) / 100;
}

function trackSeekRatioFromPointer(event) {
  if (!event || typeof event.clientX !== "number") return null;
  const rect = els.trackSeek.getBoundingClientRect();
  if (!rect.width) return null;
  return clamp((event.clientX - rect.left) / rect.width, 0, 1);
}

function setPendingTrackSeek(ratio) {
  pendingSeekRatio = clamp(Number(ratio) || 0, 0, 1);
  els.trackSeek.value = String(pendingSeekRatio * 100);
  previewTrackSeek(pendingSeekRatio);
}

function previewTrackSeek(ratio = trackSeekRatio()) {
  const duration = audioDuration();
  const previewTime = duration > 0 ? clamp(ratio, 0, 1) * duration : 0;
  els.trackCurrentTime.textContent = formatDuration(previewTime);
  els.trackDuration.textContent = formatDuration(duration);
}

function setTrackSeekVisualRatio(ratio) {
  const cleanRatio = clamp(Number(ratio) || 0, 0, 1);
  els.trackSeek.value = String(cleanRatio * 100);
  previewTrackSeek(cleanRatio);
}

function commitTrackSeek(ratio = trackSeekRatio()) {
  const duration = audioDuration();
  const cleanRatio = clamp(Number(ratio) || 0, 0, 1);

  if (duration <= 0) {
    pendingSeekRatio = cleanRatio;
    previewTrackSeek(cleanRatio);
    return;
  }

  pendingSeekRatio = null;
  const nextTime = cleanRatio * duration;
  try {
    if (typeof els.audioPlayer.fastSeek === "function") {
      els.audioPlayer.fastSeek(nextTime);
    } else {
      els.audioPlayer.currentTime = nextTime;
    }
  } catch {
    try {
      els.audioPlayer.currentTime = nextTime;
    } catch {
      return;
    }
  }

  els.trackSeek.value = String(cleanRatio * 100);
  els.trackCurrentTime.textContent = formatDuration(nextTime);
  els.trackDuration.textContent = formatDuration(duration);
}

function seekTrackBySeconds(deltaSeconds = 0) {
  if (!hasMusic || !selectedTrackPath || !els.audioPlayer) return false;
  const duration = audioDuration();
  if (duration <= 0) return false;
  const current = Number.isFinite(els.audioPlayer.currentTime) ? els.audioPlayer.currentTime : 0;
  const beforeRatio = currentAudioSeekRatio();
  const nextTime = clamp(current + Number(deltaSeconds || 0), 0, duration);
  const nextRatio = duration > 0 ? nextTime / duration : 0;
  cancelSmoothValueAnimation("seek");
  userSeeking = false;
  pendingSeekRatio = null;
  commitTrackSeek(nextRatio);
  recordTrackSeekChange(beforeRatio, nextRatio);
  updateTrackProgress();
  return true;
}

function shouldIgnoreMusicSeekKeydown(event) {
  if (!hasMusic || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return true;
  const target = event.target;
  if (!target || target === document.body || target === document.documentElement) return false;
  if (target === els.trackSeek) return false;
  if (target === els.trackVolume) return true;
  if (target.isContentEditable) return true;
  if (target.closest?.("[contenteditable='true']")) return true;
  if (target.closest?.("input, textarea, select")) return true;
  return false;
}

function shouldIgnoreMusicPlaybackKeydown(event) {
  if (!hasMusic || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return true;
  const target = event.target;
  if (!target || target === document.body || target === document.documentElement) return false;
  if (target.isContentEditable) return true;
  if (target.closest?.("[contenteditable='true']")) return true;
  if (target.closest?.("input, textarea, select")) return true;
  if (target.closest?.(".lyrics-timing-editor")) return false;
  if (target.closest?.("button, a, [role='button'], [role='link']")) return true;
  return false;
}

function handleMusicPlaybackKeydown(event) {
  if (event.key !== " " && event.key !== "Spacebar" && event.code !== "Space") return false;
  if (shouldIgnoreMusicPlaybackKeydown(event)) return false;
  event.preventDefault();
  if (!event.repeat) togglePlayback();
  return true;
}

function handleMusicSeekKeydown(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return false;
  if (shouldIgnoreMusicSeekKeydown(event)) return false;
  const direction = event.key === "ArrowRight" ? 1 : -1;
  if (!seekTrackBySeconds(direction * musicKeyboardSeekSeconds)) return false;
  event.preventDefault();
  return true;
}

function animateNumberValue(key, from, to, duration, onValue, onFinish) {
  const start = Number(from) || 0;
  const end = Number(to) || 0;
  const distance = end - start;
  cancelSmoothValueAnimation(key);
  if (Math.abs(distance) < 0.001 || duration <= 0) {
    onValue(end);
    onFinish?.(end);
    return;
  }

  const startedAt = window.performance.now();
  const ease = value => 1 - Math.pow(1 - value, 3);
  const step = now => {
    const record = smoothValueAnimations.get(key);
    if (!record) return;
    const progress = clamp((now - startedAt) / duration, 0, 1);
    const nextValue = start + distance * ease(progress);
    onValue(nextValue);
    if (progress >= 1) {
      smoothValueAnimations.delete(key);
      onFinish?.(end);
      return;
    }
    record.frame = window.requestAnimationFrame(step);
  };
  const record = {
    frame: window.requestAnimationFrame(step),
    cancel: () => onFinish?.(null)
  };
  smoothValueAnimations.set(key, record);
}

function applyTrackSeekHistory(payload) {
  const targetPath = payload?.trackPath || "";
  const targetRatio = clamp(Number(payload?.ratio) || 0, 0, 1);
  const target = targetPath ? allMusicTracks().find(item => item.path === targetPath) : null;
  if (target && selectedTrackPath !== target.path) {
    setSelectedTrack(target.path);
    const targetUrl = new URL(target.url, window.location.href).href;
    if (els.audioPlayer.src !== targetUrl) {
      els.audioPlayer.src = target.url;
      els.audioPlayer.load();
    }
  }

  if (audioDuration() <= 0) {
    pendingSeekRatio = targetRatio;
    setTrackSeekVisualRatio(targetRatio);
    return;
  }

  const startRatio = currentAudioSeekRatio();
  animateNumberValue(
    "seek",
    startRatio,
    targetRatio,
    320,
    setTrackSeekVisualRatio,
    value => {
      if (value == null) return;
      commitTrackSeek(targetRatio);
      updateTrackProgress();
    }
  );
}

function recordTrackSeekChange(beforeRatio, afterRatio) {
  if (beforeRatio == null) return;
  const before = clamp(Number(beforeRatio) || 0, 0, 1);
  const after = clamp(Number(afterRatio) || 0, 0, 1);
  if (Math.abs(before - after) < 0.004) return;
  pushConsoleHistory({
    type: "track-seek",
    before: { trackPath: selectedTrackPath || "", ratio: before },
    after: { trackPath: selectedTrackPath || "", ratio: after },
    apply: applyTrackSeekHistory
  });
}

function setTrackVolume(value, options = {}) {
  const nextVolume = clamp(Number(value) || 0, 0, 1);
  els.audioPlayer.volume = nextVolume;
  els.trackVolume.value = String(nextVolume);
  if (options.persist !== false) {
    localStorage.setItem(storageKeys.volume, String(nextVolume));
  }
}

function applyVolumeHistory(value) {
  const targetVolume = clamp(Number(value) || 0, 0, 1);
  const startVolume = clamp(Number(els.audioPlayer.volume) || 0, 0, 1);
  animateNumberValue(
    "volume",
    startVolume,
    targetVolume,
    240,
    volume => setTrackVolume(volume),
    value => {
      if (value != null) setTrackVolume(targetVolume);
    }
  );
}

function recordVolumeChange(beforeVolume, afterVolume) {
  const before = clamp(Number(beforeVolume) || 0, 0, 1);
  const after = clamp(Number(afterVolume) || 0, 0, 1);
  if (Math.abs(before - after) < 0.006) return;
  pushConsoleHistory({
    type: "volume",
    before,
    after,
    apply: applyVolumeHistory
  });
}

function beginVolumeGesture() {
  cancelSmoothValueAnimation("volume");
  if (volumeHistoryStart == null) {
    volumeHistoryStart = clamp(Number(els.audioPlayer.volume) || 0, 0, 1);
  }
}

function commitVolumeGesture() {
  if (volumeHistoryStart == null) return;
  const before = volumeHistoryStart;
  const after = clamp(Number(els.audioPlayer.volume) || 0, 0, 1);
  volumeHistoryStart = null;
  recordVolumeChange(before, after);
}

function applyPendingTrackSeek() {
  if (userSeeking || pendingSeekRatio == null || audioDuration() <= 0) return false;
  commitTrackSeek(pendingSeekRatio);
  return true;
}

function addTrackSeekWindowListeners() {
  window.addEventListener("pointermove", moveTrackSeek, { passive: false });
  window.addEventListener("pointerup", finishTrackSeek);
  window.addEventListener("pointercancel", finishTrackSeek);
}

function removeTrackSeekWindowListeners() {
  window.removeEventListener("pointermove", moveTrackSeek);
  window.removeEventListener("pointerup", finishTrackSeek);
  window.removeEventListener("pointercancel", finishTrackSeek);
}

function beginTrackSeek(event) {
  if (event?.button != null && event.button !== 0) return;
  event?.preventDefault?.();
  cancelSmoothValueAnimation("seek");
  userSeeking = true;
  activeSeekPointerId = event?.pointerId ?? null;
  seekHistoryStartRatio = currentAudioSeekRatio();
  setPendingTrackSeek(trackSeekRatioFromPointer(event) ?? trackSeekRatio());
  addTrackSeekWindowListeners();
  if (event?.pointerId != null && typeof els.trackSeek.setPointerCapture === "function") {
    try {
      els.trackSeek.setPointerCapture(event.pointerId);
    } catch {}
  }
}

function moveTrackSeek(event) {
  if (!userSeeking) return;
  if (activeSeekPointerId != null && event?.pointerId != null && event.pointerId !== activeSeekPointerId) return;
  event?.preventDefault?.();
  setPendingTrackSeek(trackSeekRatioFromPointer(event) ?? trackSeekRatio());
}

function handleTrackSeekInput(event) {
  cancelSmoothValueAnimation("seek");
  pendingSeekRatio = trackSeekRatioFromPointer(event) ?? trackSeekRatio();
  if (userSeeking) {
    previewTrackSeek(pendingSeekRatio);
    return;
  }
  const beforeRatio = seekHistoryStartRatio ?? currentAudioSeekRatio();
  commitTrackSeek(pendingSeekRatio);
  recordTrackSeekChange(beforeRatio, pendingSeekRatio);
  seekHistoryStartRatio = null;
  updateTrackProgress();
}

function finishTrackSeek(event) {
  if (event?.type === "lostpointercapture") return;
  if (activeSeekPointerId != null && event?.pointerId != null && event.pointerId !== activeSeekPointerId) return;
  if (!userSeeking && pendingSeekRatio == null) return;
  const ratio = trackSeekRatioFromPointer(event) ?? pendingSeekRatio ?? trackSeekRatio();
  userSeeking = false;
  activeSeekPointerId = null;
  removeTrackSeekWindowListeners();
  if (
    event?.pointerId != null &&
    typeof els.trackSeek.hasPointerCapture === "function" &&
    els.trackSeek.hasPointerCapture(event.pointerId)
  ) {
    try {
      els.trackSeek.releasePointerCapture(event.pointerId);
    } catch {}
  }
  commitTrackSeek(ratio);
  recordTrackSeekChange(seekHistoryStartRatio, ratio);
  seekHistoryStartRatio = null;
  updateTrackProgress();
}

function updateTrackProgress() {
  const duration = audioDuration();
  const current = Number.isFinite(els.audioPlayer.currentTime) ? els.audioPlayer.currentTime : 0;
  if (smoothValueAnimations.has("seek")) {
    previewTrackSeek(trackSeekRatio());
    return;
  }
  if (userSeeking) {
    previewTrackSeek(pendingSeekRatio ?? trackSeekRatio());
    return;
  }
  if (pendingSeekRatio != null) {
    if (duration > 0 && applyPendingTrackSeek()) return;
    previewTrackSeek(pendingSeekRatio);
    return;
  }
  els.trackCurrentTime.textContent = formatDuration(current);
  els.trackDuration.textContent = formatDuration(duration);
  els.trackSeek.value = duration > 0 ? String((current / duration) * 100) : "0";
  updateLyricsProgress(current);
}

async function loadWallpapers() {
  try {
    const response = await fetch("/api/wallpapers", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    wallpapers = Array.isArray(payload.wallpapers) ? payload.wallpapers : [];
    syncWallpaperOrder(Array.isArray(payload.order) ? payload.order : null);
    if (selectedWallpaperPath && !wallpapers.some(item => item.path === selectedWallpaperPath)) {
      selectedWallpaperPath = "";
      localStorage.removeItem(storageKeys.selectedWallpaper);
    }
    renderWallpapers();
  } catch (error) {
    setStatus(text("loadFailed", error.message));
  }
}

async function loadMusic() {
  try {
    const preferredSelectedTrackPath = normalizeMusicTrackPathValue(localStorage.getItem(storageKeys.selectedTrack) || selectedTrackPath);
    const response = await fetch("/api/music", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    tracks = Array.isArray(payload.tracks) ? payload.tracks : [];
    musicLibraries = Array.isArray(payload.libraries) ? payload.libraries : musicLibraries;
    musicCookieState = payload.cookies || { available: false };
    applyMusicState(payload.state, { preferredSelectedTrackPath });
    libraryTracks = flattenLibraryTracks(musicLibraries);
    if (selectedTrackPath && !tracks.some(item => item.path === selectedTrackPath)) {
      const stillExists = libraryTracks.some(item => item.path === selectedTrackPath);
      if (!stillExists) {
        setSelectedTrackPath("", { persist: "now" });
      }
    }
    renderMusic();
    renderMusicLibraries();
    scheduleSelectedLyricsPreload(40);
    scheduleMusicLibraryPoll();
  } catch (error) {
    musicNotice = text("musicLoadFailed", error.message);
    renderMusic();
    renderMusicLibraries();
  }
}

async function loadMaterialCandidates() {
  if (!hasMaterialWorkspace) return;
  if (!downloadIntakeEnabled) {
    materialCandidates = [];
    selectedMaterialPath = "";
    materialNotice = text("renderTextureDisabled");
    renderTextureNotice = text("renderTextureDisabled");
    renderMaterialImport();
    return;
  }
  try {
    const response = await fetch("/api/material-import/candidates", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    materialCandidates = Array.isArray(payload.candidates) ? payload.candidates : [];
    if (selectedMaterialPath && !materialCandidates.some(item => item.path === selectedMaterialPath)) {
      selectedMaterialPath = "";
    }
    materialNotice = "";
    renderMaterialImport(payload);
  } catch (error) {
    materialNotice = text("materialLoadFailed", error.message);
    renderMaterialImport();
  }
}

async function importMaterialCandidate(path = selectedMaterialCandidate()?.path) {
  if (!hasMaterialWorkspace) return;
  if (!path) return;
  const candidate = materialCandidates.find(item => item.path === path) || selectedMaterialCandidate();
  materialNotice = text("materialImporting", candidate ? candidate.name : path);
  renderMaterialImport();

  try {
    const result = await postJson("/api/material-import/import", { path });
    materialCandidates = Array.isArray(result.candidates) ? result.candidates : materialCandidates;
    selectedMaterialPath = "";
    materialNotice = text("materialImported", candidate ? candidate.name : path, Array.isArray(result.files) ? result.files.length : 0);
    renderMaterialImport(result);
  } catch (error) {
    materialNotice = text("materialImportFailed", error.message);
    renderMaterialImport();
  }
}

async function openDownloadsFolder() {
  if (!hasMaterialWorkspace) return;
  if (els.openDownloads) els.openDownloads.disabled = true;
  try {
    const result = await postJson("/api/workspace/open-downloads");
    setMaterialStatus(text("downloadsOpened"));
    if (result.path && els.materialSourcePath) {
      els.materialSourcePath.textContent = result.path;
    }
  } catch (error) {
    setMaterialStatus(text("openDownloadsFailed", error.message));
  } finally {
    if (els.openDownloads) els.openDownloads.disabled = false;
  }
}

function setRandomRealmReleaseStatus(message) {
  const value = message || text("randomRealmOpenReady");
  if (els.randomRealmReleaseStatusText) {
    els.randomRealmReleaseStatusText.textContent = value;
  }
  if (els.unityStatusText) {
    els.unityStatusText.textContent = value;
  }
}

function setSteamworkStatus(message) {
  if (els.steamworkStatusText) {
    els.steamworkStatusText.textContent = message || text("steamworkReady");
  }
}

function setSteamworkDropzoneStatus(kind, message) {
  const node = kind === "publishTool" ? els.steamworkPublishToolStatus : els.steamworkGameContentStatus;
  if (node) {
    node.textContent = message || text(kind === "publishTool" ? "steamworkPublishToolReady" : "steamworkGameContentReady");
  }
}

function randomRealmResourceButtons() {
  return [
    els.openSteamworks,
    els.openSteamPublishFolder,
    els.openSteamworkDashboard,
    els.openSteamworkPublishFolder,
    els.openSteamworkGameContent,
    els.openSteamworkPublishTool,
    els.openSteamworkPublishToolTip,
    els.openSteamworkBuildsTip,
    els.locateSteamworkPublishTool,
    els.openSteamworkArtAsset,
    els.openRandomRealmProject,
    els.openRandomRealmPromo,
    els.openUnityProjectFolder,
    els.openUnityPromoFolder
  ].filter(Boolean);
}

async function openRandomRealmResource(id, labelKey) {
  const label = text(labelKey);
  const buttons = randomRealmResourceButtons();
  setRandomRealmReleaseStatus(text("randomRealmOpening", label));
  setSteamworkStatus(text("randomRealmOpening", label));
  for (const button of buttons) button.disabled = true;

  try {
    await postJson("/api/randomrealm/open-resource", { id });
    setRandomRealmReleaseStatus(text("randomRealmOpened", label));
    setSteamworkStatus(text("randomRealmOpened", label));
  } catch (error) {
    const message = id === "publishToolFolder"
      ? text("steamworkPublishToolMissing")
      : text("randomRealmOpenFailed", error.message);
    setRandomRealmReleaseStatus(message);
    setSteamworkStatus(message);
  } finally {
    for (const button of buttons) button.disabled = false;
  }
}

function openSteamworksWebLink(url, labelKey) {
  const label = text(labelKey);
  const buttons = randomRealmResourceButtons();
  setRandomRealmReleaseStatus(text("randomRealmOpening", label));
  setSteamworkStatus(text("randomRealmOpening", label));
  for (const button of buttons) button.disabled = true;
  try {
    const opened = window.open(url, "_blank");
    if (!opened) throw new Error("popup blocked");
    try {
      opened.opener = null;
    } catch {
      // Some browsers block touching the opened window; the link is already open.
    }
    setRandomRealmReleaseStatus(text("randomRealmOpened", label));
    setSteamworkStatus(text("randomRealmOpened", label));
  } catch (error) {
    setRandomRealmReleaseStatus(text("randomRealmOpenFailed", error.message));
    setSteamworkStatus(text("randomRealmOpenFailed", error.message));
  } finally {
    for (const button of buttons) button.disabled = false;
  }
}

function steamworkTargetLabel(kind) {
  return kind === "publishTool" ? text("steamworkPublishTool") : text("steamworkGameContent");
}

async function uploadSteamworkFiles(kind, files) {
  if (!hasSteamwork) return;
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;
  const target = steamworkTargetLabel(kind);
  const formData = new FormData();
  for (const file of selectedFiles) {
    formData.append("files", file, file.name);
  }

  const dropzone = kind === "publishTool" ? els.steamworkPublishToolDropzone : els.steamworkGameContentDropzone;
  const endpoint = kind === "publishTool" ? "/api/steamwork/publish-tool/upload" : "/api/steamwork/gamecontent/upload";
  const importing = text("steamworkImporting", selectedFiles.length, target);
  setSteamworkStatus(importing);
  setSteamworkDropzoneStatus(kind, importing);
  dropzone?.classList.add("busy");
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    const count = Array.isArray(result.files) ? result.files.length : selectedFiles.length;
    const imported = text("steamworkImported", count, result.targetName || target);
    setSteamworkStatus(imported);
    setSteamworkDropzoneStatus(kind, imported);
  } catch (error) {
    const message = text("steamworkImportFailed", error.message);
    setSteamworkStatus(message);
    setSteamworkDropzoneStatus(kind, message);
  } finally {
    dropzone?.classList.remove("busy", "drag-over");
    if (kind === "publishTool" && els.steamworkPublishToolFileInput) {
      els.steamworkPublishToolFileInput.value = "";
    }
    if (kind !== "publishTool" && els.steamworkGameContentFileInput) {
      els.steamworkGameContentFileInput.value = "";
    }
  }
}

function bindSteamworkDropzone(kind, dropzone, input) {
  if (!hasSteamwork || !dropzone) return;
  dropzone.addEventListener("click", () => input?.click());
  dropzone.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input?.click();
    }
  });
  dropzone.addEventListener("dragover", event => {
    event.preventDefault();
    dropzone.classList.add("drag-over");
    setSteamworkDropzoneStatus(kind, text("steamworkImportDragging"));
  });
  dropzone.addEventListener("dragleave", event => {
    if (!dropzone.contains(event.relatedTarget)) {
      dropzone.classList.remove("drag-over");
      setSteamworkDropzoneStatus(kind);
    }
  });
  dropzone.addEventListener("drop", event => {
    event.preventDefault();
    dropzone.classList.remove("drag-over");
    uploadSteamworkFiles(kind, event.dataTransfer.files);
  });
}

function steamworkAssetStatusLabel(status) {
  if (status === "ready") return text("steamworkAssetReady");
  if (status === "review") return text("steamworkAssetReview");
  if (status === "optional") return text("steamworkAssetOptional");
  return text("steamworkAssetMissing");
}

function setSteamworkAssetRoot(root = "") {
  if (!els.steamworkAssetRoot) return;
  els.steamworkAssetRoot.textContent = root ? text("steamworkAssetSource", root) : "";
}

function setSteamworkAssetSummaryText(message) {
  if (!els.steamworkAssetSummary) return;
  els.steamworkAssetSummary.classList.remove("steamwork-summary-pill");
  els.steamworkAssetSummary.textContent = message || "";
}

function renderSteamworkAssetSummaryPills(summary, itemCount) {
  if (!els.steamworkAssetSummary) return;
  if (!itemCount) {
    setSteamworkAssetSummaryText(text("steamworkAssetLoading"));
    return;
  }

  const total = summary.total || itemCount;
  const allStats = [
    ["ready", text("steamworkAssetSummaryReady", summary.ready || 0, total)],
    ["review", text("steamworkAssetSummaryReview", summary.review || 0)],
    ["missing", text("steamworkAssetSummaryMissing", summary.missing || 0)],
    ["optional", text("steamworkAssetSummaryOptional", summary.optional || 0)],
    ["files", text("steamworkAssetSummaryFiles", summary.files || 0)]
  ];
  const stats = allStats.filter(([kind]) => {
    if (kind === "ready" || kind === "files") return true;
    return Number(summary[kind] || 0) > 0;
  });

  els.steamworkAssetSummary.classList.add("steamwork-summary-pill");
  els.steamworkAssetSummary.title = allStats.map(([, label]) => label).join(" / ");
  els.steamworkAssetSummary.setAttribute("aria-label", els.steamworkAssetSummary.title);
  els.steamworkAssetSummary.replaceChildren(...stats.map(([kind, label]) => {
    const chip = document.createElement("span");
    chip.className = `steamwork-summary-chip ${kind}`;
    chip.textContent = label;
    return chip;
  }));
}

function steamworkAssetIssueText(issue) {
  const cleanIssue = String(issue || "").trim();
  if (!cleanIssue) return "";
  if (cleanIssue === "Missing required asset") return text("steamworkIssueMissingRequired");
  if (cleanIssue === "Optional") return text("steamworkIssueOptional");
  if (cleanIssue === "File found, check size/format") return text("steamworkIssueCheckFile");
  const countMatch = cleanIssue.match(/^Need\s+(\d+)\s+files?$/i);
  if (countMatch) return text("steamworkIssueNeedFiles", Number(countMatch[1]));
  return cleanIssue;
}

function steamworkAssetTargetText(target) {
  const key = {
    "Store Page Admin > Graphical Assets": "steamworkTargetGraphicalAssets",
    "Store Page Admin > Screenshots": "steamworkTargetScreenshots",
    "Store Page Admin > Community & Client Icons": "steamworkTargetCommunityIcons",
    "Steamworks > Edit Library Assets": "steamworkTargetLibraryAssets",
    "Store Page Admin > Trailers": "steamworkTargetTrailers"
  }[String(target || "")];
  return key ? text(key) : target || "";
}

function steamworkAssetSpecText(spec) {
  const cleanSpec = String(spec || "").trim();
  if (!cleanSpec || language !== "zh") return cleanSpec;
  return {
    "5+ files, 1920 x 1080 minimum, 16:9": "5+ \u5f20\uff0c\u22651080p\uff0c16:9",
    "256 x 256 or 512 x 512, ICO/PNG": "256/512\uff0cICO/PNG",
    "184 x 184 JPG": "184 x 184\uff0cJPG",
    "3840 x 1240 PNG": "3840 x 1240\uff0cPNG",
    "PNG, 1280 wide and/or 720 tall": "PNG\uff0c\u5bbd 1280 \u6216\u9ad8 720",
    "MP4/MOV/WMV, up to 1920 x 1080, 30/60 fps": "\u22641080p\uff0c30/60fps",
    "1920 x 1080 JPG/PNG, frame from the video": "1920 x 1080\uff0cJPG/PNG"
  }[cleanSpec] || cleanSpec;
}

function steamworkAssetPreviewUrl(file) {
  if (!file?.preview || !file.path) return "";
  const version = file.modified ? `&v=${encodeURIComponent(file.modified)}` : "";
  return `/api/steamwork/asset-preview?path=${encodeURIComponent(file.path)}${version}`;
}

function steamworkAssetThumbUrl(file) {
  if (!steamworkThumbsEnabled || !file?.preview || !file.path) return "";
  const version = file.modified ? `&v=${encodeURIComponent(file.modified)}` : "";
  return `/api/steamwork/asset-thumb?path=${encodeURIComponent(file.path)}${version}`;
}

function steamworkAssetDimensions(file) {
  if (file?.width && file?.height) return `${file.width}x${file.height}`;
  return "";
}

function steamworkAssetExtension(file) {
  const explicit = String(file?.extension || "").toLowerCase();
  if (explicit) return explicit.startsWith(".") ? explicit : `.${explicit}`;
  const match = String(file?.name || "").toLowerCase().match(/\.[^.]+$/);
  return match ? match[0] : "";
}

function steamworkAssetCandidateRootHint(item) {
  if (item?.candidateRootHint) return item.candidateRootHint;
  if (item?.id === "trailer_poster") return "screenshots";
  return item?.rootHint || "";
}

function steamworkAssetCandidatePatterns(item) {
  const patterns = Array.isArray(item?.candidatePatterns) ? [...item.candidatePatterns] : [];
  if (item?.id === "trailer_poster") {
    patterns.push("screenshot", "screen");
  }
  return [...new Set(patterns.map(pattern => String(pattern || "").trim()).filter(Boolean))];
}

function steamworkAssetCandidateFolders(item) {
  if (item?.kind === "video") return new Set(["video"]);
  if (item?.id === "screenshots") return new Set(["screenshots"]);
  if (item?.id === "trailer_poster") return new Set(["screenshots", "store", "root", "staged"]);
  if (["Store", "Library", "Community", "Video"].includes(item?.category || "")) {
    return new Set(["store", "root", "staged"]);
  }
  return null;
}

function steamworkAssetCandidateFiles(item, allFiles = []) {
  const seen = new Set();
  const matchedPaths = new Set((Array.isArray(item?.files) ? item.files : [])
    .map(file => file?.path)
    .filter(Boolean));
  const folders = steamworkAssetCandidateFolders(item);
  const sourceFiles = [
    ...(Array.isArray(item?.candidates) ? item.candidates : []),
    ...(Array.isArray(allFiles) ? allFiles : [])
  ];
  return sourceFiles.filter(file => {
    const path = file?.path || "";
    if (!path || seen.has(path) || matchedPaths.has(path)) return false;
    seen.add(path);
    const extension = steamworkAssetExtension(file);
    if (item?.kind === "video") {
      if (![".mp4", ".mov", ".wmv"].includes(extension)) return false;
    } else if (![".png", ".jpg", ".jpeg", ".webp", ".ico", ".psd"].includes(extension)) {
      return false;
    }
    return !folders || folders.has(file?.folder || "");
  });
}

function steamworkAssetDimensionsOk(item, file) {
  const mode = item?.dimensionMode || "";
  const extension = steamworkAssetExtension(file);
  const width = Number(file?.width) || 0;
  const height = Number(file?.height) || 0;
  if (mode === "video") return [".mp4", ".mov", ".wmv"].includes(extension);
  if (mode === "exact") return width === Number(item?.width || 0) && height === Number(item?.height || 0);
  if (mode === "min16x9") {
    const ratio = height > 0 ? width / height : 0;
    return width >= Number(item?.minWidth || 0) && height >= Number(item?.minHeight || 0) && Math.abs(ratio - 16 / 9) < 0.04;
  }
  if (mode === "shortcutIcon") {
    if (extension === ".ico") return true;
    return extension === ".png" && (width === 256 && height === 256 || width === 512 && height === 512);
  }
  if (mode === "appIcon") return [".jpg", ".jpeg"].includes(extension) && width === 184 && height === 184;
  if (mode === "libraryLogo") return extension === ".png" && (width === 1280 || height === 720);
  return false;
}

function steamworkAssetFitInfo(item, file) {
  if (!item || !file) return null;
  if (steamworkAssetDimensionsOk(item, file)) {
    return { kind: "ok", label: text("steamworkAssetFitOk") };
  }

  const mode = item?.dimensionMode || "";
  const extension = steamworkAssetExtension(file);
  const width = Number(file?.width) || 0;
  const height = Number(file?.height) || 0;
  const hasDimensions = width > 0 && height > 0;
  const isImageLike = [".png", ".jpg", ".jpeg", ".webp", ".ico"].includes(extension);
  const isVideoLike = [".mp4", ".mov", ".wmv"].includes(extension);

  if (item?.kind === "video") {
    return { kind: isVideoLike ? "check" : "type", label: isVideoLike ? text("steamworkAssetFitCheck") : text("steamworkAssetFitType") };
  }
  if (!isImageLike) {
    return { kind: "type", label: text("steamworkAssetFitType") };
  }

  if (mode === "appIcon") {
    const formatOk = [".jpg", ".jpeg"].includes(extension);
    const sizeOk = hasDimensions && width === 184 && height === 184;
    if (!formatOk && hasDimensions && !sizeOk) return { kind: "format-size", label: text("steamworkAssetFitFormatSize") };
    if (!formatOk) return { kind: "format", label: text("steamworkAssetFitFormat") };
    return { kind: hasDimensions ? "size" : "check", label: hasDimensions ? text("steamworkAssetFitSize") : text("steamworkAssetFitCheck") };
  }

  if (mode === "shortcutIcon") {
    if (![".ico", ".png"].includes(extension)) return { kind: "format", label: text("steamworkAssetFitFormat") };
    return { kind: hasDimensions || extension === ".png" ? "size" : "check", label: hasDimensions || extension === ".png" ? text("steamworkAssetFitSize") : text("steamworkAssetFitCheck") };
  }

  if (mode === "libraryLogo" && extension !== ".png") {
    return { kind: "format", label: text("steamworkAssetFitFormat") };
  }

  if (mode === "video") {
    return { kind: "format", label: text("steamworkAssetFitFormat") };
  }

  return { kind: hasDimensions ? "size" : "check", label: hasDimensions ? text("steamworkAssetFitSize") : text("steamworkAssetFitCheck") };
}

function steamworkAssetCandidateScore(item, file) {
  const extension = steamworkAssetExtension(file);
  const kind = item?.kind || "";
  if (kind === "video" && ![".mp4", ".mov", ".wmv"].includes(extension)) return -1;
  if (kind !== "video" && ![".png", ".jpg", ".jpeg", ".webp", ".ico"].includes(extension)) return -1;

  let score = 0;
  let hasSignal = false;
  if (steamworkAssetDimensionsOk(item, file)) {
    score += 120;
    hasSignal = true;
  }
  if (file?.folder === "staged") {
    score += 90;
    hasSignal = true;
  }
  const candidateRoot = steamworkAssetCandidateRootHint(item);
  if (candidateRoot && file?.folder === candidateRoot) {
    score += 80;
    hasSignal = true;
  }
  if (file?.folder === "video" && item?.category === "Video") {
    score += 80;
    hasSignal = true;
  }

  const haystack = `${file?.name || ""} ${file?.path || ""}`.replace(/[_-]/g, " ").toLowerCase();
  for (const pattern of [...(item?.patterns || []), ...steamworkAssetCandidatePatterns(item)]) {
    const cleanPattern = String(pattern || "").replace(/[_-]/g, " ").toLowerCase();
    if (cleanPattern && haystack.includes(cleanPattern)) {
      score += cleanPattern.length > 4 ? 35 : 15;
      hasSignal = true;
    }
  }
  return hasSignal ? score : -1;
}

function steamworkAssetReferenceScore(item, file) {
  const extension = steamworkAssetExtension(file);
  const kind = item?.kind || "";
  if (kind === "video") {
    return [".mp4", ".mov", ".wmv"].includes(extension) ? 100 : -1;
  }
  if (![".png", ".jpg", ".jpeg", ".webp", ".ico"].includes(extension)) return -1;

  let score = steamworkAssetDimensionsOk(item, file) ? 300 : 0;
  if (file?.folder === "staged") score += 80;
  const candidateRoot = steamworkAssetCandidateRootHint(item);
  if (candidateRoot && file?.folder === candidateRoot) score += 140;
  if (["Store", "Library", "Community", "Video"].includes(item?.category || "") && ["store", "root", "staged"].includes(file?.folder || "")) {
    score += 18;
  }

  const width = Number(file?.width) || 0;
  const height = Number(file?.height) || 0;
  const targetWidth = Number(item?.width || item?.minWidth) || 0;
  const targetHeight = Number(item?.height || item?.minHeight) || 0;
  if (width > 0 && height > 0 && targetWidth > 0 && targetHeight > 0) {
    const ratio = width / height;
    const targetRatio = targetWidth / targetHeight;
    const ratioDelta = Math.abs(Math.log(ratio / targetRatio));
    const areaDelta = Math.abs(Math.log((width * height) / (targetWidth * targetHeight)));
    score += Math.max(0, 110 - ratioDelta * 180);
    score += Math.max(0, 75 - areaDelta * 28);
    if ((width >= height) === (targetWidth >= targetHeight)) score += 18;
    if (width < targetWidth * 0.25 || height < targetHeight * 0.25) score -= 80;
    if (Math.abs(ratio - 1) < 0.04 && Math.abs(targetRatio - 1) > 0.2) score -= 70;
  }

  const haystack = `${file?.name || ""} ${file?.path || ""}`.replace(/[_-]/g, " ").toLowerCase();
  if (item?.id === "trailer_poster") {
    const looksLikeIcon = extension === ".ico" || /\b(?:icon|logo)\b/i.test(haystack);
    if (looksLikeIcon) score -= 140;
  }
  for (const pattern of [...(item?.patterns || []), ...steamworkAssetCandidatePatterns(item)]) {
    const cleanPattern = String(pattern || "").replace(/[_-]/g, " ").toLowerCase();
    if (cleanPattern && haystack.includes(cleanPattern)) {
      score += cleanPattern.length > 4 ? 45 : 18;
    }
  }
  return score;
}

function steamworkRelevantAssetCandidates(item, allFiles = []) {
  const candidates = steamworkAssetCandidateFiles(item, allFiles);
  return candidates.length
    ? candidates
      .map(file => ({ file, score: steamworkAssetCandidateScore(item, file) }))
      .filter(entry => entry.score > 0)
      .sort((first, second) => second.score - first.score || String(second.file.modified || "").localeCompare(String(first.file.modified || "")))
      .map(entry => entry.file)
    : [];
}

function steamworkCandidateDisplay(item, allFiles = []) {
  const candidates = steamworkAssetCandidateFiles(item, allFiles);
  const relevant = steamworkRelevantAssetCandidates(item, allFiles);
  if (relevant.length || !candidates.length) {
    return { files: relevant, reference: false };
  }
  return {
    files: candidates
      .map(file => ({ file, score: steamworkAssetReferenceScore(item, file) }))
      .filter(entry => entry.score >= 0)
      .sort((first, second) => second.score - first.score || String(second.file.modified || "").localeCompare(String(first.file.modified || "")))
      .map(entry => entry.file),
    reference: true
  };
}

function createSteamworkAssetThumb(file, status) {
  const thumb = document.createElement("div");
  thumb.className = "steamwork-asset-thumb";
  if (file?.preview) {
    thumb.textContent = (file.extension || "img").replace(".", "").toUpperCase().slice(0, 4);
    const previewUrl = steamworkAssetPreviewUrl(file);
    const thumbUrl = steamworkAssetThumbUrl(file);
    const image = document.createElement("img");
    image.src = thumbUrl || previewUrl;
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => {
      const fallbackHref = previewUrl ? new URL(previewUrl, window.location.href).href : "";
      if (thumbUrl && fallbackHref && image.src !== fallbackHref) {
        image.src = previewUrl;
        return;
      }
      image.remove();
    });
    thumb.appendChild(image);
  } else {
    thumb.textContent = file?.type === "video" ? "MP4" : status === "missing" ? "..." : "IMG";
  }
  return thumb;
}

function steamworkAssetMetaV2(file) {
  if (!file) return text("steamworkAssetNoFile");
  const pieces = [];
  const dimensions = steamworkAssetDimensions(file);
  if (dimensions) pieces.push(dimensions);
  if (Number.isFinite(Number(file.size))) pieces.push(formatBytes(Number(file.size)));
  return pieces.join(" / ");
}

function steamworkAssetFolderLabel(file) {
  const folder = String(file?.folder || "").toLowerCase();
  const key = {
    store: "steamworkAssetFolderStore",
    screenshots: "steamworkAssetFolderScreenshots",
    video: "steamworkAssetFolderVideo",
    staged: "steamworkAssetFolderStaged"
  }[folder];
  return key ? text(key) : file?.folder || "";
}

function steamworkAssetFileDisplayName(file) {
  const name = file?.name || text("steamworkAssetNoFile");
  if (String(file?.folder || "").toLowerCase() !== "screenshots") return name;
  const stem = name.replace(/\.[^.]+$/, "");
  const match = stem.match(/^screenshot[\s_-]+(\d{4}-\d{2}-\d{2})[\s_-]+(\d{2})(\d{2})(\d{2})$/i);
  if (match) {
    return `${match[1]} ${match[2]}:${match[3]}:${match[4]}`;
  }
  return stem.replace(/^screenshot[\s_-]*/i, "") || stem || name;
}

function createSteamworkStatusBadge(statusValue) {
  const status = document.createElement("span");
  status.className = `steamwork-status-badge ${statusValue || "missing"}`;
  status.textContent = steamworkAssetStatusLabel(statusValue);
  return status;
}

function renderSteamworkAssetFileV2(file, options = {}) {
  const compact = Boolean(options.compact);
  const showOpen = options.showOpen !== false;
  const fitInfo = steamworkAssetFitInfo(options.requirement, file);
  const wrap = document.createElement("div");
  wrap.className = compact ? "steamwork-current-file compact" : "steamwork-current-file";
  if (String(file?.folder || "").toLowerCase() === "screenshots") {
    wrap.classList.add("screenshot-file");
  }

  if (file?.preview) {
    wrap.appendChild(createSteamworkAssetThumb(file, ""));
  }

  const body = document.createElement("div");
  body.className = "steamwork-current-body";

  const name = document.createElement("div");
  name.className = "steamwork-current-name";
  name.textContent = steamworkAssetFileDisplayName(file);
  if (file?.name && name.textContent !== file.name) {
    name.title = file.name;
  }
  body.appendChild(name);

  const tags = document.createElement("div");
  tags.className = "steamwork-current-tags";

  const meta = document.createElement("div");
  meta.className = "steamwork-current-meta";
  meta.textContent = steamworkAssetMetaV2(file);
  tags.appendChild(meta);

  if (fitInfo) {
    const fit = document.createElement("div");
    fit.className = `steamwork-fit-badge ${fitInfo.kind}`;
    fit.textContent = fitInfo.label;
    tags.appendChild(fit);
  }

  const folderLabel = steamworkAssetFolderLabel(file);
  if (folderLabel) {
    const source = document.createElement("div");
    source.className = "steamwork-current-source";
    source.textContent = folderLabel;
    tags.appendChild(source);
  }

  if (tags.childNodes.length) {
    body.appendChild(tags);
  }

  if (file?.path && !compact) {
    const path = document.createElement("div");
    path.className = "steamwork-current-path";
    path.textContent = file.path;
    body.appendChild(path);
  }

  if (file?.path && showOpen) {
    const openButton = document.createElement("button");
    openButton.className = "mini-button steamwork-open-asset";
    openButton.type = "button";
    openButton.dataset.path = file.path;
    openButton.textContent = text("steamworkAssetOpen");
    body.appendChild(openButton);
  }

  wrap.appendChild(body);
  return wrap;
}

function createSteamworkAssetStageZone(item) {
  const zone = document.createElement("div");
  zone.className = "steamwork-stage-zone";
  zone.tabIndex = 0;
  zone.dataset.slot = item.id || "";

  const title = document.createElement("strong");
  title.textContent = text("steamworkAssetStageTitle");
  const hint = document.createElement("span");
  hint.textContent = text("steamworkAssetStageHint");
  zone.append(title, hint);

  const pickFiles = () => {
    pendingSteamworkAssetSlot = item.id || "";
    els.steamworkAssetFileInput?.click();
  };

  zone.addEventListener("click", pickFiles);
  zone.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      pickFiles();
    }
  });
  zone.addEventListener("dragover", event => {
    event.preventDefault();
    zone.classList.add("drag-over");
    hint.textContent = text("steamworkAssetStageDragging");
  });
  zone.addEventListener("dragleave", event => {
    if (!zone.contains(event.relatedTarget)) {
      zone.classList.remove("drag-over");
      hint.textContent = text("steamworkAssetStageHint");
    }
  });
  zone.addEventListener("drop", event => {
    event.preventDefault();
    zone.classList.remove("drag-over");
    hint.textContent = text("steamworkAssetStageHint");
    stageSteamworkAssetFiles(item.id || "", event.dataTransfer.files, item.name || item.id || "");
  });

  return zone;
}

function createSteamworkMissingGuide(item) {
  if (item?.status !== "missing") return null;
  const guide = document.createElement("div");
  guide.className = "steamwork-missing-guide";

  const title = document.createElement("strong");
  title.textContent = text("steamworkAssetMissingGuideTitle");
  guide.appendChild(title);

  const tags = document.createElement("span");
  tags.className = "steamwork-missing-guide-tags";
  for (const label of [
    text("steamworkAssetMissingGuideSpec", steamworkAssetSpecText(item.spec)),
    text("steamworkAssetMissingGuideDrop"),
    text("steamworkAssetMissingGuideTarget", steamworkAssetTargetText(item.target))
  ].filter(Boolean)) {
    const tag = document.createElement("small");
    tag.textContent = label;
    tags.appendChild(tag);
  }
  guide.appendChild(tags);
  return guide;
}

function createSteamworkOptionalGuide(item) {
  if (item?.status !== "optional" || item?.files?.length) return null;
  const guide = document.createElement("div");
  guide.className = "steamwork-optional-guide";

  const title = document.createElement("strong");
  title.textContent = text("steamworkAssetOptionalGuideTitle");
  guide.appendChild(title);

  const tags = document.createElement("span");
  tags.className = "steamwork-optional-guide-tags";
  for (const label of [
    text("steamworkAssetOptionalGuideNote"),
    text("steamworkAssetOptionalGuideSpec", steamworkAssetSpecText(item.spec)),
    text("steamworkAssetOptionalGuideTarget", steamworkAssetTargetText(item.target))
  ].filter(Boolean)) {
    const tag = document.createElement("small");
    tag.textContent = label;
    tags.appendChild(tag);
  }
  guide.appendChild(tags);
  return guide;
}

function renderSteamworkAssetGroup(titleText, files, emptyText, options = {}) {
  const allFiles = Array.isArray(files) ? files : [];
  const limit = Number.isFinite(options.limit) ? options.limit : allFiles.length;
  const visibleFiles = Array.isArray(files)
    ? allFiles.slice(0, limit)
    : [];
  const hiddenFiles = allFiles.slice(visibleFiles.length);
  const hiddenCount = hiddenFiles.length;
  const group = document.createElement("div");
  group.className = [
    "steamwork-asset-group",
    options.candidate ? "candidate-group" : "",
    options.reference ? "reference-group" : "",
    options.optionalReference ? "optional-reference-group" : ""
  ].filter(Boolean).join(" ");
  if (options.assetId) {
    group.classList.add(`asset-${String(options.assetId).replace(/[^a-z0-9_-]/gi, "-")}`);
  }

  const title = document.createElement("div");
  title.className = "steamwork-asset-group-title";
  const titleLabel = document.createElement("span");
  titleLabel.textContent = titleText;
  title.appendChild(titleLabel);
  if (Array.isArray(files) && files.length) {
    const count = document.createElement("span");
    count.className = "steamwork-asset-group-count";
    count.textContent = text("steamworkAssetFileCount", files.length);
    title.appendChild(count);
  }
  group.appendChild(title);
  if (options.note) {
    const note = document.createElement("div");
    note.className = "steamwork-asset-group-note";
    note.textContent = options.note;
    group.appendChild(note);
  }

  if (!Array.isArray(files) || !files.length) {
    const empty = document.createElement("div");
    const details = Array.isArray(options.emptyDetails)
      ? options.emptyDetails.filter(Boolean)
      : [];
    empty.className = `steamwork-empty ${details.length ? "steamwork-empty-panel" : ""}`.trim();
    const message = document.createElement("span");
    message.textContent = emptyText;
    empty.appendChild(message);
    for (const detailText of details) {
      const detail = document.createElement("small");
      detail.textContent = detailText;
      empty.appendChild(detail);
    }
    group.appendChild(empty);
    return group;
  }

  if (visibleFiles.length) {
    const grid = document.createElement("div");
    grid.className = `steamwork-file-grid ${options.candidate ? "candidate-grid" : ""}`.trim();
    for (const file of visibleFiles) {
      grid.appendChild(renderSteamworkAssetFileV2(file, { compact: true, requirement: options.requirement || null }));
    }
    group.appendChild(grid);
  }
  if (hiddenCount) {
    const more = document.createElement("details");
    more.className = "steamwork-asset-more";
    const summary = document.createElement("summary");
    const moreKey = options.candidate
      ? visibleFiles.length
        ? "steamworkAssetMoreCandidates"
        : "steamworkAssetShowCandidates"
      : visibleFiles.length
        ? "steamworkAssetMoreFiles"
        : "steamworkAssetShowFiles";
    summary.textContent = text(moreKey, hiddenCount);
    more.appendChild(summary);

    const moreGrid = document.createElement("div");
    moreGrid.className = `steamwork-file-grid ${options.candidate ? "candidate-grid" : ""}`.trim();
    for (const file of hiddenFiles) {
      moreGrid.appendChild(renderSteamworkAssetFileV2(file, { compact: true, requirement: options.requirement || null }));
    }
    more.appendChild(moreGrid);
    group.appendChild(more);
  }
  return group;
}

function steamworkCurrentGroupLimit(fileCount = 0) {
  if (fileCount <= 3) return fileCount;
  return window.matchMedia?.("(max-width: 540px)")?.matches ? 3 : fileCount;
}

function steamworkCandidateGroupLimit(fileCount = 0) {
  if (fileCount <= 3) return fileCount;
  return window.matchMedia?.("(max-width: 540px)")?.matches ? 3 : 8;
}

function steamworkCandidateGroupLimitForItem(item, fileCount = 0) {
  if (item?.status === "missing" || item?.status === "review") {
    return steamworkCandidateGroupLimit(fileCount);
  }
  return 0;
}

function shouldShowSteamworkCandidateGroup(item, candidateDisplay) {
  if (candidateDisplay?.files?.length) return true;
  return item?.status === "missing" || item?.status === "review";
}

function steamworkCategoryLabel(categoryName) {
  const key = {
    Store: "steamworkCategoryStore",
    Library: "steamworkCategoryLibrary",
    Community: "steamworkCategoryCommunity",
    Video: "steamworkCategoryVideo"
  }[categoryName];
  return key ? text(key) : categoryName;
}

function createSteamworkCategorySummary(items) {
  const ready = items.filter(item => item.status === "ready").length;
  const missing = items.filter(item => item.status === "missing").length;
  const review = items.filter(item => item.status === "review").length;
  const optional = items.filter(item => item.status === "optional").length;
  const stats = [
    ["ready", text("steamworkAssetSummaryReady", ready, items.length)]
  ];
  if (missing) stats.push(["missing", text("steamworkCategoryMissing", missing)]);
  if (review) stats.push(["review", text("steamworkCategoryReview", review)]);
  if (optional) stats.push(["optional", text("steamworkCategoryOptional", optional)]);

  const wrap = document.createElement("div");
  wrap.className = "steamwork-category-stats";
  wrap.append(...stats.map(([kind, label]) => {
    const chip = document.createElement("span");
    chip.className = `steamwork-category-chip ${kind}`;
    chip.textContent = label;
    return chip;
  }));
  return wrap;
}

function renderSteamworkCategoryNav(items, categoryOrder) {
  const nav = document.createElement("div");
  nav.className = "steamwork-category-nav";
  for (const categoryName of categoryOrder) {
    const categoryItems = items.filter(item => item.category === categoryName);
    if (!categoryItems.length) continue;

    const ready = categoryItems.filter(item => item.status === "ready").length;
    const missing = categoryItems.filter(item => item.status === "missing").length;
    const review = categoryItems.filter(item => item.status === "review").length;
    const optional = categoryItems.filter(item => item.status === "optional").length;

    const button = document.createElement("button");
    button.className = `steamwork-category-jump ${missing ? "has-missing" : review ? "has-review" : ""}`.trim();
    button.type = "button";
    button.dataset.category = categoryName;
    button.title = steamworkCategoryLabel(categoryName);

    const main = document.createElement("span");
    main.className = "steamwork-category-jump-main";
    const label = document.createElement("strong");
    label.textContent = steamworkCategoryLabel(categoryName);
    const readyText = document.createElement("span");
    readyText.className = "steamwork-category-jump-ready";
    readyText.textContent = text("steamworkAssetSummaryReady", ready, categoryItems.length);
    main.append(label, readyText);
    button.appendChild(main);

    const tags = document.createElement("span");
    tags.className = "steamwork-category-jump-tags";
    if (missing) {
      const tag = document.createElement("small");
      tag.className = "missing";
      tag.textContent = text("steamworkCategoryMissing", missing);
      tags.appendChild(tag);
    }
    if (review) {
      const tag = document.createElement("small");
      tag.className = "review";
      tag.textContent = text("steamworkCategoryReview", review);
      tags.appendChild(tag);
    }
    if (optional) {
      const tag = document.createElement("small");
      tag.className = "optional";
      tag.textContent = text("steamworkCategoryOptional", optional);
      tags.appendChild(tag);
    }
    if (tags.childElementCount) button.appendChild(tags);
    nav.appendChild(button);
  }
  return nav.childElementCount ? nav : null;
}

function renderSteamworkAssetAttention(items) {
  const attentionItems = items.filter(item => item.status === "missing" || item.status === "review");
  if (!attentionItems.length) return null;

  const wrap = document.createElement("section");
  wrap.className = "steamwork-asset-alerts";
  if (attentionItems.length === 1) {
    wrap.classList.add("is-compact");
  }

  const head = document.createElement("div");
  head.className = "steamwork-asset-alerts-head";
  const title = document.createElement("strong");
  title.textContent = text("steamworkAttentionTitle");
  const count = document.createElement("span");
  count.textContent = text("steamworkAttentionCount", attentionItems.length);
  head.append(title, count);
  wrap.appendChild(head);

  const list = document.createElement("div");
  list.className = "steamwork-asset-alert-list";
  for (const item of attentionItems) {
    const button = document.createElement("button");
    button.className = `steamwork-asset-alert status-${item.status || "missing"}`;
    button.type = "button";
    button.dataset.slot = item.id || "";
    button.title = text("steamworkAttentionHint");

    const status = document.createElement("span");
    status.className = "steamwork-alert-status";
    status.textContent = steamworkAssetStatusLabel(item.status);
    button.appendChild(status);

    const body = document.createElement("span");
    body.className = "steamwork-alert-body";
    const name = document.createElement("strong");
    name.textContent = item.name || "";
    const specText = steamworkAssetSpecText(item.spec);
    const tags = document.createElement("span");
    tags.className = "steamwork-alert-tags";
    const actionText = item.status === "missing"
      ? text("steamworkAttentionFixMissing")
      : text("steamworkAttentionReview");
    const tagItems = [
      ["action", actionText],
      ["spec", specText],
      ["category", steamworkCategoryLabel(item.category || "")]
    ];
    for (const [kind, label] of tagItems.filter(([, label]) => Boolean(label))) {
      const tag = document.createElement("small");
      tag.className = `steamwork-alert-tag-${kind}`;
      tag.textContent = label;
      tags.appendChild(tag);
    }
    const target = document.createElement("small");
    target.className = "steamwork-alert-target";
    target.textContent = steamworkAssetTargetText(item.target);
    body.append(name, tags, target);
    button.appendChild(body);

    list.appendChild(button);
  }
  wrap.appendChild(list);
  return wrap;
}

function createSteamworkAssetCard(item, openIds, allFiles = []) {
  const card = document.createElement("details");
  card.className = `steamwork-asset-card status-${item.status || "missing"}`;
  card.dataset.slot = item.id || "";
  if (openIds.has(item.id)) {
    card.open = true;
  }
  const primaryFile = Array.isArray(item.files) ? item.files[0] : null;
  const fileCount = Array.isArray(item.files) ? item.files.length : 0;

  const summaryNode = document.createElement("summary");
  summaryNode.className = "steamwork-asset-summary";

  const asset = document.createElement("div");
  asset.className = "steamwork-asset-namecell";
  asset.appendChild(createSteamworkAssetThumb(primaryFile, item.status));

  const assetText = document.createElement("div");
  assetText.className = "steamwork-asset-titlewrap";
  const title = document.createElement("strong");
  title.textContent = item.name || "";
  const category = document.createElement("span");
  category.textContent = steamworkCategoryLabel(item.category || "");
  assetText.append(title, category);
  asset.appendChild(assetText);
  summaryNode.appendChild(asset);

  const statusCell = document.createElement("div");
  statusCell.className = "steamwork-asset-statuscell";
  statusCell.dataset.label = text("steamworkStatusColumn");
  statusCell.appendChild(createSteamworkStatusBadge(item.status));
  summaryNode.appendChild(statusCell);

  const specCell = document.createElement("span");
  specCell.className = "steamwork-spec-text steamwork-asset-speccell";
  specCell.dataset.label = text("steamworkSpecColumn");
  specCell.textContent = steamworkAssetSpecText(item.spec);
  summaryNode.appendChild(specCell);

  const currentCell = document.createElement("div");
  currentCell.className = `steamwork-asset-currentcell ${primaryFile ? "" : "is-empty"}`.trim();
  currentCell.dataset.label = text("steamworkCurrentColumn");
  const currentName = document.createElement("span");
  currentName.className = "steamwork-current-name";
  currentName.textContent = primaryFile ? steamworkAssetFileDisplayName(primaryFile) : text("steamworkAssetNoFile");
  if (primaryFile?.name && currentName.textContent !== primaryFile.name) {
    currentName.title = primaryFile.name;
  }
  currentCell.appendChild(currentName);
  const primarySource = steamworkAssetFolderLabel(primaryFile);
  if (primarySource) {
    const source = document.createElement("span");
    source.className = "steamwork-current-source";
    source.textContent = primarySource;
    currentCell.appendChild(source);
  }
  if (fileCount > 1) {
    const currentMeta = document.createElement("span");
    currentMeta.className = "steamwork-current-meta";
    currentMeta.textContent = text("steamworkAssetFileCount", fileCount);
    currentCell.appendChild(currentMeta);
  }
  if (item.issue && item.status !== "optional") {
    const issue = document.createElement("div");
    issue.className = "steamwork-current-meta";
    issue.textContent = steamworkAssetIssueText(item.issue);
    currentCell.appendChild(issue);
  }
  summaryNode.appendChild(currentCell);

  const where = document.createElement("span");
  where.className = "steamwork-asset-where";
  where.dataset.label = text("steamworkTargetColumn");
  where.textContent = steamworkAssetTargetText(item.target);
  summaryNode.appendChild(where);
  card.appendChild(summaryNode);

  const candidateDisplay = steamworkCandidateDisplay(item, allFiles);
  const showCandidateGroup = shouldShowSteamworkCandidateGroup(item, candidateDisplay);
  const details = document.createElement("div");
  details.className = `steamwork-asset-details ${fileCount ? "" : "no-current"} ${showCandidateGroup ? "" : "no-candidates"}`.trim();
  const detailStack = document.createElement("div");
  detailStack.className = "steamwork-asset-detail-stack";
  const missingGuide = createSteamworkMissingGuide(item);
  const optionalGuide = createSteamworkOptionalGuide(item);
  if (missingGuide || optionalGuide) {
    details.classList.add("has-guide");
  }
  if (missingGuide) {
    detailStack.appendChild(missingGuide);
  }
  if (optionalGuide) {
    detailStack.appendChild(optionalGuide);
  }
  const currentGroup = renderSteamworkAssetGroup(text("steamworkAssetMatched"), item.files, text("steamworkAssetNoFile"), {
    assetId: item.id,
    limit: steamworkCurrentGroupLimit(fileCount),
    emptyDetails: item.status === "missing" || item.status === "optional"
      ? []
      : [
        text("steamworkAssetNeedSpec", steamworkAssetSpecText(item.spec)),
        text("steamworkAssetWhereToUse", steamworkAssetTargetText(item.target))
      ]
  });
  detailStack.append(currentGroup, createSteamworkAssetStageZone(item));
  details.appendChild(detailStack);
  if (showCandidateGroup) {
    const optionalReference = item.status === "optional" && candidateDisplay.reference;
    const candidateGroup = renderSteamworkAssetGroup(
      optionalReference
        ? text("steamworkAssetOptionalCandidates")
        : candidateDisplay.reference
          ? text("steamworkAssetReferenceCandidates")
          : text("steamworkAssetCandidates"),
      candidateDisplay.files,
      text("steamworkAssetNoCandidates"),
      {
        candidate: true,
        requirement: item,
        reference: candidateDisplay.reference,
        optionalReference,
        note: optionalReference
          ? text("steamworkAssetOptionalReferenceHint")
          : candidateDisplay.reference
            ? text("steamworkAssetReferenceHint")
            : "",
        limit: steamworkCandidateGroupLimitForItem(item, candidateDisplay.files.length)
      }
    );
    details.appendChild(candidateGroup);
  }
  card.appendChild(details);

  return card;
}

function renderSteamworkAssets(state) {
  if (!hasSteamwork || !els.steamworkAssetList) return;
  const summary = state?.summary || {};
  const items = Array.isArray(state?.items) ? state.items : [];
  const allFiles = Array.isArray(state?.files) ? state.files : [];
  steamworkThumbsEnabled = Boolean(state?.thumbs);
  setSteamworkAssetRoot(state?.root || "D:\\ArtAsset");

  renderSteamworkAssetSummaryPills(summary, items.length);

  const openIds = new Set(
    [...els.steamworkAssetList.querySelectorAll(".steamwork-asset-card[open]")]
      .map(node => node.dataset.slot)
      .filter(Boolean)
  );
  els.steamworkAssetList.innerHTML = "";

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "steamwork-empty";
    empty.textContent = text("steamworkAssetNoFile");
    els.steamworkAssetList.appendChild(empty);
    return;
  }

  const categoryOrder = ["Store", "Library", "Community", "Video"];
  const attention = renderSteamworkAssetAttention(items);
  if (attention) els.steamworkAssetList.appendChild(attention);
  const categoryNav = renderSteamworkCategoryNav(items, categoryOrder);
  if (categoryNav) els.steamworkAssetList.appendChild(categoryNav);

  for (const categoryName of categoryOrder) {
    const categoryItems = items.filter(item => item.category === categoryName);
    if (!categoryItems.length) continue;

    const section = document.createElement("section");
    section.className = "steamwork-asset-category";
    section.dataset.category = categoryName;

    const head = document.createElement("div");
    head.className = "steamwork-category-head";
    const title = document.createElement("h4");
    title.textContent = steamworkCategoryLabel(categoryName);
    head.append(title, createSteamworkCategorySummary(categoryItems));
    section.appendChild(head);

    const body = document.createElement("div");
    body.className = "steamwork-category-body";
    const columns = document.createElement("div");
    columns.className = "steamwork-category-columns";
    for (const label of [
      text("steamworkAssetColumn"),
      text("steamworkStatusColumn"),
      text("steamworkSpecColumn"),
      text("steamworkCurrentColumn"),
      text("steamworkTargetColumn")
    ]) {
      const cell = document.createElement("span");
      cell.textContent = label;
      columns.appendChild(cell);
    }
    columns.appendChild(document.createElement("span"));
    body.appendChild(columns);
    for (const item of categoryItems) {
      body.appendChild(createSteamworkAssetCard(item, openIds, allFiles));
    }
    section.appendChild(body);
    els.steamworkAssetList.appendChild(section);
  }
}

async function loadSteamworkAssets() {
  if (!hasSteamwork || !els.steamworkAssetList) return;
  setSteamworkAssetSummaryText(text("steamworkAssetLoading"));
  setSteamworkAssetRoot("");
  try {
    const response = await fetch("/api/steamwork/assets", { cache: "no-store" });
    const state = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(state.error || `HTTP ${response.status}`);
    renderSteamworkAssets(state);
    setSteamworkStatus(text("steamworkAssetSource", state.root || "D:\\ArtAsset"));
  } catch (error) {
    const message = text("steamworkAssetLoadFailed", error.message);
    setSteamworkStatus(message);
    setSteamworkAssetRoot("D:\\ArtAsset");
    setSteamworkAssetSummaryText(message);
  }
}

async function stageSteamworkAssetFiles(slot, files, label = slot) {
  if (!hasSteamwork || !slot) return;
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;

  const formData = new FormData();
  selectedFiles.forEach(file => formData.append("files", file, file.name));
  setSteamworkStatus(text("steamworkAssetStaging", selectedFiles.length, label));

  try {
    const response = await fetch(`/api/steamwork/assets/stage/${encodeURIComponent(slot)}`, {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    if (result.state) {
      renderSteamworkAssets(result.state);
    } else {
      await loadSteamworkAssets();
    }
    const count = Array.isArray(result.files) ? result.files.length : selectedFiles.length;
    setSteamworkStatus(text("steamworkAssetStaged", count, result.destination || "D:\\ArtAsset"));
  } catch (error) {
    setSteamworkStatus(text("steamworkAssetStageFailed", error.message));
  } finally {
    if (els.steamworkAssetFileInput) {
      els.steamworkAssetFileInput.value = "";
    }
  }
}

async function openSteamworkAsset(path) {
  if (!path) return;
  try {
    await postJson("/api/steamwork/open-asset", { path });
  } catch (error) {
    setSteamworkStatus(text("steamworkAssetOpenFailed", error.message));
  }
}

async function uploadRenderTextureFiles(files) {
  if (!hasMaterialWorkspace) return;
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) return;
  if (!downloadIntakeEnabled) {
    setRenderTextureStatus(text("renderTextureDisabled"));
    return;
  }

  const formData = new FormData();
  for (const file of selectedFiles) {
    formData.append("files", file, file.name);
  }

  setRenderTextureStatus(text("renderTextureImporting", selectedFiles.length));
  els.renderTextureDropzone.classList.add("busy");
  try {
    const response = await fetch("/api/workzones/render-textures/upload", {
      method: "POST",
      body: formData
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    materialCandidates = Array.isArray(result.candidates) ? result.candidates : materialCandidates;
    materialNotice = text("renderTextureImported", result.folder || "render-textures", Array.isArray(result.files) ? result.files.length : 0);
    setRenderTextureStatus(materialNotice);
    renderMaterialImport(result);
  } catch (error) {
    setRenderTextureStatus(text("renderTextureFailed", error.message));
  } finally {
    els.renderTextureDropzone.classList.remove("busy", "drag-over");
    if (els.workzoneFileInput) els.workzoneFileInput.value = "";
  }
}

function tick() {
  if (!els.localTime) return;
  const nextClock = formatClock(new Date());
  if (els.localTime.textContent !== nextClock) {
    els.localTime.textContent = nextClock;
  }
}

function scheduleClockTick() {
  if (clockTickTimer) {
    window.clearTimeout(clockTickTimer);
    clockTickTimer = 0;
  }
  tick();
  if (!els.localTime || document.hidden) return;
  const now = new Date();
  const nextMinuteDelay = 60000 - (now.getSeconds() * 1000 + now.getMilliseconds()) + 30;
  clockTickTimer = window.setTimeout(scheduleClockTick, Math.max(500, nextMinuteDelay));
}

if (els.languageToggle) els.languageToggle.addEventListener("click", () => {
  language = language === "zh" ? "en" : "zh";
  localStorage.setItem(storageKeys.language, language);
  applyLanguage();
});
if (els.themeToggle) els.themeToggle.addEventListener("click", () => {
  setTheme(nextTheme(theme));
});
if (els.tutorialModeToggle) els.tutorialModeToggle.addEventListener("click", toggleTutorialMode);
if (els.feedbackTop) els.feedbackTop.addEventListener("click", openFeedbackPanel);
if (els.moduleArchiveDrop) els.moduleArchiveDrop.addEventListener("click", event => {
  event.stopPropagation();
  const nextView = event.ctrlKey || event.metaKey ? "deep" : "main";
  const shouldExpand = archiveView !== nextView || !archiveExpanded;
  archiveView = nextView;
  renderModuleArchive();
  setArchiveExpanded(shouldExpand);
});
if (els.moduleArchive) els.moduleArchive.addEventListener("mouseup", handleArchiveRightRelease);
if (els.moduleArchive) els.moduleArchive.addEventListener("contextmenu", event => {
  event.preventDefault();
  event.stopPropagation();
});
window.addEventListener("popstate", () => {
  activateModule(moduleIdFromPage(currentPageName()), false);
});
if (hasWallpaper) els.addWallpaper.addEventListener("click", openAddWallpaperPicker);
if (hasWallpaper) els.wallpaperFileInput.addEventListener("change", event => uploadWallpaperFiles(event.target.files));
if (hasWallpaper) els.wallpaperPreview.addEventListener("dblclick", () => applyWallpaper());
if (hasWallpaper) els.wallpaperPreview.addEventListener("keydown", event => {
  if (event.key === "Enter") {
    applyWallpaper();
  }
});
if (hasMusic) els.musicFileInput.addEventListener("change", event => uploadMusicFiles(event.target.files));
if (hasMusic && els.addMusic) els.addMusic.addEventListener("click", toggleMusicAddMenu);
if (hasMusic && els.addMusicByUrl) els.addMusicByUrl.addEventListener("click", showMusicAddUrlForm);
if (hasMusic && els.addMusicByFile) els.addMusicByFile.addEventListener("click", openAddMusicPicker);
if (hasMusic && els.addMusicByLibrary) els.addMusicByLibrary.addEventListener("click", showMusicAddLibraryForm);
if (hasMusic && els.musicAddUrlForm) els.musicAddUrlForm.addEventListener("submit", submitMusicAddUrl);
if (hasMusic && els.musicAddLibraryForm) els.musicAddLibraryForm.addEventListener("submit", submitMusicAddLibrary);
if (hasMusic && els.musicAddCookieButton) {
  els.musicAddCookieButton.addEventListener("click", () => {
    if (els.musicCookieFileInput) els.musicCookieFileInput.click();
  });
}
if (hasMusic && els.musicCookieFileInput) {
  els.musicCookieFileInput.addEventListener("change", event => uploadMusicCookieFile(event.target.files));
}
if (hasSteamwork && els.openSteamworkDashboard) {
  els.openSteamworkDashboard.addEventListener("click", () => openSteamworksWebLink(steamworksAppUrl, "steamworkDashboard"));
}
if (hasSteamwork && els.openSteamworkPublishFolder) {
  els.openSteamworkPublishFolder.addEventListener("click", () => openRandomRealmResource("publishFolder", "steamworkPublishRoot"));
}
if (hasSteamwork && els.openSteamworkGameContent) {
  els.openSteamworkGameContent.addEventListener("click", () => openRandomRealmResource("gameContentFolder", "steamworkGameContent"));
}
if (hasSteamwork && els.openSteamworkPublishTool) {
  els.openSteamworkPublishTool.addEventListener("click", () => openRandomRealmResource("publishToolFolder", "steamworkPublishTool"));
}
if (hasSteamwork && els.openSteamworkPublishToolTip) {
  els.openSteamworkPublishToolTip.addEventListener("click", () => openRandomRealmResource("publishToolFolder", "steamworkPublishTool"));
}
if (hasSteamwork && els.openSteamworkBuildsTip) {
  els.openSteamworkBuildsTip.addEventListener("click", () => openSteamworksWebLink(steamworksBuildsUrl, "steamworkBuildsLink"));
}
if (hasSteamwork && els.locateSteamworkPublishTool) {
  els.locateSteamworkPublishTool.addEventListener("click", () => {
    setRandomRealmReleaseStatus(text("steamworkPublishToolChoose"));
    setSteamworkStatus(text("steamworkPublishToolChoose"));
    els.steamworkPublishToolFileInput?.click();
  });
}
if (hasSteamwork && els.openSteamworkArtAsset) {
  els.openSteamworkArtAsset.addEventListener("click", () => openRandomRealmResource("steamworkAssetFolder", "steamworkArtAssets"));
}
if (hasSteamwork && els.steamworkGameContentFileInput) {
  els.steamworkGameContentFileInput.addEventListener("change", event => uploadSteamworkFiles("gameContent", event.target.files));
}
if (hasSteamwork && els.steamworkPublishToolFileInput) {
  els.steamworkPublishToolFileInput.addEventListener("change", event => uploadSteamworkFiles("publishTool", event.target.files));
}
if (hasSteamwork && els.steamworkAssetList) {
  els.steamworkAssetList.addEventListener("click", event => {
    const categoryJump = event.target.closest(".steamwork-category-jump");
    if (categoryJump) {
      event.preventDefault();
      const category = categoryJump.dataset.category || "";
      const section = Array.from(els.steamworkAssetList.querySelectorAll(".steamwork-asset-category"))
        .find(node => node.dataset.category === category);
      section?.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }

    const jump = event.target.closest(".steamwork-asset-alert");
    if (jump) {
      event.preventDefault();
      const card = Array.from(els.steamworkAssetList.querySelectorAll(".steamwork-asset-card"))
        .find(node => node.dataset.slot === (jump.dataset.slot || ""));
      if (card) {
        card.open = true;
        window.requestAnimationFrame(() => {
          const rect = card.getBoundingClientRect();
          const scrollRoot = document.scrollingElement || document.documentElement;
          const viewportGap = Math.max(12, (window.innerHeight - Math.min(rect.height, window.innerHeight)) / 2);
          scrollRoot.scrollTop = Math.max(0, scrollRoot.scrollTop + rect.top - viewportGap);
          card.querySelector(".steamwork-asset-summary")?.focus?.({ preventScroll: true });
        });
      }
      return;
    }

    const button = event.target.closest(".steamwork-open-asset");
    if (!button) return;
    event.preventDefault();
    openSteamworkAsset(button.dataset.path || "");
  });
}
if (hasSteamwork && els.steamworkAssetFileInput) {
  els.steamworkAssetFileInput.addEventListener("change", event => {
    stageSteamworkAssetFiles(pendingSteamworkAssetSlot, event.target.files, pendingSteamworkAssetSlot);
  });
}
bindSteamworkDropzone("gameContent", els.steamworkGameContentDropzone, els.steamworkGameContentFileInput);
bindSteamworkDropzone("publishTool", els.steamworkPublishToolDropzone, els.steamworkPublishToolFileInput);
if (hasMusic) els.musicDock.addEventListener("dragover", handleLocalMusicDragOver);
if (hasMusic) els.musicDock.addEventListener("dragleave", handleLocalMusicDragLeave);
if (hasMusic) els.musicDock.addEventListener("drop", handleLocalMusicDrop);
if (hasMusic && els.nowPlayingArt) els.nowPlayingArt.addEventListener("dblclick", toggleNowPlayingLyrics);
if (hasMusic && els.nowPlayingLyricsPanel) {
  els.nowPlayingLyricsPanel.addEventListener("pointerdown", beginLyricsPanelResize);
  els.nowPlayingLyricsPanel.addEventListener("pointermove", setLyricsPanelResizeHover);
  els.nowPlayingLyricsPanel.addEventListener("pointerleave", clearLyricsPanelResizeHover);
  window.addEventListener("resize", resizeLyricsPanelToViewport);
}
if (hasMusic && els.nowPlayingLyricsList) {
  els.nowPlayingLyricsList.addEventListener("contextmenu", openLyricsTimingEditorFromContext);
}
if (hasMusic && els.lyricsTimingEditor) bindLyricsTimingEditorEvents(els.lyricsTimingEditor);
if (hasMusic) window.addEventListener("beforeunload", () => {
  flushPendingMusicLyricMarks({ beacon: true });
  flushMusicStateBeforeUnload();
});
document.addEventListener("visibilitychange", () => {
  if (hasMusic && document.visibilityState === "hidden") {
    flushPendingMusicLyricMarks({ beacon: true });
    flushMusicStateBeforeUnload();
  }
  scheduleClockTick();
  syncRuntimeActivity({ resume: document.visibilityState === "visible" });
});
if (hasMusic) els.previousTrack.addEventListener("click", () => playRelativeTrack(-1));
if (hasMusic) els.playPauseTrack.addEventListener("click", togglePlayback);
if (hasMusic) els.nextTrack.addEventListener("click", () => playRelativeTrack(1));
if (hasMusic && els.playbackModeToggle) els.playbackModeToggle.addEventListener("click", cyclePlaybackMode);
if (hasMusic) (els.trackSeekArea || els.trackSeek).addEventListener("pointerdown", beginTrackSeek);
if (hasMusic) els.trackSeek.addEventListener("lostpointercapture", finishTrackSeek);
if (hasMusic) els.trackSeek.addEventListener("change", finishTrackSeek);
if (hasMusic) els.trackSeek.addEventListener("input", handleTrackSeekInput);
if (hasMusic) els.trackVolume.addEventListener("pointerdown", beginVolumeGesture);
if (hasMusic) els.trackVolume.addEventListener("keydown", event => {
  if (event.key.startsWith("Arrow") || event.key === "Home" || event.key === "End" || event.key === "PageUp" || event.key === "PageDown") {
    beginVolumeGesture();
  }
});
if (hasMusic) els.trackVolume.addEventListener("input", () => {
  beginVolumeGesture();
  setTrackVolume(els.trackVolume.value);
});
if (hasMusic) els.trackVolume.addEventListener("change", commitVolumeGesture);
if (hasMusic) els.trackVolume.addEventListener("pointerup", commitVolumeGesture);
if (hasMusic) els.trackVolume.addEventListener("pointercancel", commitVolumeGesture);
if (hasMusic) els.trackVolume.addEventListener("blur", commitVolumeGesture);
if (hasMusic) els.audioPlayer.addEventListener("loadedmetadata", updateTrackProgress);
if (hasMusic) els.audioPlayer.addEventListener("durationchange", updateTrackProgress);
if (hasMusic) els.audioPlayer.addEventListener("canplay", updateTrackProgress);
if (hasMusic) els.audioPlayer.addEventListener("seeked", updateTrackProgress);
if (hasMusic) els.audioPlayer.addEventListener("timeupdate", updateTrackProgress);
if (hasMusic) els.audioPlayer.addEventListener("play", () => {
  renderMusic();
  renderMusicLibraries();
  syncLyricsAnimationLoop();
});
if (hasMusic) els.audioPlayer.addEventListener("pause", () => {
  stopLyricsAnimationLoop();
  renderMusic();
  renderMusicLibraries();
});
if (hasMusic) els.audioPlayer.addEventListener("ended", () => {
  stopLyricsAnimationLoop();
  handleTrackEnded();
});
if (hasMusic) els.audioPlayer.addEventListener("error", () => {
  stopLyricsAnimationLoop();
  musicNotice = text("musicPlayFailed", "unsupported or unavailable audio");
  renderMusic();
});
if (els.openSteamworks) {
  els.openSteamworks.addEventListener("click", () => openSteamworksWebLink(steamworksAppUrl, "randomRealmSteamworks"));
}
if (els.openSteamPublishFolder) {
  els.openSteamPublishFolder.addEventListener("click", () => openRandomRealmResource("publishFolder", "randomRealmPublishFolder"));
}
if (els.openRandomRealmPromo) {
  els.openRandomRealmPromo.addEventListener("click", () => openRandomRealmResource("promoFolder", "randomRealmPromoFolder"));
}
if (els.openRandomRealmProject) {
  els.openRandomRealmProject.addEventListener("click", () => openRandomRealmResource("projectFolder", "randomRealmProjectFolder"));
}
if (els.openUnityProjectFolder) {
  els.openUnityProjectFolder.addEventListener("click", () => openRandomRealmResource("projectFolder", "randomRealmProjectFolder"));
}
if (els.openUnityPromoFolder) {
  els.openUnityPromoFolder.addEventListener("click", () => openRandomRealmResource("promoFolder", "randomRealmPromoFolder"));
}
for (const button of document.querySelectorAll("[data-console-view-target]")) {
  button.addEventListener("click", () => setConsoleWorkspaceView(button.dataset.consoleViewTarget));
  button.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const buttons = Array.from(document.querySelectorAll("[data-console-view-target]"));
    const currentIndex = buttons.indexOf(button);
    if (currentIndex < 0) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = buttons[(currentIndex + direction + buttons.length) % buttons.length];
    next?.focus();
    setConsoleWorkspaceView(next?.dataset.consoleViewTarget);
  });
}
for (const button of document.querySelectorAll("[data-blender-view-target]")) {
  button.addEventListener("click", () => setBlenderWorkspaceView(button.dataset.blenderViewTarget));
  button.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const buttons = Array.from(document.querySelectorAll("[data-blender-view-target]"));
    const currentIndex = buttons.indexOf(button);
    if (currentIndex < 0) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = buttons[(currentIndex + direction + buttons.length) % buttons.length];
    next?.focus();
    setBlenderWorkspaceView(next?.dataset.blenderViewTarget);
  });
}
for (const trigger of document.querySelectorAll("[data-blender-view-jump]")) {
  trigger.addEventListener("click", () => setBlenderWorkspaceView(trigger.dataset.blenderViewJump));
}
for (const trigger of document.querySelectorAll("[data-blender-helper-jump]")) {
  trigger.addEventListener("click", () => {
    const target = document.getElementById(trigger.dataset.blenderHelperJump);
    target?.scrollIntoView({
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "auto" : "smooth",
      block: "start"
    });
    window.setTimeout(() => els.blenderGithubProject?.focus({ preventScroll: true }), 260);
  });
}
if (els.blenderGithubToggle) {
  setBlenderGithubExpanded(true);
  els.blenderGithubToggle.addEventListener("dblclick", event => {
    event.preventDefault();
    setBlenderGithubExpanded(els.blenderGithubToggle.getAttribute("aria-expanded") !== "true");
  });
  els.blenderGithubToggle.addEventListener("keydown", event => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setBlenderGithubExpanded(els.blenderGithubToggle.getAttribute("aria-expanded") !== "true");
  });
}
if (els.blenderGithubAdd) {
  els.blenderGithubAdd.addEventListener("click", addBlenderGithubProject);
}
if (els.blenderGithubProject) {
  els.blenderGithubProject.addEventListener("change", () => {
    syncBlenderGithubProjectContext(els.blenderGithubProject.value);
    loadBlenderGithubShare({ project: els.blenderGithubProject.value });
  });
}
if (els.blenderGithubRefresh) {
  els.blenderGithubRefresh.addEventListener("click", () => loadBlenderGithubShare({
    project: els.blenderGithubProject?.value
      || blenderGithubShareState?.project?.repositoryUrl
      || blenderGithubShareState?.project?.path
      || ""
  }));
}
if (els.blenderGithubBlendCards) {
  els.blenderGithubBlendCards.addEventListener("dragstart", event => {
    const card = event.target.closest(".blender-github-blend-card");
    const path = card?.dataset.projectPath || "";
    if (!card || !path || blenderGithubBusy) {
      event.preventDefault();
      return;
    }
    clearBlenderGithubCardClick();
    blenderGithubDraggedPath = path;
    blenderGithubDropCommitted = false;
    card.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-codex-blender-project", path);
    event.dataTransfer.setData("text/plain", path);
    if (typeof event.dataTransfer.setDragImage === "function") {
      event.dataTransfer.setDragImage(card, 24, 24);
    }
  });
  els.blenderGithubBlendCards.addEventListener("dragover", event => {
    if (!blenderGithubDraggedPath) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const dragging = els.blenderGithubBlendCards.querySelector(".blender-github-blend-card.dragging");
    const target = event.target.closest(".blender-github-blend-card");
    if (!dragging) return;
    if (!target) {
      els.blenderGithubBlendCards.appendChild(dragging);
      return;
    }
    if (target === dragging) return;
    const bounds = target.getBoundingClientRect();
    const horizontal = Math.abs(event.clientY - (bounds.top + bounds.height / 2)) < bounds.height * 0.42;
    const placeAfter = horizontal
      ? event.clientX > bounds.left + bounds.width / 2
      : event.clientY > bounds.top + bounds.height / 2;
    els.blenderGithubBlendCards.insertBefore(dragging, placeAfter ? target.nextSibling : target);
  });
  els.blenderGithubBlendCards.addEventListener("drop", event => {
    if (!blenderGithubDraggedPath) return;
    event.preventDefault();
    blenderGithubDropCommitted = true;
    saveBlenderGithubCardOrder();
  });
  els.blenderGithubBlendCards.addEventListener("dragend", () => {
    const committed = blenderGithubDropCommitted;
    els.blenderGithubBlendCards.querySelectorAll(".dragging").forEach(card => card.classList.remove("dragging"));
    blenderGithubDraggedPath = "";
    blenderGithubDropCommitted = false;
    if (!committed && blenderGithubShareState) {
      renderBlenderGithubBlendCards(blenderGithubShareState);
    }
  });
}
for (const input of document.querySelectorAll('input[name="blenderGithubVisibility"]')) {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    if (input.value === "public" && !blenderGithubPublicConfirmed) {
      if (!window.confirm(text("blenderGithubPublicConfirm"))) {
        setBlenderGithubCheckedValue("blenderGithubVisibility", "private");
        return;
      }
      blenderGithubPublicConfirmed = true;
    } else if (input.value === "private") {
      blenderGithubPublicConfirmed = false;
    }
    saveBlenderGithubShare();
  });
}
for (const input of document.querySelectorAll('input[name="blenderGithubScope"]')) {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    renderBlenderGithubCustomScope();
    saveBlenderGithubShare();
  });
}
for (const field of [
  els.blenderGithubRepository,
  els.blenderGithubVersion,
  els.blenderGithubMessage,
  els.blenderGithubIncludes,
  els.blenderGithubExcludes
].filter(Boolean)) {
  field.addEventListener("change", () => saveBlenderGithubShare());
}
if (els.blenderGithubRepository) {
  els.blenderGithubRepository.addEventListener("input", updateBlenderGithubActionState);
}
if (els.blenderGithubInitialize) {
  els.blenderGithubInitialize.addEventListener("click", () => runBlenderGithubAction("init"));
}
if (els.blenderGithubCommit) {
  els.blenderGithubCommit.addEventListener("click", () => runBlenderGithubAction("commit"));
}
if (els.blenderGithubPush) {
  els.blenderGithubPush.addEventListener("click", () => runBlenderGithubAction("push"));
}
if (els.blenderGithubOpen) {
  els.blenderGithubOpen.addEventListener("click", () => openBlenderGithubTarget("github"));
}
if (els.blenderGithubDesktop) {
  els.blenderGithubDesktop.addEventListener("click", () => openBlenderGithubTarget("desktop"));
}
if (els.blenderGithubFolder) {
  els.blenderGithubFolder.addEventListener("click", () => openBlenderGithubTarget("folder"));
}
for (const field of [
  els.randomRealmArtType
].filter(Boolean)) {
  field.addEventListener("input", updateRandomRealmArtContext);
  field.addEventListener("change", updateRandomRealmArtContext);
}
for (const field of [
  els.blenderPromptFormat,
  els.blenderPromptImage,
  els.blenderPromptCustomWidth,
  els.blenderPromptCustomLength,
  els.blenderPromptStyle,
  els.blenderPromptBasics
].filter(Boolean)) {
  field.addEventListener("input", updateBlenderPromptOutput);
}
if (els.blenderPromptResolution) {
  els.blenderPromptResolution.addEventListener("change", () => {
    renderBlenderPromptResolution();
    updateBlenderPromptOutput();
    if (els.blenderPromptResolution.value === "custom") {
      els.blenderPromptCustomWidth?.focus();
    }
  });
}
if (els.generateBlenderPrompt) {
  els.generateBlenderPrompt.addEventListener("click", generateBlenderPrompt);
}
if (els.copyBlenderPrompt) {
  els.copyBlenderPrompt.addEventListener("click", copyBlenderPrompt);
}
if (els.clearBlenderPrompt) {
  els.clearBlenderPrompt.addEventListener("click", clearBlenderPrompt);
}
if (els.randomRealmProjectSearch) {
  els.randomRealmProjectSearch.addEventListener("input", scheduleRandomRealmProjectSearch);
  els.randomRealmProjectSearch.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (randomRealmProjectSearchTimer) {
        window.clearTimeout(randomRealmProjectSearchTimer);
        randomRealmProjectSearchTimer = null;
      }
      loadRandomRealmBlenderProjects({ loadObjects: false });
    }
  });
}
if (els.randomRealmBlenderProject) {
  els.randomRealmBlenderProject.addEventListener("change", () => {
    randomRealmArtContext.project = els.randomRealmBlenderProject.value;
    randomRealmLoadedObjectsProject = "";
    randomRealmLastLiveObject = "";
    randomRealmLiveSelectedObjects = [];
    updateRandomRealmProjectAddress();
    saveRandomRealmArtContext();
    loadRandomRealmBlenderObjects();
  });
}
if (els.randomRealmSyncLiveSelection) {
  els.randomRealmSyncLiveSelection.addEventListener("click", () => syncRandomRealmLiveSelection({ quiet: false }));
}
if (els.randomRealmObjectSearch) {
  els.randomRealmObjectSearch.addEventListener("focus", () => openRandomRealmObjectPicker({ selectText: true }));
  els.randomRealmObjectSearch.addEventListener("click", () => {
    if (!randomRealmObjectPickerOpen) {
      openRandomRealmObjectPicker({ selectText: true });
    }
  });
  els.randomRealmObjectSearch.addEventListener("input", () => {
    setRandomRealmObjectPickerOpen(true);
    renderRandomRealmBlenderObjects();
  });
  els.randomRealmObjectSearch.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault();
      setRandomRealmObjectPickerOpen(false);
      return;
    }
    if ((event.key === "Backspace" || event.key === "Delete") && els.randomRealmObjectSearch.selectionStart === 0 && els.randomRealmObjectSearch.selectionEnd === els.randomRealmObjectSearch.value.length) {
      event.preventDefault();
      clearRandomRealmObjectSearch();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openRandomRealmObjectPicker();
      els.randomRealmBlenderObject?.focus();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      openRandomRealmObjectPicker();
      confirmRandomRealmObjectSelection();
    }
  });
}
if (els.randomRealmBlenderObject) {
  els.randomRealmBlenderObject.addEventListener("change", () => {
    randomRealmSelectedOldTexture = null;
    randomRealmSelectedMaterial = "";
    randomRealmAddMapMode = false;
    renderRandomRealmUsedTextures();
  });
  els.randomRealmBlenderObject.addEventListener("dblclick", confirmRandomRealmObjectSelection);
  els.randomRealmBlenderObject.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      confirmRandomRealmObjectSelection();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setRandomRealmObjectPickerOpen(false);
      els.randomRealmObjectSearch?.focus();
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      clearRandomRealmObjectSearch();
      els.randomRealmObjectSearch?.focus();
    }
  });
}
if (els.randomRealmTextureFileInput) {
  els.randomRealmTextureFileInput.addEventListener("change", event => uploadRandomRealmNewTexture(event.target.files));
}
if (els.randomRealmTextureKind) {
  els.randomRealmTextureKind.addEventListener("change", () => {
    selectRandomRealmStagedTextureForKind(els.randomRealmTextureKind.value);
    renderRandomRealmUsedTextures();
    scheduleRandomRealmTextureAutoPack();
  });
}
if (els.randomRealmStageBlankTexture) {
  els.randomRealmStageBlankTexture.addEventListener("click", stageRandomRealmBlankTexture);
}
if (els.randomRealmClearNewTexture) {
  els.randomRealmClearNewTexture.addEventListener("keydown", event => {
    event.stopPropagation();
  });
  els.randomRealmClearNewTexture.addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
    clearRandomRealmNewTexture();
  });
}
if (els.randomRealmNewTextureDrop) {
  els.randomRealmNewTextureDrop.addEventListener("click", () => els.randomRealmTextureFileInput?.click());
  els.randomRealmNewTextureDrop.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      els.randomRealmTextureFileInput?.click();
    }
  });
  els.randomRealmNewTextureDrop.addEventListener("dragover", event => {
    event.preventDefault();
    els.randomRealmNewTextureDrop.classList.add("drag-over");
  });
  els.randomRealmNewTextureDrop.addEventListener("dragleave", event => {
    if (!els.randomRealmNewTextureDrop.contains(event.relatedTarget)) {
      els.randomRealmNewTextureDrop.classList.remove("drag-over");
    }
  });
  els.randomRealmNewTextureDrop.addEventListener("drop", event => {
    event.preventDefault();
    uploadRandomRealmNewTexture(event.dataTransfer.files);
  });
}
if (hasMaterialWorkspace && els.downloadIntakeToggle) els.downloadIntakeToggle.addEventListener("change", () => {
  downloadIntakeEnabled = els.downloadIntakeToggle.checked;
  localStorage.setItem(storageKeys.downloadIntake, String(downloadIntakeEnabled));
  if (downloadIntakeEnabled) {
    loadMaterialCandidates();
  } else {
    materialCandidates = [];
    selectedMaterialPath = "";
    materialNotice = text("renderTextureDisabled");
    renderTextureNotice = text("renderTextureDisabled");
    renderMaterialImport();
  }
});
if (hasMaterialWorkspace && els.openDownloads) els.openDownloads.addEventListener("click", openDownloadsFolder);
if (hasMaterialWorkspace && els.refreshMaterialCandidates) els.refreshMaterialCandidates.addEventListener("click", loadMaterialCandidates);
if (hasMaterialWorkspace && els.importMaterial) els.importMaterial.addEventListener("click", () => importMaterialCandidate());
if (hasMaterialWorkspace && els.renderTextureDropzone) {
  els.renderTextureDropzone.addEventListener("click", () => {
    if (downloadIntakeEnabled && els.workzoneFileInput) els.workzoneFileInput.click();
  });
  els.renderTextureDropzone.addEventListener("keydown", event => {
    if ((event.key === "Enter" || event.key === " ") && downloadIntakeEnabled && els.workzoneFileInput) {
      event.preventDefault();
      els.workzoneFileInput.click();
    }
  });
  els.renderTextureDropzone.addEventListener("dragover", event => {
    event.preventDefault();
    if (!downloadIntakeEnabled) {
      setRenderTextureStatus(text("renderTextureDisabled"));
      return;
    }
    els.renderTextureDropzone.classList.add("drag-over");
    setRenderTextureStatus(text("renderTextureDragging"));
  });
  els.renderTextureDropzone.addEventListener("dragleave", event => {
    if (!els.renderTextureDropzone.contains(event.relatedTarget)) {
      els.renderTextureDropzone.classList.remove("drag-over");
      setRenderTextureStatus();
    }
  });
  els.renderTextureDropzone.addEventListener("drop", event => {
    event.preventDefault();
    els.renderTextureDropzone.classList.remove("drag-over");
    uploadRenderTextureFiles(event.dataTransfer.files);
  });
}
if (hasMaterialWorkspace && els.workzoneFileInput) {
  els.workzoneFileInput.addEventListener("change", event => uploadRenderTextureFiles(event.target.files));
}
if (hasWorkspace && els.openGithubDownloads) {
  els.openGithubDownloads.addEventListener("click", openGithubDownloads);
}
if (hasWorkspace && els.githubDownloadsLink) {
  els.githubDownloadsLink.addEventListener("click", event => {
    if (!githubDownloadsInfo?.configured) {
      event.preventDefault();
    }
  });
}
if (els.consoleUpdateAuto) {
  els.consoleUpdateAuto.addEventListener("change", saveProductUpdatePreference);
}
if (els.consoleUpdateRefresh) {
  els.consoleUpdateRefresh.addEventListener("click", () => loadProductUpdateStatuses({ force: true }));
}
if (els.consoleUpdateInstall) {
  els.consoleUpdateInstall.addEventListener("click", () => installSelectedProductUpdate());
}
if (els.consoleUninstall) {
  els.consoleUninstall.addEventListener("click", () => uninstallSelectedProduct());
}
if (els.consoleUpdateTop) {
  els.consoleUpdateTop.addEventListener("click", handleProductUpdateTop);
}
if (els.updateProductConsole) {
  els.updateProductConsole.addEventListener("click", () => selectUpdateProduct("console"));
}
if (els.updateProductWorld) {
  els.updateProductWorld.addEventListener("click", () => selectUpdateProduct("world"));
}
if (els.desktopLayoutPlan) {
  els.desktopLayoutPlan.addEventListener("change", selectDesktopLayoutPlan);
}
if (els.desktopLayoutRestore) {
  els.desktopLayoutRestore.addEventListener("click", restoreDesktopLayout);
}
if (els.desktopLayoutSave) {
  els.desktopLayoutSave.addEventListener("click", saveDesktopLayout);
}
if (els.desktopLayoutImport) {
  els.desktopLayoutImport.addEventListener("click", () => els.desktopLayoutFileInput?.click());
}
if (els.desktopLayoutFileInput) {
  els.desktopLayoutFileInput.addEventListener("change", event => importDesktopLayouts(event.target.files));
}
if (els.feedbackForm) {
  els.feedbackForm.addEventListener("submit", submitFeedback);
}
if (els.feedbackScreenshotButton) {
  els.feedbackScreenshotButton.addEventListener("click", () => els.feedbackScreenshotInput?.click());
}
if (els.feedbackScreenshotInput) {
  els.feedbackScreenshotInput.addEventListener("change", event => selectFeedbackImage(event.target.files?.[0]));
}
if (els.feedbackRemoveImage) {
  els.feedbackRemoveImage.addEventListener("click", clearFeedbackImage);
}
if (els.feedbackDescription) {
  els.feedbackDescription.addEventListener("paste", event => {
    const image = Array.from(event.clipboardData?.items || [])
      .find(item => item.kind === "file" && item.type.startsWith("image/"))
      ?.getAsFile();
    if (image) selectFeedbackImage(image);
  });
}
if (els.feedbackInboxRefresh) {
  els.feedbackInboxRefresh.addEventListener("click", () => loadFeedbackInbox());
}
if (els.feedbackAdminForm) {
  els.feedbackAdminForm.addEventListener("submit", saveFeedbackAdminConfig);
}
if (hasWorkspace && els.addWorkspaceTodo) {
  els.addWorkspaceTodo.addEventListener("click", addWorkspaceTodo);
}
if (hasWorkspace && els.resetWorkspaceTodo) {
  els.resetWorkspaceTodo.addEventListener("click", () => {
    resetWorkspaceTodoGroups();
    renderWorkspaceTodos();
  });
}
if (hasWorkspace && els.workspaceTodoInput) {
  els.workspaceTodoInput.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      addWorkspaceTodo();
    }
  });
}
document.addEventListener("click", event => {
  if (archiveExpanded && els.moduleArchive && !event.target.closest(".module-archive")) {
    setArchiveExpanded(false);
  }
  if (hasMusic && els.musicAddMenu && !event.target.closest(".music-add-menu-wrap")) {
    setMusicAddMenuOpen(false);
  }
  if (randomRealmObjectPickerOpen && !event.target.closest(".object-picker-field")) {
    setRandomRealmObjectPickerOpen(false);
  }
  if (pendingDeletePath) {
    if (!event.target.closest(".delete-popover") && !event.target.closest(".delete-wallpaper-button")) {
      cancelDeleteWallpaper();
    }
  }
  if (pendingDeleteTrackPath) {
    if (!event.target.closest(".delete-popover") && !event.target.closest(".delete-track-button")) {
      cancelDeleteTrack();
    }
  }
});

document.addEventListener("keydown", event => {
  if (handleConsoleUndoRedoKeydown(event)) return;
  if (handleMusicPlaybackKeydown(event)) return;
  if (handleMusicSeekKeydown(event)) return;
  if (event.key === "Escape" && hasMusic && els.musicAddMenu && !els.musicAddMenu.hidden) {
    setMusicAddMenuOpen(false);
    els.addMusic?.focus();
  }
  if (event.ctrlKey && event.altKey && event.key === "Backspace" && els.clearBlenderPrompt) {
    const active = document.activeElement;
    if (active?.closest?.(".blender-prompt-panel")) {
      event.preventDefault();
      clearBlenderPrompt();
    }
  }
});

const savedVolume = Number(localStorage.getItem(storageKeys.volume));
const initialVolume = Number.isFinite(savedVolume) ? Math.max(0, Math.min(1, savedVolume)) : 0.8;
if (hasMusic) {
  els.audioPlayer.volume = initialVolume;
  els.trackVolume.value = String(initialVolume);
}

applyConsoleEdition(consoleEdition, { activate: false, forceRender: true });
applyLanguage();
setConsoleWorkspaceView(activeConsoleView, { persist: false });
setBlenderWorkspaceView(activeBlenderView, { persist: false });
loadConsoleConfig();
restoreInitialModuleUrl();
renderRandomRealmArtContext();
renderBlenderPromptBuilder();
runtimeActivityReady = true;
syncRuntimeActivity({ resume: true });
loadProductUpdateStatuses({ check: true, quiet: true });
loadDesktopLayout({ quiet: true });
loadFeedbackConfig({ quiet: true });
scheduleClockTick();
