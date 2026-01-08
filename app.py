# app.py
import threading
import queue
import json
import time
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入重构后的模块
from modules.utils import sanitize_filename
from modules.downloader import MusicDownloader, parse_music_source
from modules.sorter import MusicSorter

# --- 应用配置 ---
MAX_WORKERS = 4
app = Flask(__name__, template_folder='templates', static_folder='static')

class DownloadManager:
    """封装下载任务的状态和逻辑，解决全局变量问题。"""
    def __init__(self):
        self.is_downloading = False
        self.thread = None
        self.message_queue = queue.Queue()
        self.failed_songs = []
        self.current_playlist_dir = None
        self.stop_event = threading.Event()

    def _put_message(self, msg_type, **kwargs):
        """向前端推送消息。"""
        kwargs['type'] = msg_type
        self.message_queue.put(kwargs)

    def start_download(self, **kwargs):
        if self.is_downloading:
            return False, "已有下载任务在进行中"
        
        self.is_downloading = True
        self.failed_songs.clear()
        self.stop_event.clear()
        
        self.thread = threading.Thread(target=self._download_task, kwargs=kwargs, daemon=True)
        self.thread.start()
        return True, "下载任务已启动"

    def retry_download(self, **kwargs):
        if self.is_downloading:
            return False, "已有下载任务在进行中"
        
        self.is_downloading = True
        self.stop_event.clear() # 重置停止事件
        
        # 重新下载时，失败列表应基于传入的 song_ids，并在任务开始时清空
        self.failed_songs.clear()
        
        self.thread = threading.Thread(target=self._retry_task, kwargs=kwargs, daemon=True)
        self.thread.start()
        return True, "重新下载任务已启动"

    def stop_download(self):
        if not self.is_downloading:
            return False, "没有正在进行的下载任务"
        
        self.stop_event.set()
        self._put_message('log', message="用户请求停止下载...")
        return True, "停止信号已发送"

    def _download_task(self, save_dir, playlist_url, parse_type, quality, dl_lyrics, dl_lyrics_translated, api):
        """后台下载线程执行的实际任务。"""
        try:
            self._put_message('log', message=f"正在解析链接...")
            playlist_data = parse_music_source(parse_type, playlist_url)
            tracks = playlist_data.get('tracks', [])
            
            # 确定并创建保存目录
            base_save_path = Path(save_dir)
            subfolder_map = {'playlist': 'playlist', 'album': 'album', 'link': 'songs'}
            subfolder = subfolder_map.get(parse_type, 'misc')
            
            playlist_title = sanitize_filename(playlist_data.get('name') or f"unnamed_{int(time.time())}")
            
            if parse_type == 'link':
                playlist_save_dir = base_save_path / subfolder
            else:
                playlist_save_dir = base_save_path / subfolder / playlist_title
            
            playlist_save_dir.mkdir(parents=True, exist_ok=True)
            self.current_playlist_dir = str(playlist_save_dir)

            self._put_message('log', message=f"歌曲将保存到: {self.current_playlist_dir}")
            self._put_message('log', message=f"使用API: {api}, 音质: {quality}")
            self._put_message('log', message=f"共找到 {len(tracks)} 首歌曲，开始下载...")
            
            downloader = MusicDownloader(self.current_playlist_dir, quality, api)
            self._execute_downloads(downloader, tracks, dl_lyrics, dl_lyrics_translated, api)
            
            # 任务结束后，保存歌单信息文件
            if parse_type != 'link' and (len(tracks) - len(self.failed_songs)) > 0:
                json_path = playlist_save_dir / f"{playlist_title}.json"
                json_path.write_text(json.dumps(playlist_data, ensure_ascii=False, indent=4), encoding='utf-8')
                self._put_message('log', message=f"✓ 歌单信息文件已保存: {json_path.name}")

        except Exception as e:
            error_msg = f"下载过程中出现严重错误: {e}"
            self._put_message('log', message=error_msg)
            self._put_message('error', message=error_msg)
        finally:
            self.is_downloading = False

    def _retry_task(self, playlist_dir, song_ids, quality, dl_lyrics, dl_lyrics_translated, api):
        """后台重新下载任务。"""
        try:
            self.current_playlist_dir = playlist_dir
            self._put_message('log', message=f"开始重新下载 {len(song_ids)} 首歌曲...")
            self._put_message('log', message=f"将保存到: {playlist_dir}")
            
            downloader = MusicDownloader(playlist_dir, quality, api)
            
            # 将 song_ids 转换为 tracks 格式以复用执行逻辑
            tracks = [{'id': song_id} for song_id in song_ids]
            self._execute_downloads(downloader, tracks, dl_lyrics, dl_lyrics_translated, api)

        except Exception as e:
            error_msg = f"重新下载过程中出现严重错误: {e}"
            self._put_message('log', message=error_msg)
            self._put_message('error', message=error_msg)
        finally:
            self.is_downloading = False

    def _execute_downloads(self, downloader, tracks, dl_lyrics, dl_lyrics_translated, api):
        """统一的下载执行逻辑，支持多线程和停止。"""
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_track = {
                executor.submit(
                    downloader.download_song, str(track['id']), dl_lyrics, api, track, dl_lyrics_translated
                ): track for track in tracks
            }
            
            total = len(tracks)
            for i, future in enumerate(as_completed(future_to_track), 1):
                if self.stop_event.is_set():
                    # 取消所有未完成的 future
                    for f in future_to_track: f.cancel()
                    break
                
                track = future_to_track[future]
                try:
                    status, filename, song_id = future.result()
                    results.append({'status': status, 'song_id': song_id})
                    if status == "downloaded":
                        self._put_message('log', message=f"✓ 下载成功: {filename}")
                    elif status == "skipped":
                        self._put_message('log', message=f"→ 已跳过: {filename}")
                    else:
                        self.failed_songs.append(str(song_id))
                        self._put_message('log', message=f"✗ 下载失败: ID {song_id}")
                except Exception as exc:
                    song_id = str(track['id'])
                    self.failed_songs.append(song_id)
                    results.append({'status': 'failed', 'song_id': song_id})
                    self._put_message('log', message=f"✗ 处理歌曲 {song_id} 时出错: {exc}")
                
                self._put_message('progress', progress=(i / total) * 100, status_text=f"进度: {i}/{total}")
        
        # 任务结束总结
        success_count = sum(1 for r in results if r['status'] in ['downloaded', 'skipped'])
        failed_count = len(self.failed_songs)
        
        if self.stop_event.is_set():
            msg = f"下载已停止。成功: {success_count}，失败: {failed_count}"
            self._put_message('stopped', message=msg, has_failed=(failed_count > 0), failed_count=failed_count, success_count=success_count)
        else:
            msg = f"任务完成！成功: {success_count}，失败: {failed_count}"
            self._put_message('done', message=msg, has_failed=(failed_count > 0), failed_count=failed_count, success_count=success_count)

