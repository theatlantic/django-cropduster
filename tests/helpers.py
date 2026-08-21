from io import open
import contextlib
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

#: The modal's shadow host, inserted into ``document.body`` of the admin page.
MODAL_HOST = 'cropduster-dialog'

#: The modal host while its ``data-state`` is ``open``.
OPEN_MODAL_HOST = 'cropduster-dialog[data-state="open"]'

#: The full-page or popup dialog's shadow host in ``cropduster/upload.html``.
PAGE_HOST = '#cropduster-app'

#: The dialog host for the active presentation.
#:
#: A modal inserts its host into the page containing the widget.
#: ``upload.html`` renders the other host in a popup or iframe. Ignore a modal
#: whose ``data-state`` is no longer ``open``.
_HOST_JS = """
var host = document.querySelector('%s') || document.querySelector('%s');
""" % (OPEN_MODAL_HOST, PAGE_HOST)

#: Return one element from the dialog's shadow root, or ``null`` before the
#: dialog has rendered.
#:
#: This uses ``execute_script`` instead of Selenium 4's ``shadow_root`` because
#: it can return ``null`` while waiting and accepts selectors such as
#: ``:not(.disabled)`` that Selenium's ``ShadowRoot`` search rejects.
_FIND_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
return host.shadowRoot.querySelector(arguments[0]);
"""

_FIND_ALL_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return []; }
return Array.prototype.slice.call(host.shadowRoot.querySelectorAll(arguments[0]));
"""

_VALUE_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
return el ? el.value : null;
"""

_TEXT_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
return el ? el.textContent : null;
"""

_RECT_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
if (!el) { return null; }
var rect = el.getBoundingClientRect();
return {
    "x": rect.left, "y": rect.top,
    "width": rect.width, "height": rect.height};
"""

#: Sample a dialog button's two disabled signals together.
_SIGNALS_SCRIPT = _HOST_JS + """
if (!host || !host.shadowRoot) { return null; }
var el = host.shadowRoot.querySelector(arguments[0]);
if (!el) { return null; }
return {
    "value": el.value,
    "attribute": el.hasAttribute("disabled"),
    "class": el.classList.contains("disabled")};
"""

#: Whether the dialog app has rendered into its shadow root.
_RENDERED_SCRIPT = _HOST_JS + """
return !!(host && host.shadowRoot && host.shadowRoot.firstElementChild);
"""

#: Record every state of ``css`` until the test reads the samples.
#:
#: A crop can finish between Selenium polls, so a MutationObserver records
#: transient states. It watches the whole shadow root because React may replace
#: the button instead of updating the existing element.
_WATCH_SIGNALS_SCRIPT = _HOST_JS + """
var root = host.shadowRoot;
var css = arguments[0];
var samples = [];
window.__cropdusterSignals = samples;
var sample = function() {
    var el = root.querySelector(css);
    samples.push(el ? {
        "value": el.value,
        "attribute": el.hasAttribute("disabled"),
        "class": el.classList.contains("disabled")} : null);
};
sample();
new MutationObserver(sample).observe(
    root, {attributes: true, childList: true, subtree: true});
"""

#: Record the sizes of two elements after every relevant DOM change.
#:
#: The reducer can correct an initial render before the next Selenium poll, so
#: the page records the intermediate sizes.
_WATCH_RECTS_SCRIPT = _HOST_JS + """
var root = host.shadowRoot;
var selectors = arguments[0];
var samples = [];
window.__cropdusterRects = samples;
var sample = function() {
    var measured = selectors.map(function (css) {
        var el = root.querySelector(css);
        if (!el) { return null; }
        var rect = el.getBoundingClientRect();
        return {"width": rect.width, "height": rect.height};
    });
    samples.push(measured);
};
sample();
new MutationObserver(sample).observe(
    root, {attributes: true, childList: true, subtree: true});
"""

#: Return the ``data-state`` of every modal host on the page.
_MODAL_STATES_SCRIPT = """
return Array.prototype.map.call(
    document.querySelectorAll('%s'),
    function (el) { return el.getAttribute('data-state'); });
