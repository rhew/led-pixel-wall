from typing import List, Tuple

PANEL_WIDTH = 10
PANEL_HEIGHT = 10


def serpentine_index(x: int, y: int, width: int = PANEL_WIDTH, height: int = PANEL_HEIGHT) -> int:
    hw_y = height - 1 - y
    if hw_y % 2 == 0:
        return hw_y * width + x
    return hw_y * width + (width - 1 - x)


def blank_frame(width: int = PANEL_WIDTH, height: int = PANEL_HEIGHT) -> List[Tuple[int, int, int]]:
    return [(0, 0, 0)] * (width * height)
