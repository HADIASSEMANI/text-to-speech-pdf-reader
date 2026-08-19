import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

Item {
    id: root

    property bool shown: false

    signal openRequested()

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

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall

            Label {
                text: "Your Library"

                font.pixelSize: Theme.fontSizeDisplay
                font.weight: Font.DemiBold

                color: Theme.text

                Layout.fillWidth: true
                elide: Label.ElideRight
            }

            Button {
                text: "Settings"
                onClicked: vm.showSettings()
            }

            Button {
                text: "Open Book"
                highlighted: true

                onClicked: root.openRequested()
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

                text: "No books yet. Open a book to begin."

                color: Theme.textFaint
                font.pixelSize: Theme.fontSizeReader
            }
        }
    }
}
