from collections.abc import Sequence
# from dataclasses import dataclass, field
import math
from pathlib import Path
from pprint import pprint
import shutil
from typing import Any, cast, Optional, Self, TypedDict
import warnings

from ruamel.yaml import YAML

import mkhexgrid_wrapper as mw


SQRT3 = math.sqrt(3)
INTERSECTION_CENTER = 0
INTERSECTION_OUTER = 1
INTERSECTION_INNER = 2
HP_ACROSS = 'length_across'
HP_ACROSS_DIVS = 'divisions_across'
HP_BORDER_HEX = 'border_hex'
HP_DIR = 'page_dir'
HP_HEXPAGE = 'hexpage'
HP_ICOPAGE = 'icopage'
HP_IMAGE_LONG = 'image_long'
HP_IMAGE_ACROSS = 'image_across'
HP_LONG = 'length_long'
HP_LONG_DIVS = 'divisions_long'
HP_MASK_BACKGROUND = 'ffaaaa'
HP_X = 'x'
HP_Y = 'y'
HP_COORD_FORMAT_AS_MKHEXGRID = 'coord_format_as_mkhexgrid'
HP_COORDS_FIXED_TO_GRAIN = 'coords_fixed_to_grain'
HP_SHOW_OUTPUT = 'show_output'
HP_TOOL = 'tool'
MHG_BACKGROUND_COLOR = 'background_color'
MHG_C = 'c'
MHG_COLUMNS = 'columns'
MHG_COORD_FORMAT = 'coord_format'
MHG_DEFAULT_GRID_GRAIN = 'v'
MHG_DEFAULT_GRID_THICKNESS = 1
MHG_DEFAULT_OUTPUT = 'png'
MHG_GRID_GRAIN = 'grid_grain'
MHG_GRID_THICKNESS = 'grid_thickness'
MHG_HEX_HEIGHT = 'hex_height'
MHG_HEX_WIDTH = 'hex_width'
MHG_IMAGE_HEIGHT = 'image_height'
MHG_IMAGE_WIDTH = 'image_width'
MHG_MATTE = 'matte'
MHG_OUTFILE = 'outfile'
MHG_OUTPUT = 'output'
MHG_R = 'r'
MHG_ROWS = 'rows'
YAML_LOADER_SAFE = 'safe'
LIST_OF_DICTS_INDEX_KEY = 'name'    # Not used but needed by copied code
defaults = Path('hex_defaults.yml')


class IncompleteHexDimensionsGivenError(mw.BaseError):
    """Not enough settings were given to calculate the rest."""

    def __init__(self) -> None:
        self.message = ('Not enough settings were given to make a hexpage or '
                        'icopage.\nOne of either "length_across" or '
                        '"length_long" must be given in the "hexpage" (or '
                        '"icopage")\npart of the run settings. '
                        'Likewise, one of "divisions_across" or '
                        '"divisions_long" must be\npresent as well.')


class ProgramNotFoundError(mw.BaseError):
    """Tool used with subprocess was not found."""

    def __init__(self, argument: str) -> None:
        super().__init__(argument)
        self.message = (f'The program, "{argument}" could not be found on the '
                        'system or user PATH.\nEither add it to one of those '
                        'environment variables or include the full path to '
                        'a new line\nin the run settings YAML file like the '
                        'following:\n\ngrid_maker_general:\n'
                        f'  tool: "C:\\path\\to\\{argument}.exe"')


def more_hex_dimensions_given_than_needed_warning() -> None:
    """Warn about extra settings."""
    warnings.warn(('More settings were given than are needed to make a hexpage'
                   ' or an icopage.\nOnly one of "length_across" or '
                   '"length_long" and one of "divisions_across" or '
                   '"divisions_long"\nare needed. The others are then '
                   'calculated.\n\nBy default, the "across" settings are used '
                   'as given with calculated values superseding any given for '
                   'the "long" settings.\n'), stacklevel=2)


class GridMakerGeneralParams(TypedDict):
    """General parameters for the GridMaker."""
    tool: str
    show_output: bool


