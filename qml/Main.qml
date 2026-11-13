import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

import "."

ApplicationWindow {
    id: window

    width: 1100
    height: 760

    minimumWidth: 420
    minimumHeight: 460

    visible: true
    title: "Book TTS Reader"

    color: Theme.background

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeBody

    Binding {
        target: window
        property: "palette"
        value: Theme.darkPalette
        when: Qt.platform.os === "osx"
    }

    onClosing: vm.shutdown()

    /*
       Every screen stays instantiated and fades in and out. The reader keeps
       its scroll position across a trip to the library, and a transition
       costs an opacity animation rather than a rebuild.
    */
    Item {
        id: pages

        anchors.fill: parent

        LibraryPage {
            id: libraryPage

            anchors.fill: parent
            shown: vm.page === "library"
            onOpenRequested: fileDialog.open()
            onPasteRequested: pasteDialog.open()
        }

        LoadingPage {
            anchors.fill: parent
            shown: vm.page === "loading"
        }

        ReaderPage {
            id: readerPage

            anchors.fill: parent
            shown: vm.page === "reader"

            onShortcutsRequested: shortcutsDialog.open()
        }

        SettingsPage {
            anchors.fill: parent
            shown: vm.page === "settings"
        }
    }

    FileDialog {
        id: fileDialog

        objectName: "fileDialog"

        title: "Open Book"

        nameFilters: [
            "Supported Books and Text (*.pdf *.epub *.txt)",
            "PDF Files (*.pdf)",
            "EPUB Files (*.epub)",
            "Text Files (*.txt)"
        ]

        onAccepted: vm.openBook(selectedFile)
    }

    Dialog {
        id: pasteDialog
        objectName: "pasteDialog"

        anchors.centerIn: parent
        width: Math.min(720, window.width - 48)
        height: Math.min(560, window.height - 48)

        title: "Paste text to read"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        onOpened: {
            standardButton(Dialog.Ok).Accessible.name = "Read pasted text"
            standardButton(Dialog.Cancel).Accessible.name = "Cancel pasting text"
            standardButton(Dialog.Ok).enabled = Qt.binding(function() {
                return pastedText.text.trim().length > 0
            })
            pastedText.forceActiveFocus()
        }
        onAccepted: {
            vm.openPastedText(textTitle.text, pastedText.text)
            textTitle.clear()
            pastedText.clear()
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.spacingSmall

            Label {
                text: "Title (optional)"
                color: Theme.textMuted
            }

            TextField {
                id: textTitle
                Accessible.name: "Title (optional)"
                Layout.fillWidth: true
                placeholderText: "Uses the first line when left blank"
                maximumLength: 80
            }

            Label {
                text: "Text"
                color: Theme.textMuted
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                TextArea {
                    id: pastedText
                    Accessible.name: "Text to read aloud"
                    placeholderText: "Paste or type the text you want read aloud..."
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                }
            }

            Label {
                text: "The text will be saved in your library so you can resume later."
                color: Theme.textFaint
                wrapMode: Label.Wrap
                Layout.fillWidth: true
            }
        }
    }

    Dialog {
        id: errorDialog
        objectName: "errorDialog"
        onOpened: standardButton(Dialog.Ok).Accessible.name = "Dismiss error"

        property string message: ""

        anchors.centerIn: parent

        modal: true
        standardButtons: Dialog.Ok

        width: Math.min(520, window.width - 48)
        height: Math.min(implicitHeight, window.height - 48)

        contentItem: ScrollView {
            id: errorScroll
            clip: true
            contentWidth: availableWidth

            Label {
                width: errorScroll.availableWidth
                text: errorDialog.message
                textFormat: Text.PlainText
                wrapMode: Label.Wrap
            }
        }
    }

    RemoveBookDialog {
        id: deleteDialog

        returnFocusTo: libraryPage.primaryAction

        // One handler, so the removal runs exactly once however the dialog
        // was accepted.
        onAccepted: vm.deleteBook(path)
    }

    /*
       Shortcuts are only useful if they can be found. This is what F1 and
       the "?" key open, and what the reader's keyboard hint points at.
    */
    Dialog {
        id: shortcutsDialog
        objectName: "shortcutsDialog"
        width: Math.min(520, window.width - 48)
        height: Math.min(implicitHeight, window.height - 48)
        onOpened: standardButton(Dialog.Ok).Accessible.name = "Close keyboard shortcuts"

        anchors.centerIn: parent

        title: "Keyboard shortcuts"

        modal: true
        standardButtons: Dialog.Ok

        contentItem: ScrollView {
            id: shortcutsScroll
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: shortcutsScroll.availableWidth
                spacing: Theme.spacingTight

                Repeater {
                    model: [
                        { keys: "Space", action: "Play or pause" },
                        { keys: "\u2190 / \u2192", action: "Previous or next passage" },
                        { keys: "Shift \u2190 / \u2192", action: "Skip 15 seconds" },
                        { keys: Theme.shortcutLabel("L", Qt.platform.os), action: "Go to page" },
                        { keys: Theme.shortcutLabel("O", Qt.platform.os), action: "Open a book" },
                        { keys: "Esc", action: "Back to the library" },
                        { keys: "F1 or ?", action: "Show this list" }
                    ]

                    delegate: RowLayout {
                        required property var modelData

                        Layout.fillWidth: true

                        spacing: Theme.spacingLarge

                        Label {
                            text: modelData.keys

                            color: Theme.text
                            font.family: "monospace"

                            Layout.minimumWidth: 110
                        }

                        Label {
                            text: modelData.action
                            wrapMode: Label.Wrap

                            color: Theme.textMuted

                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: vm

        function onErrorRaised(title, message) {
            errorDialog.title = title
            errorDialog.message = message
            errorDialog.open()
        }

        function onDeleteRequested(path, title) {
            deleteDialog.path = path
            deleteDialog.bookTitle = title
            deleteDialog.open()
        }
    }

    Shortcut {
        sequence: "Space"
        enabled: vm.page === "reader"
        onActivated: vm.togglePlay()
    }

    Shortcut {
        sequence: "Right"
        enabled: vm.page === "reader"
        onActivated: vm.next()
    }

    Shortcut {
        sequence: "Left"
        enabled: vm.page === "reader"
        onActivated: vm.previous()
    }

    Shortcut {
        sequence: "Shift+Right"
        enabled: vm.page === "reader"
        onActivated: vm.skipForward()
    }

    Shortcut {
        sequence: "Shift+Left"
        enabled: vm.page === "reader"
        onActivated: vm.skipBack()
    }

    Shortcut {
        sequence: "Ctrl+O"
        autoRepeat: false
        onActivated: fileDialog.open()
    }

    Shortcut {
        sequence: "Ctrl+L"
        enabled: vm.page === "reader"
        onActivated: readerPage.focusPageField()
    }

    Shortcut {
        sequence: "Escape"
        enabled: vm.page === "reader"
        onActivated: vm.showLibrary()
    }

    Shortcut {
        sequence: "Escape"
        enabled: vm.page === "settings"
        onActivated: vm.closeSettings()
    }

    Shortcut {
        sequences: ["F1", "?"]
        onActivated: shortcutsDialog.open()
    }
}
