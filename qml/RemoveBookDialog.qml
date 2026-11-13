import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "."

/*
   Confirmation for removing a book from the library.

   Two things are deliberate here. The dialog never sizes itself from the
   book title: a long filename wraps inside a fixed column instead of
   stretching the window. And the footer is written out rather than left to
   `standardButtons`, because Qt orders those by platform convention and the
   order this reader wants is Yes then No.
*/
Dialog {
    id: control

    property string path: ""
    property string bookTitle: ""

    // The control the library should get focus back to once this closes.
    property Item returnFocusTo: null

    readonly property int preferredWidth: 480
    readonly property int windowMargin: 24

    parent: Overlay.overlay

    anchors.centerIn: Overlay.overlay

    width: Math.min(
        preferredWidth,
        (parent ? parent.width : preferredWidth) - windowMargin * 2)

    height: Math.min(
        implicitHeight,
        (parent ? parent.height : implicitHeight) - windowMargin * 2)

    title: "Remove book"

    modal: true

    // Escape cancels; clicking away does not, because removing a book is
    // worth an explicit answer.
    closePolicy: Popup.CloseOnEscape

    // The generated footer is turned off so it cannot appear alongside the
    // explicit one below.
    standardButtons: Dialog.NoButton

    padding: Theme.spacing

    /*
       The style's own dialog background does not draw here, so the panel and
       the dim behind it are stated in the reader's own tokens. Without them
       the library reads straight through the dialog.
    */
    background: Rectangle {
        color: Theme.surfaceRaised
        radius: Theme.radiusLarge

        border.width: 1
        border.color: Theme.borderStrong
    }

    Overlay.modal: Rectangle {
        color: "#a6000000"
    }

    header: Label {
        text: control.title

        color: Theme.text
        font.pixelSize: Theme.fontSizeTitle
        font.weight: Font.DemiBold

        elide: Label.ElideRight

        leftPadding: Theme.spacing
        rightPadding: Theme.spacing
        topPadding: Theme.spacing
        bottomPadding: Theme.spacingTight
    }

    onOpened: noButton.forceActiveFocus()

    onClosed: {
        if (returnFocusTo)
            returnFocusTo.forceActiveFocus()
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingSmall

        Label {
            text: "Remove this book from your library?"

            color: Theme.text
            wrapMode: Label.Wrap

            Layout.fillWidth: true
        }

        /*
           The title is bounded in both directions: it wraps to the dialog
           width, and an unreasonably long filename scrolls rather than
           pushing the buttons off the bottom.
        */
        ScrollView {
            Layout.fillWidth: true
            Layout.maximumHeight: 120

            clip: true

            contentWidth: availableWidth

            Label {
                width: control.availableWidth

                text: control.bookTitle

                // Plain text: a filename can contain characters that would
                // otherwise be read as markup.
                textFormat: Text.PlainText

                color: Theme.text
                font.weight: Font.DemiBold

                wrapMode: Label.Wrap
            }
        }

        Label {
            text: "The original book file will not be deleted."

            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSmall

            wrapMode: Label.Wrap

            Layout.fillWidth: true
        }
    }

    footer: Item {
        implicitHeight: footerRow.implicitHeight + Theme.spacing * 2

        RowLayout {
            id: footerRow

            anchors.fill: parent
            anchors.margins: Theme.spacing

            spacing: Theme.spacingSmall

            Item {
                // Pushes the pair right without stretching either button.
                Layout.fillWidth: true
            }

            Button {
                id: yesButton

                text: "Yes"
                highlighted: Qt.platform.os !== "osx"

                implicitWidth: 92

                Accessible.name: "Remove this book from the library"

                onClicked: control.accept()
            }

            Button {
                id: noButton

                text: "No"

                implicitWidth: 92

                Accessible.name: "Keep this book in the library"

                onClicked: control.reject()
            }
        }
    }
}
