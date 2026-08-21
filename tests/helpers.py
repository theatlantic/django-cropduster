from io import open
import tempfile
import os
import shutil
import uuid

import PIL.Image

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.test import override_settings

from .utils import repr_rgb


PATH = os.path.split(__file__)[0]
ORIG_IMG_PATH = os.path.join(PATH, 'data')

FILESYSTEM_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


_PAGE_HOST_JS = """
var host = document.querySelector('#cropduster-app');
"""

_DIALOG_FIND_SCRIPT = _PAGE_HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
return host.shadowRoot.querySelector(arguments[0]);
"""

_DIALOG_RENDERED_SCRIPT = _PAGE_HOST_JS + """
return !!(host && host.shadowRoot && host.shadowRoot.firstElementChild);
"""

_DIALOG_VALUE_SCRIPT = _PAGE_HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
return el ? el.value : null;
"""

_DIALOG_TEXT_SCRIPT = _PAGE_HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
return el ? el.textContent : null;
"""

_DIALOG_RECT_SCRIPT = _PAGE_HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
if (!el) { return null; }
var rect = el.getBoundingClientRect();
return {
    "x": rect.left, "y": rect.top,
    "width": rect.width, "height": rect.height};
"""


def _displayed(element):
    from selenium.common.exceptions import StaleElementReferenceException

    try:
        return element.is_displayed()
    except StaleElementReferenceException:
        return False


def _enabled(element):
    from selenium.common.exceptions import StaleElementReferenceException

    try:
        classes = (element.get_attribute('class') or '').split()
        return element.is_enabled() and 'disabled' not in classes
    except StaleElementReferenceException:
        return False


