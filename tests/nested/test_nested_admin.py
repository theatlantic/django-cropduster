"""
Browser tests for Cropduster fields inside two nested inline formsets.

Some tests cover the markup django-nested-admin depends on:
``.cropduster-form`` for renaming and ``id_{prefix}-0-DELETE`` for its delete
cascade. The remaining tests cover mounting after insertion, skipping
empty-form templates, and deriving a field prefix after a row is renamed.

``NestedAdminTest`` uses the popup because a row can be renamed while the
dialog is in another window. ``NestedAdminModalTest`` verifies that a modal
still writes to the row from which it was opened after that row is moved.
"""

import os

from django.test import override_settings

from cropduster.models import Image
from tests.nested.helpers import UPLOAD_BUTTON, NestedAdminTestCase
from tests.nested.models import NestedItem
# Use the crop response passed to ``CropDuster.complete`` in compatibility tests.
from tests.test_admin_compat import CROP_PAYLOAD


@override_settings(CROPDUSTER_DIALOG_MODE='window')
class NestedAdminTest(NestedAdminTestCase):

    dialog_mode = 'window'

    # -- markup used by nested-admin ---------------------------------------

    def test_delete_cascades_delete_checkbox(self):
        """
        Deleting a row selects its widgets' DELETE checkboxes.

        nested-admin finds each ``.cropduster-form`` and selects its literal
        ``id_{prefix}-0-DELETE`` checkbox. Those values remove the related
        ``cropduster.Image`` rows when the form is saved.
        """
        root = self.make_root(sections=1, items=2, with_images=True)
        self.load_admin(root)

        item_prefix = 'section_set-0-items-0'
        checkboxes = [
            'id_%s-image-0-DELETE' % item_prefix,
            'id_%s-alt_image-0-DELETE' % item_prefix,
        ]
        for element_id in checkboxes:
            self.assertIs(self.is_checked(element_id), False, element_id)

        self.delete_inline(item_prefix)

        for element_id in checkboxes:
            self.assertIs(self.is_checked(element_id), True, element_id)
        # The cascade selects checkboxes only within the deleted row.
        self.assertIs(
            self.is_checked('id_section_set-0-items-1-image-0-DELETE'), False)

        self.undelete_inline(item_prefix)

        for element_id in checkboxes:
            self.assertIs(self.is_checked(element_id), False, element_id)

    def test_delete_cascade_survives_the_save(self):
        """Save the selected DELETE values and remove their related rows."""
        root = self.make_root(sections=1, items=2, with_images=True)
        item = NestedItem.objects.order_by('pk').first()
        self.assertEqual(Image.objects.filter(object_id=item.pk).count(), 2)
        self.load_admin(root)

        self.delete_inline('section_set-0-items-0')
        self.save_form()

        self.assertFalse(NestedItem.objects.filter(pk=item.pk).exists())
        self.assertEqual(NestedItem.objects.count(), 1)
        self.assertFalse(Image.objects.filter(object_id=item.pk).exists())
        self.assertEqual(Image.objects.count(), 2)

    def test_remove_row_fills_gap_renames(self):
        """
        Removing a row renames later rows and their widget fields.

        ``_fillGap`` rewrites ``id``, ``name``, ``for``, ``href``, ``class``
        and ``onclick`` inside ``.cropduster-form``. This includes the group
        ID, data field, and subformset management fields. It does not rewrite
        ``<cropduster-widget data-config>``, so that attribute cannot contain
        values derived from the formset prefix.
        """
        root = self.make_root(sections=1, items=0)
        self.load_admin(root)

        first = self.add_inline('section_set-0-items')
        second = self.add_inline('section_set-0-items')
        self.assertEqual([first, second],
                         ['section_set-0-items-0', 'section_set-0-items-1'])

        moved = set(self.field_names('section_set-0-items-1'))
        self.assertIn('section_set-0-items-1-image-0-image', moved)

        self.remove_inline('section_set-0-items-0')

        self.assertEqual(self.row_ids('section_set-0-items'),
                         ['section_set-0-items-0'])
        renamed = set(self.field_names('section_set-0-items-0'))
        self.assertEqual(
            renamed,
            {name.replace('items-1', 'items-0') for name in moved})
        self.assertTrue(self.selenium.execute_script(
            "return !!document.getElementById("
            "'section_set-0-items-0-image-group');"))

    # -- mounting ----------------------------------------------------------

    def test_empty_template_not_mounted(self):
        """
        Do not mount the ``-empty`` template or enable its upload button.

        The outer group's template contains ``-empty-`` and the template
        inside the saved section contains ``__prefix__``. Both must remain
        unmounted until nested-admin clones and renames them.
        """
        root = self.make_root(sections=1, items=1)
        self.load_admin(root)

        mounts = self.widget_mounts()
        templates = {prefix: mounted for prefix, mounted in mounts.items()
                     if '__prefix__' in prefix or '-empty-' in prefix}
        rows = {prefix: mounted for prefix, mounted in mounts.items()
                if prefix not in templates}

        self.assertTrue(templates, "no empty-form template on the page")
        self.assertTrue(rows, "no real row on the page")
        self.assertEqual(set(templates.values()), {False}, sorted(templates))
        self.assertEqual(set(rows.values()), {True}, sorted(rows))
        self.assertIn('section_set-0-items-0-image', rows)

        popups = self.record_popups()
        template_prefix = sorted(templates)[0]
        self.click_upload_button(template_prefix)
        self.assertEqual(popups(), [], template_prefix)

        # Confirm that the stub records a click from a mounted row.
        self.click_upload_button('section_set-0-items-0-image')
        self.assertEqual([popup['name'] for popup in popups()],
                         ['section_set____0____items____0____image'])

    def test_add_row_then_upload(self):
        """Mount a widget inserted after page load and upload through it."""
        root = self.make_root(sections=1, items=0)
        self.load_admin(root)

        row = self.add_inline('section_set-0-items')
        self.assertEqual(row, 'section_set-0-items-0')
        prefix = '%s-image' % row
        self.assertIs(self.widget_mounts()[prefix], True)

        self.upload_into(prefix)

        state = self.widget_state(prefix)
        self.assertEqual(state['total'], '1')
        self.assertEqual(state['initial'], '0')
        self.assertTrue(state['image'])
        self.assertEqual(state['value'], state['image'])
        self.assertEqual(len(state['thumbs']), 2)
        self.assertEqual(len(state['previews']), 1)

        self.save_form()

        item = NestedItem.objects.get()
        self.assertEqual(item.image.name, state['image'])
        image = item.image.related_object
        self.assertEqual(
            sorted(image.thumbs.values_list('name', flat=True)), ['main', 'thumb'])

    def test_nested_group_added_inside_a_new_parent(self):
        """
        Initialize an items group inside a newly inserted section.

        The inner formset is initialized after the outer row is inserted, and
        nested-admin reports that initialization through
        ``djnesting:initialized``.
        """
        root = self.make_root(sections=0, items=0)
        self.load_admin(root)

        section = self.add_inline('section_set')
        self.assertEqual(section, 'section_set-0')
        row = self.add_inline('%s-items' % section)
        self.assertEqual(row, 'section_set-0-items-0')

        prefix = '%s-image' % row
        self.assertIs(self.widget_mounts()[prefix], True)
        self.upload_into(prefix)

        self.save_form()

        item = NestedItem.objects.get()
        self.assertEqual(item.section.root, root)
        self.assertTrue(item.image.name)

    def test_independent_rows(self):
        """Uploading into one row leaves sibling formsets unchanged."""
        root = self.make_root(sections=1, items=2)
        self.load_admin(root)

        target = 'section_set-0-items-0-image'
        sibling = 'section_set-0-items-1-image'
        before = self.widget_state(sibling)

        self.upload_into(target)

        self.assertEqual(self.widget_state(sibling), before)
        self.assertEqual(before['image'], '')
        self.assertEqual(before['thumbs'], [])
        self.assertEqual(before['previews'], [])
        self.assertTrue(self.widget_state(target)['image'])

        self.save_form()

        first, second = self.items(root)
        self.assertTrue(first.image.name)
        self.assertFalse(second.image.name)

    def test_two_fields_on_one_row_are_independent(self):
        """Keep the ``image`` and ``alt_image`` formsets independent."""
        root = self.make_root(sections=1, items=1)
        self.load_admin(root)

        main = 'section_set-0-items-0-image'
        alt = 'section_set-0-items-0-alt_image'

        self.upload_into(main, image='img.jpg')
        self.assertEqual(self.widget_state(alt)['image'], '')

        self.upload_into(alt, image='img2.jpg')

        main_state = self.widget_state(main)
        alt_state = self.widget_state(alt)
        self.assertNotEqual(main_state['image'], alt_state['image'])
        self.assertEqual(len(main_state['thumbs']), 2)
        self.assertEqual(len(alt_state['thumbs']), 1)

        self.save_form()

        item = NestedItem.objects.get()
        self.assertEqual(item.image.name, main_state['image'])
        self.assertEqual(item.alt_image.name, alt_state['image'])
        self.assertEqual(item.image.related_object.field_identifier, '')
        self.assertEqual(item.alt_image.related_object.field_identifier, 'alt')

    # -- moving rows -------------------------------------------------------

    def test_reorder_within_group_renames_nothing(self):
        """
        Reordering within a group changes position values, not form indexes.

        ``spliceInto`` returns early for a same-group move, so IDs and field
        names remain unchanged and each widget derives the same prefix.
        """
        root = self.make_root(sections=1, items=2, with_images=True)
        first, second = self.items(root)
        self.load_admin(root)

        names = {row: self.field_names(row) for row in
                 ('section_set-0-items-0', 'section_set-0-items-1')}
        images = {row: self.widget_state('%s-image' % row)['image'] for row in names}

        self.move_after('section_set-0-items-0', 'section_set-0-items-1')

        self.assertEqual(
            self.row_ids('section_set-0-items'),
            ['section_set-0-items-1', 'section_set-0-items-0'])
        for row, expected in names.items():
            self.assertEqual(self.field_names(row), expected, row)
            self.assertEqual(
                self.widget_state('%s-image' % row)['image'], images[row], row)

        self.save_form()

        # The rows retain their images after their order changes.
        self.assertEqual([item.pk for item in self.items(root)],
                         [second.pk, first.pk])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.image.name, images['section_set-0-items-0'])
        self.assertEqual(second.image.name, images['section_set-0-items-1'])

    def test_upload_then_reorder_then_save(self):
        """
        Keep a crop on its row when that row moves within a formset.

        ``spliceInto`` returns early for a move within one formset, so IDs and
        field names do not change. This verifies that React does not retain
        separate formset values based on the row's original index. The popup
        rename case is covered by
        ``test_complete_after_gap_fill_targets_the_renumbered_row``.
        """
        root = self.make_root(sections=1, items=2)
        first, second = self.items(root)
        self.load_admin(root)

        prefix = 'section_set-0-items-1-image'
        self.upload_into(prefix)
        uploaded = self.widget_state(prefix)['image']

        self.move_after('section_set-0-items-0', 'section_set-0-items-1')
        self.assertEqual(self.widget_state(prefix)['image'], uploaded)

        self.save_form()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.image.name, uploaded)
        self.assertFalse(first.image.name)
        self.assertEqual([item.pk for item in self.items(root)],
                         [second.pk, first.pk])

    def test_complete_after_gap_fill_targets_the_renumbered_row(self):
        """
        Apply a popup result to the row currently using its retained prefix.

        A window-mode popup retains ``el_id`` as a string, and ``complete``
        resolves it through ``#id_{prefix}`` as 4.x did. If a row is removed
        while the popup is open, ``_fillGap`` moves the last row into the freed
        index. The retained prefix then identifies that different row.

        This records the existing popup behavior without treating it as the
        preferred implementation. The modal retains the widget that opened it
        and is covered by
        ``test_modal_complete_after_gap_fill_targets_the_original_row``.
        """
        root = self.make_root(sections=1, items=0)
        self.load_admin(root)

        rows = [self.add_inline('section_set-0-items') for _ in range(3)]
        self.assertEqual(rows, ['section_set-0-items-%d' % i for i in range(3)])
        for index, row in enumerate(rows):
            self.set_alt_text('%s-image' % row, 'Row %d' % index)

        # A popup opened from row 0 retains only this prefix. Call
        # ``complete()`` directly to reproduce the popup's final write.
        prefix = 'section_set-0-items-0-image'
        self.assertEqual(self.widget_state(prefix)['altText'], 'Row 0')

        self.remove_inline('section_set-0-items-0')

        # Row 2 took the freed index; row 1 kept the one it had.
        self.assertEqual(self.row_ids('section_set-0-items'),
                         ['section_set-0-items-1', 'section_set-0-items-0'])
        self.assertEqual(self.widget_state(prefix)['altText'], 'Row 2')

        self.complete(prefix, CROP_PAYLOAD)

        landed = self.widget_state(prefix)
        self.assertEqual(landed['image'], CROP_PAYLOAD['crop']['orig_image'])
        self.assertEqual(landed['altText'], 'Row 2')

        untouched = self.widget_state('section_set-0-items-1-image')
        self.assertEqual(untouched['altText'], 'Row 1')
        self.assertFalse(untouched['image'])

    def test_cross_group_splice(self):
        """Move a row to another section and rename it and its widgets."""
        root = self.make_root(sections=2, items=0)
        self.load_admin(root)

        row = self.add_inline('section_set-0-items')
        self.assertEqual(row, 'section_set-0-items-0')
        prefix = '%s-image' % row
        self.upload_into(prefix)
        uploaded = self.widget_state(prefix)['image']
        config = self.selenium.execute_script(
            "return document.querySelector('#' + arguments[0]"
            " + '-group cropduster-widget').getAttribute('data-config');", prefix)

        moved = self.splice_into(row, 'section_set-1-items')

        self.assertEqual(moved, 'section_set-1-items-0')
        self.assertEqual(self.row_ids('section_set-0-items'), [])
        self.assertEqual(self.row_ids('section_set-1-items'), [moved])

        new_prefix = '%s-image' % moved
        state = self.widget_state(new_prefix)
        self.assertEqual(state['prefix'], new_prefix)
        self.assertEqual(state['image'], uploaded)
        self.assertEqual(len(state['thumbs']), 2)
        self.assertIs(self.widget_mounts()[new_prefix], True)
        self.assertNotIn(prefix, self.widget_mounts())

        # nested-admin does not rewrite ``data-config``, so it must not contain
        # values derived from the formset prefix.
        self.assertEqual(self.selenium.execute_script(
            "return document.querySelector('#' + arguments[0]"
            " + '-group cropduster-widget').getAttribute('data-config');",
            new_prefix), config)

        self.save_form()

        item = NestedItem.objects.get()
        self.assertEqual(item.section.name, "Section 1")
        self.assertEqual(item.image.name, uploaded)

    # -- failed form submission -------------------------------------------

    def test_validation_error_round_trip(self):
        """
        Render an uploaded crop again after nested form validation fails.

        ``_construct_form`` rebuilds the thumbs queryset from primary keys in
        the POST, and ``inline.html`` renders ``non_form_errors`` before its
        field loop. The latter is required for the ``require_alt_text`` error
        to appear.
        """
        from selenium.webdriver.common.by import By

        root = self.make_root(sections=1, items=0)
        self.load_admin(root)

        row = self.add_inline('section_set-0-items')
        prefix = '%s-image' % row
        self.upload_into(prefix)

        alt_text = self.selenium.find_element(By.ID, 'id_%s-0-alt_text' % prefix)
        alt_text.clear()
        before = self.widget_state(prefix)

        self.save_form()

        self.assertFalse(NestedItem.objects.exists())
        self.assertIn(
            "Alt text describing the image is required",
            self.selenium.find_element(By.TAG_NAME, 'body').text)

        self.wait_for_preview(prefix)
        after = self.widget_state(prefix)
        self.assertEqual(after['image'], before['image'])
        self.assertEqual(after['value'], before['value'])
        self.assertEqual(after['thumbs'], before['thumbs'])
        self.assertEqual(len(after['previews']), 1)
        self.assertIs(self.widget_mounts()[prefix], True)

        self.selenium.find_element(
            By.ID, 'id_%s-0-alt_text' % prefix).send_keys("An alt text")
        self.save_form()

        item = NestedItem.objects.get()
        self.assertEqual(item.image.name, before['image'])
        self.assertEqual(
            sorted(item.image.related_object.thumbs.values_list('name', flat=True)),
            ['main', 'thumb'])


