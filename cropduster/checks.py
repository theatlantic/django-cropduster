"""System checks for Cropduster."""

from django.core import checks

from cropduster.conf import CROPDUSTER_APP_LABEL


FROZEN_APP_LABEL = 'cropduster'


def check_app_config(app_configs=None, **kwargs):
    """Report an app label that does not match Cropduster's migrations."""
    if CROPDUSTER_APP_LABEL == FROZEN_APP_LABEL:
        return []

    return [checks.Error(
        "cropduster's app label is %r, but it has to be %r." % (
            CROPDUSTER_APP_LABEL, FROZEN_APP_LABEL),
        hint=(
            "CROPDUSTER_APP_LABEL (or CROPDUSTER_V4_APP_LABEL) is set to %r. "
            "cropduster's migrations hardcode the 'cropduster' label, so a "
            "different one leaves their self-references and every downstream "
            "dependency on ('cropduster', '0001_initial') pointing at nothing. "
            "Remove the setting; to keep the tables out of another install's "
            "way, set CROPDUSTER_DB_PREFIX instead." % CROPDUSTER_APP_LABEL),
        id='cropduster.E010')]
