"""
Generate and verify the widget HTML fixtures used by the frontend tests.

The fixtures cover an unbound top-level field, two fields on one saved object,
and a nested inline's empty-form template. Tests also verify the class names,
field names, and element order used by django-nested-admin and downstream
stylesheets or scripts.

Regenerate them with ``pytest tests/test_widget_html.py --write-fixtures``.
"""

import html as html_module
import json as stdlib_json
import os
import re

import django
import lxml.html
import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase, override_settings

import cropduster
from tests.helpers import CropdusterTestCaseMediaMixin
from tests.models import Article, Author


FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'frontend', 'tests', 'fixtures')

#: Normalization rules and Django version used to write the fixtures.
RULES_FILENAME = 'normalize.json'

DJANGO_VERSION = '%d.%d' % django.VERSION[:2]

HAS_GRAPPELLI = 'grappelli' in django_settings.INSTALLED_APPS

TEST_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'img.jpg')

LOCAL_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
#
# Rules are plain regexes over the raw markup, in this order, so that the same
# string transform can be applied anywhere the markup turns up.

#: Django's CSRF token is masked with fresh randomness on every read, so two
#: widgets on one page do not even agree with each other.
CSRF_CONFIG_RE = re.compile(r'(?<=&quot;csrfToken&quot;: &quot;)[^&]*(?=&quot;)')

#: A ``csrfmiddlewaretoken`` input, in case one is rendered inside the
#: widget. Same value, same reason.
CSRF_INPUT_RE = re.compile(r'(?<=name="csrfmiddlewaretoken" value=")[^"]*(?=")')

#: ``.../2026/08/...`` -> ``.../{Y}/{m}/...``. ``upload_to`` patterns contain
#: strftime codes, which expand at upload time.
DATE_PATH_RE = re.compile(r"(?<=/)(?:19|20)\d{2}/\d{2}(?=/)")

#: FileRenderer derives this value from ``date_modified`` on the row created
#: while rendering the fixture.
CACHE_BUSTER_RE = re.compile(r"(?<=\?mod=)\d+")

NORMALIZE_RULES = [
    {
        "name": "CSRF_CONFIG",
        "pattern": CSRF_CONFIG_RE.pattern,
        "replacement": "{CSRF}",
        "why": (
            "django.middleware.csrf.get_token() masks the secret with fresh "
            "randomness per call, so the token in data-config differs between "
            "renders and between widgets."),
    },
    {
        "name": "CSRF_INPUT",
        "pattern": CSRF_INPUT_RE.pattern,
        "replacement": "{CSRF}",
        "why": "Same as CSRF_CONFIG, for a token rendered as a form input.",
    },
    {
        "name": "DATE",
        "pattern": DATE_PATH_RE.pattern,
        "replacement": "{Y}/{m}",
        "why": (
            "upload_to values contain strftime codes (%Y/%m); the expanded "
            "year and month depend on the date the fixture was written."),
    },
    {
        "name": "CACHE_BUSTER",
        "pattern": CACHE_BUSTER_RE.pattern,
        "replacement": "{MOD}",
        "why": (
            "FileRenderer uses the Image or Thumb date_modified timestamp, "
            "which is assigned when the fixture creates its rows."),
    },
]

_SUBSTITUTIONS = [
    (CSRF_CONFIG_RE, "{CSRF}"),
    (CSRF_INPUT_RE, "{CSRF}"),
    (DATE_PATH_RE, "{Y}/{m}"),
    (CACHE_BUSTER_RE, "{MOD}"),
]


def normalize(markup):
    """Replace values that vary between otherwise identical renders."""
    for pattern, replacement in _SUBSTITUTIONS:
        markup = pattern.sub(replacement, markup)
    return markup


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

WIDGET_START_RE = re.compile(
    r'<div class="module cropduster-form nested-inline-form"[^>]*>')
DIV_TAG_RE = re.compile(r'<(/?)div\b[^>]*>', re.IGNORECASE)


