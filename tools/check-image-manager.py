"""Small original-byte and replacement-safety checks using disposable images."""
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from image_manager import ImageManagerService, ImageManagerError, _title
import image_manager


def picture(color, format='PNG'):
    with Image.new('RGB', (24, 16), color) as image:
        stream = io.BytesIO()
        image.save(stream, format=format)
        return stream.getvalue()


class ImageManagerChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-images-check-')
        self.directory = Path(self.temporary.name)
        self.root = self.directory / 'library'
        self.root.mkdir()
        self.device = self.directory / 'device'
        self.device.mkdir()
        self.service = ImageManagerService(self.directory / 'config.json')
        self.service.configure({'root': str(self.root)})

    def tearDown(self):
        self.temporary.cleanup()

    def scan(self):
        return self.service.scan({'expectedRoot': str(self.root)})

    def apply(self, plan, action):
        return self.service.apply({'expectedRoot': str(self.root), 'planId': plan['id'],
                                   'decisions': [{'id': item['id'], 'action': action} for item in plan['candidates']]})

    def test_same_pixels_in_another_format_are_duplicate_not_a_rename(self):
        original = picture('red')
        (self.root / 'original.png').write_bytes(original)
        (self.root / 'inbox' / 'different.bmp').write_bytes(picture('red', 'BMP'))
        plan = self.scan()
        self.assertEqual(plan['candidates'][0]['status'], 'duplicate')
        self.assertEqual(plan['candidates'][0]['matchReason'], 'pixels')
        self.assertEqual((self.root / 'original.png').read_bytes(), original)
        self.apply(plan, 'keep')
        self.assertEqual(self.scan()['candidates'], [])
        self.assertTrue((self.root / 'inbox' / 'different.bmp').exists())

    def test_same_title_and_size_require_confirmation_and_preserve_both_versions(self):
        red, blue = picture('red'), picture('blue')
        original = self.root / 'Title_24x16.png'
        original.write_bytes(red)
        (self.root / 'inbox' / 'Title - 24x16.png').write_bytes(blue)
        plan = self.scan()
        self.assertEqual(plan['candidates'][0]['status'], 'conflict')
        self.assertEqual(original.read_bytes(), red)
        receipt = self.apply(plan, 'replace')
        self.assertEqual(original.read_bytes(), blue)
        self.assertFalse((self.root / 'inbox' / 'Title - 24x16.png').exists())
        backups = list(Path(receipt['historyPath']).glob('*.png'))
        self.assertIn(red, [path.read_bytes() for path in backups])
        self.assertIn(blue, [path.read_bytes() for path in backups])
        replay = self.apply(plan, 'replace')
        self.assertTrue(replay['replayed'])
        self.assertEqual(self.scan()['candidates'], [])

    def test_changed_target_and_root_switch_reject_stale_review(self):
        original = self.root / 'Title.png'
        original.write_bytes(picture('red'))
        (self.root / 'inbox' / 'Title.png').write_bytes(picture('blue'))
        plan = self.scan()
        green = picture('green')
        original.write_bytes(green)
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')
        self.assertEqual(original.read_bytes(), green)
        self.service.configure({'root': str(self.device)})
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')

    def test_uploaded_bytes_keep_content_and_use_actual_dimensions(self):
        original = picture('red')
        plan = self.service.import_files([('Photo_999x999.png', original)], {'expectedRoot': str(self.root)})
        candidate = plan['candidates'][0]
        self.assertEqual(candidate['incoming']['canonicalName'], 'Photo - 24x16.png')
        receipt = self.apply(plan, 'add')
        self.assertEqual((self.root / 'Photo - 24x16.png').read_bytes(), original)
        self.assertEqual(receipt['applied'], 1)
        self.assertEqual(self.service.state()['items'][0]['width'], 24)

    def test_device_sync_conflict_is_reviewed_in_both_directions(self):
        self.service.configure({'root': str(self.root), 'deviceRoot': str(self.device)})
        (self.root / 'Image_24x16.png').write_bytes(picture('red'))
        destination = self.device / 'Image - 24x16.png'
        blue = picture('blue')
        destination.write_bytes(blue)
        plan = self.service.sync_device({'expectedRoot': str(self.root), 'direction': 'to-device'})
        self.assertEqual(plan['candidates'][0]['status'], 'conflict')
        self.assertEqual(destination.read_bytes(), blue)
        self.apply(plan, 'replace')
        self.assertEqual(destination.read_bytes(), picture('red'))
        self.assertTrue((self.root / 'Image_24x16.png').exists())
        self.assertEqual(self.service.sync_device({'expectedRoot': str(self.root), 'direction': 'from-device'})['candidates'], [])

    def device_service(self):
        service = ImageManagerService(self.directory / 'device-config.json')
        service.configure({'root':str(self.device)})
        self.service.configure({'root':str(self.root), 'deviceRoot':str(self.device)})
        return service

    @staticmethod
    def label(service, root, item, group, variant, parent=''):
        return service.annotate({'expectedRoot':str(root), 'path':item['path'], 'sha256':item['sha256'],
            'groupTitle':group, 'variantLabel':variant, 'derivedFromId':parent})['item']

    def test_device_same_sha_metadata_only_updates_persist_without_touching_originals(self):
        other = self.device_service()
        for directory in (self.root, self.device):
            (directory / 'Source.png').write_bytes(picture('red'))
            (directory / 'Output.png').write_bytes(picture('blue'))
        items = {item['title']:item for item in self.scan()['state']['items']}
        other.scan({'expectedRoot':str(self.device)})
        self.label(self.service, self.root, items['Source'], '主游戏 · 图标', '正式版')
        self.label(self.service, self.root, items['Output'], '主游戏 · 图标', '派生尺寸', items['Source']['sha256'])
        before = {str(path):path.read_bytes() for directory in (self.root, self.device) for path in directory.glob('*.png')}
        result = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual(result['candidates'], [])
        self.assertEqual((result['metadataSync']['applied'],result['metadataSync']['status']), (2,'completed'))
        received = {item['title']:item for item in other.state()['items']}
        self.assertEqual((received['Source']['groupTitle'],received['Source']['variantLabel']), ('主游戏 · 图标','正式版'))
        self.assertEqual(received['Output']['derivedFromId'], items['Source']['sha256'])
        self.assertEqual({path:Path(path).read_bytes() for path in before}, before)
        repeat = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual(repeat['metadataSync']['applied'], 0)

    def test_device_reverse_direction_uses_device_annotations_not_console_projection(self):
        other = self.device_service()
        for directory in (self.root, self.device):
            (directory / 'Icon.png').write_bytes(picture('red'))
        local = self.scan()['state']['items'][0]
        remote = other.scan({'expectedRoot':str(self.device)})['state']['items'][0]
        self.label(self.service, self.root, local, 'Console旧用途', '旧方案')
        self.label(other, self.device, remote, 'Playtest · 图标', '设备新方案')
        device_before = (self.device / '.image-manager/library.json').read_bytes()
        result = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'from-device'})
        received = self.service.state()['items'][0]
        self.assertEqual((received['groupTitle'],received['variantLabel']), ('Playtest · 图标','设备新方案'))
        self.assertEqual(result['metadataSync']['target'], 'console')
        self.assertEqual((self.device / '.image-manager/library.json').read_bytes(), device_before)
        (self.device / 'New.png').write_bytes(picture('blue'))
        incoming = next(item for item in other.scan({'expectedRoot':str(self.device)})['state']['items'] if item['title']=='New')
        self.label(other, self.device, incoming, '设备新增用途', '新增方案')
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'from-device'})
        self.assertEqual(plan['candidates'][0]['incoming']['groupTitle'], '设备新增用途')
        self.assertEqual(self.service.state()['plan']['candidates'][0]['incoming']['groupTitle'], '设备新增用途')
        self.assertFalse((self.root / 'New - 24x16.png').exists())
        self.apply(plan, 'add')
        received = next(item for item in self.service.state()['items'] if item['title']=='New')
        self.assertEqual((received['groupTitle'],received['variantLabel']), ('设备新增用途','新增方案'))

    def test_device_new_and_conflict_metadata_waits_for_confirmed_apply_and_excludes_inbox(self):
        other = self.device_service()
        (self.root / 'Icon.png').write_bytes(picture('red'))
        (self.root / 'New.png').write_bytes(picture('green'))
        (self.device / 'Icon.png').write_bytes(picture('blue'))
        pending = self.root / 'inbox/Pending.png'
        pending.write_bytes(picture('purple'))
        local = {item['title']:item for item in self.scan()['state']['items']}
        for item in local.values():
            self.label(self.service, self.root, item, '主游戏用途', '已保存方案')
        other.scan({'expectedRoot':str(self.device)})
        device_before = (self.device / '.image-manager/library.json').read_bytes()
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual({item['status'] for item in plan['candidates']}, {'new','conflict'})
        self.assertEqual(plan['metadataSync']['status'], 'needs_review')
        self.assertEqual((self.device / '.image-manager/library.json').read_bytes(), device_before)
        self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
        self.assertEqual(len(list(self.device.glob('*.png'))), 1)
        receipt = self.service.apply({'expectedRoot':str(self.root), 'planId':plan['id'],
            'decisions':[{'id':item['id'], 'action':'replace' if item['status']=='conflict' else 'add'} for item in plan['candidates']]})
        self.assertEqual(receipt['metadataSync']['status'], 'completed')
        self.assertEqual({(item['groupTitle'],item['variantLabel']) for item in other.state()['items']}, {('主游戏用途','已保存方案')})
        self.assertEqual(pending.read_bytes(), picture('purple'))
        self.assertEqual(len(list(self.device.glob('*.png'))), 2)
        self.service.restore({'expectedRoot':str(self.root), 'planId':plan['id']})
        self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
        self.assertEqual(len(other.state()['items']), 1)
        self.assertEqual(other.state()['items'][0]['sha256'], image_manager._sha(self.device / 'Icon.png'))

    def test_device_metadata_cas_and_source_change_reject_stale_confirmation(self):
        other = self.device_service()
        (self.root / 'Icon.png').write_bytes(picture('red'))
        (self.device / 'Icon.png').write_bytes(picture('blue'))
        self.scan()
        remote = other.scan({'expectedRoot':str(self.device)})['state']['items'][0]
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.label(other, self.device, remote, '用户随后修改', '必须保留')
        protected = (self.device / '.image-manager/library.json').read_bytes()
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')
        self.assertEqual((self.device / '.image-manager/library.json').read_bytes(), protected)
        self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        local = self.service.state()['items'][0]
        self.label(self.service, self.root, local, '源随后修改', '重新核对')
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')
        self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        previous_device = self.directory / 'previous-device'
        self.device.rename(previous_device)
        self.device.mkdir()
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')
        self.assertEqual(list(self.device.iterdir()), [])
        self.assertEqual((previous_device / 'Icon.png').read_bytes(), picture('blue'))

    def test_device_byte_change_and_linked_manifest_reject_metadata_only_write(self):
        other = self.device_service()
        for directory in (self.root, self.device):
            (directory / 'Icon.png').write_bytes(picture('red'))
        local = self.scan()['state']['items'][0]
        other.scan({'expectedRoot':str(self.device)})
        self.label(self.service, self.root, local, '本地已改用途', '新版')
        target = self.device / '.image-manager/library.json'
        protected = target.read_bytes()
        merge = self.service._merge_device_annotations
        def change_during_merge(*args):
            result = merge(*args)
            (self.device / 'Icon.png').write_bytes(picture('blue'))
            return result
        with patch.object(self.service, '_merge_device_annotations', side_effect=change_during_merge):
            with self.assertRaises(ImageManagerError):
                self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual(target.read_bytes(), protected)
        os.link(target, self.directory / 'external-metadata.json')
        with self.assertRaises(ImageManagerError):
            self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual(target.read_bytes(), protected)

    def test_device_apply_metadata_failure_rolls_back_bytes_and_target_annotations(self):
        other = self.device_service()
        (self.root / 'Icon.png').write_bytes(picture('red'))
        (self.device / 'Icon.png').write_bytes(picture('blue'))
        local = self.scan()['state']['items'][0]
        self.label(self.service, self.root, local, '主游戏', '确认方案')
        other.scan({'expectedRoot':str(self.device)})
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        protected = (self.device / '.image-manager/library.json').read_bytes()
        original_write = image_manager._atomic_json
        failed = False
        def fail_after_device_save(path, value):
            nonlocal failed
            if path == self.root / '.image-manager/library.json' and not failed:
                failed = True
                raise PermissionError('fixture final root metadata failure')
            return original_write(path, value)
        with patch.object(image_manager, '_atomic_json', side_effect=fail_after_device_save):
            with self.assertRaises(PermissionError):
                self.apply(plan, 'replace')
        self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
        self.assertEqual((self.device / '.image-manager/library.json').read_bytes(), protected)
        saved = json.loads((self.root / '.image-manager/plans' / (plan['id']+'.json')).read_text(encoding='utf-8'))
        self.assertNotEqual(saved['status'], 'completed')

    def test_device_distinct_original_duplicate_and_keep_do_not_claim_metadata_synchronized(self):
        other = self.device_service()
        (self.root / 'Source.png').write_bytes(picture('red'))
        (self.device / 'Existing.bmp').write_bytes(picture('red', 'BMP'))
        local = self.scan()['state']['items'][0]
        self.label(self.service, self.root, local, '主游戏用途', '独立原件')
        other.scan({'expectedRoot':str(self.device)})
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        self.assertEqual(plan['candidates'][0]['status'], 'duplicate')
        self.assertEqual(plan['metadataSync']['status'], 'needs_review')
        protected = (self.device / 'Existing.bmp').read_bytes()
        receipt = self.apply(plan, 'keep')
        self.assertEqual((receipt['metadataSync']['status'], receipt['metadataSync']['notSynced']), ('needs_review', 1))
        self.assertEqual((self.device / 'Existing.bmp').read_bytes(), protected)
        self.assertNotEqual(other.state()['items'][0]['groupTitle'], '主游戏用途')
        plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
        receipt = self.apply(plan, 'add')
        self.assertEqual(receipt['metadataSync']['status'], 'completed')
        received = next(item for item in other.state()['items'] if item['sha256']==local['sha256'])
        self.assertEqual((received['groupTitle'],received['variantLabel']), ('主游戏用途','独立原件'))

    def test_device_apply_preserves_root_metadata_changed_during_transfer_or_target_save(self):
        other = self.device_service()
        (self.root / 'Icon.png').write_bytes(picture('red'))
        (self.device / 'Icon.png').write_bytes(picture('blue'))
        self.scan()
        other.scan({'expectedRoot':str(self.device)})
        original_write = image_manager._atomic_json
        original_guard = self.service._device_guard
        root_record = self.root / '.image-manager/library.json'
        device_record = self.device / '.image-manager/library.json'
        for phase in ('after-copy', 'after-device-metadata'):
            with self.subTest(phase=phase):
                plan = self.service.sync_device({'expectedRoot':str(self.root), 'direction':'to-device'})
                device_before = device_record.read_bytes()
                protected, guard_calls = [], 0
                def concurrent_edit():
                    value = json.loads(root_record.read_text(encoding='utf-8'))
                    for annotation in value['annotations'].values():
                        annotation.update(groupTitle='并行保存用途 '+phase, variantLabel='保留用户修改')
                    original_write(root_record, value)
                    protected.append(root_record.read_bytes())
                def guard(*args, **kwargs):
                    nonlocal guard_calls
                    guard_calls += 1
                    if phase == 'after-copy' and guard_calls == 2:
                        concurrent_edit()
                    return original_guard(*args, **kwargs)
                def write(path, value):
                    result = original_write(path, value)
                    if phase == 'after-device-metadata' and path == device_record and not protected:
                        concurrent_edit()
                    return result
                with patch.object(self.service, '_device_guard', side_effect=guard):
                    with patch.object(image_manager, '_atomic_json', side_effect=write):
                        with self.assertRaises(ImageManagerError):
                            self.apply(plan, 'replace')
                self.assertEqual(len(protected), 1)
                self.assertEqual(root_record.read_bytes(), protected[0])
                self.assertEqual((self.device / 'Icon.png').read_bytes(), picture('blue'))
                self.assertEqual(device_record.read_bytes(), device_before)
                saved = json.loads((self.root / '.image-manager/plans' / (plan['id']+'.json')).read_text(encoding='utf-8'))
                self.assertEqual(saved['status'], 'recovery_required')

    def test_ambiguous_match_cannot_replace_multiple_existing_images(self):
        (self.root / 'A.png').write_bytes(picture('red'))
        (self.root / 'B.png').write_bytes(picture('red'))
        (self.root / 'inbox' / 'C.bmp').write_bytes(picture('red', 'BMP'))
        plan = self.scan()
        pending = next(item for item in plan['candidates'] if item['source'].startswith('inbox/'))
        self.assertEqual(pending['status'], 'ambiguous')
        with self.assertRaises(ImageManagerError):
            self.apply(plan, 'replace')
        self.assertTrue((self.root / 'A.png').exists())
        self.assertTrue((self.root / 'B.png').exists())

    def test_path_escape_and_nested_device_rejected(self):
        with self.assertRaises(ImageManagerError):
            self.service.image('../config.json', str(self.root))
        with self.assertRaises(ImageManagerError):
            self.service.configure({'root': str(self.root), 'deviceRoot': str(self.root / 'inbox')})
        with self.assertRaises(ImageManagerError):
            self.service.import_files([('../escape.png', picture('red'))], {'expectedRoot': str(self.root)})
        self.assertEqual(_title('LibraryCapsule_600x900.png'), 'LibraryCapsule')
        self.assertEqual(_title('HeaderCapsule_920x430_v9.png'), 'HeaderCapsule_v9')

    def test_cross_format_replace_uses_new_extension_and_can_restore_originals(self):
        previous = picture('red', 'BMP')
        incoming = picture('blue')
        (self.root / 'Title_24x16.bmp').write_bytes(previous)
        source = self.root / 'inbox' / 'Title_24x16.png'
        source.write_bytes(incoming)
        plan = self.scan()
        self.assertEqual(plan['candidates'][0]['target'], 'Title_24x16.png')
        self.apply(plan, 'replace')
        self.assertFalse((self.root / 'Title_24x16.bmp').exists())
        self.assertEqual((self.root / 'Title_24x16.png').read_bytes(), incoming)
        self.assertEqual(self.service.image('Title_24x16.png', str(self.root))['mimeType'], 'image/png')
        self.service.restore({'expectedRoot': str(self.root), 'planId': plan['id']})
        self.assertEqual((self.root / 'Title_24x16.bmp').read_bytes(), previous)
        self.assertEqual(source.read_bytes(), incoming)
        self.assertFalse((self.root / 'Title_24x16.png').exists())
        self.assertTrue(self.service.restore({'expectedRoot': str(self.root), 'planId': plan['id']})['replayed'])

    def test_restore_refuses_to_overwrite_later_user_edits(self):
        original = self.root / 'Title.png'
        original.write_bytes(picture('red'))
        (self.root / 'inbox' / 'Title.png').write_bytes(picture('blue'))
        plan = self.scan()
        self.apply(plan, 'replace')
        later = picture('green')
        original.write_bytes(later)
        with self.assertRaises(ImageManagerError):
            self.service.restore({'expectedRoot': str(self.root), 'planId': plan['id']})
        self.assertEqual(original.read_bytes(), later)

    def test_receipt_failure_rolls_back_files_and_catalogue(self):
        original = self.root / 'Title.png'
        original.write_bytes(picture('red'))
        source = self.root / 'inbox' / 'Title.png'
        source.write_bytes(picture('blue'))
        plan = self.scan()
        before = self.service.state()['items']
        real_atomic = image_manager._atomic_json

        def fail_receipt(path, value):
            if Path(path).name == plan['id'] + '.json' and value.get('status') == 'completed':
                raise OSError('fixture receipt write failed')
            return real_atomic(path, value)

        with patch.object(image_manager, '_atomic_json', side_effect=fail_receipt):
            with self.assertRaises(OSError):
                self.apply(plan, 'replace')
        self.assertEqual(original.read_bytes(), picture('red'))
        self.assertEqual(source.read_bytes(), picture('blue'))
        self.assertEqual(self.service.state()['items'], before)
        self.assertIsNone(self.service.state()['lastSync'])

    def test_root_cross_format_duplicate_can_keep_incoming_path_as_target(self):
        (self.root / 'Title.bmp').write_bytes(picture('red', 'BMP'))
        incoming = self.root / 'Title.png'
        incoming.write_bytes(picture('red'))
        plan = self.scan()
        self.assertEqual(len(plan['candidates']), 1)
        self.apply(plan, 'replace')
        self.assertEqual(incoming.read_bytes(), picture('red'))
        self.assertFalse((self.root / 'Title.bmp').exists())

    def test_duplicates_within_one_upload_are_detected_before_apply(self):
        plan = self.service.import_files([('First.png', picture('red')), ('Second.bmp', picture('red', 'BMP'))],
                                        {'expectedRoot': str(self.root)})
        self.assertEqual([item['status'] for item in plan['candidates']], ['new', 'duplicate'])
        self.assertNotIn('replace', plan['candidates'][1]['actions'])
        self.assertEqual(self.service.state()['inboxCount'], 2)
        self.service.apply({'expectedRoot': str(self.root), 'planId': plan['id'],
                            'decisions': [{'id': item['id'], 'action': item['suggestedAction']} for item in plan['candidates']]})
        self.assertEqual(len(self.service.state()['items']), 1)
        self.assertEqual(self.scan()['candidates'], [])

    def test_final_journal_failure_never_replays_a_rolled_back_success(self):
        original = self.root / 'Title.png'
        original.write_bytes(picture('red'))
        source = self.root / 'inbox' / 'Title.png'
        source.write_bytes(picture('blue'))
        plan = self.scan()
        real_atomic = image_manager._atomic_json

        def fail_final_journal(path, value):
            if Path(path).name == 'recovery.json' and value.get('status') == 'completed':
                raise OSError('fixture final journal write failed')
            return real_atomic(path, value)

        with patch.object(image_manager, '_atomic_json', side_effect=fail_final_journal):
            with self.assertRaises(OSError):
                self.apply(plan, 'replace')
        self.assertEqual(original.read_bytes(), picture('red'))
        self.assertEqual(source.read_bytes(), picture('blue'))
        self.assertIsNone(self.service.state()['lastSync'])
        retry = self.apply(plan, 'replace')
        self.assertFalse(retry.get('replayed', False))
        self.assertEqual(original.read_bytes(), picture('blue'))

    def annotate(self, item, group=None, label=None, **extra):
        return self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],
            'sha256':item['sha256'],'groupTitle':group or item['groupTitle'],
            'variantLabel':label or item['variantLabel'],**extra})

    def test_togo_display_alias_preserves_file_title_and_does_not_merge_logo(self):
        (self.root / 'Togo.png').write_bytes(picture('red'))
        (self.root / 'Logo.png').write_bytes(picture('blue'))
        # Windows filenames are case-insensitive; use a subfolder for the
        # lowercase spelling so this remains a real cross-platform check.
        (self.root / 'lowercase').mkdir()
        (self.root / 'lowercase/togo.png').write_bytes(picture('green'))
        plan = self.scan()
        upper = next(item for item in plan['state']['items'] if item['name'] == 'Togo.png')
        logo = next(item for item in plan['state']['items'] if item['name'] == 'Logo.png')
        lower = next(item for item in plan['state']['items'] if item['path'] == 'lowercase/togo.png')
        self.assertEqual((upper['title'],upper['name'],upper['displayTitle']),('Togo','Togo.png','透明Logo'))
        self.assertEqual(lower['displayTitle'],'togo')
        self.assertNotEqual(upper['groupId'],logo['groupId'])
        self.assertEqual((self.root / 'Togo.png').read_bytes(),picture('red'))

    def test_two_same_size_schemes_keep_stable_labels_after_add_and_scan(self):
        (self.root / 'Title - 24x16.png').write_bytes(picture('red'))
        (self.root / 'inbox/Title - 24x16.png').write_bytes(picture('blue'))
        plan = self.scan()
        candidate = plan['candidates'][0]
        self.assertEqual(candidate['status'],'conflict')
        self.assertEqual(candidate['incoming']['groupId'],candidate['existing']['groupId'])
        self.assertNotEqual(candidate['incoming']['variantId'],candidate['existing']['variantId'])
        labels = {item['sha256']:item['variantLabel'] for item in [candidate['incoming'],candidate['existing']]}
        self.assertEqual(set(labels.values()),{'方案1','方案2'})
        self.apply(plan,'add')
        current = self.scan()
        self.assertEqual(current['candidates'],[])
        self.assertEqual(len(current['state']['items']),2)
        self.assertEqual({item['sha256']:item['variantLabel'] for item in current['state']['items']},labels)
        self.assertEqual(len({item['groupId'] for item in current['state']['items']}),1)
        (self.root / 'Title - 24x16 (0).png').write_bytes(picture('green'))
        reordered = self.scan()['state']['items']
        for item in reordered:
            if item['sha256'] in labels:
                self.assertEqual(item['variantLabel'],labels[item['sha256']])
        self.assertEqual(_title('Title - 32x24 (2).png'),'Title')
        self.assertEqual(_title('Title_32x24_v9.png'),'Title_v9')

    def test_annotation_reprojects_pending_plan_without_changing_id_or_bytes(self):
        plan = self.service.import_files([('Title.png',picture('blue'))],{'expectedRoot':str(self.root)})
        item = plan['candidates'][0]['incoming']
        path = self.root / item['path']
        original = path.read_bytes()
        result = self.annotate(item,group='Header',label='蓝色方案')
        self.assertEqual(result['state']['plan']['id'],plan['id'])
        projected = result['state']['plan']['candidates'][0]['incoming']
        self.assertEqual((projected['groupTitle'],projected['variantLabel']),('Header','蓝色方案'))
        self.assertEqual(path.read_bytes(),original)
        self.apply(plan,'add')
        saved = self.service.state()['items'][0]
        self.assertEqual(saved['variantLabel'],'蓝色方案')
        self.assertIn('[方案 蓝色方案]',saved['syncName'])

    def test_explicit_derivation_rejects_self_unknown_and_cycles(self):
        for name,color in [('Parent','red'),('Child','blue')]:
            (self.root / (name+'.png')).write_bytes(picture(color))
        items = {item['title']:item for item in self.scan()['state']['items']}
        parent,child = items['Parent'],items['Child']
        result = self.annotate(child,group='Header',label='缩小版',derivedFromId=parent['id'])
        self.assertEqual(result['item']['derivedFromId'],parent['sha256'])
        before = (self.root / '.image-manager/library.json').read_bytes()
        for target in [child['sha256'],'0'*64]:
            with self.assertRaises(ImageManagerError):
                self.annotate(child,derivedFromId=target)
        with self.assertRaises(ImageManagerError):
            self.annotate(parent,derivedFromId=child['sha256'])
        self.assertEqual((self.root / '.image-manager/library.json').read_bytes(),before)

    def test_atomic_catalogue_rejects_bad_batch_and_resolves_explicit_pending_source(self):
        (self.root / 'Child.png').write_bytes(picture('blue'))
        child = self.scan()['state']['items'][0]
        parent_digest = image_manager.hashlib.sha256(picture('red')).hexdigest()
        result = self.service.import_annotations({'expectedRoot':str(self.root),'entries':[
            {'sha256':child['sha256'],'groupTitle':'Header','variantLabel':'蓝色','derivedFromId':parent_digest}]})
        projected = result['state']['items'][0]
        self.assertEqual(projected['derivedFromId'],'')
        self.assertEqual(projected['pendingDerivedFromId'],parent_digest)
        self.assertEqual(len(result['unresolved']),1)
        before = (self.root / '.image-manager/library.json').read_bytes()
        with self.assertRaises(ImageManagerError):
            self.service.import_annotations({'expectedRoot':str(self.root),'entries':[
                {'sha256':child['sha256'],'groupTitle':'Changed','variantLabel':'Changed'},
                {'sha256':'not-a-hash','groupTitle':'Invalid','variantLabel':'Invalid'}]})
        self.assertEqual((self.root / '.image-manager/library.json').read_bytes(),before)
        (self.root / 'Parent.png').write_bytes(picture('red'))
        self.scan()
        result = self.service.import_annotations({'expectedRoot':str(self.root),'entries':[]})
        resolved = next(item for item in result['state']['items'] if item['sha256']==child['sha256'])
        self.assertEqual(resolved['derivedFromId'],parent_digest)
        self.assertEqual(resolved['pendingDerivedFromId'],'')

    def test_catalogue_cycles_are_rejected_even_when_remote_assets_are_absent(self):
        before = (self.root / '.image-manager/library.json').read_bytes() if (self.root / '.image-manager/library.json').exists() else None
        with self.assertRaises(ImageManagerError):
            self.service.import_annotations({'expectedRoot':str(self.root),'entries':[
                {'sha256':'a'*64,'groupTitle':'A','variantLabel':'A','derivedFromId':'b'*64},
                {'sha256':'b'*64,'groupTitle':'B','variantLabel':'B','derivedFromId':'a'*64}]})
        self.assertEqual((self.root / '.image-manager/library.json').read_bytes() if (self.root / '.image-manager/library.json').exists() else None,before)

    def test_changed_original_rejects_annotation_without_writing_catalogue(self):
        path = self.root / 'Title.png'
        path.write_bytes(picture('red'))
        item = self.scan()['state']['items'][0]
        before = (self.root / '.image-manager/library.json').read_bytes()
        path.write_bytes(picture('blue'))
        with self.assertRaises(ImageManagerError):
            self.annotate(item,label='Wrong bytes')
        self.assertEqual((self.root / '.image-manager/library.json').read_bytes(),before)

    def test_restore_keeps_annotations_saved_after_the_original_import(self):
        plan = self.service.import_files([('Title.png',picture('blue'))],{'expectedRoot':str(self.root)})
        self.apply(plan,'add')
        item = self.service.state()['items'][0]
        self.annotate(item,label='保留的方案')
        self.service.restore({'expectedRoot':str(self.root),'planId':plan['id']})
        returned = self.scan()['candidates'][0]['incoming']
        self.assertEqual(returned['variantLabel'],'保留的方案')

    def test_explicit_sync_filename_restores_group_and_variant_metadata(self):
        plan = self.service.import_files([('Header [方案 蓝色方案] - 24x16.png',picture('blue'))],
                                        {'expectedRoot':str(self.root)})
        incoming = plan['candidates'][0]['incoming']
        self.assertEqual((incoming['groupTitle'],incoming['variantLabel']),('Header','蓝色方案'))
        self.assertTrue(incoming['variantExplicit'])
        self.assertEqual(incoming['syncName'],'Header [方案 蓝色方案] - 24x16.png')

    def test_notion_underscore_marker_preserves_literal_names_and_catalogue_wins(self):
        original = picture('blue')
        plan = self.service.import_files([('Steam_Header_[方案_Blue_Sky]_-_24x16.png',original)],
                                        {'expectedRoot':str(self.root)})
        item = plan['candidates'][0]['incoming']
        self.assertEqual((item['groupTitle'],item['variantLabel']),('Steam_Header','Blue_Sky'))
        self.assertTrue(item['variantExplicit'])
        result = self.service.import_annotations({'expectedRoot':str(self.root),'entries':[
            {'sha256':item['sha256'],'groupTitle':'Steam Header','variantLabel':'Blue Sky'}]})
        restored = result['state']['plan']['candidates'][0]['incoming']
        self.assertEqual((restored['groupTitle'],restored['variantLabel']),('Steam Header','Blue Sky'))
        self.assertEqual(result['state']['plan']['id'],plan['id'])
        self.assertEqual((self.root / item['path']).read_bytes(),original)

    def test_in_place_content_update_keeps_known_purpose_and_scheme_without_derivation(self):
        path = self.root / 'Togo.png'
        path.write_bytes(picture('red'))
        original = self.scan()['state']['items'][0]
        annotated = self.annotate(original,group='Steam透明Logo',label='正式版')['item']
        path.write_bytes(picture('blue'))
        updated = self.scan()['state']['items'][0]
        self.assertNotEqual(updated['assetId'],original['assetId'])
        self.assertEqual((updated['groupTitle'],updated['variantLabel']),
                         (annotated['groupTitle'],annotated['variantLabel']))
        self.assertNotEqual(updated['variantId'],annotated['variantId'])
        self.assertEqual(updated['derivedFromId'],'')
        self.assertEqual(updated['displayTitle'],'透明Logo')
        self.assertEqual(path.name,'Togo.png')

    def test_default_replace_updates_existing_scheme_while_add_keeps_another_scheme(self):
        (self.root / 'Title.png').write_bytes(picture('red'))
        original = self.scan()['state']['items'][0]
        (self.root / 'inbox/Title.png').write_bytes(picture('blue'))
        plan = self.scan()
        self.apply(plan,'replace')
        updated = self.service.state()['items'][0]
        self.assertNotEqual(updated['variantId'],original['variantId'])
        self.assertEqual(updated['variantLabel'],original['variantLabel'])
        self.assertNotEqual(updated['assetId'],original['assetId'])
        self.annotate(updated,group='新的用途',label='新名称')
        (self.root / updated['path']).write_bytes(picture('green'))
        reupdated = self.scan()['state']['items'][0]
        self.assertEqual((reupdated['groupTitle'],reupdated['variantLabel']),('新的用途','新名称'))

    def test_actual_alpha_marks_transparency_but_opaque_rgba_does_not(self):
        for name,alpha in [('Togo',0),('aaa',255)]:
            with Image.new('RGBA',(24,16),(255,0,0,alpha)) as image:
                image.save(self.root / (name+'.png'))
        items = {item['title']:item for item in self.scan()['state']['items']}
        self.assertIs(items['Togo']['hasTransparency'],True)
        self.assertIs(items['aaa']['hasTransparency'],False)
        self.assertEqual(items['Togo']['displayTitle'],'透明Logo')

    @unittest.skipUnless(os.name == 'nt','Windows reader delete-sharing behavior')
    def test_atomic_json_waits_for_actual_short_windows_read_handle(self):
        target = self.directory / 'state.json'
        original = b'{"version":1,"preserve":"original"}'
        target.write_bytes(original)
        blocked = threading.Event()
        failures = []
        real_replace = os.replace

        def observe_replace(source,destination):
            try:
                return real_replace(source,destination)
            except PermissionError:
                blocked.set()
                raise

        def write():
            try:
                image_manager._atomic_json(target,{'version':2,'preserve':'new complete value'})
            except Exception as error:
                failures.append(error)

        with patch.object(image_manager.os,'replace',side_effect=observe_replace):
            with target.open('rb') as reader:
                worker = threading.Thread(target=write,daemon=True)
                worker.start()
                self.assertTrue(blocked.wait(2),'Fixture must encounter the real Windows sharing denial')
                self.assertEqual(reader.read(),original)
                time.sleep(0.08)
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures,[])
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'version':2,'preserve':'new complete value'})
        self.assertEqual(list(self.directory.glob('state.json.*.tmp')),[])

    def test_atomic_json_permanent_permission_denial_preserves_original_and_cleans_temp(self):
        target = self.directory / 'state.json'
        original = b'{"preserve":"original bytes"}'
        target.write_bytes(original)
        with patch.object(image_manager.os,'replace',side_effect=PermissionError('fixture permanent target denial')) as replace:
            with patch.object(image_manager.time,'sleep'):
                with self.assertRaises(PermissionError):
                    image_manager._atomic_json(target,{'preserve':'must not replace'})
        self.assertEqual(replace.call_count,8)
        self.assertEqual(target.read_bytes(),original)
        self.assertEqual(list(self.directory.glob('state.json.*.tmp')),[])


