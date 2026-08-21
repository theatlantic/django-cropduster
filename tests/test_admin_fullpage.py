"""
Rerun the admin browser scenarios with the popup dialog.

The popup remains available through ``CROPDUSTER_DIALOG_MODE="window"`` and is
selected automatically for small embedded viewports. It completes a crop
across a window boundary by resolving the widget from its prefix, so the modal
tests are inherited here under the popup setting.
"""

import json

from django.test import override_settings

from tests import test_admin
from .models import Author


@override_settings(CROPDUSTER_DIALOG_MODE='window')
class TestAdminFullPage(test_admin.TestAdmin):

    dialog_mode = 'window'

    def test_the_widget_is_told_which_presentation_to_use(self):
        """
        Verify that the field's ``data-config`` selects the popup.

        ``auto`` would select the modal at this window size, so this assertion
        confirms that the override reached the widget rendered by the live
        server.
        """
        self.load_admin(Author)

        config = json.loads(self.selenium.execute_script(
            "return document.querySelector("
            "  '#headshot-group cropduster-widget').getAttribute('data-config');"))
        self.assertEqual(config['dialogMode'], 'window')
