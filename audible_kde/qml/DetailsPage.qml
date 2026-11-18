import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    property string asin: ""
    property var book: backend.book(asin)
    title: book.title || ""

    // si aggiorna quando cambiano progresso, download o riproduzione
    Connections {
        target: backend.library
        function onDataChanged() { page.book = backend.book(page.asin) }
    }
    Connections {
        target: backend
        function onNowChanged() { page.book = backend.book(page.asin) }
        function onTickChanged() {
            if (page.book.playing !== (backend.nowAsin === page.asin && backend.playing))
                page.book = backend.book(page.asin)
        }
    }

    function duration(min) {
        return Math.floor(min / 60) + " h " + (min % 60) + " min"
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            Image {
                source: page.book.cover_url || ""
                sourceSize.height: 640
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 12
                Layout.preferredWidth: Layout.preferredHeight
                Layout.alignment: Qt.AlignTop
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Heading { text: page.book.title || ""; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                QQC2.Label { text: page.book.authors || ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.8 }

                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    QQC2.Label {
                        Kirigami.FormData.label: "Letto da:"
                        visible: !!page.book.narrators
                        text: page.book.narrators || ""
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    QQC2.Label {
                        Kirigami.FormData.label: "Serie:"
                        visible: !!page.book.series
                        text: (page.book.series || "") + (page.book.seq ? " #" + page.book.seq : "")
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    QQC2.Label { Kirigami.FormData.label: "Durata:"; text: page.duration(page.book.minutes || 0) }
                    QQC2.Label {
                        Kirigami.FormData.label: "Acquistato il:"
                        visible: !!page.book.purchased
                        text: page.book.purchased || ""
                    }
                    QQC2.Label {
                        Kirigami.FormData.label: "Stato:"
                        text: page.book.finished ? "Finito"
                              : (page.book.percent || 0) > 0 ? "In corso, " + Math.round(page.book.percent) + "%"
                              : "Da iniziare"
                    }
                    QQC2.Label {
                        Kirigami.FormData.label: "File:"
                        visible: !!page.book.downloaded
                        text: page.book.path || ""
                        wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                        font: Kirigami.Theme.smallFont
                    }
                }

                Rectangle {
                    visible: (page.book.percent || 0) > 0 && !page.book.finished
                    Layout.fillWidth: true
                    implicitHeight: Kirigami.Units.smallSpacing
                    radius: height / 2
                    color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
                    Rectangle {
                        width: parent.width * (page.book.percent || 0) / 100
                        height: parent.height
                        radius: parent.radius
                        color: Kirigami.Theme.highlightColor
                    }
                }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.Button {
                        enabled: !page.book.busy
                        icon.name: page.book.playing ? "media-playback-pause" : "media-playback-start"
                        text: page.book.playing ? "Pausa"
                              : page.book.downloaded ? "Ascolta" : "Scarica e ascolta"
                        highlighted: true
                        onClicked: backend.play(page.asin)
                    }
                    QQC2.Button {
                        visible: !page.book.downloaded && !page.book.busy
                        icon.name: "download"
                        text: "Solo download"
                        onClicked: backend.download(page.asin)
                    }
                    QQC2.BusyIndicator { running: !!page.book.busy; visible: !!page.book.busy }
                }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.Button {
                        icon.name: page.book.finished ? "edit-undo" : "checkmark"
                        text: page.book.finished ? "Segna come da finire" : "Segna come finito"
                        onClicked: backend.markFinished(page.asin, !page.book.finished)
                    }
                    QQC2.Button {
                        visible: !!page.book.downloaded
                        enabled: !page.book.busy
                        icon.name: "edit-delete"
                        text: "Elimina file…"
                        onClicked: confirmDelete.open()
                    }
                }
            }
        }

        Kirigami.Heading {
            level: 3
            text: "Trama"
            visible: !!page.book.summary
        }
        QQC2.Label {
            Layout.fillWidth: true
            visible: !!page.book.summary
            text: page.book.summary || ""
            wrapMode: Text.WordWrap
        }
    }

    Kirigami.PromptDialog {
        id: confirmDelete
        title: "Eliminare il file?"
        subtitle: "Il file scaricato di «" + (page.book.title || "") + "» verrà rimosso dal disco. "
                  + "Potrai scaricarlo di nuovo da Audible; il punto di ascolto resta salvato."
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                text: "Elimina"
                icon.name: "edit-delete"
                onTriggered: { backend.deleteFile(page.asin); confirmDelete.close() }
            },
            Kirigami.Action {
                text: "Annulla"
                icon.name: "dialog-cancel"
                onTriggered: confirmDelete.close()
            }
        ]
    }
}