class StandardNamingChecks(unittest.TestCase):
    """142 adoption is explicit and preserves original bytes and later edits."""
    setUp = ImageManagerChecks.setUp
    tearDown = ImageManagerChecks.tearDown
    scan = ImageManagerChecks.scan
    apply = ImageManagerChecks.apply
    annotate = ImageManagerChecks.annotate

    def naming(self, types):
        items = self.service.state()['items']
        return self.service.naming_plan({'expectedRoot':str(self.root),'entries':[
            {'path':item['path'],'sha256':item['sha256'],'assetType':types[item['path']]}
            for item in items if item['path'] in types]})

    def adopt(self, types):
        plan = self.naming(types)
        return plan, self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})

    @staticmethod
    def sized(color, size):
        stream = io.BytesIO()
        Image.new('RGB',size,color).save(stream,format='PNG')
        return stream.getvalue()

    def visible_bytes(self, root=None):
        root = root or self.root
        return {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*')
                if path.is_file() and image_manager.META not in path.relative_to(root).parts}

    def test_explicit_standard_adoption_uses_actual_format_dimensions_and_keeps_semantics_on_undo(self):
        originals = {'Mira_story_v9_Final_999x999.png':picture('red','JPEG'),
                     'Parent_999x999.png':picture('green')}
        for name,data in originals.items():
            (self.root / name).write_bytes(data)
        before = {item['path']:item for item in self.scan()['state']['items']}
        self.assertFalse(self.service.state()['standardNaming'])
        self.assertIn('v9',before['Mira_story_v9_Final_999x999.png']['syncName'])
        child = self.annotate(before['Mira_story_v9_Final_999x999.png'],group='Old purpose',label='Blue option',
                              derivedFromId=before['Parent_999x999.png']['sha256'])['item']
        self.assertFalse(self.service.state()['standardNaming'])
        plan,receipt = self.adopt({'Mira_story_v9_Final_999x999.png':'LibraryHeader',
                                  'Parent_999x999.png':'LibraryHero'})
        after = {item['groupTitle']:item for item in receipt['state']['items']}
        self.assertTrue(receipt['state']['standardNaming'])
        self.assertEqual(after['LibraryHeader']['path'],'LibraryHeader_24x16.jpg')
        self.assertEqual(after['LibraryHero']['path'],'LibraryHero_24x16.png')
        self.assertEqual((after['LibraryHeader']['width'],after['LibraryHeader']['height']),(24,16))
        for item in after.values():
            self.assertEqual(item['syncName'],item['canonicalName'])
            self.assertEqual(item['canonicalName'],Path(item['path']).name)
        self.assertEqual((after['LibraryHeader']['variantId'],after['LibraryHeader']['variantLabel'],
                          after['LibraryHeader']['derivedFromId']),
                         (child['variantId'],'Blue option',before['Parent_999x999.png']['sha256']))
        for row in receipt['results']:
            self.assertEqual((self.root / row['to']).read_bytes(),originals[row['from']])
        version = self.service._manifest_version(self.root)
        replay = self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertTrue(replay['replayed'])
        self.assertEqual(self.service._manifest_version(self.root),version)
        restored = self.service.naming_restore({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertTrue(restored['restored'])
        self.assertEqual(self.visible_bytes(),originals)
        self.assertFalse(restored['state']['standardNaming'])
        restored_child = next(item for item in restored['state']['items'] if item['sha256']==child['sha256'])
        self.assertEqual((restored_child['groupTitle'],restored_child['variantLabel'],restored_child['derivedFromId']),
                         ('Old purpose','Blue option',before['Parent_999x999.png']['sha256']))

    def test_same_type_size_options_keep_one_strict_basename_and_distinct_originals(self):
        originals = {'First_Final.png':picture('red'),'Second_v9.png':picture('blue')}
        for name,data in originals.items():
            (self.root / name).write_bytes(data)
        before = self.scan()['state']['items']
        first,second = before
        self.annotate(first,group='HeaderCapsule',label='A')
        self.annotate(second,group='HeaderCapsule',label='B',derivedFromId=first['sha256'])
        plan,receipt = self.adopt({name:'HeaderCapsule' for name in originals})
        items = receipt['state']['items']
        self.assertEqual(len({item['path'] for item in items}),2)
        self.assertEqual({Path(item['path']).name for item in items},{'HeaderCapsule_24x16.png'})
        self.assertTrue(all(item['path'].startswith('Options/HeaderCapsule/') for item in items))
        self.assertEqual({item['syncName'] for item in items},{'HeaderCapsule_24x16.png'})
        self.assertEqual({item['variantLabel'] for item in items},{'A','B'})
        self.assertEqual({item['sha256'] for item in items},{hashlib.sha256(data).hexdigest() for data in originals.values()})
        self.assertEqual(next(item for item in items if item['variantLabel']=='B')['derivedFromId'],first['sha256'])
        self.service.naming_restore({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(self.visible_bytes(),originals)

    def test_unindexed_foreign_canonical_target_is_a_conflict_not_a_silent_option(self):
        original,foreign = picture('red'),picture('blue')
        (self.root / 'Story.png').write_bytes(original)
        self.scan()
        (self.root / 'LibraryHero_24x16.png').write_bytes(foreign)
        plan = self.naming({'Story.png':'LibraryHero'})
        self.assertFalse(plan['canApply'])
        self.assertEqual(plan['candidates'][0]['status'],'conflict')
        with self.assertRaises(ImageManagerError):
            self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(self.visible_bytes(),{'Story.png':original,'LibraryHero_24x16.png':foreign})
        self.assertFalse((self.root / 'Options').exists())

    def test_changed_source_and_foreign_manifest_reject_prepared_naming_without_writes(self):
        path = self.root / 'Story.png'
        path.write_bytes(picture('red'))
        self.scan()
        plan = self.naming({'Story.png':'LibraryHero'})
        path.write_bytes(picture('blue'))
        with self.assertRaises(ImageManagerError):
            self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(path.read_bytes(),picture('blue'))
        self.scan()
        plan = self.naming({'Story.png':'LibraryHero'})
        manifest_path = self.root / image_manager.META / 'library.json'
        foreign = json.loads(manifest_path.read_text(encoding='utf-8'))
        foreign['foreignEdit'] = 'preserve'
        image_manager._atomic_json(manifest_path,foreign)
        snapshot = manifest_path.read_bytes()
        with self.assertRaises(ImageManagerError):
            self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(manifest_path.read_bytes(),snapshot)
        self.assertEqual(self.visible_bytes(),{'Story.png':picture('blue')})

    def test_naming_rejects_hardlinks_path_escape_and_changed_root_identity(self):
        source = self.root / 'Story.png'
        source.write_bytes(picture('red'))
        item = self.scan()['state']['items'][0]
        external = self.directory / 'linked.png'
        os.link(source,external)
        with self.assertRaises(ImageManagerError):
            self.naming({'Story.png':'LibraryHero'})
        self.assertEqual(source.read_bytes(),external.read_bytes())
        external.unlink()
        with self.assertRaises(ImageManagerError):
            self.service.naming_plan({'expectedRoot':str(self.root),'entries':[
                {'path':'../outside.png','sha256':item['sha256'],'assetType':'LibraryHero'}]})
        plan = self.naming({'Story.png':'LibraryHero'})
        preserved = self.directory / 'preserved-root'
        self.root.rename(preserved)
        self.root.mkdir()
        with self.assertRaises(ImageManagerError):
            self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual((preserved / source.name).read_bytes(),picture('red'))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_naming_checks_existing_option_parent_identity_before_moving_images(self):
        for name,color in [('One.png','red'),('Two.png','blue')]:
            (self.root / name).write_bytes(picture(color))
        self.scan()
        parent = self.root / 'Options/LibraryHero'
        parent.mkdir(parents=True)
        plan = self.naming({'One.png':'LibraryHero','Two.png':'LibraryHero'})
        parent.rename(self.root / 'Options/preserved-parent')
        parent.mkdir()
        with self.assertRaises(ImageManagerError):
            self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(self.visible_bytes(),{'One.png':picture('red'),'Two.png':picture('blue')})

    def test_final_receipt_failures_roll_back_only_owned_manifest_and_paths(self):
        for mode in ('apply','restore'):
            for boundary in ('owned_receipt','foreign_version','foreign_receipt'):
                with self.subTest(mode=mode,boundary=boundary):
                    root = self.directory / (mode+'-'+boundary)
                    root.mkdir()
                    service = ImageManagerService(self.directory / (root.name+'.json'))
                    service.configure({'root':str(root)})
                    original = picture('red')
                    (root / 'Story.png').write_bytes(original)
                    item = service.scan({'expectedRoot':str(root)})['state']['items'][0]
                    plan = service.naming_plan({'expectedRoot':str(root),'entries':[
                        {'path':item['path'],'sha256':item['sha256'],'assetType':'LibraryHero'}]})
                    payload = {'expectedRoot':str(root),'planId':plan['planId']}
                    if mode=='restore':
                        service.naming_apply(payload)
                    meta = root / image_manager.META
                    manifest_path = meta / 'library.json'
                    plan_path = meta / 'naming-plans' / (plan['planId']+'.json')
                    before = manifest_path.read_bytes()
                    real_atomic = image_manager._atomic_json
                    real_version = service._saved_manifest_version
                    injected,foreign_bytes = [],[]

                    def inject_foreign():
                        foreign = json.loads(manifest_path.read_text(encoding='utf-8'))
                        foreign['foreignEdit'] = boundary
                        foreign['annotations'][item['sha256']]['variantLabel'] = 'Foreign label'
                        real_atomic(manifest_path,foreign)
                        foreign_bytes.append(manifest_path.read_bytes())

                    def receipt_write(path,value):
                        if (Path(path)==plan_path and value.get('status')==('completed' if mode=='apply' else 'restored')
                                and not injected and boundary!='foreign_version'):
                            injected.append(True)
                            if boundary=='foreign_receipt':
                                inject_foreign()
                            raise PermissionError('fixture final durable receipt failure')
                        return real_atomic(path,value)

                    def capture_version(directory,expected):
                        if boundary=='foreign_version' and not injected:
                            injected.append(True)
                            inject_foreign()
                            raise PermissionError('fixture ownership capture failure')
                        return real_version(directory,expected)

                    with patch.object(image_manager,'_atomic_json',side_effect=receipt_write):
                        with patch.object(service,'_saved_manifest_version',side_effect=capture_version):
                            with self.assertRaises(PermissionError):
                                (service.naming_apply if mode=='apply' else service.naming_restore)(payload)
                    self.assertTrue(injected)
                    foreign = boundary.startswith('foreign')
                    expected_name = ('LibraryHero_24x16.png' if mode=='apply' else 'Story.png') if foreign else (
                        'Story.png' if mode=='apply' else 'LibraryHero_24x16.png')
                    self.assertEqual(self.visible_bytes(root),{expected_name:original})
                    self.assertEqual(manifest_path.read_bytes(),foreign_bytes[0] if foreign else before)
                    record = json.loads(plan_path.read_text(encoding='utf-8'))
                    journal = json.loads((meta / 'history' / ('naming-'+plan['planId']) / 'recovery.json').read_text(encoding='utf-8'))
                    self.assertEqual(record['status'],journal['status'])
                    self.assertEqual(record['status'],'recovery_required' if foreign or mode=='restore' else 'rolled_back')
                    self.assertNotEqual(record['status'],'completed')

    def test_naming_and_undo_never_revive_old_image_apply_or_restore_plans(self):
        for completed in (False,True):
            with self.subTest(completedImagePlan=completed):
                root = self.directory / ('completed' if completed else 'pending')
                root.mkdir()
                service = ImageManagerService(self.directory / (root.name+'.json'))
                service.configure({'root':str(root)})
                original = picture('red')
                if completed:
                    old = service.import_files([('Story.png',original)],{'expectedRoot':str(root)})
                    old_payload = {'expectedRoot':str(root),'planId':old['planId'],
                                   'decisions':[{'id':row['id'],'action':'add'} for row in old['candidates']]}
                    service.apply(old_payload)
                else:
                    (root / 'Story.png').write_bytes(original)
                    service.scan({'expectedRoot':str(root)})
                    old = service.import_files([('Pending.png',picture('blue'))],{'expectedRoot':str(root)})
                    old_payload = {'expectedRoot':str(root),'planId':old['planId'],
                                   'decisions':[{'id':row['id'],'action':'add'} for row in old['candidates']]}
                item = service.state()['items'][0]
                epochs = [service.state()['namingEpoch']]
                naming = service.naming_plan({'expectedRoot':str(root),'entries':[
                    {'path':item['path'],'sha256':item['sha256'],'assetType':'LibraryHero'}]})
                payload = {'expectedRoot':str(root),'planId':naming['planId']}
                service.naming_apply(payload)
                for phase in ('named','undone'):
                    if phase=='undone':
                        service.naming_restore(payload)
                    epochs.append(service.state()['namingEpoch'])
                    images = self.visible_bytes(root)
                    manifest_path = root / image_manager.META / 'library.json'
                    manifest = manifest_path.read_bytes()
                    with self.assertRaises(ImageManagerError):
                        if completed:
                            service.restore({'expectedRoot':str(root),'planId':old['planId']})
                        else:
                            service.apply(old_payload)
                    self.assertEqual(self.visible_bytes(root),images)
                    self.assertEqual(manifest_path.read_bytes(),manifest)
                self.assertEqual(len(set(epochs)),3)

    def test_two_file_swap_and_undo_preserve_both_originals(self):
        originals = {'HeaderCapsule_24x16.png':picture('red'),'LibraryHeader_24x16.png':picture('blue')}
        for name,data in originals.items():
            (self.root / name).write_bytes(data)
        self.scan()
        plan,_ = self.adopt({'HeaderCapsule_24x16.png':'LibraryHeader','LibraryHeader_24x16.png':'HeaderCapsule'})
        self.assertEqual((self.root / 'LibraryHeader_24x16.png').read_bytes(),picture('red'))
        self.assertEqual((self.root / 'HeaderCapsule_24x16.png').read_bytes(),picture('blue'))
        self.service.naming_restore({'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(self.visible_bytes(),originals)

    def test_indexed_purpose_edit_renames_atomically_but_variant_edit_keeps_the_image_path(self):
        original = picture('red')
        (self.root / 'Story.png').write_bytes(original)
        self.scan()
        _,receipt = self.adopt({'Story.png':'HeaderCapsule'})
        item = receipt['state']['items'][0]
        epoch = receipt['state']['namingEpoch']
        variant = self.annotate(item,group='HeaderCapsule',label='B')['item']
        self.assertEqual(variant['path'],item['path'])
        self.assertEqual(self.service.state()['namingEpoch'],epoch)
        renamed = self.annotate(variant,group='LibraryHeader',label='B')
        self.assertEqual(renamed['item']['path'],'LibraryHeader_24x16.png')
        self.assertEqual(renamed['item']['variantId'],item['variantId'])
        self.assertEqual(renamed['item']['variantLabel'],'B')
        self.assertEqual(renamed['renamed']['from'],item['path'])
        self.assertEqual(self.visible_bytes(),{'LibraryHeader_24x16.png':original})
        self.assertNotEqual(renamed['state']['namingEpoch'],epoch)

    def test_inbox_unique_size_is_only_a_suggestion_until_manual_adoption_and_unknown_root_cannot_export(self):
        (self.root / 'Known.png').write_bytes(picture('red'))
        self.scan()
        self.adopt({'Known.png':'LibraryHero'})
        original = self.sized('blue',(800,450))
        plan = self.service.import_files([('Clipboard_story_Final.png',original)],{'expectedRoot':str(self.root)})
        incoming = plan['candidates'][0]['incoming']
        self.assertEqual(incoming['standardType'],'')
        self.assertEqual(incoming['suggestedStandardType'],'EventCover')
        self.assertTrue(incoming['namingNeedsReview'])
        self.assertNotEqual(self.service._manifest(self.root)['annotations'].get(incoming['sha256'],{}).get('groupTitle'),'EventCover')
        receipt = self.apply(plan,'add')
        adopted = next(item for item in receipt['state']['items'] if item['sha256']==incoming['sha256'])
        self.assertEqual((adopted['path'],adopted['groupTitle'],adopted['standardType']),
                         ('EventCover_800x450.png','EventCover','EventCover'))
        self.assertFalse(adopted['namingNeedsReview'])
        self.assertEqual((self.root / adopted['path']).read_bytes(),original)
        unknown = self.sized('green',(600,900))
        (self.root / 'External_story_Final.png').write_bytes(unknown)
        item = next(item for item in self.scan()['state']['items'] if item['name']=='External_story_Final.png')
        self.assertEqual((item['standardType'],item['suggestedStandardType']),('','LibraryCapsule'))
        self.assertTrue(item['namingNeedsReview'])
        self.service.configure({'root':str(self.root),'deviceRoot':str(self.device)})
        with self.assertRaises(ImageManagerError):
            self.service.sync_device({'expectedRoot':str(self.root),'direction':'to-device'})
        self.assertEqual(self.visible_bytes(self.device),{})
        self.assertEqual((self.root / item['path']).read_bytes(),unknown)

    def test_inbox_ambiguous_920_type_edit_rematches_only_changed_candidate_in_same_plan(self):
        red,blue = self.sized('red',(920,430)),self.sized('blue',(920,430))
        (self.root / 'Header.png').write_bytes(red)
        self.scan()
        self.adopt({'Header.png':'HeaderCapsule'})
        plan = self.service.import_files([('Unknown_story.png',blue),('Other_pending.png',picture('green'))],
                                         {'expectedRoot':str(self.root)})
        changed = next(row for row in plan['candidates'] if row['incoming']['width']==920)
        other = next(row for row in plan['candidates'] if row['id']!=changed['id'])
        self.assertEqual(changed['incoming']['standardType'],'')
        self.assertEqual(changed['incoming']['suggestedStandardType'],'')
        self.assertEqual(changed['status'],'new')
        edited = self.annotate(changed['incoming'],group='HeaderCapsule',label='B')
        rebuilt = edited['state']['plan']
        self.assertEqual(rebuilt['planId'],plan['planId'])
        current = next(row for row in rebuilt['candidates'] if row['incoming']['sha256']==changed['incoming']['sha256'])
        untouched = next(row for row in rebuilt['candidates'] if row['incoming']['sha256']==other['incoming']['sha256'])
        self.assertNotEqual(current['id'],changed['id'])
        self.assertEqual(current['previousCandidateId'],changed['id'])
        self.assertEqual((current['status'],current['existing']['path']),('conflict','HeaderCapsule_920x430.png'))
        self.assertEqual(untouched['id'],other['id'])
        self.assertEqual((self.root / changed['incoming']['path']).read_bytes(),blue)
        self.assertEqual((self.root / 'HeaderCapsule_920x430.png').read_bytes(),red)

    def test_standard_inbox_apply_preserves_foreign_manifest_and_current_paths_on_transfer_or_receipt_failure(self):
        for phase in ('copy','receipt'):
            with self.subTest(phase=phase):
                root = self.directory / ('inbox-'+phase)
                root.mkdir()
                service = ImageManagerService(self.directory / (root.name+'.json'))
                service.configure({'root':str(root)})
                original,incoming = picture('red'),self.sized('blue',(800,450))
                (root / 'Known.png').write_bytes(original)
                known = service.scan({'expectedRoot':str(root)})['state']['items'][0]
                naming = service.naming_plan({'expectedRoot':str(root),'entries':[
                    {'path':known['path'],'sha256':known['sha256'],'assetType':'HeaderCapsule'}]})
                service.naming_apply({'expectedRoot':str(root),'planId':naming['planId']})
                plan = service.import_files([('Pending_story.png',incoming)],{'expectedRoot':str(root)})
                meta = root / image_manager.META
                manifest_path = meta / 'library.json'
                plan_path = meta / 'plans' / (plan['planId']+'.json')
                real_atomic,real_copy = image_manager._atomic_json,image_manager.shutil.copy2
                injected,foreign_bytes = [],[]

                def foreign_edit():
                    foreign = json.loads(manifest_path.read_text(encoding='utf-8'))
                    foreign['foreignEdit'] = phase
                    foreign['annotations'][known['sha256']]['variantLabel'] = 'Foreign label'
                    real_atomic(manifest_path,foreign)
                    foreign_bytes.append(manifest_path.read_bytes())
                    injected.append(True)

                def copy(source,destination,*args,**kwargs):
                    result = real_copy(source,destination,*args,**kwargs)
                    if phase=='copy' and Path(destination).name.startswith('.image-import-') and not injected:
                        foreign_edit()
                    return result

                def write(path,value):
                    if phase=='receipt' and Path(path)==plan_path and value.get('status')=='completed' and not injected:
                        foreign_edit()
                        raise PermissionError('fixture final adopt receipt failure')
                    return real_atomic(path,value)

                with patch.object(image_manager.shutil,'copy2',side_effect=copy):
                    with patch.object(image_manager,'_atomic_json',side_effect=write):
                        with self.assertRaises((ImageManagerError,PermissionError)):
                            service.apply({'expectedRoot':str(root),'planId':plan['planId'],
                                'decisions':[{'id':row['id'],'action':'add'} for row in plan['candidates']]})
                self.assertTrue(injected)
                self.assertEqual(manifest_path.read_bytes(),foreign_bytes[0])
                images = self.visible_bytes(root)
                self.assertEqual(images['HeaderCapsule_24x16.png'],original)
                self.assertEqual(sum(value==incoming for value in images.values()),1)
                if phase=='receipt':
                    self.assertEqual(images['EventCover_800x450.png'],incoming)
                stored = json.loads(plan_path.read_text(encoding='utf-8'))
                journal = json.loads((meta / 'history' / plan['planId'] / 'recovery.json').read_text(encoding='utf-8'))
                self.assertEqual((stored['status'],journal['status']),('recovery_required','recovery_required'))


class ImageDeletionChecks(unittest.TestCase):
    """145 reversible local deletion; user libraries and remote services are never used."""
    setUp = ImageManagerChecks.setUp
    tearDown = ImageManagerChecks.tearDown
    scan = ImageManagerChecks.scan
    apply = ImageManagerChecks.apply
    annotate = ImageManagerChecks.annotate
    visible_bytes = StandardNamingChecks.visible_bytes

    def indexed(self,name='Image.png',color='red'):
        (self.root / name).write_bytes(picture(color))
        return next(item for item in self.scan()['state']['items'] if item['path']==name)

    def deletion(self,item,character='a'):
        return {'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],'requestId':character*32}

    def undo_payload(self,request):
        return {'expectedRoot':request['expectedRoot'],'requestId':request['requestId']}

    def file_snapshot(self):
        return {path.relative_to(self.root).as_posix():path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def backup(self,request):
        return self.root / image_manager.META / 'history' / ('trash-'+request['requestId']) / ('original'+Path(request['path']).suffix)

    def test_root_delete_and_undo_keep_original_bytes_and_persist_at_most_once_receipts(self):
        item = self.annotate(self.indexed(),group='TransparentLogo',label='Blue option')['item']
        request = self.deletion(item)
        source = self.root / item['path']
        original = source.read_bytes()
        result = self.service.delete(request)
        self.assertTrue(result['deleted'])
        self.assertEqual((result['requestId'],result['path'],result['sha256']),
                         (request['requestId'],item['path'],item['sha256']))
        self.assertFalse(source.exists())
        self.assertEqual(self.backup(request).read_bytes(),original)
        self.assertEqual(result['state']['items'],[])
        self.assertEqual(result['state']['lastDeletion']['requestId'],request['requestId'])
        self.assertTrue(result['state']['lastDeletion']['canRestore'])
        before = self.file_snapshot()
        operation = self.service.delete_operation(self.undo_payload(request))
        self.assertEqual(operation['status'],'completed')
        self.assertEqual((operation['path'],operation['sha256']),(item['path'],item['sha256']))
        self.assertEqual(self.file_snapshot(),before,'A receipt lookup must remain read-only')
        reopened = ImageManagerService(self.directory / 'config.json')
        replay = reopened.delete(request)
        self.assertTrue(replay['deleted'])
        self.assertEqual(self.file_snapshot(),before,'A repeated request must not start another deletion')
        restored = reopened.delete_restore(self.undo_payload(request))
        self.assertTrue(restored['restored'])
        self.assertEqual(source.read_bytes(),original)
        self.assertEqual((restored['state']['items'][0]['variantId'],restored['state']['items'][0]['variantLabel']),
                         (item['variantId'],'Blue option'))
        self.assertEqual(reopened.delete_operation(self.undo_payload(request))['status'],'restored')
        after = self.file_snapshot()
        reopened.delete_restore(self.undo_payload(request))
        try:
            reopened.delete(request)
        except ImageManagerError:
            pass  # A restored ID may report its terminal result or reject a new delete intent.
        self.assertEqual(self.file_snapshot(),after,'Old delete IDs must not delete a restored original again')

    def test_same_sha_copies_and_explicit_derivative_metadata_are_not_deleted_by_asset_identity(self):
        first = self.indexed('First.png')
        (self.root / 'Second.png').write_bytes(picture('red'))
        derived = self.indexed('Derived.png','blue')
        first = next(item for item in self.service.state()['items'] if item['path']=='First.png')
        self.annotate(first,group='Logo',label='Original')
        self.annotate(derived,group='Logo',label='Smaller',derivedFromId=first['sha256'])
        annotations = json.loads(json.dumps(self.service._manifest(self.root)['annotations']))
        request = self.deletion(first)
        result = self.service.delete(request)
        self.assertEqual((self.root / 'Second.png').read_bytes(),picture('red'))
        self.assertEqual((self.root / 'Derived.png').read_bytes(),picture('blue'))
        self.assertEqual(sum(item['sha256']==first['sha256'] for item in result['state']['items']),1)
        self.assertEqual(self.service._manifest(self.root)['annotations'],annotations)
        child = next(item for item in result['state']['items'] if item['path']=='Derived.png')
        self.assertEqual(child['derivedFromId'],first['sha256'])
        self.service.delete_restore(self.undo_payload(request))
        self.assertEqual((self.root / 'First.png').read_bytes(),picture('red'))
        self.assertEqual(self.service._manifest(self.root)['annotations'],annotations)

    def test_inbox_deletion_removes_only_selected_candidate_and_keeps_other_choices_addressable(self):
        plan = self.service.import_files([('One.png',picture('red')),('Two.png',picture('blue'))],
                                         {'expectedRoot':str(self.root)})
        selected,other = plan['candidates']
        request = self.deletion(selected['incoming'])
        original = (self.root / selected['incoming']['path']).read_bytes()
        result = self.service.delete(request)
        self.assertEqual(result['state']['inboxCount'],1)
        current = result['state']['plan']
        self.assertNotEqual(current['planId'],plan['planId'])
        self.assertEqual(len(current['candidates']),1)
        self.assertEqual(current['candidates'][0]['id'],other['id'])
        self.assertEqual((self.root / other['incoming']['path']).read_bytes(),picture('blue'))
        self.assertEqual(result['state']['items'],[],'Deleting an Inbox item must not adopt any other item')
        with self.assertRaises(ImageManagerError):
            self.apply(plan,'add')
        self.assertEqual(self.backup(request).read_bytes(),original)
        restored = self.service.delete_restore(self.undo_payload(request))
        self.assertEqual(restored['state']['inboxCount'],2)
        self.assertEqual((self.root / selected['incoming']['path']).read_bytes(),original)

    def test_invalid_scope_sha_path_device_payload_and_reused_request_cannot_delete_another_file(self):
        item = self.indexed()
        request = self.deletion(item)
        malformed = [dict(request,sha256='0'*64),dict(request,expectedRoot=str(self.device)),
                     dict(request,path='../outside.png'),dict(request,path=str(self.root / item['path'])),
                     dict(request,path=image_manager.META+'/library.json'),dict(request,space='device'),
                     dict(request,requestId='invalid')]
        for payload in malformed:
            with self.subTest(payloadKeys=sorted(payload),path=payload['path']):
                with self.assertRaises(ImageManagerError):
                    self.service.delete(payload)
                self.assertEqual((self.root / item['path']).read_bytes(),picture('red'))
        self.service.delete(request)
        (self.root / 'Other.png').write_bytes(picture('blue'))
        other = next(item for item in self.scan()['state']['items'] if item['path']=='Other.png')
        with self.assertRaises(ImageManagerError):
            self.service.delete(dict(self.deletion(other),requestId=request['requestId']))
        self.assertEqual((self.root / 'Other.png').read_bytes(),picture('blue'))

    def test_changed_original_hardlink_and_root_identity_reject_before_moving_any_file(self):
        item = self.indexed()
        request = self.deletion(item)
        source = self.root / item['path']
        source.write_bytes(picture('blue'))
        with self.assertRaises(ImageManagerError):
            self.service.delete(request)
        self.assertEqual(source.read_bytes(),picture('blue'))
        item = self.scan()['state']['items'][0]
        request = self.deletion(item,'b')
        external = self.directory / 'hardlink.png'
        os.link(source,external)
        with self.assertRaises(ImageManagerError):
            self.service.delete(request)
        self.assertEqual(source.read_bytes(),external.read_bytes())
        external.unlink()
        old_root = self.directory / 'preserved-root'
        self.root.rename(old_root)
        self.root.mkdir()
        with self.assertRaises(ImageManagerError):
            self.service.delete(dict(request,requestId='c'*32))
        self.assertEqual((old_root / item['path']).read_bytes(),picture('blue'))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_undo_refuses_occupied_path_and_foreign_metadata_without_overwriting_either(self):
        item = self.indexed()
        request = self.deletion(item)
        self.service.delete(request)
        source = self.root / item['path']
        source.write_bytes(picture('blue'))
        with self.assertRaises(ImageManagerError):
            self.service.delete_restore(self.undo_payload(request))
        self.assertEqual(source.read_bytes(),picture('blue'))
        self.assertEqual(self.backup(request).read_bytes(),picture('red'))
        source.unlink()
        manifest_path = self.root / image_manager.META / 'library.json'
        foreign = json.loads(manifest_path.read_text(encoding='utf-8'))
        foreign['foreignMetadata'] = 'preserve'
        image_manager._atomic_json(manifest_path,foreign)
        snapshot = manifest_path.read_bytes()
        with self.assertRaises(ImageManagerError):
            self.service.delete_restore(self.undo_payload(request))
        self.assertEqual(manifest_path.read_bytes(),snapshot)
        self.assertFalse(source.exists())
        self.assertEqual(self.backup(request).read_bytes(),picture('red'))
        self.assertNotEqual(self.service.delete_operation(self.undo_payload(request))['status'],'restored')

    def test_delete_and_undo_epochs_reject_old_image_apply_and_restore_without_reviving_them(self):
        for completed in (False,True):
            with self.subTest(completedImagePlan=completed):
                root = self.directory / ('delete-completed' if completed else 'delete-pending')
                root.mkdir()
                service = ImageManagerService(self.directory / (root.name+'.json'))
                service.configure({'root':str(root)})
                if completed:
                    old = service.import_files([('Image.png',picture('red'))],{'expectedRoot':str(root)})
                    choices = [{'id':row['id'],'action':'add'} for row in old['candidates']]
                    service.apply({'expectedRoot':str(root),'planId':old['planId'],'decisions':choices})
                else:
                    (root / 'Image.png').write_bytes(picture('red'))
                    service.scan({'expectedRoot':str(root)})
                    old = service.import_files([('Pending.png',picture('blue'))],{'expectedRoot':str(root)})
                    choices = [{'id':row['id'],'action':'add'} for row in old['candidates']]
                item = service.state()['items'][0]
                epochs = [service.state()['namingEpoch']]
                request = {'expectedRoot':str(root),'requestId':'a'*32,'path':item['path'],'sha256':item['sha256']}
                service.delete(request)
                for phase in ('deleted','undone'):
                    if phase=='undone':
                        service.delete_restore({'expectedRoot':str(root),'requestId':request['requestId']})
                    epochs.append(service.state()['namingEpoch'])
                    before = {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()}
                    with self.assertRaises(ImageManagerError):
                        if completed:
                            service.restore({'expectedRoot':str(root),'planId':old['planId']})
                        else:
                            service.apply({'expectedRoot':str(root),'planId':old['planId'],'decisions':choices})
                    self.assertEqual({path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()},before)
                self.assertEqual(len(set(epochs)),3)

    def test_unknown_operation_lookup_is_read_only_and_corrupt_trash_cannot_restore(self):
        item = self.indexed()
        before = self.file_snapshot()
        missing = self.service.delete_operation({'expectedRoot':str(self.root),'requestId':'f'*32})
        self.assertEqual(missing['status'],'not_found')
        self.assertEqual(self.file_snapshot(),before)
        request = self.deletion(item)
        self.service.delete(request)
        self.backup(request).write_bytes(picture('blue'))
        with self.assertRaises(ImageManagerError):
            self.service.delete_restore(self.undo_payload(request))
        self.assertFalse((self.root / item['path']).exists())
        self.assertEqual(self.backup(request).read_bytes(),picture('blue'))

    def test_delete_and_undo_final_receipt_failure_roll_back_owned_state_but_preserve_foreign_state(self):
        for mode in ('delete','undo'):
            for foreign in (False,True):
                with self.subTest(mode=mode,foreign=foreign):
                    root = self.directory / (mode+('-foreign' if foreign else '-own'))
                    root.mkdir()
                    service = ImageManagerService(self.directory / (root.name+'.json'))
                    service.configure({'root':str(root)})
                    original = picture('red')
                    source = root / 'Image.png'
                    source.write_bytes(original)
                    item = service.scan({'expectedRoot':str(root)})['state']['items'][0]
                    request = {'expectedRoot':str(root),'path':item['path'],'sha256':item['sha256'],'requestId':'a'*32}
                    undo = {'expectedRoot':str(root),'requestId':request['requestId']}
                    if mode=='undo':
                        service.delete(request)
                    meta = root / image_manager.META
                    manifest_path = meta / 'library.json'
                    record_path = meta / 'history' / ('trash-'+request['requestId']) / 'operation.json'
                    before = manifest_path.read_bytes()
                    real_atomic = image_manager._atomic_json
                    injected,foreign_bytes = [],[]

                    def write(path,value):
                        if (Path(path)==record_path and value.get('status')==('completed' if mode=='delete' else 'restored')
                                and not injected):
                            injected.append(True)
                            if foreign:
                                changed = json.loads(manifest_path.read_text(encoding='utf-8'))
                                changed['foreignEdit'] = mode
                                real_atomic(manifest_path,changed)
                                foreign_bytes.append(manifest_path.read_bytes())
                            raise PermissionError('fixture durable deletion receipt failure')
                        return real_atomic(path,value)

                    with patch.object(image_manager,'_atomic_json',side_effect=write):
                        with self.assertRaises((ImageManagerError,PermissionError)):
                            (service.delete(request) if mode=='delete' else service.delete_restore(undo))
                    self.assertTrue(injected,'Fixture must reach the final durable operation record')
                    self.assertEqual(manifest_path.read_bytes(),foreign_bytes[0] if foreign else before)
                    should_exist = mode=='undo' if foreign else mode=='delete'
                    self.assertEqual(source.exists(),should_exist)
                    history_images = [path for path in record_path.parent.glob('original.*') if path.is_file()]
                    self.assertTrue(source.exists() and source.read_bytes()==original or
                                    any(path.read_bytes()==original for path in history_images))
                    operation = service.delete_operation(undo)
                    self.assertNotEqual(operation['status'],'completed' if mode=='delete' else 'restored')
                    snapshot = {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()}
                    try:
                        service.delete(request)
                    except ImageManagerError:
                        pass
                    self.assertEqual({path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()},snapshot,
                                     'A failed or uncertain known request must never start deletion again')

    def test_delete_prepared_record_cannot_bypass_source_or_manifest_change_before_move(self):
        for change in ('source','manifest','pointer'):
            with self.subTest(change=change):
                root = self.directory / ('prepared-'+change)
                root.mkdir()
                service = ImageManagerService(self.directory / (root.name+'.json'))
                service.configure({'root':str(root)})
                source = root / 'Image.png'
                source.write_bytes(picture('red'))
                item = service.scan({'expectedRoot':str(root)})['state']['items'][0]
                request = {'expectedRoot':str(root),'path':item['path'],'sha256':item['sha256'],'requestId':'a'*32}
                meta = root / image_manager.META
                record_path = meta / 'history' / ('trash-'+request['requestId']) / 'operation.json'
                manifest_path = meta / 'library.json'
                real_atomic = image_manager._atomic_json
                injected,foreign_bytes = [],[]
                pointer_path = meta / 'latest-plan.json'

                def write(path,value):
                    result = real_atomic(path,value)
                    if Path(path)==record_path and value.get('status')=='prepared' and not injected:
                        injected.append(True)
                        if change=='source':
                            source.write_bytes(picture('blue'))
                        elif change=='manifest':
                            foreign = json.loads(manifest_path.read_text(encoding='utf-8'))
                            foreign['foreignEdit'] = change
                            real_atomic(manifest_path,foreign)
                            foreign_bytes.append(manifest_path.read_bytes())
                        else:
                            real_atomic(pointer_path,{'planId':'f'*32,'foreignEdit':change})
                            foreign_bytes.append(pointer_path.read_bytes())
                    return result

                with patch.object(image_manager,'_atomic_json',side_effect=write):
                    with self.assertRaises(ImageManagerError):
                        service.delete(request)
                self.assertTrue(injected)
                self.assertEqual(source.read_bytes(),picture('blue' if change=='source' else 'red'))
                self.assertFalse((record_path.parent / 'original.png').exists())
                if change=='manifest':
                    self.assertEqual(manifest_path.read_bytes(),foreign_bytes[0])
                elif change=='pointer':
                    self.assertEqual(pointer_path.read_bytes(),foreign_bytes[0])
                operation = service.delete_operation({'expectedRoot':str(root),'requestId':request['requestId']})
                self.assertIn(operation['status'],('failed','recovery_required'))


class ImageDiscoveryChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-image-discovery-')
        self.directory = Path(self.temporary.name)
        self.root = self.directory / 'library'
        self.root.mkdir()
        self.service = ImageManagerService(self.directory / 'config.json')
        self.service.configure({'root':str(self.root)})

    def tearDown(self):
        self.temporary.cleanup()

    def refresh(self, **keywords):
        observed = image_manager._discovery_inventory(self.root)
        return self.service.safe_refresh_local({'expectedRoot':str(self.root), **observed}, **keywords)

    def private_bytes(self):
        return {path.relative_to(self.root).as_posix():path.read_bytes()
                for path in (self.root / image_manager.META).rglob('*') if path.is_file()}

    def test_new_root_and_inbox_are_discovered_without_adopting_or_renaming_originals(self):
        root_image = self.root / 'Unfinished_v9.png'
        root_image.write_bytes(picture('red'))
        first = self.refresh()
        self.assertEqual(first['status'],'updated')
        state = self.service.state()
        self.assertEqual([item['path'] for item in state['items']],['Unfinished_v9.png'])
        self.assertEqual(state['plan']['candidates'],[])
        self.assertEqual(state['localRevision'],self.service.local_revision(str(self.root))['revision'])
        incoming = self.root / 'inbox' / 'Different.png'
        incoming.write_bytes(picture('blue'))
        second = self.refresh()
        self.assertEqual(second['status'],'updated')
        state = self.service.state()
        self.assertEqual(len(state['items']),1)
        self.assertEqual(len(state['plan']['candidates']),1)
        self.assertNotEqual(first['planId'],second['planId'])
        self.assertEqual(root_image.read_bytes(),picture('red'))
        self.assertEqual(incoming.read_bytes(),picture('blue'))

    def test_in_place_change_inherits_annotation_and_external_delete_preserves_history(self):
        source = self.root / 'Image.png'
        source.write_bytes(picture('red'))
        self.refresh()
        item = self.service.state()['items'][0]
        self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
            'groupTitle':'Purpose','variantLabel':'Choice A'})
        source.write_bytes(picture('blue'))
        self.assertEqual(self.refresh()['status'],'updated')
        changed = self.service.state()['items'][0]
        self.assertEqual((changed['groupTitle'],changed['variantLabel']),('Purpose','Choice A'))
        self.assertNotEqual(item['sha256'],changed['sha256'])
        source.unlink()  # The external editor deletes its file; discovery only observes it.
        self.assertEqual(self.refresh()['status'],'updated')
        manifest = json.loads((self.root/image_manager.META/'library.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['items'],[])
        self.assertIn(item['sha256'],manifest['annotations'])
        self.assertIn(changed['sha256'],manifest['annotations'])

    def test_noop_and_touch_same_bytes_do_not_write_or_allocate_a_review(self):
        source = self.root / 'Image.png'
        source.write_bytes(picture('red'))
        self.refresh()
        before = self.private_bytes()
        revision = self.service.local_revision()['revision']
        with patch.object(image_manager,'_atomic_json',side_effect=AssertionError('no discovery write')):
            self.assertEqual(self.refresh()['status'],'noop')
            information = source.stat()
            os.utime(source, ns=(information.st_atime_ns,information.st_mtime_ns+10_000_000))
            with patch.object(image_manager.uuid,'uuid4',side_effect=AssertionError('no UUID for a touch')):
                self.assertEqual(self.refresh()['status'],'noop')
        self.assertEqual(self.private_bytes(),before)
        self.assertEqual(self.service.local_revision()['revision'],revision)

    def test_nonempty_review_is_preserved_until_user_finishes_it(self):
        (self.root/'Image.png').write_bytes(picture('red'))
        (self.root/'inbox'/'Other.png').write_bytes(picture('red'))
        self.refresh()
        plan = self.service.state()['plan']
        (self.root/'New.png').write_bytes(picture('blue'))
        before = self.private_bytes()
        with patch.object(image_manager,'_metadata',side_effect=AssertionError('preserve active review')):
            result = self.refresh()
        self.assertEqual((result['status'],result['reason']),('deferred','active_review'))
        self.assertEqual(self.private_bytes(),before)
        self.assertEqual(self.service.state()['plan']['id'],plan['id'])
        self.service.apply({'expectedRoot':str(self.root),'planId':plan['id'],
            'decisions':[{'id':candidate['id'],'action':'keep'} for candidate in plan['candidates']]})
        self.assertEqual(self.refresh()['status'],'noop')  # Explicit keep already refreshed the root index.
        self.assertEqual({item['path'] for item in self.service.state()['items']},{'Image.png','New.png'})

    def test_device_naming_and_prepared_delete_records_block_automatic_publication(self):
        (self.root/'Image.png').write_bytes(picture('red'))
        self.refresh()
        device = self.directory/'device'
        device.mkdir()
        (device/'Image.png').write_bytes(picture('blue'))
        self.service.configure({'root':str(self.root),'deviceRoot':str(device)})
        self.service.sync_device({'expectedRoot':str(self.root),'direction':'to-device'})
        (self.root/'New.png').write_bytes(picture('green'))
        before = self.private_bytes()
        self.assertEqual(self.refresh()['reason'],'active_review')
        self.assertEqual(self.private_bytes(),before)
        # A separate library exercises a real persistent naming preview.
        other = self.directory/'other'
        other.mkdir()
        service = ImageManagerService(self.directory/'other.json')
        service.configure({'root':str(other)})
        (other/'Image.png').write_bytes(picture('red'))
        item = service.scan({'expectedRoot':str(other)})['state']['items'][0]
        service.naming_plan({'expectedRoot':str(other),'entries':[{'path':item['path'],'sha256':item['sha256'],'assetType':'Logo'}]})
        observed = image_manager._discovery_inventory(other)
        self.assertEqual(service.safe_refresh_local({'expectedRoot':str(other),**observed})['reason'],'active_naming')
        # A crash can leave a prepared deletion without publishing lastDeletion.
        clean = self.directory/'prepared'
        clean.mkdir()
        service = ImageManagerService(self.directory/'prepared.json')
        service.configure({'root':str(clean)})
        (clean/'Image.png').write_bytes(picture('red'))
        record = clean/image_manager.META/'history'/('trash-'+'a'*32)/'operation.json'
        image_manager._atomic_json(record,{'requestId':'a'*32,'status':'prepared'})
        self.assertEqual(service.safe_refresh_local({'expectedRoot':str(clean),**image_manager._discovery_inventory(clean)})['reason'],'active_deletion')
        self.assertFalse((clean/image_manager.META/'library.json').exists())

    def test_incomplete_or_temporarily_unreadable_copy_never_removes_valid_index(self):
        source = self.root/'Image.png'
        source.write_bytes(picture('red'))
        self.refresh()
        (self.root/'inbox'/'Copy.png').write_bytes(picture('blue')[:30])
        before = self.private_bytes()
        self.assertEqual(self.refresh()['status'],'deferred')
        self.assertEqual(self.private_bytes(),before)
        self.assertEqual(len(self.service.state()['items']),1)
        (self.root/'inbox'/'Copy.png').unlink()
        information = source.stat()
        os.utime(source,ns=(information.st_atime_ns,information.st_mtime_ns+10_000_000))
        with patch.object(image_manager,'_metadata',side_effect=PermissionError('writer retains the file')):
            self.assertEqual(self.refresh()['status'],'deferred')
        self.assertEqual(self.private_bytes(),before)

    def test_stale_inventory_and_cancellation_after_decode_leave_all_metadata_untouched(self):
        source = self.root/'Image.png'
        source.write_bytes(picture('red'))
        observed = image_manager._discovery_inventory(self.root)
        source.write_bytes(picture('blue'))
        before = self.private_bytes()
        result = self.service.safe_refresh_local({'expectedRoot':str(self.root),**observed})
        self.assertEqual(result['reason'],'inventory_changed')
        stopped = []
        real_metadata = image_manager._metadata
        def decode(*args,**kwargs):
            value = real_metadata(*args,**kwargs)
            stopped.append(True)
            return value
        with patch.object(image_manager,'_metadata',side_effect=decode):
            result = self.refresh(cancelled=lambda:bool(stopped))
        self.assertEqual((result['status'],result['reason']),('deferred','stopped'))
        self.assertEqual(self.private_bytes(),before)
        self.assertEqual(self.refresh(cancelled=lambda:True)['reason'],'stopped')
        self.assertEqual(self.private_bytes(),before)

    def test_foreign_manifest_or_review_change_during_decode_is_preserved(self):
        for change in ('manifest','pointer'):
            with self.subTest(change=change):
                root = self.directory/change
                root.mkdir()
                service = ImageManagerService(self.directory/(change+'.json'))
                service.configure({'root':str(root)})
                (root/'Image.png').write_bytes(picture('red'))
                service.safe_refresh_local({'expectedRoot':str(root),**image_manager._discovery_inventory(root)})
                (root/'New.png').write_bytes(picture('blue'))
                manifest = root/image_manager.META/'library.json'
                pointer = root/image_manager.META/'latest-plan.json'
                captured=[]
                real_metadata = image_manager._metadata
                def decode(*args,**kwargs):
                    value=real_metadata(*args,**kwargs)
                    if not captured:
                        if change=='manifest':
                            foreign=json.loads(manifest.read_text(encoding='utf-8'))
                            foreign['foreignEdit']='preserve'
                            image_manager._atomic_json(manifest,foreign)
                            captured.append((manifest,manifest.read_bytes()))
                        else:
                            item=service._manifest(root)['items'][0]
                            plan={'id':'f'*32,'status':'review','direction':'inbox',
                                  'candidates':[{'id':'e'*32,'incoming':item,'existing':None,'matches':[]}]}
                            image_manager._atomic_json(root/image_manager.META/'plans'/('f'*32+'.json'),plan)
                            image_manager._atomic_json(pointer,{'planId':'f'*32})
                            captured.append((pointer,pointer.read_bytes()))
                    return value
                with patch.object(image_manager,'_metadata',side_effect=decode):
                    result=service.safe_refresh_local({'expectedRoot':str(root),**image_manager._discovery_inventory(root)})
                self.assertEqual(result['status'],'deferred')
                self.assertEqual(captured[0][0].read_bytes(),captured[0][1])

    def test_publication_failure_rolls_back_owned_manifest_but_never_foreign_metadata(self):
        for foreign in (False,True):
            with self.subTest(foreign=foreign):
                root=self.directory/('foreign' if foreign else 'owned')
                root.mkdir()
                service=ImageManagerService(self.directory/(root.name+'.json'))
                service.configure({'root':str(root)})
                (root/'Image.png').write_bytes(picture('red'))
                service.safe_refresh_local({'expectedRoot':str(root),**image_manager._discovery_inventory(root)})
                manifest=root/image_manager.META/'library.json'
                pointer=root/image_manager.META/'latest-plan.json'
                old_manifest,old_pointer=manifest.read_bytes(),pointer.read_bytes()
                (root/'New.png').write_bytes(picture('blue'))
                real_atomic=image_manager._atomic_json
                captured=[]
                def write(path,value):
                    if Path(path)==pointer or foreign and Path(path).parent.name=='plans':
                        if foreign and not captured:
                            changed=json.loads(manifest.read_text(encoding='utf-8'))
                            changed['foreignEdit']='after owned write'
                            real_atomic(manifest,changed)
                            captured.append(manifest.read_bytes())
                        raise PermissionError('final publication is unavailable')
                    return real_atomic(path,value)
                with patch.object(image_manager,'_atomic_json',side_effect=write):
                    result=service.safe_refresh_local({'expectedRoot':str(root),**image_manager._discovery_inventory(root)})
                self.assertEqual((result['status'],result['reason']),('deferred','publication_failed'))
                self.assertEqual(pointer.read_bytes(),old_pointer)
                self.assertEqual(manifest.read_bytes(),captured[0] if foreign else old_manifest)
                self.assertEqual((root/'Image.png').read_bytes(),picture('red'))
                self.assertEqual((root/'New.png').read_bytes(),picture('blue'))

    def test_shared_existing_original_is_not_interpreted_as_an_external_deletion(self):
        source=self.root/'Image.png'
        source.write_bytes(picture('red'))
        self.refresh()
        os.link(source,self.directory/'shared.png')
        before=self.private_bytes()
        self.assertEqual(self.refresh()['reason'],'unsafe_existing_image')
        self.assertEqual(self.private_bytes(),before)
        self.assertEqual(len(self.service.state()['items']),1)

    def test_revision_is_cheap_and_state_refuses_a_mislabeled_concurrent_snapshot(self):
        (self.root/'Image.png').write_bytes(picture('red'))
        self.refresh()
        with (patch.object(image_manager,'_metadata',side_effect=AssertionError('no photo decode')),
             patch.object(image_manager,'_sha',side_effect=AssertionError('no photo hash')),
             patch.object(image_manager.os,'scandir',side_effect=AssertionError('no recursive inventory'))):
            revision=self.service.local_revision(str(self.root))['revision']
        self.assertEqual(self.service.state()['localRevision'],revision)
        manifest=self.root/image_manager.META/'library.json'
        real_manifest=self.service._manifest
        touched=[]
        def read(root):
            value=real_manifest(root)
            if not touched:
                changed=json.loads(json.dumps(value))
                changed['foreignEdit']='during state'
                image_manager._atomic_json(manifest,changed)
                touched.append(True)
            return value
        with patch.object(self.service,'_manifest',side_effect=read):
            with self.assertRaises(ImageManagerError):self.service.state()


if __name__ == '__main__':
    unittest.main(verbosity=2)