def extract_widgets(markup):
    """
    Return each ``.cropduster-form`` without parsing and re-serializing it.

    Slicing retains the bytes rendered by Django instead of applying a parser's
    formatting.
    """
    widgets = []
    for start in WIDGET_START_RE.finditer(markup):
        depth = 0
        for tag in DIV_TAG_RE.finditer(markup, start.start()):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                widgets.append(markup[start.start():tag.end()])
                break
        else:
            raise AssertionError("unbalanced <div> in a .cropduster-form")
    return widgets


def has_class(*names):
    """An XPath predicate matching an element that has all of ``names``."""
    return "".join(
        "[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]" % name
        for name in names)


def parse(markup):
    return lxml.html.fragment_fromstring(markup)


def widget_config(tree):
    """The parsed ``data-config`` of the ``<cropduster-widget>`` in ``tree``."""
    element, = tree.xpath('.//cropduster-widget')
    return stdlib_json.loads(element.get('data-config'))


def prefix_haystack(config):
    """
    ``config`` as JSON, minus the values that are not formset prefixes.

    ``uploadTo`` and the preview URLs are built from the field's ``upload_to``,
    and the test models name theirs after the field they belong to. Their
    overlap with the formset prefix is a property of the fixtures, not the
    widget putting a prefix where one does not belong. ``target.fieldName`` is
    the model field's own name, which a top-level widget's prefix is equal to
    and which no amount of cloning or reordering changes.
    """
    scrubbed = {key: value for key, value in config.items() if key != 'uploadTo'}
    scrubbed['preview'] = {
        key: value for key, value in config['preview'].items()
        if key not in ('url', 'rendererUrl', 'srcset')}
    scrubbed['target'] = {
        key: value for key, value in (config['target'] or {}).items()
        if key != 'fieldName'}
    return stdlib_json.dumps(scrubbed)