class CropDusterDialogMixin(object):
    """Find controls inside the page dialog's open shadow root."""

    dialog_timeout = 10

    def dialog_query(self, css):
        return self.selenium.execute_script(_DIALOG_FIND_SCRIPT, css)

    def wait_for_dialog(self, timeout=None):
        self.wait_until(
            lambda driver: driver.execute_script(_DIALOG_RENDERED_SCRIPT),
            timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for the crop dialog to render")

    def dialog_find(self, css, timeout=None, visible=True):
        found = []

        def ready(_driver):
            element = self.dialog_query(css)
            if element is None or (visible and not _displayed(element)):
                return False
            found.append(element)
            return True

        self.wait_until(
            ready, timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for dialog element at selector='%s'" % css)
        return found[-1]

    def dialog_click(self, css, timeout=None):
        from selenium.common.exceptions import StaleElementReferenceException

        def click(_driver):
            element = self.dialog_query(css)
            if element is None or not _displayed(element) or not _enabled(element):
                return False
            try:
                element.click()
            except StaleElementReferenceException:
                return False
            return True

        self.wait_until(
            click, timeout=timeout if timeout is not None else self.dialog_timeout,
            message=(
                "Timeout waiting for clickable dialog element at selector='%s'" % css))

    def dialog_send_keys(self, css, value, timeout=None):
        from selenium.common.exceptions import ElementNotInteractableException

        element = self.dialog_find(css, timeout=timeout, visible=False)
        try:
            element.send_keys(value)
        except ElementNotInteractableException:
            self.selenium.execute_script(
                "arguments[0].style.setProperty('display', 'block', 'important');"
                "arguments[0].style.setProperty('visibility', 'visible', 'important');"
                "arguments[0].style.setProperty('opacity', '1', 'important');"
                "arguments[0].style.setProperty('width', 'auto', 'important');"
                "arguments[0].style.setProperty('height', 'auto', 'important');",
                element)
            element.send_keys(value)
        return element

    def dialog_value(self, css):
        return self.selenium.execute_script(_DIALOG_VALUE_SCRIPT, css)

    def dialog_text(self, css):
        return self.selenium.execute_script(_DIALOG_TEXT_SCRIPT, css)

    def dialog_rect(self, css):
        return self.selenium.execute_script(_DIALOG_RECT_SCRIPT, css)

    def dialog_upload(self, value, timeout=None):
        self.dialog_send_keys('#id_image', value, timeout=timeout)
        return self.dialog_find('#image-container', timeout=timeout)

    def dialog_can_commit(self):
        return bool(self.selenium.execute_script(
            "return !!(window.CropDusterDialog"
            " && window.CropDusterDialog.canCommit"
            " && window.CropDusterDialog.canCommit());"))

    def dialog_populate_all_crops(self):
        total = int(self.dialog_text('#thumb-total-count') or 0)
        for index in range(total):
            self.dialog_click('#crop-preview-%d' % index)
        self.wait_until(
            lambda d: self.dialog_can_commit(),
            timeout=self.dialog_timeout,
            message="Timeout waiting for every crop to be populated")

    def dialog_save(self):
        self.dialog_populate_all_crops()
        self.dialog_click('#crop-button')


class CropdusterTestCaseMediaMixin(CropDusterDialogMixin):
    def __call__(self, result=None):
        testMethod = getattr(self, self._testMethodName)
        skipped = (
            getattr(self.__class__, "__unittest_skip__", False) or
            getattr(testMethod, "__unittest_skip__", False)
        )
        if not skipped:
            self._instance_pre_setup()
        return super().__call__(result)

    def _instance_pre_setup(self):
        self.temp_media_root = tempfile.mkdtemp(prefix='TEST_MEDIA_ROOT_')
        self.override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.override.enable()

    def _post_teardown(self):
        if hasattr(default_storage, 'bucket'):
            default_storage.bucket.objects.filter(Prefix=default_storage.location).delete()
        shutil.rmtree(self.temp_media_root)
        self.override.disable()
        super(CropdusterTestCaseMediaMixin, self)._post_teardown()

    def setUp(self):
        super(CropdusterTestCaseMediaMixin, self).setUp()

        random = uuid.uuid4().hex
        self.TEST_IMG_DIR = ORIG_IMG_PATH
        self.TEST_IMG_DIR_RELATIVE = os.path.join(random, 'data')

    def assertImageColorEqual(self, element, image):
        self.selenium.execute_script('arguments[0].scrollIntoView()', element)
        scroll_top = -1 * self.selenium.execute_script(
            'return document.body.getBoundingClientRect().top')
        tmp_file = tempfile.NamedTemporaryFile(suffix='.png')
        pixel_density = self.selenium.execute_script('return window.devicePixelRatio') or 1
        x1 = int(round(element.location['x'] + (element.size['width'] // 2.0)))
        y1 = int(round(element.location['y'] - scroll_top + (element.size['height'] // 2.0)))

        image_path = os.path.join(os.path.dirname(__file__), 'data', image)
        ref_im = PIL.Image.open(image_path).convert('RGB')
        w, h = ref_im.size
        x2, y2 = int(round(w // 2.0)), int(round(h // 2.0))
        ref_rgb = ref_im.getpixel((x2, y2))
        ref_im.close()

        def get_screenshot_rgb():
            if not self.selenium.save_screenshot(tmp_file.name):
                raise Exception("Failed to save screenshot")
            im = PIL.Image.open(tmp_file.name).convert('RGB')
            rgb = im.getpixel((x1 * pixel_density, y1 * pixel_density))
            im.close()
            return rgb

        self.wait_until(
            lambda d: get_screenshot_rgb() == ref_rgb,
            message=(
                "Colors differ: %s != %s" % (repr_rgb(ref_rgb), repr_rgb(get_screenshot_rgb()))))

    def create_unique_image(self, image):
        image_uuid = uuid.uuid4().hex

        ext = os.path.splitext(image)[1]
        image_name = os.path.join(
            self.TEST_IMG_DIR_RELATIVE, image_uuid, "original%s" % ext)
        preview_image_name = os.path.join(                                                                            
            self.TEST_IMG_DIR_RELATIVE, image_uuid, "_preview%s" % ext) 

        with open("%s/%s" % (ORIG_IMG_PATH, image), mode='rb') as f:
            default_storage.save(image_name, ContentFile(f.read()))

        with open("%s/%s" % (ORIG_IMG_PATH, image), mode='rb') as f:
            default_storage.save(preview_image_name, ContentFile(f.read()))

        return image_name