class BorderBoxParams(TypedDict):
    """Settings for icopage border rectangle."""
    thickness: float
    # TODO: add equivalents of mkhexgrid center settings.


class PageMakerSettings(TypedDict):
    """Settings for each page made."""
    name: str
    divs: list[int]


class MapSettings(TypedDict):
    """Settings in the hex_page or ico_page section."""
    border: BorderBoxParams
    border_hex: mw.HexMakerParams
    coord_format_as_mkhexgrid: bool
    coord_plan: str
    coords_fixed_to_grain: bool
    divisions_across: Optional[list[int]]
    divisions_long: Optional[list[int]]
    highlights: Optional[mw.HexMakerParams]
    image_across: Optional[float]
    image_long: Optional[float]
    page_dir: str
    length_across: Optional[int]
    length_long: Optional[int]
    pages: Optional[list[PageMakerSettings]]


class GridMakerSettings(TypedDict):
    """All settings available for producing hex_pages and ico_pages."""
    grid_maker_general: GridMakerGeneralParams
    fixed: mw.HexMakerParams
    variable: dict[int, mw.HexMakerParams]
    subprocess_kwargs: mw.SubprocessKwargs
    hexpage: MapSettings
    icopage: MapSettings


class Base(object):
    """Base class with more informative __repr__."""

    def __repr__(self) -> str:
        """Object representation."""
        params = (f'{key}={repr(self.__dict__[key])}' for key in self.__dict__)
        return f'{repr(self.__class__)}({", ".join(params)})'


class SettingsHandler(Base):
    """Handle settings for producing pages."""

    def __init__(self,
                 grid_maker_general: GridMakerGeneralParams,
                 fixed: mw.HexMakerParams,
                 variable: dict[int, mw.HexMakerParams],
                 subprocess_kwargs: mw.SubprocessKwargs,
                 hexpage: MapSettings,
                 icopage: MapSettings) -> None:
        """Initialize object."""
        self.grid_maker_general = grid_maker_general
        self.fixed = fixed
        self.variable = variable
        self.subprocess_kwargs = subprocess_kwargs
        self.hexpage = hexpage
        self.icopage = icopage
        self.check_tool()

    def check_tool(self) -> None:
        """Check that object can use mkhexgrid."""
        # tool_not_found = False
        try:
            _ = self.grid_maker_general[HP_TOOL]
        except KeyError:
            self.grid_maker_general[HP_TOOL] = mw.TOOL
        if shutil.which(self.grid_maker_general[HP_TOOL]) is None:
            raise ProgramNotFoundError(mw.TOOL)

    @classmethod
    def from_yaml(cls: type[Self], doc: Path,
                  typ: str = YAML_LOADER_SAFE) -> Self:
        """Fill class instance with settings from one yaml file."""
        return cls(**cast(GridMakerSettings, load_yaml(doc, typ)))

    @classmethod
    def from_yamls_or_dicts(cls: type[Self],
                            dicts_or_files: list[str | Path | dict[Any, Any]],
                            typ: str = YAML_LOADER_SAFE) -> Self:
        """Fill class instance from list of yaml paths or dicts."""
        merger = DictMerger([get_dict_from_file(yaml_dict)
                             for yaml_dict in dicts_or_files])
        settings = merger.merge_all()
        return cls(**cast(GridMakerSettings, settings))


def get_dict_from_file(dict_or_file: str | Path | dict[Any, Any],
                       typ: str = YAML_LOADER_SAFE) -> dict[Any, Any]:
    """Get list of loaded yaml files or passed-through dicts."""
    if not isinstance(dict_or_file, dict):
        dict_or_file = load_yaml(dict_or_file, typ)
    return dict_or_file


