import copy
import errno
import logging
import os
import sys

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.utils.encoding import force_str
from django.utils.safestring import mark_safe


logger = logging.getLogger('cropduster')


class FauxTb(object):

    def __init__(self, tb_frame, tb_lineno, tb_next):
        self.tb_frame = tb_frame
        self.tb_lineno = tb_lineno
        self.tb_next = tb_next


def current_stack(skip=0):
    try:
        1 / 0
    except ZeroDivisionError:
        f = sys.exc_info()[2].tb_frame
    for i in range(skip + 2):
        f = f.f_back
    lst = []
    while f is not None:
        lst.append((f, f.f_lineno))
        f = f.f_back
    return lst


def extend_traceback(tb, stack):
    """Extend traceback with stack info."""
    head = tb
    for tb_frame, tb_lineno in stack:
        head = FauxTb(tb_frame, tb_lineno, head)
    return head


def full_exc_info():
    """Like sys.exc_info, but includes the full traceback."""
    t, v, tb = sys.exc_info()
    full_tb = extend_traceback(tb, current_stack(1))
    return t, v, full_tb


def format_error(error):
    from generic_plus.utils import get_relative_media_url

    if isinstance(error, str):
        return error
    elif isinstance(error, IOError):
        if error.errno == errno.ENOENT:  # No such file or directory
            file_name = get_relative_media_url(error.filename)
            return "Could not find file %s" % file_name

    return "[%(type)s] %(msg)s" % {
        'type': error.__class__.__name__,
        'msg': error,
    }


def log_error(request, view, action, errors, exc_info=None):
    # We only log the first error, send the rest as data; it's simpler this way
    error_msg = "Error %s: %s" % (action, format_error(errors[0]))

    log_kwargs = {}

    if not exc_info:
        try:
            exc_info = full_exc_info()
        except Exception:
            exc_info = None
    if exc_info and not isinstance(exc_info, tuple) or not len(exc_info) or not exc_info[0]:
        exc_info = None

    if exc_info:
        log_kwargs["exc_info"] = exc_info

    logger.error(error_msg, extra={
        'errors': errors,
        'process_id': os.getpid(),
        'request': request,
        'url': request.path_info,
        'view': 'cropduster.views.%s' % view,
    }, **log_kwargs)


def json_error(request, view, action, errors=None, forms=None, formsets=None, log=False, exc_info=None):
    from .utils import json

    if forms:
        formset_errors = [[copy.deepcopy(f.errors) for f in forms]]
    elif formsets:
        formset_errors = [copy.deepcopy(f.errors) for f in formsets]
    else:
        formset_errors = []

    if not errors and not formset_errors:
        return HttpResponse(json.dumps({'error': 'An unknown error occurred'}),
                content_type='application/json')

    error_str = ''
    for forms in formset_errors:
        for form_errors in forms:
            for k in sorted(form_errors.keys()):
                v = form_errors.pop(k)
                k = mark_safe('<span class="error-field error-%(k)s">%(k)s</span>' % {'k': k})
                form_errors[k] = v
            error_str += force_str(form_errors)
    errors = errors or [error_str]

    if log:
        log_error(request, view, action, errors, exc_info=exc_info)

    if len(errors) == 1:
        error_msg = "Error %s: %s" % (action, format_error(errors[0]))
    else:
        error_msg = "Errors %s: " % action
        error_msg += "<ul>"
        for error in errors:
            error_msg += "<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;%s</li>" % format_error(error)
        error_msg += "</ul>"
    return HttpResponse(json.dumps({'error': error_msg}), content_type='application/json')


class CropDusterException(Exception):
    pass


class CropDusterUrlException(CropDusterException):
    pass


class CropDusterViewException(CropDusterException):
    pass


class CropDusterModelException(CropDusterException):
    pass


class CropDusterImageException(CropDusterException):
    pass


class CropDusterFileException(CropDusterException):
    pass


class CropDusterResizeException(CropDusterException):
    pass


class CropDusterFileMissing(CropDusterFileException):
    """A referenced image file is missing from storage."""


class CropDusterConfigurationError(ImproperlyConfigured):
    """Cropduster cannot run with the current installation or settings."""


class ImageTooSmallError(CropDusterException):
    """An uploaded image is too small for one or more required sizes.

    The editor sees the value returned by ``str()``, so the message includes
    both the required and uploaded dimensions.
    """

    message_template = (
        "Image must be at least %(min_w)sx%(min_h)s "
        "(%(min_w)s pixels wide and %(min_h)s pixels high). "
        "The image you uploaded was %(orig_w)sx%(orig_h)s pixels.")

    def __init__(self, min_size, actual_size):
        self.min_size = tuple(min_size)
        self.actual_size = tuple(actual_size)
        super(ImageTooSmallError, self).__init__(self.message_template % {
            'min_w': self.min_size[0],
            'min_h': self.min_size[1],
            'orig_w': self.actual_size[0],
            'orig_h': self.actual_size[1],
        })
