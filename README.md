# 网易云音乐播放器3.0 + 音效引擎V3

给你纯粹的网易云，大幅度减少性能开销

音效引擎与网易云均衡器音效相似度90%以上

会稳定更新，感兴趣的可以加star和watching

## 快速上手

### Termux
1. 首先下载[Termux](https://github.com/termux/termux-app/releases) ，找到符合您手机配置的apk文件（如果您的手机是在2020年以后购买的，那就选择带有arm64文件名的apk），下载并安装，接着打开应用，然后输入
```bash
termux-setup-storage
```
并回车(也就是换行)。执行后，系统会弹出一个权限请求，请点击“允许”来获取存储权限。

2. 下载文件v.py、effects.py、text.py，并通过文件管理器获取到这些文件所处的目录位置并复制它备用。在Termux输入：
```bash
cd+空格+复制的目录
```
然后回车。
> 注：文件所处的目录位置就是下载的文件所在的地方，比如：/storage/emulated/0/Download/

3. 在Termux中依次输入安装命令并回车运行：
```bash
# 换源
sed -i 's@^\(deb.*stable main\)$@#\1\ndeb https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main stable main@' $PREFIX/etc/apt/sources.list

# 更新库
pkg update && pkg upgrade

# 安装基础依赖
pkg install python python-pip ffmpeg mpv python-numpy python-scipy portaudio

# 安装构建工具和 C 编译器（可选，构建出现报错时可运行，但正常来讲不需要）
pkg install clang cmake make pkg-config

# 安装 Python 库
pip install requests urllib3 pydub rich readchar pyaudio

# 可选：安装歌曲封面查看工具
pkg install chafa
```

### Windows
```bash
# 安装 Python 并勾选 Add to PATH)

# 安装 Python 库
pip install requests urllib3 pydub numpy scipy rich readchar Pillow pyaudio

# 若在安装 pyaudio 时报错：
pip install pipwin
pipwin install pyaudio

# 手动下载并加入系统环境变量的系统工具：
MPV 播放器: 从 https://mpv.io/installation/ 下载 Windows 版本
- FFmpeg: 从 https://www.gyan.dev/ffmpeg/builds/ 下载 release full 版本
(必须将 mpv.exe 和 ffmpeg/bin 目录加入系统的 PATH 环境变量，否则无法播放和获取时长！)
```

### macOS
```bash
# 1. 使用 Homebrew 安装系统依赖
brew install python3 mpv ffmpeg portaudio chafa

# 2. 安装 Python 库
pip3 install requests urllib3 pydub numpy scipy rich readchar pyaudio Pillow
```

### Linux (Ubuntu/Debian)
```bash
# 1. 安装系统级依赖
sudo apt update
sudo apt install python3 python3-pip python3-numpy python3-scipy mpv ffmpeg chafa portaudio19-dev python3-pil -y

# 2. 安装 Python 库
pip3 install requests urllib3 pydub rich readchar pyaudio
```

## 运行程序

- 主程序
```bash
python v.py
```

## 文件说明

- **v.py** - 主播放器程序
- **effects.py** - 音效引擎模块
- **text.py** - VIP音乐播放所需模块
- **sound_effects_config.json** - 音效设置保存文件
- **playlists_cache.json** - 歌单存储文件
- **app_settings.json** - 设置状态记录文件


## 注意事项

1. 下载的三个文件必须处在同一目录

## 常见问题

1.`此程序有什么优势？`

我们做到了其他命令行播放器所没有的音效功能，整个程序占用存储、性能损耗极小，对低端设备友好，且文档简单易懂。

2.`我该怎么退出程序？`

在主页面ctrl+c并回车。

3.`歌单id在哪里获取？`

打开网易云音乐，找到你想要播放的歌单，点击分享，在弹框中点击复制链接，你会得到如：
> 分享歌单: Be infatuated with Dlmily https://music.163.com/m/playlist?id=12824371087&creatorId=2070898638

这样的链接。其中“12824371087”就是歌单id。

4.`为什么歌词出现的时间比歌手唱歌词的时间要快一点？`

这是低端设备中的硬件问题，在如骁龙400左右的机型情况比较明显，硬件稍好一些的机型几乎无感，目前不影响正常使用。

5.`为什么音乐刚开始播放后会卡顿一下？`

这是设备的硬件问题，当这种设备接入蓝牙播放音乐时情况明显，通常在如骁龙400左右或蓝牙性能较弱的设备发生，硬件好一些的设备不会出现这种情况

## 免责声明

　　本项目仅供个人学习、技术研究使用，严禁用于任何商业或非法用途。

　　项目调用了第三方公开API，这些接口并非本项目维护或控制，其稳定性、准确性及合法性由接口提供方负责。本项目仅作为技术演示调用，不分发任何来自这些接口的数据，未对目标服务器造成恶意压力，禁止高频请求或大规模抓取。若相关接口涉及版权内容或违反服务条款，请权利人直接联系接口提供方处理。

　　音效算法基于公开的 DSP 知识编写，不包含任何反编译、逆向工程代码。若涉及第三方专利技术特征，请使用者自行核实并承担相关责任。

　　本项目不提供任何音乐文件存储、分发功能，仅作为接口工具播放用户主动获取的网络链接。用户必须确保所播放的内容已获得合法授权，因播放受版权保护内容而产生的一切后果由用户本人承担。

　　使用即视为同意以上声明。开发者保留对此声明的最终解释权。

## 了解其他产品

[DL报刊论坛](https://dlbkltos.s7123.xyz/)

[番茄小说下载器精简版](https://github.com/Dlmily/Tomato-Novel-Downloader-Lite)

[小米手环七图像转换工具](https://github.com/Dlmily/ImageToMiBand7)

[绝区零般岳角色搓招攻略](https://github.com/Dlmily/zzz-Banyue-character-guide)

## 关于开源协议

　　本项目采用 **Mozilla Public License Version 2.0（MPL-2.0）** 开源协议。

　　您有权自由使用、修改及分发本软件及其源代码，但必须遵守以下核心条件：

　　**如果您修改了本项目中任何采用 MPL-2.0 许可的文件，则必须将这些修改后的文件以 MPL-2.0 协议开源；未修改的原文件及您新增的文件，可使用其他许可证（包括闭源）。**

　　这意味着，您可以在本项目基础上添加闭源的模块，只要保持 MPL 文件的修改部分透明即可。

　　详细条款请参阅根目录下的 LICENSE 文件。

## 关于版本号

版本号格式为：[大更新].[小更新].[修复更新]

## 未来发展

- [√]添加歌单导入功能
- [√]添加移动歌曲进度
- [√]添加更好的错误处理（因为清屏原因，错误信息也一并清除了）
- [√]实现列表播放/随机播放/单曲循环
- [√]修复返回时在主页面的输入没办法显示
- [√]修复重启终端音乐会继续播放
- [√]添加在歌曲播放页中不中断播放修改音效
- [√]预加载下一首，只有一首歌曲播放时除外
- [√]正确获取歌曲时长
- [√]添加歌单记忆功能
- [√]进一步适配小屏终端
- [√]添加上下一首切换
- [√]修复移动歌曲进度后，歌曲没有正确在相应进度播放
- [√]添加与其他应用同时播放
- [√]添加自动判断歌曲是否为vip切换对应的api进行音乐获取
- [√]添加更好的空间、混响音效
- 添加歌词在未停止音乐播放时可滑动查看功能
- 分页功能加入可输入特定页码跳转
- 添加对vip歌曲的免费播放（2026.5.16：已实现，但鉴于项目使用人数太少，所以暂时不更新）
- 添加播放时可进入歌单进行切换歌曲
- 优化准备歌曲资源时的重试逻辑
- 添加在搜索功能中加入特定歌曲加入歌单的功能