class GridGrainOrienter(Base):
    """Adjusts mkhexgrid parameters based on grid_grain setting.

    Some mkhexgrid settings are best thought about in terms of a map
    being oriented to the terrain; rows aren't up and down on a page but
    ahead and behind as one looks at a properly-turned map.

    This is because using a horizontal grid grain can have surprising
    results. Rows become columns, and coordinate formats look reversed.
    For those parameters, the grain is always vertical; it's just that
    the map is no longer presented on the page in portait layout but in
    landscape.

    Furthermore, hexes are measured across by height in vertically-
    grained grids, and this corresponds to using the width with a
    horizontal grain. These parameters do not rotate like rows and
    columns, but their prominence is swapped. Confusingly, image_height
    and image_width do rotate, which solidifies the portrait vs.
    landscape model.

    Therefore, the hexpage scheme deviates from mkhexgrid in order to
    smooth out these differences.
        across: The measure of a hex from side to side (or center to the
                center of an adjacent hex).
        long: The measure of a hex from one point to the opposite point,
              which ie equal to twice the length of a side.
        x, y: Coordinate values relative to the drawing rather than the
              grain grid. X is always side-to-side and Y is always up-
              and-down.
    """
    by_grain = {mw.GRID_GRAIN_HORIZONTAL: {HP_ACROSS: MHG_HEX_WIDTH,
                                           HP_ACROSS_DIVS: MHG_COLUMNS,
                                           HP_LONG: MHG_HEX_HEIGHT,
                                           HP_LONG_DIVS: MHG_ROWS,
                                           HP_IMAGE_ACROSS: MHG_IMAGE_HEIGHT,
                                           HP_IMAGE_LONG: MHG_IMAGE_WIDTH,
                                           HP_X: MHG_R,
                                           HP_Y: MHG_C},
                mw.GRID_GRAIN_VERTICAL: {HP_ACROSS: MHG_HEX_HEIGHT,
                                         HP_ACROSS_DIVS: MHG_ROWS,
                                         HP_LONG: MHG_HEX_WIDTH,
                                         HP_LONG_DIVS: MHG_COLUMNS,
                                         HP_IMAGE_ACROSS: MHG_IMAGE_WIDTH,
                                         HP_IMAGE_LONG: MHG_IMAGE_HEIGHT,
                                         HP_X: MHG_C,
                                         HP_Y: MHG_R}}

    def __init__(self, grid_grain: str,  # coord_format: str,
                 coords_fixed_to_grain: bool) -> None:
        """Initialize object"""
        self.grid_grain = grid_grain
        self.coords_fixed_to_grain = coords_fixed_to_grain
        self.axes = self.by_grain[grid_grain]
        self.x = self.get_coord(HP_X)
        self.y = self.get_coord(HP_Y)

    def adjust_coord_format(self, coord_format: str | None) -> str | None:
        """Translate coord_format to send to mkhexgrid."""
        if coord_format is None:
            return coord_format
        adjustments = {HP_X: self.x, HP_Y: self.y}
        for key in adjustments.keys():
            coord_format = coord_format.replace(key, adjustments[key])
            coord_format = coord_format.replace(key.upper(),
                                                adjustments[key].upper())
        return coord_format

    def get_coord(self, coord: str) -> str:
        """Get character to send to mkhexgrid for coordinate."""
        lookup = self.grid_grain
        if self.coords_fixed_to_grain:
            lookup = mw.GRID_GRAIN_VERTICAL
        return self.by_grain[lookup][coord]


class PagePlanner(Base):
    """Get values given and those calculated between across and long."""

    def __init__(self, page_type: str, checks: tuple[bool, bool]) -> None:
        """Initialize object."""
        calc_across, calc_divs_across = checks
        self.page_type = page_type
        self.divs_calc_func = plus_one
        self.calc_across = calc_across
        if calc_across:
            self.given = HP_LONG
            self.calc = HP_ACROSS
        else:
            self.given = HP_ACROSS
            self.calc = HP_LONG
        if calc_divs_across:
            self.given_divs = HP_LONG_DIVS
            self.calc_divs = HP_ACROSS_DIVS
            if page_type == HP_HEXPAGE:
                self.divs_calc_func = hexes_across
        else:
            self.given_divs = HP_ACROSS_DIVS
            self.calc_divs = HP_LONG_DIVS
            if page_type == HP_HEXPAGE:
                self.divs_calc_func = hexes_long


