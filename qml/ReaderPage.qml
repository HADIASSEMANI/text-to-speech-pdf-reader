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

    function focusPageField() {
        pageField.forceActiveFocus()
        pageField.contentItem.selectAll()
    }

    /*
       The cue the reader is speaking is shown as a selection rather than as
       restyled rich text: a selection moves without relaying out the
       document, and the document here can be a full page of prose.
    */
    function showHighlight() {
        if (vm.highlightEnd > vm.highlightStart) {
            body.select(vm.highlightStart, vm.highlightEnd)
            root.ensureHighlightVisible()
        } else {
            body.deselect()
        }
    }

    function ensureHighlightVisible() {
        const flick = scroll.contentItem

        if (flick.contentHeight <= flick.height)
            return

        const rect = body.positionToRectangle(vm.highlightStart)

        const margin = 48

        if (rect.y < flick.contentY) {
            flick.contentY = Math.max(0, rect.y - margin)
        } else if (rect.y + rect.height > flick.contentY + flick.height) {
            flick.contentY = Math.min(
                flick.contentHeight - flick.height,
                rect.y + rect.height - flick.height + margin)
        }
    }

    Connections {
        target: vm

        function onHighlightChanged() {
            root.showHighlight()
        }

        function onSegmentChanged() {
            body.deselect()
            scroll.contentItem.contentY = 0
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.narrow ? Theme.spacing : Theme.pageMargin

        spacing: Theme.spacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall

            Button {
                text: "Library"
                flat: true

                onClicked: vm.showLibrary()
            }

            Label {
                text: vm.bookTitle

                color: Theme.text
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.DemiBold

                horizontalAlignment: Label.AlignHCenter
                elide: Label.ElideRight

                Layout.fillWidth: true
            }

            Button {
                text: "Settings"
                flat: true

                onClicked: vm.showSettings()
            }
        }

        Label {
            text: vm.statusText

            color: Theme.textMuted

            horizontalAlignment: Label.AlignHCenter
            Layout.fillWidth: true
        }

        ComboBox {
            id: chapterBox

            visible: vm.chapterTitles.length > 0

            Layout.fillWidth: true
            Layout.maximumWidth: 420

            model: vm.chapterTitles
            currentIndex: vm.currentChapter

            displayText: currentIndex < 0
                         ? "Chapters"
                         : currentText.trim()

            onActivated: (index) => vm.goToChapter(index)
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            color: Theme.surface
            radius: Theme.radius

            border.width: 1
            border.color: Theme.border

            ScrollView {
                id: scroll

                anchors.fill: parent
                anchors.margins: 1

                clip: true

                TextArea {
                    id: body

                    text: vm.segmentText

                    readOnly: true
                    wrapMode: TextArea.Wrap

                    // The selection is the narration highlight, so it has to
                    // survive losing focus and must not be draggable.
                    persistentSelection: true
                    selectByMouse: false
                    selectByKeyboard: false

                    color: Theme.text
                    selectionColor: Theme.highlight
                    selectedTextColor: Theme.highlightText

                    font.pixelSize: Theme.fontSizeReader

                    // The style centres a short segment and sets its own
                    // paddings, so both are stated here rather than through
                    // the shared `padding`.
                    verticalAlignment: TextArea.AlignTop

                    topPadding: Theme.spacingLarge
                    bottomPadding: Theme.spacingLarge

                    // Caps the line length on a wide window and centres the
                    // column, instead of running prose the full 1100px.
                    leftPadding: Math.max(Theme.spacingLarge,
                                          (scroll.width - 760) / 2)
                    rightPadding: leftPadding

                    background: null

                    MouseArea {
                        anchors.fill: parent

                        cursorShape: Qt.IBeamCursor

                        onClicked: (mouse) => vm.seekToCharacter(
                                       body.positionAt(mouse.x, mouse.y))
                    }
                }
            }
        }

        /*
           Transport on one side, position in the book on the other. Below
           the breakpoint the page field drops to its own line rather than
           stealing width from the buttons.
        */
        GridLayout {
            Layout.fillWidth: true

            columns: root.narrow ? 1 : 2

            columnSpacing: Theme.spacing
            rowSpacing: Theme.spacingSmall

            PlayerControls {
                Layout.fillWidth: true

                narrow: root.narrow
            }

            RowLayout {
                Layout.alignment: Qt.AlignRight | Qt.AlignBottom

                spacing: Theme.spacingTight

                Label {
                    text: "Page"
                    color: Theme.textMuted
                }

                SpinBox {
                    id: pageField

                    from: 1
                    to: Math.max(1, vm.maxPage)

                    value: vm.currentPage
                    editable: true

                    onValueModified: vm.goToPage(value)
                }
            }
        }
    }
}
