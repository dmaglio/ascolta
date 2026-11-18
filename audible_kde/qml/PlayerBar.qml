import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

QQC2.ToolBar {
    id: bar
    position: QQC2.ToolBar.Footer

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            Image {
                source: backend.nowCover
                sourceSize.height: 160
                fillMode: Image.PreserveAspectFit
                Layout.preferredHeight: Kirigami.Units.gridUnit * 3
                Layout.preferredWidth: Layout.preferredHeight
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                QQC2.Label { text: backend.nowTitle; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                QQC2.Label { text: backend.nowAuthors; opacity: 0.7; Layout.fillWidth: true; elide: Text.ElideRight }
                QQC2.Label { text: backend.chapterTitle; opacity: 0.7; Layout.fillWidth: true; elide: Text.ElideRight
                    visible: text !== "" }
            }

            QQC2.ToolButton { icon.name: "media-skip-backward"; onClicked: backend.chapter(-1)
                QQC2.ToolTip.text: "Capitolo precedente"; QQC2.ToolTip.visible: hovered }
            QQC2.ToolButton { icon.name: "media-seek-backward"; onClicked: backend.skip(-15)
                QQC2.ToolTip.text: "Indietro di 15 s"; QQC2.ToolTip.visible: hovered }
            QQC2.RoundButton {
                icon.name: backend.playing ? "media-playback-pause" : "media-playback-start"
                onClicked: backend.toggle()
            }
            QQC2.ToolButton { icon.name: "media-seek-forward"; onClicked: backend.skip(15)
                QQC2.ToolTip.text: "Avanti di 15 s"; QQC2.ToolTip.visible: hovered }
            QQC2.ToolButton { icon.name: "media-skip-forward"; onClicked: backend.chapter(1)
                QQC2.ToolTip.text: "Capitolo successivo"; QQC2.ToolTip.visible: hovered }

            QQC2.ToolButton {
                text: backend.speed.toFixed(2).replace(/0$/, "") + "×"
                onClicked: speedMenu.popup()
                QQC2.Menu {
                    id: speedMenu
                    Repeater {
                        model: [0.8, 1.0, 1.2, 1.5, 1.75, 2.0, 2.5]
                        QQC2.MenuItem { required property real modelData
                            text: modelData + "×"; onTriggered: backend.setSpeed(modelData) }
                    }
                }
            }
            QQC2.ToolButton {
                icon.name: "clock"
                text: backend.sleepLeft > 0 ? backend.sleepLeft + " min" : ""
                onClicked: sleepMenu.popup()
                QQC2.ToolTip.text: "Sleep timer"; QQC2.ToolTip.visible: hovered
                QQC2.Menu {
                    id: sleepMenu
                    QQC2.MenuItem { text: "Spento"; onTriggered: backend.setSleep(0) }
                    Repeater {
                        model: [15, 30, 45, 60]
                        QQC2.MenuItem { required property int modelData
                            text: modelData + " minuti"; onTriggered: backend.setSleep(modelData) }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            QQC2.Label { text: backend.positionText; font: Kirigami.Theme.fixedWidthFont }
            QQC2.Slider {
                id: seek
                Layout.fillWidth: true
                from: 0
                to: Math.max(backend.duration, 1)
                value: backend.position
                onMoved: backend.seekTo(value)
            }
            QQC2.Label { text: backend.durationText; font: Kirigami.Theme.fixedWidthFont }
        }
    }
}
