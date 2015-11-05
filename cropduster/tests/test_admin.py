import os
import contextlib

from django.contrib.auth.models import User
from django.contrib.admin.tests import AdminSeleniumWebDriverTestCase
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    visibility_of_element_located, element_to_be_clickable)

try:
    import grappelli
except ImportError:
    grappelli = None

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author, TestForOptionalSizes, TestForOrphanedThumbs
from ..models import Size, Thumb


@override_settings(ROOT_URLCONF='cropduster.tests.urls')
class TestAdmin(CropdusterTestCaseMediaMixin, AdminSeleniumWebDriverTestCase):

    available_apps = [
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.messages',
        'django.contrib.sessions',
        'django.contrib.sites',
        'django.contrib.staticfiles',
        'django.contrib.admin',
        'generic_plus',
        'cropduster',
    ]

    if grappelli:
        available_apps.insert(0, 'grappelli')

    webdriver_class = 'selenium.webdriver.phantomjs.webdriver.WebDriver'

    def setUp(self):
        super(TestAdmin, self).setUp()
        self.selenium.set_window_size(1120, 550)
        self.selenium.set_page_load_timeout(10)
        User.objects.create_superuser('mtwain', 'me@example.com', 'p@ssw0rd')

    def wait_until_visible_selector(self, selector, timeout=10):
        self.wait_until(
            visibility_of_element_located((By.CSS_SELECTOR, selector)),
            timeout=timeout)

    def wait_until_clickable_xpath(self, xpath, timeout=10):
        self.wait_until(
            element_to_be_clickable((By.XPATH, xpath)), timeout=timeout)

    def wait_until_clickable_selector(self, selector, timeout=10):
        self.wait_until(
            element_to_be_clickable((By.CSS_SELECTOR, selector)),
            timeout=timeout)

    @contextlib.contextmanager
    def visible_selector(self, selector, timeout=10):
        self.wait_until_visible_selector(selector, timeout)
        yield self.selenium.find_element_by_css_selector(selector)

    @contextlib.contextmanager
    def clickable_selector(self, selector, timeout=10):
        self.wait_until_clickable_selector(selector, timeout)
        yield self.selenium.find_element_by_css_selector(selector)

    @contextlib.contextmanager
    def clickable_xpath(self, xpath, timeout=10):
        self.wait_until_clickable_xpath(xpath, timeout)
        yield self.selenium.find_element_by_xpath(xpath)

    @contextlib.contextmanager
    def switch_to_popup_window(self):
        self.wait_until(lambda d: len(d.window_handles) == 2)
        self.selenium.switch_to.window(self.selenium.window_handles[1])
        yield
        self.wait_until(lambda d: len(d.window_handles) == 1)
        self.selenium.switch_to.window(self.selenium.window_handles[0])

    def test_addform_single_image(self):
        self.admin_login("mtwain", "p@ssw0rd", login_url=reverse('admin:cropduster_author_add'))
        browser = self.selenium
        browser.find_element_by_id('id_name').send_keys('Mark Twain')
        browser.find_element_by_css_selector('#headshot-group .rounded-button').click()

        with self.switch_to_popup_window():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            with self.clickable_selector('#crop-button') as el:
                el.click()

        with self.clickable_xpath('//input[@value="Save and continue editing"]') as el:
            el.click()

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

        self.admin_login("mtwain", "p@ssw0rd", login_url=reverse('admin:cropduster_article_add'))

        browser = self.selenium
        browser.find_element_by_id('id_title').send_keys("A Connecticut Yankee in King Arthur's Court")

        # Upload and crop first Image
        browser.find_element_by_css_selector('#lead_image-group .rounded-button').click()

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
        with self.clickable_selector('#alt_image-group .rounded-button') as el:
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
        browser.find_element_by_xpath('//input[@value="Save and continue editing"]').click()

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

        url = reverse('admin:cropduster_author_change', args=(author.pk, ))
        browser = self.selenium

        self.admin_login("mtwain", "p@ssw0rd", login_url=url)

        elem = browser.find_element_by_id('id_name')
        elem.clear()
        elem.send_keys("Mark Twain")
        old_page_id = browser.find_element_by_tag_name('html').id
        browser.find_element_by_xpath('//input[@value="Save and continue editing"]').click()
        self.wait_until(lambda b: b.find_element_by_tag_name('html').id != old_page_id)
        self.assertEqual(Author.objects.get(pk=author.pk).name, 'Mark Twain')

    def test_changeform_multiple_images(self):
        author = Author.objects.create(name="Samuel Langhorne Clemens")
        article = Article.objects.create(title="title", author=author,
            lead_image=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg'),
            alt_image=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.png'))
        article.lead_image.generate_thumbs()
        article.alt_image.generate_thumbs()

        url = reverse('admin:cropduster_article_change', args=(article.pk, ))
        browser = self.selenium

        self.admin_login("mtwain", "p@ssw0rd", login_url=url)

        elem = browser.find_element_by_id('id_title')
        elem.clear()
        elem.send_keys("Updated Title")
        old_page_id = browser.find_element_by_tag_name('html').id
        browser.find_element_by_xpath('//input[@value="Save and continue editing"]').click()
        self.wait_until(lambda b: b.find_element_by_tag_name('html').id != old_page_id)
        self.assertEqual(Article.objects.get(pk=article.pk).title, 'Updated Title')

    def test_changeform_with_optional_sizes_small_image(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')

        self.admin_login("mtwain", "p@ssw0rd",
            login_url=reverse('admin:cropduster_testforoptionalsizes_change', args=[test_a.pk]))
        self.wait_page_loaded()

        # Upload and crop image
        with self.clickable_selector('#image-group .rounded-button') as el:
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

        self.selenium.find_element_by_xpath('//input[@name="_continue"]').click()
        self.wait_page_loaded()

        test_a = TestForOptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 1, "Expected one thumb; instead got %d" % num_thumbs)

    def test_changeform_with_optional_sizes_large_image(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')

        self.admin_login("mtwain", "p@ssw0rd",
            login_url=reverse('admin:cropduster_testforoptionalsizes_change', args=[test_a.pk]))
        self.wait_page_loaded()

        # Upload and crop image
        with self.clickable_selector('#image-group .rounded-button') as el:
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

        self.selenium.find_element_by_xpath('//input[@name="_continue"]').click()
        self.wait_page_loaded()

        test_a = TestForOptionalSizes.objects.get(slug='a')
        image = test_a.image.related_object
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 2, "Expected one thumb; instead got %d" % num_thumbs)

    def test_orphaned_thumbs_after_delete(self):
        test_a = TestForOrphanedThumbs.objects.create(slug='a')

        self.admin_login("mtwain", "p@ssw0rd",
            login_url=reverse('admin:cropduster_testfororphanedthumbs_change', args=[test_a.pk]))
        self.wait_page_loaded()

        # Upload and crop image
        with self.clickable_selector('#image-group .rounded-button') as el:
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
            with self.clickable_selector('#crop-button:not(.disabled)') as el:
                el.click()

        self.selenium.find_element_by_xpath('//input[@name="_continue"]').click()
        self.wait_page_loaded()

        test_a = TestForOrphanedThumbs.objects.get(slug='a')
        test_a.delete()

        num_thumbs = len(Thumb.objects.all())
        self.assertEqual(num_thumbs, 0, "%d orphaned thumbs left behind after deletion")
