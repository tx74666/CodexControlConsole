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
  lastModule: "codexControl.lastModule.v1",
  downloadIntake: "codexControl.downloadIntake.v1",
  workspaceTodos: "codexControl.workspaceTodos.v1",
  randomRealmArtContext: "codexControl.randomRealmArtContext.v1",
  blenderPromptConfig: "codexControl.blenderPromptConfig.v1"
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
  lite: ["wallpaper", "music"]
};
const moduleMap = new Map(modules.map(item => [item.id, item]));
const initialEditionParams = new URLSearchParams(window.location.search);
const initialEditionQuery = initialEditionParams.get("edition");
const hasEditionQuery = initialEditionParams.has("edition");

function normalizeEdition(value) {
  return String(value || "").trim().toLowerCase() === "lite" ? "lite" : "developer";
}

let consoleEdition = normalizeEdition(hasEditionQuery ? initialEditionQuery : "developer");

const playbackModes = ["repeatAll", "repeatOne"];
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
const musicStateVersion = 2;
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
    blenderSectionLabel: "Blender",
    unitySectionLabel: "Unity",
    unityControlTitle: "Unity Control",
    unityControlBody: "RandomRealm2 工程入口、素材入口和 Unity 侧发布前检查。",
    unityBridgeLabel: "桥接状态",
    unityBridgeTempLabel: "临时导入",
    unityBridgeReady: "等待 Blender 发送",
    unityBridgeBody: "Blender 导出到 Unity temp 后，RandomRealm 导入器再把 temp 内容归类到 Builder 生成资产、Prefab 和清单里。",
    steamworkTitle: "Steamwork",
    steamworkReady: "\u5c31\u7eea",
    steamworkBody: "\u7ba1\u7406 Steamworks\u3001SteamPipeGUI\u3001ContentBuilder/content \u548c\u5ba3\u4f20\u66f4\u65b0\u7d20\u6750\u3002",
    steamworkDashboard: "Steamworks",
    steamworkPublishRoot: "ContentBuilder",
    steamworkGameContent: "Content",
    steamworkPublishTool: "SteamPipeGUI",
    steamworkArtAssets: "\u7d20\u6750",
    steamworkGameContentLabel: "Content",
    steamworkGameContentTitle: "\u5bfc\u5165\u6e38\u620f\u5185\u5bb9",
    steamworkGameContentReady: "\u628a\u6e38\u620f\u6784\u5efa\u6587\u4ef6\u62d6\u5230 ContentBuilder/content\u3002",
    steamworkPublishToolLabel: "SteamPipeGUI",
    steamworkPublishToolTitle: "\u5bfc\u5165 SteamPipeGUI \u5de5\u5177",
    steamworkPublishToolReady: "\u628a SteamPipeGUI \u76f8\u5173\u6587\u4ef6\u62d6\u5230\u8fd9\u91cc\u3002",
    steamworkTipsLabel: "\u53d1\u5e03\u6d41\u7a0b Tips",
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
    steamworkTipConfig: "SteamPipeGUI \u5efa\u8bae\u586b\u5199\uff1aApp ID 3983670\uff0cDepot ID 3983671\uff0cBuild Description \u53ef\u7528 1.5.31\u3002",
    steamworkTipPaths: "\u8def\u5f84\uff1aBuild Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\\content\uff0cContentBuilder Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\u3002",
    steamworkTipLogin: "Steam Login = pixel_roblez\uff1b\u5bc6\u7801\u4e0d\u5199\u8fdb Console\u3002",
    steamworkTipContent: "\u628a\u6253\u5305\u7ed3\u679c\u653e\u5230 ContentBuilder/content\u3002",
    steamworkTipPipe: "\u6253\u5f00 SteamPipe Build Uploader\uff0c\u586b\u5b57\u6bb5\u540e\u4e0a\u4f20\u3002",
    steamworkUploadNote: "PC + Mobile \u786e\u8ba4\u3002",
    steamworkTipRenewDepot: "\u5728\u7f51\u9875\u7248 Steamworks \u91cc Renew / Update Depot\uff0c\u628a\u751f\u6210\u7684 build \u8bbe\u4e3a\u4e0a\u7ebf\u7248\u672c\u3002",
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
    cardTitle: name => `${name}\n双击应用，右键唤出删除`,
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
    previousTrack: "上一首",
    playTrack: "播放",
    pauseTrack: "暂停",
    nextTrack: "下一首",
    playbackModeSequential: "顺序",
    playbackModeRepeatAll: "循环",
    playbackModeRepeatOne: "单曲",
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
    blenderSectionLabel: "Blender",
    unitySectionLabel: "Unity",
    unityControlTitle: "Unity Control",
    unityControlBody: "RandomRealm2 project entry points, promo assets, and Unity-side pre-release checks.",
    unityBridgeLabel: "Bridge",
    unityBridgeTempLabel: "Temp Import",
    unityBridgeReady: "Waiting for Blender",
    unityBridgeBody: "Blender exports into Unity temp; the RandomRealm importer consumes that temp output and categorizes it into Builder assets, prefabs, and inventory.",
    steamworkTitle: "Steamwork",
    steamworkReady: "Ready",
    steamworkBody: "Manage Steamworks, SteamPipeGUI, ContentBuilder/content, and promo/update assets.",
    steamworkDashboard: "Steamworks",
    steamworkPublishRoot: "ContentBuilder",
    steamworkGameContent: "Content",
    steamworkPublishTool: "SteamPipeGUI",
    steamworkArtAssets: "Assets",
    steamworkGameContentLabel: "Content",
    steamworkGameContentTitle: "Import game content",
    steamworkGameContentReady: "Drop game build files into ContentBuilder/content.",
    steamworkPublishToolLabel: "SteamPipeGUI",
    steamworkPublishToolTitle: "Import SteamPipeGUI tools",
    steamworkPublishToolReady: "Drop SteamPipeGUI-related files here.",
    steamworkTipsLabel: "Publish Tips",
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
    steamworkTipConfig: "SteamPipeGUI fields: App ID 3983670, Depot ID 3983671, Build Description can use 1.5.31.",
    steamworkTipPaths: "Paths: Build Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder\\content, ContentBuilder Path = D:\\Steamwork\\Steamwork\\sdk\\tools\\ContentBuilder.",
    steamworkTipLogin: "Steam Login = pixel_roblez. Do not store the password in Console.",
    steamworkTipContent: "Put the build output into ContentBuilder/content.",
    steamworkTipPipe: "Open SteamPipe Build Uploader, fill the fields, then upload.",
    steamworkUploadNote: "PC + Mobile confirmation.",
    steamworkTipRenewDepot: "In Steamworks web, renew/update the depot and set the generated build live.",
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
    cardTitle: name => `${name}\nDouble-click to apply, right-click for delete`,
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
    previousTrack: "Previous track",
    playTrack: "Play",
    pauseTrack: "Pause",
    nextTrack: "Next track",
    playbackModeSequential: "Order",
    playbackModeRepeatAll: "Loop",
    playbackModeRepeatOne: "Single",
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
let githubDownloadsInfo = null;
let pendingSteamworkAssetSlot = "";
let steamworkThumbsEnabled = false;
let workspaceTodoGroups = loadWorkspaceTodos();
let randomRealmArtContext = loadRandomRealmArtContext();
let blenderPromptConfig = loadBlenderPromptConfig();
let randomRealmBlenderProjects = [];
let randomRealmBlenderObjects = [];
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