class GridMaker(Base):
    """Makes hex grids using mkhexgrid."""

    def __init__(self, settings: SettingsHandler) -> None:
        """Initialize object."""
        self.settings = settings
        self.results = []

    def check_page_settings(self, page_type: str) -> tuple[bool, bool]:
        """Check that enough setings are given to calculate the rest."""
        page_settings = getattr(self.settings, page_type)
        settings = [HP_ACROSS, HP_ACROSS_DIVS, HP_LONG, HP_LONG_DIVS]
        presents = {setting: dict_has_key(page_settings, setting)
                    for setting in settings}
        if ((not presents[HP_LONG] and not presents[HP_ACROSS])
           or (not presents[HP_LONG_DIVS] and not presents[HP_ACROSS_DIVS])):
            raise IncompleteHexDimensionsGivenError()
        if ((presents[HP_LONG] and presents[HP_ACROSS])
           or (presents[HP_LONG_DIVS] and presents[HP_ACROSS_DIVS])):
            more_hex_dimensions_given_than_needed_warning()
        calc_across = (presents[HP_LONG] and not presents[HP_ACROSS])
        calc_divs_across = (presents[HP_LONG_DIVS]
                            and not presents[HP_ACROSS_DIVS])
        return (calc_across, calc_divs_across)

    def format_coord(self, settings: mw.HexMakerParams,
                     orienter: GridGrainOrienter,
                     coord_format_as_mkhexgrid: bool) -> None:
        """Use orienter to modify coord_format setting, if needed."""
        if not coord_format_as_mkhexgrid:
            try:
                coord_format = settings[MHG_COORD_FORMAT]
            except KeyError:
                pass
            else:
                adjusted = orienter.adjust_coord_format(coord_format)
                settings[MHG_COORD_FORMAT] = adjusted

    def get_border_thickness(self, page_settings, planner) -> float:
        """Get grid_thickness setting from hexpage border_hex."""
        border_hex = page_settings[HP_BORDER_HEX]
        try:
            grid_thickness = border_hex[MHG_GRID_THICKNESS]
        except KeyError:
            grid_thickness = MHG_DEFAULT_GRID_THICKNESS
        if planner.given == HP_LONG:
            grid_thickness *= (2 / SQRT3)
        return grid_thickness

    def get_calc_settings(self, page_settings: MapSettings,
                          planner: PagePlanner,
                          orienter: GridGrainOrienter,
                          div: int) -> mw.HexMakerParams:
        """Get settings calculated from those present."""
        calcs = {MHG_OUTFILE: self.name_outfile(page_settings[HP_DIR], div),
                 orienter.axes[planner.given]:
                 page_settings[planner.given] / div,
                 orienter.axes[planner.given_divs]: div + 1,
                 orienter.axes[planner.calc_divs]: planner.divs_calc_func(div)}
        for setting in [HP_IMAGE_ACROSS, HP_IMAGE_LONG]:
            try:
                calcs.update({orienter.axes[setting]: page_settings[setting]})
            except KeyError:
                pass
        return cast(mw.HexMakerParams, calcs)

    def get_grid_grain(self) -> str:
        """Get grid_grain value."""
        try:
            return_value = self.settings.fixed[MHG_GRID_GRAIN]
        except KeyError:
            return_value = MHG_DEFAULT_GRID_GRAIN
        return return_value

    def get_suffix(self) -> str:
        """Get file extension for desired output format."""
        try:
            suffix = self.settings.fixed[MHG_OUTPUT]
        except KeyError:
            suffix = MHG_DEFAULT_OUTPUT
        return suffix

    def make_border_hex(self, page_settings: MapSettings,
                        orienter: GridGrainOrienter, planner: PagePlanner,
                        ) -> None:
        """Make big hex border around hexpage."""
        div_settings = {MHG_OUTFILE: (f'{page_settings[HP_DIR]}'
                                      f'\\border.{self.get_suffix()}'),
                        orienter.axes[planner.given]:
                        page_settings[planner.given],
                        MHG_ROWS: 1, MHG_COLUMNS: 1}
        div_settings.update(page_settings[HP_BORDER_HEX])
        self.make_one_grid(cast(mw.HexMakerParams, div_settings))

    def make_grids(self, page_type: str) -> None:
        """Make grid svgs for all divisions."""
        planner = PagePlanner(page_type, self.check_page_settings(page_type))
        page_settings = getattr(self.settings, page_type)
        orienter = GridGrainOrienter(self.get_grid_grain(),
                                     page_settings[HP_COORDS_FIXED_TO_GRAIN])
        for div in page_settings[planner.given_divs]:
            try:
                div_settings = self.settings.variable[div].copy()
            except KeyError:
                div_settings = cast(mw.HexMakerParams, {})
            div_settings.update(self.get_calc_settings(page_settings, planner,
                                                       orienter, div))
            self.format_coord(div_settings, orienter,
                              page_settings[HP_COORD_FORMAT_AS_MKHEXGRID])
            self.make_one_grid(div_settings)
        if page_type == HP_HEXPAGE:
            self.make_border_hex(page_settings, orienter, planner)
            self.make_mask_hex(page_settings, orienter, planner)
        if self.settings.grid_maker_general[HP_SHOW_OUTPUT]:
            pprint(self.results)

    def make_hexpage_grids(self) -> None:
        """Make grid svgs for use in hexpages."""
        self.make_grids(HP_HEXPAGE)

    def make_icopage_grids(self) -> None:
        """Make grid svgs for use in icopages."""
        self.make_grids(HP_ICOPAGE)

    def make_mask_hex(self, page_settings: MapSettings,
                      orienter: GridGrainOrienter, planner: PagePlanner,
                      ) -> None:
        """Make start of mask for hexpage interior.

        This requires further tweaking elsewhere to remove the stroke
        and add the fill, but at least the size is calculated.
        """
        grid_thickness = self.get_border_thickness(page_settings, planner)
        div_settings = ({MHG_OUTFILE: (f'{page_settings[HP_DIR]}'
                                       f'\\mask.{self.get_suffix()}'),
                         orienter.axes[planner.given]:
                         page_settings[planner.given] - grid_thickness,
                         MHG_ROWS: 1, MHG_COLUMNS: 1})
        self.make_one_grid(cast(mw.HexMakerParams, div_settings))

    def make_one_grid(self, div_settings: mw.HexMakerParams) -> None:
        """Make one grid destined for hexpage or icopage."""
        run_settings = self.settings.fixed.copy()
        run_settings.update(div_settings)
        out_dir = Path(run_settings[MHG_OUTFILE]).parent  # type: ignore
        if not out_dir.exists():
            out_dir.mkdir(parents=True)
        mhg = mw.MkHexGrid(run_settings,
                           tool=self.settings.grid_maker_general[HP_TOOL])
        self.results.append(mhg.run(self.settings.subprocess_kwargs))

    def name_outfile(self, out_dir: str, div: int) -> str:
        """Get path of file to which to write output."""
        return f'{out_dir}/div{div}.{self.get_suffix()}'


