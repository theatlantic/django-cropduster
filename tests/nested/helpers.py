"""
Helpers for django-nested-admin browser tests.

django-nested-admin does not include its test helpers in the wheel, so these
helpers use the selectors in ``nesting/admin/inlines/stacked.html``.

The reorder helpers call nested-admin's own ``updatePositions`` and
``spliceInto`` functions. Reproducing a jQuery UI drag with Selenium would
require several pointer movements through a placeholder that exists only
during the drag, which is unreliable in headless Chrome. Calling the same
functions still tests nested-admin's renaming, management-form updates, and
events. See ``sortable.js:222-252``.
"""

import json
import os

from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

import cropduster
from tests.helpers import CropdusterTestCaseMediaMixin
from tests.nested.models import NestedItem, NestedRoot, NestedSection


#: The add handler sits directly under the group, except when the inline
#: declares ``classes``, which wraps the body in a fieldset.
ADD_HANDLER = (
    '#{prefix}-group > .djn-add-item > a.djn-add-handler, '
    '#{prefix}-group > fieldset > .djn-add-item > a.djn-add-handler')

#: The remove link of a row that has never been saved, and the delete checkbox
#: of one that has. Only one of the two is rendered per row.
REMOVE_HANDLER = '#{prefix} > h3 a.djn-remove-handler'
DELETE_HANDLER = '#{prefix} > h3 span.djn-delete-handler'

#: The upload button of one widget. React renders its contents into the
#: server-rendered anchor, which is where the click listener lives.
UPLOAD_BUTTON = '#{prefix}-group a.cropduster-customfield'

#: Shared setup for scripts that call nested-admin. Its bundle assigns
#: Webpack's exports object to ``window.DJNesting``; some builds expose the
#: module API on its ``default`` property.
NESTING_JS = """
var $ = window.django.jQuery;
var DJN = window.DJNesting || {};
if (!DJN.updatePositions && DJN['default']) { DJN = DJN['default']; }
var items = function ($group) {
    return $group.find('> .djn-items, > fieldset > .djn-items').eq(0);
};
"""


