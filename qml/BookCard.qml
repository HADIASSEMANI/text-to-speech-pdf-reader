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

    radius: Theme.radiusLarge

    color: hover.hovered ? Theme.surfaceHover : Theme.surfaceRaised

    border.width: 1
    border.color: card.missing
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
            text: "Delete"

            // Only offered once the card is under the pointer: a library of
            // cards should read as covers, not as a row of controls.
            opacity: hover.hovered ? 1 : 0
            visible: opacity > 0

            Behavior on opacity {
                NumberAnimation { duration: Theme.transitionDuration }
            }

            ToolTip.visible: hovered
            ToolTip.text: "Remove this book from the library"

            onClicked: card.deleted()
        }
    }
}
