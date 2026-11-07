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
        from cropduster.checks import (
            check_app_config, check_metadata_only_renderer,
            check_thumbor_media_url, check_url_renderer)
        from cropduster.conf import settings as cropduster_settings
        from cropduster.renderers import reset_renderer_cache

        setting_changed.connect(cropduster_settings.reset)
        setting_changed.connect(reset_renderer_cache)
        checks.register(check_app_config)
        checks.register(check_url_renderer)
        checks.register(check_metadata_only_renderer)
        checks.register(check_thumbor_media_url)
