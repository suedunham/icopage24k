from dataclasses import dataclass
import re
import subprocess
from pathlib import Path
import shutil
from typing import Any, cast, Optional, Mapping, TypedDict


TOOL = 'mkhexgrid'
HELP_URL = 'https://www.nomic.net/~uckelman/mkhexgrid/mkhexgrid.html'
OUTPUT = 'output'
OUTPUT_PNG = 'png'
OUTPUT_PS = 'ps'
OUTPUT_SVG = 'svg'
OUTPUTS = [OUTPUT_PNG, OUTPUT_PS, OUTPUT_SVG]
PS_UNIT_INCH = 'in'
PS_UNIT_MILLIMETER = 'mm'
PS_UNIT_POINT = 'pt'
PS_UNITS = [PS_UNIT_INCH, PS_UNIT_MILLIMETER, PS_UNIT_POINT]
GRID_START_IN = 'i'
GRID_START_OUT = 'o'
GRID_STARTS = [GRID_START_IN, GRID_START_OUT]
GRID_GRAIN_HORIZONTAL = 'h'
GRID_GRAIN_VERTICAL = 'v'
GRID_GRAINS = [GRID_GRAIN_HORIZONTAL, GRID_GRAIN_VERTICAL]
COORD_ORIGIN_UPPER_LEFT = 'ul'
COORD_ORIGIN_UPPER_RIGHT = 'ur'
COORD_ORIGIN_LOWER_LEFT = 'll'
COORD_ORIGIN_LOWER_RIGHT = 'lr'
COORD_ORIGINS = [COORD_ORIGIN_UPPER_LEFT, COORD_ORIGIN_UPPER_RIGHT,
                 COORD_ORIGIN_LOWER_LEFT, COORD_ORIGIN_LOWER_RIGHT]
CENTER_STYLE_NONE = 'n'
CENTER_STYLE_DOT = 'd'
CENTER_STYLE_CROSS = 'c'
CENTER_STYLES = [CENTER_STYLE_NONE, CENTER_STYLE_DOT, CENTER_STYLE_CROSS]
hex_color_pattern = re.compile(r'(?i)^[0-9A-F]{6}$')
coord_format_pattern = re.compile(r'^(?:.*%(?:t?[CR]|0?\d?[cr])){2}.*$')


class BaseError(Exception):
    """Base exception class."""

    def __init__(self, argument: str = "") -> None:
        self.argument = argument
        self.message = "Base exception message has not been overwritten."
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ProgramNotFoundError(BaseError):
    """Tool used with subprocess was not found."""

    def __init__(self, argument: str, class_name: str) -> None:
        super().__init__(argument)
        self.message = (f'The program, "{argument}" could not be found on the '
                        'system or user PATH.\nEither add it to one of those '
                        'environment variables or include the full path to it '
                        'when initializing the wrapper\nobject like the '
                        f'following:\n\nobj = {class_name}(settings, '
                        f'tool="C:\\path\\to\\{argument}.exe")')


class UnknownParameterError(BaseError):
    """Unknown error passed to MkHexGrid object."""

    def __init__(self, argument: str, allowed_values: list[str]) -> None:
        super().__init__(argument)
        delim = ', '
        self.message = (f'An unknown parameter, "{argument}", was given to '
                        'the MkHexGrid object.\nAllowed parameters include the'
                        f' following:\n{delim.join(sorted(allowed_values))}')


class ParamBase():
    """Base class for parameter classes."""

    def __init__(self, param: str, value: Any, tool_arg: str = "") -> None:
        self.param = param
        self.value = value
        self.tool_arg = tool_arg

    def __str__(self) -> str:
        """String used for parameter in subprocess call."""
        return f'{self.tool_arg}={str(self.value)}'

    def debug(self) -> tuple[bool, str]:
        """Return passed."""
        return self.get_pass_result()

    def get_pass_result(self) -> tuple[bool, str]:
        """Get default debug test passed result tuple."""
        return (True, f'{self.param} passed')


class ParamFromList(ParamBase):
    """Base class for parameters within listed values."""

    def __init__(self, param: str, value: str, tool_arg: str,
                 value_options: list[str]) -> None:
        """Initialize object."""
        super().__init__(param, value, tool_arg)
        self.value_options = value_options

    def debug(self) -> tuple[bool, str]:
        """Check given parameter value for problems."""
        return_value = self.get_pass_result()
        if self.value not in self.value_options:
            return_value = (False, self.get_list_message())
        return return_value

    def get_list_message(self) -> str:
        """Get debug message for value not in list."""
        delim = '", "'
        return (f'The parameter, "{self.param}", must be one of the '
                f'following values: "{delim.join(self.value_options)}".\n'
                f'Instead, "{self.value}" was given.')


