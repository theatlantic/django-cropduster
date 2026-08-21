"""Apply the configured permission check to JSON API requests.

``CROPDUSTER_API_PERMISSION`` names a callable taking ``(request, target)``,
where ``target`` is the requested :class:`~cropduster.api.schema.TargetInfo` or
``None``. It raises ``PermissionDenied`` to refuse a request. The API converts
that exception to JSON with status 403 rather than redirecting a ``fetch()``
request to an HTML login page.

:func:`staff_and_object_perm` is the default. Projects that require the 4.x
``@login_required`` behavior can select :func:`login_required_only`.
"""

from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.utils.module_loading import import_string

from cropduster.conf import settings as cropduster_settings


__all__ = ('check_permission', 'get_permission_check', 'login_required_only',
           'staff_and_object_perm')


def get_permission_check():
    """Return the configured permission callable."""
    return import_string(cropduster_settings.CROPDUSTER_API_PERMISSION)


def check_permission(request, target=None):
    result = get_permission_check()(request, target)
    if result is False:
        raise PermissionDenied("The configured permission check refused the request.")
    return result


def login_required_only(request, target=None):
    """Allow any active, authenticated user."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("You must be logged in to do that.")


def staff_and_object_perm(request, target=None):
    """Require staff status and the target model's add or change permission.

    A request without a target requires only staff status because the image is
    not yet associated with an object.

    A target with an existing object requires ``change`` permission. An
    unsaved target requires ``add`` permission, matching the admin form.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("You must be logged in to do that.")
    if not user.is_staff:
        raise PermissionDenied("You must be a staff member to do that.")
    if target is None:
        return

    model = target.model
    action = 'change' if target.object_id is not None else 'add'
    opts = model._meta
    permission = '%s.%s' % (
        opts.app_label, get_permission_codename(action, opts))
    if not user.has_perm(permission):
        raise PermissionDenied(
            "You do not have permission to %s %s." % (action, opts.verbose_name))
