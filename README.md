# Ascolta

Lettore di audiolibri per KDE Plasma (Qt6, Kirigami, PySide6), compatibile con
Audible. Il backend deriva da [audible-tui](https://github.com/dmaglio/audible-tui).

> **Progetto non ufficiale.** Non è affiliato, sponsorizzato né approvato da
> Audible, Inc. o da Amazon. «Audible» è un marchio dei rispettivi titolari e qui
> indica solo il servizio con cui il programma è compatibile.

- libreria con ricerca, download e decifratura in M4B (ffmpeg), riproduzione con mpv
- capitoli, velocità, ±15 s, sleep timer
- punto di ascolto sincronizzato con Audible ed eventi di ascolto
- icona nel tray: chiudere la finestra la nasconde, l'ascolto continua
- tasti multimediali e controller multimediale di Plasma (MPRIS)

## Uso consentito

Serve ad ascoltare **i libri che hai acquistato con il tuo account**, per uso
personale. Le condizioni d'uso di Audible restano valide e rispettarle è una tua
responsabilità. Il programma non è pensato per condividere o ridistribuire i
libri. Le credenziali restano sul tuo computer e vengono inviate solo ad Audible.

## Installazione

### Flatpak

```sh
cd packaging/flatpak
flatpak run org.flatpak.Builder --user --install --force-clean \
    --disable-rofiles-fuse build io.github.dmaglio.Ascolta.yml
flatpak run io.github.dmaglio.Ascolta
```

Servono `org.kde.Platform//6.11`, `org.kde.Sdk//6.11`, `io.qt.PySide.BaseApp//6.11`
e `org.flatpak.Builder` (da Flathub). Nel sandbox i libri vanno in `~/Audiolibri`
e il token in `~/.var/app/io.github.dmaglio.Ascolta/`.

### Da sorgente (Fedora)

```sh
sudo dnf install python3-pyside6 kf6-kirigami kf6-qqc2-desktop-style mpv-libs ffmpeg
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e . --ignore-requires-python   # audible 0.13 dichiara Python < 3.15
.venv/bin/audible-kde
```

Al primo avvio la schermata di accesso apre il login Audible nel browser (vanno
bene 2FA e captcha): si incolla l'indirizzo finale. Il token resta in
`~/.config/audible-kde/auth.json` (**non condividerlo mai**, nemmeno nelle
segnalazioni). Libri in `~/Audiolibri` (`AUDIBLE_KDE_BOOKS`), mercato `it`
(`AUDIBLE_KDE_LOCALE`).

## Versione GTK (GNOME)

Oltre a quella Qt c'è un'interfaccia GTK4 / libadwaita (`ascolta-gtk`), che usa
gli stessi moduli di accesso, riproduzione, MPRIS e statistiche. Chiudere la
finestra la nasconde e l'ascolto continua; si disattiva in **Preferenze →
Resta attivo in background**. Per uscire del tutto: menu → Esci, Ctrl+Q o il
comando *Quit* del controller multimediale.

```sh
sudo dnf install python3-gobject libadwaita mpv-libs ffmpeg
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e . --ignore-requires-python
.venv/bin/ascolta-gtk
```

Manifest Flatpak in `packaging/flatpak-gtk/` (non ancora compilato). Il token
resta in `~/.config/audible-kde/auth.json`, lo stesso della versione Qt; le
preferenze GTK in `gtk-settings.json` accanto.

## Feedback

Segnalazioni e idee sono benvenute: [issues](https://github.com/dmaglio/ascolta/issues)
per i problemi, [discussions](https://github.com/dmaglio/ascolta/discussions) per
le proposte. Si apre anche da *Informazioni* dentro l'app.

## Licenza

[GNU AGPL-3.0 o successiva](LICENSE). Il software è fornito «così com'è», senza
garanzie. Usa Qt e KDE Frameworks (LGPL), PySide6 (LGPL), mpv, FFmpeg e
[python-audible](https://github.com/mkb79/Audible) (AGPL), ciascuno con la propria licenza.
