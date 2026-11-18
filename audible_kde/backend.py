"""Ponte tra Python (Audible, mpv) e l'interfaccia QML."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict

import audible
from PySide6.QtCore import (Property, QAbstractListModel, QByteArray, QModelIndex,
                            QObject, Qt, QTimer, Signal, Slot)

from .api import Audible, Book
from .config import AUTH_FILE, CONFIG_DIR, LOCALE
from .mpris_qt import MprisBridge
from .stats import ListeningSession

SYNC_EVERY = 30.0  # secondi tra due scritture della posizione su Audible


def hms(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


class LibraryModel(QAbstractListModel):
    ROLES = ["asin", "title", "authors", "narrators", "series", "seq", "minutes",
             "percent", "finished", "coverUrl", "summary", "downloaded", "busy", "progress"]

    def __init__(self) -> None:
        super().__init__()
        self._all: list[Book] = []
        self._shown: list[Book] = []
        self._filter = ""
        self._status = "all"
        self._sort = "series"
        self._desc = False
        self._group = False
        self.busy: set[str] = set()
        self.progress: dict[str, float] = {}  # 0..1 scaricando, -1 = decifro

    def roleNames(self):
        return {Qt.UserRole + i: QByteArray(n.encode()) for i, n in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._shown)

    def data(self, index, role):
        if not index.isValid():
            return None
        b = self._shown[index.row()]
        name = self.ROLES[role - Qt.UserRole]
        if name == "coverUrl":
            return b.cover_url
        if name == "downloaded":
            return b.path() is not None
        if name == "busy":
            return b.asin in self.busy
        if name == "progress":
            return self.progress.get(b.asin, 0.0)
        return getattr(b, name)

    def set_books(self, books: list[Book]) -> None:
        self._all = books
        self._apply()

    def set_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._apply()

    def set_status(self, status: str) -> None:
        self._status = status
        self._apply()

    def set_sort(self, key: str, desc: bool) -> None:
        self._sort, self._desc = key, desc
        self._apply()

    def set_group(self, group: bool) -> None:
        self._group = group
        self._apply()

    def refresh(self) -> None:
        self._apply()

    def _match(self, b: Book) -> bool:
        f = self._filter
        if f and f not in f"{b.title} {b.authors} {b.narrators} {b.series}".lower():
            return False
        st = self._status
        if st == "inprogress":
            return b.percent > 0 and not b.finished
        if st == "unstarted":
            return b.percent <= 0 and not b.finished
        if st == "finished":
            return b.finished
        if st == "downloaded":
            return b.path() is not None
        return True

    def _key(self, b: Book):
        return {"series": lambda: b.sort_key,
                "title": lambda: b.title.lower(),
                "authors": lambda: (b.authors.lower(), b.sort_key),
                "purchased": lambda: b.purchased,
                "minutes": lambda: b.minutes,
                "percent": lambda: b.percent}[self._sort]()

    def _apply(self) -> None:
        shown = sorted((b for b in self._all if self._match(b)),
                       key=self._key, reverse=self._desc)
        if self._group:  # ordinamento stabile: le serie restano insieme, "senza serie" in fondo
            shown.sort(key=lambda b: (not b.series, b.series.lower()))
        self.beginResetModel()
        self._shown = shown
        self.endResetModel()

    def find(self, asin: str) -> Book | None:
        return next((b for b in self._all if b.asin == asin), None)

    def touch(self, asin: str) -> None:
        for i, b in enumerate(self._shown):
            if b.asin == asin:
                ix = self.index(i)
                self.dataChanged.emit(ix, ix)


class Backend(QObject):
    stateChanged = Signal()
    messageChanged = Signal()
    nowChanged = Signal()
    groupedChanged = Signal()
    tickChanged = Signal()
    sleepChanged = Signal()
    notify = Signal(str, str)  # titolo, testo: la shell li mostra come notifica
    loginUrl = Signal(str)
    # segnali interni per rientrare nel thread principale
    _libraryReady = Signal(object, object)
    _loggedIn = Signal()
    _loginFailed = Signal(str)
    _playReady = Signal(str, float)
    _info = Signal(str)
    _touch = Signal(str)
    _marked = Signal(str, bool)

    def __init__(self) -> None:
        super().__init__()
        self.api: Audible | None = None
        self.model = LibraryModel()
        self.remote: dict[str, int] = {}
        self.player = None
        self.current: Book | None = None
        self.session: ListeningSession | None = None
        self._state = "login" if not AUTH_FILE.exists() else "loading"
        self._message = ""
        self._speed = 1.0
        self._sleep_at: float | None = None
        self._sleep_min = 0
        self._last_sync = 0.0
        self._last_synced_pos = -1.0
        self._login_event = threading.Event()
        self._login_answer = ""
        self._dl: dict[str, float] = {}

        self._libraryReady.connect(self._on_library)
        self._loggedIn.connect(self._start_session)
        self._loginFailed.connect(self._on_login_failed)
        self._playReady.connect(self._start_playback)
        self._info.connect(self._set_message)
        self._touch.connect(self.model.touch)
        self._marked.connect(self._on_marked)

        self.mpris = MprisBridge()
        self.mpris.toggleRequested.connect(self.toggle)
        self.mpris.pausedRequested.connect(self._set_paused)
        self.mpris.skipRequested.connect(self.skip)
        self.mpris.seekRequested.connect(self.seekTo)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------- proprietà
    def _get_state(self) -> str: return self._state
    state = Property(str, _get_state, notify=stateChanged)

    def _get_message(self) -> str: return self._message
    message = Property(str, _get_message, notify=messageChanged)

    @Property(QObject, constant=True)
    def library(self): return self.model

    @Property(str, notify=nowChanged)
    def nowAsin(self): return self.current.asin if self.current else ""

    @Property(str, notify=nowChanged)
    def nowTitle(self): return self.current.title if self.current else ""

    @Property(str, notify=nowChanged)
    def nowAuthors(self): return self.current.authors if self.current else ""

    @Property(str, notify=nowChanged)
    def nowCover(self): return self.current.cover_url if self.current else ""

    @Property(float, notify=tickChanged)
    def position(self): return self.player.position if self._loaded() else 0.0

    @Property(float, notify=tickChanged)
    def duration(self): return self.player.duration if self._loaded() else 0.0

    @Property(bool, notify=tickChanged)
    def playing(self): return self._loaded() and not self.player.paused

    @Property(float, notify=tickChanged)
    def speed(self): return self._speed

    @Property(str, notify=tickChanged)
    def positionText(self): return hms(self.position)

    @Property(str, notify=tickChanged)
    def durationText(self): return hms(self.duration)

    @Property(str, notify=tickChanged)
    def chapterTitle(self):
        if not self._loaded():
            return ""
        ch = self.player.chapters
        return ch[self.player.chapter_index()][1] if ch else ""

    @Property(int, notify=sleepChanged)
    def sleepLeft(self):
        """Minuti rimasti allo sleep timer (0 = spento)."""
        if not self._sleep_at:
            return 0
        return max(int((self._sleep_at - time.monotonic()) // 60) + 1, 0)

    def _loaded(self) -> bool:
        return bool(self.player and self.player.loaded and self.current)

    # --------------------------------------------------------------- avvio
    @Slot()
    def start(self) -> None:
        self.mpris.start()
        if AUTH_FILE.exists():
            self._start_session()

    def _set_state(self, s: str) -> None:
        if s != self._state:
            self._state = s
            self.stateChanged.emit()

    def _set_message(self, m: str) -> None:
        self._message = m
        self.messageChanged.emit()

    def _bg(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # --------------------------------------------------------------- login
    @Slot()
    def beginLogin(self) -> None:
        """Avvia il login esterno: emette loginUrl, poi attende submitLogin()."""
        self._login_event.clear()
        self._bg(self._login_thread)

    def _login_thread(self) -> None:
        def ask(url: str) -> str:
            self.loginUrl.emit(url)
            self._login_event.wait()
            return self._login_answer

        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            auth = audible.Authenticator.from_login_external(
                locale=LOCALE, with_username=False, login_url_callback=ask)
            auth.to_file(AUTH_FILE)
            AUTH_FILE.chmod(0o600)
        except Exception as e:
            self._loginFailed.emit(str(e))
            return
        self._loggedIn.emit()

    @Slot(str)
    def submitLogin(self, url: str) -> None:
        self._login_answer = url.strip()
        self._login_event.set()

    @Slot()
    def cancelLogin(self) -> None:
        self._login_answer = ""
        self._login_event.set()

    def _on_login_failed(self, msg: str) -> None:
        self._set_message(f"Accesso non riuscito: {msg}")

    # ------------------------------------------------------------- libreria
    def _start_session(self) -> None:
        try:
            self.api = Audible()
        except Exception as e:
            self._set_message(f"Credenziali non valide: {e}")
            self._set_state("login")
            return
        self.model.set_books(sorted(self.api.cached_library(), key=lambda b: b.sort_key))
        self._set_state("ready")
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        if self.api:
            self._set_message("Aggiorno la libreria…")
            self._bg(self._fetch_library)

    def _fetch_library(self) -> None:
        try:
            books = sorted(self.api.library(), key=lambda b: b.sort_key)
        except Exception as e:  # rete assente: resta la cache
            self._info.emit(f"Libreria non aggiornata: {e}")
            return
        try:
            remote = self.api.remote_positions([b.asin for b in books])
        except Exception:
            remote = self.remote
        self._libraryReady.emit(books, remote)

    def _on_library(self, books: list[Book], remote: dict[str, int]) -> None:
        self.remote = remote
        self.model.set_books(books)
        self._set_message(f"{len(books)} audiolibri")

    @Slot(str)
    def setFilter(self, text: str) -> None:
        self.model.set_filter(text)

    @Slot(str)
    def setStatusFilter(self, status: str) -> None:
        self.model.set_status(status)

    @Slot(str, bool)
    def setSort(self, key: str, descending: bool) -> None:
        self.model.set_sort(key, descending)

    @Slot(bool)
    def setGrouped(self, grouped: bool) -> None:
        if grouped != self.model._group:
            self.model.set_group(grouped)
            self.groupedChanged.emit()

    @Property(bool, notify=groupedChanged)
    def grouped(self): return self.model._group

    @Slot(str, bool)
    def markFinished(self, asin: str, finished: bool) -> None:
        b = self.model.find(asin)
        if not (b and self.api):
            return

        def run() -> None:
            try:
                self.api.mark_finished(asin, finished)
            except Exception as e:
                self._info.emit(f"Impossibile aggiornare lo stato: {e}")
                return
            self._marked.emit(asin, finished)

        self._bg(run)

    def _on_marked(self, asin: str, finished: bool) -> None:
        b = self.model.find(asin)
        if not b:
            return
        b.finished = finished
        if finished:
            b.percent = 100.0
        elif b.percent >= 100:
            b.percent = 0.0
        try:
            self.api.save_library(self.model._all)
        except OSError:
            pass
        if self.model._status != "all":
            self.model.refresh()
        else:
            self.model.touch(asin)
        self._set_message(f"«{b.title}» segnato come {'finito' if finished else 'da finire'}")

    @Slot(str)
    def deleteFile(self, asin: str) -> None:
        b = self.model.find(asin)
        path = b.path() if b else None
        if not path or asin in self.model.busy:
            return
        if self.current and self.current.asin == asin:
            self._unload()
        try:
            path.unlink()
            try:
                path.parent.rmdir()  # cartella dell'autore, se rimasta vuota
            except OSError:
                pass
        except OSError as e:
            self._set_message(f"File non eliminato: {e}")
            return
        self.model.touch(asin)
        if self.model._status == "downloaded":
            self.model.refresh()
        self._set_message(f"File di «{b.title}» eliminato")

    def _unload(self) -> None:
        """Ferma la riproduzione e scrive la posizione (prima di eliminare il file)."""
        self._flush_position()
        self._stats_close()
        self.session = None
        if self.player:
            self.player.loaded = False
            try:
                self.player.mpv.stop()
            except Exception:
                pass
        self.current = None
        self.nowChanged.emit()
        self.tickChanged.emit()

    @Slot(str, result="QVariantMap")
    def book(self, asin: str) -> dict:
        """Dati completi di un libro per la pagina dei dettagli."""
        b = self.model.find(asin)
        if not b:
            return {}
        d = asdict(b)
        d["downloaded"] = b.path() is not None
        d["busy"] = asin in self.model.busy
        d["playing"] = asin == self.nowAsin and self.playing
        d["path"] = str(b.path() or "")
        return d

    # ------------------------------------------------------------- download
    def _download(self, b: Book, then_play: bool) -> None:
        if b.asin in self.model.busy:
            return
        self.model.busy.add(b.asin)
        self.model.touch(b.asin)
        last = [0.0]

        def progress(stage: str, frac: float) -> None:
            self.model.progress[b.asin] = -1.0 if stage == "decifro" else frac
            if time.monotonic() - last[0] > 0.25 or frac >= 1:
                last[0] = time.monotonic()
                self._touch.emit(b.asin)
                self._info.emit("Decifro…" if stage == "decifro"
                                else f"Scarico «{b.title}» {frac:4.0%}")

        def run() -> None:
            try:
                self.api.download(b, progress)
                self._info.emit(f"Scaricato «{b.title}»")
                self.notify.emit("Download completato", b.title)
            except Exception as e:
                self._info.emit(f"Download fallito: {e}")
                self.notify.emit(f"Download fallito: {b.title}", str(e) or type(e).__name__)
            finally:
                self.model.busy.discard(b.asin)
                self.model.progress.pop(b.asin, None)
                self._touch.emit(b.asin)
            if then_play and b.path():
                self._play_book_thread(b)

        self._bg(run)

    @Slot(str)
    def download(self, asin: str) -> None:
        b = self.model.find(asin)
        if b and self.api and not b.path():
            self._download(b, False)

    # --------------------------------------------------------- riproduzione
    @Slot(str)
    def play(self, asin: str) -> None:
        b = self.model.find(asin)
        if not (b and self.api) or b.asin in self.model.busy:
            return
        if self.current and self.current.asin == asin and self._loaded():
            return self.toggle()
        if b.path():
            self._bg(self._play_book_thread, b)
        else:
            self._download(b, True)

    def _play_book_thread(self, b: Book) -> None:
        """Legge il punto di ascolto aggiornato, poi avvia nel thread principale."""
        try:
            ms = self.api.remote_positions([b.asin]).get(b.asin, self.remote.get(b.asin, 0))
        except Exception:
            ms = self.remote.get(b.asin, 0)
        self.remote[b.asin] = ms
        self._playReady.emit(b.asin, ms / 1000)

    def _start_playback(self, asin: str, start_s: float) -> None:
        b = self.model.find(asin)
        if not b or not b.path():
            return
        self._flush_position()
        self._stats_close()
        if self.player is None:
            from .player import Player
            self.player = Player()
            self.player.set_speed(self._speed)
        self.current = b
        self.player.load(b.path(), start_s)
        self._last_sync = time.monotonic()
        self._last_synced_pos = -1.0
        self.nowChanged.emit()
        self._set_message(f"Riprendo da {hms(start_s)}" if start_s else "Parto dall'inizio")
        self._bg(self._begin_session, b)

    @Slot()
    def toggle(self) -> None:
        if self._loaded():
            self.player.toggle()
            if self.player.paused:
                self._flush_position()
            self.tickChanged.emit()

    def _set_paused(self, paused: bool) -> None:
        if self._loaded() and self.player.paused != paused:
            self.toggle()

    @Slot(float)
    def skip(self, seconds: float) -> None:
        if self._loaded():
            self.player.seek(seconds)

    @Slot(float)
    def seekTo(self, seconds: float) -> None:
        if self._loaded():
            self.player.seek_to(seconds)

    @Slot(int)
    def chapter(self, step: int) -> None:
        if self._loaded():
            self.player.chapter(step)

    @Slot(float)
    def setSpeed(self, speed: float) -> None:
        self._speed = round(min(max(speed, 0.5), 3.0), 2)
        if self.player:
            self.player.set_speed(self._speed)
        self.tickChanged.emit()

    @Slot(int)
    def setSleep(self, minutes: int) -> None:
        self._sleep_min = minutes
        self._sleep_at = time.monotonic() + minutes * 60 if minutes else None
        self.sleepChanged.emit()

    # ------------------------------------------------- tick e sincronizzazione
    def _publish_mpris(self) -> None:
        if not self._loaded():
            snap = {"active": False, "status": "Stopped", "rate": 1.0, "position": 0.0,
                    "asin": "", "title": "", "authors": "", "album": "", "duration": 0.0}
        else:
            p, b = self.player, self.current
            snap = {"active": True, "status": "Paused" if p.paused else "Playing",
                    "rate": p.speed, "position": p.position, "asin": b.asin,
                    "title": b.title, "authors": b.authors,
                    "album": b.series or b.title, "duration": p.duration}
        self.mpris.publish(snap)

    def _tick(self) -> None:
        self._publish_mpris()
        if not self._loaded():
            return
        p, b = self.player, self.current
        self.tickChanged.emit()
        if self._sleep_at:
            if time.monotonic() >= self._sleep_at:
                p.pause()
                self._sleep_at = None
                self.notify.emit("Sleep timer", f"Riproduzione fermata: {b.title}")
                self._flush_position()
            self.sleepChanged.emit()
        if time.monotonic() - self._last_sync >= SYNC_EVERY and not p.paused:
            self._flush_position()
        self._stats_tick()
        if p.ended and not b.finished:
            b.finished = True
            self._flush_position(final=True)
            self._stats_close(finished=True)
            self.notify.emit("Libro finito", b.title)
            self.model.touch(b.asin)

    def _flush_position(self, final: bool = False) -> None:
        p, b = self.player, self.current
        if not (p and b and p.loaded):
            return
        pos = p.position
        self._last_sync = time.monotonic()
        if abs(pos - self._last_synced_pos) < 1:
            return
        self._last_synced_pos = pos
        self.remote[b.asin] = int(pos * 1000)
        if p.duration:
            b.percent = pos / p.duration * 100
            self.model.touch(b.asin)
        self._bg(self._push, b.asin, int(pos * 1000))

    def _push(self, asin: str, ms: int) -> None:
        try:
            self.api.set_position(asin, ms)
        except Exception as e:
            self._info.emit(f"Sincronizzazione fallita: {e}")

    def _begin_session(self, b: Book) -> None:
        try:
            meta = self.api.meta(b.asin)
            if not meta.get("license_id"):
                _, meta = self.api.license(b.asin)
            length = meta.get("length_ms") or int((self.player.duration if self.player else 0) * 1000)
            session = ListeningSession(b.asin, meta.get("license_id", ""), length)
        except Exception as e:
            self._info.emit(f"Eventi di ascolto non attivi: {e}")
            return
        if self.current and self.current.asin == b.asin:
            self.session = session

    def _send_stats(self, events: list[dict]) -> None:
        try:
            self.api.send_stats(events)
        except Exception as e:
            self._info.emit(f"Eventi di ascolto non inviati: {e}")

    def _stats_tick(self) -> None:
        p, ss = self.player, self.session
        if not (p and ss and self.current and ss.asin == self.current.asin and p.loaded):
            return
        evs = ss.tick(p.position * 1000, not p.paused and not p.ended, p.speed)
        if evs:
            self._bg(self._send_stats, evs)

    def _stats_close(self, finished: bool = False) -> None:
        p, ss = self.player, self.session
        if not (p and ss and p.loaded):
            return
        evs = ss.end(p.position * 1000, p.speed)
        if finished:
            evs += ss.finished(p.speed)
        if evs:
            self._send_stats(evs)

    # ---------------------------------------------------------------- uscita
    @Slot()
    def shutdown(self) -> None:
        """Scrive la posizione prima di chiudere (sincrono: l'app sta uscendo)."""
        p, b = self.player, self.current
        if p and b and p.loaded and self.api:
            try:
                self._stats_close()
                self.api.set_position(b.asin, int(p.position * 1000))
            except Exception:
                pass
        if p:
            p.close()
        self.mpris.stop()
