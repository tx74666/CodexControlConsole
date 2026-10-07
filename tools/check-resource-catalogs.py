"""Catalogue adapter regressions; all responses are injected, no network or DB."""
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_catalogs import CATALOG_PROVIDERS, search_catalog


KENNEY_FORM = '<input type="search" name="search" value="car">'
KENNEY_CAR = '''<div class='asset'>
  <a href='https://kenney.nl/assets/toy-car-kit'><div class='cover'
    style='background-image:url("https://kenney.nl/media/pages/assets/toy-car-kit/hash/preview-400x.png")'></div></a>
  <h2><a href='https://kenney.nl/assets/toy-car-kit'>Toy Car Kit</a></h2>
  <span><a href='https://kenney.nl/assets/category:3D?search=car'>3D</a></span>
</div>'''
KENNEY_VFX = '''<div class='asset'>
  <div class='cover' style='background-image:url("https://kenney.nl/media/pages/assets/particle-pack/hash/preview-400x.png")'></div>
  <h2><a href='/assets/particle-pack'>Particle Pack</a></h2>
  <a href='/assets/category:2D'>2D</a><a href='/assets/series:VFX'>VFX</a>
</div>'''
KENNEY_TEXTURE = '''<div class='asset'>
  <h2><a href='/assets/retro-textures'>Retro Textures</a></h2>
  <a href='/assets/category:Textures'>Textures</a>
</div>'''
KENNEY_OTHER = '''<div class='asset'>
  <h2><a href='/assets/input-prompts'>Input Prompts</a></h2>
  <a href='/assets/category:2D'>2D</a>
</div>'''
OGA_FORM = '''<input id="edit-keys" name="keys" value="car">
<select name="field_art_type_tid[]"><option value="10" selected="selected">3D Art</option></select>'''
OGA_CAR = '''<div class="views-row art-previews-inline">
  <div class="field field-name-title"><span class="art-preview-title"><a href="/content/car-0">Car &amp; Wheels</a></span></div>
  <div class="field field-name-field-art-preview"><a href="/content/car-0">
    <img src="https://opengameart.org/sites/default/files/styles/thumbnail/public/car_image_1.png" alt="Preview"></a></div>
</div>'''


