from pathlib import Path
import os

LOCALE = os.environ.get("AUDIBLE_KDE_LOCALE", "it")  # mercato: it, de, fr, uk, us…
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "audible-kde"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "audible-kde"
AUTH_FILE = CONFIG_DIR / "auth.json"
BOOKS_DIR = Path(os.environ.get("AUDIBLE_KDE_BOOKS", Path.home() / "Audiolibri"))

# In Flatpak l'ID dell'app è dato da FLATPAK_ID; fuori resta "audible-kde"
APP_ID = os.environ.get("FLATPAK_ID", "audible-kde")
