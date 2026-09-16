import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

Item {
    id: root

    property bool shown: false

    signal openRequested()
    signal pasteRequested()

    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown

    Behavior on opacity {
        NumberAnimation {
            duration: Theme.transitionDuration
            easing.type: Easing.OutCubic
        }
    }

    readonly property bool narrow: width < Theme.narrowWidth

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.narrow ? Theme.spacing : Theme.pageMargin

        spacing: Theme.spacingLarge

        /*
           On a narrow window the title and three buttons cannot share a row
           without the title being squeezed to nothing, so the actions drop
           to their own line instead of clipping.
        */
        GridLayout {
            Layout.fillWidth: true

            columns: root.narrow ? 1 : 2

            columnSpacing: Theme.spacingSmall
            rowSpacing: Theme.spacingSmall

            Label {
                text: "Your Library"

                font.pixelSize: Theme.fontSizeDisplay
                font.weight: Font.DemiBold

                color: Theme.text

                Layout.fillWidth: true
                elide: Label.ElideRight
            }

            Flow {
                Layout.fillWidth: root.narrow
                Layout.alignment: root.narrow
                                  ? Qt.AlignLeft
                                  : Qt.AlignRight | Qt.AlignVCenter

                spacing: Theme.spacingSmall

                Button {
                    text: "Settings"

                    Accessible.name: "Settings"

                    onClicked: vm.showSettings()
                }

                Button {
                    text: "Paste Text"

                    Accessible.name: "Read pasted text"

                    onClicked: root.pasteRequested()
                }

                Button {
                    text: "Open Book"
                    highlighted: true

                    Accessible.name: "Open a book"

                    onClicked: root.openRequested()
                }
            }
        }

        GridView {
            id: view

            Layout.fillWidth: true
            Layout.fillHeight: true

            clip: true

            model: vm.books

            // Cards keep a comfortable reading width and the column count
            // follows the window, so nothing has to be measured by hand.
            readonly property int columns: Math.max(1, Math.floor(width / 380))

            cellWidth: width / columns
            cellHeight: 132

            delegate: Item {
                width: view.cellWidth
                height: view.cellHeight

                BookCard {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingTight / 2

                    title: model.title
                    subtitle: model.subtitle
                    fileType: model.fileType
                    missing: model.missing

                    onOpened: vm.openBook(model.path)
                    onDeleted: vm.requestDelete(model.path, model.title)
                }
            }

            ScrollBar.vertical: ScrollBar {}

            Label {
                anchors.centerIn: parent

                visible: view.count === 0

                text: "No books or texts yet. Open a book or paste text to begin."

                color: Theme.textFaint
                font.pixelSize: Theme.fontSizeReader
            }
        }
    }
}
