using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Unity.RandomRealm.Gameplay.BuildsEditor
{
    // Explicit, temporary main-Editor resource window. Importing this file does not
    // activate a watcher, scan a mailbox, or write a document. Reload closes it.
    public static class DevRoomConsoleBridge
    {
        const int MaxRequestBytes = 4 * 1024 * 1024;
        const int MaxMediaBytes = 16 * 1024 * 1024;
        const int MaxImageDimension = 8192;
        const string ProjectLibraryPath = "Assets/Resources/DevsRealm/DocumentLibrary.asset";
        const string ProjectLibraryGuid = "4d80e8531f4fc6d46b38bbafa382008e";
        const string MediaAssetRoot = "Assets/Resources/UI/DevsRealm/ConsoleMedia";
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        static readonly string ProjectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        static readonly string BridgeRoot = Path.Combine(ProjectRoot, ".codex", "console-content-sync", "v2");
        static readonly string RequestsRoot = Path.Combine(BridgeRoot, "requests");
        static readonly string ReceiptsRoot = Path.Combine(BridgeRoot, "receipts");
        static readonly string MediaRoot = Path.Combine(BridgeRoot, "media");
        static readonly object QueueLock = new object();
        static readonly HashSet<string> Incoming = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        static FileSystemWatcher Watcher;
        static Session Active;
        static double NextCheck;
        static bool WatcherInterrupted;

        [Serializable] public sealed class Session
        {
            public int schemaVersion = 2;
            public bool enabled;
            public string editorInstanceNonce;
            public string ownerToken;
            public string projectRoot;
            public string startedAt;
            public string expiresAt;
        }
        [Serializable] public sealed class SourceFile
        {
            public string kind;
            public string path;
            public string guid;
            public string revision;
            public string metaRevision;
        }
        [Serializable] public sealed class DocumentSource
        {
            public string path;
            public string id;
            public string guid;
            public long localFileId;
            public string revision;
            public string metaRevision;
            public string contentRevision;
            public string structureRevision;
            public string mediaRevision;
        }
        [Serializable] public sealed class ImageReference
        {
            public string guid;
            public long fileID;
            public int type;
            public string resourcePath;
            public string assetPath;
            public string sha256;
            public string metaRevision;
            public string stagingName;
        }
        [Serializable] public sealed class SectionContent
        {
            public int index;
            public string title;
            public string body;
            public string imageCaption;
            public ImageReference image;
        }
        [Serializable] public sealed class Content
        {
            public string title;
            public string summary;
            public SectionContent[] sections;
        }
        [Serializable] public sealed class Request
        {
            public int schemaVersion;
            public string requestId;
            public string editorInstanceNonce;
            public string projectId;
            public string projectLibraryGuid;
            public string workspace;
            public string language;
            public string documentId;
            public string consoleRevision;
            public string contentSha256;
            public SourceFile expectedLibrary;
            public DocumentSource document;
            public Content target;
        }
        [Serializable] public sealed class Receipt
        {
            public int schemaVersion = 2;
            public string requestId;
            public string editorInstanceNonce;
            public string requestSha256;
            public string projectId;
            public string projectLibraryGuid;
            public string documentId;
            public string consoleRevision;
            public string contentSha256;
            public string status;
            public string message;
            public string processedAt;
            public bool attemptStarted;
            public bool recovered;
            public int undoGroup;
            public string undoName;
            public string protectedLibraryRevision;
            public string protectedDocumentRevision;
            public string appliedLibraryRevision;
            public string appliedLibraryMetaRevision;
            public string appliedUnityRevision;
            public string appliedMetaRevision;
            public string appliedContentSha256;
            public string appliedStructureRevision;
            public string appliedMediaRevision;
            public SourceFile expectedLibrary;
            public DocumentSource document;
            public Content actual;
            public string[] createdMediaPaths;
        }
        sealed class Conflict : Exception { public Conflict(string message) : base(message) { } }
        sealed class Busy : Exception { public Busy(string message) : base(message) { } }
        sealed class MediaPlan
        {
            public string path;
            public string source;
            public string sha;
            public bool create;
            public byte[] bytes;
            public Texture2D texture;
            public ImageReference expected;
        }

        [MenuItem("Tools/RandomRealm/Dev Room/Enable Console Content Bridge (15 Minutes)")]
        public static void Enable()
        {
            RequireMainEditor();
            if (EditorBusy(out string reason)) throw new InvalidOperationException(reason);
            if (!EditorUtility.DisplayDialog("Console document write window",
                "Enable confirmed Console document content requests in this main Editor for 15 minutes? " +
                "Use this only after the active Unity task has released its resource window. " +
                "Structure, tabs, layout and order stay owned by the game editor.", "Enable", "Cancel")) return;
            EnableForOwnedTask("manual-" + Guid.NewGuid().ToString("N"), 15);
        }

        // Called only by an explicitly authorized coordinator while it owns the
        // main-Editor resource lease. This uses the identical mailbox processor;
        // it is not a test-only apply path and never inherits an earlier nonce.
        public static void EnableForOwnedTask(string ownerToken, int minutes)
        {
            RequireMainEditor();
            Need(!string.IsNullOrWhiteSpace(ownerToken) && ownerToken.Length <= 240, "An explicit owned-task resource token is required.");
            Need(minutes >= 1 && minutes <= 120, "Resource-window length must be from 1 to 120 minutes.");
            if (EditorBusy(out string reason)) throw new InvalidOperationException(reason);
            Disable();
            foreach (string directory in new[] { BridgeRoot, RequestsRoot, ReceiptsRoot, MediaRoot })
            { RejectLinks(directory); Directory.CreateDirectory(directory); RejectLinks(directory); }
            Active = new Session { enabled = true, editorInstanceNonce = Guid.NewGuid().ToString("N"), ownerToken = ownerToken,
                projectRoot = ProjectRoot, startedAt = UtcNow(), expiresAt = DateTimeOffset.UtcNow.AddMinutes(minutes).ToString("O") };
            Watcher = new FileSystemWatcher(RequestsRoot, "*.json") { IncludeSubdirectories = false,
                NotifyFilter = NotifyFilters.FileName, EnableRaisingEvents = false };
            Watcher.Created += (sender, args) => Enqueue(args.FullPath);
            Watcher.Renamed += (sender, args) => Enqueue(args.FullPath);
            Watcher.Error += (sender, args) => { lock (QueueLock) WatcherInterrupted = true; };
            Watcher.EnableRaisingEvents = true;
            EditorApplication.update += ProcessEvents;
            AssemblyReloadEvents.beforeAssemblyReload += Disable;
            EditorApplication.quitting += Disable;
            // Publish the enabled nonce only after notifications and processor are
            // ready, so a sender cannot race a request through the setup gap.
            try { AtomicJson(Path.Combine(BridgeRoot, "session.json"), Active); }
            catch { Disable(); throw; }
            // No startup or enable-time scan: stale requests are never resumed automatically.
        }

        [MenuItem("Tools/RandomRealm/Dev Room/Disable Console Content Bridge")]
        public static void Disable()
        {
            EditorApplication.update -= ProcessEvents;
            AssemblyReloadEvents.beforeAssemblyReload -= Disable;
            EditorApplication.quitting -= Disable;
            Watcher?.Dispose(); Watcher = null;
            lock (QueueLock) { Incoming.Clear(); WatcherInterrupted = false; }
            if (Active != null)
            {
                Active.enabled = false;
                try { AtomicJson(Path.Combine(BridgeRoot, "session.json"), Active); }
                catch (Exception exception) { Debug.LogWarning("[Console Content] Session closed in memory; session-file cleanup failed: " + exception.Message); }
            }
            Active = null;
        }

        [MenuItem("Tools/RandomRealm/Dev Room/Process Current Session Requests")]
        public static void ProcessCurrentSessionRequests()
        {
            RequireMainEditor(); RequireSession(null); RejectLinks(RequestsRoot);
            foreach (string path in Directory.GetFiles(RequestsRoot, "*.json", SearchOption.TopDirectoryOnly)) Enqueue(path);
            NextCheck = 0; ProcessEvents();
        }
        static void Enqueue(string path) { lock (QueueLock) Incoming.Add(path); }
        static void ProcessEvents()
        {
            if (Active == null || !Active.enabled) return;
            if (DateTimeOffset.UtcNow >= DateTimeOffset.Parse(Active.expiresAt, CultureInfo.InvariantCulture)) { Disable(); return; }
            if (EditorApplication.timeSinceStartup < NextCheck) return;
            NextCheck = EditorApplication.timeSinceStartup + 1;
            string[] paths; bool interrupted;
            lock (QueueLock) { paths = Incoming.ToArray(); Incoming.Clear(); interrupted = WatcherInterrupted; WatcherInterrupted = false; }
            if (interrupted) Debug.LogWarning("[Console Content] Mailbox watcher interrupted; use explicit current-session scan.");
            foreach (string path in paths) if (!ProcessRequest(path)) Enqueue(path);
        }

        static bool ProcessRequest(string path)
        {
            Request request = null; Receipt receipt = null; DevsRealmDocumentAsset changed = null;
            string beforeSerialized = null; bool saveStarted = false; bool savedVerified = false;
            var created = new Dictionary<string, string>(StringComparer.Ordinal);
            try
            {
                RequireMainEditor(); RequireSession(null); RequireRequestPath(path);
                byte[] bytes = ReadBounded(path, MaxRequestBytes);
                string requestHash = Hash(bytes);
                request = JsonUtility.FromJson<Request>(Utf8.GetString(bytes));
                Need(request != null && request.requestId == Path.GetFileNameWithoutExtension(path), "Request filename/identity mismatch.");
                string receiptPath = ReceiptPath(request.requestId);
                if (File.Exists(receiptPath))
                {
                    receipt = JsonUtility.FromJson<Receipt>(Utf8.GetString(ReadBounded(receiptPath, MaxRequestBytes)));
                    Need(receipt != null && receipt.requestId == request.requestId, "Receipt identity is invalid.");
                    if (receipt.requestSha256 != requestHash) { Debug.LogWarning("[Console Content] Changed bytes under an already consumed UUID refused."); return true; }
                    if (receipt.status != "pending" && receipt.status != "unknown") return true;
                }
                else receipt = new Receipt { requestId = request.requestId, requestSha256 = requestHash,
                    editorInstanceNonce = request.editorInstanceNonce, projectId = request.projectId, projectLibraryGuid = request.projectLibraryGuid,
                    documentId = request.documentId, consoleRevision = request.consoleRevision,
                    contentSha256 = request.contentSha256, expectedLibrary = request.expectedLibrary, document = request.document };
                ValidateRequest(request); RequireSession(request.editorInstanceNonce);
                if (EditorBusy(out string reason)) throw new Busy(reason);
                string libraryFile = AssetFile(request.expectedLibrary.path), targetFile = AssetFile(request.document.path);
                CheckGuid(request.expectedLibrary.path, request.expectedLibrary.guid);
                CheckGuid(request.document.path, request.document.guid);
                CheckRevision(libraryFile + ".meta", request.expectedLibrary.metaRevision);
                CheckRevision(targetFile + ".meta", request.document.metaRevision);
                Object library = LoadParent(request.expectedLibrary);
                DevsRealmDocumentAsset target = LoadDocument(request.document);
                VerifyMembership(library, target);
                RequireCleanBundle(request.expectedLibrary.path); RequireCleanBundle(request.document.path);
                Need(target.Sections != null && target.Sections.Count == request.target.sections.Length, "Section count changed.");
                string protectedLibrary = Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(library)));
                string protectedDocument = ProtectedRevision(target);
                string structure = StructureRevision(target, request.document.guid, request.document.localFileId);
                if (structure != request.document.structureRevision) throw new Conflict("Game document structure changed; refresh the mirror.");
                Content current = ReadContent(target);
                // An interrupted attempt may only confirm a complete, protected result. It never writes again.
                if (receipt.attemptStarted)
                {
                    if (receipt.protectedLibraryRevision == protectedLibrary && receipt.protectedDocumentRevision == protectedDocument &&
                        ContentRevision(current) == request.contentSha256 && ActualImagesMatch(current, request.target))
                    { receipt.recovered = true; return Applied(receipt, request, target, library, "Verified an interrupted saved result without repeating its write."); }
                    return Finish(receipt, "unknown", "An interrupted attempt requires explicit review; this UUID will not write again.");
                }
                CheckRevision(libraryFile, request.expectedLibrary.revision); CheckRevision(targetFile, request.document.revision);
                if (ContentRevision(current) != request.document.contentRevision || MediaRevision(current) != request.document.mediaRevision)
                    throw new Conflict("Document text or image references changed since the mirror was read.");
                if (ContentRevision(current) == request.contentSha256 && ActualImagesMatch(current, request.target))
                    return Applied(receipt, request, target, library, "Confirmed matching content without saving.");
                MediaPlan[] plans = PlanImages(request.target);
                RequireSession(request.editorInstanceNonce);
                if (EditorBusy(out reason)) throw new Busy(reason);
                RequireCleanBundle(request.expectedLibrary.path); RequireCleanBundle(request.document.path);
                CheckRevision(libraryFile, request.expectedLibrary.revision); CheckRevision(targetFile, request.document.revision);
                CheckRevision(libraryFile + ".meta", request.expectedLibrary.metaRevision); CheckRevision(targetFile + ".meta", request.document.metaRevision);
                receipt.attemptStarted = true; receipt.protectedLibraryRevision = protectedLibrary;
                receipt.protectedDocumentRevision = protectedDocument;
                receipt.createdMediaPaths = plans.Where(plan => plan != null && plan.create).Select(plan => plan.path).Distinct().ToArray();
                Finish(receipt, "pending", "Write-ahead record saved; applying this exact confirmed content.");
                ImportImages(plans, created);
                // Imports can cause callbacks/domain reload: do not continue unless the same window and all source pins survived.
                RequireSession(request.editorInstanceNonce); if (EditorBusy(out reason)) throw new Busy(reason);
                RequireCleanBundle(request.expectedLibrary.path); RequireCleanBundle(request.document.path);
                CheckRevision(libraryFile, request.expectedLibrary.revision); CheckRevision(targetFile, request.document.revision);
                CheckRevision(libraryFile + ".meta", request.expectedLibrary.metaRevision); CheckRevision(targetFile + ".meta", request.document.metaRevision);
                VerifyPlannedImages(plans);
                beforeSerialized = EditorJsonUtility.ToJson(target); changed = target;
                Undo.IncrementCurrentGroup(); int undoGroup = Undo.GetCurrentGroup();
                Undo.SetCurrentGroupName("Console document content"); Undo.RecordObject(target, "Console document content");
                receipt.undoGroup = undoGroup; receipt.undoName = "Console document content";
                var serialized = new SerializedObject(target);
                serialized.FindProperty("m_Title").stringValue = request.target.title;
                serialized.FindProperty("m_Summary").stringValue = request.target.summary;
                SerializedProperty sections = serialized.FindProperty("m_Sections");
                for (int index = 0; index < request.target.sections.Length; index++)
                {
                    SectionContent content = request.target.sections[index];
                    SerializedProperty section = sections.GetArrayElementAtIndex(index);
                    section.FindPropertyRelative("m_Title").stringValue = content.title;
                    section.FindPropertyRelative("m_Body").stringValue = content.body;
                    section.FindPropertyRelative("m_ImageCaption").stringValue = content.imageCaption ?? "";
                    section.FindPropertyRelative("m_ImageResourcePath").stringValue = content.image?.resourcePath ?? "";
                    section.FindPropertyRelative("m_Image").objectReferenceValue = plans[index]?.texture;
                }
                serialized.ApplyModifiedPropertiesWithoutUndo();
                Need(ProtectedRevision(target) == protectedDocument && Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(library))) == protectedLibrary,
                    "A protected field changed before save.");
                Need(ContentRevision(ReadContent(target)) == request.contentSha256 && ActualImagesMatch(ReadContent(target), request.target), "Editable content failed in-memory verification.");
                Need(target.IsValid(out string validity), "Game document is invalid: " + validity);
                CheckRevision(libraryFile, request.expectedLibrary.revision); CheckRevision(targetFile, request.document.revision);
                VerifyPlannedImages(plans);
                RequireSession(request.editorInstanceNonce); if (EditorBusy(out reason)) throw new Busy(reason);
                // Documents may be subassets of a per-Device content bundle. Save
                // the exact main asset once; never SaveAssets or unrelated scenes.
                Object saveTarget = AssetDatabase.LoadMainAssetAtPath(request.document.path);
                Need(saveTarget != null, "Bound bundle main asset is missing.");
                EditorUtility.SetDirty(target); EditorUtility.SetDirty(saveTarget); saveStarted = true;
                AssetDatabase.SaveAssetIfDirty(saveTarget);
                Need(!EditorUtility.IsDirty(target) && !EditorUtility.IsDirty(saveTarget), "Bound bundle save did not finish.");
                CheckRevision(libraryFile + ".meta", request.expectedLibrary.metaRevision); CheckRevision(targetFile + ".meta", request.document.metaRevision);
                Need(ProtectedRevision(target) == protectedDocument && Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(library))) == protectedLibrary,
                    "Protected identity changed during save.");
                // Force a disk import and resolve the same GUID/local-fileID again, rather than trusting only memory.
                AssetDatabase.ImportAsset(request.document.path, ImportAssetOptions.ForceSynchronousImport | ImportAssetOptions.ForceUpdate);
                target = LoadDocument(request.document); library = LoadParent(request.expectedLibrary); VerifyMembership(library, target);
                Need(ContentRevision(ReadContent(target)) == request.contentSha256 && ActualImagesMatch(ReadContent(target), request.target) && ProtectedRevision(target) == protectedDocument &&
                    Hash(Utf8.GetBytes(EditorJsonUtility.ToJson(library))) == protectedLibrary, "Saved asset re-import differs from the confirmed result.");
                savedVerified = true; Undo.CollapseUndoOperations(undoGroup);
                return Applied(receipt, request, target, library, "Saved and independently re-read the exact Unity content and image references.");
            }
            catch (Busy exception)
            {
                if (receipt?.attemptStarted == true) return FailAttempt(receipt, changed, beforeSerialized, saveStarted, savedVerified, created, exception.Message);
                if (receipt != null) Finish(receipt, "pending", exception.Message);
                return false;
            }
            catch (Conflict exception)
            {
                if (receipt?.attemptStarted == true) return FailAttempt(receipt, changed, beforeSerialized, saveStarted, savedVerified, created, exception.Message);
                if (receipt != null) return Finish(receipt, "conflict", exception.Message);
                Debug.LogWarning("[Console Content] " + exception.Message); return true;
            }
            catch (Exception exception)
            {
                if (receipt?.attemptStarted == true) return FailAttempt(receipt, changed, beforeSerialized, saveStarted, savedVerified, created, exception.Message);
                if (receipt != null) return TryFinish(receipt, "failed", exception.Message);
                Debug.LogWarning("[Console Content] Invalid request refused: " + exception.Message); return true;
            }
        }

        static bool FailAttempt(Receipt receipt, DevsRealmDocumentAsset changed, string before, bool saveStarted,
            bool savedVerified, Dictionary<string, string> created, string message)
        {
            if (!saveStarted)
            {
                if (changed != null && before != null)
                { EditorJsonUtility.FromJsonOverwrite(before, changed); EditorUtility.ClearDirty(changed); }
                // Only media created by this attempt, with its exact hash, is eligible for deletion.
                foreach (KeyValuePair<string, string> owned in created)
                {
                    try
                    {
                        string path = owned.Key;
                        string full = ProjectFile(path); Object image = AssetDatabase.LoadMainAssetAtPath(path);
                        if (owned.Value != null && image != null && !EditorUtility.IsDirty(image) &&
                            HashFile(full) == Path.GetFileNameWithoutExtension(path) && HashFile(full + ".meta") == owned.Value)
                            AssetDatabase.MoveAssetToTrash(path);
                    }
                    catch (Exception exception) { Debug.LogWarning("[Console Content] Owned media retained for review: " + exception.Message); }
                }
                return TryFinish(receipt, "failed", "No document save started; prior content restored. " + message);
            }
            return TryFinish(receipt, "unknown", (savedVerified ? "Saved content was verified; receipt recovery is required. " :
                "Save outcome requires explicit review; this UUID will never write again. ") + message);
        }

        static bool Applied(Receipt receipt, Request request, DevsRealmDocumentAsset target, Object library, string message)
        {
            Content actual = ReadContent(target);
            Need(ContentRevision(actual) == request.contentSha256 && ActualImagesMatch(actual, request.target), "Applied content or resolved image binding differs.");
            receipt.actual = actual; receipt.appliedContentSha256 = ContentRevision(actual);
            receipt.appliedStructureRevision = StructureRevision(target, request.document.guid, request.document.localFileId);
            receipt.appliedMediaRevision = MediaRevision(actual);
            receipt.appliedUnityRevision = HashFile(AssetFile(request.document.path));
            receipt.appliedMetaRevision = HashFile(AssetFile(request.document.path) + ".meta");
            receipt.appliedLibraryRevision = HashFile(AssetFile(request.expectedLibrary.path));
            receipt.appliedLibraryMetaRevision = HashFile(AssetFile(request.expectedLibrary.path) + ".meta");
            DevsRealmDocumentLibrary.Reload();
            return Finish(receipt, "applied", message);
        }
        static bool Finish(Receipt receipt, string status, string message)
        {
            receipt.status = status; receipt.message = message; receipt.processedAt = UtcNow();
            AtomicJson(ReceiptPath(receipt.requestId), receipt); return true;
        }
        static bool TryFinish(Receipt receipt, string status, string message)
        {
            try { return Finish(receipt, status, message); }
            catch (Exception exception) { Debug.LogWarning("[Console Content] Receipt needs explicit recovery: " + exception.Message); return true; }
        }

        static Object LoadParent(SourceFile source)
        {
            Object parent = AssetDatabase.LoadMainAssetAtPath(source.path);
            Need(source.kind == "devRoomLibrary" && parent is DevsRealmDocumentLibraryAsset ||
                source.kind == "displayContent" && parent is InteractiveDisplayContent, "Parent asset type differs from its binding.");
            return parent;
        }
        static DevsRealmDocumentAsset LoadDocument(DocumentSource source)
        {
            var matches = AssetDatabase.LoadAllAssetsAtPath(source.path).OfType<DevsRealmDocumentAsset>().Where(document =>
                document.Id == source.id && AssetDatabase.TryGetGUIDAndLocalFileIdentifier(document, out string guid, out long localId) &&
                guid == source.guid && localId == source.localFileId).ToArray();
            Need(matches.Length == 1, "GUID/local file ID/document ID do not identify exactly one document."); return matches[0];
        }
        static void VerifyMembership(Object parent, DevsRealmDocumentAsset document)
        {
            IEnumerable<DevsRealmDocumentAsset> members;
            if (parent is DevsRealmDocumentLibraryAsset library) members = library.Documents;
            else if (parent is InteractiveDisplayContent display)
                members = Enumerable.Range(0, display.TabCount).Select(index => display.GetTab(index)?.Document);
            else throw new InvalidOperationException("Unsupported bound parent.");
            Need(members != null && members.Count(item => item == document) == 1 &&
                members.Count(item => item != null && item.Id == document.Id) == 1, "Document is not a unique bound parent member.");
        }
        static void RequireCleanBundle(string path)
        {
            if (AssetDatabase.LoadAllAssetsAtPath(path).Any(asset => asset != null && EditorUtility.IsDirty(asset)))
                throw new Busy("The bound asset bundle has unsaved changes; the bridge will not save another editor's edits.");
        }
        static void CheckGuid(string path, string guid)
        {
            Need(AssetDatabase.AssetPathToGUID(path) == guid && AssetDatabase.GUIDToAssetPath(guid) == path,
                "GUID and bound path no longer agree.");
        }
        static void CheckRevision(string path, string expected)
        { if (!File.Exists(path) || HashFile(path) != expected) throw new Conflict("Pinned source file changed: " + Path.GetFileName(path)); }

        static MediaPlan[] PlanImages(Content content)
        {
            var plans = new MediaPlan[content.sections.Length];
            for (int index = 0; index < plans.Length; index++)
            {
                ImageReference image = content.sections[index].image;
                if (image == null || string.IsNullOrEmpty(image.sha256))
                {
                    Need(image == null || string.IsNullOrEmpty(image.guid) && image.fileID == 0 && image.type == 0 &&
                        string.IsNullOrEmpty(image.resourcePath) && string.IsNullOrEmpty(image.assetPath) && string.IsNullOrEmpty(image.stagingName),
                        "A removed image must have an empty identity."); continue;
                }
                Need(IsHex(image.sha256, 64), "Image hash invalid.");
                if (!string.IsNullOrEmpty(image.stagingName))
                {
                    string extension = Path.GetExtension(image.stagingName);
                    Need((extension == ".png" || extension == ".jpg") && image.stagingName == image.sha256 + extension &&
                        string.IsNullOrEmpty(image.guid) && image.fileID == 0 && image.type == 3, "Staged image identity is invalid.");
                    string path = MediaAssetRoot + "/" + image.stagingName;
                    Need(image.assetPath == path && image.resourcePath == "UI/DevsRealm/ConsoleMedia/" + image.sha256,
                        "Staged image destination must be its exact content-addressed resource path.");
                    byte[] bytes = ReadBounded(Path.Combine(MediaRoot, image.stagingName), MaxMediaBytes);
                    Need(Hash(bytes) == image.sha256, "Staged media hash differs."); ValidatePixels(bytes, extension);
                    var plan = new MediaPlan { path = path, source = image.stagingName, sha = image.sha256, bytes = bytes, expected = image,
                        create = !File.Exists(ProjectFile(path)) };
                    if (!plan.create)
                    { Need(HashFile(ProjectFile(path)) == image.sha256, "An existing media path has different bytes."); plan.texture = RequireTexture(path, null, 0); }
                    plans[index] = plan;
                }
                else
                {
                    Need(IsHex(image.guid, 32) && image.fileID != 0 && image.type == 3 && IsHex(image.metaRevision, 64), "Existing image identity is invalid.");
                    string path = image.assetPath; ProjectFile(path); CheckGuid(path, image.guid);
                    CheckRevision(ProjectFile(path), image.sha256); CheckRevision(ProjectFile(path) + ".meta", image.metaRevision);
                    Texture2D texture = RequireTexture(path, image.guid, image.fileID);
                    Need(string.IsNullOrEmpty(image.resourcePath) || Resources.Load<Texture2D>(image.resourcePath) == texture,
                        "Image resource path resolves to a different texture.");
                    plans[index] = new MediaPlan { path = path, sha = image.sha256, texture = texture, expected = image };
                }
            }
            return plans;
        }
        static void ImportImages(MediaPlan[] plans, Dictionary<string, string> created)
        {
            foreach (MediaPlan plan in plans.Where(value => value != null))
            {
                if (plan.create && !created.ContainsKey(plan.path))
                {
                    EnsureAssetFolders(MediaAssetRoot); string full = ProjectFile(plan.path);
                    Need(!File.Exists(full) && !File.Exists(full + ".meta"), "New media destination appeared after validation.");
                    using (var stream = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    { stream.Write(plan.bytes, 0, plan.bytes.Length); stream.Flush(true); }
                    created.Add(plan.path, null);
                    AssetDatabase.ImportAsset(plan.path, ImportAssetOptions.ForceSynchronousImport | ImportAssetOptions.ForceUpdate);
                    var importer = AssetImporter.GetAtPath(plan.path) as TextureImporter;
                    Need(importer != null, "New image did not become a TextureImporter.");
                    importer.textureType = TextureImporterType.Default; importer.mipmapEnabled = false;
                    importer.isReadable = false; importer.maxTextureSize = MaxImageDimension; importer.SaveAndReimport();
                    created[plan.path] = HashFile(full + ".meta");
                }
                plan.texture = RequireTexture(plan.path, null, 0);
                Need(HashFile(ProjectFile(plan.path)) == plan.sha, "Imported media source differs from the confirmed object.");
            }
        }
        static void ValidatePixels(byte[] bytes, string extension)
        {
            Need(extension == ".png" ? bytes.Length >= 8 && bytes[0] == 137 && bytes[1] == 80 && bytes[2] == 78 && bytes[3] == 71 :
                bytes.Length >= 3 && bytes[0] == 255 && bytes[1] == 216 && bytes[2] == 255, "Image signature differs from its extension.");
            // Check encoded dimensions before asking Unity to allocate the decoded bitmap.
            int width = 0, height = 0;
            if (extension == ".png")
            {
                Need(bytes.Length >= 24 && bytes[12] == 73 && bytes[13] == 72 && bytes[14] == 68 && bytes[15] == 82, "PNG IHDR missing.");
                width = BigEndian32(bytes, 16); height = BigEndian32(bytes, 20);
            }
            else
            {
                int offset = 2;
                while (offset + 3 < bytes.Length)
                {
                    Need(bytes[offset++] == 255, "JPEG marker is invalid.");
                    while (offset < bytes.Length && bytes[offset] == 255) offset++;
                    Need(offset < bytes.Length, "JPEG marker is incomplete."); int marker = bytes[offset++];
                    if (marker == 217 || marker == 218) break;
                    if (marker == 1 || marker >= 208 && marker <= 215) continue;
                    Need(offset + 2 <= bytes.Length, "JPEG marker length missing.");
                    int length = (bytes[offset] << 8) | bytes[offset + 1];
                    Need(length >= 2 && offset + length <= bytes.Length, "JPEG marker is truncated.");
                    if ((marker >= 192 && marker <= 195) || (marker >= 197 && marker <= 199) ||
                        (marker >= 201 && marker <= 203) || (marker >= 205 && marker <= 207))
                    { Need(length >= 8, "JPEG frame incomplete."); height = (bytes[offset + 3] << 8) | bytes[offset + 4]; width = (bytes[offset + 5] << 8) | bytes[offset + 6]; break; }
                    offset += length;
                }
            }
            Need(width > 0 && height > 0 && width <= MaxImageDimension && height <= MaxImageDimension &&
                (long)width * height <= 16 * 1024 * 1024, "Encoded image dimensions exceed the allocation limit.");
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try { Need(ImageConversion.LoadImage(texture, bytes, true) && texture.width <= MaxImageDimension && texture.height <= MaxImageDimension,
                "Image cannot be decoded or dimensions exceed the limit."); }
            finally { Object.DestroyImmediate(texture); }
        }
        static int BigEndian32(byte[] bytes, int offset) => (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];
        static void VerifyPlannedImages(MediaPlan[] plans)
        {
            foreach (MediaPlan plan in plans.Where(value => value != null))
            {
                CheckRevision(ProjectFile(plan.path), plan.sha);
                if (string.IsNullOrEmpty(plan.expected.stagingName))
                {
                    CheckGuid(plan.path, plan.expected.guid); CheckRevision(ProjectFile(plan.path) + ".meta", plan.expected.metaRevision);
                    Need(RequireTexture(plan.path, plan.expected.guid, plan.expected.fileID) == plan.texture, "Planned texture binding changed.");
                }
                Need(string.IsNullOrEmpty(plan.expected.resourcePath) || Resources.Load<Texture2D>(plan.expected.resourcePath) == plan.texture,
                    "Planned resource no longer resolves to its verified image.");
            }
        }
        static Texture2D RequireTexture(string path, string guid, long localFileId)
        {
            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            Need(texture != null && !EditorUtility.IsDirty(texture), "Texture is missing or has unsaved edits.");
            if (guid != null) Need(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(texture, out string actualGuid, out long actualId) &&
                actualGuid == guid && actualId == localFileId, "Texture local identity differs.");
            return texture;
        }
        static void EnsureAssetFolders(string path)
        {
            string current = "Assets";
            foreach (string part in path.Split('/').Skip(1))
            { string next = current + "/" + part; RejectLinks(ProjectFile(next)); if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, part); current = next; }
        }

        static Content ReadContent(DevsRealmDocumentAsset target)
        {
            return new Content { title = target.Title, summary = target.Summary,
                sections = target.Sections.Select((section, index) => new SectionContent { index = index, title = section.Title,
                    body = section.Body, imageCaption = section.ImageCaption, image = ReadImage(section) }).ToArray() };
        }
        static ImageReference ReadImage(DevsRealmDocumentSectionData section)
        {
            Texture2D image = section.Image ?? (string.IsNullOrEmpty(section.ImageResourcePath) ? null : Resources.Load<Texture2D>(section.ImageResourcePath));
            if (image == null) { Need(string.IsNullOrEmpty(section.ImageResourcePath), "Image resource reference is unresolved."); return new ImageReference(); }
            Need(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(image, out string guid, out long localId), "Texture is not a persistent asset.");
            string path = AssetDatabase.GetAssetPath(image);
            return new ImageReference { guid = guid, fileID = localId, type = 3, resourcePath = section.ImageResourcePath,
                assetPath = path, sha256 = HashFile(ProjectFile(path)), metaRevision = HashFile(ProjectFile(path) + ".meta") };
        }
        static bool ActualImagesMatch(Content actual, Content desired)
        {
            if (actual.sections.Length != desired.sections.Length) return false;
            for (int index = 0; index < actual.sections.Length; index++)
            {
                ImageReference found = actual.sections[index].image ?? new ImageReference();
                ImageReference expected = desired.sections[index].image ?? new ImageReference();
                if ((found.sha256 ?? "") != (expected.sha256 ?? "") || (found.resourcePath ?? "") != (expected.resourcePath ?? "")) return false;
                if (string.IsNullOrEmpty(expected.sha256))
                { if (!string.IsNullOrEmpty(found.guid) || found.fileID != 0 || !string.IsNullOrEmpty(found.assetPath)) return false; }
                else if (!string.IsNullOrEmpty(expected.stagingName))
                { if (found.assetPath != expected.assetPath || found.type != 3 || !IsHex(found.guid, 32) || found.fileID == 0) return false; }
                else if (found.guid != expected.guid || found.fileID != expected.fileID || found.type != expected.type ||
                    found.assetPath != expected.assetPath || found.metaRevision != expected.metaRevision) return false;
            }
            return true;
        }
        public static string ContentRevision(Content content)
        {
            return Framed(stream => { WriteText(stream, content.title); WriteText(stream, content.summary); WriteLength(stream, content.sections.Length);
                foreach (SectionContent section in content.sections) { WriteText(stream, section.title); WriteText(stream, section.body);
                    WriteText(stream, section.imageCaption); WriteText(stream, section.image?.resourcePath); WriteText(stream, section.image?.sha256); } });
        }
        public static string StructureRevision(DevsRealmDocumentAsset document, string guid, long localId)
        {
            return Framed(stream => { WriteText(stream, document.Id); WriteText(stream, guid); WriteText(stream, Number(localId));
                WriteText(stream, Number((int)document.Category)); WriteText(stream, Number(document.DisplayOrder)); WriteLength(stream, document.Sections.Count);
                for (int index = 0; index < document.Sections.Count; index++) { WriteText(stream, Number(index)); WriteText(stream, "section"); } });
        }
        public static string MediaRevision(Content content)
        {
            return Framed(stream => { WriteLength(stream, content.sections.Length);
                foreach (SectionContent section in content.sections) { ImageReference image = section.image;
                    WriteText(stream, image?.guid); WriteText(stream, Number(image?.fileID ?? 0)); WriteText(stream, Number(image?.type ?? 0));
                    WriteText(stream, image?.resourcePath); WriteText(stream, image?.assetPath); WriteText(stream, image?.sha256); WriteText(stream, image?.metaRevision); } });
        }
        static string ProtectedRevision(DevsRealmDocumentAsset document)
        {
            Need(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(document, out string guid, out long localId), "Document is not persistent.");
            return Framed(stream => { WriteText(stream, StructureRevision(document, guid, localId)); WriteText(stream, document.UpdatedAt);
                WriteText(stream, document.SourceReference); WriteText(stream, document.SourceUpdatedAt); });
        }
        static string Framed(Action<Stream> write) { using (var stream = new MemoryStream()) { write(stream); return Hash(stream.ToArray()); } }
        static void WriteText(Stream stream, string value) { byte[] bytes = Utf8.GetBytes(value ?? ""); WriteLength(stream, bytes.Length); stream.Write(bytes, 0, bytes.Length); }
        static void WriteLength(Stream stream, int value) { stream.WriteByte((byte)(value >> 24)); stream.WriteByte((byte)(value >> 16)); stream.WriteByte((byte)(value >> 8)); stream.WriteByte((byte)value); }
        static string Number(long value) => value.ToString(CultureInfo.InvariantCulture);

        static void ValidateRequest(Request request)
        {
            Need(request.schemaVersion == 2 && Guid.TryParseExact(request.requestId, "D", out Guid id) && id.ToString("D") == request.requestId,
                "Unsupported schema or noncanonical request UUID.");
            Need(string.Equals(Path.GetFullPath(request.workspace).TrimEnd('\\', '/'), ProjectRoot.TrimEnd('\\', '/'),
                StringComparison.OrdinalIgnoreCase), "Request belongs to another workspace.");
            Need(request.expectedLibrary != null && request.document != null && request.target != null, "Bound source or target is missing.");
            AssetFile(request.expectedLibrary.path); AssetFile(request.document.path);
            Need(IsHex(request.expectedLibrary.guid, 32) && IsHex(request.document.guid, 32) && request.document.localFileId != 0 &&
                IsHex(request.expectedLibrary.revision, 64) && IsHex(request.expectedLibrary.metaRevision, 64) &&
                IsHex(request.document.revision, 64) && IsHex(request.document.metaRevision, 64) && IsHex(request.document.contentRevision, 64) &&
                IsHex(request.document.structureRevision, 64) && IsHex(request.document.mediaRevision, 64) && IsHex(request.contentSha256, 64) &&
                IsHex(request.consoleRevision, 64) && IsHex(request.projectId, 64), "Source pins are incomplete.");
            // Project identity stays in the original global-library namespace.
            // A Device's private parent GUID is a binding pin, never a new project ID.
            Need(request.projectLibraryGuid == ProjectLibraryGuid, "Canonical project-library namespace differs.");
            CheckGuid(ProjectLibraryPath, request.projectLibraryGuid);
            Need(request.projectId == ProjectIdentity(request.projectLibraryGuid), "Canonical project identity differs.");
            Need(request.language == "zh" || request.language == "en", "Content language is invalid.");
            Need(!string.IsNullOrWhiteSpace(request.documentId) && !string.IsNullOrWhiteSpace(request.document.id), "Document identity missing.");
            ValidateContent(request.target);
            Need(ContentRevision(request.target) == request.contentSha256, "Confirmed content hash differs from target content.");
        }
        static void ValidateContent(Content content)
        {
            Need(!string.IsNullOrWhiteSpace(content.title) && Utf8.GetByteCount(content.title) <= 1024 && !string.IsNullOrWhiteSpace(content.summary),
                "Game document needs a title and summary.");
            Need(content.sections != null && content.sections.Length > 0 && content.sections.Length <= 128, "Ordered sections are missing or too large.");
            for (int index = 0; index < content.sections.Length; index++)
            { SectionContent section = content.sections[index]; Need(section != null && section.index == index && !string.IsNullOrWhiteSpace(section.title) &&
                !string.IsNullOrWhiteSpace(section.body), "Existing game sections must retain their indexes and valid title/body."); }
        }
        static void RequireSession(string nonce)
        {
            Need(Active != null && Active.enabled && DateTimeOffset.UtcNow < DateTimeOffset.Parse(Active.expiresAt, CultureInfo.InvariantCulture) &&
                (nonce == null || Active.editorInstanceNonce == nonce), "This Editor instance has no matching enabled resource window.");
        }
        static bool EditorBusy(out string reason)
        {
            reason = null;
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating)
                reason = "Waiting for Play, compilation and imports to finish.";
            else
            {
                Type api = AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetType("UnityEditor.TestTools.TestRunner.Api.TestRunnerApi", false)).FirstOrDefault(type => type != null);
                // Verified read-only against com.unity.test-framework 1.7.0,
                // Api/TestRunnerApi.cs:217-220: internal static bool IsRunActive()
                // inspects GetAllRunners().Any(r => r.GetData().isRunning).
                MethodInfo active = api?.GetMethod("IsRunActive", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic,
                    null, Type.EmptyTypes, null);
                if (api == null || active == null || active.ReturnType != typeof(bool)) reason = "TestRunner idle state cannot be verified; no content write is allowed.";
                else if ((bool)active.Invoke(null, null)) reason = "Waiting for the active Unity test run to finish.";
            }
            return reason != null;
        }
        static void RequireMainEditor()
        { Need(Unity.Multiplayer.PlayMode.CurrentPlayer.IsMainEditor && !AssetDatabase.IsAssetImportWorkerProcess(), "Only the main Editor can process content requests."); }
        static string ProjectIdentity(string libraryGuid)
        { string identityRoot = ProjectRoot.TrimEnd('\\', '/').Replace('/', '\\').ToLowerInvariant(); return Hash(Utf8.GetBytes("unity-dev-room-v1\n" + identityRoot + "\n" + libraryGuid)); }
        static string AssetFile(string path) { Need(path != null && path.EndsWith(".asset", StringComparison.Ordinal), "Document binding must be an .asset."); return ProjectFile(path); }
        static string ProjectFile(string path)
        {
            Need(!string.IsNullOrEmpty(path) && path.StartsWith("Assets/", StringComparison.Ordinal) && !path.Contains('\\') &&
                !path.Contains(':') && !path.Split('/').Any(part => part == ".." || part == "." || part.Length == 0), "Asset path is not a bounded project-relative path.");
            string full = Path.GetFullPath(Path.Combine(ProjectRoot, path));
            Need(full.StartsWith(ProjectRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase), "Asset path escaped the project.");
            RejectLinks(full); return full;
        }
        static void RequireRequestPath(string path)
        { Need(Path.GetDirectoryName(Path.GetFullPath(path)) == RequestsRoot && Path.GetExtension(path) == ".json", "Request escaped its mailbox."); RejectLinks(path); }
        static string ReceiptPath(string id) { Need(Guid.TryParseExact(id, "D", out Guid value) && value.ToString("D") == id, "Receipt UUID invalid."); return Path.Combine(ReceiptsRoot, id + ".json"); }
        static byte[] ReadBounded(string path, int maximum)
        {
            RejectLinks(path); using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            { Need(stream.Length > 0 && stream.Length <= maximum, "File exceeds the bounded content limit."); var bytes = new byte[(int)stream.Length]; int offset = 0;
                while (offset < bytes.Length) { int read = stream.Read(bytes, offset, bytes.Length - offset); Need(read > 0, "File is incomplete."); offset += read; } return bytes; }
        }
        static void AtomicJson(string path, object value)
        {
            RejectLinks(path); string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            byte[] bytes = Utf8.GetBytes(JsonUtility.ToJson(value, true));
            try { using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { stream.Write(bytes, 0, bytes.Length); stream.Flush(true); }
                if (File.Exists(path)) File.Replace(temporary, path, null); else File.Move(temporary, path); }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        static void RejectLinks(string path)
        {
            for (string current = Path.GetFullPath(path); !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
                if (File.Exists(current) || Directory.Exists(current)) Need((File.GetAttributes(current) & FileAttributes.ReparsePoint) == 0, "Bridge paths cannot use symlinks or junctions.");
        }
        static string HashFile(string path) { RejectLinks(path); return Hash(File.ReadAllBytes(path)); }
        static string Hash(byte[] bytes) { using (SHA256 algorithm = SHA256.Create()) return BitConverter.ToString(algorithm.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        static bool IsHex(string value, int length) => value != null && value.Length == length && value.All(character => character >= '0' && character <= '9' || character >= 'a' && character <= 'f');
        static string UtcNow() => DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture);
        static void Need(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    }
}
