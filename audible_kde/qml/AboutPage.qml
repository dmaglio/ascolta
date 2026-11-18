import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Informazioni"

    readonly property string repoUrl: "https://github.com/dmaglio/ascolta"

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Icon {
            source: "io.github.dmaglio.Ascolta"
            fallback: "audio-headphones"
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Kirigami.Units.iconSizes.huge
            Layout.preferredHeight: Kirigami.Units.iconSizes.huge
        }
        Kirigami.Heading {
            text: "Ascolta"
            Layout.alignment: Qt.AlignHCenter
        }
        QQC2.Label {
            text: "Versione " + Qt.application.version
            opacity: 0.7
            Layout.alignment: Qt.AlignHCenter
        }
        QQC2.Label {
            text: "Lettore non ufficiale per gli audiolibri che hai acquistato su Audible. Non è affiliato né approvato da Audible o Amazon."
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
        QQC2.Label {
            text: "Licenza AGPL-3.0-or-later · © 2026 Davide Maglio"
            opacity: 0.7
            Layout.alignment: Qt.AlignHCenter
        }

        Kirigami.Separator { Layout.fillWidth: true }

        Kirigami.Heading {
            level: 3
            text: "Note legali"
        }
        QQC2.Label {
            text: "Audible è un marchio di Audible, Inc. (gruppo Amazon); questo progetto è indipendente e usa quel nome solo per indicare il servizio con cui è compatibile.\n\n" +
                  "Il programma serve ad ascoltare gli audiolibri che hai acquistato con il tuo account, per uso personale. L'uso del servizio resta soggetto alle condizioni di Audible: sei tu responsabile di rispettarle. Non aggira la protezione per condividere o ridistribuire i libri.\n\n" +
                  "Il software è fornito «così com'è», senza alcuna garanzia, secondo i termini della licenza AGPL-3.0-or-later. Le credenziali restano sul tuo computer e vengono inviate solo ad Audible.\n\n" +
                  "Usa Qt e KDE Frameworks (LGPL), mpv e FFmpeg, python-audible (AGPL), PySide6 (LGPL) e altre librerie libere, ciascuna con la propria licenza."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        Kirigami.Separator { Layout.fillWidth: true }

        Kirigami.Heading {
            level: 3
            text: "Feedback"
        }
        QQC2.Label {
            text: "Hai trovato un problema o hai un'idea? Scrivilo nelle segnalazioni del progetto: ogni commento è benvenuto. Se possibile indica la versione e cosa stavi facendo; non allegare mai il file auth.json."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            QQC2.Button {
                icon.name: "tools-report-bug"
                text: "Segnala un problema"
                onClicked: Qt.openUrlExternally(page.repoUrl + "/issues/new")
            }
            QQC2.Button {
                icon.name: "mail-message-new"
                text: "Proponi un'idea"
                onClicked: Qt.openUrlExternally(page.repoUrl + "/discussions")
            }
            QQC2.Button {
                icon.name: "internet-services"
                text: "Sito del progetto"
                onClicked: Qt.openUrlExternally(page.repoUrl)
            }
        }
    }
}
