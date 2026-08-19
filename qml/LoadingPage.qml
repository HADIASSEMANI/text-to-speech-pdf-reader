import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

Item {
    id: root

    property bool shown: false

    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown

    Behavior on opacity {
        NumberAnimation {
            duration: Theme.transitionDuration
            easing.type: Easing.OutCubic
        }
    }

    ColumnLayout {
        anchors.centerIn: parent

        width: Math.min(parent.width - Theme.pageMargin * 2, 460)

        spacing: Theme.spacingLarge

        RainbowSpinner {
            Layout.alignment: Qt.AlignHCenter

            // Nothing to animate while the page is off screen.
            running: root.shown
        }

        Label {
            text: vm.loadingTitle

            color: Theme.text
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold

            horizontalAlignment: Label.AlignHCenter
            Layout.fillWidth: true
        }

        Label {
            text: vm.loadingStatus

            color: Theme.textMuted

            horizontalAlignment: Label.AlignHCenter
            wrapMode: Label.Wrap

            Layout.fillWidth: true
        }

        ProgressBar {
            from: 0
            to: 100
            value: vm.loadingProgress

            Layout.fillWidth: true

            Behavior on value {
                NumberAnimation {
                    duration: 220
                    easing.type: Easing.OutCubic
                }
            }
        }
    }
}
