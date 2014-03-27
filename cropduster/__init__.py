import pkg_resources

try:
    __version__ = pkg_resources.get_distribution('django-cropduster').version
except pkg_resources.DistributionNotFound:
    __version__ = None
