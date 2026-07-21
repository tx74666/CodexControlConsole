import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import world_console


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def main():
    values = {"WallpaperStyle": "10", "TileWallpaper": "0"}
    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=1,
        REG_SZ=1,
        OpenKey=lambda *args, **kwargs: FakeKey(),
        QueryValueEx=lambda key, name: (values[name], 1),
        SetValueEx=lambda key, name, reserved, kind, value: values.__setitem__(name, value),
    )
    with patch.dict(sys.modules, {"winreg": fake}):
        current = world_console.get_windows_wallpaper_style()
        assert current["name"] == "fill", current
        position = world_console.set_windows_wallpaper_style("fit")
        assert position == 3, position
        assert values == {"WallpaperStyle": "6", "TileWallpaper": "0"}, values
    print("PASS wallpaper display style")


if __name__ == "__main__":
    main()
