"""Impostazioni dell'interfaccia GTK, in un piccolo file JSON accanto al token."""
from __future__ import annotations

import json

from audible_kde.config import CONFIG_DIR

FILE = CONFIG_DIR / "gtk-settings.json"
DEFAULTS = {
    # Chiudere la finestra non termina l'app: l'ascolto continua (Esci dal menu per uscire)
    "background": True,
}


class Settings:
    def __init__(self) -> None:
        self._data = dict(DEFAULTS)
        try:
            loaded = json.loads(FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def get(self, key: str):
        return self._data[key]

    def set(self, key: str, value) -> None:
        if key not in DEFAULTS or self._data[key] == value:
            return
        self._data[key] = value
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(FILE)
        except OSError:
            pass  # resta valida per questa sessione
