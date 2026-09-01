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

        anchors.centerIn: parent
        width: Math.min(720, window.width - 48)
        height: Math.min(560, window.height - 48)

        title: "Paste text to read"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        onOpened: {
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

        property string message: ""

        anchors.centerIn: parent

        modal: true
        standardButtons: Dialog.Ok

        Label {
            text: errorDialog.message
            wrapMode: Label.Wrap
            width: Math.min(implicitWidth, window.width - 120)
        }
    }

    Dialog {
        id: deleteDialog

        property string path: ""
        property string bookTitle: ""

        anchors.centerIn: parent

        title: "Remove book"

        modal: true
        standardButtons: Dialog.Yes | Dialog.No

        onAccepted: vm.deleteBook(path)

        Label {
            text: "Remove \"" + deleteDialog.bookTitle + "\" from your library?\n\n"
                  + "The original book file will not be deleted."
            wrapMode: Label.Wrap
            width: Math.min(implicitWidth, window.width - 120)
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
}
