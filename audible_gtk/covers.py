"""Copertine: scaricate in un thread, tenute su disco e come texture in memoria."""
from __future__ import annotations

import hashlib
import threading

import httpx
from gi.repository import Gdk, GLib

from audible_kde.config import DATA_DIR

CACHE = DATA_DIR / "covers"
_textures: dict[str, Gdk.Texture] = {}
_pending: dict[str, list] = {}  # url -> immagini in attesa
_lock = threading.Lock()


def _show(widget, tex: Gdk.Texture) -> None:
    widget.set_from_paintable(tex)


def _file(url: str):
    return CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".jpg")


def _texture(url: str) -> Gdk.Texture | None:
    path = _file(url)
    if not path.exists():
        return None
    try:
        tex = Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        path.unlink(missing_ok=True)  # file rovinato: si riscarica alla prossima volta
        return None
    _textures[url] = tex
    return tex


def _fetch(url: str) -> None:
    ok = False
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        r = httpx.get(url, timeout=20, follow_redirects=True)
        r.raise_for_status()
        tmp = _file(url).with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(_file(url))
        ok = True
    except Exception:
        pass
    GLib.idle_add(_done, url, ok)


def _done(url: str, ok: bool) -> bool:
    with _lock:
        waiting = _pending.pop(url, [])
    tex = _texture(url) if ok else None
    if tex:
        for picture in waiting:
            _show(picture, tex)
    return False


def load(url: str, picture) -> None:
    """Mette la copertina nella Gtk.Image, appena disponibile."""
    if not url:
        return
    tex = _textures.get(url) or _texture(url)
    if tex:
        _show(picture, tex)
        return
    with _lock:
        first = url not in _pending
        _pending.setdefault(url, []).append(picture)
    if first:
        threading.Thread(target=_fetch, args=(url,), daemon=True).start()
