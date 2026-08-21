"""
Render Cropduster fields in django-nested-admin's empty-form templates.

These templates cover two cases not present in a normal admin form. The
custom element must not mount while its prefix contains ``-empty-`` or
``__prefix__``. Also, ``data-config`` must not contain a formset prefix,
because nested-admin clones the attribute without rewriting it when a new row
is added.
"""

import json as stdlib_json

from tests.nested.models import NestedItem, NestedRoot, NestedSection
from tests.test_widget_html import WidgetHtmlTestBase, parse, widget_config


ADD_URL = "/admin/nested/nestedroot/add/"

#: The two placeholders replaced by nested-admin's ``add()``. Container IDs
#: contain ``-empty`` and field names contain ``__prefix__``.
EMPTY_PREFIX = 'section_set-empty-items-__prefix__'


class NestedWidgetHtmlTest(WidgetHtmlTestBase):

    def test_empty_form_template(self):
        widgets = self.render(ADD_URL)
        self.assertEqual(len(widgets), 2)

        for widget, field in zip(widgets, ('image', 'alt_image')):
            prefix = '%s-%s' % (EMPTY_PREFIX, field)
            self.assert_dom_selectors(widget, prefix)
            self.assert_config_keys(widget, prefix)

        self.assertIs(widget_config(parse(widgets[0]))['requireAltText'], True)
        self.assertEqual(widget_config(parse(widgets[1]))['fieldIdentifier'], 'alt')

        self.assert_fixture('nested_empty_item', widgets)

    def test_config_is_identical_across_prefixes(self):
        """
        The saved row and both empty-form templates differ only in object ID.

        nested-admin does not rewrite ``data-config`` while cloning a row, so
        all prefix-dependent values must be derived from the surrounding
        formset. ``target.objectId`` is intentionally different: saved rows
        name their object and templates use ``null``.
        """
        root = NestedRoot.objects.create(title="A root")
        section = NestedSection.objects.create(root=root, name="A section", position=0)
        item = NestedItem.objects.create(section=section, position=0)

        widgets = self.render("/admin/nested/nestedroot/%s/change/" % root.pk)
        configs = {}
        object_ids = {}
        for widget in widgets:
            tree = parse(widget)
            prefix = tree.get('id')[:-len('-group')]
            field = prefix.rsplit('-', 1)[-1]
            config = widget_config(tree)
            # Django masks the token for every render, so compare the
            # remaining configuration.
            config.pop('csrfToken')
            object_ids[prefix] = config['target'].pop('objectId')
            configs.setdefault(field, {})[prefix] = stdlib_json.dumps(
                config, sort_keys=True)

        self.assertEqual(
            sorted(configs), ['alt_image', 'image'],
            "expected both fields of the item row")
        for field, by_prefix in configs.items():
            # Compare the saved row with the inner and outer templates.
            self.assertGreaterEqual(len(by_prefix), 2, field)
            self.assertEqual(len(set(by_prefix.values())), 1, sorted(by_prefix))

        # Saved rows name their object. Templates use ``null`` because a
        # cloned row has not been saved.
        for prefix, object_id in object_ids.items():
            expected = None if ('empty' in prefix or '__prefix__' in prefix) else item.pk
            self.assertEqual(object_id, expected, prefix)
