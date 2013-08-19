__version_info__ = (4, 0, 0, 'rc2')
__version__ = '.'.join(map(str, __version_info__))

# Import these into module root for API simplicity
from .resizing import Size, Box, Crop
