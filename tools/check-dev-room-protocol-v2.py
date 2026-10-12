"""Independent BE32 framing vectors shared with the C# Editor bridge.

This verifies three source hashes and emits a non-executing JSON contract fixture;
it is not a Unity compilation or an Editor write receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unity_dev_room_documents as source


def text(value):
    raw = str(value or '').encode('utf-8')
    return struct.pack('>I', len(raw)) + raw


def vectors():
    image = {'guid': '17f6c37f25f1f7a4d97b03bb8f2ed61a', 'fileID': 2800000, 'type': 3,
             'resourcePath': '', 'assetPath': 'Assets/Art/Images/UI/DevsRealm/示意图.png',
             'sha256': 'a' * 64, 'metaRevision': 'b' * 64, 'stagingName': ''}
    none = {'guid': '', 'fileID': 0, 'type': 0, 'resourcePath': '', 'assetPath': '',
            'sha256': '', 'metaRevision': '', 'stagingName': ''}
    document = {'id': 'device-editor-example', 'guid': 'fa74d2fe4a6e0c24599e9a4364a206a5',
                'localFileId': 4643311352111938372, 'category': 0, 'order': 1,
                'title': '中文 / Content', 'summary': 'Exact whitespace  \n', 'sections': [
                    {'index': 0, 'title': '一', 'body': '第一行\nSecond line  ', 'imageCaption': '示意图 / caption', 'image': image},
                    {'index': 1, 'title': '二', 'body': 'No image', 'imageCaption': '', 'image': none}]}
    sections = document['sections']; count = struct.pack('>I', len(sections))
    content = text(document['title']) + text(document['summary']) + count
    for section in sections:
        content += b''.join(text(value) for value in (section['title'], section['body'], section['imageCaption'],
                                  section['image']['resourcePath'], section['image']['sha256']))
    structure = b''.join(text(value) for value in (document['id'], document['guid'], document['localFileId'],
                                                 str(document['category']), str(document['order']))) + count
    for section in sections:
        structure += text(str(section['index'])) + text('section')
    images = count
    for section in sections:
        image = section['image']
        images += b''.join(text(value) for value in (image['guid'], str(image['fileID']), str(image['type']),
                                                   image['resourcePath'], image['assetPath'], image['sha256'], image['metaRevision']))
    expected = {name: hashlib.sha256(raw).hexdigest() for name, raw in
                (('contentRevision', content), ('structureRevision', structure), ('mediaRevision', images))}
    observed = {'contentRevision': source.document_content_revision(document),
                'structureRevision': source.document_structure_revision(document),
                'mediaRevision': source.document_media_revision(document)}
    assert expected == observed, (expected, observed)
    # A document identity is a signed Int64, framed as its invariant decimal
    # string. Use the minimum value to catch sign removal or float conversion.
    negative_document = dict(document, localFileId=-(2 ** 63))
    negative_structure = b''.join(text(value) for value in (
        negative_document['id'], negative_document['guid'], '-9223372036854775808',
        str(negative_document['category']), str(negative_document['order']))) + count
    for section in sections:
        negative_structure += text(str(section['index'])) + text('section')
    negative_sha = hashlib.sha256(negative_structure).hexdigest()
    assert source.document_structure_revision(negative_document) == negative_sha
    assert negative_sha != expected['structureRevision']
    cs = Path(__file__).resolve().parents[1].joinpath('unity', 'Editor', 'DevRoomConsoleBridge.cs').read_text(encoding='utf-8-sig')
    assert 'WriteText(stream, Number(localId))' in cs
    assert 'WriteText(stream, section.imageCaption); WriteText(stream, section.image?.resourcePath); WriteText(stream, section.image?.sha256)' in cs
    assert 'WriteText(stream, image?.sha256); WriteText(stream, image?.metaRevision)' in cs
    assert 'public long localFileId' in cs and 'public long fileID' in cs
    assert 'static string Number(long value) => value.ToString(CultureInfo.InvariantCulture);' in cs
    assert 'request.document.localFileId != 0' in cs
    staged = {'section': 0, 'imageCaption': 'Replace pixels', 'guid': '', 'fileID': 0, 'type': 3,
              'sha256': 'c' * 64, 'stagingName': 'c' * 64 + '.png',
              'resourcePath': 'UI/DevsRealm/ConsoleMedia/' + 'c' * 64,
              'assetPath': 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + 'c' * 64 + '.png'}
    planned = source.validate_image_edit(staged, sections[0])
    assert planned['assetPath'] == 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + planned['stagingName']
    assert 'string path = MediaAssetRoot + "/" + image.stagingName' in cs
    assert 'Need(image.assetPath == path && image.resourcePath ==' in cs
    legacy = dict(staged, assetPath='')
    assert source.validate_image_edit(legacy, sections[0])['assetPath'] == planned['assetPath']
    return {'schemaVersion': 2, 'purpose': 'Non-executing C#/Python framing vector', 'document': document,
            'negativeInt64Vector': {'document': negative_document, 'structureRevision': negative_sha},
            'expected': expected, 'framing': 'UTF-8 BE32 length prefixes; BE32 section count; exact whitespace'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--write-fixture')
    args = parser.parse_args(); result = vectors()
    if args.write_fixture:
        path = Path(args.write_fixture); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'hashes': result['expected'], 'longFileId': result['document']['localFileId'],
                      'negativeLocalFileId': result['negativeInt64Vector']['document']['localFileId'],
                      'negativeStructureRevision': result['negativeInt64Vector']['structureRevision']}))
