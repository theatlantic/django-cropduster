import os
import sys
import logging
import copy
import errno

try:
    from django.urls import get_urlconf, get_resolver
except ImportError:
    from django.core.urlresolvers import get_urlconf, get_resolver
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.utils import six
from django.utils.six.moves import xrange

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_unicode as force_text


logger = logging.getLogger('cropduster')


SentryHandler = raven_client = None


try:
    from sentry.client.handlers import SentryHandler
except ImportError:
    try:
        from raven.contrib.django.models import get_client
    except ImportError:
        pass
    else:
        raven_client = get_client()


if SentryHandler:
    logger.addHandler(SentryHandler())


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
    for i in xrange(skip + 2):
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

    if isinstance(error, six.string_types):
        return error
    elif isinstance(error, IOError):
        if error.errno == errno.ENOENT:  # No such file or directory
            file_name = get_relative_media_url(error.filename)
            return u"Could not find file %s" % file_name

    return u"[%(type)s] %(msg)s" % {
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
        except:
            exc_info = None
    if exc_info and not isinstance(exc_info, tuple) or not len(exc_info) or not exc_info[0]:
        exc_info = None

    if exc_info:
        log_kwargs["exc_info"] = exc_info

    extra_data = {
        'errors': errors,
        'process_id': os.getpid()
    }

    try:
        import psutil, math, time, thread
    except ImportError:
        pass
    else:
        p = psutil.Process(os.getpid())
        proc_timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.create_time))
        try:
            create_usec = six.text_type(p.create_time - math.floor(p.create_time))[1:5]
        except:
            create_usec = ''
        proc_timestamp += create_usec
        extra_data['process_create_date'] = proc_timestamp
        extra_data['thread_id'] = thread.get_ident()

    if isinstance(errors[0], CropDusterUrlException):
        urlconf = get_urlconf()
        resolver = get_resolver(urlconf)
        extra_data['resolver_data'] = {
            "regex": resolver.regex,
            "urlconf_name": resolver.urlconf_name,
            "default_kwargs": resolver.default_kwargs,
            "namespace": resolver.namespace,
            "urlconf_module": resolver.urlconf_module
        }

        resolver_reverse_dict = dict(
            [(force_text(k), resolver.reverse_dict[k]) for k in resolver.reverse_dict])
        resolver_namespace_dict = dict(
            [(force_text(k), resolver.namespace_dict[k]) for k in resolver.namespace_dict])

        extra_data.update({
            'resolver_data': {
                "regex": resolver.regex,
                "urlconf_name": resolver.urlconf_name,
                "default_kwargs": resolver.default_kwargs,
                "namespace": resolver.namespace,
                "urlconf_module": resolver.urlconf_module
            },
            'resolver_reverse_dict': resolver_reverse_dict,
            'resolver_namespace_dict': resolver_namespace_dict,
            'resolver_app_dict': resolver.app_dict,
            'resolver_url_patterns': resolver.url_patterns,
            'urlconf': urlconf,
            'view': 'cropduster.views.%s' % view,
        })

    raven_kwargs = {'request': request, 'extra': extra_data, 'data': {'message': error_msg}}

    if raven_client:
        if exc_info:
            return raven_client.get_ident(
                raven_client.captureException(exc_info=exc_info, **raven_kwargs))
        else:
            return raven_client.get_ident(
                raven_client.captureMessage(error_msg, **raven_kwargs))
    else:
        extra_data.update({
            'request': request,
            'url': request.path_info,
        })
        logger.error(error_msg, extra=extra_data, **log_kwargs)
        return None


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

    error_str = u''
    for forms in formset_errors:
        for form_errors in forms:
            for k in sorted(form_errors.keys()):
                v = form_errors.pop(k)
                k = mark_safe('<span class="error-field error-%(k)s">%(k)s</span>' % {'k': k})
                form_errors[k] = v
            error_str += force_text(form_errors)
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
