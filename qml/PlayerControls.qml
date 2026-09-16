import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

Item {
    id: controls

    property bool narrow: false

    implicitHeight: layout.implicitHeight

    function formatTime(seconds) {
        const whole = Math.max(0, Math.floor(seconds))

        const minutes = Math.floor(whole / 60)
        const remaining = whole % 60

        return minutes + ":" + (remaining < 10 ? "0" : "") + remaining
    }

    ColumnLayout {
        id: layout

        anchors.fill: parent
        spacing: Theme.spacingSmall

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall

            Label {
                text: controls.formatTime(vm.position)

                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSmall

                // Fixed width so the row does not jitter as the digits change.
                Layout.minimumWidth: 44
            }

            Slider {
                id: seekSlider

                Layout.fillWidth: true

                Accessible.name: "Position in this passage"

                from: 0
                to: 1

                value: vm.duration > 0 ? vm.position / vm.duration : 0

                // `onMoved` fires for user input only, so the binding above
                // is never fighting the playhead.
                onMoved: vm.seek(value * vm.duration)
            }

            Label {
                text: controls.formatTime(vm.duration)

                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSmall

                Layout.minimumWidth: 44
                horizontalAlignment: Label.AlignRight
            }
        }

        // Below the breakpoint the transport wraps rather than shrinking its
        // buttons past the point of being hittable.
        Flow {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter

            spacing: Theme.spacingTight

            Button {
                text: "Previous"

                Accessible.name: "Previous passage"
                Accessible.description: "Restarts this passage, or moves back "
                                        + "when you are near its start"

                onClicked: vm.previous()
            }

            Button {
                text: "-15s"

                Accessible.name: "Back fifteen seconds"

                onClicked: vm.skipBack()
            }

            Button {
                /*
                   The label follows the controller's own state, so it can no
                   longer say Play while audio is sounding. A passage that is
                   still being prepared already counts as playing: the
                   listener asked for it, and pressing again stops it.
                */
                text: vm.playing ? "Pause" : "Play"

                highlighted: true

                implicitWidth: Math.max(implicitContentWidth + 40, 110)

                Accessible.name: vm.playing ? "Pause" : "Play"
                Accessible.description: vm.playbackState === "preparing"
                                        ? "Preparing audio for this passage"
                                        : ""

                onClicked: vm.togglePlay()
            }

            Button {
                text: "+15s"

                Accessible.name: "Forward fifteen seconds"

                onClicked: vm.skipForward()
            }

            Button {
                text: "Next"

                Accessible.name: "Next passage"

                onClicked: vm.next()
            }
        }
    }
}