class NestedAdminModalTest(NestedAdminTestCase):
    """
    Run the nested widget with the dialog in the current page.

    ``CROPDUSTER_DIALOG_MODE`` retains its default. The test viewport resolves
    ``auto`` to the modal.
    """

    dialog_mode = 'modal'

    def test_modal_complete_after_gap_fill_targets_the_original_row(self):
        """
        Return a modal crop to its original row after that row is renamed.

        ``_fillGap`` fills a removed row's index with the *last* row, so the
        row that opened a dialog can be renumbered while the dialog is open.
        A popup retains only its original prefix, so its crop is written to
        the row using that prefix when the result returns
        (``test_complete_after_gap_fill_targets_the_renumbered_row``); the
        modal retains its originating widget and writes to that same row.
        """
        root = self.make_root(sections=1, items=0)
        self.load_admin(root)

        rows = [self.add_inline('section_set-0-items') for _ in range(3)]
        self.assertEqual(rows, ['section_set-0-items-%d' % i for i in range(3)])

        # ``_fillGap`` moves the last row. Its alt text identifies it after the
        # rename.
        prefix = 'section_set-0-items-2-image'
        self.set_alt_text(prefix, 'Row 2')

        self.click_selector(UPLOAD_BUTTON.format(prefix=prefix))
        with self.crop_dialog():
            self.dialog_upload(
                os.path.join(self.TEST_IMG_DIR, 'img.jpg'))

            self.remove_inline('section_set-0-items-0', via_script=True)
            # Row 2 took the freed index; row 1 kept the one it had. The
            # prefix the dialog was opened with now names nothing.
            self.assertEqual(self.row_ids('section_set-0-items'),
                             ['section_set-0-items-1', 'section_set-0-items-0'])
            self.assertIsNone(self.widget_state(prefix))

            self.dialog_save()

        moved = 'section_set-0-items-0-image'
        self.wait_for_preview(moved)
        landed = self.widget_state(moved)
        self.assertEqual(landed['altText'], 'Row 2')
        self.assertEqual(landed['prefix'], moved)
        self.assertTrue(landed['image'])
        self.assertEqual(landed['value'], landed['image'])
        self.assertEqual(len(landed['thumbs']), 2)
        self.assertEqual(len(landed['previews']), 1)

        untouched = self.widget_state('section_set-0-items-1-image')
        self.assertFalse(untouched['image'])
        self.assertEqual(untouched['thumbs'], [])

        self.save_form()

        # The other surviving row is an untouched extra form and is not saved.
        items = self.items(root)
        cropped = [item for item in items if item.image.name]
        self.assertEqual(len(cropped), 1)
        self.assertEqual(cropped[0].image.name, landed['image'])
        self.assertEqual(cropped[0].image.related_object.alt_text, 'Row 2')
        self.assertEqual(
            sorted(cropped[0].image.related_object.thumbs.values_list(
                'name', flat=True)),
            ['main', 'thumb'])
