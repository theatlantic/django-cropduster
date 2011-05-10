import os

from django.conf import settings

# Main Media Settings
CROPDUSTER_MEDIA_ROOT = getattr(settings, "CROPDUSTER_MEDIA_ROOT", os.path.join(settings.MEDIA_ROOT, 'cropduster/'))
CROPDUSTER_MEDIA_URL = getattr(settings, "CROPDUSTER_MEDIA_URL", os.path.join(settings.MEDIA_URL, 'cropduster/'))

