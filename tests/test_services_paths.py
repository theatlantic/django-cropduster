import os
import shutil
import tempfile

from django import test
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage

from cropduster.services.paths import unique_upload_dir
from cropduster.utils import get_upload_foldername


class ListdirlessStorage(Storage):
    """Implement storage without directory listings.

    ``exists()`` uses a set of object names and treats a prefix as present when
    at least one object is stored below it.
    """

    def __init__(self, names=()):
        self.names = set(names)

    def listdir(self, path):
        raise NotImplementedError("This backend doesn't support listdir().")

    def exists(self, name):
        return any(n == name or n.startswith(name + '/') for n in self.names)


class TestUniqueUploadDir(test.SimpleTestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='TEST_UNIQUE_UPLOAD_DIR_')
        self.addCleanup(shutil.rmtree, self.tmpdir)
        self.storage = FileSystemStorage(location=self.tmpdir)

    def test_names_the_directory_after_the_file(self):
        self.assertEqual(
            unique_upload_dir('my img.jpg', 'a/b', storage=self.storage), 'a/b/my_img')

    def test_missing_name_falls_back(self):
        self.assertEqual(
            unique_upload_dir('', 'a/b', storage=self.storage), 'a/b/no_name')

    def test_suffixes_until_unused(self):
        self.storage.save('a/b/my_img/original.jpg', ContentFile(b''))
        self.assertEqual(
            unique_upload_dir('my img.jpg', 'a/b', storage=self.storage), 'a/b/my_img-1')

        self.storage.save('a/b/my_img-1/original.jpg', ContentFile(b''))
        self.assertEqual(
            unique_upload_dir('my img.jpg', 'a/b', storage=self.storage), 'a/b/my_img-2')

    def test_reserves_the_directory(self):
        first = unique_upload_dir(
            'img.jpg', 'not/created/yet', storage=self.storage)
        second = unique_upload_dir(
            'img.jpg', 'not/created/yet', storage=self.storage)

        self.assertEqual(first, 'not/created/yet/img')
        self.assertEqual(second, 'not/created/yet/img-1')
        self.assertTrue(os.path.isdir(self.storage.path(first)))
        self.assertTrue(os.path.isdir(self.storage.path(second)))

    def test_strftime_upload_to(self):
        import datetime

        expected = datetime.datetime.now().strftime('%Y/%m')
        self.assertEqual(
            unique_upload_dir('img.jpg', '%Y/%m', storage=self.storage),
            '%s/img' % expected)

    def test_no_upload_to_is_the_storage_root(self):
        """The directory is at the storage root when ``upload_to`` is ``None``.

        Cropduster 4.x passed ``str(None)`` to ``strftime`` and placed these
        files in a directory named ``None``. No caller uses that directory by
        name.
        """
        self.assertEqual(unique_upload_dir('img.jpg', None, storage=self.storage), 'img')

    def test_callable_upload_to(self):
        self.assertEqual(
            unique_upload_dir('img.jpg', lambda instance, name: 'fixed/%s' % name,
                              storage=self.storage),
            'fixed/img')

    def test_max_length_clamps_the_directory_name(self):
        name = ('x' * 40) + '.jpg'
        path = unique_upload_dir(name, 'a/b', storage=self.storage, max_length=20)
        self.assertEqual(len(path), 20)
        self.assertTrue(path.startswith('a/b/xxx'))

    def test_max_length_keeps_the_uniqueness_suffix(self):
        name = ('x' * 40) + '.jpg'
        taken = unique_upload_dir(name, 'a/b', storage=self.storage, max_length=20)
        self.storage.save('%s/original.jpg' % taken, ContentFile(b''))

        path = unique_upload_dir(name, 'a/b', storage=self.storage, max_length=20)
        self.assertNotEqual(path, taken)
        self.assertTrue(path.endswith('-1'))
        self.assertEqual(len(path), 20)


class TestUniqueUploadDirWithoutListdir(test.SimpleTestCase):

    def test_falls_back_to_exists(self):
        storage = ListdirlessStorage(['a/b/my_img/original.jpg'])
        self.assertEqual(unique_upload_dir('my img.jpg', 'a/b', storage=storage), 'a/b/my_img-1')

    def test_unused_name_is_returned_as_is(self):
        storage = ListdirlessStorage()
        self.assertEqual(unique_upload_dir('my img.jpg', 'a/b', storage=storage), 'a/b/my_img')


class TestGetUploadFoldernameWrapper(test.SimpleTestCase):

    def test_delegates(self):
        import datetime

        expected = datetime.datetime.now().strftime('%Y/%m')
        self.assertEqual(get_upload_foldername('img.jpg'), '%s/img' % expected)
