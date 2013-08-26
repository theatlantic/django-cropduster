import os
import re
import ctypes

import libxmp


check_file_format = libxmp._exempi.xmp_files_check_file_format
get_format_info = libxmp._exempi.xmp_files_get_format_info

if not check_file_format.argtypes:
    check_file_format.argtypes = [ctypes.c_char_p]
if not check_file_format.restype:
    check_file_format.restype = ctypes.c_ulong

if not get_format_info.argtypes:
    get_format_info.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
if not get_format_info.restype:
    get_format_info.restype = ctypes.c_bool


class EnumerationMeta(type):

    def __new__(cls, name, bases, attrs):
        if '_lookup' not in attrs:
            lookup = {}
            for k, v in attrs.iteritems():
                if isinstance(v, (int, long)):
                    lookup.setdefault(v, k)
            attrs['_lookup'] = lookup

        return super(EnumerationMeta, cls).__new__(cls, name, bases, attrs)

    def __contains__(self, value):
        return value in self._lookup


class Enumeration(object):
    __metaclass__ = EnumerationMeta
    @classmethod
    def value_name(cls, value):
        return cls._lookup.get(value)


class FormatOptions(Enumeration):

    XMP_FMT_CAN_INJECT_XMP = 0x0001
    XMP_FMT_CAN_EXPAND = 0x0002
    XMP_FMT_CAN_REWRITE = 0x0004
    XMP_FMT_PREFERS_IN_PLACE = 0x0008
    XMP_FMT_CAN_RECONCILE = 0x0010
    XMP_FMT_ALLOWS_ONLY_XMP = 0x0020
    XMP_FMT_RETURNS_RAW_PACKET = 0x0040
    XMP_FMT_HANDLER_OWNS_FILE = 0x0100
    XMP_FMT_ALLOW_SAFE_UPDATE = 0x0200
    XMP_FMT_NEEDS_READONLY_PACKET = 0x0400
    XMP_FMT_USE_SIDECAR_XMP = 0x0800
    XMP_FMT_FOLDER_BASED_FORMAT = 0x1000


class FileFormats(Enumeration):

    XMP_FT_PDF      = 0x50444620  # 'PDF '
    XMP_FT_PS       = 0x50532020  # 'PS  ', general PostScript following DSC conventions.
    XMP_FT_EPS      = 0x45505320  # 'EPS ', encapsulated PostScript.

    XMP_FT_JPEG     = 0x4A504547  # 'JPEG'
    XMP_FT_JPEG2K   = 0x4A505820  # 'JPX ', ISO 15444-1
    XMP_FT_TIFF     = 0x54494646  # 'TIFF'
    XMP_FT_GIF      = 0x47494620  # 'GIF '
    XMP_FT_PNG      = 0x504E4720  # 'PNG '

    XMP_FT_SWF      = 0x53574620  # 'SWF '
    XMP_FT_FLA      = 0x464C4120  # 'FLA '
    XMP_FT_FLV      = 0x464C5620  # 'FLV '

    XMP_FT_MOV      = 0x4D4F5620  # 'MOV ', Quicktime
    XMP_FT_AVI      = 0x41564920  # 'AVI '
    XMP_FT_CIN      = 0x43494E20  # 'CIN ', Cineon
    XMP_FT_WAV      = 0x57415620  # 'WAV '
    XMP_FT_MP3      = 0x4D503320  # 'MP3 '
    XMP_FT_SES      = 0x53455320  # 'SES ', Audition session
    XMP_FT_CEL      = 0x43454C20  # 'CEL ', Audition loop
    XMP_FT_MPEG     = 0x4D504547  # 'MPEG'
    XMP_FT_MPEG2    = 0x4D503220  # 'MP2 '
    XMP_FT_MPEG4    = 0x4D503420  # 'MP4 ', ISO 14494-12 and -14
    XMP_FT_WMAV     = 0x574D4156  # 'WMAV', Windows Media Audio and Video
    XMP_FT_AIFF     = 0x41494646  # 'AIFF'

    XMP_FT_HTML     = 0x48544D4C  # 'HTML'
    XMP_FT_XML      = 0x584D4C20  # 'XML '
    XMP_FT_TEXT     = 0x74657874  # 'text'

    # Adobe application file formats.
    XMP_FT_PHOTOSHOP       = 0x50534420  # 'PSD '
    XMP_FT_ILLUSTRATOR     = 0x41492020  # 'AI  '
    XMP_FT_INDESIGN        = 0x494E4444  # 'INDD'
    XMP_FT_AEPROJECT       = 0x41455020  # 'AEP '
    XMP_FT_AEPROJTEMPLATE  = 0x41455420  # 'AET ', After Effects Project Template
    XMP_FT_AEFILTERPRESET  = 0x46465820  # 'FFX '
    XMP_FT_ENCOREPROJECT   = 0x4E434F52  # 'NCOR'
    XMP_FT_PREMIEREPROJECT = 0x5052504A  # 'PRPJ'
    XMP_FT_PREMIERETITLE   = 0x5052544C  # 'PRTL'

    # Catch all.
    XMP_FT_UNKNOWN  = 0x20202020   # '    '


