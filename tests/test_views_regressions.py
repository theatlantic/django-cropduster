from django import test

from cropduster.models import Thumb
from cropduster.views.utils import FakeQuerySet


class TestFakeQuerySet(test.SimpleTestCase):

    def test_iterates(self):
        objs = [Thumb(name='a'), Thumb(name='b')]
        fake = FakeQuerySet(objs, Thumb.objects.none())
        self.assertEqual([thumb.name for thumb in fake], ['a', 'b'])

    def test_iterating_twice_restarts(self):
        fake = FakeQuerySet([Thumb(name='a')], Thumb.objects.none())
        self.assertEqual(len(list(fake)), 1)
        self.assertEqual(len(list(fake)), 1)

    def test_len_and_getitem(self):
        objs = [Thumb(name='a'), Thumb(name='b')]
        fake = FakeQuerySet(objs, Thumb.objects.none())
        self.assertEqual(len(fake), 2)
        self.assertIs(fake[1], objs[1])
