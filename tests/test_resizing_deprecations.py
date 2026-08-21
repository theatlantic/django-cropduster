import warnings

from django import test

from cropduster.resizing import Size, _warn_retina_deprecated
from cropduster.utils import json


class TestRetinaDeprecation(test.SimpleTestCase):

    def setUp(self):
        _warn_retina_deprecated.cache_clear()
        self.addCleanup(_warn_retina_deprecated.cache_clear)

    def test_retina_warns(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            size = Size('main', w=100, h=50, retina=True)

        self.assertEqual([w.category for w in caught], [DeprecationWarning])
        self.assertIn('retina', str(caught[0].message))
        self.assertTrue(size.retina)

    def test_warns_only_once(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Size('a', retina=True)
            Size('b', retina=True)

        self.assertEqual(len(caught), 1)

    def test_no_warning_without_retina(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Size('main', w=100, h=50)
            Size('main', w=100, h=50, retina=0)

        self.assertEqual(caught, [])

    def test_serialize_still_emits_the_key(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertEqual(Size('a', retina=True).__serialize__()['retina'], 1)
        self.assertEqual(Size('a').__serialize__()['retina'], 0)

    def test_deserialization_still_accepts_the_key(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            sizes = json.loads(json.dumps([Size('a', retina=True)]))

        self.assertEqual(len(sizes), 1)
        self.assertTrue(sizes[0].retina)
