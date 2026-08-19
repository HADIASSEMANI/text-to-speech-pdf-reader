import QtQuick

import "."

/*
   The widget spinner repainted itself thirty times a second to turn. Here
   the ring is painted once and the item is rotated, which is a transform on
   an already-uploaded texture rather than a redraw.
*/
Item {
    id: spinner

    property bool running: true

    implicitWidth: 72
    implicitHeight: 72

    Canvas {
        id: ring

        anchors.fill: parent

        onPaint: {
            const context = getContext("2d")

            context.reset()

            const centre = width / 2
            const radius = centre - 8

            const gradient = context.createConicalGradient(centre, centre, 0)

            gradient.addColorStop(0.00, "#ff557f")
            gradient.addColorStop(0.17, "#ffb84d")
            gradient.addColorStop(0.34, "#80e36c")
            gradient.addColorStop(0.51, "#48d8e8")
            gradient.addColorStop(0.68, "#6695ff")
            gradient.addColorStop(0.85, "#b96cff")
            gradient.addColorStop(1.00, "#ff557f")

            context.strokeStyle = gradient
            context.lineWidth = 7
            context.lineCap = "round"

            context.beginPath()
            context.arc(centre, centre, radius, 0, Math.PI * 1.58)
            context.stroke()
        }
    }

    RotationAnimator on rotation {
        running: spinner.running && spinner.visible

        from: 0
        to: 360

        duration: 2200
        loops: Animation.Infinite
    }
}
