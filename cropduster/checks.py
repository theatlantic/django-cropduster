"""System checks for Cropduster."""

from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from cropduster.conf import CROPDUSTER_APP_LABEL, settings as cropduster_settings


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


def _get_renderer():
    """Return the configured renderer and any construction error."""
    from cropduster.renderers import get_renderer

    try:
        return get_renderer(), None
    except (ImproperlyConfigured, ImportError, TypeError, ValueError) as error:
        return None, error


def check_url_renderer(app_configs=None, **kwargs):
    """``cropduster.E001``: the configured URL renderer cannot be built."""
    error = _get_renderer()[1]
    if error is None:
        return []
    return [checks.Error(
        "cropduster's URL renderer could not be loaded: %s" % error,
        hint=(
            "CROPDUSTER_URL_RENDERER is %r. It takes a dotted path to a "
            "BaseRenderer subclass, or a dict of {'BACKEND': <dotted path>, "
            "'OPTIONS': {...}}."
            % (cropduster_settings.CROPDUSTER_URL_RENDERER,)),
        id='cropduster.E001')]


def check_metadata_only_renderer(app_configs=None, **kwargs):
    """``cropduster.W002``: metadata-only mode needs an on-demand renderer."""
    if cropduster_settings.CROPDUSTER_CREATE_THUMBS:
        return []
    renderer = _get_renderer()[0]
    if renderer is None or renderer.supports_metadata_only:
        return []
    return [checks.Warning(
        'CROPDUSTER_CREATE_THUMBS is False, but %s.%s cannot render crops '
        'without the files it turns off.' % (
            type(renderer).__module__, type(renderer).__name__),
        hint=(
            'Point CROPDUSTER_URL_RENDERER at a renderer whose '
            'supports_metadata_only is True, or turn '
            'CROPDUSTER_CREATE_THUMBS back on.'),
        id='cropduster.W002')]
