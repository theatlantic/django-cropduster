"""System checks for Cropduster."""

from django.conf import settings as django_settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from cropduster.conf import (
    CROPDUSTER_APP_LABEL, DIALOG_MODES, settings as cropduster_settings)


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


def check_api_permission(app_configs=None, **kwargs):
    """``cropduster.E002``: the API permission setting is not callable."""
    from cropduster.api.permissions import get_permission_check

    path = cropduster_settings.CROPDUSTER_API_PERMISSION
    try:
        permission = get_permission_check()
    except (ImportError, AttributeError, TypeError, ValueError) as error:
        problem = str(error)
    else:
        if callable(permission):
            return []
        problem = '%r is not callable.' % (permission,)
    return [checks.Error(
        "cropduster's API permission callable could not be loaded: %s"
        % problem,
        hint=(
            'CROPDUSTER_API_PERMISSION is %r. It must be the dotted path '
            'to a callable accepting (request, target).' % path),
        id='cropduster.E002')]


def check_dialog_mode(app_configs=None, **kwargs):
    """``cropduster.E003``: the default dialog mode is not recognized."""
    value = cropduster_settings.CROPDUSTER_DIALOG_MODE
    if value in DIALOG_MODES:
        return []
    return [checks.Error(
        'CROPDUSTER_DIALOG_MODE must be one of %s, got %r.' % (
            ', '.join(repr(mode) for mode in DIALOG_MODES), value),
        hint=(
            "Use 'auto' to select by viewport size, 'modal' for the in-page "
            "dialog, or 'window' for the popup."),
        id='cropduster.E003')]


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
            'supports_metadata_only is True '
            '(cropduster.renderers.ThumborRenderer), or turn '
            'CROPDUSTER_CREATE_THUMBS back on.'),
        id='cropduster.W002')]


PROBE_NAME = 'w001-probe.jpg'


def check_thumbor_media_url(app_configs=None, **kwargs):
    """``cropduster.W001``: ThumborRenderer cannot strip the storage URL
    prefix."""
    from cropduster.renderers import ThumborRenderer
    from cropduster.renderers.thumbor import normalize_prefix
    from cropduster.utils.storage import get_image_storage

    renderer = _get_renderer()[0]
    if not isinstance(renderer, ThumborRenderer):
        return []

    candidates = [
        renderer.media_url,
        str(django_settings.MEDIA_URL),
        *renderer.extra_media_urls,
    ]
    try:
        probe_url = get_image_storage().url(PROBE_NAME)
    except Exception:
        return []

    if any(
            prefix and probe_url.startswith(normalize_prefix(prefix))
            for prefix in candidates):
        return []

    return [checks.Warning(
        "cropduster's image storage emits URLs that no CROPDUSTER_THUMBOR "
        'prefix matches, so Thumbor receives whole URLs to fetch.',
        hint=(
            'The storage renders %r as %r, which starts with none of the '
            'prefixes ThumborRenderer strips: %s. Set '
            "CROPDUSTER_THUMBOR['MEDIA_URL'] to the prefix the storage emits, "
            'or list every prefix it can emit in '
            "CROPDUSTER_THUMBOR['EXTRA_MEDIA_URLS']." % (
                PROBE_NAME, probe_url,
                ', '.join(repr(candidate) for candidate in candidates))),
        id='cropduster.W001')]
