"""Small original-byte and replacement-safety checks using disposable images."""
import io
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
