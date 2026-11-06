from __future__ import absolute_import

import os

from django.core.files.storage import default_storage
from django.test import override_settings
from django.test.testcases import LiveServerThread
from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

from cropduster.models import Image, Size
from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author, OptionalSizes


class TestAdmin(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):
    """
    Run the admin widget and dialog against the default modal presentation.

    At this viewport size, ``CROPDUSTER_DIALOG_MODE="auto"`` selects the modal.
    :mod:`tests.test_admin_fullpage` inherits these scenarios and reruns them
    with the popup, so the assertions here concentrate on the formset and
    database results rather than presentation-specific behavior.
    """

    root_urlconf = 'tests.urls'
    server_thread_class = LiveServerThread
    dialog_mode = 'modal'

    @class_property
    def available_apps(cls):
        apps = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.messages',
            'django.contrib.sessions',
            'django.contrib.sites',
            'django.contrib.staticfiles',
            'django.contrib.admin',
            'generic_plus',
            'cropduster',
            'tests',
            'tests.standalone',
            'selenosis',
        ]
        if cls.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    def test_addform_single_image(self):
        from selenium.webdriver.common.by import By

        self.load_admin(Author)

        browser = self.selenium
        browser.find_element(By.ID, 'id_name').send_keys('Mark Twain')
        with self.clickable_selector('#headshot-group .cropduster-button') as el:
            el.click()

        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_save()

        self.save_form()

        author = Author.objects.all()[0]
        sizes = list(Size.flatten(Author.HEADSHOT_SIZES))
        self.assertTrue(bool(author.headshot.name))

        image = author.headshot.related_object
        thumbs = image.thumbs.all()
        self.assertEqual(len(thumbs), len(sizes))
        main_thumb = image.thumbs.get(name='main')
        self.assertEqual(main_thumb.to_dict(), {
            'reference_thumb_id': None,
            'name': 'main',
            'width': 220,
            'height': 180,
            'crop_w': 674,
            'crop_h': 551,
            'crop_x': 0,
            'crop_y': 125,
            'image_id': image.pk,
            'id': main_thumb.pk,
        })
        auto_thumb = image.thumbs.get(name='thumb')
        self.assertEqual(auto_thumb.to_dict(), {
            'reference_thumb_id': main_thumb.pk,
            'name': 'thumb',
            'width': 110,
            'height': 90,
            'crop_w': None,
            'crop_h': None,
            'crop_x': None,
            'crop_y': None,
            'image_id': image.pk,
            'id': auto_thumb.pk,
        })
        self.assertTrue(default_storage.exists(auto_thumb.image_name))

    def crop_lead_image(self, path):
        """Fill in an add form for Article and crop both lead_image sizes."""
        from selenium.webdriver.common.by import By

        author = Author.objects.create(name="Mark Twain")
        self.load_admin(Article)
        browser = self.selenium
        browser.find_element(By.ID, 'id_title').send_keys("A Connecticut Yankee")
        with self.clickable_selector('#lead_image-group .cropduster-button') as el:
            browser.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(path)
            self.dialog_save()

        browser.find_element(
            By.XPATH,
            '//select[@id="id_author"]/option[@value=%d]' % author.pk).click()
        self.save_form()
        return Article.objects.get()

    def test_save_keeps_the_measured_preview_scale(self):
        """
        Keep crop coordinates tied to the rendered preview dimensions.

        Populate both crop boxes against the rendition that is actually drawn,
        then change the server preview bounds before the single Save request.
        The submitted geometry must remain tied to the measured display scale;
        no selection may outgrow the rendered preview while Save is in flight.
        """
        from selenium.webdriver.common.by import By

        Author.objects.create(name="Mark Twain")
        self.load_admin(Article)
        browser = self.selenium
        browser.find_element(By.ID, 'id_title').send_keys("Widened preview bounds")
        with self.clickable_selector('#lead_image-group .cropduster-button') as el:
            browser.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(self.create_upload_file(1300, 1016))
            # The preview is on disk now, 640x500 inside the default bounds.
            self.wait_until(
                # 1x1 until the preview has loaded: that is the blank gif.
                lambda d: (self.dialog_rect('#cropbox') or {}).get('width', 0) > 1,
                message="Timeout waiting for the preview to be drawn")
            drawn = self.dialog_rect('#cropbox')
            self.dialog_populate_all_crops()

            with override_settings(CROPDUSTER_PREVIEW_WIDTH=1600,
                                   CROPDUSTER_PREVIEW_HEIGHT=1000):
                self.dialog_watch_rects('#cropbox', '.ReactCrop__crop-selection')
                frames = self.dialog_recorded_rects()
                self.dialog_click('#crop-button')

        self.save_form()

        self.assertGreater(drawn['width'], 1)
        self.assertLessEqual(drawn['width'], 640)
        self.assertLessEqual(drawn['height'], 500)
        self.assertAlmostEqual(
            drawn['width'] / drawn['height'], 640 / 500, delta=0.02,
            msg="The preview rendition may fit down, but must not distort.")
        # Allow one pixel for the selection border.
        oversized = [
            (image, selection) for image, selection in frames
            if image and selection and (
                selection['width'] > image['width'] + 1
                or selection['height'] > image['height'] + 1)]
        self.assertEqual(oversized, [], "the selection outgrew the image")

        article = Article.objects.get()
        thumbs = {t.name: t for t in article.lead_image.related_object.thumbs.all()}
        no_height = thumbs['no_height']
        # The dialog seeds ``no_height`` by fitting ``main``'s box, so this is
        # ``fit_to_crop`` of main's (15, 0, 1270, 1016) default.
        self.assertEqual(
            (no_height.crop_x, no_height.crop_y, no_height.crop_w, no_height.crop_h),
            (15, 0, 1270, 1016),
            "the second size's client crop was rescaled on its way through")

    def test_reopen_dialog_preserves_existing_crop(self):
        """
        Reopening the dialog and cropping again changes nothing.

        Every size is visited without changing its box. Recomputing a stored
        crop or assigning different thumb ids would change the before/after
        dictionaries asserted below.
        """
        article = self.crop_lead_image(
            os.path.join(self.TEST_IMG_DIR, 'img2.jpg'))
        image = article.lead_image.related_object
        before = {thumb.name: thumb.to_dict() for thumb in image.thumbs.all()}
        self.assertEqual(sorted(before), ['main', 'no_height', 'thumb'])
        # ``no_height`` uses the suggestion returned by the crop endpoint, not
        # the full 1300x1016 box the dialog computes for a free-height size.
        # Assert it separately so a recomputation before the comparison cannot
        # produce the same value twice and hide the regression.
        self.assertEqual(
            [(before[name]['crop_x'], before[name]['crop_y'],
              before[name]['crop_w'], before[name]['crop_h'])
             for name in ('main', 'no_height')],
            [(15, 0, 1270, 1016), (15, 0, 1270, 1016)])

        self.load_admin(article)
        with self.clickable_selector('#lead_image-group .cropduster-button') as el:
            self.selenium.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
        # Visit both sizes with the arrows, then save once without dragging.
            self.dialog_click('#nav-right')
            self.dialog_click('#nav-left')
            self.dialog_save()

        self.save_form()

        article.refresh_from_db()
        reopened = article.lead_image.related_object
        self.assertEqual(reopened.pk, image.pk)
        self.assertEqual(
            {thumb.name: thumb.to_dict() for thumb in reopened.thumbs.all()},
            before)

    def test_save_button_disabled_signals_agree(self):
        """
        Keep the button's two disabled signals in sync.

        The attribute is what stops a click and what assistive technology
        reads; the class is what the CKEditor plugin and downstream
        stylesheets have always tested. If they differ, a busy control can
        remain clickable or an enabled control can retain disabled styling.
        """
        from selenium.webdriver.common.by import By

        Author.objects.create(name="Mark Twain")
        self.load_admin(Article)
        browser = self.selenium
        browser.find_element(By.ID, 'id_title').send_keys("Disabled signals")
        with self.clickable_selector('#lead_image-group .cropduster-button') as el:
            browser.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(
                os.path.join(self.TEST_IMG_DIR, 'img2.jpg'))
            self.dialog_populate_all_crops()
            # Save has to be armed before its busy signals are watched.
            self.dialog_find('#crop-button')
            self.dialog_watch_signals('#crop-button')
            self.dialog_click('#crop-button')
            samples = self.dialog_recorded_signals()

        # Ignore samples taken after React removed one button and before it
        # inserted the next.
        samples = [sample for sample in samples if sample]
        for sample in samples:
            self.assertEqual(
                sample['attribute'], sample['class'],
                "#crop-button carried one disabled signal without the other: "
                "%r (all: %r)" % (sample, samples))
        busy = [sample for sample in samples if sample['value'] == 'Saving...']
        self.assertTrue(
            busy, "#crop-button never went busy during Save: %r" % (samples,))
        self.assertTrue(all(sample['attribute'] and sample['class'] for sample in busy))

    def test_addform_multiple_image(self):
        from selenium.webdriver.common.by import By

        author = Author.objects.create(name="Mark Twain")
        self.load_admin(Article)
        browser = self.selenium
        browser.find_element(By.ID, 'id_title').send_keys("A Connecticut Yankee in King Arthur's Court")

        # Upload and crop first Image
        browser.find_element(By.CSS_SELECTOR, '#lead_image-group .cropduster-button').click()

        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            self.dialog_save()

        # Upload and crop second Image
        with self.clickable_selector('#alt_image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            browser.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_save()

        # Add required FK
        browser.find_element(By.XPATH, '//select[@id="id_author"]/option[@value=%d]' % author.pk).click()

        self.save_form()

        # Test that crops saved correctly
        article = Article.objects.all()[0]
        lead_sizes = list(Size.flatten(Article.LEAD_IMAGE_SIZES))
        alt_sizes = list(Size.flatten(Article.ALT_IMAGE_SIZES))

        self.assertTrue(article.lead_image.name.endswith('.jpg'))
        self.assertEqual(len(article.lead_image.related_object.thumbs.all()), len(lead_sizes))
        self.assertTrue(article.alt_image.name.endswith('.png'))
        self.assertEqual(len(article.alt_image.related_object.thumbs.all()), len(alt_sizes))

    def test_changeform_single_image(self):
        from selenium.webdriver.common.by import By

        image_path = self.create_unique_image('img.png')
        author = Author.objects.create(name="Samuel Langhorne Clemens",
            headshot=image_path)
        Image.objects.create(image=image_path, content_object=author)
        author.refresh_from_db()
        author.headshot.generate_thumbs()

        self.load_admin(author)

        # The widget's summary card renders inside a shadow root on the
        # images container.
        self.wait_until(
            lambda d: self.selenium.execute_script(
                "var images = document.querySelector("
                "    '#headshot-group .cropduster-images');"
                "return !!(images && images.shadowRoot && "
                "    images.shadowRoot.querySelector('.cropduster-image-thumb'));"),
            message="Timeout waiting for the widget preview to render")
        images_el = self.selenium.find_element(
            By.CSS_SELECTOR, '#headshot-group .cropduster-images')
        preview_image_el = images_el.shadow_root.find_element(
            By.CSS_SELECTOR, '.cropduster-image-thumb')
        src_image_path = os.path.join(self.TEST_IMG_DIR, 'img.png')
        self.assertImageColorEqual(preview_image_el, src_image_path)

        elem = self.selenium.find_element(By.ID, 'id_name')
        elem.clear()
        elem.send_keys("Mark Twain")

        self.save_form()

        author = Author.objects.get(pk=author.pk)
        self.assertEqual(author.name, 'Mark Twain')
        self.assertEqual(author.headshot.name, image_path)
        self.assertEqual(len(author.headshot.related_object.thumbs.all()), 2)

    def test_changeform_multiple_images(self):
        from selenium.webdriver.common.by import By

        author = Author.objects.create(name="Samuel Langhorne Clemens")
        lead_image_path = self.create_unique_image('img.jpg')
        alt_image_path = self.create_unique_image('img.png')
        article = Article.objects.create(title="title", author=author,
            lead_image=lead_image_path,
            alt_image=alt_image_path)
        Image.objects.create(image=lead_image_path, content_object=article)
        Image.objects.create(
            image=alt_image_path, content_object=article, field_identifier='alt')
        article.refresh_from_db()
        article.lead_image.generate_thumbs()
        article.alt_image.generate_thumbs()

        self.load_admin(article)

        elem = self.selenium.find_element(By.ID, 'id_title')
        elem.clear()
        elem.send_keys("Updated Title")

        self.save_form()

        article.refresh_from_db()
        self.assertEqual(article.title, 'Updated Title')
        self.assertEqual(article.lead_image.name, lead_image_path)
        self.assertEqual(article.alt_image.name, alt_image_path)
        self.assertEqual(len(article.lead_image.related_object.thumbs.all()), 3)
        self.assertEqual(len(article.alt_image.related_object.thumbs.all()), 1)

    def test_changeform_with_optional_sizes_small_image(self):
        test_a = OptionalSizes.objects.create(slug='a')

        self.load_admin(test_a)

        # Upload and crop image
        with self.clickable_selector('#image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            self.selenium.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            self.dialog_save()

        self.save_form()

        test_a = OptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 1, "Expected one thumb; instead got %d" % num_thumbs)

    def test_changeform_with_optional_sizes_large_image(self):
        test_a = OptionalSizes.objects.create(slug='a')
        self.load_admin(test_a)

        # Upload and crop image
        with self.clickable_selector('#image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            self.selenium.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.crop_dialog():
            self.dialog_upload(os.path.join(self.TEST_IMG_DIR, 'img2.jpg'))
            self.dialog_save()

        self.save_form()

        test_a = OptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 2, "Expected one thumb; instead got %d" % num_thumbs)
