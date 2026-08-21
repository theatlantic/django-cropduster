import os
import re

from django import forms
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase, override_settings

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

    def test_subclass_media_appends_after_the_bundle(self):
        class Subclass(CropDusterWidget):
            class Media:
                js = ('project/extra.js',)

        self.assertEqual(
            list(Subclass(field=None).media._js),
            ['cropduster/dist/cropduster.js', 'project/extra.js'])

    def test_production_media_renders_an_ordinary_script(self):
        self.assertEqual(widget().media.render_js(), [
            '<script src="/static/cropduster/dist/cropduster.js"></script>'])

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

    def test_the_old_popup_assets_are_removed(self):
        for name in (
                'js/upload.js', 'js/jquery.jcrop.js', 'js/jquery.jcrop.min.js',
                'js/jquery.form.js', 'js/jquery.class.js', 'js/json2.js',
                'css/upload.css', 'css/jquery.jcrop.css', 'css/jcrop.gif',
                'img/arrows.png', 'img/progressbar.gif',
                'img/cropduster_icon_upload_hover.png',
                'img/cropduster_icon_upload_select.png'):
            path = os.path.join(STATIC_DIR, *name.split('/'))
            self.assertFalse(os.path.exists(path), name)

    def test_legacy_paths_still_used_by_compatibility_code_remain(self):
        for name in ('css/cropduster.css', 'img/blank.gif'):
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


@override_settings(
    DEBUG=True,
    CROPDUSTER_DEV_SERVER_URL='http://localhost:5173/')
class DevServerPageTest(TestCase):

    def setUp(self):
        super().setUp()
        user = User.objects.create_superuser(
            'test', 'test@test.com', 'password')
        self.client = Client()
        self.client.force_login(user)

    def page(self):
        response = self.client.get('/admin/tests/author/add/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode('utf-8')

    def test_dev_scripts_reach_the_admin_page_as_modules(self):
        html = self.page()
        for src in (
                'http://localhost:5173/@vite/client',
                'http://localhost:5173/src/entry.tsx'):
            self.assertIn(
                '<script type="module" src="%s"></script>' % src, html)
            self.assertNotIn('<script src="%s"></script>' % src, html)

    def test_the_react_refresh_preamble_precedes_the_entry(self):
        # Without the preamble, @vitejs/plugin-react raises "can't detect
        # preamble" from every transformed module and the entry never runs.
        html = self.page()
        self.assertIn(
            "import RefreshRuntime from 'http://localhost:5173/@react-refresh'",
            html)
        self.assertIn('window.__vite_plugin_react_preamble_installed__', html)
        self.assertLess(
            html.index('@react-refresh'),
            html.index('src/entry.tsx'))

    def test_the_built_bundle_is_not_loaded_with_the_dev_server(self):
        html = self.page()
        self.assertNotIn('cropduster/dist/cropduster.js', html)
        self.assertNotIn('cropduster/dist/cropduster.css', html)
