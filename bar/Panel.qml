import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Bar button for the motherboard's onboard LCD (the maxsun-lcd daemon).
//
// Clicking it covers the screen it sits on with Overlay.qml: every
// panel-sized image in ready/, scrollable, plus the fixed/rotate switch and
// the rotation interval. Picking anything runs the `maxsun-lcd` CLI, which
// only writes the daemon's state files; the daemon does the work and reports
// back through $XDG_RUNTIME_DIR/maxsun-lcd.json, removed when it exits, so the
// button dims whenever the panel is not being driven.
// Right click opens the inbox folder.
// `omarchy-shell ai.bkblab.maxsun-lcd toggle` opens the overlay from a keybinding.
Panel {
  id: root
  moduleName: "ai.bkblab.maxsun-lcd"
  ipcTarget: "ai.bkblab.maxsun-lcd"

  // Not `state`: Item already has one.
  property var daemon: null

  readonly property bool running: daemon !== null
  readonly property bool connected: running && daemon.device === "connected"
  readonly property string selected: running ? daemon.selected : ""
  readonly property bool rotating: running && daemon.slideshow === true
  readonly property int interval: running && daemon.interval > 0 ? daemon.interval : 5
  // Colour correction + backlight (see `maxsun-lcd adjust --help`).
  readonly property var adjustDefaults: ({ backlight: 10, brightness: 100, contrast: 100, saturation: 100, hue: 0, red: 100, green: 100, blue: 100 })
  readonly property var adjust: running && daemon.adjust ? daemon.adjust : adjustDefaults
  readonly property string rootDir: Quickshell.env("HOME") + "/Pictures/MaxsunLCD"
  readonly property string inboxDir: running ? daemon.inbox : rootDir + "/inbox"
  readonly property string readyDir: running ? daemon.ready : rootDir + "/ready"
  property alias imageModel: images
  // The overlay opens on the monitor whose bar was clicked.
  readonly property var overlayScreen: button.QsWindow.window ? button.QsWindow.window.screen : null

  readonly property string statusText: {
    if (!running) return "后台服务没有运行"
    if (daemon.device === "connected") {
      if (selected === "") return "还没有选图片"
      return (rotating ? "轮播中 · " : "固定显示 · ") + selected
    }
    if (daemon.device === "missing") return "没找到屏幕（USB 0416:5021）"
    if (daemon.device === "no-permission") return "没有权限访问屏幕，需要安装 udev 规则"
    return "屏幕出错：" + (daemon.error || "未知原因")
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  FileView {
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/maxsun-lcd.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        root.daemon = JSON.parse(String(text() || ""))
      } catch (e) {
        root.daemon = null
      }
    }
    onLoadFailed: root.daemon = null
  }

  // Newest first; the daemon's slideshow walks ready/ in the same order.
  FolderListModel {
    id: images
    folder: "file://" + root.readyDir
    nameFilters: ["*.png", "*.jpg", "*.jpeg"]
    showDirs: false
    sortField: FolderListModel.Time
  }

  function indexOf(name) {
    for (var i = 0; i < images.count; i++)
      if (images.get(i, "fileName") === name) return i
    return -1
  }

  function pick(index) {
    var name = images.get(index, "fileName")
    if (name) Quickshell.execDetached(["maxsun-lcd", "select", name])
  }

  function setRotating(on) {
    Quickshell.execDetached(["maxsun-lcd", "slideshow", on ? "on" : "off"])
  }

  function setInterval(seconds) {
    if (seconds >= 1) Quickshell.execDetached(["maxsun-lcd", "interval", String(seconds)])
  }

  function openInbox() {
    Quickshell.execDetached(["xdg-open", root.inboxDir])
  }

  // Slider drags arrive many times a second; batch them so one CLI call
  // carries everything that changed in the last 120 ms.
  property var pendingAdjust: ({})

  function setAdjust(name, value) {
    var next = {}
    for (var k in pendingAdjust) next[k] = pendingAdjust[k]
    next[name] = Math.round(value)
    pendingAdjust = next
    adjustFlush.restart()
  }

  function resetAdjust() {
    adjustFlush.stop()
    pendingAdjust = {}
    Quickshell.execDetached(["maxsun-lcd", "adjust", "reset"])
  }

  Timer {
    id: adjustFlush
    interval: 120
    onTriggered: {
      var args = ["maxsun-lcd", "adjust"]
      for (var k in root.pendingAdjust) args.push(k, String(root.pendingAdjust[k]))
      root.pendingAdjust = {}
      if (args.length > 2) Quickshell.execDetached(args)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰋩"
    dimmed: !root.connected
    tooltipText: ""
    onPressed: function(b) {
      if (b === Qt.RightButton) root.openInbox()
      else root.toggle()
    }
  }

  Overlay {
    host: root
  }
}