class PageMaker(Base):
    """Assemble grids into pages."""

    def __init__(self, settings: SettingsHandler) -> None:
        """Initialize object."""
        self.settings = settings


class DictMerger(Base):
    """Merge dicts, updating any nested dicts."""

    def __init__(self, top_dicts: list[dict[Any, Any]],
                 list_index_key: str = LIST_OF_DICTS_INDEX_KEY) -> None:
        """Initialize object.

        In this case, list_index_key isn't in use but was inherited from
        where these functions were developed.
        """
        self.merged = top_dicts.pop(0)
        self.top_dicts = top_dicts
        self.list_index_key = list_index_key

    def get_dict_by_item(self, dicts: list[dict[Any, Any]],
                         target: Any) -> dict[Any, Any] | None:
        """Get dict from list where dict[key] == value."""
        dict_found = False
        return_dict = None
        for list_dict in dicts:
            for item_key, item_value in list_dict.items():
                if item_key == self.list_index_key and item_value == target:
                    return_dict = list_dict
                    dict_found = True
                    break
            if dict_found:
                break
        return return_dict

    def merge_all(self) -> dict[Any, Any]:
        """Merge all dicts present."""
        for top_dict in self.top_dicts:
            self.update_by_key(self.merged, top_dict)
        return self.merged

    def update_by_key(self, update_to: dict[Any, Any],
                      update_from: dict[Any, Any]) -> None:
        """Update nested dictionary from another key by key."""
        for key, from_value in update_from.items():
            try:
                to_value = update_to[key]
            except KeyError:
                update_to.update({key: from_value})
            else:
                if isinstance(from_value, dict):
                    self.update_by_key(to_value, from_value)
                elif is_list_or_tuple(from_value) and to_value is not None:
                    update_to[key] = self.update_list(to_value, from_value)
                else:
                    update_to[key] = from_value

    def update_list(self, update_tos: list[Any],
                    update_froms: list[Any]) -> list[Any] | None:
        """Update list values.

        At this time, it is assumed that a sorted list of unique values
        is desired. Yeah, more parameters should  be created for this,
        but not now.
        """
        returns = None
        if update_tos is not None and update_froms is not None:
            update_tos.extend(update_froms)
            returns = sorted(list(set(update_tos)))
        return returns

    def update_list_of_dicts(self, update_tos: list[dict[str, Any]],
                             update_froms: list[dict[str, Any]]) -> None:
        """Update each dict in list from dict with matching key value."""
        for item_from in update_froms:
            try:
                item_to = self.get_dict_by_item(update_tos,
                                                item_from[self.list_index_key])
            except KeyError:
                item_to = None
            if item_to is not None:
                self.update_by_key(item_to, item_from)
            else:
                update_tos.append(item_from)


