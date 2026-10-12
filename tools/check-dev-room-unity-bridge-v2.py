"""Lightweight protocol/source checks; does not compile or call Unity, read Assets, or write production.

This checks the Python/C# framing contract and rejects missing explicit safety
boundaries. It is not a claim that the Editor bridge has executed successfully.
"""
import hashlib
import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'unity' / 'Editor' / 'DevRoomConsoleBridge.cs'
CONTRACT = ROOT / 'unity' / 'Editor' / 'DevRoomConsoleBridge.contract.json'
QA_SOURCE = ROOT / 'unity' / 'Editor' / 'DevRoomConsoleSyncVerification.cs'
QA_INSTRUCTIONS = ROOT / 'unity' / 'Editor' / 'DevRoomConsoleSyncVerification.machine.json'


def text(value):
    raw = (value or '').encode('utf-8')
    return struct.pack('>I', len(raw)) + raw


def content_hash(title, summary, sections):
    framed = text(title) + text(summary) + struct.pack('>I', len(sections))
    for section in sections:
        framed += b''.join(text(value) for value in section)
    return hashlib.sha256(framed).hexdigest()


class BridgeContractChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding='utf-8-sig')
        cls.contract = json.loads(CONTRACT.read_text(encoding='utf-8-sig'))

    def test_opt_in_window_and_no_startup_scan(self):
        self.assertNotIn('[InitializeOnLoad]', self.source)
        self.assertNotIn('[InitializeOnLoadMethod]', self.source)
        enable = self.source.split('public static void Enable()', 1)[1].split('public static void Disable()', 1)[0]
        self.assertIn('EditorUtility.DisplayDialog', enable)
        self.assertNotIn('Directory.GetFiles', enable)
        self.assertIn('Guid.NewGuid().ToString("N")', enable)
        self.assertIn('beforeAssemblyReload += Disable', enable)
        self.assertIn('EnableForOwnedTask(string ownerToken, int minutes)', enable)
        self.assertIn('minutes >= 1 && minutes <= 120', enable)
        self.assertIn('DateTimeOffset.UtcNow < DateTimeOffset.Parse(Active.expiresAt', self.source)

    def test_exact_subasset_identity_and_main_bundle_save(self):
        self.assertIn('LoadAllAssetsAtPath(source.path).OfType<DevsRealmDocumentAsset>()', self.source)
        self.assertIn('localId == source.localFileId', self.source)
        self.assertIn('display.GetTab(index)?.Document', self.source)
        self.assertEqual(self.source.count('AssetDatabase.SaveAssetIfDirty('), 1)
        self.assertIn('AssetDatabase.SaveAssetIfDirty(saveTarget)', self.source)
        self.assertNotIn('AssetDatabase.SaveAssets(', self.source)
        self.assertIn('ForceSynchronousImport | ImportAssetOptions.ForceUpdate', self.source)

    def test_fail_closed_busy_and_dirty_guards(self):
        for marker in ['isPlayingOrWillChangePlaymode', 'isCompiling', 'isUpdating',
                       'AssetDatabase.IsAssetImportWorkerProcess()', 'TestRunner idle state cannot be verified',
                       'RequireCleanBundle(request.document.path)', 'Image resource path resolves to a different texture']:
            self.assertIn(marker, self.source)

    def test_immutable_uuid_and_no_second_attempt(self):
        self.assertIn('receipt.requestSha256 != requestHash', self.source)
        self.assertIn('if (receipt.attemptStarted)', self.source)
        self.assertIn('this UUID will not write again', self.source)
        self.assertIn('Finish(receipt, "pending", "Write-ahead record saved', self.source)
        self.assertIn('ActualImagesMatch(current, request.target)', self.source)

    def test_media_sha_and_dimensions_checked_before_decode(self):
        self.assertIn('image.stagingName == image.sha256 + extension', self.source)
        self.assertIn('Hash(bytes) == image.sha256', self.source)
        self.assertLess(self.source.index('Encoded image dimensions exceed'), self.source.index('ImageConversion.LoadImage'))
        self.assertIn('FileMode.CreateNew', self.source)
        self.assertNotIn('File.WriteAllText', self.source)
        self.assertIn('protectedDocument', self.source)

    def test_contract_has_fixed_structure_and_separate_image_identity(self):
        self.assertEqual(self.contract['schemaVersion'], 2)
        self.assertIn('localFileId', self.contract['documentFields'])
        self.assertEqual(self.contract['contentHash']['section'], ['title', 'body', 'imageCaption', 'image.resourcePath', 'image.sha256'])
        self.assertIn('document.localFileId', self.contract['structureHash']['prefix'])
        self.assertIn('displayContent', self.contract['parentKinds'])
        self.assertIn('ProjectIdentity(request.projectLibraryGuid)', self.source)
        self.assertIn('CheckGuid(ProjectLibraryPath, request.projectLibraryGuid)', self.source)
        self.assertNotIn('ProjectIdentity(request.expectedLibrary.guid)', self.source)
        self.assertIn('appliedLibraryRevision', self.contract['receiptAppliedFields'])

    def test_content_changes_caption_resource_or_image_sha(self):
        section = ('第一节', '正文\n保留尾空格 ', '示意图', 'UI/DevsRealm/示意图', 'a' * 64)
        baseline = content_hash('文档 \n', ' A & B ', [section])
        for index in (2, 3, 4):
            changed = list(section); changed[index] += 'x'
            self.assertNotEqual(baseline, content_hash('文档 \n', ' A & B ', [changed]))
        self.assertNotEqual(baseline, content_hash('文档', ' A & B ', [section]))
        self.assertNotEqual(content_hash('A', 'B', [('ab', 'c', '', '', '')]), content_hash('A', 'B', [('a', 'bc', '', '', '')]))

    def test_owned_qa_uses_real_mailbox_and_receipts(self):
        source = QA_SOURCE.read_text(encoding='utf-8-sig')
        instructions = json.loads(QA_INSTRUCTIONS.read_text(encoding='utf-8-sig'))
        self.assertIn('DevRoomConsoleBridge.ProcessCurrentSessionRequests()', source)
        self.assertNotIn('[InitializeOnLoad]', source)
        self.assertNotIn('new DevRoomConsoleBridge.Receipt', source)
        self.assertNotIn('WriteReceipt', source)
        self.assertTrue(instructions['preparedOnly'])
        self.assertIn('receipt.requestSha256 == Hash(requestBytes)', source)
        self.assertIn('source-bindings.json', source)

    def test_owned_qa_protects_scene_and_undo_boundaries(self):
        source = QA_SOURCE.read_text(encoding='utf-8-sig')
        for forbidden in ['Undo.ClearAll', 'AssetDatabase.DeleteAsset(', 'SaveScene(', 'NewScene(', 'SetActiveScene(']:
            self.assertNotIn(forbidden, source)
        self.assertIn('Undo.GetCurrentGroup() == receipt.undoGroup', source)
        self.assertIn('before.isDirty == saved.dirty', source)
        self.assertIn('HashFile(ProjectFile(saved.path)) == saved.fileSha256', source)
        self.assertIn('AssetDatabase.MoveAssetToTrash(manifest.fixtureRoot)', source)
        self.assertIn('binding.path == manifest.fixtureRoot +', source)

    def test_actual_game_display_preview_reads_persisted_fixture(self):
        source = QA_SOURCE.read_text(encoding='utf-8-sig')
        render = source.split('public static void RenderVerifiedDevice(', 1)[1].split('public static void VerifyDirtyBlocked(', 1)[0]
        for marker in ['EditorSceneManager.NewPreviewScene()', 'InteractiveDisplayBaker.CreateEditablePreview(preview, content',
                       'display.Content == content', 'display.PageIndex == index', 'body.text == section.Body',
                       'image.texture == expectedImage', 'EditorSceneManager.GetSceneCullingMask(preview)',
                       'CaptureDisplayFrame(', 'EditorSceneManager.ClosePreviewScene(preview)', 'VerifyRenderAssets(dependencies)']:
            self.assertIn(marker, render)
        self.assertIn('camera.Render()', source)
        for forbidden in ['Undo.PerformUndo(', 'Undo.PerformRedo(', 'Undo.ClearUndo(', 'AssetDatabase.SaveAssetIfDirty(']:
            self.assertNotIn(forbidden, render)


if __name__ == '__main__':
    unittest.main()