def file_format_supported(file_path):
    if not os.path.exists(file_path):
        raise IOError("File %s could not be found" % file_path)
    file_format = check_file_format(os.path.abspath(file_path))
    format_options = ctypes.c_int()
    if file_format != FileFormats.XMP_FT_UNKNOWN:
        format_options = get_format_info(
                file_format, ctypes.byref(format_options))
    if isinstance(format_options, ctypes.c_int):
        format_options = format_options.value
    return bool(format_options & FormatOptions.XMP_FMT_CAN_INJECT_XMP)


class MetadataDict(dict):
    """
    Normalizes the key/values returned from libxmp.file_to_dict()
    into something more useful. Among the transformations:

      - Flattens namespaces (file_to_dict returns metadata tuples keyed on
        the namespaces)
      - Removes namespace prefixes from keys (e.g. "mwg-rs", "xmpMM", "stArea")
      - Expands '/' and '[index]' into dicts and lists. For example
        the key 'mwg-rs:Regions/mwg-rs:RegionList[1]' becomes

            {'Regions': {'RegionList: []}}

        (note that list from libxmp.file_to_dict() are 1-indexed)
      - Converts stDim:* and stArea:* values into ints and floats,
        respectively
    """

    def __init__(self, file_path):
        self.file_path = file_path
        ns_dict = libxmp.file_to_dict(file_path)
        for ns, values in ns_dict.iteritems():
            for k, v, opts in values:
                current = self
                bits = k.split('/')
                for bit in bits[:-1]:
                    bit = bit.rpartition(':')[-1]
                    m = re.search(r'^(.*)\[(\d+)\](?=\/|\Z)', bit)
                    if not m:
                        current = current.setdefault(bit, {})
                    else:
                        bit = m.group(1)
                        index = int(m.group(2)) - 1
                        if isinstance(current.get(bit), list):
                            if len(current[bit]) < (index + 1):
                                current[bit] += [{}] * (1 + index - len(current[bit]))
                            current = current[bit][index]
                        else:
                            current[bit] = [{}] * (index + 1)
                            current = current[bit][index]

                if opts.get('VALUE_IS_ARRAY') and not v:
                    v = []
                elif opts.get('VALUE_IS_STRUCT') and not v:
                    v = {}

                ns_prefix, sep, k = bits[-1].rpartition(':')

                if ns_prefix == 'stDim' and k in ('w, h'):
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        v = None
                elif ns_prefix == 'stArea' and k in ('w', 'h', 'x', 'y'):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        v = None
                elif k == 'DerivedFrom' and isinstance(v, basestring):
                    v = re.sub(r'^xmp\.did:', '', v).lower()

                m = re.search(r'^(.*)\[(\d+)\](?=\/|\Z)', k)
                if m:
                    current = current.setdefault(m.group(1), [{}])
                    k = int(m.group(2)) - 1

                if isinstance(current, list) and isinstance(k, int):
                    if len(current) < k:
                        print 'len(current) = %s' % len(current)
                        print 'k = %s' % k
                        print 'current = %s' % current
                        current.append(*([{}] * (k - len(current))))

                # Now assign value to current position
                try:
                    current[k] = v
                except TypeError: # Special-case if current isn't a dict.
                    current = {k: v}
                except IndexError:
                    if k != 0 or not isinstance(current, list):
                        raise
                    current = [v]
