"""Settings file in the style of MATLAB ``kv3_inimanage`` (kazan3.ini).

Sections such as ``[KazanViewer]`` and one ``[PLUGINNAME]`` section per plugin
(``favorite = 1``). Stored separately from the MATLAB file so the two versions do
not overwrite each other's settings.
"""
from __future__ import annotations

import configparser
from pathlib import Path

DEFAULT_INI = Path.home() / '.kazanpy' / 'kazan3.ini'


class KazanIni:
    def __init__(self, path: Path = DEFAULT_INI):
        self.path = Path(path)
        self._cp = configparser.ConfigParser(interpolation=None)
        self._cp.optionxform = str  # keep key case, as MATLAB does
        if self.path.exists():
            self._cp.read(self.path, encoding='utf-8')

    def get(self, section: str, key: str, default: str = '') -> str:
        return self._cp.get(section, key, fallback=default)

    def set(self, section: str, key: str, value) -> None:
        if not self._cp.has_section(section):
            self._cp.add_section(section)
        self._cp.set(section, key, str(value))

    def get_list(self, section: str, key: str) -> list[str]:
        """MATLAB array style: ``Key(1) = a``, ``Key(2) = b``, ..."""
        out, i = [], 1
        while self._cp.has_option(section, f'{key}({i})'):
            out.append(self._cp.get(section, f'{key}({i})'))
            i += 1
        return out

    def set_list(self, section: str, key: str, values: list[str]) -> None:
        if self._cp.has_section(section):
            for k in [k for k in self._cp.options(section) if k.startswith(f'{key}(')]:
                self._cp.remove_option(section, k)
        for i, v in enumerate(values, 1):
            self.set(section, f'{key}({i})', v)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            self._cp.write(f)
