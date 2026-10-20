import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

// Full-screen image picker for the onboard LCD, opened by the bar button
// (Panel.qml, passed in as `host`, which owns the state and the actions).
//
// Mouse: click an image to show it, wheel or drag to scroll, click the margin
// to close. Keys: arrows / hjkl move, Enter shows the image under the cursor,
// s flips fixed / rotate, c shows the colour panel, o opens the inbox folder,
// Esc closes. In the colour panel, right-click a slider to reset just that one.
// The overlay stays open after a pick so a slideshow can be watched and
// changed from here.
PanelWindow {
  id: win
  required property var host

  readonly property color fg: Color.imagePicker.text
  readonly property color dim: Qt.darker(fg, 1.4)
  readonly property string fontFamily: Style.font.family
  readonly property real thumbWidth: Style.space(150)
  readonly property real thumbHeight: Math.round(thumbWidth * 960 / 412)
  readonly property real gap: Style.space(20)
  readonly property real labelHeight: Style.font.body + Style.space(10)
  readonly property real adjustWidth: Style.space(340)
  // The colour panel on the right; remembered between opens.
  property bool adjustOpen: false

  visible: host.opened
  screen: host.overlayScreen
  anchors { top: true; bottom: true; left: true; right: true }
  color: "transparent"
  WlrLayershell.namespace: "ai-bkblab-maxsun-lcd"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore

  // Every open starts with the cursor on the image that is showing.
  onVisibleChanged: {
    if (!visible) return
    grid.currentIndex = Math.max(0, host.indexOf(host.selected))
    grid.positionViewAtIndex(grid.currentIndex, GridView.Center)
    focusGrab.tries = 0
    focusGrab.restart()
  }

  // The layer surface gets keyboard focus a moment after it maps, and
  // forceActiveFocus() before that is lost; keep asking until it sticks.
  Timer {
    id: focusGrab
    property int tries: 0
    interval: 50
    repeat: true
    onTriggered: {
      grid.forceActiveFocus()
      if (grid.activeFocus || ++tries >= 20) stop()
    }
  }

  function move(dx, dy) {
    if (grid.count === 0) return
    grid.currentIndex = Math.max(0, Math.min(grid.count - 1, grid.currentIndex + dx + dy * grid.columns))
    grid.positionViewAtIndex(grid.currentIndex, GridView.Contain)
  }

  Rectangle {
    anchors.fill: parent
    color: Util.alpha(Color.background, 0.95)
  }

  // Clicks that miss the header and the grid close the overlay.
  MouseArea {
    anchors.fill: parent
    onClicked: win.host.close()
  }

  FocusScope {
    id: content
    anchors.fill: parent
    anchors.margins: Style.space(56)
    focus: true

    // Keys the grid or the interval field leave unhandled bubble up here.
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape) {
        win.host.close()
        event.accepted = true
        return
      }
      if (intervalField.field.activeFocus) return  // typing a number
      var handled = true
      if (event.key === Qt.Key_Left || event.text === "h") win.move(-1, 0)
      else if (event.key === Qt.Key_Right || event.text === "l") win.move(1, 0)
      else if (event.key === Qt.Key_Up || event.text === "k") win.move(0, -1)
      else if (event.key === Qt.Key_Down || event.text === "j") win.move(0, 1)
      else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space)
        win.host.pick(grid.currentIndex)
      else if (event.text === "s") win.host.setRotating(!win.host.rotating)
      else if (event.text === "o") win.host.openInbox()
      else if (event.text === "c") win.adjustOpen = !win.adjustOpen
      else handled = false
      event.accepted = handled
    }

    Item {
      id: header
      anchors { top: parent.top; left: parent.left; right: parent.right }
      height: Math.max(titles.implicitHeight, controls.implicitHeight)

      MouseArea { anchors.fill: parent }

      Column {
        id: titles
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(4)

        Text {
          textFormat: Text.PlainText
          text: "󰋩  主板小屏"
          color: win.fg
          font.family: win.fontFamily
          font.pixelSize: Style.font.display
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          text: win.host.statusText + "  ·  " + grid.count + " 张"
          color: win.dim
          font.family: win.fontFamily
          font.pixelSize: Style.font.body
        }
      }

      Row {
        id: controls
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(16)

        ButtonGroup {
          anchors.verticalCenter: parent.verticalCenter
          focusable: false
          foreground: win.fg
          fontFamily: win.fontFamily
          options: [
            { value: "fixed", label: "固定这一张" },
            { value: "rotate", label: "轮播", tooltip: "按 s 切换" }
          ]
          value: win.host.rotating ? "rotate" : "fixed"
          onChanged: function(v) { win.host.setRotating(v === "rotate") }
        }

        // 1 s is the floor; anything longer can be typed in, up to a day.
        NumberField {
          id: intervalField
          anchors.verticalCenter: parent.verticalCenter
          label: "间隔（秒）"
          from: 1
          to: 86400
          value: win.host.interval
          foreground: win.fg
          fontFamily: win.fontFamily
          onModified: function(v) { win.host.setInterval(v) }
        }

        PanelActionButton {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰏘"
          tooltipText: "调色 (c)"
          foreground: win.fg
          fontFamily: win.fontFamily
          bordered: win.adjustOpen
          onClicked: win.adjustOpen = !win.adjustOpen
        }

        PanelActionButton {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰉋"
          tooltipText: "打开图片文件夹 (o)"
          foreground: win.fg
          fontFamily: win.fontFamily
          onClicked: win.host.openInbox()
        }

        PanelActionButton {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰅖"
          tooltipText: "关闭 (Esc)"
          foreground: win.fg
          fontFamily: win.fontFamily
          onClicked: win.host.close()
        }
      }
    }

    GridView {
      id: grid
      // Room left of the colour panel when it is open; the grid centres in it.
      readonly property real room: content.width - (win.adjustOpen ? win.adjustWidth + win.gap * 2 : 0)
      readonly property int columns: Math.max(1, Math.floor((room + win.gap) / cellWidth))

      anchors.top: header.bottom
      anchors.topMargin: Style.space(32)
      anchors.bottom: parent.bottom
      x: (room - width) / 2
      width: columns * cellWidth - win.gap
      cellWidth: win.thumbWidth + win.gap
      cellHeight: win.thumbHeight + win.labelHeight + win.gap
      model: win.host.imageModel
      focus: true
      clip: true
      keyNavigationEnabled: false  // the FocusScope moves the cursor and scrolls
      boundsBehavior: Flickable.StopAtBounds

      delegate: Thumb {}
    }

    // Scroll position, shown only when there is something to scroll to.
    Rectangle {
      visible: grid.contentHeight > grid.height
      x: grid.x + grid.width + win.gap / 2 - width / 2
      y: grid.y + grid.visibleArea.yPosition * grid.height
      width: Style.space(4)
      height: grid.visibleArea.heightRatio * grid.height
      radius: width / 2
      color: Util.alpha(win.fg, 0.35)
    }

    Text {
      visible: grid.count === 0
      anchors.centerIn: grid
      width: Math.min(grid.width, Style.space(560))
      horizontalAlignment: Text.AlignHCenter
      wrapMode: Text.Wrap
      textFormat: Text.PlainText
      text: "还没有图片。把图片放进 " + win.host.inboxDir + "，会自动裁切成 412×960 出现在这里。"
      color: win.dim
      font.family: win.fontFamily
      font.pixelSize: Style.font.title
    }

    // Colour correction for the panel. Every change goes straight to the
    // panel (the daemon re-sends the image), so tune it while looking at the
    // screen. The images in ready/ are never modified.
    Rectangle {
      id: adjustPanel
      visible: win.adjustOpen
      anchors.top: header.bottom
      anchors.topMargin: Style.space(32)
      anchors.right: parent.right
      width: win.adjustWidth
      height: Math.min(parent.height - y, adjustColumn.implicitHeight + Style.space(40))
      radius: Style.cornerRadius
      color: Util.alpha(win.fg, 0.05)
      border.width: 1
      border.color: Util.alpha(win.fg, 0.12)

      MouseArea { anchors.fill: parent }

      Column {
        id: adjustColumn
        anchors.fill: parent
        anchors.margins: Style.space(20)
        spacing: Style.space(16)

        Text {
          textFormat: Text.PlainText
          text: "调色"
          color: win.fg
          font.family: win.fontFamily
          font.pixelSize: Style.font.heading
          font.bold: true
        }

        AdjustRow { name: "backlight"; label: "背光（屏幕硬件）"; minimum: 1; maximum: 10; unit: "" }
        AdjustRow { name: "brightness"; label: "亮度"; minimum: 0; maximum: 200; unit: "%" }
        AdjustRow { name: "contrast"; label: "对比度"; minimum: 0; maximum: 200; unit: "%" }
        AdjustRow { name: "saturation"; label: "饱和度"; minimum: 0; maximum: 200; unit: "%" }
        AdjustRow { name: "hue"; label: "色相"; minimum: -180; maximum: 180; unit: "°" }
        AdjustRow { name: "red"; label: "红"; minimum: 0; maximum: 200; unit: "%" }
        AdjustRow { name: "green"; label: "绿"; minimum: 0; maximum: 200; unit: "%" }
        AdjustRow { name: "blue"; label: "蓝"; minimum: 0; maximum: 200; unit: "%" }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          text: "偏色先调红 / 绿 / 蓝；背光只能比默认（10）更暗。右键滑块可单独重置。"
          color: win.dim
          font.family: win.fontFamily
          font.pixelSize: Style.font.caption
        }

        Button {
          text: "全部重置"
          bordered: true
          foreground: win.fg
          fontFamily: win.fontFamily
          onClicked: win.host.resetAdjust()
        }
      }
    }
  }

  // ---------------------------------------------------------- components

  // "亮度            110%" over a slider bound to one adjust.json setting.
  component AdjustRow: Column {
    id: row
    required property string name
    required property string label
    required property int minimum
    required property int maximum
    required property string unit
    readonly property int stored: win.host.adjust[name]
    width: parent ? parent.width : 0
    spacing: Style.space(6)

    Item {
      width: parent.width
      implicitHeight: rowLabel.implicitHeight

      Text {
        id: rowLabel
        textFormat: Text.PlainText
        text: row.label
        color: win.fg
        font.family: win.fontFamily
        font.pixelSize: Style.font.bodySmall
      }

      Text {
        anchors.right: parent.right
        textFormat: Text.PlainText
        text: Math.round(slider.liveValue) + row.unit
        color: Math.round(slider.liveValue) === win.host.adjustDefaults[row.name] ? win.dim : win.fg
        font.family: win.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
    }

    PanelSlider {
      id: slider
      width: parent.width
      minimum: row.minimum
      maximum: row.maximum
      step: 1
      integer: true
      value: row.stored
      trackColor: Util.alpha(win.fg, 0.18)
      fillColor: win.fg
      knobColor: win.fg
      tickColor: Color.background
      onMoved: function(v) { win.host.setAdjust(row.name, v) }
      onReleased: function(v) { win.host.setAdjust(row.name, v) }
      onRightClicked: win.host.setAdjust(row.name, win.host.adjustDefaults[row.name])
    }
  }

  // One ready/ image over its file name. The one on the panel gets the accent
  // border, the keyboard / hover cursor a foreground one.
  component Thumb: Item {
    id: thumb
    required property int index
    required property string fileName
    required property string filePath
    readonly property bool current: fileName === win.host.selected
    readonly property bool hot: index === grid.currentIndex
    width: grid.cellWidth
    height: grid.cellHeight

    Rectangle {
      id: frame
      width: win.thumbWidth
      height: win.thumbHeight
      radius: Style.cornerRadius
      color: "black"
      border.width: thumb.current ? Style.space(4) : (thumb.hot ? Style.space(2) : 1)
      border.color: thumb.current ? Color.imagePicker.selectedBorder
        : (thumb.hot ? win.fg : Color.imagePicker.unselectedBorder)

      Image {
        anchors.fill: parent
        anchors.margins: parent.border.width
        source: "file://" + thumb.filePath
        sourceSize: Qt.size(win.thumbWidth * 2, win.thumbHeight * 2)
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        cache: false
      }

      MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onEntered: grid.currentIndex = thumb.index
        onClicked: {
          grid.currentIndex = thumb.index
          grid.forceActiveFocus()
          win.host.pick(thumb.index)
        }
      }
    }

    Text {
      anchors.top: frame.bottom
      anchors.topMargin: Style.space(6)
      width: win.thumbWidth
      textFormat: Text.PlainText
      text: (thumb.current && win.host.rotating ? "▶ " : "") + thumb.fileName
      color: thumb.current ? win.fg : win.dim
      font.family: win.fontFamily
      font.pixelSize: Style.font.body
      font.bold: thumb.current
      elide: Text.ElideMiddle
      horizontalAlignment: Text.AlignHCenter
    }
  }
}