""" % MODAL_HOST


class CropDusterDialogMixin(object):
    """
    Helpers for interacting with the crop dialog through Selenium.

    The dialog controls are inside an open shadow root, so every internal
    selector must begin at the active host. Modal controls are in the admin
    page; full-page and popup controls are in their own browsing contexts.
    These helpers select the correct host after the caller has entered that
    context.
    """

    #: Seconds to wait for a dialog element. Short probes can override this
    #: without changing Selenium's default timeout.
    dialog_timeout = 20

    #: The presentation expected by :meth:`crop_dialog`.
    #:
    #: The default ``"auto"`` setting selects ``"modal"`` at this viewport.
    #: :mod:`tests.test_admin_fullpage` sets ``"window"`` for the popup tests.
    dialog_mode = "modal"

    def dialog_query(self, css):
        """Return the first matching dialog element, or ``None``."""
        return self.selenium.execute_script(_FIND_SCRIPT, css)

    def dialog_find_all(self, css):
        """Return all matching dialog elements in document order."""
        return self.selenium.execute_script(_FIND_ALL_SCRIPT, css)

    def wait_for_dialog(self, timeout=None):
        """Block until the dialog app has rendered into its shadow root."""
        self.wait_until(
            lambda d: d.execute_script(_RENDERED_SCRIPT),
            timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for the crop dialog to render")

    def modal_states(self):
        """Return each modal host's ``data-state`` in document order."""
        return self.selenium.execute_script(_MODAL_STATES_SCRIPT)

    def wait_for_modal(self, timeout=None):
        """
        Block until exactly one open modal has rendered.

        Check the host count during the wait so a second host cannot make the
        dialog selectors ambiguous.
        """
        self.wait_until(
            lambda d: self.modal_states() == ['open'] and d.execute_script(
                _RENDERED_SCRIPT),
            timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for one open crop modal (states: %r)" % (
                self.modal_states(),))

    def wait_for_modal_closed(self, timeout=None):
        """Block until no modal host has ``data-state="open"``."""
        self.wait_until(
            lambda d: 'open' not in self.modal_states(),
            timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for the crop modal to close (states: %r)" % (
                self.modal_states(),))

    def dialog_find(self, css, timeout=None, visible=True):
        """
        Wait for one element inside the dialog and return it.

        Set ``visible=False`` for elements the test must use while hidden,
        such as the file input behind the image chooser.
        """
        found = []

        def ready(driver):
            el = self.dialog_query(css)
            if el is None:
                return False
            if visible and not _displayed(el):
                return False
            found.append(el)
            return True

        self.wait_until(
            ready, timeout=timeout if timeout is not None else self.dialog_timeout,
            message="Timeout waiting for dialog element at selector='%s'" % css)
        return found[-1]

    def dialog_click(self, css, timeout=None, settle=False):
        """
        Click a dialog control once it is enabled.

        The control must have neither a ``disabled`` attribute nor a
        ``disabled`` class. When ``settle`` is true, wait for the control to
        become disabled before returning so the next crop-step click does not
        reach the same step.
        """
        from selenium.common.exceptions import StaleElementReferenceException

        def click(driver):
            el = self.dialog_query(css)
            if el is None or not _displayed(el) or not _enabled(el):
                return False
            try:
                el.click()
            except StaleElementReferenceException:
                # The dialog re-rendered between finding the control and
                # clicking it; the next poll finds the replacement.
                return False
            return True

        self.wait_until(
            click, timeout=timeout if timeout is not None else self.dialog_timeout,
            message=(
                "Timeout waiting for clickable dialog element at selector='%s'" % css))

        if settle:
            self._wait_until_busy(css)

    def _wait_until_busy(self, css, timeout=2):
        """
        Wait briefly for a clicked control to disable itself.

        This reduces the chance that a second click arrives before the first
        state update. A control that stays enabled, or a window that closes
        after the final crop, does not make this helper fail.
        """
        from selenium.common.exceptions import TimeoutException, WebDriverException

        def busy(driver):
            try:
                el = self.dialog_query(css)
            except WebDriverException:
                return True
            return el is None or not _enabled(el)

        try:
            self.wait_until(busy, timeout=timeout)
        except (TimeoutException, WebDriverException):
            pass

    def dialog_send_keys(self, css, value, timeout=None):
        """
        Type into a dialog field, including a file input the dialog hides.

        If Chrome rejects ``send_keys`` because the file input is hidden,
        expose the input for the duration of the call.
        """
        from selenium.common.exceptions import ElementNotInteractableException

        el = self.dialog_find(css, timeout=timeout, visible=False)
        try:
            el.send_keys(value)
        except ElementNotInteractableException:
            self.selenium.execute_script(
                "arguments[0].style.setProperty('display', 'block', 'important');"
                "arguments[0].style.setProperty('visibility', 'visible', 'important');"
                "arguments[0].style.setProperty('opacity', '1', 'important');"
                "arguments[0].style.setProperty('width', 'auto', 'important');"
                "arguments[0].style.setProperty('height', 'auto', 'important');",
                el)
            el.send_keys(value)
        return el

    def dialog_upload(self, value, timeout=None):
        """Select an image and wait until the dialog enters the crop stage."""
        self.dialog_send_keys('#id_image', value, timeout=timeout)
        return self.dialog_find('#image-container', timeout=timeout)

    def dialog_can_commit(self):
        """Return whether every crop is populated and the dialog can save."""
        return bool(self.selenium.execute_script(
            "return !!(window.CropDusterDialog"
            " && window.CropDusterDialog.canCommit"
            " && window.CropDusterDialog.canCommit());"))

    def dialog_populate_all_crops(self):
        """Visit every configured crop so each one has editable geometry."""
        total = int(self.dialog_text('#thumb-total-count') or 0)
        for index in range(total):
            self.dialog_click('#crop-preview-%d' % index)
        self.wait_until(
            lambda d: self.dialog_can_commit(),
            timeout=self.dialog_timeout,
            message="Timeout waiting for every crop to be populated")

    def dialog_save(self):
        """Populate every crop and invoke the dialog's single Save action."""
        self.dialog_populate_all_crops()
        self.dialog_click('#crop-button')

    def dialog_commit(self):
        """
        Save the complete crop set through the dialog's imperative API.

        CKEditor's OK button calls this API. Standalone mode hides the dialog's
        crop button, so its host provides the button and calls the dialog
        action.
        """
        self.wait_until(
            lambda d: self.dialog_can_commit(),
            timeout=self.dialog_timeout,
            message="Timeout waiting for the dialog to be ready to save")
        self.selenium.execute_script("window.CropDusterDialog.commit();")

    def dialog_value(self, css):
        """Return a dialog field's value, or ``None`` if it is absent."""
        return self.selenium.execute_script(_VALUE_SCRIPT, css)

    def dialog_text(self, css):
        """Return a dialog element's text, or ``None`` if it is absent."""
        return self.selenium.execute_script(_TEXT_SCRIPT, css)

    def dialog_rect(self, css):
        """Return a dialog element's viewport rect, or ``None`` if absent."""
        return self.selenium.execute_script(_RECT_SCRIPT, css)

    def dialog_signals(self, css):
        """Return a control's value, ``disabled`` attribute, and class."""
        return self.selenium.execute_script(_SIGNALS_SCRIPT, css)

    def dialog_watch_signals(self, css):
        """Start recording ``dialog_signals(css)`` on every DOM change."""
        self.selenium.execute_script(_WATCH_SIGNALS_SCRIPT, css)

    def dialog_recorded_signals(self):
        """Return the signals recorded by ``dialog_watch_signals`` so far."""
        return self.selenium.execute_script("return window.__cropdusterSignals;")

    def dialog_watch_rects(self, *selectors):
        """Start recording the size of each of ``selectors`` on every change."""
        self.selenium.execute_script(_WATCH_RECTS_SCRIPT, list(selectors))

    def dialog_recorded_rects(self):
        """Return the sizes recorded by ``dialog_watch_rects`` so far."""
        return self.selenium.execute_script("return window.__cropdusterRects;")

    def dialog_state(self):
        """Return the dialog state through the handle used by CKEditor."""
        return self.selenium.execute_script(
            "return window.CropDusterDialog && window.CropDusterDialog.state;")

    @contextlib.contextmanager
    def crop_dialog(self):
        """
        Enter the dialog opened by the upload button.

        A modal remains in the current page and removes itself after the final
        crop. Window mode opens ``upload.html`` in a popup, which closes after
        passing the result back to its opener.
        """
        if self.dialog_mode == 'window':
            with self.switch_to_popup_window():
                self.wait_for_dialog()
                yield
            return

        self.wait_for_modal()
        yield
        self.wait_for_modal_closed()


def _displayed(el):
    from selenium.common.exceptions import StaleElementReferenceException

    try:
        return el.is_displayed()
    except StaleElementReferenceException:
        return False


def _enabled(el):
    """
    Return whether a dialog control can be clicked.

    Buttons use both the ``disabled`` attribute, for the browser and assistive
    technology, and the ``disabled`` class read by the CKEditor plugin and
    downstream stylesheets. Both must indicate that the button is enabled.
    """
    from selenium.common.exceptions import StaleElementReferenceException

    try:
        return el.is_enabled() and 'disabled' not in (el.get_attribute('class') or '').split()
    except StaleElementReferenceException:
        return False


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

    def create_upload_file(self, width, height, name='original.jpg'):
        """
        Create an image file of the requested dimensions for a browser upload.

        Unlike ``create_unique_image()``, this returns a local path rather than
        populating an existing model field.
        """
        directory = tempfile.mkdtemp(prefix='TEST_UPLOAD_')
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, name)
        PIL.Image.new('RGB', (width, height), (109, 121, 145)).save(path)
        return path

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
