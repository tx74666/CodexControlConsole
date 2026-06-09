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
const musicReorderCommitRatio = 2 / 3;
const musicReorderReturnRatio = 1 - musicReorderCommitRatio;
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
    steamworkBody: "\u7ba1\u7406 Steamworks\u3001\u53d1\u5e03\u5de5\u5177\u3001GameContent \u548c\u5ba3\u4f20\u66f4\u65b0\u7d20\u6750\u3002",
    steamworkDashboard: "Steamworks \u540e\u53f0",
    steamworkPublishRoot: "Publish \u6839\u76ee\u5f55",
    steamworkGameContent: "GameContent",
    steamworkPublishTool: "Publish Tool",
    steamworkGameContentLabel: "GameContent",
    steamworkGameContentTitle: "\u5bfc\u5165\u6e38\u620f\u5185\u5bb9",
    steamworkGameContentReady: "\u628a\u6784\u5efa\u6587\u4ef6\u62d6\u5230\u8fd9\u91cc\u3002",
    steamworkPublishToolLabel: "Publish Tool",
    steamworkPublishToolTitle: "\u5bfc\u5165\u53d1\u5e03\u5de5\u5177",
    steamworkPublishToolReady: "\u628a\u53d1\u5e03\u5de5\u5177\u6587\u4ef6\u62d6\u5230\u8fd9\u91cc\u3002",
    steamworkImportDragging: "\u677e\u624b\u540e\u5bfc\u5165\u3002",
    steamworkImporting: (count, target) => `\u6b63\u5728\u5bfc\u5165 ${count} \u4e2a\u6587\u4ef6\u5230 ${target}\u3002`,
    steamworkImported: (count, target) => `\u5df2\u5bfc\u5165 ${count} \u4e2a\u6587\u4ef6\u5230 ${target}\u3002`,
    steamworkImportFailed: message => `Steamwork \u5bfc\u5165\u5931\u8d25\uff1a${message}`,
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
    githubDownloadsTitle: "GitHub 下载",
    githubDownloadsStatus: "待连接",
    githubDownloadsReady: "已定位",
    githubDownloadsMissing: "未连接",
    githubDownloadsResolving: "正在定位 GitHub Releases...",
    githubDownloadsBody: "打开 World Console 的 GitHub Releases 下载页。",
    githubDownloadsLink: "Release 页面",
    openGithubDownloads: "打开下载页",
    githubDownloadsFound: url => `下载页：${url}`,
    githubDownloadsNotConfigured: "还没有连接 GitHub 仓库。给 WorldConsole 添加 origin 以后，这里会自动定位到 Releases。",
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
    steamworkBody: "Manage Steamworks, publish tools, GameContent, and promo/update assets.",
    steamworkDashboard: "Steamworks",
    steamworkPublishRoot: "Publish Root",
    steamworkGameContent: "GameContent",
    steamworkPublishTool: "Publish Tool",
    steamworkGameContentLabel: "GameContent",
    steamworkGameContentTitle: "Import game content",
    steamworkGameContentReady: "Drop build files here.",
    steamworkPublishToolLabel: "Publish Tool",
    steamworkPublishToolTitle: "Import publish tools",
    steamworkPublishToolReady: "Drop publish tool files here.",
    steamworkImportDragging: "Release to import.",
    steamworkImporting: (count, target) => `Importing ${count} file${count === 1 ? "" : "s"} to ${target}.`,
    steamworkImported: (count, target) => `Imported ${count} file${count === 1 ? "" : "s"} to ${target}.`,
    steamworkImportFailed: message => `Steamwork import failed: ${message}`,
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
    githubDownloadsTitle: "GitHub Downloads",
    githubDownloadsStatus: "Not linked",
    githubDownloadsReady: "Ready",
    githubDownloadsMissing: "Not linked",
    githubDownloadsResolving: "Finding GitHub Releases...",
    githubDownloadsBody: "Open the World Console GitHub Releases download page.",
    githubDownloadsLink: "Release page",
    openGithubDownloads: "Open downloads",
    githubDownloadsFound: url => `Downloads: ${url}`,
    githubDownloadsNotConfigured: "No GitHub repository is linked yet. Add an origin remote to WorldConsole and this shortcut will target Releases automatically.",
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
  steamworkGameContentDropzone: document.getElementById("steamworkGameContentDropzone"),
  steamworkPublishToolDropzone: document.getElementById("steamworkPublishToolDropzone"),
  steamworkGameContentStatus: document.getElementById("steamworkGameContentStatus"),
  steamworkPublishToolStatus: document.getElementById("steamworkPublishToolStatus"),
  steamworkGameContentFileInput: document.getElementById("steamworkGameContentFileInput"),
  steamworkPublishToolFileInput: document.getElementById("steamworkPublishToolFileInput"),
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
let suppressTrackClickUntil = 0;
let lastTrackPointerStart = 0;
let lastPersistedModuleId = "";
let suppressModuleClickUntil = 0;
let lastModulePointerStart = 0;
let lastArchivePointerStart = 0;
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
const shouldRestoreLastModuleOnLoad = currentPageName() === "index.html" && lastModuleId();
let activeModuleId = initialModuleId();
const hasWallpaper = Boolean(els.wallpaperDock);
const hasMusic = Boolean(els.musicDock);
const hasWorkspace = Boolean(els.workspaceTodoList || els.materialCandidates);
const hasMaterialWorkspace = Boolean(els.materialCandidates);
const hasSteamwork = Boolean(els.steamworkStatusText);
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

  document.title = `Codex Control Console - ${text(next.titleKey)}`;

  if (push && currentPageName() !== next.href) {
    history.pushState({ moduleId: next.id }, "", moduleUrl(next.href));
  }

  renderModuleNavs();
}

