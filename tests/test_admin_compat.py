"""
Browser tests for the APIs and markup used by downstream admin code.

Downstream admin scripts call ``window.CropDuster``, update formset inputs
through jQuery, retain the sizes array by reference, and listen for
``cropduster:update``. Each test below describes the downstream usage and
asserts the selector, method, event, or mutation it depends on.

These tests use the built bundle and the admin's actual jQuery instances,
including grappelli's separate copy when it is installed.
"""

import json
import os

from django.test import override_settings
from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

import cropduster
from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author


TEST_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'img.jpg')


#: A crop response returned by ``/cropduster/crop/`` and forwarded to
#: ``window.opener.CropDuster.complete``.
CROP_PAYLOAD = {
    "crop": {
        "image_id": 41,
        "orig_image": "author/headshots/2026/09/abc/original.jpg",
        "orig_w": 674,
        "orig_h": 800,
        "thumbs": {
            "main": {
                "id": 91,
                "name": "main",
                "width": 220,
                "height": 180,
                "url": "/media/author/headshots/2026/09/abc/main.jpg",
            },
            "thumb": {
                "id": 92,
                "name": "thumb",
                "width": 110,
                "height": 90,
                "url": "/media/author/headshots/2026/09/abc/thumb.jpg",
            },
        },
    },
    "thumbs": [],
    "initial": True,
    "preview_url": "/media/author/headshots/2026/09/abc/_preview.jpg",
    "preview_w": 421,
    "preview_h": 500,
}


