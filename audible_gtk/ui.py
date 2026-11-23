"""Interfaccia GTK4 / libadwaita: libreria, dettagli, accesso, barra del player."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import covers
from .core import Controller, hms

STATUS = [("all", "Tutti"), ("inprogress", "In corso"), ("unstarted", "Da iniziare"),
          ("finished", "Finiti"), ("downloaded", "Scaricati")]
SORT = [("series", "Serie"), ("title", "Titolo"), ("authors", "Autore"),
        ("purchased", "Data di acquisto"), ("minutes", "Durata"), ("percent", "Avanzamento")]
SPEEDS = [0.8, 1.0, 1.2, 1.5, 1.75, 2.0, 2.5]
SLEEPS = [("Spento", 0), ("15 minuti", 15), ("30 minuti", 30), ("45 minuti", 45), ("60 minuti", 60)]


def duration_text(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60} min"


def state_text(finished: bool, percent: float) -> str:
    if finished:
        return "Finito"
    return f"In corso, {round(percent)}%" if percent > 0 else "Da iniziare"


def picture(size: int) -> Gtk.Picture:
    p = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
    p.set_size_request(size, size)
    p.set_halign(Gtk.Align.START)
    p.set_valign(Gtk.Align.START)
    p.add_css_class("card")
    return p


def label(text: str = "", *classes: str, wrap: bool = False, xalign: float = 0.0) -> Gtk.Label:
    lb = Gtk.Label(label=text, xalign=xalign, hexpand=True)
    for c in classes:
        lb.add_css_class(c)
    if wrap:
        lb.set_wrap(True)
        lb.set_wrap_mode(2)  # WORD_CHAR
    else:
        lb.set_ellipsize(3)  # END
    return lb


def icon_button(icon: str, tip: str, cb, flat: bool = True) -> Gtk.Button:
    b = Gtk.Button(icon_name=icon, tooltip_text=tip, valign=Gtk.Align.CENTER)
    if flat:
        b.add_css_class("flat")
    b.connect("clicked", lambda *_: cb())
    return b


# --------------------------------------------------------------------- libreria
class BookRow(Gtk.ListBoxRow):
    def __init__(self, ctl: Controller, asin: str) -> None:
        super().__init__()
        self.ctl, self.asin = ctl, asin
        self._cover_url = None

        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        self.cover = picture(64)
        box.append(self.cover)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True,
                      valign=Gtk.Align.CENTER)
        self.title = label("", "heading", wrap=True)
        self.authors = label("", "dim-label")
        self.series = label("", "dim-label", "caption")
        self.info = label("", "dim-label", "caption")
        self.bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.bar.add_css_class("osd")
        for w in (self.title, self.authors, self.series, self.info, self.bar):
            col.append(w)
        box.append(col)

        self.spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)
        self.download = icon_button("folder-download-symbolic", "Scarica",
                                    lambda: ctl.download(asin))
        self.play = icon_button("media-playback-start-symbolic", "Ascolta / Pausa",
                                lambda: ctl.play(asin), flat=False)
        self.play.add_css_class("circular")
        for w in (self.spinner, self.download, self.play):
            box.append(w)
        self.set_child(box)
        self.update()

    def update(self) -> None:
        info = self.ctl.book_info(self.asin)
        if not info:
            return
        if info["cover_url"] != self._cover_url:
            self._cover_url = info["cover_url"]
            covers.load(self._cover_url, self.cover)
        self.title.set_label(info["title"])
        self.authors.set_label(info["authors"])
        series = info["series"] + (f" #{info['seq']}" if info["seq"] else "") if info["series"] else ""
        self.series.set_label(series)
        self.series.set_visible(bool(series))
        tail = " · finito" if info["finished"] else (
            f" · {round(info['percent'])}%" if info["percent"] > 0 else "")
        self.info.set_label(duration_text(info["minutes"]) + tail)

        busy = info["busy"]
        prog = self.ctl.lib.progress.get(self.asin, 0.0)
        self.bar.set_visible(busy or (info["percent"] > 0 and not info["finished"]))
        if busy:
            if prog < 0:
                self.bar.pulse()
            else:
                self.bar.set_fraction(max(min(prog, 1.0), 0.0))
        else:
            self.bar.set_fraction(info["percent"] / 100)
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)
        self.download.set_visible(not info["downloaded"] and not busy)
        self.play.set_sensitive(not busy)
        self.play.set_icon_name("media-playback-pause-symbolic" if info["playing"]
                                else "media-playback-start-symbolic")
        if info["playing"] or (self.ctl.current and self.ctl.current.asin == self.asin):
            self.add_css_class("accent")
        else:
            self.remove_css_class("accent")


class LibraryPage(Adw.NavigationPage):
    def __init__(self, ctl: Controller, open_book, menu: Gio.MenuModel) -> None:
        super().__init__(title="La mia libreria", tag="library")
        self.ctl, self.open_book = ctl, open_book
        self.rows: dict[str, BookRow] = {}

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Aggiorna (F5)")
        refresh.connect("clicked", lambda *_: ctl.refresh())
        header.pack_start(refresh)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       primary=True, tooltip_text="Menu"))
        view.add_top_bar(header)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                           margin_start=12, margin_end=12, margin_top=6, margin_bottom=6)
        self.search = Gtk.SearchEntry(placeholder_text="Cerca per titolo, autore, narratore o serie…")
        self.search.connect("search-changed", lambda e: ctl.set_filter(e.get_text()))
        controls.append(self.search)

        row = Gtk.Box(spacing=6)
        row.append(Gtk.Label(label="Mostra"))
        self.status = Gtk.DropDown.new_from_strings([t for _, t in STATUS])
        self.status.connect("notify::selected", self._on_status)
        row.append(self.status)
        row.append(Gtk.Box(hexpand=True))
        row.append(Gtk.Label(label="Ordina per"))
        self.sort = Gtk.DropDown.new_from_strings([t for _, t in SORT])
        self.sort.connect("notify::selected", self._on_sort)
        row.append(self.sort)
        self.desc = Gtk.ToggleButton(icon_name="view-sort-ascending-symbolic",
                                     tooltip_text="Crescente / decrescente")
        self.desc.connect("toggled", self._on_desc)
        row.append(self.desc)
        controls.append(row)
        self.group = Gtk.CheckButton(label="Raggruppa per serie")
        self.group.connect("toggled", lambda b: ctl.set_grouped(b.get_active()))
        controls.append(self.group)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(controls)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("navigation-sidebar")
        self.list.set_header_func(self._header)
        self.list.connect("row-activated", lambda _l, r: open_book(r.asin))
        self.empty = Adw.StatusPage(icon_name="audio-headphones-symbolic",
                                    title="Nessun audiolibro",
                                    description="Nessun audiolibro corrisponde ai filtri.")
        self.stack = Gtk.Stack()
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=900, child=self.list)
        scroller.set_child(clamp)
        self.stack.add_named(scroller, "list")
        self.stack.add_named(self.empty, "empty")
        body.append(self.stack)
        self.message = label("", "dim-label", "caption")
        self.message.set_margin_start(12)
        self.message.set_margin_end(12)
        self.message.set_margin_bottom(6)
        body.append(self.message)
        view.set_content(body)
        self.set_child(view)

        ctl.connect("books", lambda *_: self.rebuild())
        ctl.connect("book-changed", lambda _c, asin: self.refresh_row(asin))
        ctl.connect("message", lambda *_: self.message.set_label(ctl.message))
        self.rebuild()

    def _on_status(self, dd, _p) -> None:
        self.ctl.set_status_filter(STATUS[dd.get_selected()][0])

    def _apply_sort(self) -> None:
        key = SORT[self.sort.get_selected()][0]
        self.ctl.set_sort(key, self.desc.get_active())

    def _on_sort(self, dd, _p) -> None:
        key = SORT[dd.get_selected()][0]
        # acquisti e avanzamento: prima i più recenti / più avanti
        newest = key in ("purchased", "percent")
        if self.desc.get_active() != newest:
            self.desc.handler_block_by_func(self._on_desc)
            self.desc.set_active(newest)
            self.desc.handler_unblock_by_func(self._on_desc)
        self.desc.set_icon_name("view-sort-descending-symbolic" if newest
                                else "view-sort-ascending-symbolic")
        self._apply_sort()

    def _on_desc(self, btn) -> None:
        btn.set_icon_name("view-sort-descending-symbolic" if btn.get_active()
                          else "view-sort-ascending-symbolic")
        self._apply_sort()

    def _header(self, row, before) -> None:
        if not self.ctl.lib.group:
            row.set_header(None)
            return
        book = self.ctl.lib.find(row.asin)
        prev = self.ctl.lib.find(before.asin) if before else None
        series = book.series if book else ""
        if prev is None or (prev.series if prev else "") != series:
            h = Gtk.Label(label=series or "Senza serie", xalign=0, margin_start=12,
                          margin_top=12, margin_bottom=4)
            h.add_css_class("heading")
            row.set_header(h)
        else:
            row.set_header(None)

    def rebuild(self) -> None:
        self.list.remove_all()
        self.rows.clear()
        for b in self.ctl.lib.shown:
            row = BookRow(self.ctl, b.asin)
            self.rows[b.asin] = row
            self.list.append(row)
        self.stack.set_visible_child_name("list" if self.rows else "empty")

    def refresh_row(self, asin: str) -> None:
        row = self.rows.get(asin)
        if row:
            row.update()


# --------------------------------------------------------------------- dettagli
class DetailsPage(Adw.NavigationPage):
    def __init__(self, ctl: Controller, asin: str) -> None:
        info = ctl.book_info(asin)
        super().__init__(title=info.get("title", ""), tag="details")
        self.ctl, self.asin = ctl, asin
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        scroller.set_child(Adw.Clamp(maximum_size=800, child=self.body))
        view.set_content(scroller)
        self.set_child(view)
        self._ids = [ctl.connect("book-changed", self._changed), ctl.connect("now", self._now)]
        self.connect("hidden", self._cleanup)
        self.render()

    def _cleanup(self, *_) -> None:
        for i in self._ids:
            self.ctl.disconnect(i)
        self._ids = []

    def _changed(self, _c, asin: str) -> None:
        if asin == self.asin:
            self.render()

    def _now(self, *_) -> None:
        self.render()

    def render(self) -> None:
        child = self.body.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.body.remove(child)
            child = nxt
        ctl, asin = self.ctl, self.asin
        b = ctl.book_info(asin)
        if not b:
            return

        top = Gtk.Box(spacing=18)
        cover = picture(192)
        covers.load(b["cover_url"], cover)
        top.append(cover)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True,
                      valign=Gtk.Align.START)
        col.append(label(b["title"], "title-2", wrap=True))
        col.append(label(b["authors"], "dim-label", wrap=True))
        if not b["finished"] and b["percent"] > 0:
            bar = Gtk.ProgressBar(fraction=b["percent"] / 100)
            col.append(bar)

        buttons = Gtk.Box(spacing=6, margin_top=6)
        play = Gtk.Button(label="Pausa" if b["playing"] else (
            "Ascolta" if b["downloaded"] else "Scarica e ascolta"),
            sensitive=not b["busy"])
        play.add_css_class("suggested-action")
        play.connect("clicked", lambda *_: ctl.play(asin))
        buttons.append(play)
        if not b["downloaded"] and not b["busy"]:
            dl = Gtk.Button(label="Solo download")
            dl.connect("clicked", lambda *_: ctl.download(asin))
            buttons.append(dl)
        if b["busy"]:
            buttons.append(Gtk.Spinner(spinning=True))
        col.append(buttons)

        more = Gtk.Box(spacing=6)
        done = Gtk.Button(label="Segna come da finire" if b["finished"] else "Segna come finito")
        done.connect("clicked", lambda *_: ctl.mark_finished(asin, not b["finished"]))
        more.append(done)
        if b["downloaded"]:
            rm = Gtk.Button(label="Elimina file…", sensitive=not b["busy"])
            rm.add_css_class("destructive-action")
            rm.connect("clicked", lambda *_: self._confirm_delete(b["title"]))
            more.append(rm)
        col.append(more)
        top.append(col)
        self.body.append(top)

        group = Adw.PreferencesGroup()
        rows = []
        if b["narrators"]:
            rows.append(("Letto da", b["narrators"]))
        if b["series"]:
            rows.append(("Serie", b["series"] + (f" #{b['seq']}" if b["seq"] else "")))
        rows.append(("Durata", duration_text(b["minutes"])))
        if b["purchased"]:
            rows.append(("Acquistato il", b["purchased"]))
        rows.append(("Stato", state_text(b["finished"], b["percent"])))
        if b["downloaded"]:
            rows.append(("File", b["path"]))
        for t, v in rows:
            r = Adw.ActionRow(title=t, subtitle=GLib.markup_escape_text(v), subtitle_selectable=True)
            r.add_css_class("property")
            group.add(r)
        self.body.append(group)

        if b["summary"]:
            self.body.append(label("Trama", "heading"))
            self.body.append(label(b["summary"], wrap=True))

    def _confirm_delete(self, title: str) -> None:
        d = Adw.AlertDialog(
            heading="Eliminare il file?",
            body=f"Il file scaricato di «{title}» verrà rimosso dal disco. Potrai scaricarlo "
                 "di nuovo da Audible; il punto di ascolto resta salvato.")
        d.add_response("cancel", "Annulla")
        d.add_response("delete", "Elimina")
        d.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel")
        d.set_close_response("cancel")
        d.connect("response", lambda _d, r: self.ctl.delete_file(self.asin) if r == "delete" else None)
        d.present(self)


# --------------------------------------------------------------------- accesso
class LoginPage(Adw.NavigationPage):
    def __init__(self, ctl: Controller) -> None:
        super().__init__(title="Accedi ad Audible", tag="login")
        self.ctl, self.url = ctl, ""
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER,
                      halign=Gtk.Align.CENTER, margin_start=24, margin_end=24)
        icon = Gtk.Image(icon_name="audio-headphones-symbolic", pixel_size=96)
        box.append(icon)
        self.text = label("Accedi con il tuo account Audible nel browser. Funzionano anche 2FA "
                          "e captcha.", wrap=True, xalign=0.5)
        self.text.set_justify(Gtk.Justification.CENTER)
        box.append(self.text)
        self.start = Gtk.Button(label="Inizia", halign=Gtk.Align.CENTER)
        self.start.add_css_class("suggested-action")
        self.start.connect("clicked", lambda *_: ctl.begin_login())
        self.open = Gtk.Button(label="Apri la pagina di accesso", halign=Gtk.Align.CENTER,
                               visible=False)
        self.open.connect("clicked", self._open_url)
        self.entry = Gtk.Entry(placeholder_text="Incolla qui l'indirizzo finale", visible=False,
                               width_chars=40)
        self.entry.connect("activate", lambda *_: self._send())
        self.send = Gtk.Button(label="Conferma", halign=Gtk.Align.CENTER, visible=False)
        self.send.connect("clicked", lambda *_: self._send())
        self.error = label("", "error", wrap=True, xalign=0.5)
        for w in (self.start, self.open, self.entry, self.send, self.error):
            box.append(w)
        view.set_content(box)
        self.set_child(view)
        ctl.connect("login-url", self._on_url)
        ctl.connect("message", lambda *_: self.error.set_label(
            ctl.message if ctl.state == "login" else ""))

    def _on_url(self, _c, url: str) -> None:
        self.url = url
        self.text.set_label("1. Apri la pagina e accedi.\n2. Copia l'indirizzo della pagina su cui "
                            "finisci (anche se è un errore) e incollalo qui sotto.")
        for w in (self.open, self.entry, self.send):
            w.set_visible(True)
        self.start.set_visible(False)

    def _open_url(self, *_) -> None:
        if self.url:
            Gtk.UriLauncher(uri=self.url).launch(self.get_root(), None, None, None)

    def _send(self) -> None:
        if self.entry.get_text().strip():
            self.ctl.submit_login(self.entry.get_text())


# --------------------------------------------------------------------- player
class PlayerBar(Gtk.Revealer):
    def __init__(self, ctl: Controller) -> None:
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        self.ctl = ctl
        self._dragging = False

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8,
                        margin_bottom=8, margin_start=12, margin_end=12)
        outer.add_css_class("toolbar")

        row = Gtk.Box(spacing=12)
        self.cover = picture(48)
        row.append(self.cover)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.title = label("", "heading")
        self.authors = label("", "dim-label", "caption")
        self.chapter = label("", "dim-label", "caption")
        for w in (self.title, self.authors, self.chapter):
            text.append(w)
        row.append(text)
        row.append(icon_button("media-skip-backward-symbolic", "Capitolo precedente",
                               lambda: ctl.chapter(-1)))
        row.append(icon_button("media-seek-backward-symbolic", "Indietro di 15 s",
                               lambda: ctl.skip(-15)))
        self.play = icon_button("media-playback-start-symbolic", "Play / Pausa",
                                ctl.toggle, flat=False)
        self.play.add_css_class("circular")
        row.append(self.play)
        row.append(icon_button("media-seek-forward-symbolic", "Avanti di 15 s",
                               lambda: ctl.skip(15)))
        row.append(icon_button("media-skip-forward-symbolic", "Capitolo successivo",
                               lambda: ctl.chapter(1)))

        self.speed = Gtk.MenuButton(label="1×", tooltip_text="Velocità", valign=Gtk.Align.CENTER)
        self.speed.add_css_class("flat")
        self.speed.set_popover(self._menu([(f"{s}×", s) for s in SPEEDS], ctl.set_speed))
        row.append(self.speed)
        self.sleep = Gtk.MenuButton(tooltip_text="Sleep timer", valign=Gtk.Align.CENTER)
        self.sleep_content = Adw.ButtonContent(icon_name="alarm-symbolic", label="")
        self.sleep.set_child(self.sleep_content)
        self.sleep.add_css_class("flat")
        self.sleep.set_popover(self._menu(SLEEPS, ctl.set_sleep))
        row.append(self.sleep)
        outer.append(row)

        seek = Gtk.Box(spacing=8)
        self.pos = Gtk.Label(label="0:00:00")
        self.pos.add_css_class("numeric")
        self.dur = Gtk.Label(label="0:00:00")
        self.dur.add_css_class("numeric")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.connect("change-value", self._seek)
        press = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        press.connect("pressed", lambda *_: setattr(self, "_dragging", True))
        press.connect("released", lambda *_: setattr(self, "_dragging", False))
        self.scale.add_controller(press)
        seek.append(self.pos)
        seek.append(self.scale)
        seek.append(self.dur)
        outer.append(seek)
        self.set_child(outer)

        ctl.connect("now", lambda *_: self.on_now())
        ctl.connect("tick", lambda *_: self.on_tick())
        ctl.connect("sleep", lambda *_: self.on_sleep())
        self.on_now()

    def _menu(self, items, cb) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for text, value in items:
            b = Gtk.Button(label=text)
            b.add_css_class("flat")

            def clicked(_b, v=value):
                cb(v)
                pop.popdown()

            b.connect("clicked", clicked)
            box.append(b)
        pop.set_child(box)
        return pop

    def _seek(self, _scale, _scroll, value: float) -> bool:
        self.ctl.seek_to(value)
        return False

    def on_now(self) -> None:
        b = self.ctl.current
        self.set_reveal_child(bool(b))
        if b:
            self.title.set_label(b.title)
            self.authors.set_label(b.authors)
            covers.load(b.cover_url, self.cover)
        self.on_tick()

    def on_tick(self) -> None:
        c = self.ctl
        self.play.set_icon_name("media-playback-pause-symbolic" if c.playing
                                else "media-playback-start-symbolic")
        text = c.chapter_title
        self.chapter.set_label(text)
        self.chapter.set_visible(bool(text))
        self.speed.set_label(f"{c.speed:g}×")
        self.pos.set_label(hms(c.position))
        self.dur.set_label(hms(c.duration))
        self.scale.set_range(0, max(c.duration, 1))
        if not self._dragging:
            self.scale.set_value(c.position)

    def on_sleep(self) -> None:
        left = self.ctl.sleep_left
        self.sleep_content.set_label(f"{left} min" if left > 0 else "")
