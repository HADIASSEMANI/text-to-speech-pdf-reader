import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

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
            "Supported Books (*.pdf *.epub)",
            "PDF Files (*.pdf)",
            "EPUB Files (*.epub)"
        ]

        onAccepted: vm.openBook(selectedFile)
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
