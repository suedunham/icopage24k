from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional, Pattern, Self
# from typing_extensions import Annotated

from pydantic import BaseModel, Field, model_validator, ValidationError
# from pydantic.functional_validators import AfterValidator, BeforeValidator
from ruamel.yaml import YAML

import mkhexgrid_wrapper as mw


# HP_TOOL = 'tool'
YAML_LOADER_SAFE = 'safe'
LIST_OF_DICTS_INDEX_KEY = 'name'    # Not used but needed by copied code
config = Path('ip24k_config.yml')
DictOrFile = str | Path | dict[Any, Any]


# Patch mkhexgrid_wrapper objects for customizations needed here.
COORD_FORMAT_TOKENS = 'crxy'
coord_format_re = mw.get_coord_format_re(COORD_FORMAT_TOKENS)


# def validate_coord_format(value: str | None) -> str | None:
#     """Validate the standard coord_format setting."""
#     if value is None:
#         return value
#     is_valid = coord_format_re.match(value) or value == ""
#     assert is_valid, (f'{value} is not a valid coord_format, empty string, '
#                       'or None/Null.')
#     return value


# CoordFormat = Annotated[str | None, AfterValidator(validate_coord_format)]


class HexMakerModel(mw.SvgMakerModel, mw.HexMakerMethods):
    """mkhexgrids.exe params customized for this script.

    Several fields are not to be set directly and should not be present
    in the settings file input. These mostly pertain to grid size
    calculations, and the needed values are inserted by the script. The
    out_file setting is likewise generated.

    Other settings are not intended to be present in the settings file,
    but they shouldn't prevent mkhexgrid.exe from generating valid
    output. These fields include: antialias, centered, matte, and
    background_color. background_opacity should be set to 0 to allow for
    multiple grids, but this is not enforced.
    """
    coord_format_re: ClassVar[Pattern] = coord_format_re
    out_file: Literal[None] = None
    hex_height: Literal[None] = None
    hex_width: Literal[None] = None
    hex_side: Literal[None] = None
    image_height: Literal[None] = None
    image_width: Literal[None] = None
    image_margin: Literal[None] = None
    rows: Literal[None] = None
    columns: Literal[None] = None


class CoordPlanModel(BaseModel):
    """Model for coordinate plans."""
    name: str
    mkhexgrid: HexMakerModel


class GridMakerGeneralModel(BaseModel):
    """Model for general GridMaker settings."""
    tool: Optional[str] = None
    do_tool_check_in_wrapper: bool = False
    use_wrapper_default_tool_on_err: bool = False
    coord_format_as_mkhexgrid: bool = False
    coords_fixed_to_grain: bool = False
    coord_plans: list[CoordPlanModel] = Field(default_factory=list)
    show_output: bool = False
    svg_namespace: Optional[str] = None


class GridMakerFixedModel(BaseModel):
    """Model for basic settings more-or-less common to each grid."""
    coord_plan: Optional[str] = None
    mkhexgrid: HexMakerModel


class GridMakerVariableModel(GridMakerFixedModel):
    """Model for settings particular to a given grid."""
    name: str
    div: int


class GridMakerSettingsModel(BaseModel):
    """Parent model collecting the others."""
    grid_maker_general: GridMakerGeneralModel
    fixed: GridMakerFixedModel
    variable: list[GridMakerVariableModel] = Field(default_factory=list)
    subprocess_kwargs: mw.SubprocessKwargsModel

    @model_validator(mode='after')
    def check_coord_plans(self) -> 'GridMakerSettingsModel':
        """Check that coord_plan values are in coord_plans list."""
        plans = [None] + [x.name for x in self.grid_maker_general.coord_plans]
        used_plans = set([self.fixed.coord_plan]
                         + [x.coord_plan for x in self.variable])
        undefineds = [item for item in used_plans if item not in plans]
        assert len(undefineds) == 0, ('An unknown value or values, '
                                      f'{str(undefineds)}, was given in a '
                                      'fixed or variable coord_plan field.')
        return self


class Base(object):
    """Base class with more informative __repr__."""

    def __repr__(self) -> str:
        """Object representation."""
        params = (f'{key}={repr(self.__dict__[key])}' for key in self.__dict__)
        return f'{repr(self.__class__)}({", ".join(params)})'


class SettingsHandler(Base):
    """Handle settings for producing pages."""

    def __init__(self,
                 settings: GridMakerSettingsModel) -> None:
        """Initialize object."""
        self.settings = settings
        # self.fixed = fixed
        # self.variable = variable
        # self.subprocess_kwargs = subprocess_kwargs
        # self.hexpage = hexpage
        # self.icopage = icopage
        # mw.check_tool(wherever_that[IS], type(self).__name__,
        #               use_wrapper_default_on_err=this_one[TOO])

    @classmethod
    def from_yaml(cls: type[Self], doc: Path,
                  typ: str = YAML_LOADER_SAFE) -> Self:
        """Fill class instance with settings from one yaml file."""
        return cls(**load_yaml(doc, typ))

    @classmethod
    def from_yamls_or_dicts(cls: type[Self],
                            dicts_or_files: list[DictOrFile],
                            typ: str = YAML_LOADER_SAFE) -> Self:
        """Fill class instance from list of yaml paths or dicts."""
        merger = DictMerger([get_dict_from_file(yaml_dict)
                             for yaml_dict in dicts_or_files])
        settings = merger.merge_all()
        return cls(GridMakerSettingsModel(**settings))


def get_dict_from_file(dict_or_file: DictOrFile,
                       typ: str = YAML_LOADER_SAFE) -> dict[Any, Any]:
    """Get list of loaded yaml files or passed-through dicts."""
    if not isinstance(dict_or_file, dict):
        dict_or_file = load_yaml(dict_or_file, typ)
    return dict_or_file


class DictMerger(Base):
    """Merge dicts, updating any nested dicts."""

    def __init__(self, top_dicts: list[dict[Any, Any]],
                 list_index_key: str = LIST_OF_DICTS_INDEX_KEY) -> None:
        """Initialize object."""
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
        is desired. Yeah, more parameters should be created for this,
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


def is_list_or_tuple(variable: Any) -> bool:
    """Check if variable is a list or tuple but not a string."""
    return isinstance(variable, Sequence) and not isinstance(variable, str)


def load_yaml(doc: str | Path, typ: str = YAML_LOADER_SAFE) -> dict[Any, Any]:
    """Load yaml doc with ruamel.yaml."""
    loader = YAML(typ=typ)
    return loader.load(Path(doc))


def append_one_to_config(dict_or_file: DictOrFile) -> list[DictOrFile]:
    """Run GridMaker with yaml or dict imput."""
    return [config, dict_or_file]


def append_list_to_config(dicts_or_files: list[DictOrFile]
                          ) -> list[DictOrFile]:
    return [config] + dicts_or_files


def run_grid_maker(settings):
    if is_list_or_tuple(settings):
        all_settings = append_list_to_config(settings)
    else:
        all_settings = append_one_to_config(settings)
    handler = SettingsHandler.from_yamls_or_dicts(all_settings)
    # print(handler)
