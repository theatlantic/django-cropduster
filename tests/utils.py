import six


def esc_code(codes=None):
    if codes is None:
        # reset escape code
        return "\x1b[0m"
    if not isinstance(codes, (list, tuple)):
        codes = [codes]
    return '\x1b[0;' + ';'.join(map(six.text_type, codes)) + 'm'


def get_luminance(rgb):
    rgb_map = []
    for val in rgb:
        val = val / 256
        if val <= 0.03928:
            rgb_map.append(val / 12.92)
        else:
            rgb_map.append(pow((val + 0.055) / 1.055, 2.4))

    return (0.2126 * rgb_map[0]) + (0.7152 * rgb_map[1]) + (0.0722 * rgb_map[2])


def repr_rgb(rgb):
    r, g, b = rgb
    codes = (48, 2, r, g, b)
    reset = "\x1b[0m"
    hex_color = "#%s" % ("".join(["%02x" % c for c in rgb]))
    luminance = get_luminance(rgb)
    if luminance > 0.5:
        codes += (38, 2, 0, 0, 0)
    else:
        codes += (38, 2, 255, 255, 255)

    return "%(codes)s%(hex)s%(reset)s" % {
        'codes': esc_code(codes),
        'hex': hex_color,
        'reset': reset,
    }
