using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using Unity.RandomRealm.Gameplay.Builds.EditorTools;
using Object = UnityEngine.Object;

namespace Unity.RandomRealm.Gameplay.BuildsEditor
{
    // Preparation source only. There are no startup hooks or alternate Apply/
    // receipt implementations. Process calls the production bridge mailbox.
    public static class DevRoomConsoleSyncVerification
    {
        const string FixtureParent = "Assets/ConsoleContentSyncVerification";
        const string GlobalLibrary = "Assets/Resources/DevsRealm/DocumentLibrary.asset";
        const string GlobalLibraryGuid = "4d80e8531f4fc6d46b38bbafa382008e";
        static readonly string ProjectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

        [Serializable] public sealed class SceneSnapshot
        {
            public int handle;
            public string name;
            public string path;
            public bool loaded;
            public bool dirty;
            public string fileSha256;
        }
        [Serializable] public sealed class Binding
        {
            public string name;
            public string path;
            public string guid;
            public long localFileId;
            public string id;
            public DevRoomConsoleBridge.SourceFile expectedLibrary;
            public string originalContentRevision;
            public string originalMediaRevision;
            public string originalStructureRevision;
            public string originalDocumentRawRevision;
            public string originalParentSerializationRevision;
            public string originalMetadataRevision;
        }
        [Serializable] public sealed class Evidence
        {
            public string phase;
            public string at;
            public string requestId;
            public string receiptSha256;
            public string sourceAssetSha256;
            public string sourcePixelsSha256;
            public string importedPixelsSha256;
            public string contentRevision;
            public string mediaRevision;
            public bool originalScenesProtected;
            public bool canonicalLibraryProtected;
            public string detail;
            public RenderedFrame[] renderedFrames;
        }
        [Serializable] public sealed class RenderedFrame
        {
            public int sectionIndex;
            public string sectionTitle;
            public string bodySha256;
            public string imageCaption;
            public string imageAssetPath;
            public string imageAssetSha256;
            public string pngPath;
            public string pngSha256;
            public string framePixelsSha256;
            public int uploadedImageVisiblePixels;
            public bool imageElementActive;
            public bool captionElementActive;
        }
        sealed class AssetSnapshot
        {
            public string path;
            public string bytes;
            public string metadata;
            public string serialized;
            public bool dirty;
            public Object asset;
        }
        [Serializable] public sealed class Manifest
        {
            public int schemaVersion = 2;
            public string ownerToken;
            public string ownerId;
            public string workspace;
            public string fixtureRoot;
            public string workRoot;
            public string sourceBindingsPath;
            public string isolatedConsoleRoot;
            public string projectId;
            public string projectLibraryGuid;
            public string editorInstanceNonce;
            public string stage;
            public int initialUndoGroup;
            public string initialUndoName;
            public int initialActiveScene;
            public SceneSnapshot[] scenes;
            public int[] selectedInstanceIds;
            public int activeSelectionInstanceId;
            public string globalLibraryRevision;
            public string globalLibraryMetaRevision;
            public string beforeImagePath;
            public string beforeImageGuid;
            public string beforeImageSha256;
            public string uploadImagePath;
            public string uploadImageSha256;
            public string uploadImagePixelsSha256;
            public string expectedImportedImagePath;
            public bool importedImageWasAbsent;
            public string importedImageGuid;
            public string importedImageMetaRevision;
            public bool importedImageOwned;
            public Binding[] bindings;
            public string dirtyBinding;
            public string dirtyBeforeSerialized;
            public string dirtyDiskRevision;
            public string conflictDiskRevision;
            public string lastAppliedRequestId;
            public Evidence[] evidence = Array.Empty<Evidence>();
        }

