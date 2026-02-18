# 网易云音乐播放器 + 音效引擎V7

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

2. 下载文件v.py、effects.py，并通过文件管理器获取到这个文件所处的目录位置并复制它备用。在Termux输入：
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
pkg install python python-pip ffmpeg mpv

# 安卓编译优化库
pkg install tur-repo && pkg install python-cryptography

# 安装 X11 仓库（提供 Chromium 运行所需的底层库）
pkg install x11-repo

# 安装Chromium和ChromeDriver
pkg install chromium chromedriver

# 安装Python库
pip install selenium requests pydub numpy scipy rich readchar

# 安装图片查看工具
pkg install chafa
```

### Windows
```bash
# 1. 安装Python库
pip install selenium requests pydub numpy scipy rich readchar

# 2. 安装MPV播放器
# 从 https://mpv.io/installation/ 下载并安装

# 3. 安装Chrome和ChromeDriver
# Chrome: https://www.google.com/chrome/
# ChromeDriver: https://chromedriver.chromium.org/

# 4. 设置环境变量
# 将ChromeDriver路径添加到系统PATH
```

### macOS
```bash
# 使用Homebrew安装依赖
brew install python3 mpv chromedriver

# 安装Python库
pip3 install selenium requests pydub numpy scipy rich readchar

# 安装Chrome
brew install --cask google-chrome
```

### Linux (Ubuntu/Debian)
```bash
# 安装系统依赖
sudo apt update
sudo apt install python3-pip mpv chromium-chromedriver chafa -y

# 安装Python库
pip3 install selenium requests pydub numpy scipy rich readchar
```

## 运行程序

- 主程序
```bash
python v.py
```

## 文件说明

- **v.py** - 主播放器程序
- **effects.py** - 音效引擎模块
- **sound_effects_config.json** - 音效设置保存文件（自动生成）

## 注意事项

1. **Windows用户**需要手动配置ChromeDriver路径

## 常见问题

1.`此程序有什么优势？`

我们做到了其他命令行播放器所没有的音效功能，整个程序占用存储极小，对低端设备友好，且文档简单易懂。

2.`我该怎么退出程序？`

在主页面ctrl+c并回车。

3.`歌单id在哪里获取？`

打开网易云音乐，找到你想要播放的歌单，点击分享，在弹框中点击复制链接，你会得到如：
> 分享歌单: Be infatuated with Dlmily https://music.163.com/m/playlist?id=12824371087&creatorId=2070898638
这样的链接，其中“12824371087”就是歌单id。


## 免责声明

　　本项目（网易云音乐播放器 + 音效引擎）仅供个人学习、技术研究使用，严禁用于任何商业或非法用途。

　　项目中的搜索功能通过模拟浏览器访问公开网页获取信息，未对目标服务器造成恶意压力。使用者应遵守相关网站的使用协议及法律法规，禁止高频请求或大规模抓取。因使用本软件导致的任何访问限制、法律纠纷由使用者自行承担。

　　项目调用了第三方公开API，这些接口并非本项目维护或控制，其稳定性、准确性及合法性由接口提供方负责。本项目仅作为技术演示调用，不存储、缓存或分发任何来自这些接口的数据，未对目标服务器造成恶意压力，禁止高频请求或大规模抓取。若相关接口涉及版权内容或违反服务条款，请权利人直接联系接口提供方处理。

　　代码中的音效预设名称（如“鲸云空间”“沉浸环绕”等）仅用于描述听感风格，与任何商业音效品牌或产品无关。音效算法基于公开的 DSP 知识编写，不包含任何反编译、逆向工程代码。若涉及第三方专利技术特征，请使用者自行核实并承担相关责任。

　　本软件不提供任何音乐文件存储、分发功能，仅作为接口工具播放用户主动获取的网络链接。用户必须确保所播放的内容已获得合法授权，因播放受版权保护内容而产生的一切后果由用户本人承担。

　　使用即视为同意以上声明。开发者保留对此声明的最终解释权。

## 了解其他产品

[DL报刊论坛](https://dlbkltos.s7123.xyz/)

[番茄小说下载器精简版](https://github.com/Dlmily/Tomato-Novel-Downloader-Lite)

[小米手环七图像转换工具](https://github.com/Dlmily/ImageToMiBand7)

## 关于开源协议

　　本项目采用 **GNU General Public License v3.0（GPL-3.0）** 开源协议。

　　您有权自由使用、修改及分发本软件及其源代码，但必须遵守以下核心条件：

　　**任何形式的公开发布或分发，包括修改后的衍生版本，都必须完整开源，并继续采用 GPL-3.0 协议。**

　　这意味着任何人不得将本软件或其中部分代码用于闭源商业产品或服务。

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
- 修复移动歌曲进度后，歌曲没有正确在相应进度播放
- 分页功能加入可输入特定页码跳转
- 添加与其他应用同时播放
- 添加歌词下一句渐显
- 添加歌词分页，每页显示11个歌词，暂停时可进行上一页下一页操作，可设置每页显示的歌词数
- 修复移动歌曲进度后，歌曲没有正确在相应进度播放，而是又重新从开头播放
- 添加音量平衡
