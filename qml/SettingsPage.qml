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

    readonly property bool narrow: width < Theme.narrowWidth

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.narrow ? Theme.spacing : Theme.pageMargin

        spacing: Theme.spacingLarge

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Settings"

                color: Theme.text
                font.pixelSize: Theme.fontSizeDisplay
                font.weight: Font.DemiBold

                Layout.fillWidth: true
            }

            Button {
                text: "Done"
                highlighted: Qt.platform.os !== "osx"

                Accessible.name: "Close settings"

                onClicked: vm.closeSettings()
            }
        }

        /*
           The settings did not scroll, so on a short window the lower
           controls ran off the bottom with no way to reach them.
        */
        ScrollView {
            id: settingsScroll

            Layout.fillWidth: true
            Layout.fillHeight: true

            clip: true

            contentWidth: availableWidth

        ColumnLayout {
            width: settingsScroll.availableWidth

            spacing: Theme.spacingLarge

        Rectangle {
            Layout.fillWidth: true

            color: Theme.surface
            radius: Theme.radius

            border.width: 1
            border.color: Theme.border

            implicitHeight: narrationLayout.implicitHeight
                            + Theme.spacingLarge * 2

            GridLayout {
                id: narrationLayout

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: Theme.spacingLarge

                // One column when there is no room for a label beside its
                // control.
                columns: root.narrow ? 1 : 2

                rowSpacing: Theme.spacing
                columnSpacing: Theme.spacing

                Label {
                    text: "Text size"
                    color: Theme.textMuted
                }

                SpinBox {
                    objectName: "textSizeControl"
                    Layout.fillWidth: true
                    Layout.maximumWidth: 320
                    from: vm.minimumTextSize
                    to: vm.maximumTextSize
                    stepSize: 1
                    value: vm.textSize
                    textFromValue: function(value) { return value + " px" }
                    Accessible.name: "Text size"
                    Accessible.description: "Reader text size in pixels, from "
                                            + from + " to " + to
                    onValueModified: vm.textSize = value
                }

                Label {
                    text: "Voice"
                    color: Theme.textMuted
                }

                ComboBox {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 320

                    model: ["af_heart", "af_bella", "am_adam"]

                    currentIndex: Math.max(0, model.indexOf(vm.voice))

                    Accessible.name: "Narration voice"

                    onActivated: (index) => vm.voice = model[index]
                }

                Label {
                    text: "Narration speed"
                    color: Theme.textMuted
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 320

                    spacing: Theme.spacingSmall

                    Slider {
                        id: speedSlider

                        Layout.fillWidth: true

                        from: 0.5
                        to: 2.0
                        stepSize: 0.05

                        value: vm.speed

                        Accessible.name: "Narration speed"

                        onMoved: vm.speed = value
                    }

                    Label {
                        text: speedSlider.value.toFixed(2) + "×"

                        color: Theme.text
                        Layout.minimumWidth: 48
                    }
                }

                Label {
                    text: "Audio cache limit"
                    color: Theme.textMuted
                }

                SpinBox {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 320

                    from: 256
                    to: 8192
                    stepSize: 256
                    editable: true
                    value: vm.cacheLimitMb

                    textFromValue: function(value) {
                        return value >= 1024
                                ? (value / 1024).toFixed(value % 1024 ? 1 : 0) + " GB"
                                : value + " MB"
                    }

                    valueFromText: function(text) {
                        var amount = parseFloat(text)
                        return text.toLowerCase().indexOf("gb") >= 0
                                ? Math.round(amount * 1024)
                                : Math.round(amount)
                    }

                    Accessible.name: "Audio cache limit"

                    onValueModified: vm.cacheLimitMb = value
                }

                Label {
                    text: "Stored audio"
                    color: Theme.textMuted
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 320

                    spacing: Theme.spacingSmall

                    Label {
                        text: vm.cacheSizeText
                        color: Theme.text
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }

                    Button {
                        objectName: "clearCacheButton"
                        text: "Clear cache"
                        enabled: vm.cacheSizeBytes > 0

                        Accessible.name: "Clear audio cache"
                        Accessible.description: "Deletes generated audio. Your library and reading positions are kept."

                        onClicked: vm.clearCache()
                    }
                }

                Label {
                    text: "Voice and speed apply to the book you have open, "
                          + "keeping your place. Audio for the new setting is "
                          + "prepared as you reach it. Clearing the cache "
                          + "removes generated audio only; your books and "
                          + "reading positions are kept."

                    color: Theme.textFaint
                    font.pixelSize: Theme.fontSizeSmall

                    wrapMode: Label.Wrap

                    Layout.fillWidth: true
                    Layout.columnSpan: root.narrow ? 1 : 2
                    Layout.topMargin: Theme.spacingTight
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true

            color: Theme.surface
            radius: Theme.radius

            border.width: 1
            border.color: Theme.border

            implicitHeight: contentLayout.implicitHeight
                            + Theme.spacingLarge * 2

            ColumnLayout {
                id: contentLayout

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: Theme.spacingLarge

                spacing: Theme.spacingSmall

                Label {
                    text: "What gets read"

                    color: Theme.textMuted
                    font.weight: Font.DemiBold
                }

                Switch {
                    text: "Read footnotes"
                    Accessible.name: text

                    checked: vm.readFootnotes
                    onToggled: vm.readFootnotes = checked
                }

                Switch {
                    text: "Read figure captions"
                    Accessible.name: text

                    checked: vm.readCaptions
                    onToggled: vm.readCaptions = checked
                }

                Switch {
                    text: "Read sidebars"
                    Accessible.name: text

                    checked: vm.readSidebars
                    onToggled: vm.readSidebars = checked
                }

                Label {
                    text: "These apply the next time a book is opened."

                    color: Theme.textFaint
                    font.pixelSize: Theme.fontSizeSmall

                    Layout.topMargin: Theme.spacingTight
                }
            }
        }

        }
        }
    }
}