        public static string Prepare(string ownerToken)
        {
            RequireIdle(); Need(!string.IsNullOrWhiteSpace(ownerToken), "An authorized owned-task token is required.");
            string ownerId = Guid.NewGuid().ToString("N");
            string root = FixtureParent + "/" + ownerId;
            string work = Path.Combine(ProjectRoot, ".codex", "console-content-sync-verification", ownerId);
            Need(!Directory.Exists(ProjectFile(root)) && !Directory.Exists(work), "Task fixture destination already exists.");
            RejectLinks(work); Directory.CreateDirectory(work); RejectLinks(work);
            var manifest = new Manifest { ownerToken = ownerToken, ownerId = ownerId, workspace = ProjectRoot,
                fixtureRoot = root, workRoot = work, sourceBindingsPath = Path.Combine(work, "source-bindings.json"),
                isolatedConsoleRoot = Path.Combine(work, "console-fixture"), stage = "preparing",
                initialUndoGroup = Undo.GetCurrentGroup(), initialUndoName = Undo.GetCurrentGroupName(),
                initialActiveScene = SceneManager.GetActiveScene().handle, scenes = CaptureScenes(),
                selectedInstanceIds = Selection.objects.Select(value => value.GetInstanceID()).ToArray(),
                activeSelectionInstanceId = Selection.activeObject != null ? Selection.activeObject.GetInstanceID() : 0,
                projectLibraryGuid = GlobalLibraryGuid, globalLibraryRevision = HashFile(ProjectFile(GlobalLibrary)),
                globalLibraryMetaRevision = HashFile(ProjectFile(GlobalLibrary) + ".meta") };
            Need(AssetDatabase.AssetPathToGUID(GlobalLibrary) == GlobalLibraryGuid, "Canonical project library identity changed.");
            manifest.projectId = Hash(Utf8.GetBytes("unity-dev-room-v1\n" + ProjectRoot.TrimEnd('\\', '/').Replace('/', '\\').ToLowerInvariant() + "\n" + GlobalLibraryGuid));
            Persist(manifest); // Durable owner record exists before any fixture asset is created.
            try
            {
                EnsureFolders(root);
                manifest.beforeImagePath = root + "/Before.png";
                manifest.uploadImagePath = root + "/Upload.png";
                WriteFixtureImage(manifest.beforeImagePath, ownerId, false);
                WriteFixtureImage(manifest.uploadImagePath, ownerId, true);
                manifest.beforeImageGuid = AssetDatabase.AssetPathToGUID(manifest.beforeImagePath);
                manifest.beforeImageSha256 = HashFile(ProjectFile(manifest.beforeImagePath));
                manifest.uploadImageSha256 = HashFile(ProjectFile(manifest.uploadImagePath));
                manifest.uploadImagePixelsSha256 = SourcePixelsHash(ProjectFile(manifest.uploadImagePath));
                manifest.expectedImportedImagePath = "Assets/Resources/UI/DevsRealm/ConsoleMedia/" + manifest.uploadImageSha256 + ".png";
                manifest.importedImageWasAbsent = !File.Exists(ProjectFile(manifest.expectedImportedImagePath)) &&
                    !File.Exists(ProjectFile(manifest.expectedImportedImagePath) + ".meta");
                Need(manifest.importedImageWasAbsent, "Unique task media already exists; prepare a new fixture identity.");
                Texture2D before = AssetDatabase.LoadAssetAtPath<Texture2D>(manifest.beforeImagePath);
                Need(before != null, "Fixture image did not import as Texture2D.");
                var standalone = MakeDocument("qa-standalone-" + ownerId, before);
                string standalonePath = root + "/Standalone.asset", libraryPath = root + "/Library.asset";
                AssetDatabase.CreateAsset(standalone, standalonePath);
                var library = ScriptableObject.CreateInstance<DevsRealmDocumentLibraryAsset>();
                library.name = "Console QA Library";
                library.Configure(new[] { new DevsRealmDocumentCategoryInfo(DevsRealmDocumentCategory.Project, 0, "Task fixture", "Isolated bridge QA") }, new[] { standalone });
                AssetDatabase.CreateAsset(library, libraryPath);
                var device = MakeDocument("qa-device-" + ownerId, before);
                var display = ScriptableObject.CreateInstance<InteractiveDisplayContent>();
                display.name = "Console QA Display"; display.ConfigureDocuments("Task fixture display", new[] { new InteractiveDisplayTab("Overview", device, 0) });
                string displayPath = root + "/Display.asset";
                AssetDatabase.CreateAsset(display, displayPath); AssetDatabase.AddObjectToAsset(device, display);
                // Save only these new task assets, with the same subasset bundle pattern as Device authoring.
                EditorUtility.SetDirty(standalone); AssetDatabase.SaveAssetIfDirty(standalone);
                EditorUtility.SetDirty(library); AssetDatabase.SaveAssetIfDirty(library);
                EditorUtility.SetDirty(device); EditorUtility.SetDirty(display); AssetDatabase.SaveAssetIfDirty(display);
                AssetDatabase.ImportAsset(displayPath, ImportAssetOptions.ForceSynchronousImport | ImportAssetOptions.ForceUpdate);
                device = AssetDatabase.LoadAllAssetsAtPath(displayPath).OfType<DevsRealmDocumentAsset>().Single();
                manifest.bindings = new[] { CaptureBinding("standalone", standalone, library, "devRoomLibrary"),
                    CaptureBinding("device", device, display, "displayContent") };
                WriteSourceBindings(manifest);
                Directory.CreateDirectory(manifest.isolatedConsoleRoot);
                Need(Undo.GetCurrentGroup() == manifest.initialUndoGroup && Undo.GetCurrentGroupName() == manifest.initialUndoName,
                    "Fixture preparation unexpectedly changed the user's Undo group.");
                VerifyProtected(manifest);
                DevRoomConsoleBridge.EnableForOwnedTask(ownerToken, 60);
                var session = ReadJson<DevRoomConsoleBridge.Session>(Path.Combine(MailboxRoot(), "session.json"));
                Need(session.enabled && session.ownerToken == ownerToken, "Owned bridge session did not enable.");
                manifest.editorInstanceNonce = session.editorInstanceNonce; manifest.stage = "prepared";
                AddEvidence(manifest, "prepared", null, "Two typed fixture bindings; ordinary Library+Document and Device main+subasset; no scene opened or written.");
                Persist(manifest); return Path.Combine(work, "manifest.json");
            }
            catch (Exception exception)
            { manifest.stage = "prepare-failed"; AddEvidence(manifest, "prepare-failed", null, exception.Message); Persist(manifest); DevRoomConsoleBridge.Disable(); throw; }
        }

        public static void Process(string manifestPath)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            DevRoomConsoleBridge.ProcessCurrentSessionRequests(); VerifyProtected(manifest);
            AddEvidence(manifest, "processed-real-mailbox", null, "Production bridge processor invoked; no fabricated receipt or separate apply path."); Persist(manifest);
        }

