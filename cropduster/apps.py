from django.apps import AppConfig
from django.core import checks
from django.core.signals import setting_changed

from cropduster.conf import CROPDUSTER_APP_LABEL


class CropdusterConfig(AppConfig):
    """Use the app label stored in Cropduster's existing migrations."""

    name = 'cropduster'
    label = CROPDUSTER_APP_LABEL
    verbose_name = 'Cropduster'

    def ready(self):
        from cropduster.checks import check_app_config
        from cropduster.conf import settings as cropduster_settings

        setting_changed.connect(cropduster_settings.reset)
        checks.register(check_app_config)