class WidgetHtmlTestBase(CropdusterTestCaseMediaMixin, TransactionTestCase):
    """
    Renders through the real admin, because that is the only place the widget's
    context is fully assembled: the bound field, the request, the inline
    formset and the fieldset template all come from it.
    """

    #: The fixtures name primary keys, which are only reproducible from an
    #: empty database.
    reset_sequences = True

    @pytest.fixture(autouse=True)
    def _fixture_options(self, request):
        self.write_fixtures = request.config.getoption("--write-fixtures")

    def setUp(self):
        super().setUp()
        # A signed S3 URL changes on every render. Another tox environment
        # covers the storage backend.
        storages = override_settings(STORAGES=LOCAL_STORAGES)
        storages.enable()
        self.addCleanup(storages.disable)
        user = User.objects.create_superuser("test", "test@test.com", "password")
        self.client = Client()
        self.client.force_login(user)

    def render(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        widgets = extract_widgets(response.content.decode('utf-8'))
        self.assertTrue(widgets, "no .cropduster-form rendered by %s" % url)
        return widgets

    def fixture_metadata(self):
        with open(os.path.join(FIXTURE_DIR, RULES_FILENAME)) as f:
            return stdlib_json.load(f)

    def assert_fixture(self, name, widgets):
        """Pin ``widgets`` against ``frontend/tests/fixtures/{name}.html``."""
        path = os.path.join(FIXTURE_DIR, '%s.html' % name)
        actual = '%s\n%s\n' % (
            '<!-- Generated by tests/test_widget_html.py --write-fixtures '
            'against Django %s. Do not edit. -->' % DJANGO_VERSION,
            '\n\n'.join(normalize(widget) for widget in widgets))

        if self.write_fixtures:
            os.makedirs(FIXTURE_DIR, exist_ok=True)
            with open(path, 'w') as f:
                f.write(actual)
            return

        # The admin and grappelli fieldset templates change independently, so
        # one environment compares bytes and every environment checks selectors.
        if HAS_GRAPPELLI:
            self.skipTest("the fixtures were written without grappelli")
        written_with = self.fixture_metadata()['django']
        if written_with != DJANGO_VERSION:
            self.skipTest(
                "the fixtures were written against Django %s, this is %s"
                % (written_with, DJANGO_VERSION))

        self.assertTrue(
            os.path.exists(path),
            "%s is missing; run pytest --write-fixtures to generate it" % path)
        with open(path) as f:
            self.assertEqual(
                f.read(), actual,
                "%s is stale; re-run with --write-fixtures and review the diff "
                "against the selectors these tests assert" % path)

    # -- the selectors downstream code uses ------------------------------

    def assert_dom_selectors(self, markup, prefix, deletable=False):
        """
        Assert every selector downstream styles and scripts use.

        ``deletable`` is True for a widget whose formset has a saved row, which
        is the only case that renders the DELETE checkbox nested-admin's
        cascade toggles.
        """
        tree = parse(markup)

        self.assertEqual(tree.tag, 'div')
        self.assertEqual(tree.get('id'), '%s-group' % prefix)
        self.assertIn('data-media-url', tree.attrib)
        for name in ('module', 'cropduster-form', 'nested-inline-form'):
            self.assertIn(name, tree.get('class').split())

        # The pk of the cropduster.Image row, and the field the file path
        # round-trips through. Downstream code writes both by name.
        id_input, = tree.xpath('.//input[@name="%s-0-id"]' % prefix)
        self.assertEqual(id_input.get('type'), 'hidden')
        self.assertEqual(id_input.get('id'), 'id_%s-0-id' % prefix)

        data_field, = tree.xpath(
            './/input%s' % has_class('cropduster-data-field', 'cropduster-text-field'))
        self.assertEqual(data_field.get('type'), 'text')
        self.assertEqual(data_field.get('name'), prefix)
        self.assertEqual(data_field.get('id'), 'id_%s' % prefix)
        for attr in ('data-sizes', 'data-preview-url',
                     'data-preview-renderer-url', 'data-preview-srcset',
                     'data-preview-w', 'data-preview-h', 'data-upload-to'):
            self.assertIn(attr, data_field.attrib)

        element, = tree.xpath('.//cropduster-widget')
        self.assertIn('data-config', element.attrib)
        self.assertEqual(element.getparent(), tree)

        link, = tree.xpath(
            './/a%s' % has_class('cropduster-customfield', 'cropduster-upload-form'))
        self.assertIn('data-cropduster-url', link.attrib)
        button, = link.xpath('./div%s' % has_class('cropduster-button'))

        # Document order: the frontend portals into the two server-rendered
        # containers and the sibling selectors of downstream stylesheets run
        # across the include that sits between them.
        order = [child for child in tree.iterchildren()
                 if child in (data_field, element, link)]
        self.assertEqual(order, [data_field, element, link])

        for key in ('TOTAL_FORMS', 'INITIAL_FORMS', 'MIN_NUM_FORMS', 'MAX_NUM_FORMS'):
            self.assertEqual(
                len(tree.xpath('.//input[@name="%s-%s"]' % (prefix, key))), 1, key)

        empty, = tree.xpath('.//div[@id="%s-empty"]' % prefix)
        for name in ('empty-form', 'grp-empty-form', 'last-related'):
            self.assertIn(name, empty.get('class').split())

        self.assertEqual(len(tree.xpath('.//select[@name="%s-0-thumbs"]' % prefix)), 1)

        # One row per field, per rendered form: the saved one and the template.
        # grappelli names the row after the field and the admin prefixes it;
        # downstream styles select both spellings, so both are asserted
        # here.
        row = has_class('grp-row') if HAS_GRAPPELLI else has_class('form-row')
        for field in ('image', 'thumbs', 'caption', 'alt_text', 'attribution',
                      'attribution_link', 'field_identifier'):
            name = field if HAS_GRAPPELLI else 'field-%s' % field
            self.assertEqual(
                len(tree.xpath('.//div%s%s' % (row, has_class(name)))), 2, field)

        self.assertEqual(len(tree.xpath('.//div[@id="%s-0"]' % prefix)), 1)

        if deletable:
            delete, = tree.xpath(
                './/span%s/input[@name="%s-0-DELETE"]' % (has_class('delete'), prefix))
            self.assertEqual(delete.get('type'), 'checkbox')
            self.assertEqual(delete.get('id'), 'id_%s-0-DELETE' % prefix)
        else:
            self.assertEqual(
                len(tree.xpath('.//input[@name="%s-0-DELETE"]' % prefix)), 0)

        group, = tree.xpath(
            './/div%s' % has_class('manual_images', 'cropduster-image-group'))
        thumbs, = group.xpath('./div%s' % has_class('thumbs', 'cropduster-images'))
        self.assertEqual(len(thumbs), 0)

    # -- data-config -------------------------------------------------------

    EXPECTED_CONFIG_KEYS = {
        'sizes', 'uploadTo', 'mediaUrl', 'fieldIdentifier', 'requireAltText',
        'preview', 'urls', 'dialogMode', 'dispatchInputEvents', 'features',
        'target', 'csrfToken', 'debug',
    }

    def assert_config_keys(self, markup, prefix):
        config = widget_config(parse(markup))

        self.assertEqual(set(config), self.EXPECTED_CONFIG_KEYS)
        self.assertEqual(
            set(config['preview']), {'url', 'rendererUrl', 'srcset', 'w', 'h'})
        self.assertEqual(set(config['urls']), {'index', 'upload', 'crop', 'api'})
        self.assertEqual(set(config['features']), {'overrideSources'})
        self.assertEqual(set(config['target']), {'model', 'objectId', 'fieldName'})
        self.assertIsInstance(config['sizes'], list)

        raw = parse(markup).xpath('.//cropduster-widget')[0].get('data-config')

        # nested-admin renames a cloned row by rewriting id/name/for/href/
        # class/onclick on a fixed selector list that <cropduster-widget> is
        # not on, so a prefix baked in here would survive the rename and point
        # at the row it was cloned from.
        self.assertIsNone(
            re.search(r'-(?:\d+|empty|__prefix__)-', raw),
            "data-config contains a formset index: %s" % raw)

        self.assertNotIn(prefix, prefix_haystack(config))


class WidgetHtmlTest(WidgetHtmlTestBase):

    def test_author_add_form(self):
        """A top-level field on an unbound add form."""
        widgets = self.render("/admin/tests/author/add/")
        self.assertEqual(len(widgets), 1)

        self.assert_dom_selectors(widgets[0], 'headshot')
        self.assert_config_keys(widgets[0], 'headshot')
        self.assert_fixture('author_add_headshot', widgets)

    def test_article_change_form(self):
        """
        Two fields on one bound change form, one of them with an image.

        ``alt_image`` has a ``field_identifier``, which keeps two cropduster
        fields on one model from reading each other's rows, and the saved
        image on ``lead_image`` makes the formset render its DELETE checkbox
        and its populated thumbs select.
        """
        article = Article.objects.create(title="Some article")
        cropduster.attach(article, "lead_image", TEST_IMAGE,
                          metadata={"alt_text": "An alt text", "caption": "A caption"})

        widgets = self.render("/admin/tests/article/%s/change/" % article.pk)
        self.assertEqual(len(widgets), 2)

        self.assert_dom_selectors(widgets[0], 'lead_image', deletable=True)
        self.assert_config_keys(widgets[0], 'lead_image')
        self.assert_dom_selectors(widgets[1], 'alt_image')
        self.assert_config_keys(widgets[1], 'alt_image')

        self.assertFalse(widget_config(parse(widgets[0]))['fieldIdentifier'])
        self.assertEqual(widget_config(parse(widgets[1]))['fieldIdentifier'], 'alt')

        lead_tree = parse(widgets[0])
        lead_config = widget_config(lead_tree)
        lead_data, = lead_tree.xpath('.//input[@name="lead_image"]')
        self.assertTrue(
            lead_config['preview']['rendererUrl'].startswith(
                lead_config['preview']['url']))
        self.assertIsNone(lead_config['preview']['srcset'])
        self.assertEqual(
            lead_data.get('data-preview-renderer-url'),
            lead_config['preview']['rendererUrl'])
        self.assertEqual(lead_data.get('data-preview-srcset'), '')

        self.assert_fixture('article_change_lead_and_alt', widgets)

    def test_config_urls_are_reversed(self):
        widgets = self.render("/admin/tests/author/add/")
        self.assertEqual(widget_config(parse(widgets[0]))['urls'], {
            'index': '/cropduster/',
            'upload': '/cropduster/upload/',
            'crop': '/cropduster/crop/',
            'api': '/cropduster/api/v1/',
        })

    def test_config_require_alt_text_follows_the_field(self):
        widgets = self.render("/admin/tests/author/add/")
        self.assertIs(widget_config(parse(widgets[0]))['requireAltText'], False)

    def test_config_csrf_token_is_null_without_a_request(self):
        """
        The key is still there, with ``null`` in it, off the admin.

        ``ModelAdmin`` is what hands the widget a request; a widget built
        straight off the model field has none, and there is no token to mask
        without one. The key stays present because the config is a fixed
        shape the client validates against.
        """
        widget = Author._meta.get_field('headshot').formfield().widget
        self.assertIsNone(widget.request)

        config = widget_config(parse(widget.render('headshot', None)))

        self.assertIn('csrfToken', config)
        self.assertIsNone(config['csrfToken'])

    @override_settings(CROPDUSTER_DIALOG_MODE="window")
    def test_config_dialog_mode_follows_the_setting(self):
        widgets = self.render("/admin/tests/author/add/")
        self.assertEqual(widget_config(parse(widgets[0]))['dialogMode'], 'window')

    @override_settings(CROPDUSTER_DIALOG_MODE="modal")
    def test_config_dialog_mode_can_request_the_modal(self):
        widgets = self.render("/admin/tests/author/add/")
        self.assertEqual(widget_config(parse(widgets[0]))['dialogMode'], 'modal')

    def test_config_target_names_the_field_being_edited(self):
        """
        What makes the API answer from the model rather than from the client.

        The add form has no object yet, which the API reads as "no instance"
        and answers with the field's declared sizes all the same.
        """
        widgets = self.render("/admin/tests/author/add/")

        self.assertEqual(widget_config(parse(widgets[0]))['target'], {
            'model': 'tests.author',
            'objectId': None,
            'fieldName': 'headshot',
        })

    def test_config_target_names_the_object_on_a_change_form(self):
        article = Article.objects.create(title="Some article")

        widgets = self.render("/admin/tests/article/%s/change/" % article.pk)

        self.assertEqual(widget_config(parse(widgets[0]))['target'], {
            'model': 'tests.article',
            'objectId': article.pk,
            'fieldName': 'lead_image',
        })
        self.assertEqual(
            widget_config(parse(widgets[1]))['target']['fieldName'], 'alt_image')

    def test_normalize_rules_are_published(self):
        """The rules the fixtures were written with ship next to them."""
        path = os.path.join(FIXTURE_DIR, RULES_FILENAME)

        if self.write_fixtures:
            os.makedirs(FIXTURE_DIR, exist_ok=True)
            with open(path, 'w') as f:
                stdlib_json.dump(
                    {"django": DJANGO_VERSION, "rules": NORMALIZE_RULES}, f, indent=2)
                f.write('\n')
            return

        published = self.fixture_metadata()
        self.assertEqual(published['rules'], NORMALIZE_RULES)
        self.assertRegex(published['django'], r'^\d+\.\d+$')

    def test_data_config_is_html_escaped(self):
        """
        The attribute is escaped by the template, not marked safe.

        A caption or an ``upload_to`` with a quote in it would otherwise close
        the attribute early.
        """
        widgets = self.render("/admin/tests/author/add/")
        raw = re.search(r'<cropduster-widget data-config="([^"]*)"', widgets[0]).group(1)
        self.assertNotIn('"', raw)
        stdlib_json.loads(html_module.unescape(raw))
