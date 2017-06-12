import django
from django.template import Library

if django.VERSION < (1, 5):
    from django.templatetags.future import url as url_compat
else:
    from django.template.defaulttags import url as url_compat


register = Library()


@register.tag
def url(parser, token):
    return url_compat(parser, token)
