from django.test.testcases import LiveServerThread
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

from .helpers import CropdusterTestCaseMediaMixin
from .models import Author


class TestSaveForm(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

    root_urlconf = 'tests.urls'
    server_thread_class = LiveServerThread

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

    def _save_with_delayed_submission(self, save_and_continue):
        author = Author.objects.create(name='Samuel Langhorne Clemens')
        self.load_admin(author)
        self.addCleanup(self.selenium.get, 'about:blank')

        name = self.selenium.find_element(By.ID, 'id_name')
        name.clear()
        name.send_keys('Mark Twain')
        if not save_and_continue:
            self.selenium.execute_script("""
                document.querySelectorAll('[name="_continue"]').forEach(
                    function (button) { button.remove(); });
            """)

        # Keep the original page open after the Save click returns.
        # requestSubmit preserves the clicked button's name in the POST.
        self.selenium.execute_script("""
            var form = document.getElementById('id_name').form;
            form.addEventListener('submit', function (event) {
                event.preventDefault();
                var submitter = event.submitter;
                window.setTimeout(function () {
                    form.requestSubmit(submitter);
                }, 1000);
            }, {once: true});
        """)

        self.save_form()

        author.refresh_from_db()
        self.assertEqual(author.name, 'Mark Twain')
        if save_and_continue:
            path = reverse('admin:tests_author_change', args=[author.pk])
        else:
            path = reverse('admin:tests_author_changelist')
        self.assertEqual(self.selenium.current_url, self.live_server_url + path)
        self.assertTrue(self.selenium.execute_script(
            'return window.$ === django.jQuery'))

    def test_save_and_continue_waits_for_delayed_submission(self):
        self._save_with_delayed_submission(save_and_continue=True)

    def test_save_waits_for_delayed_submission(self):
        self._save_with_delayed_submission(save_and_continue=False)
