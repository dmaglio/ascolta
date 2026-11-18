"""Avvio dell'applicazione Qt / Kirigami, con icona nel tray."""
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .backend import Backend
from .config import APP_ID

ICON = "audio-headphones"


class Shell(QObject):
    """Finestra + tray: chiudere la finestra la nasconde, l'app resta attiva."""

    def __init__(self, app: QApplication, backend: Backend, window) -> None:
        super().__init__()
        self.app, self.backend, self.window = app, backend, window
        self.tray = QSystemTrayIcon(QIcon.fromTheme(ICON), app)
        self.tray.setToolTip("Ascolta")
        menu = QMenu()
        self.act_show = menu.addAction("Mostra / nascondi", self.toggle_window)
        menu.addSeparator()
        self.act_play = menu.addAction("Play / Pausa", backend.toggle)
        menu.addAction(QIcon.fromTheme("media-seek-backward"), "Indietro di 15 s",
                       lambda: backend.skip(-15))
        menu.addAction(QIcon.fromTheme("media-seek-forward"), "Avanti di 15 s",
                       lambda: backend.skip(15))
        menu.addSeparator()
        menu.addAction(QIcon.fromTheme("application-exit"), "Esci", app.quit)
        self.menu = menu  # tenuto vivo
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()
        backend.nowChanged.connect(self._tooltip)
        backend.notify.connect(self._notify)
        backend.mpris.raiseRequested.connect(self.show_window)
        backend.mpris.quitRequested.connect(app.quit)

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()
        elif reason == QSystemTrayIcon.MiddleClick:
            self.backend.toggle()

    def _tooltip(self) -> None:
        b = self.backend
        self.tray.setToolTip(f"{b.nowTitle}\n{b.nowAuthors}" if b.nowTitle else "Ascolta")

    @Slot(str, str)
    def _notify(self, title: str, text: str) -> None:
        # con la finestra davanti i messaggi sono già nel piè di pagina
        if self.window.isVisible() and self.window.isActive():
            return
        if QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, text, QIcon.fromTheme(ICON), 8000)

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def toggle_window(self) -> None:
        if self.window.isVisible() and self.window.isActive():
            self.window.hide()
        else:
            self.show_window()


def main() -> None:
    if "QT_QUICK_CONTROLS_STYLE" not in os.environ:
        QQuickStyle.setStyle("org.kde.desktop")
    app = QApplication(sys.argv)
    app.setApplicationName("audible-kde")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationDomain("kde.org")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(ICON))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    backend = Backend()
    app.aboutToQuit.connect(backend.shutdown)

    tray_ok = Shell.available()
    app.setQuitOnLastWindowClosed(not tray_ok)  # con il tray, chiudere = nascondere

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("hasTray", tray_ok)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    shell = Shell(app, backend, engine.rootObjects()[0]) if tray_ok else None
    backend.start()
    code = app.exec()
    del shell
    sys.exit(code)