class ParamNumber(ParamBase):
    """Class with numeric arguments."""

    def debug_float(self, output_obj: Optional[ParamFromList] = None
                    ) -> tuple[bool, str]:
        """Check that value can be converted to float."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". A number is required.')
        value = self.get_value_numeric(output_obj)
        try:
            _ = float(value)
        except ValueError:
            return_value = (False, message)
        return return_value

    def debug_int(self, output_obj: Optional[ParamFromList] = None
                  ) -> tuple[bool, str]:
        """Check that value can be converted to int."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". An integer is required.')
        value = self.get_value_numeric(output_obj)
        try:
            value_int = int(value)
        except ValueError:
            return_value = (False, message)
        else:
            if isinstance(value, float) and value != value_int:
                return_value = (False, message)
        return return_value

    def get_value_numeric(self, output_obj: Optional[ParamFromList] = None
                          ) -> str | int | float:
        """Get numeric part of value without any unit present."""
        value = self.value
        if output_obj is not None:
            if output_obj.value == OUTPUT_PS:
                try:
                    unit = value[-2:]
                except TypeError:
                    pass
                else:
                    if unit in OUTPUTS:
                        value = value[:-2]
        return value


class ParamArgList(ParamBase):
    """Class with an argument sometimes with multiple values."""

    def __str__(self) -> str:
        """String used for in subprocess call, adjusted for tuple."""
        return_value = f'{self.tool_arg}={str(self.value)}'
        if isinstance(self.value, list):
            str_list = ",".join(str(value) for value in self.value)
            return_value = f'{self.tool_arg}={str_list}'
        return return_value


class ParamNoDebug(ParamBase):
    """Base class for params with no meaningful debug method."""

    def get_pass_result(self):
        """Get default debug test passed result tuple."""
        return (True, (f'The parameter, "{self.param}", has no debugging '
                       'routine.'))


class ParamString(ParamNoDebug):
    """String parameter object."""

    # def __str__(self) -> str:
    #     """String used for parameter in subprocess call.

    #     This works when passing a string to subprocess.run but not when
    #     passing a list; spaces in the value mess up the output when
    #     addressed both here and there.
    #     """
    #     value = str(self.value)
    #     return_value = f'{self.tool_arg}={value}'
    #     if " " in value:
    #         return_value = f'{self.tool_arg}="{value}"'
    #     return return_value
    pass


class ParamAngle(ParamNumber):
    """Parameter for angles."""

    def debug(self) -> tuple[bool, str]:
        """Check that value can be converted to float."""
        return self.debug_float()


class ParamColor(ParamArgList):
    """Parameter for color, format differing by output type."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check that value is a string or three floats list color."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". Either a string like a hex color (without'
                   ' the "#" at the front) for SVG and PNG output or a list of'
                   'three numbers from 0 to 1 for PostScript output is '
                   'required.')
        if isinstance(self.value, list):
            objects = [ParamNumber(self.param, value) for value in self.value]
            checks = [obj.debug_float(output_obj)[0] for obj in objects]
            if (False in checks or len(checks) != 3
               or False in [0 <= obj.value <= 1 for obj in objects]):
                return_value = (False, message)
        else:
            if hex_color_pattern.match(self.value) is None:
                return_value = (False, message)
        return return_value


class ParamCoordFont(ParamString):
    """Parameter for coord font."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check for possible bug in PNG fonts."""
        # TODO: Add png file exists check if exe bug is not addressed.
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". A possible bug in mkhexgrid.exe may not '
                   'find a font by name for PNG output. One must supply a link'
                   ' to the font file instead, like '
                   r'"C:\Windows\Fonts\consola.ttf".')
        if output_obj.value == OUTPUT_PNG:
            return_value = (False, message)
        return return_value


class ParamCoordFormat(ParamBase):
    """Parameter for coord format with its own syntax."""

    def debug(self) -> tuple[bool, str]:
        """Check that value can generate a coordinate."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". This did not generate a well-formed grid '
                   'coordinate.\n    Basic numeral: "%c" or "%r"\n'
                   '    Space-padded numeral: insert number like "%2c" or '
                   '"%3r"\n'
                   '    Zero-padded numneral: like "%02c" or "%03r"\n'
                   '    Letter (AB after AA): "%C" or "%R"\n'
                   '    Letter (BB after AA): "%tC" or "%tR"\n'
                   'Other characters may go around those patterns. Column and '
                   'row may be reversed with horizontal grid grain. See '
                   f'{HELP_URL} for more information.')
        if coord_format_pattern.match(self.value) is None:
            return_value = (False, message)
        return return_value


class ParamCount(ParamBase):
    """Parameter for positive integers."""

    def debug(self) -> tuple[bool, str]:
        """Check that value can be converted to positive int."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". A positive integer is required.')
        try:
            value_int = int(self.value)
        except ValueError:
            return_value = (False, message)
        else:
            if self.value != value_int or value_int <= 0:
                return_value = (False, message)
        return return_value


