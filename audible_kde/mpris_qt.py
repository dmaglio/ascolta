"""MPRIS dentro Qt: il server D-Bus gira in un thread con il suo event loop.

I comandi (tasti multimediali, Plasma media controller) diventano segnali Qt,
quindi vengono eseguiti nel thread principale. Lo stato letto dal bus è una
copia (`snap`) aggiornata dal backend a ogni tick, così i due thread non si
toccano.
"""
from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import QObject, Signal

from .mpris import Mpris, metadata

SKIP = 15.0  # secondi per Avanti / Indietro, come i tasti freccia


class _Ctl:
    """Quello che il server MPRIS chiede all'app (vedi PlayerIface)."""
    SKIP = SKIP

    def __init__(self, bridge: "MprisBridge") -> None:
        self.b = bridge

    def active(self) -> bool: return self.b.snap["active"]
    def status(self) -> str: return self.b.snap["status"]
    def rate(self) -> float: return self.b.snap["rate"]
    def position(self) -> float: return self.b.snap["position"]
    def track_id(self) -> str: return self.b.snap["asin"]

    def metadata(self) -> dict:
        s = self.b.snap
        if not s["active"]:
            return {}
        return metadata(s["asin"], s["title"], s["authors"], s["album"], s["duration"])

    def skip(self, seconds: float) -> None: self.b.skipRequested.emit(seconds)
    def seek_to(self, seconds: float) -> None: self.b.seekRequested.emit(seconds)
    def toggle(self) -> None: self.b.toggleRequested.emit()

    def set_paused(self, paused: bool) -> None:
        # confronto nel thread principale, dove lo stato è affidabile
        self.b.pausedRequested.emit(paused)


class MprisBridge(QObject):
    toggleRequested = Signal()
    pausedRequested = Signal(bool)
    skipRequested = Signal(float)
    seekRequested = Signal(float)
    raiseRequested = Signal()
    quitRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.snap = {"active": False, "status": "Stopped", "rate": 1.0, "position": 0.0,
                     "asin": "", "title": "", "authors": "", "album": "", "duration": 0.0}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mpris: Mpris | None = None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="mpris").start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._mpris = Mpris(_Ctl(self), self.quitRequested.emit, self.raiseRequested.emit)
        try:
            self._loop.run_until_complete(self._mpris.start())
        except Exception as e:  # niente bus di sessione: l'app funziona senza tasti multimediali
            print(f"MPRIS non attivo: {e}")
            return
        self._loop.run_forever()

    def publish(self, snap: dict) -> None:
        """Chiamato dal thread principale: aggiorna la copia e annuncia i cambi."""
        self.snap = snap
        if self._loop and self._mpris:
            self._loop.call_soon_threadsafe(self._mpris.update)

    def stop(self) -> None:
        if self._loop and self._mpris:
            fut = asyncio.run_coroutine_threadsafe(self._mpris.stop(), self._loop)
            try:
                fut.result(timeout=1)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
