"""Logica dell'app senza Qt: libreria, riproduzione, sincronizzazione con Audible.

È la controparte GTK di audible_kde.backend: stessa logica, ma i segnali sono
GObject e il rientro nel thread principale passa da GLib.idle_add. Usa gli stessi
moduli di accesso (api), riproduzione (player), MPRIS e statistiche.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict

import audible
from gi.repository import GLib, GObject

from audible_kde.api import Audible, Book
from audible_kde.config import AUTH_FILE, CONFIG_DIR, LOCALE
from audible_kde.mpris import Mpris, metadata
from audible_kde.stats import ListeningSession

SYNC_EVERY = 30.0  # secondi tra due scritture della posizione su Audible
SKIP = 15.0

EMPTY_SNAP = {"active": False, "status": "Stopped", "rate": 1.0, "position": 0.0,
              "asin": "", "title": "", "authors": "", "album": "", "duration": 0.0}


def hms(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def on_main(fn, *args) -> None:
    """Esegue fn(*args) nel thread principale (da qualunque altro thread)."""
    GLib.idle_add(lambda: (fn(*args), False)[1])


class Library:
    """Elenco dei libri con filtro, ordinamento e raggruppamento per serie."""

    def __init__(self) -> None:
        self.all: list[Book] = []
        self.shown: list[Book] = []
        self.filter = ""
        self.status = "all"
        self.sort = "series"
        self.desc = False
        self.group = False
        self.busy: set[str] = set()
        self.progress: dict[str, float] = {}  # 0..1 scaricando, -1 = decifro

    def set_books(self, books: list[Book]) -> None:
        self.all = books
        self.apply()

    def _match(self, b: Book) -> bool:
        f = self.filter
        if f and f not in f"{b.title} {b.authors} {b.narrators} {b.series}".lower():
            return False
        st = self.status
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
                "percent": lambda: b.percent}[self.sort]()

    def apply(self) -> None:
        shown = sorted((b for b in self.all if self._match(b)), key=self._key, reverse=self.desc)
        if self.group:  # ordinamento stabile: le serie restano insieme, "senza serie" in fondo
            shown.sort(key=lambda b: (not b.series, b.series.lower()))
        self.shown = shown

    def find(self, asin: str) -> Book | None:
        return next((b for b in self.all if b.asin == asin), None)


class Controller(GObject.Object):
    __gsignals__ = {
        "state": (GObject.SignalFlags.RUN_FIRST, None, ()),         # login / loading / ready
        "message": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "now": (GObject.SignalFlags.RUN_FIRST, None, ()),           # cambia il libro in ascolto
        "tick": (GObject.SignalFlags.RUN_FIRST, None, ()),          # posizione / stato play
        "sleep": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "books": (GObject.SignalFlags.RUN_FIRST, None, ()),         # la lista va ricostruita
        "book-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # una riga va aggiornata
        "notify-user": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "login-url": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "raise-window": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "quit-app": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__()
        self.api: Audible | None = None
        self.lib = Library()
        self.remote: dict[str, int] = {}
        self.player = None
        self.current: Book | None = None
        self.session: ListeningSession | None = None
        self.state = "login" if not AUTH_FILE.exists() else "loading"
        self.message = ""
        self.speed = 1.0
        self._sleep_at: float | None = None
        self._last_sync = 0.0
        self._last_synced_pos = -1.0
        self._login_event = threading.Event()
        self._login_answer = ""
        self.snap = dict(EMPTY_SNAP)
        self._mpris_loop: asyncio.AbstractEventLoop | None = None
        self._mpris: Mpris | None = None
        self._timer = GLib.timeout_add(500, self._tick)

    # ------------------------------------------------------------- stato
    @property
    def loaded(self) -> bool:
        return bool(self.player and self.player.loaded and self.current)

    @property
    def playing(self) -> bool:
        return self.loaded and not self.player.paused

    @property
    def position(self) -> float:
        return self.player.position if self.loaded else 0.0

    @property
    def duration(self) -> float:
        return self.player.duration if self.loaded else 0.0

    @property
    def chapter_title(self) -> str:
        if not self.loaded:
            return ""
        ch = self.player.chapters
        return ch[self.player.chapter_index()][1] if ch else ""

    @property
    def sleep_left(self) -> int:
        """Minuti rimasti allo sleep timer (0 = spento)."""
        if not self._sleep_at:
            return 0
        return max(int((self._sleep_at - time.monotonic()) // 60) + 1, 0)

    def _set_state(self, s: str) -> None:
        if s != self.state:
            self.state = s
            self.emit("state")

    def set_message(self, m: str) -> None:
        self.message = m
        self.emit("message")

    @staticmethod
    def _bg(fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # ------------------------------------------------------------- avvio
    def start(self) -> None:
        self._start_mpris()
        if AUTH_FILE.exists():
            self._start_session()

    # ------------------------------------------------------------- login
    def begin_login(self) -> None:
        self._login_event.clear()
        self._bg(self._login_thread)

    def _login_thread(self) -> None:
        def ask(url: str) -> str:
            on_main(self.emit, "login-url", url)
            self._login_event.wait()
            return self._login_answer

        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            auth = audible.Authenticator.from_login_external(
                locale=LOCALE, with_username=False, login_url_callback=ask)
            auth.to_file(AUTH_FILE)
            AUTH_FILE.chmod(0o600)
        except Exception as e:
            on_main(self.set_message, f"Accesso non riuscito: {e}")
            return
        on_main(self._start_session)

    def submit_login(self, url: str) -> None:
        self._login_answer = url.strip()
        self._login_event.set()

    def cancel_login(self) -> None:
        self._login_answer = ""
        self._login_event.set()

    # ------------------------------------------------------------- libreria
    def _start_session(self) -> None:
        try:
            self.api = Audible()
        except Exception as e:
            self.set_message(f"Credenziali non valide: {e}")
            self._set_state("login")
            return
        self.lib.set_books(sorted(self.api.cached_library(), key=lambda b: b.sort_key))
        self._set_state("ready")
        self.emit("books")
        self.refresh()

    def refresh(self) -> None:
        if self.api:
            self.set_message("Aggiorno la libreria…")
            self._bg(self._fetch_library)

    def _fetch_library(self) -> None:
        try:
            books = sorted(self.api.library(), key=lambda b: b.sort_key)
        except Exception as e:  # rete assente: resta la cache
            on_main(self.set_message, f"Libreria non aggiornata: {e}")
            return
        try:
            remote = self.api.remote_positions([b.asin for b in books])
        except Exception:
            remote = self.remote
        on_main(self._on_library, books, remote)

    def _on_library(self, books: list[Book], remote: dict[str, int]) -> None:
        self.remote = remote
        self.lib.set_books(books)
        self.emit("books")
        self.set_message(f"{len(books)} audiolibri")

    def reapply(self) -> None:
        self.lib.apply()
        self.emit("books")

    def set_filter(self, text: str) -> None:
        self.lib.filter = text.strip().lower()
        self.reapply()

    def set_status_filter(self, status: str) -> None:
        self.lib.status = status
        self.reapply()

    def set_sort(self, key: str, descending: bool) -> None:
        self.lib.sort, self.lib.desc = key, descending
        self.reapply()

    def set_grouped(self, grouped: bool) -> None:
        if grouped != self.lib.group:
            self.lib.group = grouped
            self.reapply()

    def mark_finished(self, asin: str, finished: bool) -> None:
        b = self.lib.find(asin)
        if not (b and self.api):
            return

        def run() -> None:
            try:
                self.api.mark_finished(asin, finished)
            except Exception as e:
                on_main(self.set_message, f"Impossibile aggiornare lo stato: {e}")
                return
            on_main(self._on_marked, asin, finished)

        self._bg(run)

    def _on_marked(self, asin: str, finished: bool) -> None:
        b = self.lib.find(asin)
        if not b:
            return
        b.finished = finished
        if finished:
            b.percent = 100.0
        elif b.percent >= 100:
            b.percent = 0.0
        try:
            self.api.save_library(self.lib.all)
        except OSError:
            pass
        if self.lib.status != "all":
            self.reapply()
        self.emit("book-changed", asin)
        self.set_message(f"«{b.title}» segnato come {'finito' if finished else 'da finire'}")

    def delete_file(self, asin: str) -> None:
        b = self.lib.find(asin)
        path = b.path() if b else None
        if not path or asin in self.lib.busy:
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
            self.set_message(f"File non eliminato: {e}")
            return
        if self.lib.status == "downloaded":
            self.reapply()
        self.emit("book-changed", asin)
        self.set_message(f"File di «{b.title}» eliminato")

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
        self.emit("now")
        self.emit("tick")

    def book_info(self, asin: str) -> dict:
        """Dati completi di un libro per la pagina dei dettagli."""
        b = self.lib.find(asin)
        if not b:
            return {}
        d = asdict(b)
        d["downloaded"] = b.path() is not None
        d["busy"] = asin in self.lib.busy
        d["playing"] = bool(self.current and asin == self.current.asin and self.playing)
        d["path"] = str(b.path() or "")
        return d

    # ------------------------------------------------------------- download
    def _download(self, b: Book, then_play: bool) -> None:
        if b.asin in self.lib.busy:
            return
        self.lib.busy.add(b.asin)
        self.emit("book-changed", b.asin)
        last = [0.0]

        def progress(stage: str, frac: float) -> None:
            self.lib.progress[b.asin] = -1.0 if stage == "decifro" else frac
            if time.monotonic() - last[0] > 0.25 or frac >= 1:
                last[0] = time.monotonic()
                on_main(self.emit, "book-changed", b.asin)
                on_main(self.set_message, "Decifro…" if stage == "decifro"
                        else f"Scarico «{b.title}» {frac:4.0%}")

        def run() -> None:
            try:
                self.api.download(b, progress)
                on_main(self.set_message, f"Scaricato «{b.title}»")
                on_main(self.emit, "notify-user", "Download completato", b.title)
            except Exception as e:
                on_main(self.set_message, f"Download fallito: {e}")
                on_main(self.emit, "notify-user", f"Download fallito: {b.title}",
                        str(e) or type(e).__name__)
            finally:
                self.lib.busy.discard(b.asin)
                self.lib.progress.pop(b.asin, None)
                on_main(self.emit, "book-changed", b.asin)
            if then_play and b.path():
                self._play_book_thread(b)

        self._bg(run)

    def download(self, asin: str) -> None:
        b = self.lib.find(asin)
        if b and self.api and not b.path():
            self._download(b, False)

    # ------------------------------------------------------------- riproduzione
    def play(self, asin: str) -> None:
        b = self.lib.find(asin)
        if not (b and self.api) or b.asin in self.lib.busy:
            return
        if self.current and self.current.asin == asin and self.loaded:
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
        on_main(self._start_playback, b.asin, ms / 1000)

    def _start_playback(self, asin: str, start_s: float) -> None:
        b = self.lib.find(asin)
        if not b or not b.path():
            return
        self._flush_position()
        self._stats_close()
        previous = self.current.asin if self.current else None
        if self.player is None:
            from audible_kde.player import Player
            self.player = Player()
            self.player.set_speed(self.speed)
        self.current = b
        self.player.load(b.path(), start_s)
        self._last_sync = time.monotonic()
        self._last_synced_pos = -1.0
        self.emit("now")
        if previous and previous != asin:
            self.emit("book-changed", previous)
        self.emit("book-changed", asin)
        self.set_message(f"Riprendo da {hms(start_s)}" if start_s else "Parto dall'inizio")
        self._bg(self._begin_session, b)

    def toggle(self) -> None:
        if self.loaded:
            self.player.toggle()
            if self.player.paused:
                self._flush_position()
            self.emit("tick")
            self.emit("book-changed", self.current.asin)

    def _set_paused(self, paused: bool) -> None:
        if self.loaded and self.player.paused != paused:
            self.toggle()

    def skip(self, seconds: float) -> None:
        if self.loaded:
            self.player.seek(seconds)

    def seek_to(self, seconds: float) -> None:
        if self.loaded:
            self.player.seek_to(seconds)

    def chapter(self, step: int) -> None:
        if self.loaded:
            self.player.chapter(step)

    def set_speed(self, speed: float) -> None:
        self.speed = round(min(max(speed, 0.5), 3.0), 2)
        if self.player:
            self.player.set_speed(self.speed)
        self.emit("tick")

    def set_sleep(self, minutes: int) -> None:
        self._sleep_at = time.monotonic() + minutes * 60 if minutes else None
        self.emit("sleep")

    # ------------------------------------------------------------- tick
    def _snapshot(self) -> dict:
        if not self.loaded:
            return dict(EMPTY_SNAP)
        p, b = self.player, self.current
        return {"active": True, "status": "Paused" if p.paused else "Playing",
                "rate": p.speed, "position": p.position, "asin": b.asin,
                "title": b.title, "authors": b.authors,
                "album": b.series or b.title, "duration": p.duration}

    def _tick(self) -> bool:
        self.snap = self._snapshot()
        if self._mpris_loop and self._mpris:
            self._mpris_loop.call_soon_threadsafe(self._mpris.update)
        if not self.loaded:
            return True
        p, b = self.player, self.current
        self.emit("tick")
        if self._sleep_at:
            if time.monotonic() >= self._sleep_at:
                p.pause()
                self._sleep_at = None
                self.emit("notify-user", "Sleep timer", f"Riproduzione fermata: {b.title}")
                self._flush_position()
                self.emit("book-changed", b.asin)
            self.emit("sleep")
        if time.monotonic() - self._last_sync >= SYNC_EVERY and not p.paused:
            self._flush_position()
        self._stats_tick()
        if p.ended and not b.finished:
            b.finished = True
            self._flush_position(final=True)
            self._stats_close(finished=True)
            self.emit("notify-user", "Libro finito", b.title)
            self.emit("book-changed", b.asin)
        return True

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
            self.emit("book-changed", b.asin)
        self._bg(self._push, b.asin, int(pos * 1000))

    def _push(self, asin: str, ms: int) -> None:
        try:
            self.api.set_position(asin, ms)
        except Exception as e:
            on_main(self.set_message, f"Sincronizzazione fallita: {e}")

    def _begin_session(self, b: Book) -> None:
        try:
            meta = self.api.meta(b.asin)
            if not meta.get("license_id"):
                _, meta = self.api.license(b.asin)
            length = meta.get("length_ms") or int((self.player.duration if self.player else 0) * 1000)
            session = ListeningSession(b.asin, meta.get("license_id", ""), length)
        except Exception as e:
            on_main(self.set_message, f"Eventi di ascolto non attivi: {e}")
            return
        if self.current and self.current.asin == b.asin:
            self.session = session

    def _send_stats(self, events: list[dict]) -> None:
        try:
            self.api.send_stats(events)
        except Exception as e:
            on_main(self.set_message, f"Eventi di ascolto non inviati: {e}")

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

    # ------------------------------------------------------------- MPRIS
    def _start_mpris(self) -> None:
        threading.Thread(target=self._mpris_run, daemon=True, name="mpris").start()

    def _mpris_run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ctl = _MprisCtl(self)
        mpris = Mpris(ctl, lambda: on_main(self.emit, "quit-app"),
                      lambda: on_main(self.emit, "raise-window"))
        try:
            loop.run_until_complete(mpris.start())
        except Exception as e:  # niente bus di sessione: l'app funziona senza tasti multimediali
            print(f"MPRIS non attivo: {e}")
            return
        self._mpris_loop, self._mpris = loop, mpris
        loop.run_forever()

    def _stop_mpris(self) -> None:
        if self._mpris_loop and self._mpris:
            fut = asyncio.run_coroutine_threadsafe(self._mpris.stop(), self._mpris_loop)
            try:
                fut.result(timeout=1)
            except Exception:
                pass
            self._mpris_loop.call_soon_threadsafe(self._mpris_loop.stop)

    # ------------------------------------------------------------- uscita
    def shutdown(self) -> None:
        """Scrive la posizione prima di chiudere (sincrono: l'app sta uscendo)."""
        GLib.source_remove(self._timer)
        p, b = self.player, self.current
        if p and b and p.loaded and self.api:
            try:
                self._stats_close()
                self.api.set_position(b.asin, int(p.position * 1000))
            except Exception:
                pass
        if p:
            p.close()
        self._stop_mpris()


class _MprisCtl:
    """Quello che il server MPRIS chiede all'app (vedi PlayerIface)."""
    SKIP = SKIP

    def __init__(self, c: Controller) -> None:
        self.c = c

    def active(self) -> bool: return self.c.snap["active"]
    def status(self) -> str: return self.c.snap["status"]
    def rate(self) -> float: return self.c.snap["rate"]
    def position(self) -> float: return self.c.snap["position"]
    def track_id(self) -> str: return self.c.snap["asin"]

    def metadata(self) -> dict:
        s = self.c.snap
        if not s["active"]:
            return {}
        return metadata(s["asin"], s["title"], s["authors"], s["album"], s["duration"])

    def skip(self, seconds: float) -> None: on_main(self.c.skip, seconds)
    def seek_to(self, seconds: float) -> None: on_main(self.c.seek_to, seconds)
    def toggle(self) -> None: on_main(self.c.toggle)
    def set_paused(self, paused: bool) -> None: on_main(self.c._set_paused, paused)