class ParamFlag(ParamNoDebug):
    """Boolean parameter object."""

    def __str__(self) -> str:
        """String used for parameter in subprocess call."""
        return self.tool_arg


class ParamInt(ParamNumber):
    """Parameter for integers."""

    def debug(self) -> tuple[bool, str]:
        """Check that value can be converted to int."""
        return self.debug_int()


class ParamLength(ParamNumber):
    """Parameter for length, format differing by output type."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check that value can be converted to float."""
        return self.debug_float(output_obj)


class ParamMargin(ParamArgList, ParamNumber):
    """Parameter for margin with either one or four values."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check that value(s) can be converted to float."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". Either a number or a list of four numbers'
                   ' is required.')
        if isinstance(self.value, list):
            objects = [ParamNumber(self.param, value) for value in self.value]
            checks = [obj.debug_float(output_obj)[0] for obj in objects]
            if False in checks or len(checks) != 4:
                return_value = (False, message)
        else:
            return_value = self.debug_float(output_obj)
            if not return_value[0]:
                return_value = (False, message)
        return return_value


class ParamMisc(ParamNoDebug):
    """Boolean parameter object."""

    def __str__(self) -> str:
        """String used for parameter in subprocess call."""
        return self.tool_arg


class ParamOpacity(ParamNumber):
    """Parameter for opacity, format differing by output type."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check that value is the right type in the right range."""
        return_value = self.get_pass_result()
        message = (f'The parameter, "{self.param}", has a value of '
                   f'"{self.value}". ')
        check_passed = False
        if output_obj.value == OUTPUT_PNG:
            message += ('For png output, an integer in the range of 0 to 127 '
                        'is required.')
            check = self.debug_int()
            if check[0]:
                if 0 <= self.value <= 127:
                    check_passed = True
        if output_obj.value == OUTPUT_SVG:
            message += ('For svg output, a number in the range of 0 to 1 '
                        'is required.')
            check = self.debug_float()
            if check[0]:
                if 0 <= self.value <= 1:
                    check_passed = True
        else:
            message += ('For PostScript output, this parameter is ignored.')
        if not check_passed:
            return_value = (False, message)
        return return_value


class ParamSize(ParamNumber):
    """Parameter for size, format differing by output, PNG is int."""

    def debug(self, output_obj: ParamFromList) -> tuple[bool, str]:
        """Check for valid value by output."""
        if output_obj.value == OUTPUT_PNG:
            return self.debug_int(output_obj)
        else:
            return self.debug_float(output_obj)


@dataclass
class ParamInfo():
    """Info for handling parameter."""
    tool_arg: str
    param_object: type[ParamBase]
    param_list: Optional[list[str]] = None


class HexMakerParams(TypedDict, total=False):
    """Input, as from YAML, for running mkhexgrid."""
    antialias: bool
    outfile: str | Path
    output: str
    hex_width: float | str
    hex_height: float | str
    hex_side: float | str
    image_width: float | str
    image_height: float | str
    image_margin: float | str | list[float] | list[str]
    centered: bool
    rows: int
    columns: int
    grid_color: str | list[float]
    grid_opacity: int | float
    grid_thickness: float | str
    grid_grain: str
    grid_start: str
    coord_color: str | list[float]
    coord_opacity: int | float
    coord_format: str | None
    coord_font: str
    coord_size: float | str
    coord_bearing: float
    coord_distance: float | str
    coord_tilt: float
    coord_row_start: int
    coord_column_start: int
    coord_row_skip: int
    coord_column_skip: int
    coord_origin: str
    center_style: str
    center_color: str | list[float]
    center_opacity: int | float
    center_size: float | str
    background_color: str | list[float]
    background_opacity: int | float
    matte: bool
    help: bool
    version: bool


class SubprocessKwargs(TypedDict, total=False):
    """Kwargs to use with subprocess.run in the HexGridMaker."""
    capture_output: bool
    check: bool
    cwd: str
    encoding: str
    env: Mapping[str, str] | Mapping[bytes, bytes]
    input: bytes | str
    shell: bool
    stderr: str
    stdin: str | bytes
    stdout: str
    text: str
    timeout: int


