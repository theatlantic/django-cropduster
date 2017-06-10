from __future__ import absolute_import

import os

from django_admin_testutils import AdminSeleniumTestCase

from cropduster.models import Size
from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author, TestForOptionalSizes


class TestAdmin(CropdusterTestCaseMediaMixin, AdminSeleniumTestCase):

    root_urlconf = 'cropduster.tests.urls'

    @property
    def available_apps(self):
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
            'cropduster.tests',
        ]
        if self.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    def test_addform_single_image(self):
        self.load_admin(Author)

        browser = self.selenium
        browser.find_element_by_id('id_name').send_keys('Mark Twain')
        with self.clickable_selector('#headshot-group .cropduster-button') as el:
            el.click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()

        self.save_form()

        author = Author.objects.all()[0]
        sizes = list(Size.flatten(Author.HEADSHOT_SIZES))
        self.assertTrue(bool(author.headshot.path))

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

    def test_addform_multiple_image(self):
        author = Author.objects.create(name="Mark Twain")
        self.load_admin(Article)
        browser = self.selenium
        browser.find_element_by_id('id_title').send_keys("A Connecticut Yankee in King Arthur's Court")

        # Upload and crop first Image
        browser.find_element_by_css_selector('#lead_image-group .cropduster-button').click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()
            with self.clickable_selector('#crop-button:not(.disabled)') as el:
                el.click()

        # Upload and crop second Image
        with self.clickable_selector('#alt_image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            browser.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.png'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()

        # Add required FK
        browser.find_element_by_xpath('//select[@id="id_author"]/option[@value=%d]' % author.pk).click()

        self.save_form()

        # Test that crops saved correctly
        article = Article.objects.all()[0]
        lead_sizes = list(Size.flatten(Article.LEAD_IMAGE_SIZES))
        alt_sizes = list(Size.flatten(Article.ALT_IMAGE_SIZES))

        self.assertTrue(article.lead_image.path.endswith('.jpg'))
        self.assertEqual(len(article.lead_image.related_object.thumbs.all()), len(lead_sizes))
        self.assertTrue(article.alt_image.path.endswith('.png'))
        self.assertEqual(len(article.alt_image.related_object.thumbs.all()), len(alt_sizes))

    def test_changeform_single_image(self):
        author = Author.objects.create(name="Samuel Langhorne Clemens",
            headshot=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg'))
        author.headshot.generate_thumbs()

        self.load_admin(author)

        elem = self.selenium.find_element_by_id('id_name')
        elem.clear()
        elem.send_keys("Mark Twain")

        self.save_form()

        self.assertEqual(Author.objects.get(pk=author.pk).name, 'Mark Twain')

    def test_changeform_multiple_images(self):
        author = Author.objects.create(name="Samuel Langhorne Clemens")
        article = Article.objects.create(title="title", author=author,
            lead_image=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg'),
            alt_image=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.png'))
        article.lead_image.generate_thumbs()
        article.alt_image.generate_thumbs()

        self.load_admin(article)

        elem = self.selenium.find_element_by_id('id_title')
        elem.clear()
        elem.send_keys("Updated Title")

        self.save_form()

        self.assertEqual(Article.objects.get(pk=article.pk).title, 'Updated Title')

    def test_changeform_with_optional_sizes_small_image(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')

        self.load_admin(test_a)

        # Upload and crop image
        with self.clickable_selector('#image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            self.selenium.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()

        self.save_form()

        test_a = TestForOptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 1, "Expected one thumb; instead got %d" % num_thumbs)

    def test_changeform_with_optional_sizes_large_image(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')
        self.load_admin(test_a)

        # Upload and crop image
        with self.clickable_selector('#image-group .cropduster-button') as el:
            # With the Chrome driver, using Grappelli, this button can be covered
            # by the fixed footer. So we scroll the button into view.
            self.selenium.execute_script('window.scrollTo(0, %d)' % el.location['y'])
            el.click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img2.jpg'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()

        self.save_form()

        test_a = TestForOptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 2, "Expected one thumb; instead got %d" % num_thumbs)