def dict_has_key(dict_to_check: dict[Any, Any], key: Any,
                 allow_none: bool = False) -> bool:
    """Check if key is present in dict."""
    is_present = False
    try:
        check = dict_to_check[key]
        if not allow_none and check is not None:
            is_present = True
    except KeyError:
        pass
    return is_present


def is_list_or_tuple(variable: Any) -> bool:
    """Check if variable is a list or tuple but not a string."""
    return isinstance(variable, Sequence) and not isinstance(variable, str)


def load_yaml(doc: str | Path, typ: str = YAML_LOADER_SAFE) -> dict[Any, Any]:
    """Load yaml doc with ruamel.yaml."""
    loader = YAML(typ=typ)
    return loader.load(Path(doc))


def grid_intersection_type(division: int) -> int:
    """Get type of intersection between a grid and one dividing it."""
    return division % 3


def hex_across(hex_long: float | int) -> float:
    """Get length of hex across."""
    return SQRT3 / 2 * hex_long


def hex_long(hex_across: float | int) -> float:
    """Get length of hex from point to point."""
    return 2 / SQRT3 * hex_across


def hexes_across(hexes_long: int) -> int:
    """Get subhexes to fill hex across given those point to point.

    This doesn't work as well as using a known number of divisions
    across to calculate those needed long, since not all integers will
    yield integer results going this way. It is included for the sake of
    unforeseen possibilities.
    """
    if grid_intersection_type(hexes_long) != INTERSECTION_OUTER:
        hexes_long += -1
    return int(3 / 4 * hexes_long)


def hexes_long(hexes_across: int) -> int:
    """Get subhexes to fill hex point to point given those across."""
    return_value = int(4 / 3 * hexes_across)
    if grid_intersection_type(hexes_across) != INTERSECTION_OUTER:
        return_value += 1
    return return_value


def plus_one(number: int) -> int:
    """Add one to number and be a callable."""
    return number + 1


def run_main() -> None:
    """Main run function."""
    # settings = SettingsHandler.from_yaml(defaults)
    settings = SettingsHandler.from_yamls_or_dicts([defaults,
                                                   'sample_hexes.yml'])
    grid_maker = GridMaker(settings)
    grid_maker.make_hexpage_grids()
    grid_maker.make_icopage_grids()


if __name__ == '__main__':
    run_main()
