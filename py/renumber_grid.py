import math
from pathlib import Path

# from lxml import etree
import lxml.etree as etree
import numpy as np
import numpy.typing as npt


ACROSS = 4
LONG = 5
# ACROSS = 40
# LONG = 53
COORD_BEARING = 270
COORD_DISTANCE = 6
COORD_SIZE = 5.333
GRID_GRAIN = 'h'
GRID_GRAIN_HORIZONTAL = 'h'
file = Path('grids/hexpage/div4.svg')
new_file = Path('grids/hexpage/div4_cart.svg')
# file = Path('grids/hexpage/div40.svg')
# new_file = Path('grids/hexpage/div40_cart.svg')
ATTR_TRANSFORM = 'transform'
ATTR_X = 'x'
ATTR_Y = 'y'
NAMESPACE = 'http://www.w3.org/2000/svg'
TAG_TEXT = f'{{{NAMESPACE}}}text'


class CoordShifter():
    """Parses text Cartesian pair and applies shift factors."""

    def __init__(self, text: str | None, x_shift: int, y_shift: int,
                 odd_row: bool) -> None:
        """Initialize object."""
        self.text = text
        self.x_shift = x_shift
        self.y_shift = y_shift
        self.odd_row = odd_row

    def parse_text(self) -> list[int] | None:
        """Get list of integers from text."""
        return_value = None
        if self.text is not None:
            comma = self.text.find(",")
            return_value = [int(self.text[:comma]), int(self.text[comma + 1:])]
        return return_value

    def shift(self) -> str | None:
        """Shift text by given shift factors."""
        ints = self.parse_text()
        return_value = None
        if ints is not None:
            x_new = str((ints[0] - self.x_shift) * 2 + self.odd_row)
            y_new = str(ints[1] - self.y_shift)
            return_value = f'{x_new},{y_new}'
        return return_value


def parse_svg(file: str | Path) -> etree._Element:
    """Parse file and return lxml etree object of contents."""
    xml = etree.parse(file)
    return xml.getroot()


def round_int(number: float) -> int:
    """Round to nearest integer, including when it's odd."""
    return math.ceil(number)


def shift_coordinates(svg: etree._Element, across_div: int,
                      long_div: int) -> etree._Element:
    """Get center hex and renumber coordinates as Cartesian grid."""
    x_shift = round_int((across_div + 1) / 2)
    y_shift = round_int(long_div / 2)
    long_count = 0
    for element in svg.iter(TAG_TEXT):
        odd_row = (long_count % 2 == 1)
        mover = CoordShifter(element.text, x_shift, y_shift, odd_row)
        element.text = mover.shift()
        if long_count < (long_div - 1):
            long_count += 1
        else:
            long_count = 0
    return svg


def write_svg(svg: etree._Element, file_path: Path, encoding: str,
              pretty_print: bool) -> None:
    """Write the svg to a file."""
    tree = svg.getroottree()
    tree.write(file_path, encoding=encoding, pretty_print=pretty_print,
               standalone=False)


########################################################################


def get_antibearing(bearing: int, grid_grain: str) -> float:
    """Get bearing in opposite direction of that given."""
    bearing = bearing + 90 * (grid_grain == GRID_GRAIN_HORIZONTAL)
    return math.radians(bearing - 180)


def get_hex_centers(hexes: npt.NDArray[np.float_], bearing: int,
                    grid_grain: str,
                    distance: float) -> npt.NDArray[np.float_]:
    """Get hex centers from array of hex textboxes."""
    antibearing = get_antibearing(bearing, grid_grain)
    return hexes + [np.cos(antibearing) * distance,
                    np.sin(antibearing) * distance]


def filter_coordinates(svg) -> None:
    """Get coordinates within big hex.

    The output of mkhexgrid.exe always has a horizontal grid grain
    internally. For vertical grid grains, the elements have a 90-degree-
    rotate transform attribute. This function is intended to be called
    before any resolution of those transforms is performed.

    Development stalled.
    """
    hexes = np.array([[float(ele.get(ATTR_X)), float(ele.get(ATTR_Y))]
                      for ele in svg.iter(TAG_TEXT)])
    hexes = get_hex_centers(hexes, COORD_BEARING, GRID_GRAIN, COORD_DISTANCE)
    hexes = hexes.reshape(ACROSS + 1, LONG, 2)
    print(hexes[20, 26, :])


def align_border_across():
    """Cribbed from live Python with Inkscape."""
    GRID_LONG_INK = 795.929     # div42 vertical
    GRID_WIDTH = 0.5
    DIV_ACROSS = 42
    return (GRID_LONG_INK - GRID_WIDTH) / (DIV_ACROSS + 1) / 2 - GRID_WIDTH


def run_main() -> None:
    """Run script."""
    svg = parse_svg(file)
    # filter_coordinates(svg)
    svg = shift_coordinates(svg, ACROSS, LONG)
    write_svg(svg, new_file, 'utf-8', True)


if __name__ == '__main__':
    run_main()
