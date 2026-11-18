import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "Ascolta"
    width: 1000
    height: 700
    minimumWidth: 480
    minimumHeight: 360

    // con il tray, la X nasconde la finestra e la riproduzione continua
    onClosing: (close) => {
        if (hasTray) {
            close.accepted = false
            root.hide()
        }
    }

    pageStack.initialPage: backend.state === "login" ? loginPage : libraryPage
    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn

    Connections {
        target: backend
        function onStateChanged() {
            root.pageStack.clear()
            root.pageStack.push(backend.state === "login" ? loginPage : libraryPage)
        }
    }

    globalDrawer: Kirigami.GlobalDrawer {
        isMenu: true
        actions: [
            Kirigami.Action {
                icon.name: "help-about"
                text: "Informazioni su Ascolta"
                onTriggered: root.pageStack.push(aboutPage)
            }
        ]
    }

    Component { id: aboutPage; AboutPage {} }
    Component { id: loginPage; LoginPage {} }
    Component { id: libraryPage; LibraryPage {} }

    footer: PlayerBar { visible: backend.state === "ready" && backend.nowAsin !== "" }
}