class NestedAdminTestCase(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

    root_urlconf = 'tests.urls_nested'

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
            'nested_admin',
            'generic_plus',
            'cropduster',
            'tests',
            # ``admin.autodiscover()`` registers this application, so it must
            # be present when Django builds the admin index.
            'tests.standalone',
            'tests.nested',
            'selenosis',
        ]
        if cls.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    # -- fixtures ----------------------------------------------------------

    def make_root(self, sections=1, items=1, with_images=False):
        """
        Create a saved root whose inline rows can be soft-deleted.

        ``with_images`` attaches an image to both cropduster fields of every
        item. The subformset renders its DELETE checkbox only when an image
        exists, and nested-admin's delete cascade selects that checkbox.
        """
        root = NestedRoot.objects.create(title="A root")
        for section_index in range(sections):
            section = NestedSection.objects.create(
                root=root, name="Section %d" % section_index, position=section_index)
            for item_index in range(items):
                item = NestedItem.objects.create(section=section, position=item_index)
                if not with_images:
                    continue
                source = os.path.join(self.TEST_IMG_DIR, 'img2.jpg')
                for field_name in ('image', 'alt_image'):
                    cropduster.attach(item, field_name, source,
                                      metadata={'alt_text': 'An alt text'})
        return root

    def items(self, root, section=0):
        """Return the items in one section, ordered by position."""
        sections = list(root.section_set.order_by('position'))
        return list(sections[section].items.order_by('position'))

    # -- formset operations ------------------------------------------------

    def add_inline(self, prefix):
        """
        Click a group's "Add another" link and return the new row ID.

        ``prefix`` is ``section_set`` for the outer group and
        ``section_set-0-items`` for the inner group in the first section.
        """
        before = self.row_ids(prefix)
        with self.clickable_selector(ADD_HANDLER.format(prefix=prefix)) as el:
            el.click()
        self.wait_until(
            lambda d: len(self.row_ids(prefix)) > len(before),
            message="Timeout waiting for a row to be added to %s" % prefix)
        return [row for row in self.row_ids(prefix) if row not in before][0]

    def remove_inline(self, prefix, via_script=False):
        """
        Click the Remove link for an unsaved row identified by its ID.

        ``via_script`` dispatches the click while a modal covers the page.
        nested-admin uses a delegated jQuery handler, which receives the
        dispatched event as it would a browser click.
        """
        group = prefix.rsplit('-', 1)[0]
        count = len(self.row_ids(group))
        selector = REMOVE_HANDLER.format(prefix=prefix)
        if via_script:
            self.selenium.execute_script("""
                document.querySelector(arguments[0]).dispatchEvent(
                    new MouseEvent('click', {bubbles: true, cancelable: true}));
            """, selector)
        else:
            with self.clickable_selector(selector) as el:
                el.click()
        self.wait_until(
            lambda d: len(self.row_ids(group)) < count,
            message="Timeout waiting for %s to be removed" % prefix)

    def delete_inline(self, prefix):
        """Select the DELETE checkbox for a saved row identified by its ID."""
        with self.clickable_selector(DELETE_HANDLER.format(prefix=prefix)) as el:
            el.click()
        self.wait_until(
            lambda d: self.is_predeleted(prefix),
            message="Timeout waiting for %s to be marked deleted" % prefix)

    def undelete_inline(self, prefix):
        with self.clickable_selector(DELETE_HANDLER.format(prefix=prefix)) as el:
            el.click()
        self.wait_until(
            lambda d: not self.is_predeleted(prefix),
            message="Timeout waiting for %s to be restored" % prefix)

    # -- page state --------------------------------------------------------

    def row_ids(self, prefix):
        """
        Return the IDs of a group's rows in DOM order.

        Exclude the empty-form template because callers need only rows that
        nested-admin has instantiated from it.
        """
        return self.selenium.execute_script("""
            var rows = document.querySelectorAll(
                '#' + arguments[0] + '-group > .djn-items > .djn-inline-form,'
                + '#' + arguments[0] + '-group > fieldset > .djn-items > .djn-inline-form');
            return Array.prototype.filter.call(rows, function (row) {
                return !/(^|-)empty$/.test(row.id);
            }).map(function (row) { return row.id; });
        """, prefix)

    def is_predeleted(self, prefix):
        return self.selenium.execute_script(
            "var el = document.getElementById(arguments[0]);"
            "return !!el && (el.classList.contains('predelete')"
            " || el.classList.contains('grp-predelete'));", prefix)

    def field_names(self, root_id):
        """Return every field name below an element."""
        return self.selenium.execute_script(
            "return Array.prototype.map.call("
            "  document.getElementById(arguments[0]).querySelectorAll('[name]'),"
            "  function (el) { return el.name; });", root_id)

    def is_checked(self, element_id):
        return self.selenium.execute_script(
            "var el = document.getElementById(arguments[0]);"
            "return el ? el.checked : null;", element_id)

    # -- reorder operations ------------------------------------------------

    def move_after(self, row_id, target_id):
        """
        Move a row after another row in the same group.

        The sortable's ``update`` handler renumbers the position fields.
        ``spliceInto`` returns early for a move within one group, so IDs and
        field names remain unchanged.
        """
        self.selenium.execute_script(NESTING_JS + """
            var $row = $('#' + arguments[0]);
            $('#' + arguments[1]).after($row);
            var prefix = $row.djangoFormsetPrefix();
            DJN.updatePositions(prefix);
            $(document).trigger('djnesting:mutate', [$('#' + prefix + '-group')]);
        """, row_id, target_id)

    def splice_into(self, row_id, group_prefix):
        """
        Move a row into another group as the sortable's ``receive`` does.

        Return the row's new ID. ``spliceInto`` renumbers it for the receiving
        formset, unlike the ``_fillGap`` rename path.
        """
        return self.selenium.execute_script(NESTING_JS + """
            var $row = $('#' + arguments[0]);
            var $group = $('#' + arguments[1] + '-group');
            items($group).append($row);
            $group.djangoFormset().spliceInto($row);
            DJN.updatePositions($row.djangoFormsetPrefix());
            return $row.attr('id');
        """, row_id, group_prefix)

    # -- widget operations -------------------------------------------------

    def click_selector(self, selector):
        with self.clickable_selector(selector) as el:
            self.selenium.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", el)
            el.click()

    def upload_into(self, prefix, image='img.jpg', sizes=1):
        """
        Upload and crop one image through a widget.

        ``crop_dialog`` enters the modal or popup according to ``dialog_mode``.
        The popup opens ``upload.html`` and calls
        ``window.opener.CropDuster.complete`` when finished. ``sizes`` is the
        number of parent sizes expected on the field.
        """
        from selenium.webdriver.common.by import By

        self.click_selector(UPLOAD_BUTTON.format(prefix=prefix))
        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, image))
            self.assertEqual(int(self.dialog_text('#thumb-total-count')), sizes)
            self.dialog_save()
        def widget_rendered(_driver):
            state = self.widget_state(prefix)
            return bool(
                state and state['image'] and len(state['previews']) == 1)

        self.wait_until(
            widget_rendered,
            message="Timeout waiting for %s to render the crop" % prefix)
        self.selenium.find_element(By.ID, 'id_%s-0-alt_text' % prefix).send_keys(
            "An alt text")

    def complete(self, prefix, payload):
        """
        Call ``CropDuster.complete(prefix, data)`` as the popup does.

        The popup retains a prefix string rather than an element, so
        ``complete`` looks up the widget when the crop result returns.
        """
        self.selenium.execute_script(
            "window.CropDuster.complete(arguments[0], JSON.parse(arguments[1]));",
            prefix, json.dumps(payload))

    def set_alt_text(self, prefix, value):
        """Set alt text used to identify a row in later assertions."""
        self.selenium.execute_script(
            "document.getElementById('id_' + arguments[0] + '-0-alt_text')"
            ".value = arguments[1];", prefix, value)

    def widget_state(self, prefix):
        """Return one widget's formset values and rendered preview state."""
        return self.selenium.execute_script("""
            var root = document.getElementById(arguments[0] + '-group');
            if (!root) { return null; }
            var val = function (name) {
                var el = root.querySelector('[name="' + name + '"]');
                return el ? el.value : null;
            };
            var field = root.querySelector('.cropduster-data-field');
            var images = root.querySelector('.cropduster-images');
            var previewRoot = images && images.shadowRoot;
            return {
                prefix: field ? field.name : null,
                value: field ? field.value : null,
                imageId: val(arguments[0] + '-0-id'),
                image: val(arguments[0] + '-0-image'),
                altText: val(arguments[0] + '-0-alt_text'),
                total: val(arguments[0] + '-TOTAL_FORMS'),
                initial: val(arguments[0] + '-INITIAL_FORMS'),
                thumbs: Array.prototype.map.call(
                    root.querySelectorAll(
                        '[name="' + arguments[0] + '-0-thumbs"] option'),
                    function (option) { return option.value; }),
                previews: previewRoot ? Array.prototype.map.call(
                    previewRoot.querySelectorAll(
                        '.cropduster-image-thumb-preview'),
                    function (img) { return img.getAttribute('src'); }) : []
            };
        """, prefix)

    def wait_for_preview(self, prefix):
        """Wait until React renders one preview for ``prefix``."""
        self.wait_until(
            lambda d: len((self.widget_state(prefix) or {}).get('previews', [])) == 1,
            message="Timeout waiting for %s to render its preview" % prefix)

    def widget_mounts(self):
        """
        Return ``{prefix: mounted}`` for every widget element on the page.

        Each ``<cropduster-widget>`` exposes its mounted widget. The empty-form
        template and a row otherwise have identical markup until React renders
        the button contents.
        """
        return self.selenium.execute_script("""
            var out = {};
            Array.prototype.forEach.call(
                document.querySelectorAll('cropduster-widget'),
                function (el) {
                    var root = el.closest('.cropduster-form');
                    var field = root && root.querySelector('.cropduster-data-field');
                    if (field) { out[field.name] = !!el.widget; }
                });
            return out;
        """)

    def record_popups(self):
        """Stub ``window.open`` and return a function that reads its calls."""
        self.selenium.execute_script("""
            window.__popups = [];
            window.open = function (url, name) {
                window.__popups.push({url: url, name: name});
                return {focus: function () {}};
            };
        """)
        return lambda: self.selenium.execute_script("return window.__popups;")

    def click_upload_button(self, prefix):
        """
        Dispatch a click on a widget button even when it is hidden.

        This lets tests verify that the empty-form template's hidden button
        has no click listener.
        """
        self.selenium.execute_script("""
            document.querySelector(arguments[0]).dispatchEvent(
                new MouseEvent('click', {bubbles: true, cancelable: true}));
        """, UPLOAD_BUTTON.format(prefix=prefix))