# 创建 DownloadManager 的单一实例
manager = DownloadManager()

# --- Flask 路由 ---
@app.route('/')
def index():
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe文件，sys.executable 指向当前的 .exe 文件
        app_base_path = Path(sys.executable).parent
    else:
        # 否则是未打包的Python脚本，__file__ 指向脚本文件
        app_base_path = Path(__file__).parent
    default_music_dir = str(app_base_path / 'Music')
    return render_template('index.html', default_music_dir=default_music_dir)

@app.route('/start-download', methods=['POST'])
def start_download_route():
    data = request.form
    success, message = manager.start_download(
        save_dir=data.get('save_dir'),
        playlist_url=data.get('playlist_url'),
        parse_type=data.get('parse_method', 'playlist'),
        quality=data.get('quality', 'exhigh'),
        dl_lyrics=data.get('download_lyrics_original') == 'true',
        dl_lyrics_translated=data.get('download_lyrics_translated') == 'true',
        api=data.get('download_api', 'suxiaoqing')
    )
    return jsonify({'status': 'success' if success else 'error', 'message': message})

@app.route('/retry-failed-songs', methods=['POST'])
def retry_failed_songs_route():
    data = request.json
    song_ids = manager.failed_songs[:] # 复制列表以防万一
    
    # 重新下载时，使用上一次的歌单目录
    playlist_dir = manager.current_playlist_dir
    if not playlist_dir or not Path(playlist_dir).exists():
        return jsonify({'status': 'error', 'message': '无法确定上次的歌单目录，请重新进行一次完整下载'})

    success, message = manager.retry_download(
        playlist_dir=playlist_dir,
        song_ids=song_ids,
        quality=data.get('quality', 'exhigh'),
        dl_lyrics=data.get('download_lyrics', True),
        dl_lyrics_translated=data.get('download_lyrics_translated', False),
        api=data.get('download_api', 'suxiaoqing')
    )
    return jsonify({'status': 'success' if success else 'error', 'message': message})

@app.route('/stop-download', methods=['POST'])
def stop_download_route():
    success, message = manager.stop_download()
    return jsonify({'status': 'success' if success else 'error', 'message': message})

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            try:
                message = manager.message_queue.get(timeout=30)
                yield f"data: {json.dumps(message)}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/get-failed-songs')
def get_failed_songs():
    return jsonify({'failed_songs': manager.failed_songs})

