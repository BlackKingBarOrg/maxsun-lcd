# maxsun-lcd

Linux 下驱动 MAXSUN 主板板载小屏（USB 0416:5021，412×960）的工具。协议细节全部在 `docs/protocol.md`，改动设备相关代码前先读。

## 往设备发命令的规则

- 已验证安全，可以直接用：`0x01` 握手、`0x0F` 清除叠加层、`0x0E` 实时 JPG、`0x07`/`0x08` 屏幕开关、`0x0C` 背光（1–10）。
- **不要发** `0x02`（固件升级 / 文件传输）、`0x03`/`0x04`（写屏幕闪存）、`0x0A`（恢复设备）。
- 其他命令（`0x10`、`0x11`、`0x09`、`0x0D`）还没在真机上测过，第一次发之前先问用户。

## 结构

后台服务（`maxsun-lcd daemon`，systemd 用户服务）独占设备。其他组件不直接碰设备：
- 顶部栏插件和 `maxsun-lcd select/slideshow/interval/adjust` 只写 `~/.local/state/maxsun-lcd/` 下的 `selected`、`slideshow.json` 和 `adjust.json`。轮播由服务来切换 `selected`。调色在服务发图时才处理；背光由服务用 0x0C 下发，重连后会重新应用。
- 服务把状态写到 `$XDG_RUNTIME_DIR/maxsun-lcd.json`，插件监听这个文件。

`maxsun-lcd status/test/show` 会直接打开设备，和后台服务同时用会互相干扰。

## 开发

- 用 uv；逆向脚本的依赖用 `uv sync --group re` 安装。
- 改完代码跑 `./install.sh`：它会重启后台服务；插件已经装好的话会执行 `omarchy restart shell`，因为 shell 的文件监听不跟进软链接，不重启看不到 `bar/` 的改动。
- 改顶部栏或 `~/.config/omarchy` 之前先加载 omarchy 技能。插件 QML 的报错用 `quickshell log -p /usr/share/omarchy/shell` 查看。
- 覆盖层是顶部栏组件自己建的 `PanelWindow`（layer-shell 的 Overlay 层），没有另做 overlay 类型的插件。原因是 shell 的 `summon` 遇到带 bar-widget 的插件时，只会转给顶部栏组件。
- 测试时不要往用户的 `~/Pictures/MaxsunLCD` 里放测试图，也不要改轮播设置：用户可能正在用。要测试就设置 `MAXSUN_LCD_ROOT` 和 `XDG_STATE_HOME`，指向临时目录，并且不要连接设备。也不要用 wtype 之类的模拟按键去操作覆盖层，用户可能正开着它。
- 启动顺序必须是 `0x01 → 0x0F → 0x0E…`；不先发 `0x0F`，固件留下的 `Loading...` 会一直盖在画面底部。
- `.cache/vendor/` 下是官方软件和解包文件（不进 git，也不被 Syncthing 同步）。`~/Work` 是 Syncthing 同步目录，大文件不要放到 `.cache/` 以外的地方。