class MkHexGrid():
    """Handler for running mkhexgrid.exe."""

    param_data = {'antialias': ParamInfo('--antialias', ParamFlag),
                  'outfile': ParamInfo('--outfile', ParamString),
                  'output': ParamInfo('--output', ParamFromList, OUTPUTS),
                  'hex_width': ParamInfo('--hex-width', ParamLength),
                  'hex_height': ParamInfo('--hex-height', ParamLength),
                  'hex_side': ParamInfo('--hex-side', ParamLength),
                  'image_width': ParamInfo('--image-width', ParamLength),
                  'image_height': ParamInfo('--image-height', ParamLength),
                  'image_margin': ParamInfo('--image-margin', ParamMargin),
                  'centered': ParamInfo('--centered', ParamFlag),
                  'rows': ParamInfo('--rows', ParamCount),
                  'columns': ParamInfo('--columns', ParamCount),
                  'grid_color': ParamInfo('--grid-color', ParamColor),
                  'grid_opacity': ParamInfo('--grid-opacity', ParamOpacity),
                  'grid_thickness': ParamInfo('--grid-thickness', ParamSize),
                  'grid_grain': ParamInfo('--grid-grain', ParamFromList,
                                          GRID_GRAINS),
                  'grid_start': ParamInfo('--grid-start', ParamFromList,
                                          GRID_STARTS),
                  'coord_color': ParamInfo('--coord-color', ParamColor),
                  'coord_opacity': ParamInfo('--coord-opacity', ParamOpacity),
                  'coord_format': ParamInfo('--coord-format',
                                            ParamCoordFormat),
                  'coord_font': ParamInfo('--coord-font', ParamCoordFont),
                  'coord_size': ParamInfo('--coord-size', ParamLength),
                  'coord_bearing': ParamInfo('--coord-bearing', ParamAngle),
                  'coord_distance': ParamInfo('--coord-distance', ParamLength),
                  'coord_tilt': ParamInfo('--coord-tilt', ParamAngle),
                  'coord_row_start': ParamInfo('--coord-row-start', ParamInt),
                  'coord_column_start': ParamInfo('--coord-column-start',
                                                  ParamInt),
                  'coord_row_skip': ParamInfo('--coord-row-skip', ParamInt),
                  'coord_column_skip': ParamInfo('--coord-column-skip',
                                                 ParamInt),
                  'coord_origin': ParamInfo('--coord-origin', ParamFromList,
                                            COORD_ORIGINS),
                  'center_style': ParamInfo('--center-style', ParamFromList,
                                            CENTER_STYLES),
                  'center_color': ParamInfo('--center-color', ParamColor),
                  'center_opacity': ParamInfo('--center-opacity',
                                              ParamOpacity),
                  'center_size': ParamInfo('--center-size', ParamSize),
                  'background_color': ParamInfo('--bg-color', ParamColor),
                  'background_opacity': ParamInfo('--bg-opacity',
                                                  ParamOpacity),
                  'matte': ParamInfo('--matte', ParamFlag),
                  'help': ParamInfo('--help', ParamMisc),
                  'version': ParamInfo('--version', ParamMisc)}

    def __init__(self, params: HexMakerParams, tool: str = TOOL,
                 debug: bool = False) -> None:
        """Initialize object."""
        if shutil.which(tool) is None:
            raise ProgramNotFoundError(tool, type(self).__name__)
        self.tool = tool
        self.params = [self.get_param(param, value)
                       for param, value in params.items()
                       if value not in [None, False]]
        self.tool_args = [self.tool, *[str(param) for param in self.params]]

    def __str__(self) -> str:
        """Get string from which tool can be run."""
        return " ".join(self.tool_args)

    def debug_params(self) -> list[tuple[bool, str]]:
        """Check params for tool-compliant values."""
        returns = []
        output = self.get_output_param()
        for param in self.params:
            try:
                returns.append(param.debug())
            except TypeError:
                returns.append(param.debug(output))
        return returns

    def get_output_param(self) -> type[ParamBase]:
        """Get output param."""
        return_obj = None
        for param in self.params:
            if param.param == OUTPUT:
                return_obj = param
                break
        if return_obj is None:
            return_obj = self.get_param(OUTPUT, OUTPUT_PNG)
        return return_obj

    def get_param(self, param: str, value: Any) -> type[ParamBase]:
        """Get filled param object for each parameter for tool."""
        try:
            info = self.param_data[param]
        except KeyError:
            raise UnknownParameterError(param, list(self.param_data.keys()))
        try:
            return_obj = info.param_object(param, value, info.tool_arg,
                                           info.param_list)
        except TypeError:
            return_obj = info.param_object(param, value, info.tool_arg)
        return return_obj

    def run(self, subprocess_kwargs: Optional[SubprocessKwargs] = None):
        """Make hex grid with given parameters."""
        if subprocess_kwargs is None:
            subprocess_kwargs = {}
        return subprocess.run(self.tool_args,
                              **cast(dict[str, Any], subprocess_kwargs))
        # return subprocess.run(str(self), **subprocess_kwargs)