class TestAdminCompat(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

    root_urlconf = 'tests.urls'

    @class_property
    def available_apps(cls):
        apps = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.messages',
            'django.contrib.sessions',
            'django.contrib.sites',
            'django.contrib.staticfiles',
            'django.contrib.admin',
            'generic_plus',
            'cropduster',
            'tests',
            'tests.standalone',
            'selenosis',
        ]
        if cls.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    def js(self, script, *args):
        return self.selenium.execute_script(script, *args)

    def complete(self, prefix, payload=None):
        """``CropDuster.complete(prefix, data)``, as the popup calls it."""
        self.js(
            "window.CropDuster.complete(arguments[0], JSON.parse(arguments[1]));",
            prefix, json.dumps(payload if payload is not None else CROP_PAYLOAD))

    # -- the DOM ------------------------------------------------------------

    def test_dom_selectors(self):
        """
        The selectors used by thirteen stylesheets and django-nested-admin.

        django-nested-admin uses the wrapper class and id when it renames a row
        or cascades a deletion. The remaining classes and attributes are used
        by downstream stylesheets. React renders inside the server-provided
        containers instead of replacing them, so these selectors remain after
        the widget mounts.
        """
        self.load_admin(Author)

        found = self.js("""
            var root = document.getElementById('headshot-group');
            var q = function (selector) { return !!root.querySelector(selector); };
            return {
                wrapper: ['module', 'cropduster-form', 'nested-inline-form'].every(
                    function (name) { return root.classList.contains(name); }),
                mediaUrl: root.getAttribute('data-media-url'),
                idInput: q('input[type=hidden][name="headshot-0-id"]'),
                dataField: q('input.cropduster-data-field.cropduster-text-field'
                             + '[name="headshot"][data-sizes][data-preview-url]'
                             + '[data-preview-w][data-preview-h][data-upload-to]'),
                element: q('cropduster-widget[data-config]'),
                anchor: q('a.cropduster-customfield.cropduster-upload-form'
                          + '[data-cropduster-url]'),
                button: q('a.cropduster-customfield > div.cropduster-button'),
                images: q('div.manual_images.cropduster-image-group'
                          + ' > div.thumbs.cropduster-images'),
                thumbsSelect: q('select[name="headshot-0-thumbs"]'),
                management: ['TOTAL_FORMS', 'INITIAL_FORMS', 'MIN_NUM_FORMS',
                             'MAX_NUM_FORMS'].every(function (key) {
                    return q('input[name="headshot-' + key + '"]');
                }),
                order: Array.prototype.filter.call(root.children, function (el) {
                    return el.matches('.cropduster-data-field,cropduster-widget,'
                                      + '.cropduster-customfield');
                }).map(function (el) { return el.tagName.toLowerCase(); })
            };
        """)

        self.assertEqual(found.pop('order'), ['input', 'cropduster-widget', 'a'])
        self.assertEqual(found.pop('mediaUrl'), '/media/')
        self.assertEqual(found, {key: True for key in found}, found)

    def test_data_field_is_present_but_never_seen(self):
        """
        The data field is in the DOM, with its attributes, and invisible.

        It holds a storage path, and thirteen downstream stylesheets size
        ``.cropduster-form input[type=text]`` for controls that are meant to be
        visible. Showing this field would add an editable path input to
        downstream admin embeds and inline rows. Removing it would also
        break prefix derivation and ``CropDuster.complete()``, which writes to
        the field by id.
        """
        from selenium.webdriver.common.by import By

        self.load_admin(Author)

        field = self.selenium.find_element(
            By.CSS_SELECTOR,
            '#headshot-group input.cropduster-data-field.cropduster-text-field')

        self.assertFalse(field.is_displayed())
        self.assertEqual(field.get_attribute('name'), 'headshot')
        self.assertEqual(field.get_attribute('id'), 'id_headshot')

    def test_globals_are_installed(self):
        """
        ``window.CropDuster`` and its seven methods.

        Downstream admin scripts call all of these after document ready.
        """
        self.load_admin(Author)

        self.assertEqual(self.js("""
            var api = window.CropDuster;
            if (!api) { return null; }
            var out = {mediaUrl: typeof api.mediaUrl, value: api.mediaUrl};
            ['show', 'complete', 'setThumbnails', 'createThumbnails',
             'registerInput', 'removeSize', 'restoreSize'].forEach(function (name) {
                out[name] = typeof api[name];
            });
            return out;
        """), {
            'mediaUrl': 'string',
            'value': '/media/',
            'show': 'function',
            'complete': 'function',
            'setThumbnails': 'function',
            'createThumbnails': 'function',
            'registerInput': 'function',
            'removeSize': 'function',
            'restoreSize': 'function',
        })

    # -- writing --------------------------------------------------------------

    def test_set_thumbnails_option_attributes(self):
        """
        ``setThumbnails`` emits the attributes the server widget emits.

        One downstream script writes the select this way, and another reads
        the rendition from these exact option attributes.
        """
        self.load_admin(Author)

        self.js("""
            window.CropDuster.setThumbnails('headshot', JSON.parse(arguments[0]));
        """, json.dumps(CROP_PAYLOAD['crop']['thumbs']))

        self.assertEqual(self.js("""
            return Array.prototype.map.call(
                document.querySelectorAll('#id_headshot-0-thumbs option'),
                function (option) {
                    return {
                        value: option.getAttribute('value'),
                        width: option.getAttribute('data-width'),
                        height: option.getAttribute('data-height'),
                        url: option.getAttribute('data-url'),
                        tmp: option.getAttribute('data-tmp-file'),
                        selected: option.getAttribute('selected'),
                        label: option.innerHTML
                    };
                });
        """), [
            {'value': '91', 'width': '220', 'height': '180',
             'url': '/media/author/headshots/2026/09/abc/main.jpg',
             'tmp': 'true', 'selected': 'selected', 'label': 'main'},
            {'value': '92', 'width': '110', 'height': '90',
             'url': '/media/author/headshots/2026/09/abc/thumb.jpg',
             'tmp': 'true', 'selected': 'selected', 'label': 'thumb'},
        ])

    def test_complete_writes_the_whole_set(self):
        """
        ``complete`` leaves the formset exactly as 4.x left it.

        A downstream script calls this and then writes ``-0-attribution``
        itself. The remaining formset values and preview must therefore be
        complete before this method returns.
        """
        self.load_admin(Author)

        self.complete('headshot')

        state = self.js("""
            var value = function (id) {
                var el = document.getElementById(id);
                return el ? el.value : null;
            };
            var images = document.querySelector(
                '#headshot-group .cropduster-images');
            var img = images && images.shadowRoot && images.shadowRoot
                .querySelector('a.cropduster-image img');
            return {
                id: value('id_headshot-0-id'),
                image: value('id_headshot-0-image'),
                field: value('id_headshot'),
                total: value('id_headshot-TOTAL_FORMS'),
                initial: value('id_headshot-INITIAL_FORMS'),
                thumbs: Array.prototype.map.call(
                    document.querySelectorAll('#id_headshot-0-thumbs option:checked'),
                    function (option) { return option.value; }),
                previewSrc: img && img.getAttribute('src'),
                previewClass: img && img.getAttribute('class'),
                previewSize: img && [img.getAttribute('width'),
                                     img.getAttribute('height')]
            };
        """)

        self.assertEqual(state, {
            'id': '41',
            'image': 'author/headshots/2026/09/abc/original.jpg',
            'field': 'author/headshots/2026/09/abc/original.jpg',
            'total': '1',
            # Zeroed because the row had no image id before the write.
            'initial': '0',
            'thumbs': ['91', '92'],
            'previewSrc': '/media/author/headshots/2026/09/abc/_preview.jpg',
            'previewClass': 'cropduster-image-thumb cropduster-image-thumb-preview',
            'previewSize': ['421', '500'],
        })

    def test_update_event_keeps_its_jquery_signature(self):
        """
        ``cropduster:update`` fires on every jQuery instance, positionally.

        Downstream scripts bind ``$(document).on('cropduster:update',
        function (e, prefix, data) {...})``. grappelli ships its own copy of
        jQuery, and the downstream event bridge does not forward this event,
        so a handler bound on the copy we skipped never runs.
        """
        self.load_admin(Author)

        instances = self.js("""
            window.__updates = [];
            var seen = [];
            [['django', window.django && window.django.jQuery],
             ['grp', window.grp && window.grp.jQuery],
             ['global', window.jQuery]].forEach(function (entry) {
                var name = entry[0], $ = entry[1];
                if (typeof $ != 'function' || !$.fn || !$.fn.jquery) { return; }
                if (seen.indexOf($) != -1) { return; }
                seen.push($);
                $(document).on('cropduster:update', function (e, prefix, data) {
                    window.__updates.push({
                        instance: name, prefix: prefix,
                        image: data && data.crop && data.crop.image_id,
                        type: e.type
                    });
                });
            });
            window.__native = [];
            document.addEventListener('cropduster:update', function (e) {
                window.__native.push(e.detail && e.detail.prefix);
            });
            return seen.length;
        """)
        self.assertGreaterEqual(instances, 1)

        self.complete('headshot')

        # A jQuery handler on ``document`` also receives the native dispatch,
        # without positional arguments. The jQuery dispatch follows it.
        positional = [call for call in self.js("return window.__updates;")
                      if call['prefix'] is not None]
        self.assertEqual(len(positional), instances, positional)
        for call in positional:
            self.assertEqual(call['prefix'], 'headshot')
            self.assertEqual(call['image'], 41)
        self.assertEqual(self.js("return window.__native;"), ['headshot'])

    # -- reading and mutating the size list -----------------------------------

    def test_sizes_array_is_shared_with_its_consumers(self):
        """
        ``removeSize`` and ``restoreSize`` mutate the array stored by jQuery.

        One downstream script replaces the array on a layout change and keeps
        the new one; another then removes and restores entries from it. Both
        callers keep their own reference to that array, so the methods must
        modify it in place rather than copy it.
        """
        self.load_admin(Article)

        names = self.js("""
            var $ = window.django.jQuery;
            var field = document.getElementById('id_lead_image');
            // Downstream pattern: a fresh array published through jQuery
            // data, replacing whatever the attribute parsed to.
            var layout = [{name: 'main', w: 600, h: 480},
                          {name: 'no_height', w: 600},
                          {name: 'extra', w: 300, h: 300}];
            $(field).data('sizes', layout);
            window.__layout = layout;

            var read = function () {
                return window.__layout.map(function (size) { return size.name; });
            };
            var out = {start: read(), shared: $(field).data('sizes') === layout};
            window.CropDuster.removeSize('lead_image', 'no_height');
            out.removed = read();
            out.stillShared = $(field).data('sizes') === layout;
            window.CropDuster.restoreSize('lead_image', 'no_height');
            out.restored = read();
            return out;
        """)

        self.assertEqual(names, {
            'start': ['main', 'no_height', 'extra'],
            'shared': True,
            'removed': ['main', 'extra'],
            'stillShared': True,
            # Restore the size at its original position.
            'restored': ['main', 'no_height', 'extra'],
        })

    @override_settings(CROPDUSTER_DIALOG_MODE='window')
    def test_show_reads_the_live_size_list(self):
        """
        The popup URL includes whatever the size array holds at click time.

        A downstream script replaces the array when the layout changes.
        ``show`` must read its current value rather than the value present
        when the widget mounted.

        This uses window mode because only the popup encodes the sizes in a
        URL. The modal reads the same current array directly from the page.
        """
        self.load_admin(Article)

        url = self.js("""
            var $ = window.django.jQuery;
            $(document.getElementById('id_lead_image')).data(
                'sizes', [{name: 'only', w: 100, h: 100}]);
            window.__opened = [];
            window.open = function (url, name) {
                window.__opened.push({url: url, name: name});
                return {focus: function () {}};
            };
            document.querySelector('#lead_image-group a.cropduster-customfield')
                .dispatchEvent(new MouseEvent('click', {bubbles: true,
                                                        cancelable: true}));
            return window.__opened;
        """)

        self.assertEqual(len(url), 1, url)
        self.assertEqual(url[0]['name'], 'lead_image')
        self.assertIn('sizes=%5B%7B%22name%22:%22only%22', url[0]['url'])
        self.assertIn('&el_id=lead_image', url[0]['url'])

    # -- reading what other scripts write -------------------------------------

    def test_external_val_write_is_observed(self):
        """
        A jQuery ``.val()`` update reaches the rendered widget.

        Downstream scripts write this way: a property assignment with no
        event and no attribute change, which neither a listener nor a
        MutationObserver would see.
        """
        author = Author.objects.create(name="Mark Twain")
        self.load_admin(author)

        self.complete('headshot')
        self.assertTrue(self.js(
            "var images = document.querySelector("
            "'#headshot-group .cropduster-images');"
            "return !!(images && images.shadowRoot"
            " && images.shadowRoot.querySelector('img'));"))

        self.js("""
            var $ = window.django.jQuery;
            $('#id_headshot-0-image').val('');
            $('#id_headshot').val('');
        """)

        self.wait_until(
            lambda d: not self.js(
                "var images = document.querySelector("
                "'#headshot-group .cropduster-images');"
                "return !!(images && images.shadowRoot"
                " && images.shadowRoot.querySelector('img'));"),
            message="The thumbnail outlived the value it was rendered from")

    def test_delete_checkbox_toggles_the_predelete_class(self):
        """
        Ticking DELETE applies the classes used to hide a deleted row.

        nested-admin's cascade sets ``checked`` directly on the input
        (``jquery.djangoformset.js:269-276``), again with no event, and both
        grappelli and the admin style the row from the class.
        """
        author = Author.objects.create(name="Mark Twain")
        cropduster.attach(author, "headshot", TEST_IMAGE)
        self.load_admin(author)

        predeleted = """
            var root = document.getElementById('headshot-group');
            return root.classList.contains('predelete')
                && root.classList.contains('grp-predelete');
        """
        self.assertIs(self.js(predeleted), False)

        self.js("document.getElementById('id_headshot-0-DELETE').checked = true;")

        self.wait_until(lambda d: self.js(predeleted),
                        message="The DELETE checkbox did not mark the row")

        self.js("document.getElementById('id_headshot-0-DELETE').checked = false;")

        self.wait_until(lambda d: not self.js(predeleted),
                        message="Unticking DELETE did not clear the mark")