function openArchivedModule(id) {
  if (!allArchivedModuleIds().includes(id)) return;
  setArchiveExpanded(false);
  activateModule(id, true, { allowArchived: true });
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

function archiveModule(id) {
  if (deletedModuleIds().includes(id)) return;
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
}

function restoreModule(id) {
  const archived = archivedModuleIds().filter(item => item !== id);
  const deepArchived = deepArchivedModuleIds().filter(item => item !== id);
  const visible = visibleModuleOrder().filter(item => item !== id);
  const remainingArchived = moduleOrder().filter(item => archived.includes(item) || deepArchived.includes(item));
  saveArchivedModuleIds(archived);
  saveDeepArchivedModuleIds(deepArchived);
  saveModuleOrder([...visible, id, ...remainingArchived]);
  setArchiveExpanded(false);
  activateModule(id, true);
}

function deepArchiveModule(id) {
  if (deletedModuleIds().includes(id)) return;
  const archived = archivedModuleIds().filter(item => item !== id);
  const deepArchived = deepArchivedModuleIds();
  saveArchivedModuleIds(archived);
  if (!deepArchived.includes(id)) {
    saveDeepArchivedModuleIds([...deepArchived, id]);
  }
  archiveView = "main";
  renderModuleNavs();
  renderModuleArchive();
}

function permanentlyDeleteModule(id) {
  if (!isModuleId(id)) return false;
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
  return true;
}

function restoreAllArchivedModules() {
  const archived = archivedModuleIds();
  if (!archived.length) {
    setArchiveExpanded(false);
    return;
  }

  const deepArchived = deepArchivedModuleIds();
  const visible = visibleModuleOrder().filter(id => !archived.includes(id));
  saveArchivedModuleIds([]);
  saveModuleOrder([...visible, ...archived, ...deepArchived]);
  setArchiveExpanded(false);
  activateModule(activeModuleId, false);
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
        deepArchiveModule(id);
        return true;
      }
      if (sourceDepth === "deep" && overArchiveDrop) {
        return permanentlyDeleteModule(id);
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

  link.setPointerCapture(event.pointerId);

  const finish = () => {
    if (finished) return;
    finished = true;
    link.removeEventListener("pointermove", move);
    link.removeEventListener("pointerup", up);
    link.removeEventListener("pointercancel", up);
    if (!dragging) return;

    const moduleId = draggedModuleId;
    const shouldArchive = dragSession.isOverArchive();
    clearArchiveDragState();
    draggedModuleId = "";
    suppressModuleClickUntil = Date.now() + 350;
    dragSession.finish({ animate: !shouldArchive }).then(() => {
      if (shouldArchive) {
        archiveModule(moduleId);
      } else {
        saveVisibleModuleOrder(moduleIdsFromNav(nav));
        renderModuleNavs();
        renderModuleArchive();
      }
    });
  };

  const move = moveEvent => {
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

  const finish = () => {
    if (finished) return;
    finished = true;
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    if (!dragging) return;

    const moduleId = draggedModuleId;
    const shouldArchive = dragSession.isOverArchive();
    clearArchiveDragState();
    draggedModuleId = "";
    suppressModuleClickUntil = Date.now() + 350;
    dragSession.finish({ animate: !shouldArchive }).then(() => {
      if (shouldArchive) {
        archiveModule(moduleId);
      } else {
        saveVisibleModuleOrder(moduleIdsFromNav(nav));
        renderModuleNavs();
        renderModuleArchive();
      }
    });
  };

  const move = moveEvent => {
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

  const up = () => finish();

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
        activateModule(item.id, true);
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

function selectedWallpaper() {
  return wallpapers.find(item => item.path === selectedWallpaperPath) || orderedWallpapers()[0] || null;
}

function setSelectedWallpaper(path) {
  pendingDeletePath = "";
  selectedWallpaperPath = path || "";
  if (selectedWallpaperPath) {
    localStorage.setItem(storageKeys.selectedWallpaper, selectedWallpaperPath);
  } else {
    localStorage.removeItem(storageKeys.selectedWallpaper);
  }
  renderWallpapers();
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
  const cards = Array.from(els.wallpaperDock?.querySelectorAll(".wallpaper-card:not(.dragging)") || []);
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

function reorderWallpaper(path, beforePath = "") {
  if (!path || path === beforePath) return;
  const currentOrder = orderedWallpapers().map(item => item.path).filter(itemPath => itemPath !== path);
  const insertIndex = beforePath ? currentOrder.indexOf(beforePath) : -1;
  if (insertIndex >= 0) {
    currentOrder.splice(insertIndex, 0, path);
  } else {
    currentOrder.push(path);
  }
  wallpaperOrder = currentOrder;
  persistWallpaperOrderNow();
  renderWallpapers();
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
    card.draggable = true;
    card.addEventListener("click", () => {
      if (Date.now() < suppressWallpaperClickUntil) return;
      setSelectedWallpaper(item.path);
    });
    card.addEventListener("dblclick", () => applyWallpaper(item));
    card.addEventListener("dragstart", event => {
      if (event.target.closest(".delete-wallpaper-button, .delete-popover")) {
        event.preventDefault();
        return;
      }
      draggedWallpaperPath = item.path;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-control-wallpaper", item.path);
      event.dataTransfer.setData("text/plain", item.name);
      window.requestAnimationFrame(() => card.classList.add("dragging"));
    });
    card.addEventListener("dragend", () => {
      draggedWallpaperPath = "";
      suppressWallpaperClickUntil = Date.now() + 180;
      clearWallpaperDropMarkers();
      card.classList.remove("dragging");
    });
    card.addEventListener("dragover", event => {
      if (!draggedWallpaperPath) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      showWallpaperDropMarker(wallpaperDropBeforePath(event.clientX, event.clientY));
    });
    card.addEventListener("drop", event => {
      const path = event.dataTransfer.getData("application/x-control-wallpaper") || draggedWallpaperPath;
      if (!path) return;
      event.preventDefault();
      event.stopPropagation();
      const beforePath = wallpaperDropBeforePath(event.clientX, event.clientY);
      clearWallpaperDropMarkers();
      reorderWallpaper(path, beforePath);
    });
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
}

function musicDropBeforePath(section, event) {
  return musicDropBeforePathFromPoint(section, event.clientX, event.clientY);
}

function musicDropBeforePathFromPoint(section, clientX, clientY, directionX = 0, draggedRect = null, directionY = 0) {
  const cards = Array.from(section.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"));
  const rowNodes = Array.from(section.querySelectorAll(".track-card:not(.dragging)"));
  if (!cards.length) return "";

  const rows = [];
  for (const card of rowNodes) {
    const rect = card.getBoundingClientRect();
    let row = rows.find(item => Math.abs(item.top - rect.top) < 12);
    if (!row) {
      row = { top: rect.top, bottom: rect.bottom, cards: [] };
      rows.push(row);
    }
    row.top = Math.min(row.top, rect.top);
    row.bottom = Math.max(row.bottom, rect.bottom);
    if (!card.classList.contains("music-track-placeholder")) {
      row.cards.push({ card, rect });
    }
  }

  rows.sort((a, b) => a.top - b.top);
  const rowFromVerticalRatio = () => {
    if (!draggedRect) return null;
    const matchedRows = [];
    for (const row of rows) {
      const rowHeight = Math.max(1, row.bottom - row.top);
      const overlapsRow = draggedRect.bottom > row.top && draggedRect.top < row.bottom;
      if (!overlapsRow) continue;
      if (directionY > 0 && draggedRect.bottom >= row.top + rowHeight * musicReorderCommitRatio) {
        matchedRows.push(row);
      } else if (directionY < 0 && draggedRect.top <= row.bottom - rowHeight * musicReorderCommitRatio) {
        matchedRows.push(row);
      }
    }
    if (matchedRows.length) {
      return directionY < 0 ? matchedRows[0] : matchedRows[matchedRows.length - 1];
    }
    if (directionY) return null;

    let best = null;
    for (const row of rows) {
      const rowHeight = Math.max(1, row.bottom - row.top);
      const overlap = Math.max(0, Math.min(draggedRect.bottom, row.bottom) - Math.max(draggedRect.top, row.top));
      const score = overlap / rowHeight;
      if (score >= 0.5 && (!best || score > best.score)) {
        best = { row, score };
      }
    }
    return best?.row || null;
  };
  const placeWithinRow = (row, useX = true) => {
    row.cards.sort((a, b) => a.rect.left - b.rect.left);
    if (!useX) return row.cards[0]?.card?.dataset.trackPath || "";
    for (let index = 0; index < row.cards.length; index += 1) {
      const { card, rect } = row.cards[index];
      const thresholdRatio = directionX < 0
        ? musicReorderReturnRatio
        : directionX > 0
          ? musicReorderCommitRatio
          : 1 / 2;
      const threshold = rect.left + rect.width * thresholdRatio;
      const thresholdPadding = directionX ? 0 : 4;
      if (clientX <= threshold + thresholdPadding) {
        return card.dataset.trackPath || "";
      }
    }
    return "";
  };

  const ratioRow = rowFromVerticalRatio();
  if (ratioRow) {
    const beforePath = placeWithinRow(ratioRow);
    const rowIndex = rows.indexOf(ratioRow);
    const firstRowPath = ratioRow.cards[0]?.card?.dataset.trackPath || "";
    if (directionY > 0 && beforePath && beforePath === firstRowPath) {
      return ratioRow.cards[1]?.card?.dataset.trackPath || "";
    }
    if (directionY < 0 && !beforePath) {
      return rows[rowIndex + 1]?.cards?.[0]?.card?.dataset.trackPath || "";
    }
    return beforePath;
  }

  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const nextRow = rows[rowIndex + 1];
    const rowMid = row.top + (row.bottom - row.top) / 2;
    if (clientY < rowMid) {
      return placeWithinRow(row);
    }
    if (clientY <= row.bottom + 10) {
      const rowTarget = placeWithinRow(row);
      if (rowTarget || !nextRow) return rowTarget;
      return nextRow.cards?.[0]?.card?.dataset.trackPath || "";
    }
    if (nextRow && clientY < nextRow.top) {
      const gapMid = row.bottom + (nextRow.top - row.bottom) / 2;
      if (clientY < gapMid) {
        const rowTarget = placeWithinRow(row);
        return rowTarget || nextRow.cards?.[0]?.card?.dataset.trackPath || "";
      }
      return placeWithinRow(nextRow);
    }
  }
  return "";
}

function musicTierAtPoint(clientX, clientY, preferredSection = null) {
  const node = document.elementFromPoint(clientX, clientY);
  const direct = node?.closest?.(".music-tier-section") || null;
  if (direct && !preferredSection) return direct;
  if (direct && direct === preferredSection) return direct;

  const sections = Array.from(els.musicDock?.querySelectorAll(".music-tier-section") || []);
  const inHorizontalReach = section => {
    const rect = section.getBoundingClientRect();
    return clientX >= rect.left - 20 && clientX <= rect.right + 20;
  };

  if (direct && preferredSection) {
    const directRect = direct.getBoundingClientRect();
    const preferredRect = preferredSection.getBoundingClientRect();
    const guard = Math.min(34, directRect.height * 0.24);
    const enteringDown = preferredRect.top < directRect.top;
    const enteringUp = preferredRect.top > directRect.top;
    if (enteringDown && clientY < directRect.top + guard) return preferredSection;
    if (enteringUp && clientY > directRect.bottom - guard) return preferredSection;
    return direct;
  }

  if (preferredSection && inHorizontalReach(preferredSection)) {
    const rect = preferredSection.getBoundingClientRect();
    if (clientY >= rect.top - 30 && clientY <= rect.bottom + 30) return preferredSection;
  }

  const reachableSections = sections.filter(inHorizontalReach)
    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  for (let index = 0; index < reachableSections.length; index += 1) {
    const section = reachableSections[index];
    const rect = section.getBoundingClientRect();
    const prev = reachableSections[index - 1]?.getBoundingClientRect();
    const next = reachableSections[index + 1]?.getBoundingClientRect();
    const topBoundary = prev ? prev.bottom + (rect.top - prev.bottom) / 2 : rect.top - 36;
    const bottomBoundary = next ? rect.bottom + (next.top - rect.bottom) / 2 : rect.bottom + 36;
    if (clientY >= topBoundary && clientY <= bottomBoundary) return section;
  }

  return preferredSection || null;
}

function musicDropTargetAtPoint(clientX, clientY, preferredSection = null, directionX = 0, directionY = 0, draggedRect = null) {
  const section = musicTierAtPoint(clientX, clientY, preferredSection);
  if (!section) return { section: null, tierId: "", beforePath: "" };
  return {
    section,
    tierId: section.dataset.tier || "",
    beforePath: musicDropBeforePathFromPoint(section, clientX, clientY, directionX, draggedRect, directionY)
  };
}

function showMusicPointerDropTarget(target) {
  clearMusicTierDragState();
  if (!target?.section || !isValidMusicTier(target.tierId)) return;
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

function musicTrackCardsForAnimation() {
  if (!els.musicDock) return [];
  return Array.from(els.musicDock.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"));
}

function animateMusicTrackReflow(mutate) {
  const cards = musicTrackCardsForAnimation();
  const first = new Map(cards.map(card => [card.dataset.trackPath, card.getBoundingClientRect()]));
  for (const card of cards) {
    card.getAnimations().forEach(animation => animation.cancel());
  }

  mutate();

  for (const card of musicTrackCardsForAnimation()) {
    const before = first.get(card.dataset.trackPath);
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
        duration: 160,
        easing: "cubic-bezier(0.25, 0.1, 0.25, 1)"
      }
    );
  }
}

function musicGridForSection(section) {
  return section?.querySelector?.(".music-tier-track-grid") || null;
}

function musicBeforeCardFromPoint(grid, clientX, clientY, directionX = 0, draggedRect = null, directionY = 0) {
  const section = grid?.closest?.(".music-tier-section");
  const beforePath = section ? musicDropBeforePathFromPoint(section, clientX, clientY, directionX, draggedRect, directionY) : "";
  if (!beforePath) return null;
  return Array.from(grid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"))
    .find(card => card.dataset.trackPath === beforePath) || null;
}

function musicGridColumnCount(grid) {
  const columns = window.getComputedStyle(grid).gridTemplateColumns
    .split(" ")
    .filter(Boolean);
  return Math.max(1, columns.length || 1);
}

function musicRowsFromCards(cards) {
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
  for (const row of rows) {
    row.cards.sort((a, b) => a.rect.left - b.rect.left);
  }
  return rows;
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

function createMusicDragLayoutSnapshot(draggedPath) {
  const sections = new Map();
  for (const section of Array.from(els.musicDock?.querySelectorAll(".music-tier-section") || [])) {
    const grid = musicGridForSection(section);
    if (!grid) continue;
    const allCards = Array.from(grid.querySelectorAll(".track-card:not(.music-track-placeholder)"));
    const sourceCard = allCards.find(card => card.dataset.trackPath === draggedPath) || null;
    const sourceRect = sourceCard ? musicRectSnapshot(sourceCard.getBoundingClientRect()) : null;
    const cards = allCards
      .filter(card => card.dataset.trackPath && card.dataset.trackPath !== draggedPath)
      .map(card => ({
        path: card.dataset.trackPath || "",
        rect: musicRectSnapshot(card.getBoundingClientRect())
      }));
    const rows = [];
    for (const item of cards) {
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
    const sourceRowIndex = sourceRect
      ? rows.findIndex(row => {
        const overlap = Math.min(sourceRect.bottom, row.bottom) - Math.max(sourceRect.top, row.top);
        return overlap > Math.min(sourceRect.height, Math.max(1, row.bottom - row.top)) * 0.42 || Math.abs(sourceRect.top - row.top) < 12;
      })
      : -1;
    sections.set(section, {
      cards,
      rows,
      sourceRowIndex
    });
  }
  return { sections };
}

function musicDomCardByPath(grid, path) {
  if (!grid || !path) return null;
  return Array.from(grid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"))
    .find(card => card.dataset.trackPath === path) || null;
}

function musicBeforePathFromDragSnapshot(snapshot, section, clientX, clientY, directionX, directionY, draggedRect) {
  const layout = snapshot?.sections?.get(section);
  if (!layout) return { active: false, beforePath: "" };
  if (!layout.cards.length) return { active: true, beforePath: "" };

  const rowForPoint = () => {
    for (let index = 0; index < layout.rows.length; index += 1) {
      const row = layout.rows[index];
      const nextRow = layout.rows[index + 1];
      const rowMid = row.top + (row.bottom - row.top) / 2;
      if (clientY < rowMid || clientY <= row.bottom + 10) return row;
      if (nextRow && clientY < nextRow.top) {
        const gapMid = row.bottom + (nextRow.top - row.bottom) / 2;
        return clientY < gapMid ? row : nextRow;
      }
    }
    return layout.rows[layout.rows.length - 1] || null;
  };

  let targetRow = null;
  if (draggedRect && directionY) {
    for (const row of layout.rows) {
      const rowHeight = Math.max(1, row.bottom - row.top);
      const overlapsRow = draggedRect.bottom > row.top && draggedRect.top < row.bottom;
      if (!overlapsRow) continue;
      if (directionY > 0 && draggedRect.bottom >= row.top + rowHeight * musicReorderCommitRatio) {
        targetRow = row;
      } else if (directionY < 0 && draggedRect.top <= row.bottom - rowHeight * musicReorderCommitRatio) {
        targetRow = row;
        break;
      }
    }
  }
  targetRow = targetRow || rowForPoint();
  if (!targetRow) return { active: true, beforePath: "" };

  const rowIndex = layout.rows.indexOf(targetRow);
  const isCrossRow = rowIndex !== layout.sourceRowIndex;
  // Cross-row movement should not inherit horizontal hysteresis from the starting row.
  const useDirectionalX = !isCrossRow;
  const xProbe = useDirectionalX && draggedRect && directionX < 0
    ? draggedRect.left
    : useDirectionalX && draggedRect && directionX > 0
      ? draggedRect.right
      : draggedRect
        ? draggedRect.left + draggedRect.width / 2
        : clientX;
  let columnIndex = targetRow.cards.length;
  for (let index = 0; index < targetRow.cards.length; index += 1) {
    const { rect } = targetRow.cards[index];
    const thresholdRatio = !useDirectionalX
      ? 1 / 2
      : directionX < 0
      ? musicReorderReturnRatio
      : directionX > 0
        ? musicReorderCommitRatio
        : 1 / 2;
    if (xProbe <= rect.left + rect.width * thresholdRatio + (useDirectionalX && directionX ? 0 : 4)) {
      columnIndex = index;
      break;
    }
  }

  const nextRow = layout.rows[rowIndex + 1] || null;
  return {
    active: true,
    beforePath: targetRow.cards[columnIndex]?.path || nextRow?.cards?.[0]?.path || ""
  };
}

function musicBeforeCardFromVerticalSlot(grid, clientX, draggedRect, directionY) {
  if (!grid || !draggedRect || !directionY) return { active: false, before: null };
  const cards = Array.from(grid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"));
  if (!cards.length) return { active: false, before: null };

  const columns = musicGridColumnCount(grid);
  const rows = musicRowsFromCards(cards);
  let targetRow = null;
  for (const row of rows) {
    const rowHeight = Math.max(1, row.bottom - row.top);
    const overlapsRow = draggedRect.bottom > row.top && draggedRect.top < row.bottom;
    if (!overlapsRow) continue;
    if (directionY > 0 && draggedRect.bottom >= row.top + rowHeight * musicReorderCommitRatio) {
      targetRow = row;
    } else if (directionY < 0 && draggedRect.top <= row.bottom - rowHeight * musicReorderCommitRatio) {
      targetRow = row;
      break;
    }
  }
  if (!targetRow) return { active: false, before: null };

  const rowIndex = rows.indexOf(targetRow);
  let columnIndex = targetRow.cards.length;
  for (let index = 0; index < targetRow.cards.length; index += 1) {
    const { rect } = targetRow.cards[index];
    if (clientX <= rect.left + rect.width / 2) {
      columnIndex = index;
      break;
    }
  }
  if (targetRow.cards.length >= columns && columnIndex >= columns) {
    columnIndex = columns - 1;
  }

  const targetIndex = clamp(rowIndex * columns + columnIndex, 0, cards.length);
  return { active: true, before: cards[targetIndex] || null };
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

function nextMusicTrackCard(card) {
  let sibling = card?.nextElementSibling || null;
  while (sibling) {
    if (sibling.classList.contains("track-card") && !sibling.classList.contains("music-track-placeholder")) {
      return sibling;
    }
    sibling = sibling.nextElementSibling;
  }
  return null;
}

function previousMusicTrackCard(card) {
  let sibling = card?.previousElementSibling || null;
  while (sibling) {
    if (sibling.classList.contains("track-card") && !sibling.classList.contains("music-track-placeholder")) {
      return sibling;
    }
    sibling = sibling.previousElementSibling;
  }
  return null;
}

function musicCardsShareRow(first, second) {
  if (!first || !second) return false;
  const firstRect = first.getBoundingClientRect();
  const secondRect = second.getBoundingClientRect();
  return Math.abs(firstRect.top - secondRect.top) < 14;
}

function musicCardSharesPlaceholderRow(placeholder, card) {
  if (!placeholder || !card) return false;
  const placeholderRect = placeholder.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  return Math.abs(placeholderRect.top - cardRect.top) < 14;
}

function musicCardSharesDraggedRow(draggedRect, card) {
  if (!draggedRect || !card) return false;
  const cardRect = card.getBoundingClientRect();
  const draggedMidY = draggedRect.top + draggedRect.height / 2;
  return draggedMidY >= cardRect.top - 28 && draggedMidY <= cardRect.bottom + 28;
}

function shouldHoldMusicPlaceholder(placeholder, nextGrid, insertBefore, draggedRect) {
  if (!draggedRect || !placeholder.parentNode) return false;

  const currentGrid = placeholder.parentNode;
  const currentBefore = nextMusicCardAfterPlaceholder(placeholder);
  if (currentGrid === nextGrid) {
    if (insertBefore === currentBefore || (!insertBefore && !currentBefore)) return false;
    if (musicCardsShareRow(currentBefore, insertBefore)) return false;
    if (!insertBefore && musicCardSharesPlaceholderRow(placeholder, currentBefore)) return false;
    if (!currentBefore && musicCardSharesPlaceholderRow(placeholder, insertBefore)) return false;
    if (!insertBefore && musicCardSharesDraggedRow(draggedRect, currentBefore)) return false;
    if (!currentBefore && musicCardSharesDraggedRow(draggedRect, insertBefore)) return false;
  }

  const placeholderRect = placeholder.getBoundingClientRect();
  if (!placeholderRect.height) return false;
  const draggedMidY = draggedRect.top + draggedRect.height / 2;
  const placeholderMidY = placeholderRect.top + placeholderRect.height / 2;
  const deadZone = Math.min(32, Math.max(18, draggedRect.height * 0.26));
  return Math.abs(draggedMidY - placeholderMidY) < deadZone;
}

function musicBeforeCardFromDrag(grid, placeholder, draggedRect, directionX, fallbackCard) {
  if (!draggedRect || placeholder.parentNode !== grid) return fallbackCard;
  if (!directionX) return fallbackCard;

  const children = Array.from(grid.children);
  const placeholderIndex = children.indexOf(placeholder);
  const cards = Array.from(grid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"));
  const sameRow = (card, rect = card.getBoundingClientRect()) => {
    const overlap = Math.min(draggedRect.bottom, rect.bottom) - Math.max(draggedRect.top, rect.top);
    if (overlap >= Math.min(draggedRect.height, rect.height) * 0.34) return true;
    const draggedMidY = draggedRect.top + draggedRect.height / 2;
    return draggedMidY >= rect.top - 18 && draggedMidY <= rect.bottom + 18;
  };
  const currentBefore = nextMusicCardAfterPlaceholder(placeholder);
  let bestLeft = null;
  let bestRight = null;
  let sawSameRow = false;

  for (const card of cards) {
    const cardIndex = children.indexOf(card);
    const rect = card.getBoundingClientRect();
    if (cardIndex === -1 || cardIndex === placeholderIndex || !sameRow(card, rect)) continue;
    sawSameRow = true;

    if (cardIndex < placeholderIndex) {
      const threshold = rect.left + rect.width * musicReorderReturnRatio;
      const score = (threshold - draggedRect.left) / rect.width;
      if (score >= 0 && (!bestLeft || score > bestLeft.score)) {
        bestLeft = { before: card, score };
      }
      continue;
    }

    const threshold = rect.left + rect.width * musicReorderCommitRatio;
    const score = (draggedRect.right - threshold) / rect.width;
    if (score >= 0 && (!bestRight || score > bestRight.score)) {
      bestRight = { before: nextMusicTrackCard(card), score };
    }
  }

  if (!sawSameRow) return fallbackCard;
  if (bestLeft && bestRight) {
    const scoreGap = bestLeft.score - bestRight.score;
    const preferred = Math.abs(scoreGap) >= 0.08
      ? scoreGap > 0
        ? bestLeft
        : bestRight
      : directionX < 0
        ? bestLeft
        : directionX > 0
          ? bestRight
          : bestLeft.score >= bestRight.score
            ? bestLeft
            : bestRight;
    return preferred.before?.classList?.contains("track-card") ? preferred.before : null;
  }
  const best = bestLeft || bestRight;
  if (best) return best.before?.classList?.contains("track-card") ? best.before : null;
  return fallbackCard;
}

function moveMusicPlaceholder(placeholder, section, clientX, clientY, directionX = 0, directionY = 0, draggedRect = null, dragSnapshot = null) {
  const grid = musicGridForSection(section);
  if (!grid) return;
  const stableY = draggedRect ? draggedRect.top + draggedRect.height / 2 : clientY;
  const pointX = draggedRect && directionX < 0
    ? draggedRect.left
    : draggedRect && directionX > 0
      ? draggedRect.right
      : clientX;
  const snapshotTarget = musicBeforePathFromDragSnapshot(dragSnapshot, section, pointX, stableY, directionX, directionY, draggedRect);
  const verticalSlot = snapshotTarget.active ? { active: false, before: null } : musicBeforeCardFromVerticalSlot(grid, clientX, draggedRect, directionY);
  const pointBefore = snapshotTarget.active
    ? musicDomCardByPath(grid, snapshotTarget.beforePath)
    : verticalSlot.active
      ? verticalSlot.before
      : musicBeforeCardFromPoint(grid, pointX, stableY, directionX, draggedRect, directionY);
  const before = snapshotTarget.active
    ? pointBefore
    : verticalSlot.active
      ? verticalSlot.before
      : musicBeforeCardFromDrag(grid, placeholder, draggedRect, directionX, pointBefore);
  const empty = grid.querySelector(".music-tier-empty");
  const insertBefore = before || empty || null;
  if (placeholder.parentNode === grid && (insertBefore === placeholder || insertBefore === placeholder.nextElementSibling)) return;
  if (!snapshotTarget.active && !verticalSlot.active && shouldHoldMusicPlaceholder(placeholder, grid, insertBefore, draggedRect)) return;

  animateMusicTrackReflow(() => {
    placeholder.parentNode?.classList?.remove("drag-has-placeholder");
    grid.insertBefore(placeholder, insertBefore);
    grid.classList.add("drag-has-placeholder");
  });
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

function settleDraggedMusicTrack(card, placeholder, animate = true) {
  const startRect = card.getBoundingClientRect();
  const targetRect = placeholder.getBoundingClientRect();
  const grid = placeholder.parentNode;
  let settled = false;

  const cleanup = () => {
    if (settled) return;
    settled = true;
    grid.insertBefore(card, placeholder);
    placeholder.remove();
    grid.classList.remove("drag-has-placeholder");
    card.getAnimations().forEach(animation => animation.cancel());
    card.classList.remove("dragging", "music-track-floating");
    card.style.removeProperty("width");
    card.style.removeProperty("height");
    card.style.removeProperty("left");
    card.style.removeProperty("top");
  };

  if (!animate || Math.abs(startRect.left - targetRect.left) < 1 && Math.abs(startRect.top - targetRect.top) < 1) {
    cleanup();
    return Promise.resolve();
  }

  card.style.left = `${startRect.left}px`;
  card.style.top = `${startRect.top}px`;
  const animation = card.animate(
    [
      {
        left: `${startRect.left}px`,
        top: `${startRect.top}px`,
        transform: "scale(1.02)"
      },
      {
        left: `${targetRect.left}px`,
        top: `${targetRect.top}px`,
        transform: "scale(1)"
      }
    ],
    {
      duration: 260,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      fill: "forwards"
    }
  );

  return animation.finished.catch(() => {}).then(cleanup);
}

function createMusicTrackDragSession(card, item, startX, startY) {
  const sourceSection = card.closest(".music-tier-section");
  const sourceGrid = musicGridForSection(sourceSection);
  const rect = card.getBoundingClientRect();
  const placeholder = document.createElement("div");
  placeholder.className = "track-card music-track-placeholder";
  placeholder.style.minHeight = `${rect.height}px`;
  placeholder.setAttribute("aria-hidden", "true");
  let dragging = false;
  let lastTarget = { section: sourceSection, tierId: sourceSection?.dataset.tier || tierForTrack(item), beforePath: "" };
  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  const sourceBeforePath = card.nextElementSibling?.dataset?.trackPath || "";
  const trackDirectionX = createDragDirectionTracker(startX);
  const trackDirectionY = createDragDirectionTracker(startY);
  const dragSnapshot = createMusicDragLayoutSnapshot(item.path);

  const moveCardToPoint = (clientX, clientY) => {
    const clamped = clampDragPosition(clientX, clientY, offsetX, offsetY, rect.width, rect.height);
    card.style.left = `${clamped.left}px`;
    card.style.top = `${clamped.top}px`;
  };

  const finish = shouldCommit => {
    if (!dragging) return false;
    suppressTrackClickUntil = Date.now() + 240;
    draggedTrackPath = "";
    clearMusicTierDragState();
    document.body.classList.remove("music-track-dragging");

    if (!shouldCommit || !isValidMusicTier(lastTarget.tierId)) {
      const sourceBefore = sourceBeforePath
        ? Array.from(sourceGrid.querySelectorAll(".track-card:not(.dragging):not(.music-track-placeholder)"))
          .find(node => node.dataset.trackPath === sourceBeforePath)
        : null;
      animateMusicTrackReflow(() => {
        placeholder.parentNode?.classList?.remove("drag-has-placeholder");
        sourceGrid.insertBefore(placeholder, sourceBefore);
        sourceGrid.classList.add("drag-has-placeholder");
      });
      return settleDraggedMusicTrack(card, placeholder, true).then(() => false);
    }

    const targetSection = placeholder.closest(".music-tier-section");
    const tierId = targetSection?.dataset.tier || lastTarget.tierId;
    const beforePath = musicBeforePathFromPlaceholder(placeholder);
    moveTrackToTier(item.path, tierId, beforePath);
    return settleDraggedMusicTrack(card, placeholder, true).then(() => {
      renderMusic();
      return true;
    });
  };

  const move = moveEvent => {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 6) return false;
    if (!dragging) {
      dragging = true;
      draggedTrackPath = item.path;
      sourceGrid.insertBefore(placeholder, card);
      sourceGrid.classList.add("drag-has-placeholder");
      document.body.appendChild(card);
      card.classList.add("dragging", "music-track-floating");
      card.style.width = `${rect.width}px`;
      card.style.height = `${rect.height}px`;
      document.body.classList.add("music-track-dragging");
    }
    moveEvent.preventDefault();
    moveCardToPoint(moveEvent.clientX, moveEvent.clientY);
    const directionX = trackDirectionX(moveEvent.clientX);
    const directionY = trackDirectionY(moveEvent.clientY);
    const draggedRect = card.getBoundingClientRect();
    const stableX = draggedRect.left + draggedRect.width / 2;
    const stableY = draggedRect.top + draggedRect.height / 2;
    lastTarget = musicDropTargetAtPoint(stableX, stableY, lastTarget.section || sourceSection, directionX, directionY, draggedRect);
    if (lastTarget.section && isValidMusicTier(lastTarget.tierId)) {
      moveMusicPlaceholder(placeholder, lastTarget.section, moveEvent.clientX, stableY, directionX, directionY, draggedRect, dragSnapshot);
    }
    return true;
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

function moveTrackToTier(path, tierId, beforePath = "") {
  if (!localTrackExists(path)) return;
  assignTrackTier(path, tierId, false);
  reorderTrackWithinTier(path, tierId, beforePath);
  persistMusicStateNow();
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
    return normalizeWorkspaceTodoGroups(JSON.parse(localStorage.getItem(storageKeys.workspaceTodos) || "[]"));
  } catch {
    return cloneDefaultWorkspaceTodos();
  }
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
  userSeeking = true;
  activeSeekPointerId = event?.pointerId ?? null;
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
  pendingSeekRatio = trackSeekRatioFromPointer(event) ?? trackSeekRatio();
  if (userSeeking) {
    previewTrackSeek(pendingSeekRatio);
    return;
  }
  commitTrackSeek(pendingSeekRatio);
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
  updateTrackProgress();
}

function updateTrackProgress() {
  const duration = audioDuration();
  const current = Number.isFinite(els.audioPlayer.currentTime) ? els.audioPlayer.currentTime : 0;
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
  theme = nextTheme(theme);
  localStorage.setItem(storageKeys.theme, theme);
  applyTheme();
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
if (hasWallpaper) els.wallpaperDock.addEventListener("dragover", event => {
  if (!draggedWallpaperPath) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  showWallpaperDropMarker(wallpaperDropBeforePath(event.clientX, event.clientY));
});
if (hasWallpaper) els.wallpaperDock.addEventListener("dragleave", event => {
  if (!els.wallpaperDock.contains(event.relatedTarget)) {
    clearWallpaperDropMarkers();
  }
});
if (hasWallpaper) els.wallpaperDock.addEventListener("drop", event => {
  const path = event.dataTransfer.getData("application/x-control-wallpaper") || draggedWallpaperPath;
  if (!path) return;
  event.preventDefault();
  event.stopPropagation();
  const beforePath = wallpaperDropBeforePath(event.clientX, event.clientY);
  clearWallpaperDropMarkers();
  reorderWallpaper(path, beforePath);
});
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
if (hasSteamwork && els.steamworkGameContentFileInput) {
  els.steamworkGameContentFileInput.addEventListener("change", event => uploadSteamworkFiles("gameContent", event.target.files));
}
if (hasSteamwork && els.steamworkPublishToolFileInput) {
  els.steamworkPublishToolFileInput.addEventListener("change", event => uploadSteamworkFiles("publishTool", event.target.files));
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
if (hasMusic) els.trackVolume.addEventListener("input", () => {
  const nextVolume = Math.max(0, Math.min(1, Number(els.trackVolume.value) || 0));
  els.audioPlayer.volume = nextVolume;
  localStorage.setItem(storageKeys.volume, String(nextVolume));
});
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