# --- 歌单排序相关 API ---
def _find_playlist_path(base_dir, playlist_name):
    """辅助函数，在 'playlist' 和 'album' 子目录中查找歌单路径。"""
    base_path = Path(base_dir)
    for subfolder in ['playlist', 'album']:
        path = base_path / subfolder / playlist_name
        if path.is_dir():
            return path
    return None

@app.route('/get-playlists')
def get_playlists():
    path = request.args.get('path')
    if not path or not Path(path).is_dir():
        return jsonify({'playlists': [], 'message': '目录不存在或无效'}), 400
    
    playlist_info = []
    base_path = Path(path)
    sorter = MusicSorter()
    
    for type_name, subfolder in [('playlist', 'playlist'), ('album', 'album')]:
        dir_path = base_path / subfolder
        if dir_path.is_dir():
            playlists = sorter.get_playlists(str(dir_path))
            playlist_info.extend([{'name': p, 'type': type_name} for p in playlists])
            
    return jsonify({'playlists': playlist_info})

@app.route('/get-playlist-id')
def get_playlist_id_route():
    path = request.args.get('path')
    playlist_name = request.args.get('playlist')
    playlist_dir = _find_playlist_path(path, playlist_name)
    
    if not playlist_dir:
        return jsonify({'message': '未找到歌单目录'}), 404
        
    # 查找JSON文件
    json_files = list(playlist_dir.glob('*.json'))
    if not json_files:
        return jsonify({'message': '未找到歌单JSON文件'}), 404
    
    try:
        playlist_data = json.loads(json_files[0].read_text(encoding='utf-8'))
        playlist_id = playlist_data.get('id')
        if not playlist_id:
            return jsonify({'message': 'JSON文件中没有ID字段'}), 404
        return jsonify({'playlist_id': str(playlist_id)})
    except Exception as e:
        return jsonify({'message': f'读取JSON文件失败: {e}'}), 500

@app.route('/sort-playlist', methods=['POST'])
def sort_playlist_route():
    data = request.json
    base_dir = data.get('base_dir')
    playlist_name = data.get('playlist_name')
    start_number = data.get('start_number', 500)
    
    if not all([base_dir, playlist_name]):
        return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400

    try:
        sorter = MusicSorter()
        # 尝试在playlist和album文件夹中查找
        base_path = Path(base_dir)
        playlist_dir = None
        
        # 先尝试playlist文件夹
        playlist_path = base_path / 'playlist' / playlist_name
        if playlist_path.exists() and playlist_path.is_dir():
            playlist_dir = playlist_path
        else:
            # 再尝试album文件夹
            album_path = base_path / 'album' / playlist_name
            if album_path.exists() and album_path.is_dir():
                playlist_dir = album_path
        
        if not playlist_dir:
            return jsonify({'status': 'error', 'message': f"未找到歌单目录: {playlist_name}"}), 404
        
        # 查找JSON文件（可能文件名不完全匹配）
        json_files = list(playlist_dir.glob('*.json'))
        if not json_files:
            return jsonify({'status': 'error', 'message': f"未找到歌单JSON文件"}), 404
        json_file = json_files[0]  # 使用找到的第一个JSON文件
        
        with open(json_file, 'r', encoding='utf-8') as f:
            playlist_data = json.load(f)
        
        tracks = playlist_data.get('tracks', [])
        processed_count = sorter.sort_playlist(str(playlist_dir), tracks, start_number)
        
        return jsonify({'status': 'success', 'message': f"排序完成！共处理 {processed_count} 首歌曲。"})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'排序失败: {e}'}), 500


@app.route('/remove-numbering', methods=['POST'])
def remove_numbering_route():
    data = request.json
    base_dir = data.get('base_dir')
    playlist_name = data.get('playlist_name')

    if not all([base_dir, playlist_name]):
        return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400

    try:
        sorter = MusicSorter()
        # 尝试在playlist和album文件夹中查找
        base_path = Path(base_dir)
        playlist_dir = None
        
        # 先尝试playlist文件夹
        playlist_path = base_path / 'playlist' / playlist_name
        if playlist_path.exists() and playlist_path.is_dir():
            playlist_dir = playlist_path
        else:
            # 再尝试album文件夹
            album_path = base_path / 'album' / playlist_name
            if album_path.exists() and album_path.is_dir():
                playlist_dir = album_path
        
        if not playlist_dir:
            return jsonify({'status': 'error', 'message': f"未找到歌单目录: {playlist_name}"}), 404
        
        processed_count = sorter.remove_numbers(str(playlist_dir))
        
        return jsonify({'status': 'success', 'message': f"编号移除完成！共处理 {processed_count} 个文件。"})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'移除编号失败: {e}'}), 500

if __name__ == '__main__':
    app.run(debug=True, threaded=True)