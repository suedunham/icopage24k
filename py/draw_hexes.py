import math


LINE_BOTTOM = 1031.933

big = {'x': 792,
       'y_top': 773.154,
       'y_bottom': LINE_BOTTOM}
middle = {'x': 592.403,
          'y_top': 888.392,
          'y_bottom': LINE_BOTTOM}
small = {'x': 472.635,
         'y_top': 957.540,
         'y_bottom': LINE_BOTTOM}


def hex_beside_line(x, y_top, y_bottom):
    """Get svg path for hexagon beside a given line."""
    line_length = y_bottom - y_top
    interval = (line_length) / 5
    half_width = interval * math.sqrt(3)
    side_top = y_top + 2 * interval
    side_bottom = y_top + 4 * interval
    hex_top = f'{x - half_width},{y_top + interval}'
    hex_right = f'{x},{side_top}'
    hex_bottom = f'{x - half_width},{y_bottom}'
    hex_left = f'{x - 2 * half_width},{side_bottom}'
    return (f'M {hex_top} {hex_right} V {side_bottom} L {hex_bottom}'
            f' {hex_left} V {side_top} Z')


print(hex_beside_line(**big))