function moduleUrl(href) {
  const params = new URLSearchParams(window.location.search);
  if (consoleEdition === "lite") {
    params.set("edition", "lite");
  }
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
    localStorage.setItem(storageKeys.lastModule, id);
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

function activateModule(id, push = false, options = {}) {
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
}

function applyModuleHistory(id) {
  activateModule(id, false, { allowArchived: true, replaceUrl: true });
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

  for (const nav of navs) {
    nav.innerHTML = "";
    for (const id of order) {
      const item = byId.get(id);
      if (!item) continue;

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

function applyConsoleEdition(nextEdition, options = {}) {
  const previousEdition = consoleEdition;
  consoleEdition = normalizeEdition(nextEdition);
  document.documentElement.dataset.edition = consoleEdition;
  if (document.body) {
    document.body.dataset.consoleEdition = consoleEdition;
  }

  if (!isModuleAvailable(activeModuleId)) {
    activeModuleId = firstAvailableModule().id;
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
    els.languageToggle.textContent = language === "zh" ? "EN" : "中文";
  }
  applyTheme();
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
    renderWorkspaceTodos();
  }
  if (hasRandomRealmArtTools()) {
    renderRandomRealmUsedTextures();
    setRandomRealmArtStatus(randomRealmArtNotice);
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

function wallpaperDropBeforePath(clientX, clientY) {
  const cards = Array.from(els.wallpaperDock?.querySelectorAll(".wallpaper-card:not(.dragging):not(.wallpaper-placeholder)") || []);
  if (!cards.length) return "";

  const rows = [];
  for (const card of cards) {
    const rect = card.getBoundingClientRect();
    let row = rows.find(item => Math.abs(item.top - rect.top) < 12);
    if (!row) {
      row = { top: rect.top, bottom: rect.bottom, cards: [] };
      rows.push(row);
    }
    row.top = Math.min(row.top, rect.top);
    row.bottom = Math.max(row.bottom, rect.bottom);
    row.cards.push({ card, rect });
  }

  rows.sort((a, b) => a.top - b.top);
  const pathWithinRow = row => {
    row.cards.sort((a, b) => a.rect.left - b.rect.left);
    for (const { card, rect } of row.cards) {
      if (clientX < rect.left + rect.width / 2) {
        return card.dataset.wallpaperPath || "";
      }
    }
    return "";
  };

  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const nextRow = rows[rowIndex + 1];
    const rowMid = row.top + (row.bottom - row.top) / 2;
    if (clientY < rowMid || clientY <= row.bottom + 10) {
      return pathWithinRow(row);
    }
    if (nextRow && clientY < nextRow.top) {
      const gapMid = row.bottom + (nextRow.top - row.bottom) / 2;
      return clientY < gapMid ? "" : pathWithinRow(nextRow);
    }
  }
  return "";
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

function wallpaperBeforeCardFromPoint(clientX, clientY) {
  const beforePath = wallpaperDropBeforePath(clientX, clientY);
  if (!beforePath) return null;
  return Array.from(els.wallpaperDock?.querySelectorAll(".wallpaper-card:not(.dragging):not(.wallpaper-placeholder)") || [])
    .find(card => card.dataset.wallpaperPath === beforePath) || null;
}

function moveWallpaperPlaceholder(placeholder, clientX, clientY) {
  const before = wallpaperBeforeCardFromPoint(clientX, clientY);
  if (before === placeholder || before === placeholder.nextElementSibling) return;
  animateWallpaperReflow(() => {
    els.wallpaperDock.insertBefore(placeholder, before);
  });
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
  let dragging = false;

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
    moveCardToPoint(moveEvent.clientX, moveEvent.clientY);
    const draggedRect = card.getBoundingClientRect();
    moveWallpaperPlaceholder(placeholder, draggedRect.left + draggedRect.width / 2, draggedRect.top + draggedRect.height / 2);
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
    const raw = JSON.parse(localStorage.getItem(storageKeys.musicTierVisibility) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return { second: false, third: false };
    }
    const second = Boolean(raw.second);
    return {
      second,
      third: second && Boolean(raw.third)
    };
  } catch {
    return { second: false, third: false };
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
}

function musicStatePayload() {
  return {
    stateVersion: musicStateVersion,
    tiers: { ...musicTierAssignments },
    order: [...musicTierOrder],
    promotedLibraryTracks: { ...promotedLibraryTracks }
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

function applyMusicState(state) {
  if (!state || typeof state !== "object") return;
  const hasServerTiers = Object.prototype.hasOwnProperty.call(state, "tiers");
  const hasServerOrder = Object.prototype.hasOwnProperty.call(state, "order");
  const hasServerPromoted = Object.prototype.hasOwnProperty.call(state, "promotedLibraryTracks");
  const serverTiers = state.tiers && typeof state.tiers === "object" && !Array.isArray(state.tiers) ? state.tiers : {};
  const serverPromoted = state.promotedLibraryTracks && typeof state.promotedLibraryTracks === "object" && !Array.isArray(state.promotedLibraryTracks)
    ? state.promotedLibraryTracks
    : {};
  const serverOrder = sanitizeMusicTierOrder(state.order || []);
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
  if (hasServerOrder) {
    musicTierOrder = serverOrder;
  } else if (serverOrder.length) {
    musicTierOrder = sanitizeMusicTierOrder([...serverOrder, ...musicTierOrder]);
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
  const beforeItem = row.cards.find(item => probeX <= item.rect.left + item.rect.width * thresholdRatio);
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
  selectedTrackPath = path || "";
  if (selectedTrackPath) {
    localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
  } else {
    localStorage.removeItem(storageKeys.selectedTrack);
  }
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

function scheduleMusicLibraryPoll() {
  if (musicLibraryPollTimer) {
    window.clearTimeout(musicLibraryPollTimer);
    musicLibraryPollTimer = null;
  }
  if (!hasActiveMusicLibraryGrab()) return;
  musicLibraryPollTimer = window.setTimeout(() => {
    musicLibraryPollTimer = null;
    loadMusic();
  }, 4000);
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
  card.addEventListener("click", () => {
    if (Date.now() < suppressTrackClickUntil) return;
    playTrack(item);
  });
  card.addEventListener("dblclick", () => {
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

function renderMusic() {
  if (!hasMusic) return;
  syncMusicTierAssignments();
  const selected = selectedTrack();
  const playable = allMusicTracks();
  els.musicDock.innerHTML = "";
  els.musicCount.textContent = text("trackCount", tracks.length);

  if (!playable.length) {
    selectedTrackPath = "";
    localStorage.removeItem(storageKeys.selectedTrack);
    els.currentTrackName.textContent = text("musicNotSelected");
    els.currentTrackMeta.textContent = text("musicEmptyBody");
    els.trackCurrentTime.textContent = "0:00";
    els.trackDuration.textContent = "0:00";
    els.trackSeek.value = "0";
    els.playPauseTrack.textContent = "▶";
    els.playPauseTrack.setAttribute("aria-label", text("playTrack"));
    els.playPauseTrack.title = text("playTrack");
  }

  if (selected && !selectedTrackPath) {
    selectedTrackPath = selected.path;
  }

  if (selected) {
    els.currentTrackName.textContent = displayTrackName(selected.name);
    els.currentTrackMeta.textContent = musicNotice || trackMeta(selected);
  } else {
    els.currentTrackName.textContent = text("musicNotSelected");
    els.currentTrackMeta.textContent = text("musicEmptyBody");
  }

  els.playPauseTrack.textContent = els.audioPlayer.paused ? "▶" : "❚❚";
  const playLabel = els.audioPlayer.paused ? text("playTrack") : text("pauseTrack");
  els.playPauseTrack.setAttribute("aria-label", playLabel);
  els.playPauseTrack.title = playLabel;
  renderPlaybackMode();

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

function startRandomRealmLiveSelectionPolling() {
  if (!hasRandomRealmArtTools() || randomRealmLiveSelectionTimer) return;
  randomRealmLiveSelectionTimer = window.setInterval(() => {
    if (document.hidden || activeModuleId !== "blender") return;
    syncRandomRealmLiveSelection({ quiet: true });
  }, 1600);
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

function scheduleRandomRealmTextureApplyPoll(delay = 2600) {
  if (!hasRandomRealmArtTools() || !randomRealmPackedPackagePaths().length || randomRealmTextureApplyPollTimer) return;
  randomRealmTextureApplyPollTimer = window.setTimeout(() => {
    randomRealmTextureApplyPollTimer = null;
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
  setRandomRealmArtStatus(text("randomRealmBlenderLoading"));
  try {
    const url = `/api/randomrealm/blender/projects${query ? `?q=${encodeURIComponent(query)}` : ""}`;
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
  try {
    const payload = await postJson("/api/randomrealm/blender/objects", { project });
    randomRealmBlenderObjects = Array.isArray(payload.objects) ? payload.objects : [];
    renderRandomRealmBlenderObjects();
    const synced = await syncRandomRealmLiveSelection({ quiet: true });
    if (!synced) {
      setRandomRealmArtStatus(text("randomRealmBlenderObjectLoaded", randomRealmBlenderObjects.length));
    }
  } catch (error) {
    randomRealmBlenderObjects = [];
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

async function postJson(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
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
      selectedTrackPath = result.files[0].path;
      localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
    }
    musicNotice = text("musicAdded", result.files.length);
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
      selectedTrackPath = result.files[0].path;
      localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
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
      selectedTrackPath = result.file.path;
      localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
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
        selectedTrackPath = nextTrack.path;
        localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);
      } else {
        selectedTrackPath = "";
        localStorage.removeItem(storageKeys.selectedTrack);
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
  selectedTrackPath = item.path;
  localStorage.setItem(storageKeys.selectedTrack, selectedTrackPath);

  const nextUrl = new URL(item.url, window.location.href).href;
  if (els.audioPlayer.src !== nextUrl) {
    els.audioPlayer.src = item.url;
    els.audioPlayer.load();
  }

  try {
    await els.audioPlayer.play();
    musicNotice = "";
    renderMusic();
  } catch (error) {
    musicNotice = text("musicPlayFailed", error.message);
    renderMusic();
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

function handleTrackEnded() {
  const item = selectedTrack();
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
    const response = await fetch("/api/music", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    tracks = Array.isArray(payload.tracks) ? payload.tracks : [];
    musicLibraries = Array.isArray(payload.libraries) ? payload.libraries : musicLibraries;
    musicCookieState = payload.cookies || { available: false };
    applyMusicState(payload.state);
    libraryTracks = flattenLibraryTracks(musicLibraries);
    if (selectedTrackPath && !tracks.some(item => item.path === selectedTrackPath)) {
      const stillExists = libraryTracks.some(item => item.path === selectedTrackPath);
      if (!stillExists) {
        selectedTrackPath = "";
        localStorage.removeItem(storageKeys.selectedTrack);
      }
    }
    renderMusic();
    renderMusicLibraries();
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

function steamworkAssetMeta(file) {
  if (!file) return text("steamworkAssetNoFile");
  const pieces = [];
  const dimensions = steamworkAssetDimensions(file);
  if (dimensions) pieces.push(dimensions);
  if (Number.isFinite(Number(file.size))) pieces.push(formatBytes(Number(file.size)));
  return pieces.join(" · ");
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

function renderSteamworkAssetsLegacyTableUnused(state) {
  if (!hasSteamwork || !els.steamworkAssetTableBody) return;
  const summary = state?.summary || {};
  const items = Array.isArray(state?.items) ? state.items : [];

  renderSteamworkAssetSummaryPills(summary, items.length);

  els.steamworkAssetTableBody.innerHTML = "";
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = text("steamworkAssetNoFile");
    row.appendChild(cell);
    els.steamworkAssetTableBody.appendChild(row);
    return;
  }

  for (const item of items) {
    const row = document.createElement("tr");
    row.className = `steamwork-asset-row status-${item.status || "missing"}`;
    const primaryFile = Array.isArray(item.files) ? item.files[0] : null;

    const assetCell = document.createElement("td");
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
    assetCell.appendChild(asset);
    row.appendChild(assetCell);

    const specCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `steamwork-status-badge ${item.status || "missing"}`;
    status.textContent = steamworkAssetStatusLabel(item.status);
    const spec = document.createElement("div");
    spec.className = "steamwork-spec-text";
    spec.textContent = steamworkAssetSpecText(item.spec);
    specCell.append(status, spec);
    if (item.issue) {
      const issue = document.createElement("div");
      issue.className = "steamwork-current-meta";
      issue.textContent = steamworkAssetIssueText(item.issue);
      specCell.appendChild(issue);
    }
    row.appendChild(specCell);

    const currentCell = document.createElement("td");
    if (Array.isArray(item.files) && item.files.length) {
      const fileList = document.createElement("div");
      fileList.className = "steamwork-current-list";
      item.files.slice(0, 5).forEach((file, index) => {
        fileList.appendChild(renderSteamworkAssetFileV2(file, { compact: index > 0 }));
      });
      if (item.files.length > 5) {
        const more = document.createElement("div");
        more.className = "steamwork-current-meta";
        more.textContent = `+${item.files.length - 5}`;
        fileList.appendChild(more);
      }
      if (primaryFile?.path) {
        const openButton = document.createElement("button");
        openButton.className = "mini-button steamwork-open-asset";
        openButton.type = "button";
        openButton.dataset.path = primaryFile.path;
        openButton.textContent = text("steamworkAssetOpen");
        fileList.appendChild(openButton);
      }
      currentCell.appendChild(fileList);
    } else {
      currentCell.textContent = text("steamworkAssetNoFile");
    }
    row.appendChild(currentCell);

    const targetCell = document.createElement("td");
    targetCell.textContent = steamworkAssetTargetText(item.target);
    row.appendChild(targetCell);

    els.steamworkAssetTableBody.appendChild(row);
  }
}

async function loadSteamworkAssetsLegacyTableUnused() {
  if (!hasSteamwork || !els.steamworkAssetTableBody) return;
  if (els.steamworkAssetSummary) {
    els.steamworkAssetSummary.textContent = text("steamworkAssetLoading");
  }
  try {
    const response = await fetch("/api/steamwork/assets", { cache: "no-store" });
    const state = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(state.error || `HTTP ${response.status}`);
    renderSteamworkAssetsLegacyTableUnused(state);
    setSteamworkStatus(text("steamworkAssetSource", state.root || "D:\\ArtAsset"));
  } catch (error) {
    const message = text("steamworkAssetLoadFailed", error.message);
    setSteamworkStatus(message);
    if (els.steamworkAssetSummary) {
      els.steamworkAssetSummary.textContent = message;
    }
  }
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
  els.localTime.textContent = formatClock(new Date());
}

if (els.languageToggle) els.languageToggle.addEventListener("click", () => {
  language = language === "zh" ? "en" : "zh";
  localStorage.setItem(storageKeys.language, language);
  applyLanguage();
});
if (els.themeToggle) els.themeToggle.addEventListener("click", () => {
  setTheme(nextTheme(theme));
});
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
  els.openSteamworkDashboard.addEventListener("click", () => openRandomRealmResource("steamworks", "steamworkDashboard"));
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
if (hasMusic) window.addEventListener("beforeunload", flushMusicStateBeforeUnload);
if (hasMusic) document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushMusicStateBeforeUnload();
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
});
if (hasMusic) els.audioPlayer.addEventListener("pause", () => {
  renderMusic();
  renderMusicLibraries();
});
if (hasMusic) els.audioPlayer.addEventListener("ended", handleTrackEnded);
if (hasMusic) els.audioPlayer.addEventListener("error", () => {
  musicNotice = text("musicPlayFailed", "unsupported or unavailable audio");
  renderMusic();
});
if (els.openSteamworks) {
  els.openSteamworks.addEventListener("click", () => openRandomRealmResource("steamworks", "randomRealmSteamworks"));
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
loadConsoleConfig();
restoreInitialModuleUrl();
if (hasWallpaper) loadWallpapers();
if (hasMusic) loadMusic();
if (hasWorkspace) loadGithubDownloadsInfo();
if (hasSteamwork) loadSteamworkAssets();
if (hasMaterialWorkspace && downloadIntakeEnabled) {
  loadMaterialCandidates();
} else if (hasMaterialWorkspace) {
  renderDownloadIntake();
}
renderRandomRealmArtContext();
renderBlenderPromptBuilder();
loadUnityBridgeStatus();
if (hasRandomRealmArtTools()) {
  loadRandomRealmBlenderProjects();
  startRandomRealmLiveSelectionPolling();
}
tick();
setInterval(tick, 1000);
