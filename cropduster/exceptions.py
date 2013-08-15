import os
import sys
import logging
import copy
import errno

from django.http import HttpResponse
from django.utils.safestring import mark_safe


logger = logging.getLogger('root')


try:
    from sentry.client.handlers import SentryHandler
except ImportError:
    try:
        from raven.handlers.logging import SentryHandler
    except ImportError:
        SentryHandler = None


if SentryHandler:
    logger.addHandler(SentryHandler())


def format_error(error):
    from .utils import get_relative_media_url

    if isinstance(error, basestring):
        return error
    elif isinstance(error, IOError):
        if error.errno == errno.ENOENT: # No such file or directory
            file_name = get_relative_media_url(error.filename)
            return u"Could not find file %s" % file_name

    return u"[%(type)s] %(msg)s" % {
        'type': error.__class__.__name__,
        'msg': error,
    }


def log_error(request, view, action, errors):
    # We only log the first error, send the rest as data; it's simpler this way
    error_msg = "Error %s: %s" % (action, format_error(errors[0]))

    log_kwargs = {}

    if not isinstance(errors[0], basestring):
        log_kwargs["exc_info"] = sys.exc_info()

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
            create_usec = str(p.create_time - math.floor(p.create_time))[1:5]
        except:
            create_usec = ''
        proc_timestamp += create_usec
        extra_data['process_create_date'] = proc_timestamp
        extra_data['thread_id'] = thread.get_ident()

    if isinstance(errors[0], CropDusterUrlException):
        from django.core.urlresolvers import get_urlconf,get_resolver
        from django.utils.encoding import force_unicode
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
            [(force_unicode(k), resolver.reverse_dict[k]) for k in resolver.reverse_dict])
        resolver_namespace_dict = dict(
            [(force_unicode(k), resolver.namespace_dict[k]) for k in resolver.namespace_dict])

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
        })

    logger.error(error_msg, extra={
            'request': request,
            'view': 'cropduster.views.%s' % view,
            'url': request.path_info,
            'data': extra_data
        }, **log_kwargs)


def json_error(request, view, action, errors=None, forms=None, formsets=None, log_error=False):
    from .utils import json

    if forms:
        formset_errors = [[copy.deepcopy(f.errors) for f in forms]]
    elif formsets:
        formset_errors = [copy.deepcopy(f.errors) for f in formsets]
    else:
        formset_errors = []

    if not errors and not formset_errors:
        return

    error_str = u''
    for forms in formset_errors:
        for form_errors in forms:
            for k in sorted(form_errors.keys()):
                v = form_errors.pop(k)
                k = mark_safe('<span class="error-field error-%(k)s">%(k)s</span>' % {'k': k})
                form_errors[k] = v
            error_str += unicode(form_errors)
    errors = errors or [error_str]

    if log_error:
        log_error(request, view, action, errors)

    if len(errors) == 1:
        error_msg = "Error %s: %s" % (action, format_error(errors[0]))
    else:
        error_msg =  "Errors %s: " % action
        error_msg += "<ul>"
        for error in errors:
            error_msg += "<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;%s</li>" % format_error(error)
        error_msg += "</ul>"
    return HttpResponse(json.dumps({'error': error_msg}))


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
