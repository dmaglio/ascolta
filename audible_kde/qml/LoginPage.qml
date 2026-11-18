import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: page
    title: "Accedi ad Audible"
    property string url: ""

    Connections {
        target: backend
        function onLoginUrl(u) { page.url = u }
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 30)
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Icon { source: "audio-headphones"; Layout.alignment: Qt.AlignHCenter
            implicitWidth: Kirigami.Units.iconSizes.huge; implicitHeight: implicitWidth }

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            text: page.url === ""
                ? "Accedi con il tuo account Audible nel browser. Funzionano anche 2FA e captcha."
                : "1. Apri la pagina e accedi.\n2. Copia l'indirizzo della pagina su cui finisci (anche se è un errore) e incollalo qui sotto."
        }

        QQC2.Button {
            Layout.alignment: Qt.AlignHCenter
            visible: page.url === ""
            text: "Inizia"
            icon.name: "go-next"
            onClicked: backend.beginLogin()
        }

        QQC2.Button {
            Layout.alignment: Qt.AlignHCenter
            visible: page.url !== ""
            text: "Apri la pagina di accesso"
            icon.name: "internet-web-browser"
            onClicked: Qt.openUrlExternally(page.url)
        }

        QQC2.TextField {
            id: pasted
            Layout.fillWidth: true
            visible: page.url !== ""
            placeholderText: "Incolla qui l'indirizzo finale"
            onAccepted: send.clicked()
        }

        QQC2.Button {
            id: send
            Layout.alignment: Qt.AlignHCenter
            visible: page.url !== ""
            enabled: pasted.text.length > 0
            text: "Conferma"
            icon.name: "dialog-ok"
            onClicked: backend.submitLogin(pasted.text)
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: backend.message !== ""
            type: Kirigami.MessageType.Error
            text: backend.message
        }
    }
}
