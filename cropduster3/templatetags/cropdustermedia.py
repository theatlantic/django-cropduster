from django.template import Library
from django.utils.encoding import iri_to_uri
from django.core.urlresolvers import reverse

register = Library()


def cropduster_media_prefix():
    """
    Returns the string contained in the setting ADMIN_MEDIA_PREFIX.
    """
    media_url = reverse('cropduster-static', kwargs={'path': ''})
    return iri_to_uri(media_url)

cropduster_media_prefix = register.simple_tag(cropduster_media_prefix)
