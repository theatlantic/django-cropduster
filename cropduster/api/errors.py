"""Convert API failures to a consistent JSON response.

One envelope::

    {"error": {"code": ..., "message": ..., "field": ..., "details": ...}}

``code`` is stable and machine-readable. ``message`` is shown to the editor,
``field`` identifies an invalid request field, and ``details`` contains values
specific to the code. Unlike the legacy endpoints, these responses use the
appropriate HTTP status instead of HTTP 200 with an HTML ``error`` value.

:func:`json_api_view` catches :class:`ApiError` and the domain exceptions
listed by :func:`api_error`, then returns this envelope.
"""

import functools
import logging

from django.core.exceptions import (
    ObjectDoesNotExist, PermissionDenied, RequestDataTooBig, SuspiciousOperation,
    ValidationError)
from django.http import JsonResponse

from cropduster.exceptions import (
    CropDusterImageException, CropDusterResizeException, ImageTooSmallError)


__all__ = ('ApiError', 'error_response', 'json_api_view')


logger = logging.getLogger('cropduster')

#: Responses produced by inner Django decorators. Their HTML bodies are
#: replaced with the API error object.
RESPONSE_CODES = {
    403: ('csrf_failed', "CSRF verification failed."),
    405: ('method_not_allowed', "This endpoint does not accept that method."),
}


class ApiError(Exception):
    """Store an API error code, message, fields, and HTTP status."""

    def __init__(self, status, code, message, field=None, details=None):
        self.status = status
        self.code = code
        self.message = message
        self.field = field
        self.details = details
        super(ApiError, self).__init__(message)

    @property
    def envelope(self):
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                'field': self.field,
                'details': self.details,
            },
        }


def error_response(error):
    return JsonResponse(error.envelope, status=error.status)


def json_api_view(view):
    """Return API exceptions and decorator failures as JSON errors.

    :func:`api_error` translates expected domain exceptions. Other exceptions
    are logged with their tracebacks and returned as a generic 500 response.
    """
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except Exception as e:
            error = api_error(e)
            if error is None:
                logger.exception(
                    "Unhandled error in %s", getattr(view, '__name__', view),
                    extra={'request': request})
                error = ApiError(
                    500, 'server_error', "The server failed to handle the request.")
            return error_response(error)
        return _envelope_error_response(response)

    return wrapper


def api_error(exc):
    """Return an :class:`ApiError` for a known exception, otherwise ``None``.

    ``NotImplementedError`` represents the reserved per-crop source field when
    it names an unsupported source, so it returns 501 rather than 500.
    """
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, ImageTooSmallError):
        return ApiError(
            400, 'image_too_small', str(exc), field='image', details={
                'min': list(exc.min_size),
                'actual': list(exc.actual_size),
            })
    if isinstance(exc, CropDusterResizeException):
        return ApiError(400, 'resize_failed', str(exc))
    if isinstance(exc, CropDusterImageException):
        return ApiError(400, 'invalid_image', str(exc), field='image')
    if isinstance(exc, ValidationError):
        return _validation_error(exc)
    if isinstance(exc, PermissionDenied):
        return ApiError(
            403, 'permission_denied',
            str(exc) or "You do not have permission to do that.")
    if isinstance(exc, RequestDataTooBig):
        return ApiError(413, 'request_too_large', "The request body is too large.")
    if isinstance(exc, SuspiciousOperation):
        # Invalid storage paths are client input rather than server errors.
        # Match Django's 400 response without logging a traceback. Check
        # RequestDataTooBig first because it has its own status.
        return ApiError(400, 'invalid', str(exc))
    if isinstance(exc, ObjectDoesNotExist):
        return ApiError(404, 'not_found', str(exc) or "No such object.")
    if isinstance(exc, NotImplementedError):
        return ApiError(501, 'not_implemented', str(exc))
    return None


def _validation_error(exc):
    """Convert a validation error and preserve its field when available."""
    field, details = None, None
    if hasattr(exc, 'error_dict'):
        details = exc.message_dict
        field = next(iter(details))
        messages = details[field]
    else:
        messages = exc.messages
    return ApiError(
        400, 'invalid', ' '.join(messages), field=field, details=details)


def _envelope_error_response(response):
    """Replace an HTML error from an inner decorator with JSON.

    ``csrf_protect`` and ``require_http_methods`` answer with Django's own
    HTML pages rather than by raising, so they would otherwise be the one
    thing a client of this API cannot parse.
    """
    status = getattr(response, 'status_code', 200)
    if status not in RESPONSE_CODES:
        return response
    if response.headers.get('Content-Type', '').startswith('application/json'):
        return response
    code, message = RESPONSE_CODES[status]
    return error_response(ApiError(status, code, message))
