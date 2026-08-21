import os
import re

from django import forms
from django.test import SimpleTestCase, override_settings

from cropduster.forms import CropDusterWidget, ModuleScript
from tests.models import Author


STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'cropduster', 'static', 'cropduster')


def widget():
    return Author._meta.get_field('headshot').formfield().widget


class WidgetMediaTest(SimpleTestCase):

    def test_production_media_is_the_built_bundle(self):
        media = widget().media
        self.assertEqual(
            list(media._js), ['cropduster/dist/cropduster.js'])
        self.assertEqual(
            dict(media._css),
            {'all': ['cropduster/dist/cropduster.css']})

    def test_host_page_no_longer_loads_the_old_widget_scripts(self):
        paths = list(widget().media._js)
        self.assertNotIn('admin/js/jquery.init.js', paths)
        self.assertNotIn('cropduster/js/jsrender.js', paths)
        self.assertNotIn('cropduster/js/cropduster.js', paths)

    @override_settings(
        DEBUG=True,
        CROPDUSTER_DEV_SERVER_URL='http://localhost:5173/')
    def test_dev_server_media_uses_module_scripts(self):
        media = widget().media
        self.assertEqual(list(media._js), [
            'http://localhost:5173/@react-refresh',
            'http://localhost:5173/@vite/client',
            'http://localhost:5173/src/entry.tsx',
        ])
        self.assertEqual(media.render_js(), [
            '<script type="module">'
            "import RefreshRuntime from 'http://localhost:5173/@react-refresh';"
            'RefreshRuntime.injectIntoGlobalHook(window);'
            'window.$RefreshReg$ = () => {};'
            'window.$RefreshSig$ = () => (type) => type;'
            'window.__vite_plugin_react_preamble_installed__ = true;'
            '</script>',
            '<script type="module" src="http://localhost:5173/@vite/client"></script>',
            '<script type="module" src="http://localhost:5173/src/entry.tsx"></script>',
        ])
        self.assertEqual(dict(media._css), {})

    @override_settings(
        DEBUG=False,
        CROPDUSTER_DEV_SERVER_URL='http://localhost:5173/')
    def test_dev_server_setting_is_ignored_without_debug(self):
        self.assertEqual(
            list(widget().media._js), ['cropduster/dist/cropduster.js'])

    def test_module_script_survives_a_media_merge(self):
        merged = (
            forms.Media(js=['admin/js/core.js'])
            + forms.Media(js=[ModuleScript('/@vite/client')]))
        self.assertEqual(merged.render_js(), [
            '<script src="/static/admin/js/core.js"></script>',
            '<script type="module" src="/@vite/client"></script>',
        ])


class LegacyWidgetShimTest(SimpleTestCase):

    def read(self, name):
        with open(os.path.join(STATIC_DIR, 'js', name)) as source:
            return source.read()

    def test_cropduster_js_warns_and_does_nothing(self):
        source = self.read('cropduster.js')
        self.assertIn('console.warn', source)
        self.assertIn('cropduster/dist/cropduster.js', source)
        self.assertNotIn('CropDuster.complete', source)

    def test_jsrender_is_empty(self):
        self.assertEqual(self.read('jsrender.js').strip(), '')

    def test_the_old_popup_assets_are_still_present(self):
        for name in (
                'js/upload.js', 'js/jquery.jcrop.js', 'js/jquery.form.js',
                'js/json2.js', 'css/upload.css', 'css/jquery.jcrop.css'):
            path = os.path.join(STATIC_DIR, *name.split('/'))
            self.assertTrue(os.path.exists(path), name)
            self.assertGreater(os.path.getsize(path), 0, name)

    def test_crop_form_no_longer_loads_popup_assets(self):
        from cropduster.views.forms import CropForm

        self.assertEqual(list(CropForm().media._js), [])
        self.assertEqual(dict(CropForm().media._css), {})


class WidgetLicenseTest(SimpleTestCase):

    def notices(self):
        with open(os.path.join(STATIC_DIR, 'dist', 'LICENSES.txt')) as notices:
            return notices.read()

    def test_reachable_packages_have_native_vite_notices(self):
        listed = re.findall(r'^## (\S+) - (\S+) \((\S+)\)$', self.notices(), re.M)
        self.assertEqual(
            sorted(name for name, _version, _license in listed),
            ['react', 'react-dom', 'react-image-crop', 'scheduler'])

    def test_each_notice_contains_its_license_text(self):
        notices = self.notices()
        self.assertEqual(
            len(re.findall(r'(?im)^copyright \(c\)', notices)), 4)
        self.assertEqual(len(re.findall(r'(?im)^permission ', notices)), 4)
