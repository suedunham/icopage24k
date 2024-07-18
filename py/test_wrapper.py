from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import mkhexgrid_wrapper as mw


class HexMakerModel(mw.SvgMakerModel):
    """Model combining the output-determined models."""

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


def is_list_or_tuple(variable: Any) -> bool:
    """Check if variable is a list or tuple but not a string."""
    return isinstance(variable, Sequence) and not isinstance(variable, str)


def test():
    """Run the wrapper and see what happers."""
    settings = {'out_file': Path('test.svg'),
                'output': 'svg',
                # 'coord_font': r'C:\Windows\Fonts\arial.ttf',
                # 'coord_font': 'Bloovnertz',
                'hex_width': '25',
                'image_width': 300,
                'image_height': 200.5,
                # 'image_margin': ['5.5', 10, 15, 20],
                # 'grid_thickness': '1',
                # 'coord_size': 4,
                # 'center_style': 'c',
                # 'center_size': '0',
                # 'rows': 10,
                # 'columns': 10,
                'coord_format': r'%r,%c',
                'coord_row_start': '3',
                # 'coord_row_skip': 0,
                'grid_start': 'i',
                'coord_origin': 'll',
                'grid_grain': 'h',
                'coord_distance': 5,
                'coord_size': 1,
                'coord_bearing': 630.5}
    wrapper = mw.MkHexGrid.from_dict(settings)
    # wrapper = mw.MkHexGrid.from_model(HexMakerModel(**settings))
    wrapper.run()
    return settings


settings = test()
