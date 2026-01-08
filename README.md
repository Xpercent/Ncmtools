# NCM Tools - 网易云音乐下载工具

一个基于 Flask 的网易云音乐下载工具，支持下载歌单、专辑和单曲，并提供歌单排序功能。

## 功能特性

- 🎵 支持下载歌单、专辑、单曲
- 🎨 自动嵌入音频元数据和封面
- 📝 支持下载歌词（原文/翻译）
- 🔄 多下载API源（suxiaoqing、ss22y、vkeys、kxzjoker）
- 📊 歌单排序和编号管理
- 🌐 Web 界面操作

## 项目结构

```
ncmtools/
├── app.py                 # Flask 主应用
├── modules/
│   ├── downloader.py      # 下载器模块
│   ├── sorter.py          # 歌单排序模块
│   ├── Lyrics.py          # 歌词处理模块
│   └── utils.py           # 工具函数
├── templates/
│   └── index.html         # 前端页面
├── static/                # 静态资源
└── requirements.txt       # 依赖列表
```

## 安装
```bash
pip install -r requirements.txt
```

## 运行
```bash
python app.py
```

## 打包
```bash
pyinstaller --add-data "templates;templates" --add-data "static;static" app.py
```

访问 `http://localhost:5000` 使用 Web 界面。

## API 接口

### 下载相关

- `POST /start-download` - 开始下载任务
- `POST /retry-failed-songs` - 重试失败的歌曲
- `POST /stop-download` - 停止下载
- `GET /stream` - 获取下载进度（SSE）
- `GET /get-failed-songs` - 获取失败歌曲列表

### 歌单操作

- `GET /get-playlists` - 获取歌单列表
- `GET /get-playlist-id` - 获取歌单ID
- `POST /sort-playlist` - 排序歌单
- `POST /remove-numbering` - 移除文件名编号
