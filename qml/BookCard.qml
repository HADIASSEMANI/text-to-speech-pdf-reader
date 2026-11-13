import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

Rectangle {
    id: card

    property string title: ""
    property string subtitle: ""
    property string fileType: "FILE"
    property bool missing: false

    signal opened()
    signal deleted()

    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: title + (subtitle ? ", " + subtitle : "")
    Accessible.description: "Open " + title + (subtitle ? ". " + subtitle : "")
    Accessible.onPressAction: card.opened()

    Keys.onPressed: (event) => {
        if (card.activeFocus && (event.key === Qt.Key_Return
                || event.key === Qt.Key_Enter || event.key === Qt.Key_Space)) {
            if (!event.isAutoRepeat)
                card.opened()
            event.accepted = true
        }
    }

    radius: Theme.radiusLarge

    color: hover.hovered ? Theme.surfaceHover : Theme.surfaceRaised

    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.accent : card.missing
                  ? (hover.hovered ? "#5a3a40" : Theme.dangerBorder)
                  : (hover.hovered ? Theme.borderStrong : Theme.border)

    Behavior on color {
        ColorAnimation { duration: Theme.transitionDuration }
    }

    HoverHandler {
        id: hover
    }

    TapHandler {
        onTapped: card.opened()
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacing

        spacing: Theme.spacingSmall

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter

            spacing: Theme.spacingTight

            Label {
                text: card.title

                color: card.missing ? Theme.textFaint : Theme.text

                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.DemiBold

                elide: Label.ElideRight
                Layout.fillWidth: true
            }

            RowLayout {
                // Without this the badge and the subtitle size to their own
                // content and run past the card on a narrow window.
                Layout.fillWidth: true

                spacing: Theme.spacingTight

                Rectangle {
                    radius: Theme.radiusSmall / 2

                    color: Theme.surfaceHigh

                    implicitWidth: typeLabel.implicitWidth + Theme.spacingSmall
                    implicitHeight: typeLabel.implicitHeight + 6

                    Label {
                        id: typeLabel

                        anchors.centerIn: parent

                        text: card.fileType

                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeSmall
                        font.weight: Font.DemiBold
                    }
                }

                Label {
                    text: card.subtitle

                    color: card.missing ? Theme.danger : Theme.textMuted
                    font.pixelSize: Theme.fontSizeSmall

                    elide: Label.ElideRight
                    Layout.fillWidth: true
                }
            }
        }

        ToolButton {
            id: removeButton
            objectName: "removeBookButton"
            text: "Delete"
            activeFocusOnTab: true
            Accessible.name: "Remove " + card.title + " from the library"
            Accessible.description: card.subtitle + ". The original file is kept."

            Keys.onReturnPressed: (event) => {
                if (!event.isAutoRepeat) clicked()
            }
            Keys.onEnterPressed: (event) => {
                if (!event.isAutoRepeat) clicked()
            }

            background: Rectangle {
                radius: Theme.radiusSmall
                color: removeButton.hovered || removeButton.down
                       ? Theme.surfaceHover : "transparent"
                border.width: removeButton.activeFocus ? 2 : 0
                border.color: Theme.accent
            }

            // Keep it in the tab chain even before the pointer arrives.
            opacity: hover.hovered || card.activeFocus || activeFocus ? 1 : 0

            ToolTip.visible: hovered
            ToolTip.text: "Remove this book from the library"

            onClicked: card.deleted()
        }
    }
}
