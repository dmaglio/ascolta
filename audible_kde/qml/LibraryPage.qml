import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "La mia libreria"

    actions: [
        Kirigami.Action {
            icon.name: "view-refresh"
            text: "Aggiorna"
            onTriggered: backend.refresh()
        }
    ]

    header: QQC2.ToolBar {
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            Kirigami.SearchField {
                Layout.fillWidth: true
                placeholderText: "Cerca per titolo, autore, narratore o serie…"
                onTextChanged: backend.setFilter(text)
            }
            RowLayout {
                Layout.fillWidth: true
                QQC2.Label { text: "Mostra" }
                QQC2.ComboBox {
                    id: statusBox
                    textRole: "text"; valueRole: "value"
                    model: [
                        { text: "Tutti", value: "all" },
                        { text: "In corso", value: "inprogress" },
                        { text: "Da iniziare", value: "unstarted" },
                        { text: "Finiti", value: "finished" },
                        { text: "Scaricati", value: "downloaded" }
                    ]
                    onActivated: backend.setStatusFilter(currentValue)
                }
                Item { Layout.fillWidth: true }
                QQC2.Label { text: "Ordina per" }
                QQC2.ComboBox {
                    id: sortBox
                    textRole: "text"; valueRole: "value"
                    model: [
                        { text: "Serie", value: "series" },
                        { text: "Titolo", value: "title" },
                        { text: "Autore", value: "authors" },
                        { text: "Data di acquisto", value: "purchased" },
                        { text: "Durata", value: "minutes" },
                        { text: "Avanzamento", value: "percent" }
                    ]
                    onActivated: {
                        // acquisti e avanzamento: prima i più recenti / più avanti
                        dir.checked = currentValue === "purchased" || currentValue === "percent"
                        backend.setSort(currentValue, dir.checked)
                    }
                }
                QQC2.CheckBox {
                    id: groupBox
                    text: "Raggruppa per serie"
                    checked: backend.grouped
                    onToggled: backend.setGrouped(checked)
                }
                QQC2.ToolButton {
                    id: dir
                    checkable: true
                    icon.name: checked ? "view-sort-descending" : "view-sort-ascending"
                    QQC2.ToolTip.text: checked ? "Decrescente" : "Crescente"
                    QQC2.ToolTip.visible: hovered
                    onToggled: backend.setSort(sortBox.currentValue, checked)
                }
            }
        }
    }

    Kirigami.CardsListView {
        id: list
        model: backend.library
        section.property: backend.grouped ? "series" : ""
        section.criteria: ViewSection.FullString
        section.delegate: Kirigami.ListSectionHeader {
            required property string section
            width: list.width
            label: section !== "" ? section : "Senza serie"
        }
        delegate: Kirigami.AbstractCard {
            id: card
            required property string asin
            required property string title
            required property string authors
            required property string narrators
            required property string series
            required property string seq
            required property int minutes
            required property real percent
            required property bool finished
            required property string coverUrl
            required property bool downloaded
            required property bool busy

            highlighted: asin === backend.nowAsin
            contentItem: RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Image {
                    source: card.coverUrl
                    sourceSize.height: 240
                    fillMode: Image.PreserveAspectFit
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 5
                    Layout.preferredWidth: Layout.preferredHeight
                    asynchronous: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Kirigami.Heading { level: 3; text: card.title; Layout.fillWidth: true
                        elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.WordWrap }
                    QQC2.Label { text: card.authors; opacity: 0.8; Layout.fillWidth: true; elide: Text.ElideRight }
                    QQC2.Label {
                        visible: card.series !== ""
                        text: card.series + (card.seq !== "" ? " #" + card.seq : "")
                        opacity: 0.6; Layout.fillWidth: true; elide: Text.ElideRight
                    }
                    QQC2.Label {
                        text: Math.floor(card.minutes / 60) + " h " + (card.minutes % 60) + " min"
                              + (card.finished ? " · finito" : card.percent > 0 ? " · " + Math.round(card.percent) + "%" : "")
                        opacity: 0.6
                    }
                    Rectangle {
                        visible: card.percent > 0 && !card.finished
                        Layout.fillWidth: true
                        implicitHeight: Kirigami.Units.smallSpacing
                        radius: height / 2
                        color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
                        Rectangle {
                            width: parent.width * card.percent / 100
                            height: parent.height
                            radius: parent.radius
                            color: Kirigami.Theme.highlightColor
                        }
                    }
                }
                QQC2.BusyIndicator { running: card.busy; visible: card.busy }
                QQC2.Button {
                    visible: !card.downloaded && !card.busy
                    icon.name: "download"
                    display: QQC2.AbstractButton.IconOnly
                    QQC2.ToolTip.text: "Scarica"
                    QQC2.ToolTip.visible: hovered
                    onClicked: backend.download(card.asin)
                }
                QQC2.Button {
                    enabled: !card.busy
                    icon.name: card.asin === backend.nowAsin && backend.playing
                               ? "media-playback-pause" : "media-playback-start"
                    display: QQC2.AbstractButton.IconOnly
                    onClicked: backend.play(card.asin)
                }
            }
            onClicked: applicationWindow().pageStack.push(
                Qt.resolvedUrl("DetailsPage.qml"), { asin: card.asin })
        }

        QQC2.Label {
            anchors.centerIn: parent
            visible: list.count === 0
            text: "Nessun audiolibro corrisponde ai filtri"
            opacity: 0.6
        }
    }

    footer: QQC2.Label {
        text: backend.message
        padding: Kirigami.Units.smallSpacing
        opacity: 0.7
        elide: Text.ElideRight
        visible: text !== ""
    }
}