        public static void VerifyApplied(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Need(receipt.status == "applied", "Actual bridge receipt is not applied: " + receipt.status + " " + receipt.message);
            Binding binding = BindRequest(manifest, request); DevsRealmDocumentAsset document = Load(binding);
            DevRoomConsoleBridge.Content actual = ReadContent(document);
            Need(DevRoomConsoleBridge.ContentRevision(actual) == request.contentSha256 && receipt.appliedContentSha256 == request.contentSha256,
                "Actual asset content differs from the HTTP-confirmed request.");
            Need(receipt.appliedUnityRevision == HashFile(ProjectFile(binding.path)) &&
                receipt.appliedMetaRevision == HashFile(ProjectFile(binding.path) + ".meta"), "Receipt and actual saved asset bytes differ.");
            Need(receipt.appliedLibraryRevision == HashFile(ProjectFile(binding.expectedLibrary.path)) &&
                receipt.appliedLibraryMetaRevision == HashFile(ProjectFile(binding.expectedLibrary.path) + ".meta"), "Receipt parent bytes differ.");
            Need(DevRoomConsoleBridge.StructureRevision(document, binding.guid, binding.localFileId) == binding.originalStructureRevision &&
                Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(LoadParent(binding)))) == binding.originalParentSerializationRevision,
                "Fixture parent/section structure changed.");
            Need(HashFile(ProjectFile(binding.path) + ".meta") == binding.originalMetadataRevision, "Fixture ownership metadata changed.");
            for (int index = 0; index < request.target.sections.Length; index++)
            {
                var desired = request.target.sections[index]; var saved = actual.sections[index];
                Need(saved.title == desired.title && saved.body == desired.body && saved.imageCaption == desired.imageCaption,
                    "Exact requested section text/caption differs after saving.");
                var desiredImage = desired.image ?? new DevRoomConsoleBridge.ImageReference();
                Need((saved.image.sha256 ?? "") == (desiredImage.sha256 ?? "") && (saved.image.resourcePath ?? "") == (desiredImage.resourcePath ?? ""),
                    "Actual Texture2D source differs from the requested image.");
            }
            var selectedImage = actual.sections[0].image;
            Need(selectedImage.assetPath == manifest.expectedImportedImagePath && selectedImage.sha256 == manifest.uploadImageSha256,
                "First section did not use the real Console-uploaded fixture image.");
            Need(document.Sections[0].Image != null, "Saved reference is not a real Texture2D object.");
            manifest.importedImageGuid = selectedImage.guid; manifest.importedImageMetaRevision = selectedImage.metaRevision;
            manifest.importedImageOwned = manifest.importedImageWasAbsent && receipt.createdMediaPaths != null &&
                receipt.createdMediaPaths.Contains(manifest.expectedImportedImagePath);
            manifest.lastAppliedRequestId = requestId; manifest.stage = "applied-verified";
            VerifyProtected(manifest);
            var evidence = AddEvidence(manifest, "applied-verified", requestId, "Exact asset/meta/parent/content/image/caption pins read from real files; imported GPU pixels recorded separately from encoded source pixels.");
            evidence.receiptSha256 = Hash(receiptBytes); evidence.sourceAssetSha256 = selectedImage.sha256;
            evidence.sourcePixelsSha256 = SourcePixelsHash(ProjectFile(selectedImage.assetPath));
            evidence.importedPixelsSha256 = ImportedPixelsHash(document.Sections[0].Image);
            evidence.contentRevision = DevRoomConsoleBridge.ContentRevision(actual); evidence.mediaRevision = DevRoomConsoleBridge.MediaRevision(actual);
            Persist(manifest);
        }

        public static void VerifyRepeatUuid(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Need(receipt.status == "applied", "Repeat test needs an applied request."); Binding binding = BindRequest(manifest, request);
            string before = HashFile(ProjectFile(binding.path)); DateTime written = File.GetLastWriteTimeUtc(ProjectFile(binding.path));
            string receiptHash = Hash(receiptBytes);
            DevRoomConsoleBridge.ProcessCurrentSessionRequests();
            Need(HashFile(ProjectFile(binding.path)) == before && File.GetLastWriteTimeUtc(ProjectFile(binding.path)) == written &&
                HashFile(ReceiptFile(requestId)) == receiptHash, "An already-consumed UUID caused a second write or receipt change.");
            VerifyProtected(manifest); AddEvidence(manifest, "uuid-repeat-no-write", requestId, "Asset bytes, write time, and immutable receipt bytes all unchanged."); Persist(manifest);
        }

        public static void VerifyOwnUndoRedo(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Need(receipt.status == "applied" && receipt.attemptStarted && receipt.undoName == "Console document content" &&
                Undo.GetCurrentGroup() == receipt.undoGroup && Undo.GetCurrentGroupName() == receipt.undoName,
                "The current Undo group cannot be proved to be this bridge request; no Undo was performed.");
            Binding binding = BindRequest(manifest, request); var applied = ReadContent(Load(binding));
            string appliedMedia = DevRoomConsoleBridge.MediaRevision(applied), diskBefore = HashFile(ProjectFile(binding.path));
            string pixelBefore = ImportedPixelsHash(Load(binding).Sections[0].Image);
            Undo.PerformUndo();
            var original = ReadContent(Load(binding));
            Need(DevRoomConsoleBridge.ContentRevision(original) == binding.originalContentRevision &&
                DevRoomConsoleBridge.MediaRevision(original) == binding.originalMediaRevision,
                "Real Undo did not restore original text, caption, and image reference.");
            VerifyProtected(manifest);
            Undo.PerformRedo();
            var redone = ReadContent(Load(binding));
            Need(DevRoomConsoleBridge.ContentRevision(redone) == request.contentSha256 &&
                DevRoomConsoleBridge.MediaRevision(redone) == appliedMedia && ImportedPixelsHash(Load(binding).Sections[0].Image) == pixelBefore,
                "Real Redo did not restore confirmed text and imported image pixels.");
            Need(HashFile(ProjectFile(binding.path)) == diskBefore, "Undo/Redo unexpectedly wrote the task asset to disk.");
            // Return only task-owned fixture objects to a clean saved state.
            Object main = AssetDatabase.LoadMainAssetAtPath(binding.path); EditorUtility.SetDirty(main); AssetDatabase.SaveAssetIfDirty(main);
            VerifyProtected(manifest); AddEvidence(manifest, "own-undo-redo", requestId,
                "Only the receipt-proved top bridge group was undone/redone. Original scene identities/dirty flags/files and canonical library remained unchanged. No user Undo history was cleared."); Persist(manifest);
        }

        public static void ArmDirty(string manifestPath, string bindingName)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            Need(string.IsNullOrEmpty(manifest.dirtyBinding), "An owned dirty fixture is already armed.");
            Binding binding = NamedBinding(manifest, bindingName); var document = Load(binding); RequireClean(binding.path);
            manifest.dirtyBinding = bindingName; manifest.dirtyBeforeSerialized = EditorJsonUtility.ToJson(document);
            manifest.dirtyDiskRevision = HashFile(ProjectFile(binding.path)); Persist(manifest);
            var serialized = new SerializedObject(document); var body = serialized.FindProperty("m_Sections").GetArrayElementAtIndex(0).FindPropertyRelative("m_Body");
            body.stringValue += "\n[task QA unsaved edit]"; serialized.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(document);
            VerifyProtected(manifest); AddEvidence(manifest, "dirty-fixture-armed", null, "Only the selected task fixture has unsaved content; its on-disk bytes remain pinned."); Persist(manifest);
        }

        public static void RenderVerifiedDevice(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            Need(manifest.evidence.Any(item => item.phase == "own-undo-redo" && item.requestId == requestId),
                "Run the receipt-proved Undo/Redo acceptance before creating a visual preview.");
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Binding binding = BindRequest(manifest, request);
            Need(binding.name == "device" && receipt.status == "applied", "Visual acceptance needs the applied task-owned Device bundle.");
            var content = LoadParent(binding) as InteractiveDisplayContent; var document = Load(binding);
            Need(content != null && content.TabCount == 1 && content.GetTab(0).Document == document &&
                DevRoomConsoleBridge.ContentRevision(ReadContent(document)) == request.contentSha256,
                "The persisted Device binding/content differs from the verified mailbox result.");
            VerifyProtected(manifest); RequireClean(binding.path);
            string savedAssetHash = HashFile(ProjectFile(binding.path)), savedMetaHash = HashFile(ProjectFile(binding.path) + ".meta");
            int undoGroup = Undo.GetCurrentGroup(); string undoName = Undo.GetCurrentGroupName();
            int previewSceneCount = EditorSceneManager.previewSceneCount;
            int[] selection = Selection.objects.Select(value => value.GetInstanceID()).ToArray();
            int activeSelection = Selection.activeObject != null ? Selection.activeObject.GetInstanceID() : 0;
            AssetSnapshot[] dependencies = CaptureRenderAssets();
            Scene preview = default; GameObject root = null; GameObject cameraObject = null;
            var frames = new List<RenderedFrame>(); string failure = null;
            string output = Path.Combine(manifest.workRoot, "render-" + requestId + "-" + Guid.NewGuid().ToString("N"));
            RejectLinks(output); Directory.CreateDirectory(output);
            try
            {
                preview = EditorSceneManager.NewPreviewScene();
                // This is the game's public authoring preview API. It binds the
                // exact persisted content object and only borrows already-covered
                // fonts; it does not populate atlases or save generated assets.
                root = InteractiveDisplayBaker.CreateEditablePreview(preview, content, InteractiveDisplayReaderLayout.ImageRich);
                Need(root != null && root.scene == preview && !EditorUtility.IsPersistent(root), "Game preview did not create only an owned hierarchy.");
                root.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity); root.transform.localScale = Vector3.one;
                InteractiveDisplay display = root.GetComponent<InteractiveDisplay>();
                Need(display != null && display.Content == content && display.Content.GetTab(0).Document == document,
                    "Preview substituted a transient document for the actual saved fixture.");
                cameraObject = EditorUtility.CreateGameObjectWithHideFlags("Console sync task preview camera", HideFlags.HideAndDontSave, typeof(Camera));
                SceneManager.MoveGameObjectToScene(cameraObject, preview);
                Camera camera = cameraObject.GetComponent<Camera>(); camera.scene = preview;
                camera.overrideSceneCullingMask = EditorSceneManager.GetSceneCullingMask(preview);
                Need(camera.overrideSceneCullingMask != 0ul, "Owned preview has no isolated camera culling mask.");
                camera.aspect = 16f / 9f; camera.fieldOfView = 28f; camera.nearClipPlane = .05f; camera.farClipPlane = 30f;
                camera.transform.SetPositionAndRotation(new Vector3(0f, 1.85f, 5.5f), Quaternion.LookRotation(Vector3.back));
                camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(.03f, .045f, .065f);
                display.SetPointerFocus(true, camera); display.ShowOverview();
                Need(display.TryValidate(out string reason) && display.ReaderLayout == InteractiveDisplayReaderLayout.ImageRich &&
                    display.PageCount == document.Sections.Count, "Actual game display bindings failed validation: " + reason);
                TMP_Text body = FindNamed<TMP_Text>(root, "Body"); TMP_Text title = FindNamed<TMP_Text>(root, "SectionTitle");
                TMP_Text caption = FindNamed<TMP_Text>(root, "ImageCaption"); RawImage image = FindNamed<RawImage>(root, "DocumentImage");
                for (int index = 0; index < document.Sections.Count; index++)
                {
                    DevsRealmDocumentSectionData section = document.Sections[index];
                    Texture2D expectedImage = section.Image ?? (string.IsNullOrEmpty(section.ImageResourcePath) ? null : Resources.Load<Texture2D>(section.ImageResourcePath));
                    Need(display.PageIndex == index && body.text == section.Body && title.text == section.Title &&
                        caption.text == (section.ImageCaption ?? "") && image.texture == expectedImage,
                        "Actual display lost or reordered section text/image/caption at index " + index);
                    Need(image.gameObject.activeSelf == (expectedImage != null) &&
                        caption.gameObject.activeSelf == (expectedImage != null && !string.IsNullOrWhiteSpace(section.ImageCaption)),
                        "Image or caption retained residue from another section.");
                    Canvas.ForceUpdateCanvases(); LayoutRebuilder.ForceRebuildLayoutImmediate(display.ScrollView.content);
                    display.ScrollView.verticalNormalizedPosition = 1f;
                    foreach (TMP_Text label in root.GetComponentsInChildren<TMP_Text>(true)) if (label.gameObject.activeInHierarchy) label.ForceMeshUpdate();
                    Canvas.ForceUpdateCanvases();
                    string path = Path.Combine(output, "section-" + index.ToString("D3", CultureInfo.InvariantCulture) + ".png");
                    int visiblePixels; string pixels = CaptureDisplayFrame(camera, image, path, index == 0, out visiblePixels);
                    if (index == 0) Need(expectedImage != null && AssetDatabase.GetAssetPath(expectedImage) == manifest.expectedImportedImagePath && visiblePixels > 200,
                        "The real display screenshot did not visibly draw the task's uploaded blue/cyan image in its image element bounds.");
                    frames.Add(new RenderedFrame { sectionIndex = index, sectionTitle = title.text, bodySha256 = Hash(Utf8.GetBytes(body.text)),
                        imageCaption = caption.text, imageElementActive = image.gameObject.activeSelf, captionElementActive = caption.gameObject.activeSelf,
                        imageAssetPath = expectedImage != null ? AssetDatabase.GetAssetPath(expectedImage) : "",
                        imageAssetSha256 = expectedImage != null ? HashFile(ProjectFile(AssetDatabase.GetAssetPath(expectedImage))) : "",
                        pngPath = path, pngSha256 = HashFile(path), framePixelsSha256 = pixels, uploadedImageVisiblePixels = visiblePixels });
                    if (index + 1 < document.Sections.Count) display.ShowNextPage();
                }
            }
            catch (Exception exception) { failure = exception.Message; }
            finally
            {
                if (root != null) Object.DestroyImmediate(root);
                if (cameraObject != null) Object.DestroyImmediate(cameraObject);
                if (preview.IsValid()) { EditorSceneManager.ClosePreviewScene(preview); Need(!preview.IsValid() || !preview.isLoaded, "Owned preview scene could not close."); }
                Selection.objects = selection.Select(EditorUtility.InstanceIDToObject).Where(value => value != null).ToArray();
                Selection.activeObject = activeSelection == 0 ? null : EditorUtility.InstanceIDToObject(activeSelection);
            }
            // Verify original state after the owned preview has been removed.
            VerifyProtected(manifest); VerifyRenderAssets(dependencies);
            Need(EditorSceneManager.previewSceneCount == previewSceneCount, "Visual acceptance leaked or closed an unrelated preview scene.");
            Need(HashFile(ProjectFile(binding.path)) == savedAssetHash && HashFile(ProjectFile(binding.path) + ".meta") == savedMetaHash,
                "Visual preview changed the persisted fixture asset or metadata.");
            Need(Undo.GetCurrentGroup() == undoGroup && Undo.GetCurrentGroupName() == undoName,
                "Visual preview changed the current Undo group; no history is cleared or repaired.");
            Need(Selection.objects.Select(value => value.GetInstanceID()).SequenceEqual(selection) &&
                (Selection.activeObject != null ? Selection.activeObject.GetInstanceID() : 0) == activeSelection, "Selection was not restored.");
            var evidence = AddEvidence(manifest, failure == null ? "device-render-verified" : "device-render-failed", requestId,
                failure ?? "Actual persisted Device fixture rendered through the game's public ImageRich authoring preview and runtime InteractiveDisplay. Each real section's text/image/caption/order and screenshot were checked. No Play or original scene switch/write.");
            evidence.renderedFrames = frames.ToArray(); evidence.receiptSha256 = Hash(receiptBytes); Persist(manifest);
            Need(failure == null, "Owned device render acceptance failed: " + failure);
        }

        public static void VerifyDirtyBlocked(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            Need(!string.IsNullOrEmpty(manifest.dirtyBinding), "No owned dirty fixture is armed.");
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Binding binding = BindRequest(manifest, request);
            Need(binding.name == manifest.dirtyBinding && receipt.status == "pending" && EditorUtility.IsDirty(Load(binding)) &&
                HashFile(ProjectFile(binding.path)) == manifest.dirtyDiskRevision, "Dirty target was not blocked with its saved bytes intact.");
            VerifyProtected(manifest); AddEvidence(manifest, "dirty-document-blocked", requestId, receipt.message); Persist(manifest);
        }

        public static void CauseConflictFromDirty(string manifestPath, string requestId)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RequireSession(manifest);
            ReadOperation(manifest, requestId, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes);
            Binding binding = BindRequest(manifest, request);
            Need(binding.name == manifest.dirtyBinding && receipt.status == "pending", "Conflict phase requires the task's dirty-blocked request.");
            RestoreOwnedDirty(manifest);
            var document = Load(binding); var serialized = new SerializedObject(document);
            serialized.FindProperty("m_Sections").GetArrayElementAtIndex(0).FindPropertyRelative("m_Body").stringValue += "\n[task QA saved source conflict]";
            serialized.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(document);
            Object main = AssetDatabase.LoadMainAssetAtPath(binding.path); EditorUtility.SetDirty(main); AssetDatabase.SaveAssetIfDirty(main);
            manifest.conflictDiskRevision = HashFile(ProjectFile(binding.path)); Persist(manifest);
            // Main-thread sequence prevents a frame between source mutation and the common processor.
            DevRoomConsoleBridge.ProcessCurrentSessionRequests();
            ReadOperation(manifest, requestId, out request, out receipt, out receiptBytes);
            Need(receipt.status == "conflict" && HashFile(ProjectFile(binding.path)) == manifest.conflictDiskRevision,
                "Pinned source conflict was not refused without overwriting its content.");
            VerifyProtected(manifest); AddEvidence(manifest, "source-conflict-blocked", requestId, receipt.message); Persist(manifest);
        }

        public static void RestoreDirty(string manifestPath)
        { RequireIdle(); Manifest manifest = ReadManifest(manifestPath); RestoreOwnedDirty(manifest); VerifyProtected(manifest); Persist(manifest); }

        public static void Cleanup(string manifestPath)
        {
            RequireIdle(); Manifest manifest = ReadManifest(manifestPath);
            // Close the actual coordinator session before any task asset cleanup.
            DevRoomConsoleBridge.Disable();
            if (!string.IsNullOrEmpty(manifest.dirtyBinding)) RestoreOwnedDirty(manifest);
            VerifyProtected(manifest);
            string root = ProjectFile(manifest.fixtureRoot);
            if (Directory.Exists(root))
            {
                var allowed = new HashSet<string>(new[] { "Before.png", "Before.png.meta", "Upload.png", "Upload.png.meta",
                    "Standalone.asset", "Standalone.asset.meta", "Library.asset", "Library.asset.meta", "Display.asset", "Display.asset.meta" }, StringComparer.Ordinal);
                Need(Directory.GetFiles(root, "*", SearchOption.AllDirectories).All(file => allowed.Contains(Path.GetRelativePath(root, file))),
                    "Unknown files entered the task fixture; cleanup refused.");
                foreach (Binding binding in manifest.bindings ?? Array.Empty<Binding>())
                {
                    Need(AssetDatabase.AssetPathToGUID(binding.path) == binding.guid &&
                        HashFile(ProjectFile(binding.path) + ".meta") == binding.originalMetadataRevision, "Task fixture GUID/owner metadata changed; cleanup refused.");
                    RequireClean(binding.path);
                    foreach (Object value in AssetDatabase.LoadAllAssetsAtPath(binding.path)) if (value != null) Undo.ClearUndo(value);
                }
                Need(AssetDatabase.MoveAssetToTrash(manifest.fixtureRoot), "Task fixture could not be moved to Trash.");
            }
            if (manifest.importedImageOwned && File.Exists(ProjectFile(manifest.expectedImportedImagePath)))
            {
                Need(manifest.importedImageWasAbsent && AssetDatabase.AssetPathToGUID(manifest.expectedImportedImagePath) == manifest.importedImageGuid &&
                    HashFile(ProjectFile(manifest.expectedImportedImagePath)) == manifest.uploadImageSha256 &&
                    HashFile(ProjectFile(manifest.expectedImportedImagePath) + ".meta") == manifest.importedImageMetaRevision,
                    "Task-created imported image changed; preserve it for review.");
                RequireClean(manifest.expectedImportedImagePath);
                Need(AssetDatabase.MoveAssetToTrash(manifest.expectedImportedImagePath), "Task-created image could not be moved to Trash.");
            }
            Selection.objects = manifest.selectedInstanceIds.Select(EditorUtility.InstanceIDToObject).Where(value => value != null).ToArray();
            Selection.activeObject = manifest.activeSelectionInstanceId == 0 ? null : EditorUtility.InstanceIDToObject(manifest.activeSelectionInstanceId);
            VerifyProtected(manifest); manifest.stage = "cleaned";
            AddEvidence(manifest, "cleaned", null, "Actual session disabled; exact task fixtures moved to Trash; selection restored; durable evidence and mailbox retained."); Persist(manifest);
        }

        static DevsRealmDocumentAsset MakeDocument(string id, Texture2D image)
        {
            var document = ScriptableObject.CreateInstance<DevsRealmDocumentAsset>(); document.name = "Task QA document";
            document.Configure(id, DevsRealmDocumentCategory.Project, 0, "QA original title", "QA original summary", "2026-10-12",
                new[] { new DevsRealmDocumentSectionData("Overview", "Original fixture body", image, "", "Original fixture caption"),
                    new DevsRealmDocumentSectionData("Details", "Second section retains its position") });
            document.ConfigureSourceReference("Task-owned Console sync verification fixture", "2026-10-12"); return document;
        }
        static Binding CaptureBinding(string name, DevsRealmDocumentAsset document, Object parent, string kind)
        {
            Need(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(document, out string guid, out long localId), "Fixture document identity missing.");
            string path = AssetDatabase.GetAssetPath(document), parentPath = AssetDatabase.GetAssetPath(parent);
            var content = ReadContent(document);
            return new Binding { name = name, path = path, guid = guid, localFileId = localId, id = document.Id,
                expectedLibrary = new DevRoomConsoleBridge.SourceFile { kind = kind, path = parentPath, guid = AssetDatabase.AssetPathToGUID(parentPath),
                    revision = HashFile(ProjectFile(parentPath)), metaRevision = HashFile(ProjectFile(parentPath) + ".meta") },
                originalContentRevision = DevRoomConsoleBridge.ContentRevision(content), originalMediaRevision = DevRoomConsoleBridge.MediaRevision(content),
                originalStructureRevision = DevRoomConsoleBridge.StructureRevision(document, guid, localId),
                originalDocumentRawRevision = HashFile(ProjectFile(path)), originalMetadataRevision = HashFile(ProjectFile(path) + ".meta"),
                originalParentSerializationRevision = Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(parent))) };
        }
        static DevsRealmDocumentAsset Load(Binding binding)
        {
            var matches = AssetDatabase.LoadAllAssetsAtPath(binding.path).OfType<DevsRealmDocumentAsset>().Where(document => document.Id == binding.id &&
                AssetDatabase.TryGetGUIDAndLocalFileIdentifier(document, out string guid, out long localId) && guid == binding.guid && localId == binding.localFileId).ToArray();
            Need(matches.Length == 1, "Task fixture binding no longer resolves uniquely."); return matches[0];
        }
        static Object LoadParent(Binding binding) => AssetDatabase.LoadMainAssetAtPath(binding.expectedLibrary.path);
        static Binding NamedBinding(Manifest manifest, string name) { var values = manifest.bindings.Where(binding => binding.name == name).ToArray(); Need(values.Length == 1, "Unknown fixture binding name."); return values[0]; }
        static Binding BindRequest(Manifest manifest, DevRoomConsoleBridge.Request request)
        {
            var matches = manifest.bindings.Where(binding => binding.path == request.document.path && binding.guid == request.document.guid &&
                binding.localFileId == request.document.localFileId && binding.id == request.document.id &&
                binding.expectedLibrary.path == request.expectedLibrary.path && binding.expectedLibrary.guid == request.expectedLibrary.guid &&
                binding.expectedLibrary.kind == request.expectedLibrary.kind).ToArray();
            Need(matches.Length == 1, "Request does not address an exact task-owned fixture binding."); return matches[0];
        }
        static void ReadOperation(Manifest manifest, string id, out DevRoomConsoleBridge.Request request, out DevRoomConsoleBridge.Receipt receipt, out byte[] receiptBytes)
        {
            Need(Guid.TryParseExact(id, "D", out Guid value) && value.ToString("D") == id, "Request UUID is invalid.");
            byte[] requestBytes = File.ReadAllBytes(Path.Combine(MailboxRoot(), "requests", id + ".json"));
            receiptBytes = File.ReadAllBytes(ReceiptFile(id)); request = JsonUtility.FromJson<DevRoomConsoleBridge.Request>(Utf8.GetString(requestBytes));
            receipt = JsonUtility.FromJson<DevRoomConsoleBridge.Receipt>(Utf8.GetString(receiptBytes));
            Need(request != null && receipt != null && request.requestId == id && receipt.requestId == id &&
                request.editorInstanceNonce == manifest.editorInstanceNonce && receipt.editorInstanceNonce == manifest.editorInstanceNonce &&
                request.projectId == manifest.projectId && request.projectLibraryGuid == GlobalLibraryGuid &&
                receipt.projectId == request.projectId && receipt.projectLibraryGuid == request.projectLibraryGuid &&
                receipt.requestSha256 == Hash(requestBytes), "Actual mailbox request/receipt identity or hash differs."); BindRequest(manifest, request);
        }
        static void RestoreOwnedDirty(Manifest manifest)
        {
            Need(!string.IsNullOrEmpty(manifest.dirtyBinding) && manifest.dirtyBeforeSerialized != null, "No task-owned dirty snapshot to restore.");
            Binding binding = NamedBinding(manifest, manifest.dirtyBinding); var document = Load(binding);
            Need(HashFile(ProjectFile(binding.path)) == manifest.dirtyDiskRevision, "Dirty fixture disk changed; do not restore over new saved content.");
            EditorJsonUtility.FromJsonOverwrite(manifest.dirtyBeforeSerialized, document); EditorUtility.ClearDirty(document);
            manifest.dirtyBinding = null; manifest.dirtyBeforeSerialized = null; manifest.dirtyDiskRevision = null;
        }
        static DevRoomConsoleBridge.Content ReadContent(DevsRealmDocumentAsset document)
        {
            return new DevRoomConsoleBridge.Content { title = document.Title, summary = document.Summary,
                sections = document.Sections.Select((section, index) => new DevRoomConsoleBridge.SectionContent { index = index, title = section.Title,
                    body = section.Body, imageCaption = section.ImageCaption, image = ReadImage(section) }).ToArray() };
        }
        static DevRoomConsoleBridge.ImageReference ReadImage(DevsRealmDocumentSectionData section)
        {
            Texture2D image = section.Image ?? (string.IsNullOrEmpty(section.ImageResourcePath) ? null : Resources.Load<Texture2D>(section.ImageResourcePath));
            if (image == null) return new DevRoomConsoleBridge.ImageReference();
            Need(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(image, out string guid, out long localId), "Task image is not persistent.");
            string path = AssetDatabase.GetAssetPath(image); return new DevRoomConsoleBridge.ImageReference { guid = guid, fileID = localId, type = 3,
                assetPath = path, resourcePath = section.ImageResourcePath, sha256 = HashFile(ProjectFile(path)), metaRevision = HashFile(ProjectFile(path) + ".meta") };
        }
        static void WriteSourceBindings(Manifest manifest)
        {
            var items = new List<string>();
            foreach (Binding binding in manifest.bindings)
            {
                items.Add("{\"path\":" + Quote(binding.path) + ",\"guid\":" + Quote(binding.guid) + ",\"localFileId\":" + binding.localFileId.ToString(CultureInfo.InvariantCulture) +
                    ",\"expectedLibrary\":" + JsonUtility.ToJson(binding.expectedLibrary) + ",\"images\":{" + Quote(manifest.beforeImageGuid) + ":" + Quote(manifest.beforeImagePath) + "}}");
            }
            File.WriteAllText(manifest.sourceBindingsPath, "[\n" + string.Join(",\n", items) + "\n]\n", Utf8);
        }
        static void WriteFixtureImage(string path, string owner, bool replacement)
        {
            var texture = new Texture2D(16, 16, TextureFormat.RGBA32, false); var colors = new Color32[256];
            byte[] seed = Encoding.ASCII.GetBytes(owner);
            for (int index = 0; index < colors.Length; index++)
            { bool bit = ((seed[index % seed.Length] >> (index % 5)) & 1) != 0;
                colors[index] = replacement ? new Color32(0, bit ? (byte)255 : (byte)0, 255, 255) : new Color32(255, bit ? (byte)255 : (byte)0, 0, 255); }
            try { texture.SetPixels32(colors); texture.Apply(); byte[] png = texture.EncodeToPNG();
                using (var stream = new FileStream(ProjectFile(path), FileMode.CreateNew, FileAccess.Write, FileShare.None)) { stream.Write(png, 0, png.Length); stream.Flush(true); } }
            finally { Object.DestroyImmediate(texture); }
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport | ImportAssetOptions.ForceUpdate);
            var importer = AssetImporter.GetAtPath(path) as TextureImporter; Need(importer != null, "Fixture image importer missing.");
            importer.textureType = TextureImporterType.Default; importer.mipmapEnabled = false; importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.isReadable = false; importer.maxTextureSize = 32; importer.SaveAndReimport();
        }
        static string SourcePixelsHash(string path)
        {
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try { Need(ImageConversion.LoadImage(texture, File.ReadAllBytes(path), false), "Saved task image cannot be decoded."); return PixelsHash(texture.GetPixels32(), texture.width, texture.height); }
            finally { Object.DestroyImmediate(texture); }
        }
        static string ImportedPixelsHash(Texture2D texture)
        {
            Need(texture != null, "Real image reference missing."); RenderTexture previous = RenderTexture.active;
            RenderTexture target = RenderTexture.GetTemporary(texture.width, texture.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            Texture2D readback = new Texture2D(texture.width, texture.height, TextureFormat.RGBA32, false);
            try { Graphics.Blit(texture, target); RenderTexture.active = target;
                readback.ReadPixels(new Rect(0, 0, texture.width, texture.height), 0, 0); readback.Apply(); return PixelsHash(readback.GetPixels32(), readback.width, readback.height); }
            finally { RenderTexture.active = previous; RenderTexture.ReleaseTemporary(target); Object.DestroyImmediate(readback); }
        }
        static T FindNamed<T>(GameObject root, string name) where T : Component
        {
            var matches = root.GetComponentsInChildren<T>(true).Where(value => value.name == name).ToArray();
            Need(matches.Length == 1, "The current game preview does not have exactly one required " + typeof(T).Name + " named " + name);
            return matches[0];
        }
        static string CaptureDisplayFrame(Camera camera, RawImage imageElement, string path, bool checkUploadedColor, out int visiblePixels)
        {
            const int width = 1280, height = 720;
            RenderTexture previous = RenderTexture.active; RenderTexture oldTarget = camera.targetTexture;
            var target = new RenderTexture(width, height, 24); var pixels = new Texture2D(width, height, TextureFormat.RGBA32, false);
            visiblePixels = 0;
            try
            {
                target.Create(); camera.targetTexture = target; camera.Render(); RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, width, height), 0, 0); pixels.Apply(); Color32[] colors = pixels.GetPixels32();
                if (checkUploadedColor && imageElement.gameObject.activeInHierarchy)
                {
                    var corners = new Vector3[4]; imageElement.rectTransform.GetWorldCorners(corners);
                    Vector3[] screen = corners.Select(camera.WorldToScreenPoint).ToArray();
                    int minX = Mathf.Clamp(Mathf.FloorToInt(screen.Min(point => point.x)), 0, width - 1);
                    int maxX = Mathf.Clamp(Mathf.CeilToInt(screen.Max(point => point.x)), 0, width - 1);
                    int minY = Mathf.Clamp(Mathf.FloorToInt(screen.Min(point => point.y)), 0, height - 1);
                    int maxY = Mathf.Clamp(Mathf.CeilToInt(screen.Max(point => point.y)), 0, height - 1);
                    for (int y = minY; y <= maxY; y++) for (int x = minX; x <= maxX; x++)
                    { Color32 color = colors[y * width + x]; if (color.b >= 160 && color.r <= 100 && color.a >= 200) visiblePixels++; }
                    Need(visiblePixels > Math.Max(200, ((maxX - minX + 1) * (maxY - minY + 1)) / 10),
                        "Uploaded image color is absent or covers less than ten percent of its actual projected image element.");
                }
                byte[] png = pixels.EncodeToPNG(); using (var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                { stream.Write(png, 0, png.Length); stream.Flush(true); }
                return PixelsHash(colors, width, height);
            }
            finally { camera.targetTexture = oldTarget; RenderTexture.active = previous; target.Release(); Object.DestroyImmediate(target); Object.DestroyImmediate(pixels); }
        }
        static AssetSnapshot[] CaptureRenderAssets()
        {
            string[] paths = { "Assets/Art/Fonts/Inter-Regular SDF.asset", "Assets/Art/Fonts/Roboto-Bold SDF.asset",
                "Assets/Art/Generated/Fonts/InteractiveDisplay/IntroCjk SDF.asset", "Assets/Art/Materials/SimpleMat/Simple Black.mat",
                "Assets/Art/Materials/SimpleMat/Simple Blue.mat" };
            return paths.Select(path => { Object asset = AssetDatabase.LoadMainAssetAtPath(path); Need(asset != null, "Existing game preview dependency missing: " + path);
                return new AssetSnapshot { path = path, asset = asset, bytes = HashFile(ProjectFile(path)), metadata = HashFile(ProjectFile(path) + ".meta"),
                    serialized = EditorJsonUtility.ToJson(asset), dirty = EditorUtility.IsDirty(asset) }; }).ToArray();
        }
        static void VerifyRenderAssets(AssetSnapshot[] assets)
        {
            foreach (AssetSnapshot asset in assets)
                Need(HashFile(ProjectFile(asset.path)) == asset.bytes && HashFile(ProjectFile(asset.path) + ".meta") == asset.metadata &&
                    EditorUtility.IsDirty(asset.asset) == asset.dirty && EditorJsonUtility.ToJson(asset.asset) == asset.serialized,
                    "Visual preview changed an existing game font/material: " + asset.path);
        }
        static string PixelsHash(Color32[] colors, int width, int height)
        {
            using (var stream = new MemoryStream())
            { WriteInt(stream, width); WriteInt(stream, height); foreach (Color32 color in colors) { stream.WriteByte(color.r); stream.WriteByte(color.g); stream.WriteByte(color.b); stream.WriteByte(color.a); } return Hash(stream.ToArray()); }
        }
        static void WriteInt(Stream stream, int value) { stream.WriteByte((byte)(value >> 24)); stream.WriteByte((byte)(value >> 16)); stream.WriteByte((byte)(value >> 8)); stream.WriteByte((byte)value); }
        static SceneSnapshot[] CaptureScenes()
        {
            return Enumerable.Range(0, SceneManager.sceneCount).Select(index => { Scene scene = SceneManager.GetSceneAt(index);
                return new SceneSnapshot { handle = scene.handle, name = scene.name, path = scene.path, loaded = scene.isLoaded, dirty = scene.isDirty,
                    fileSha256 = string.IsNullOrEmpty(scene.path) ? "" : HashFile(ProjectFile(scene.path)) }; }).ToArray();
        }
        static void VerifyProtected(Manifest manifest)
        {
            Need(SceneManager.sceneCount == manifest.scenes.Length && SceneManager.GetActiveScene().handle == manifest.initialActiveScene,
                "Original scene count or active scene changed.");
            for (int index = 0; index < manifest.scenes.Length; index++)
            { Scene before = SceneManager.GetSceneAt(index); SceneSnapshot saved = manifest.scenes[index];
                Need(before.handle == saved.handle && before.path == saved.path && before.name == saved.name && before.isLoaded == saved.loaded && before.isDirty == saved.dirty,
                    "Original scene identity, order, loaded or dirty state changed.");
                if (!string.IsNullOrEmpty(saved.path)) Need(HashFile(ProjectFile(saved.path)) == saved.fileSha256, "An original scene file changed."); }
            Need(HashFile(ProjectFile(GlobalLibrary)) == manifest.globalLibraryRevision && HashFile(ProjectFile(GlobalLibrary) + ".meta") == manifest.globalLibraryMetaRevision,
                "Canonical original library or metadata changed.");
        }
        static Evidence AddEvidence(Manifest manifest, string phase, string request, string detail)
        {
            var entry = new Evidence { phase = phase, requestId = request, at = DateTimeOffset.UtcNow.ToString("O"), detail = detail,
                originalScenesProtected = phase != "prepare-failed", canonicalLibraryProtected = phase != "prepare-failed" };
            manifest.evidence = (manifest.evidence ?? Array.Empty<Evidence>()).Concat(new[] { entry }).ToArray(); return entry;
        }
        static void Persist(Manifest manifest)
        {
            RejectLinks(manifest.workRoot); string path = Path.Combine(manifest.workRoot, "manifest.json"), temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temporary, JsonUtility.ToJson(manifest, true) + "\n", Utf8);
            if (File.Exists(path)) File.Replace(temporary, path, null); else File.Move(temporary, path);
        }
        static Manifest ReadManifest(string path)
        {
            RejectLinks(path); Manifest manifest = ReadJson<Manifest>(path);
            Need(manifest != null && manifest.schemaVersion == 2 && Guid.TryParseExact(manifest.ownerId, "N", out Guid id) && id.ToString("N") == manifest.ownerId &&
                manifest.fixtureRoot == FixtureParent + "/" + manifest.ownerId && manifest.workspace == ProjectRoot &&
                Path.GetFullPath(path) == Path.Combine(ProjectRoot, ".codex", "console-content-sync-verification", manifest.ownerId, "manifest.json") &&
                manifest.workRoot == Path.GetDirectoryName(Path.GetFullPath(path)) &&
                manifest.sourceBindingsPath == Path.Combine(manifest.workRoot, "source-bindings.json") &&
                manifest.isolatedConsoleRoot == Path.Combine(manifest.workRoot, "console-fixture"), "Manifest ownership/path differs from this task.");
            foreach (Binding binding in manifest.bindings ?? Array.Empty<Binding>())
            {
                bool standalone = binding.name == "standalone", device = binding.name == "device";
                Need((standalone || device) && binding.path == manifest.fixtureRoot + (standalone ? "/Standalone.asset" : "/Display.asset") &&
                    binding.id == (standalone ? "qa-standalone-" : "qa-device-") + manifest.ownerId && binding.expectedLibrary != null &&
                    binding.expectedLibrary.path == manifest.fixtureRoot + (standalone ? "/Library.asset" : "/Display.asset") &&
                    binding.expectedLibrary.kind == (standalone ? "devRoomLibrary" : "displayContent"), "A manifest binding escaped the exact task-owned fixture.");
            }
            if (manifest.beforeImagePath != null) Need(manifest.beforeImagePath == manifest.fixtureRoot + "/Before.png", "Before image escaped the task.");
            if (manifest.uploadImagePath != null) Need(manifest.uploadImagePath == manifest.fixtureRoot + "/Upload.png", "Upload image escaped the task.");
            if (manifest.expectedImportedImagePath != null)
                Need(IsHex(manifest.uploadImageSha256, 64) && manifest.expectedImportedImagePath ==
                    "Assets/Resources/UI/DevsRealm/ConsoleMedia/" + manifest.uploadImageSha256 + ".png", "Imported media escaped its exact task-owned SHA path.");
            return manifest;
        }
        static T ReadJson<T>(string path) { RejectLinks(path); return JsonUtility.FromJson<T>(File.ReadAllText(path, Utf8)); }
        static void RequireSession(Manifest manifest)
        {
            var session = ReadJson<DevRoomConsoleBridge.Session>(Path.Combine(MailboxRoot(), "session.json"));
            Need(session.enabled && session.ownerToken == manifest.ownerToken && session.editorInstanceNonce == manifest.editorInstanceNonce &&
                DateTimeOffset.UtcNow < DateTimeOffset.Parse(session.expiresAt, CultureInfo.InvariantCulture), "Task-owned bridge session is not current.");
        }
        static string MailboxRoot() => Path.Combine(ProjectRoot, ".codex", "console-content-sync", "v2");
        static string ReceiptFile(string id) => Path.Combine(MailboxRoot(), "receipts", id + ".json");
        static void RequireClean(string path) { Need(!AssetDatabase.LoadAllAssetsAtPath(path).Any(value => value != null && EditorUtility.IsDirty(value)), "Task fixture has unsaved content; cleanup or write refused."); }
        static void RequireIdle()
        {
            Need(Unity.Multiplayer.PlayMode.CurrentPlayer.IsMainEditor && !AssetDatabase.IsAssetImportWorkerProcess() &&
                !EditorApplication.isPlayingOrWillChangePlaymode && !EditorApplication.isCompiling && !EditorApplication.isUpdating, "Owned QA requires the idle main Editor resource window.");
            Type api = AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetType("UnityEditor.TestTools.TestRunner.Api.TestRunnerApi", false)).FirstOrDefault(type => type != null);
            MethodInfo active = api?.GetMethod("IsRunActive", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic, null, Type.EmptyTypes, null);
            Need(active != null && active.ReturnType == typeof(bool) && !(bool)active.Invoke(null, null), "TestRunner idle cannot be confirmed.");
        }
        static void EnsureFolders(string path)
        { string current = "Assets"; foreach (string part in path.Split('/').Skip(1)) { string next = current + "/" + part; RejectLinks(ProjectFile(next)); if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, part); current = next; } }
        static string ProjectFile(string path)
        { Need(!string.IsNullOrEmpty(path) && path.StartsWith("Assets/", StringComparison.Ordinal) && !path.Contains('\\') && !path.Contains(':') &&
            !path.Split('/').Any(part => part == "." || part == ".." || part.Length == 0), "Path escaped task asset bounds."); string full = Path.GetFullPath(Path.Combine(ProjectRoot, path)); RejectLinks(full); return full; }
        static void RejectLinks(string path)
        { for (string current = Path.GetFullPath(path); !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
            if (File.Exists(current) || Directory.Exists(current)) Need((File.GetAttributes(current) & FileAttributes.ReparsePoint) == 0, "QA paths cannot use symlinks or junctions."); }
        static string Quote(string value) => "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r") + "\"";
        static string HashFile(string path) { RejectLinks(path); using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)) using (SHA256 algorithm = SHA256.Create())
            return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
        static string Hash(byte[] value) { using (SHA256 algorithm = SHA256.Create()) return BitConverter.ToString(algorithm.ComputeHash(value)).Replace("-", "").ToLowerInvariant(); }
        static bool IsHex(string value, int length) => value != null && value.Length == length && value.All(character => character >= '0' && character <= '9' || character >= 'a' && character <= 'f');
        static void Need(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    }
}
