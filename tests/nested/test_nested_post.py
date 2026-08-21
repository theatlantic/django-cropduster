"""
Submit a nested admin form without a browser.

Three nested formsets produce names such as
``section_set-0-items-0-image-0-image``. Downstream code reads those names
directly, so these tests build a POST from the fields Django rendered and
verify that each image is saved on the intended item.

The helper replaces ``__prefix__`` and ``-empty-`` in the same order as
django-nested-admin's ``add()`` implementation. No complete field prefix is
hard-coded in the payload.
"""

import json as stdlib_json
import os
import re

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TransactionTestCase
from django.urls import reverse

from cropduster.models import Image, Thumb
from tests.helpers import CropdusterTestCaseMediaMixin
from tests.nested.models import NestedItem, NestedRoot, NestedSection


ADD_URL = "/admin/nested/nestedroot/add/"

INPUT_RE = re.compile(r'<input\b([^>]*)>', re.IGNORECASE)
SELECT_RE = re.compile(r'<select\b([^>]*)>(.*?)</select>', re.IGNORECASE | re.DOTALL)
TEXTAREA_RE = re.compile(r'<textarea\b([^>]*)>(.*?)</textarea>',
                         re.IGNORECASE | re.DOTALL)
OPTION_RE = re.compile(r'<option\b([^>]*)>', re.IGNORECASE)
ATTR_RE = re.compile(r'([\w:-]+)(?:\s*=\s*"([^"]*)")?')

#: Ignore submit controls, the widget's unused file input, and unselected
#: checkboxes or radios. Tests that need nested-admin's DELETE checkbox add it
#: by name.
SKIP_TYPES = {'submit', 'button', 'image', 'file', 'checkbox', 'radio'}


def attributes(text):
    return {name: value or '' for name, value in ATTR_RE.findall(text)}


def form_fields(html):
    """
    Return ``{name: value}`` for the fields a browser would submit.

    A multiple select submits one value per selected option and nothing at all
    when none are selected. An empty Cropduster widget must therefore omit
    ``thumbs`` rather than submit an empty value.
    """
    fields = {}
    for attrs, options in SELECT_RE.findall(html):
        name = attributes(attrs).get('name')
        selected = [attributes(option).get('value', '')
                    for option in OPTION_RE.findall(options)
                    if 'selected' in attributes(option)]
        if name and selected:
            fields[name] = selected
    for attrs, content in TEXTAREA_RE.findall(html):
        name = attributes(attrs).get('name')
        if name:
            fields[name] = content
    for attrs in INPUT_RE.findall(html):
        attrs = attributes(attrs)
        name = attrs.get('name')
        if not name or attrs.get('type') in SKIP_TYPES:
            continue
        fields[name] = attrs.get('value', '')
    return fields


def rename(fields, search, replace):
    """Return fields beginning with ``search``, renamed to ``replace``."""
    return {
        name.replace(search, replace, 1): value
        for name, value in fields.items() if name.startswith(search)
    }


