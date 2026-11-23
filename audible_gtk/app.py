"""Avvio dell'applicazione GTK4 / libadwaita, con l'opzione di restare in background."""
from __future__ import annotations

import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .core import Controller
from .settings import Settings
from .ui import DetailsPage, LibraryPage, LoginPage, PlayerBar

APP_ID = os.environ.get("FLATPAK_ID", "io.github.dmaglio.AscoltaGtk")
VERSION = "0.1.0"
REPO = "https://github.com/dmaglio/ascolta"
ICON = "audio-headphones"

LEGAL = (
    "Audible è un marchio di Audible, Inc. (gruppo Amazon); questo progetto è indipendente e "
    "usa quel nome solo per indicare il servizio con cui è compatibile.\n\n"
    "Il programma serve ad ascoltare gli audiolibri che hai acquistato con il tuo account, per "
    "uso personale. L'uso del servizio resta soggetto alle condizioni di Audible: sei tu "
    "responsabile di rispettarle. Non aggira la protezione per condividere o ridistribuire i "
    "libri.\n\n"
    "Il software è fornito «così com'è», senza alcuna garanzia, secondo i termini della licenza "
    "AGPL-3.0-or-later. Le credenziali restano sul tuo computer e vengono inviate solo ad "
    "Audible."
)


class Window(Adw.ApplicationWindow):
    def __init__(self, app: "Ascolta") -> None:
        super().__init__(application=app, title="Ascolta", default_width=1000, default_height=700)
        self.set_size_request(360, 360)
        self.app, self.ctl = app, app.ctl

        menu = Gio.Menu()
        menu.append("Preferenze", "app.preferences")
        menu.append("Informazioni su Ascolta", "app.about")
        menu.append("Esci", "app.quit")
        self.menu = menu

        self.nav = Adw.NavigationView()
        self.player = PlayerBar(self.ctl)
        view = Adw.ToolbarView(content=self.nav)
        view.add_bottom_bar(self.player)
        self.set_content(view)

        self.ctl.connect("state", lambda *_: self.show_state())
        self.show_state()
        self.connect("close-request", self._on_close)

    def show_state(self) -> None:
        if self.ctl.state == "login":
            self.nav.replace([LoginPage(self.ctl)])
        else:
            self.nav.replace([LibraryPage(self.ctl, self.open_book, self.menu)])

    def open_book(self, asin: str) -> None:
        self.nav.push(DetailsPage(self.ctl, asin))

    def _on_close(self, *_) -> bool:
        return self.app.on_window_close(self)


class Ascolta(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.settings = Settings()
        self.ctl: Controller | None = None
        self.window: Window | None = None
        self._held = False
        self._started = False

    # ------------------------------------------------------------ ciclo di vita
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.ctl = Controller()
        self.ctl.connect("notify-user", self._notify)
        self.ctl.connect("raise-window", lambda *_: self.show_window())
        self.ctl.connect("quit-app", lambda *_: self.quit())

        for name, cb, accel in (
            ("preferences", self._preferences, "<primary>comma"),
            ("about", self._about, None),
            ("quit", lambda *_: self.quit(), "<primary>q"),
            ("refresh", lambda *_: self.ctl.refresh(), "F5"),
            ("show", lambda *_: self.show_window(), None),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accel:
                self.set_accels_for_action(f"app.{name}", [accel])
        Gtk.Window.set_default_icon_name(ICON)

    def do_activate(self) -> None:
        if not self.window:
            self.window = Window(self)
        self.show_window()
        if not self._started:  # un secondo avvio riporta solo avanti la finestra
            self._started = True
            self.ctl.start()

    def do_shutdown(self) -> None:
        if self.ctl:
            self.ctl.shutdown()
        Adw.Application.do_shutdown(self)

    # ------------------------------------------------------------ finestra / background
    def show_window(self) -> None:
        if not self.window:
            return
        self._release()
        self.window.set_visible(True)
        self.window.present()

    def on_window_close(self, win: Window) -> bool:
        """La X: con "resta attivo in background" nasconde la finestra e l'app continua."""
        if self.settings.get("background"):
            win.set_visible(False)
            self._hold()
            self._ask_background_portal()
            return True  # evita la distruzione della finestra
        return False  # chiusura normale: senza altre finestre l'app termina

    def _hold(self) -> None:
        if not self._held:
            self._held = True
            self.hold()

    def _release(self) -> None:
        if self._held:
            self._held = False
            self.release()

    def _ask_background_portal(self) -> None:
        """Nel Flatpak avvisa il portale: l'app compare in "Applicazioni in background"."""
        if not os.environ.get("FLATPAK_ID"):
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            options = {"reason": GLib.Variant("s", "Continua l'ascolto a finestra chiusa"),
                       "autostart": GLib.Variant("b", False)}
            bus.call("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                     "org.freedesktop.portal.Background", "RequestBackground",
                     GLib.Variant("(sa{sv})", ("", options)), None,
                     Gio.DBusCallFlags.NONE, -1, None, None, None)
        except GLib.Error:
            pass  # senza portale l'app resta comunque attiva

    # ------------------------------------------------------------ notifiche
    def _notify(self, _ctl, title: str, text: str) -> None:
        # con la finestra davanti i messaggi sono già nel piè di pagina
        if self.window and self.window.is_visible() and self.window.is_active():
            return
        n = Gio.Notification.new(title)
        n.set_body(text)
        n.set_default_action("app.show")
        self.send_notification(None, n)

    # ------------------------------------------------------------ preferenze e informazioni
    def _preferences(self, *_) -> None:
        dialog = Adw.PreferencesDialog()
        page = Adw.PreferencesPage(title="Generale", icon_name="preferences-system-symbolic")
        group = Adw.PreferencesGroup(title="Comportamento")
        row = Adw.SwitchRow(
            title="Resta attivo in background",
            subtitle="Chiudendo la finestra l'ascolto continua. Per uscire del tutto usa "
                     "«Esci» dal menu, Ctrl+Q o i controlli multimediali.",
            active=self.settings.get("background"))
        row.connect("notify::active", lambda r, _p: self.settings.set("background", r.get_active()))
        group.add(row)
        page.add(group)
        dialog.add(page)
        dialog.present(self.window)

    def _about(self, *_) -> None:
        about = Adw.AboutDialog(
            application_name="Ascolta", application_icon=ICON, version=VERSION,
            developer_name="Davide Maglio", copyright="© 2026 Davide Maglio",
            license_type=Gtk.License.AGPL_3_0, website=REPO, issue_url=REPO + "/issues/new",
            comments="Lettore non ufficiale per gli audiolibri che hai acquistato su Audible. "
                     "Non è affiliato né approvato da Audible o Amazon.")
        about.add_legal_section("Note legali", None, Gtk.License.CUSTOM, LEGAL)
        about.present(self.window)


def main() -> int:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return Ascolta().run(sys.argv)