class CatalogueTests(unittest.TestCase):
    def search(self, provider, kind, payload, query='car', count=12):
        calls = []

        def fetch(url):
            calls.append(url)
            return payload

        result = search_catalog(provider, kind, query, count, fetch_json=fetch, fetch_text=fetch)
        self.assertEqual(len(calls), 1, 'No result or image URL may trigger another fetch.')
        return result, urlsplit(calls[0]), parse_qs(urlsplit(calls[0]).query)

    def test_provider_modes_and_types_are_explicit(self):
        descriptors = {p['id']: p for p in CATALOG_PROVIDERS}
        self.assertEqual(set(descriptors), {'ambientcg', 'kenney', 'opengameart'})
        for provider in descriptors.values():
            self.assertEqual(provider['mode'], 'api')
            self.assertIn(provider['defaultKind'], provider['kinds'])
        self.assertIn('vfx', descriptors['kenney']['kinds'])
        self.assertNotIn('vfx', descriptors['opengameart']['kinds'])

    def test_ambient_v3_real_shape_and_thumbnail(self):
        rows, endpoint, params = self.search('ambientcg', 'texture', {'assets': [{
            'id': 'Ground111', 'type': 'material', 'title': 'Ground 111',
            'url': 'https://ambientcg.com/a/Ground111', 'shortDescription': '',
            'thumbnails': {'512-PNG': 'https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/512-PNG/Ground111.png'}}]})
        self.assertEqual((endpoint.scheme, endpoint.netloc, endpoint.path), ('https', 'ambientcg.com', '/api/v3/assets'))
        self.assertEqual(params['type'], ['material'])
        self.assertEqual(params['q'], ['car'])
        self.assertIn('thumbnails', params['include'][0])
        self.assertEqual(rows[0]['name'], 'Ground 111')
        self.assertTrue(rows[0]['previewUrl'].endswith('/Ground111.png'))
        self.assertEqual(rows[0]['license'], 'CC0')
        self.assertEqual(rows[0]['kind'], 'texture')

    def test_ambient_each_type_uses_v3_type(self):
        for kind, api_type in [('model', '3d-model'), ('texture', 'material'), ('hdri', 'hdri')]:
            with self.subTest(kind=kind):
                _, _, params = self.search('ambientcg', kind, {'assets': []})
                self.assertEqual(params['type'], [api_type])

    def test_ambient_wrong_type_not_mislabeled(self):
        rows, _, _ = self.search('ambientcg', 'model', {'assets': [{
            'id': 'Wood096', 'type': 'material', 'title': 'Wood 096', 'url': 'https://ambientcg.com/a/Wood096'}]})
        self.assertEqual(rows[0]['url'], '')  # Shared candidate validator reports this rejected row.
        self.assertNotEqual(rows[0]['kind'], 'model')

    def test_ambient_wrong_shape_raises(self):
        for payload in ({'foundAssets': []}, {'assets': {}}, [], None):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.search('ambientcg', 'texture', payload)

    def test_ambient_arbitrary_urls_are_never_followed(self):
        rows, endpoint, _ = self.search('ambientcg', 'model', {'assets': [{
            'id': '3DApple002', 'type': '3d-model', 'title': 'Apple',
            'url': 'https://attacker.example/apple',
            'thumbnails': {'512-PNG': 'http://127.0.0.1/private'}}]})
        self.assertEqual(endpoint.netloc, 'ambientcg.com')
        self.assertEqual(rows[0]['url'], '')
        self.assertEqual(rows[0]['previewUrl'], '')

    def test_kenney_model_card_and_fixed_filter(self):
        rows, endpoint, params = self.search('kenney', 'model', KENNEY_FORM + KENNEY_CAR)
        self.assertEqual((endpoint.netloc, endpoint.path), ('kenney.nl', '/assets/category:3D'))
        self.assertEqual(params['search'], ['car'])
        self.assertEqual(rows[0]['name'], 'Toy Car Kit')
        self.assertEqual(rows[0]['url'], 'https://kenney.nl/assets/toy-car-kit')
        self.assertTrue(rows[0]['previewUrl'].endswith('/preview-400x.png'))
        self.assertEqual((rows[0]['kind'], rows[0]['license']), ('model', 'CC0'))

    def test_kenney_vfx_and_texture_use_real_filters(self):
        for kind, fixture, path in [('vfx', KENNEY_VFX, '/assets/series:VFX'),
                                    ('texture', KENNEY_TEXTURE, '/assets/category:Textures')]:
            with self.subTest(kind=kind):
                rows, endpoint, _ = self.search('kenney', kind, KENNEY_FORM + fixture)
                self.assertEqual(endpoint.path, path)
                self.assertEqual(rows[0]['kind'], kind)

    def test_kenney_unfiltered_catalogue_preserves_actual_types(self):
        rows, endpoint, _ = self.search('kenney', 'other', KENNEY_FORM + KENNEY_CAR + KENNEY_VFX + KENNEY_OTHER)
        self.assertEqual(endpoint.path, '/assets')
        self.assertEqual([r['kind'] for r in rows], ['model', 'vfx', 'other'])

    def test_kenney_2d_is_not_automatically_vfx(self):
        rows, _, _ = self.search('kenney', 'vfx', KENNEY_FORM + KENNEY_OTHER)
        self.assertEqual(rows[0]['url'], '')
        self.assertNotEqual(rows[0]['kind'], 'vfx')

    def test_kenney_invalid_card_and_nonofficial_links(self):
        fixture = KENNEY_FORM + KENNEY_CAR.replace('https://kenney.nl/assets/toy-car-kit', '//attacker.example/assets/toy-car-kit')
        fixture += '<div class="asset"><h2>Missing link</h2></div>'
        rows, _, _ = self.search('kenney', 'model', fixture)
        self.assertEqual([r['url'] for r in rows], ['', ''])

    def test_oga_advanced_filter_and_preview(self):
        rows, endpoint, params = self.search('opengameart', 'model', '<div id="right">' + OGA_FORM + OGA_CAR + '</div>')
        self.assertEqual((endpoint.netloc, endpoint.path), ('opengameart.org', '/art-search-advanced'))
        self.assertEqual(params['field_art_type_tid[]'], ['10'])
        self.assertEqual(params['items_per_page'], ['24'])
        self.assertEqual(rows[0]['name'], 'Car & Wheels')
        self.assertEqual(rows[0]['url'], 'https://opengameart.org/content/car-0')
        self.assertTrue(rows[0]['previewUrl'].endswith('car_image_1.png'))
        self.assertEqual(rows[0]['license'], '待核對（見來源頁）')
        self.assertEqual(rows[0]['kind'], 'model')

    def test_oga_other_and_texture_are_truthfully_typed(self):
        for kind, type_id in [('texture', '14'), ('other', '9')]:
            with self.subTest(kind=kind):
                rows, _, params = self.search('opengameart', kind, '<div id="right">' + OGA_FORM.replace('value="10"', 'value="' + type_id + '"') + OGA_CAR + '</div>')
                self.assertEqual(params['field_art_type_tid[]'], [type_id])
                self.assertEqual(rows[0]['kind'], kind)
                self.assertNotEqual(rows[0]['license'], 'CC0')

    def test_oga_sidebar_is_not_a_search_result(self):
        fixture = OGA_CAR + '<div id="right">' + OGA_FORM + '</div>'
        rows, _, _ = self.search('opengameart', 'model', fixture)
        self.assertEqual(rows, [])

    def test_oga_real_form_sits_outside_results_container(self):
        fixture = '<div id="filters">' + OGA_FORM + '</div><div id="right">' + OGA_CAR + '</div>'
        rows, _, _ = self.search('opengameart', 'model', fixture)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Car & Wheels')
        self.assertEqual(rows[0]['kind'], 'model')

    def test_oga_preserves_uppercase_preview_extension(self):
        fixture = OGA_FORM + '<div id="right">' + OGA_CAR.replace('car_image_1.png', 'tex-res-prev_2.JPG') + '</div>'
        rows, _, _ = self.search('opengameart', 'model', fixture)
        self.assertTrue(rows[0]['previewUrl'].endswith('/tex-res-prev_2.JPG'))

    def test_oga_unconfirmed_filter_is_not_mislabeled(self):
        for form in (OGA_FORM.replace('value="10"', 'value="9"'), OGA_FORM.replace(' selected="selected"', '')):
            with self.subTest(form=form), self.assertRaises(ValueError):
                self.search('opengameart', 'model', '<div id="right">' + form + OGA_CAR + '</div>')

    def test_oga_invalid_source_or_image_is_not_requested(self):
        fixture = '<div id="right">' + OGA_FORM + OGA_CAR.replace('/content/car-0', 'https://attacker.example/car').replace(
            'https://opengameart.org/sites/default/files/styles/thumbnail/public/car_image_1.png', 'https://127.0.0.1/private.png') + '</div>'
        rows, _, _ = self.search('opengameart', 'model', fixture)
        self.assertEqual(rows[0]['url'], '')
        self.assertEqual(rows[0]['previewUrl'], '')

    def test_html_structural_errors_are_visible(self):
        for provider in ('kenney', 'opengameart'):
            for payload in ('<html><body>Unavailable</body></html>', None):
                with self.subTest(provider=provider, payload=payload), self.assertRaises(ValueError):
                    self.search(provider, 'model', payload)
        error = '<div id="right">' + OGA_FORM + '<div class="messages error">Illegal choice</div></div>'
        with self.assertRaises(ValueError):
            self.search('opengameart', 'model', error)

    def test_empty_html_catalogues_are_valid(self):
        for provider, html in [('kenney', KENNEY_FORM), ('opengameart', '<div id="right">' + OGA_FORM + '</div>')]:
            with self.subTest(provider=provider):
                rows, _, _ = self.search(provider, 'model', html)
                self.assertEqual(rows, [])

    def test_result_count_is_bounded(self):
        rows, _, _ = self.search('kenney', 'model', KENNEY_FORM + KENNEY_CAR * 5, count=2)
        self.assertEqual(len(rows), 2)

    def test_query_cannot_change_destination(self):
        query = 'car&url=https://127.0.0.1/&type=other'
        _, endpoint, params = self.search('ambientcg', 'model', {'assets': []}, query=query)
        self.assertEqual(endpoint.netloc, 'ambientcg.com')
        self.assertEqual(params['q'], [query])
        self.assertEqual(params['type'], ['3d-model'])

    def test_inputs_are_rejected_before_fetch(self):
        def forbidden(url):
            self.fail('Invalid input caused a request: ' + url)
        for provider, kind, query, count in [('unknown', 'model', 'car', 12),
                                            ('opengameart', 'vfx', 'fire', 12),
                                            ('kenney', 'model', '', 12),
                                            ('kenney', 'model', 'car\n', 12),
                                            ('kenney', 'model', 'car', True),
                                            ('kenney', 'model', 'car', 25)]:
            with self.subTest(provider=provider, kind=kind, query=query, count=count), self.assertRaises(ValueError):
                search_catalog(provider, kind, query, count, fetch_json=forbidden, fetch_text=forbidden)

    def test_network_exception_propagates_without_retry(self):
        def fail(url):
            raise OSError('Network unavailable')
        with self.assertRaisesRegex(OSError, 'Network unavailable'):
            search_catalog('kenney', 'model', 'car', 12, fetch_json=fail, fetch_text=fail)


if __name__ == '__main__':
    unittest.main()