class NestedPostTestCase(CropdusterTestCaseMediaMixin, TransactionTestCase):

    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_superuser("test", "test@test.com", "password")
        self.client = Client()
        self.client.force_login(self.user)

    # -- payload construction ---------------------------------------------

    def add_form_fields(self):
        response = self.client.get(ADD_URL)
        self.assertEqual(response.status_code, 200)
        return form_fields(response.content.decode('utf-8'))

    def section(self, template, index, items):
        """
        Build one section row and its items using nested-admin's field names.

        ``add()`` rewrites the outer formset's ``__prefix__``/``-empty-``
        placeholder to the row index, and the inner formset's ``add()`` then
        rewrites its own placeholder. These substitutions produce
        ``section_set-0-items-0-image-0-image`` from the rendered template
        instead of hard-coding the complete prefix.
        """
        prefix = 'section_set-%d' % index
        fields = rename(template, 'section_set-__prefix__', prefix)
        fields.update(rename(template, 'section_set-empty-items', '%s-items' % prefix))
        fields['%s-position' % prefix] = str(index)

        item_template = {
            name: value for name, value in fields.items()
            if name.startswith('%s-items-__prefix__' % prefix)}
        for name in item_template:
            del fields[name]

        fields['%s-items-TOTAL_FORMS' % prefix] = str(len(items))
        fields['%s-items-INITIAL_FORMS' % prefix] = '0'
        for item_index, item in enumerate(items):
            item_prefix = '%s-items-%d' % (prefix, item_index)
            row = rename(
                item_template, '%s-items-__prefix__' % prefix, item_prefix)
            # Neither parent formset rewrites the widget's own empty-form
            # placeholder. Django ignores it, so omit it from this POST.
            row = {name: value for name, value in row.items()
                   if '__prefix__' not in name}
            row['%s-position' % item_prefix] = str(item_index)
            for field_name, image in item.items():
                row.update(self.image_fields('%s-%s' % (item_prefix, field_name), image))
            fields.update(row)
        return fields

    def image_fields(self, prefix, image):
        """
        Return the subformset values written by ``CropDuster.complete()``.

        ``image`` contains the stored path and temporary ``Thumb`` primary
        keys returned by the crop endpoint.
        """
        if image is None:
            return {}
        return {
            '%s-TOTAL_FORMS' % prefix: '1',
            '%s-INITIAL_FORMS' % prefix: '0',
            '%s-0-id' % prefix: '',
            '%s-0-image' % prefix: image['name'],
            '%s-0-thumbs' % prefix: image['thumbs'],
            '%s-0-alt_text' % prefix: image.get('alt_text', 'An alt text'),
            prefix: image['name'],
        }

    # -- image requests ----------------------------------------------------

    def upload_and_crop(self, sizes, source='img2.jpg'):
        """Submit the dialog's upload and crop requests and return formset values."""
        serialized = [size.__serialize__() for size in sizes]
        with open(os.path.join(self.TEST_IMG_DIR, source), 'rb') as f:
            response = self.client.post(reverse('cropduster-api-upload'), {
                'image': f, 'sizes': stdlib_json.dumps(serialized)})
        self.assertEqual(response.status_code, 200, response.content)
        uploaded = stdlib_json.loads(response.content)['image']

        response = self.client.post(
            reverse('cropduster-api-crop'),
            stdlib_json.dumps({
                'image': {
                    'name': uploaded['name'],
                    'width': uploaded['width'],
                    'height': uploaded['height'],
                },
                'sizes': serialized,
                'thumbs': {
                    sizes[0].name: {
                        'crop': {'x': 0, 'y': 0,
                                 'width': uploaded['width'],
                                 'height': uploaded['height']},
                        'changed': True,
                    },
                },
            }),
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        thumbs = stdlib_json.loads(response.content)['thumbs']

        return {
            'name': uploaded['name'],
            'thumbs': [str(thumb['id']) for thumb in thumbs.values() if thumb['id']],
        }

    # -- assertions --------------------------------------------------------

    def assertSaved(self, response):
        self.assertEqual(response.status_code, 302, self.form_errors(response))

    def form_errors(self, response):
        if response.status_code != 200:
            return response.status_code
        return re.findall(
            r'<ul class="errorlist[^"]*"[^>]*>.*?</ul>',
            response.content.decode('utf-8'), re.S)

    def image_for(self, item, field_identifier=''):
        return Image.objects.get(
            content_type=ContentType.objects.get_for_model(NestedItem),
            object_id=item.pk, field_identifier=field_identifier)


class NestedPostTest(NestedPostTestCase):

    def test_two_items_get_their_own_images(self):
        """
        Save each uploaded image on the item named by its formset prefix.

        Two items in one section use different originals, so an incorrect
        composed prefix would assign a source to the wrong item or no item.
        """
        template = self.add_form_fields()
        first = self.upload_and_crop(NestedItem.IMAGE_SIZES, 'img.jpg')
        second = self.upload_and_crop(NestedItem.IMAGE_SIZES, 'img2.jpg')

        payload = dict(template, title="A root")
        payload.update({'section_set-TOTAL_FORMS': '1', 'section_set-INITIAL_FORMS': '0'})
        payload.update(self.section(
            template, 0, [{'image': first}, {'image': second}]))

        self.assertSaved(self.client.post(ADD_URL, payload))

        root = NestedRoot.objects.get()
        section = root.section_set.get()
        one, two = list(section.items.order_by('position'))

        self.assertEqual(one.image.name, first['name'])
        self.assertEqual(two.image.name, second['name'])
        self.assertEqual(self.image_for(one).image.name, first['name'])
        self.assertEqual(self.image_for(two).image.name, second['name'])

    def test_thumbs_are_adopted_by_the_image_they_were_cropped_for(self):
        """
        The crop endpoint saves temporary ``Thumb`` rows without a parent
        image. Submitting the form associates them with the saved ``Image``.
        """
        template = self.add_form_fields()
        image = self.upload_and_crop(NestedItem.IMAGE_SIZES)

        payload = dict(template, title="A root")
        payload.update({'section_set-TOTAL_FORMS': '1', 'section_set-INITIAL_FORMS': '0'})
        payload.update(self.section(template, 0, [{'image': image}]))

        self.assertSaved(self.client.post(ADD_URL, payload))

        item = NestedItem.objects.get()
        row = self.image_for(item)

        self.assertEqual(
            sorted(row.thumbs.values_list('name', flat=True)), ['main', 'thumb'])
        self.assertEqual(
            sorted(int(pk) for pk in image['thumbs']),
            sorted(row.thumbs.values_list('pk', flat=True)))
        self.assertFalse(Thumb.objects.filter(image__isnull=True).exists())

    def test_two_fields_on_one_item_are_told_apart_by_field_identifier(self):
        """
        ``image`` and ``alt_image`` use the same generic relation on one item.
        ``field_identifier`` distinguishes their ``Image`` rows.
        """
        template = self.add_form_fields()
        main = self.upload_and_crop(NestedItem.IMAGE_SIZES)
        alt = self.upload_and_crop(NestedItem.ALT_IMAGE_SIZES)

        payload = dict(template, title="A root")
        payload.update({'section_set-TOTAL_FORMS': '1', 'section_set-INITIAL_FORMS': '0'})
        payload.update(self.section(
            template, 0, [{'image': main, 'alt_image': alt}]))

        self.assertSaved(self.client.post(ADD_URL, payload))

        item = NestedItem.objects.get()

        self.assertEqual(self.image_for(item, '').image.name, main['name'])
        self.assertEqual(self.image_for(item, 'alt').image.name, alt['name'])
        self.assertEqual(item.image.name, main['name'])
        self.assertEqual(item.alt_image.name, alt['name'])

    def test_require_alt_text_is_enforced_through_the_nested_formset(self):
        """
        Render the ``require_alt_text`` error from ``NestedItem.image``
        through both nested formsets.
        """
        template = self.add_form_fields()
        image = self.upload_and_crop(NestedItem.IMAGE_SIZES)
        image['alt_text'] = ''

        payload = dict(template, title="A root")
        payload.update({'section_set-TOTAL_FORMS': '1', 'section_set-INITIAL_FORMS': '0'})
        payload.update(self.section(template, 0, [{'image': image}]))

        response = self.client.post(ADD_URL, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alt text describing the image is required")
        self.assertFalse(NestedRoot.objects.exists())


class NestedDeleteTest(NestedPostTestCase):
    """
    Submit the fields produced by nested-admin's delete cascade.

    ``jquery.djangoformset.js`` ticks the literal ``id_{prefix}-0-DELETE``
    checkbox for every ``.cropduster-form`` inside a deleted row. The POST
    therefore includes DELETE values for the row and its widgets.
    """

    def create_root(self, item_count=2):
        template = self.add_form_fields()
        images = [self.upload_and_crop(NestedItem.IMAGE_SIZES) for _ in range(item_count)]

        payload = dict(template, title="A root")
        payload.update({'section_set-TOTAL_FORMS': '1', 'section_set-INITIAL_FORMS': '0'})
        payload.update(self.section(
            template, 0, [{'image': image} for image in images]))

        self.assertSaved(self.client.post(ADD_URL, payload))
        return NestedRoot.objects.get(), images

    def change_fields(self, root):
        url = "/admin/nested/nestedroot/%s/change/" % root.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return url, form_fields(response.content.decode('utf-8'))

    def test_deleting_a_row_takes_its_image_row_with_it(self):
        root, _ = self.create_root(item_count=2)
        kept, removed = list(root.section_set.get().items.order_by('position'))
        kept_image = self.image_for(kept)

        url, fields = self.change_fields(root)
        fields['section_set-0-items-1-DELETE'] = 'on'
        fields['section_set-0-items-1-image-0-DELETE'] = 'on'
        fields['section_set-0-items-1-alt_image-0-DELETE'] = 'on'

        self.assertSaved(self.client.post(url, fields))

        self.assertFalse(NestedItem.objects.filter(pk=removed.pk).exists())
        self.assertEqual(list(NestedItem.objects.all()), [kept])
        self.assertEqual(list(Image.objects.all()), [kept_image])
        self.assertEqual(
            list(Thumb.objects.values_list('image_id', flat=True).distinct()),
            [kept_image.pk])

    def test_deleting_only_the_widget_leaves_the_row(self):
        """The cropduster DELETE on its own clears the field, not the item."""
        root, _ = self.create_root(item_count=1)
        item = root.section_set.get().items.get()

        url, fields = self.change_fields(root)
        fields['section_set-0-items-0-image-0-DELETE'] = 'on'

        self.assertSaved(self.client.post(url, fields))

        item.refresh_from_db()
        self.assertEqual(list(NestedItem.objects.all()), [item])
        self.assertFalse(Image.objects.exists())
        self.assertFalse(item.image)

    def test_deleting_a_section_takes_its_items_and_their_images(self):
        root, _ = self.create_root(item_count=2)

        url, fields = self.change_fields(root)
        fields['section_set-0-DELETE'] = 'on'
        for index in range(2):
            fields['section_set-0-items-%d-DELETE' % index] = 'on'
            fields['section_set-0-items-%d-image-0-DELETE' % index] = 'on'

        self.assertSaved(self.client.post(url, fields))

        self.assertFalse(NestedSection.objects.exists())
        self.assertFalse(NestedItem.objects.exists())
        self.assertFalse(Image.objects.exists())
