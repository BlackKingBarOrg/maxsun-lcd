# maxsun-lcd

在 Linux 下驱动 MAXSUN iCraft Z890 Pacific 主板上的 3.4 英寸小屏（USB `0416:5021`）。
官方只提供 Windows 软件（MAXSUN VIEW）；这里用的协议是逆向官方软件和屏幕固件得到的，详见 [docs/protocol.md](docs/protocol.md)。

## 使用

把图片放进 `~/Pictures/MaxsunLCD/inbox/`，后台服务会自动把它居中裁切、缩放成 412×960，存到 `~/Pictures/MaxsunLCD/ready/`。

点顶部栏的 󰋩 图标，会在当前屏幕上打开一个全屏覆盖层：
- 所有图片按缩略图网格排列，可以用滚轮、拖动或键盘滚动；点一张就显示到小屏上。
- 右上角可以切换"固定这一张"或"轮播"，"间隔（秒）"默认 5 秒，最小 1 秒，可以手动输入，最长一天。
- 点 󰏘（或按 `c`）在右侧打开调色面板：背光（屏幕硬件，1–10）、亮度、对比度、饱和度、色相、红 / 绿 / 蓝增益。拖动时小屏实时刷新；右键滑块单独重置，或者点"全部重置"。调色只在发往屏幕时生效，不修改 `ready/` 里的图片。
- 键盘：方向键或 hjkl 移动，回车显示，`s` 切换固定 / 轮播，`c` 打开 / 收起调色面板，`o` 打开图片文件夹，Esc 关闭。
- 点边缘空白处也会关闭；右键顶部栏图标直接打开图片文件夹。

其他行为：
- 第一次有图片进来、还没选过图的时候，会自动显示这张。
- 轮播顺序和网格一致（最新的在前），循环播放；轮播中点某一张，就从那张接着播。
- 当前选择记在 `~/.local/state/maxsun-lcd/selected`，轮播设置记在同一目录的 `slideshow.json`，重启后都会保留。
- 插拔、休眠唤醒之后，屏幕会退回待机画面，服务会在 5 秒内自动重新接管。
- 换一个图片目录：给服务设置环境变量 `MAXSUN_LCD_ROOT`。

```sh
./install.sh                    # 安装或重载：命令行、systemd 用户服务、顶部栏插件
maxsun-lcd select foo.png       # 命令行切换显示的图片（文件名在 ready/ 里）
maxsun-lcd slideshow on|off     # 轮播 / 固定
maxsun-lcd interval 5           # 轮播间隔（秒，至少 1）
maxsun-lcd adjust               # 查看调色设置；adjust blue 90 contrast 110 设置；adjust reset 恢复默认
journalctl --user -u maxsun-lcd -f
```

调试用的命令会直接操作设备、绕过后台服务，用之前先 `systemctl --user stop maxsun-lcd`：

```sh
maxsun-lcd status               # 握手，打印设备状态包
maxsun-lcd test                 # 显示箭头测试图
maxsun-lcd show a.png           # 直接显示一张图片
```

## 权限

屏幕的 hidraw 节点默认只有 root 能读写。安装 udev 规则，让当前登录的用户可以访问：

```sh
sudo cp udev/70-maxsun-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

## 目录

- `src/maxsun_lcd/device.py`：协议实现（握手、清除叠加层、推送实时 JPG）
- `src/maxsun_lcd/library.py`：图片目录、裁切缩放、当前选择
- `src/maxsun_lcd/daemon.py`：后台服务（监听 inbox、保持屏幕显示、写 `$XDG_RUNTIME_DIR/maxsun-lcd.json` 状态）
- `bar/`：顶部栏插件 `ai.bkblab.maxsun-lcd`，软链接到 `~/.config/omarchy/plugins/`；`Panel.qml` 是按钮和状态，`Overlay.qml` 是全屏覆盖层
- `systemd/`：用户服务单元，软链接到 `~/.config/systemd/user/`
- `docs/protocol.md`：协议、固件和官方软件的逆向笔记
- `udev/`：权限规则
- `tools/re/`：逆向辅助脚本，依赖用 `uv sync --group re` 安装
- `.cache/vendor/`：官方软件和解包文件的本地副本，不进 git，也不参与同步
