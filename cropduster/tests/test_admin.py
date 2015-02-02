import os
import shutil
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

try:
    from django.contrib.staticfiles.testing import (
        StaticLiveServerTestCase as LiveServerTestCase)
except ImportError:
    from django.test import LiveServerTestCase

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from . import ORIG_IMG_PATH
from .models import TestArticle, TestAuthor
from ..models import Size


class TestAdmin(LiveServerTestCase):

    def setUp(self):
        self.admin_url = self.live_server_url + reverse('admin:index')
        self.add_form_url = self.live_server_url + reverse('admin:cropduster_testarticle_add')

        self.TEST_IMG_ROOT = os.path.join(settings.MEDIA_ROOT, uuid.uuid4().hex)
        self.TEST_IMG_DIR = os.path.join(self.TEST_IMG_ROOT, 'data')

        # Create directory for test images
        shutil.copytree(ORIG_IMG_PATH, self.TEST_IMG_DIR)

        User.objects.create_superuser('mtwain', 'me@example.com', 'p@ssw0rd')
        browser = webdriver.PhantomJS()
        browser.set_window_size(1120, 550)
        browser.get(self.admin_url)
        browser.find_element_by_xpath('//input[@type="text"]').send_keys('mtwain')
        browser.find_element_by_xpath('//input[@type="password"]').send_keys('p@ssw0rd')
        browser.find_element_by_xpath('//input[@type="submit"]').click()
        self.browser = browser

    def test_addform_single_image(self):
        browser = self.browser
        browser.get(self.live_server_url + reverse('admin:cropduster_testauthor_add'))
        browser.find_element_by_id('id_name').send_keys('Mark Twain')
        browser.find_element_by_css_selector('#headshot-group .rounded-button').click()
        browser.switch_to_window(browser.window_handles[1])
        browser.find_element_by_id('id_image').send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'upload-button')))
        browser.find_element_by_id('upload-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        browser.switch_to_window(browser.window_handles[0])
        browser.find_element_by_xpath('//input[@value="Save and continue editing"]').click()

        author = TestAuthor.objects.all()[0]
        sizes = list(Size.flatten(TestAuthor.HEADSHOT_SIZES))
        self.assertTrue(bool(author.headshot.path))
        self.assertEqual(len(author.headshot.related_object.thumbs.all()), len(sizes))

    def test_addform_multiple_image(self):
        author = TestAuthor.objects.create(name="Mark Twain")

        browser = self.browser
        browser.get(self.add_form_url)

        browser.find_element_by_id('id_title').send_keys("A Connecticut Yankee in King Arthur's Court")

        # Upload and crop first Image
        browser.find_element_by_css_selector('#lead_image-group .rounded-button').click()
        browser.switch_to_window(browser.window_handles[1])
        browser.find_element_by_id('id_image').send_keys(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'upload-button')))
        browser.find_element_by_id('upload-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        browser.switch_to_window(browser.window_handles[0])

        # Upload and crop second Image
        browser.find_element_by_css_selector('#alt_image-group .rounded-button').click()
        browser.switch_to_window(browser.window_handles[1])
        browser.find_element_by_id('id_image').send_keys(os.path.join(self.TEST_IMG_DIR, 'img.png'))

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'upload-button')))
        browser.find_element_by_id('upload-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        WebDriverWait(browser, 10).until(EC.visibility_of_element_located((By.ID, 'crop-button')))
        browser.find_element_by_id('crop-button').click()

        browser.switch_to_window(browser.window_handles[0])

        # Add required FK
        browser.find_element_by_xpath('//select[@id="id_author"]/option[@value=%d]' % author.pk).click()
        browser.find_element_by_xpath('//input[@value="Save and continue editing"]').click()

        # Test that crops saved correctly
        article = TestArticle.objects.all()[0]
        lead_sizes = list(Size.flatten(TestArticle.LEAD_IMAGE_SIZES))
        alt_sizes = list(Size.flatten(TestArticle.ALT_IMAGE_SIZES))

        self.assertTrue(article.lead_image.path.endswith('.jpg'))
        self.assertEqual(len(article.lead_image.related_object.thumbs.all()), len(lead_sizes))
        self.assertTrue(article.alt_image.path.endswith('.png'))
        self.assertEqual(len(article.alt_image.related_object.thumbs.all()), len(alt_sizes))

    def tearDown(self):
        self.browser.quit()
        shutil.rmtree(self.TEST_IMG_ROOT, ignore_errors=True)
