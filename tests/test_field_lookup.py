import warnings

from django import test

from cropduster.fields import CropDusterField, CropDusterImageField
from cropduster.utils.fields import (
    get_cropduster_field, get_cropduster_fields, get_image_column_field)

from .models import (
    Article, Author, MultipleFieldsInheritanceChild, MultipleFieldsInheritanceParent)


class TestGetCropDusterFields(test.SimpleTestCase):

    def test_single_field(self):
        fields = get_cropduster_fields(Author)
        self.assertEqual([f.name for f in fields], ['headshot'])
        self.assertIsInstance(fields[0], CropDusterField)

    def test_two_fields_on_one_model(self):
        self.assertEqual(
            sorted(f.name for f in get_cropduster_fields(Article)),
            ['alt_image', 'lead_image'])

    def test_inherited_fields(self):
        self.assertEqual(
            sorted(f.name for f in get_cropduster_fields(MultipleFieldsInheritanceChild)),
            ['image', 'image2'])


class TestGetCropDusterField(test.SimpleTestCase):

    def test_by_field_identifier(self):
        self.assertEqual(
            get_cropduster_field(Article, field_identifier='').name, 'lead_image')
        self.assertEqual(
            get_cropduster_field(Article, field_identifier='alt').name, 'alt_image')

    def test_by_name(self):
        self.assertEqual(get_cropduster_field(Article, name='alt_image').field_identifier, 'alt')

    def test_no_criteria_returns_the_only_field(self):
        self.assertEqual(get_cropduster_field(Author).name, 'headshot')

    def test_no_match_returns_none(self):
        self.assertIsNone(get_cropduster_field(Article, field_identifier='nope'))
        self.assertIsNone(get_cropduster_field(Article, name='nope'))

    def test_inherited_field_identifiers(self):
        self.assertEqual(
            get_cropduster_field(MultipleFieldsInheritanceChild, field_identifier='').name,
            'image')
        self.assertEqual(
            get_cropduster_field(MultipleFieldsInheritanceChild, field_identifier='2').name,
            'image2')


class TestGetImageColumnField(test.SimpleTestCase):

    def test_returns_the_contributed_file_field(self):
        field = get_cropduster_field(Article, field_identifier='alt')
        column = get_image_column_field(Article, field)
        self.assertIsInstance(column, CropDusterImageField)
        self.assertEqual(column.attname, 'alt_image')
        self.assertIs(column.model, Article)

    def test_inherited_column_belongs_to_the_parent(self):
        """The column of an inherited field belongs to the parent model.

        Multi-table inheritance copies the private field onto the child, but
        the database column remains on the parent, so updates must go through
        the parent field.
        """
        field = get_cropduster_field(MultipleFieldsInheritanceChild, field_identifier='')
        column = get_image_column_field(MultipleFieldsInheritanceChild, field)
        self.assertEqual(column.attname, 'image')
        self.assertIs(column.model, MultipleFieldsInheritanceParent)

    def test_child_column_belongs_to_the_child(self):
        field = get_cropduster_field(MultipleFieldsInheritanceChild, field_identifier='2')
        column = get_image_column_field(MultipleFieldsInheritanceChild, field)
        self.assertEqual(column.attname, 'image2')
        self.assertIs(column.model, MultipleFieldsInheritanceChild)


class TestDeprecatedAlias(test.SimpleTestCase):

    def test_still_importable_and_warns(self):
        from cropduster.forms import get_cropduster_field_on_model

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            field = get_cropduster_field_on_model(Article, 'alt')

        self.assertEqual(field.name, 'alt_image')
        self.assertEqual([w.category for w in caught], [DeprecationWarning])
