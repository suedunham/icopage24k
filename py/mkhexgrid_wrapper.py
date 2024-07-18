from collections.abc import Sequence
from enum import StrEnum
import subprocess
from pathlib import Path
import re
import shutil
from typing import Any, ClassVar, Literal, Mapping, Optional, Pattern, Self
from typing_extensions import Annotated

from pydantic import (BaseModel, Field, field_validator, PlainSerializer,
                      RootModel)
from pydantic.functional_validators import AfterValidator, BeforeValidator


COORD_FORMAT_TOKENS = 'cr'
TOOL = 'mkhexgrid'
UNIT_PIXELS = 'px'

MEASURE = 'measure'
UNIT = 'unit'


class BaseError(Exception):
    """Base exception class."""

    def __init__(self, argument: str = "") -> None:
        self.argument = argument
        self.message = "Base exception message has not been overwritten."
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class IncompatableModelError(BaseError):
    """Wrapper initalized with model unlike HexMakerModel."""

    def __init__(self, argument: str, class_name: str) -> None:
        super().__init__(argument)
        self.message = (f'The model, {argument}, could not be used to '
                        f'initialize {class_name}.')


class ProgramNotFoundError(BaseError):
    """Tool used with subprocess was not found."""

    def __init__(self, argument: str, class_name: str) -> None:
        super().__init__(argument)
        self.message = (f'The program, {argument}, could not be found on the '
                        'system or user PATH.\nEither add it to one of those '
                        'environment variables or include the full path to it '
                        'when initializing the wrapper\nobject like the '
                        f'following:\n\nobj = {class_name}(settings, '
                        f'tool="C:\\path\\to\\{argument}.exe")')


class ToolNameOrPathIsNoneError(BaseError):
    """A value of None was supplied to a tool name or path parameter."""

    def __init__(self, argument: str) -> None:
        super().__init__(argument)
        self.message = (f'The class, {argument}, has been given a value of '
                        'None in place of the name or path to mkhexgrid.exe.'
                        '\n\nTo use the wrapper default and suppress this '
                        'message, call the tool-check routine in that class '
                        'with use_wrapper_default_on_err = True')


class MhgOutput(StrEnum):
    """Allowed mkHexGrid output formats."""
    PNG = 'png'     # * Tool default
    PS = 'ps'
    SVG = 'svg'


class MhgPsUnit(StrEnum):
    """Allowed units used in mkhexgrid PostScript values."""
    INCH = 'in'
    MILLIMETER = 'mm'
    POINT = 'pt'


class MhgGridStart(StrEnum):
    """Allowed values for mkhexgrid grid_start parameter.

    What this means changes with the grid_grain and coord_origin params.
    For the default vertical grid with its origin in the upper left, OUT
    means that the first column is higher than the next. With IN, it is
    lower. Other combinations may have unintuitive results.
    """
    IN = 'i'
    OUT = 'o'   # * Tool default


class MhgGridGrain(StrEnum):
    """Allowed values for mkhexgrid grid_grain parameter."""
    HORIZONTAL = 'h'    # Hexes are points up
    VERTICAL = 'v'      # * Hexes are sides up


class MhgCoordOrigin(StrEnum):
    """Allowed values for mkhexgrid coord_origin parameter."""
    UPPER_LEFT = 'ul'   # * Tool default
    UPPER_RIGHT = 'ur'
    LOWER_LEFT = 'll'
    LOWER_RIGHT = 'lr'


class MhgCenterStyle(StrEnum):
    """Allowed values for mkhexgrid center_style parameter."""
    NONE = 'n'  # * Tool default
    DOT = 'd'
    CROSS = 'c'


def get_coord_format_re(token_string: str) -> Pattern[str]:
    """Get re pattern for coord_format using given dimension tokens."""
    upper, lower = token_string.upper(), token_string.lower()
    pattern = (fr'^(?:.*%(?:t?[{upper}]|0?\d?[{lower}])){{2}}.*$')
    return re.compile(pattern)


def get_measure_re(units: list[str]) -> Pattern[str]:
    """Get re pattern for parsing number-unit pairs."""
    pattern = fr'^(?P<measure>-?\d+\.?\d*)(?P<unit>{'|'.join(units)})?$'
    return re.compile(pattern)


coord_format_re = get_coord_format_re(COORD_FORMAT_TOKENS)
png_svg_color_re = re.compile(r'(?i)^([0-9a-f]{6})$')
ps_units_re = get_measure_re(list(MhgPsUnit))
svg_units_re = get_measure_re([UNIT_PIXELS])


def get_field(alias: str) -> Any:
    """Get Field with standard settings."""
    return Field(default=None, serialization_alias=alias)


def get_flag(alias: str) -> Any:
    """Get Field with standard flag settings."""
    return Field(default=False, serialization_alias=alias)


def validate_png_font(value: Path) -> Path:
    """Validate font installed at given address."""
    assert shutil.which(value), ('There is no font file installed at '
                                 f'{value}. A file path is expected.')
    return value


def validate_png_svg_color(value: str) -> str:
    """Valadate six-digit hexadecimal color value."""
    assert png_svg_color_re.match(value), (f'{value} has not the form of a '
                                           '6-digit hexadecimal color value.')
    return value


Number = int | float
NonNegativeNumber = Annotated[Number, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveNumber = Annotated[Number, Field(gt=0)]
NonNegativeNumber = Annotated[Number, Field(ge=0)]
ZeroToOne = Annotated[Number, Field(ge=0, le=1)]


class MeasureModel(BaseModel):
    """Value potentially like '5mm' broken into parts."""
    measure: Number = Field(default=None)
    unit: MhgPsUnit | None

    def __str__(self) -> str:
        """Combine fields."""
        return_value = str(self.measure)
        if self.unit is not None:
            return_value += self.unit
        return return_value


def validate_ps_measure(value: Number | str) -> MeasureModel:
    """Validate value that could have string unit at end."""
    if isinstance(value, str):
        found = ps_units_re.match(value)
        assert found, (f'{value} has not the form of a number followed by '
                       'an allowed unit.')
        return_value = MeasureModel(**found.groupdict())  # type: ignore
    else:
        return_value = MeasureModel(**{MEASURE: value, UNIT: None})
    return return_value


def validate_svg_measure(value: Number | str) -> Number | str:
    """Validate value that could have string unit at end."""
    if isinstance(value, str):
        found = svg_units_re.match(value)
        assert found, (f'{value} has not the form of a number followed by '
                       'an allowed unit.')
        return_value = found.groupdict()[MEASURE]
    else:
        return_value = value
    return return_value


def measure_is_non_negative(model: MeasureModel) -> MeasureModel:
    """Validate non-negative value that could have string unit at end."""
    assert model.measure >= 0, (f'{str(model)} must have a non-negative '
                                'number.')
    return model


def measure_is_positive(model: MeasureModel) -> MeasureModel:
    """Validate positive value that could have string unit at end."""
    assert model.measure > 0, (f'{str(model)} must have a positive number.')
    return model


def serialize_measure(model: MeasureModel | list[MeasureModel]) -> str:
    """Get str from model or list of models."""
    return_value = str(model)
    if is_list_or_tuple(model):
        return_value = ",".join(str(item) for item in model)
    return return_value


# def validate_coord_format(value: str | None,
#                           info: ValidationInfo) -> str | None:
#     """Validate the standard coord_format setting."""
#     if value is None:
#         return value
#     is_valid = coord_format_re.match(value) or value == ""
#     assert is_valid, (f'{value} is not a valid coord_format, empty string, '
#                       'or None/Null.')
#     return value


# CoordFormat = Annotated[str | None, AfterValidator(validate_coord_format)]

PngCoordSize = Annotated[Number, Field(ge=1.2)]
PngFont = Annotated[Path, AfterValidator(validate_png_font)]
PngMargin = NonNegativeNumber | list[NonNegativeNumber]
PngOpacity = Annotated[int, Field(ge=0, le=127)]
PngSvgColor = Annotated[str, AfterValidator(validate_png_svg_color)]

PsColor = tuple[ZeroToOne, ZeroToOne, ZeroToOne]
PsMeasure = Annotated[MeasureModel, BeforeValidator(validate_ps_measure),
                      PlainSerializer(serialize_measure)]
PsNonNegativeMeasure = Annotated[MeasureModel,
                                 BeforeValidator(validate_ps_measure),
                                 AfterValidator(measure_is_non_negative),
                                 PlainSerializer(serialize_measure)]
PsPositiveMeasure = Annotated[MeasureModel,
                              BeforeValidator(validate_ps_measure),
                              AfterValidator(measure_is_positive),
                              PlainSerializer(serialize_measure)]
PsMargin = PsNonNegativeMeasure | list[PsNonNegativeMeasure]

SvgMeasure = Annotated[Number, BeforeValidator(validate_svg_measure)]
SvgNonNegativeMeasure = Annotated[SvgMeasure, Field(ge=0)]
SvgPositiveMeasure = Annotated[SvgMeasure, Field(gt=0)]
SvgMargin = SvgNonNegativeMeasure | list[SvgNonNegativeMeasure]


class HexMakerCommonModel(BaseModel):
    """Model of mkhexgrid.exe params shared by all output variants."""
    coord_format_re: ClassVar[Pattern] = coord_format_re
    antialias: bool = get_flag('--antialias')
    out_file: Path = get_field('--outfile')
    centered: bool = get_flag('--centered')
    rows: PositiveInt = get_field('--rows')
    columns: PositiveInt = get_field('--columns')
    grid_grain: MhgGridGrain = get_field('--grid-grain')
    grid_start: MhgGridStart = get_field('--grid-start')
    # coord_format: CoordFormat = get_field('--coord-format')
    coord_format: str = get_field('--coord-format')
    coord_bearing: Number = get_field('--coord-bearing')
    coord_tilt: Number = get_field('--coord-tilt')
    coord_row_start: PositiveInt = get_field('--coord-row-start')
    coord_column_start: PositiveInt = get_field('--coord-column-start')
    coord_row_skip: PositiveInt = get_field('--coord-row-skip')
    coord_column_skip: PositiveInt = get_field('--coord-column-skip')
    coord_origin: MhgCoordOrigin = get_field('--coord-origin')
    center_style: MhgCenterStyle = get_field('--center-style')
    matte: bool = get_flag('--matte')

    def items(self):
        """Needed to make pyright happy in get_tool_args()."""
        return self.items()

    @field_validator('coord_format')
    @classmethod
    def validate_coord_format(cls, value: str | None) -> str | None:
        """Validate the standard coord_format setting."""
        if value is None:
            return value
        is_valid = cls.coord_format_re.match(value) or value == ""
        assert is_valid, (f'{value} is not a valid coord_format, empty string,'
                          ' or None/Null.')
        return value


class PngMakerModel(HexMakerCommonModel):
    """Model for png output of mkhexgrid.exe parameters."""
    output: Literal[MhgOutput.PNG] = get_field('--output')
    hex_width: PositiveNumber = get_field('--hex-width')
    hex_height: PositiveNumber = get_field('--hex-height')
    hex_side: PositiveNumber = get_field('--hex-side')
    image_width: PositiveNumber = get_field('--image-width')
    image_height: PositiveNumber = get_field('--image-height')
    image_margin: PngMargin = get_field('--image-margin')
    grid_color: PngSvgColor = get_field('--grid-color')
    grid_opacity: PngOpacity = get_field('--grid-opacity')
    grid_thickness: PositiveInt = get_field('--grid-thickness')
    coord_color: PngSvgColor = get_field('--coord-color')
    coord_opacity: PngOpacity = get_field('--coord-opacity')
    coord_font: PngFont = get_field('--coord-font')
    coord_size: PngCoordSize = get_field('--coord-size')
    coord_distance: Number = get_field('--coord-distance')
    center_color: PngSvgColor = get_field('--center-color')
    center_opacity: PngOpacity = get_field('--center-opacity')
    center_size: NonNegativeNumber = get_field('--center-size')
    background_color: PngSvgColor = get_field('--bg-color')
    background_opacity: PngOpacity = get_field('--bg-opacity')


class PsMakerModel(HexMakerCommonModel):
    """Model for PostScript output of mkhexgrid.exe parameters.

    Fonts in these files are problematic; they do not use system fonts
    simply by naming them. Any string passes validation and a file can
    be produced, but that file may not open correctly. Addressing this
    matter is not a high priority at this time.

    Opacity values are ignored by mkhexgrid.exe in these files.
    """
    output: Literal[MhgOutput.PS] = get_field('--output')
    hex_width: PsPositiveMeasure = get_field('--hex-width')
    hex_height: PsPositiveMeasure = get_field('--hex-height')
    hex_side: PsPositiveMeasure = get_field('--hex-side')
    image_width: PsPositiveMeasure = get_field('--image-width')
    image_height: PsPositiveMeasure = get_field('--image-height')
    image_margin: PsMargin = get_field('--image-margin')
    grid_color: PsColor = get_field('--grid-color')
    grid_thickness: PsPositiveMeasure = get_field('--grid-thickness')
    coord_color: PsColor = get_field('--coord-color')
    coord_font: str = get_field('--coord-font')
    coord_size: PsPositiveMeasure = get_field('--coord-size')
    coord_distance: PsMeasure = get_field('--coord-distance')
    center_color: PsColor = get_field('--center-color')
    center_size: PsNonNegativeMeasure = get_field('--center-size')
    background_color: PsColor = get_field('--bg-color')


class SvgMakerModel(HexMakerCommonModel):
    """Model for svg output of mkhexgrid.exe parameters."""
    output: Literal[MhgOutput.SVG] = get_field('--output')
    hex_width: SvgPositiveMeasure = get_field('--hex-width')
    hex_height: SvgPositiveMeasure = get_field('--hex-height')
    hex_side: SvgPositiveMeasure = get_field('--hex-side')
    image_width: SvgPositiveMeasure = get_field('--image-width')
    image_height: SvgPositiveMeasure = get_field('--image-height')
    image_margin: SvgMargin = get_field('--image-margin')
    grid_color: PngSvgColor = get_field('--grid-color')
    grid_opacity: ZeroToOne = get_field('--grid-opacity')
    grid_thickness: SvgMeasure = get_field('--grid-thickness')
    coord_color: PngSvgColor = get_field('--coord-color')
    coord_opacity: ZeroToOne = get_field('--coord-opacity')
    coord_font: str = get_field('--coord-font')
    coord_size: SvgPositiveMeasure = get_field('--coord-size')
    coord_distance: SvgMeasure = get_field('--coord-distance')
    center_color: PngSvgColor = get_field('--center-color')
    center_opacity: ZeroToOne = get_field('--center-opacity')
    center_size: SvgNonNegativeMeasure = get_field('--center-size')
    background_color: PngSvgColor = get_field('--bg-color')
    background_opacity: ZeroToOne = get_field('--bg-opacity')


ModelUnion = PngMakerModel | PsMakerModel | SvgMakerModel


class HexMakerMethods(BaseModel):
    """Methods used by top-level HexMakerModel-type classes."""

    @staticmethod
    def get_one_arg(key: str, value: Any) -> str:
        """Get tool arg for subprocess.run from model_dump item."""
        return_value = f'{key}={str(value)}'
        if value is True:
            return_value = key
        elif is_list_or_tuple(value):
            return_value = f'{key}={",".join(str(item) for item in value)}'
        return return_value

    def get_tool_args(self) -> list[str]:
        """Get list of 'key=value' strings for subprocess.run()."""
        model = self.model_dump(by_alias=True, exclude_defaults=True)
        return [self.get_one_arg(key, value) for key, value in model.items()]


class HexMakerModel(RootModel, HexMakerMethods):
    """Model combining the output-determined models."""
    root: ModelUnion = Field(..., discriminator='output')


class SubprocessKwargsModel(BaseModel):
    """Kwargs to use with subprocess.run in the HexGridMaker."""
    capture_output: bool = Field(default=None)
    check: bool = Field(default=None)
    cwd: str = Field(default=None)
    encoding: str = Field(default=None)
    env: Mapping[str, str] | Mapping[bytes, bytes] = Field(default=None)
    input_: bytes | str = Field(default=None, alias='input')
    shell: bool = Field(default=None)
    stderr: str = Field(default=None)
    stdin: str | bytes = Field(default=None)
    stdout: str = Field(default=None)
    text: str = Field(default=None)
    timeout: int = Field(default=None)


class MkHexGrid():
    """Handler for running mkhexgrid.exe."""

    def __init__(self, tool_args: list[str], tool: str = TOOL,
                 subprocess_kwargs: Optional[dict[str, Any]] = None,
                 do_tool_check: bool = True) -> None:
        """Initialize object with raw list of tool_args.

        This list should be fully-formed CLI strings to be fed directly
        to subprocess.run(). They should be the format
            mkhexgrid arg=value, such as '--outfile=text.svg'

        One of the class methods is likely handier, but they end up here
        in the end.

        The subprocess_kwargs dict is validated with the model here.
        Note that the usual "input" param should be aliased "input_", if
        used.
        """
        if do_tool_check:
            check_tool(tool, type(self).__name__)
        self.tool_args = tool_args
        self.tool = tool
        self.subprocess_kwargs = self.get_subprocess_kwargs(subprocess_kwargs)

    @classmethod
    def from_dict(cls, tool_kwargs: dict[str, Any], tool: str = TOOL,
                  subprocess_kwargs: Optional[dict[str, Any]] = None
                  ) -> Self:
        """Initialize object from a dict of tool kwargs.

        This dict should have Python-named keys from the pydantic models
        here, which are used to validate the input.
        """
        tool_args = HexMakerModel(**tool_kwargs).get_tool_args()
        return cls(tool_args, tool, subprocess_kwargs)

    @classmethod
    def from_model(cls, tool_model: HexMakerModel, tool: str = TOOL,
                   subprocess_kwargs: Optional[dict[str, Any]] = None
                   ) -> Self:
        """Initialize object from a pydantic model.

        This is useful if another validation step is not desired. The
        model, HexMakerModel, from above is intended, though another
        can work if it resembles that model in its fields and methods.
        """
        try:
            tool_args = tool_model.get_tool_args()
        except AttributeError:
            raise IncompatableModelError(type(tool_model).__name__,
                                         cls.__name__)
        return cls(tool_args, tool, subprocess_kwargs)

    @staticmethod
    def get_subprocess_kwargs(subprocess_kwargs:
                              Optional[dict[str, Any]] = None
                              ) -> dict[str, Any]:
        if subprocess_kwargs is None:
            subprocess_kwargs = {}
        else:
            subprocess_kwargs = (SubprocessKwargsModel(**subprocess_kwargs)
                                 .model_dump(by_alias=True,
                                             exclude_defaults=True))
        return subprocess_kwargs

    def run(self) -> subprocess.CompletedProcess[str | bytes]:
        """Make hex grid with given parameters."""
        tool_args = [self.tool] + self.tool_args
        return subprocess.run(tool_args, **self.subprocess_kwargs)

    def run_help(self) -> subprocess.CompletedProcess[str | bytes]:
        """Run mkhexgrid.exe --help."""
        return subprocess.run([self.tool, '--help'], **self.subprocess_kwargs)

    def run_version(self) -> subprocess.CompletedProcess[str | bytes]:
        """Run mkhexgrid.exe --version."""
        return subprocess.run([self.tool, '--version'],
                              **self.subprocess_kwargs)


def check_tool(tool: str | Path, checking_class_name: str,
               use_wrapper_default_on_err: bool = False) -> str | Path:
    """Check that the mkhexgrid tool is usable on the system."""
    return_value = None
    try:
        check = shutil.which(tool)
    except TypeError:
        if use_wrapper_default_on_err:
            return_value = TOOL
        else:
            raise ToolNameOrPathIsNoneError(checking_class_name)
    else:
        return_value = tool
        if check is None:
            raise ProgramNotFoundError(str(tool), checking_class_name)
    return return_value


def is_list_or_tuple(variable: Any) -> bool:
    """Check if variable is a list or tuple but not a string."""
    return isinstance(variable, Sequence) and not isinstance(variable, str)
