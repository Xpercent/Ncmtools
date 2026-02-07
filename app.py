# app.py
import threading
import queue
import json
import time
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入自定义模块
from modules.utils import sanitize_filename
from modules.downloader import MusicDownloader, parse_music_source
from modules.sorter import MusicSorter

# --- 配置 ---
MAX_WORKERS = 8
app = Flask(__name__, template_folder='templates', static_folder='static')

class DownloadManager:
    """管理下载任务的状态和线程"""
    def __init__(self):
        self.is_downloading = False
        self.thread = None
        self.message_queue = queue.Queue()
        self.failed_songs = [] 
        self.current_playlist_dir = None
        self.stop_event = threading.Event()

    def _emit(self, msg_type, **kwargs):
        kwargs['type'] = msg_type
        self.message_queue.put(kwargs)

    def start_task(self, **kwargs):
        if self.is_downloading:
            return False, "已有任务在运行中"
        
        self.is_downloading = True
        self.failed_songs.clear()
        self.stop_event.clear()
        
        self.thread = threading.Thread(target=self._run_new_download, kwargs=kwargs, daemon=True)
        self.thread.start()
        return True, "下载任务已启动"

    def retry_task(self, **kwargs):
        if self.is_downloading:
            return False, "已有任务在运行中"
        if not self.current_playlist_dir:
            return False, "无法找到上次下载目录"
            
        self.is_downloading = True
        self.stop_event.clear()
        self.failed_songs.clear()
        
        kwargs['playlist_dir'] = self.current_playlist_dir
        self.thread = threading.Thread(target=self._run_retry_download, kwargs=kwargs, daemon=True)
        self.thread.start()
        return True, "重试任务已启动"

    def stop(self):
        if not self.is_downloading:
            return False, "当前无任务运行"
        self.stop_event.set()
        self._emit('log', message="正在请求停止下载...")
        return True, "停止信号已发送"

    # --- 内部逻辑 ---

    def _run_new_download(self, save_dir, playlist_url, parse_type, quality, dl_lyrics, dl_trans, api):
        try:
            self._emit('log', message="正在解析链接信息...")
            data = parse_music_source(parse_type, playlist_url)
            
            # --- 关键重构点：识别数据结构 ---
            base = Path(save_dir)
            if 'tracks' in data:
                # 歌单/专辑模式
                tracks = data['tracks']
                pl_name = sanitize_filename(data.get('name') or f"PL_{int(time.time())}")
                sub = 'album' if parse_type == 'album' else 'playlist'
                dest_dir = base / sub / pl_name
            else:
                # 单曲模式：data 只有 {'id': 'xxx'}
                tracks = [data] # 包装成列表方便循环，但字典里没 name
                dest_dir = base / 'songs'
            
            dest_dir.mkdir(parents=True, exist_ok=True)
            self.current_playlist_dir = str(dest_dir)
            
            self._emit('log', message=f"保存目录: {dest_dir.name}")
            self._emit('log', message=f"解析成功: 共 {len(tracks)} 首歌曲")

            self._process_common_download(dest_dir, tracks, quality, dl_lyrics, dl_trans, api)
            
            # 如果是歌单，保存一下 JSON 供后续排序使用
            if 'tracks' in data and not self.stop_event.is_set():
                (dest_dir / f"{pl_name}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=4), encoding='utf-8'
                )

        except Exception as e:
            self._emit('error', message=f"下载任务出错: {e}")
        finally:
            self.is_downloading = False

    def _run_retry_download(self, playlist_dir, songs_to_retry, quality, dl_lyrics, dl_trans, api):
        try:
            self._emit('log', message=f"开始重试下载 {len(songs_to_retry)} 首歌曲...")
            self._process_common_download(Path(playlist_dir), songs_to_retry, quality, dl_lyrics, dl_trans, api)
        except Exception as e:
            self._emit('error', message=f"重试任务出错: {e}")
        finally:
            self.is_downloading = False

    def _process_common_download(self, dest_dir, tracks, quality, dl_lyrics, dl_trans, api):
        downloader = MusicDownloader(dest_dir, quality, api)
        total = len(tracks)
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {}
            for t in tracks:
                # 只有当字典里有 'name' 时，才认为元数据完整
                # 如果没有 'name'（如单曲模式），则传 None，强制 downloader 去调 API 获取详情
                track_info_param = t if 'name' in t else None
                
                future = executor.submit(
                    downloader.download_song, 
                    str(t['id']), 
                    dl_lyrics, 
                    api, 
                    track_info_param, 
                    dl_trans
                )
                future_map[future] = t
            
            for i, future in enumerate(as_completed(future_map), 1):
                if self.stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                original_track = future_map[future]
                try:
                    status, fname, sid = future.result()
                    
                    # 确定显示用的名称
                    if fname:
                        log_name = fname
                    elif 'name' in original_track:
                        log_name = f"{original_track['name']} - {original_track.get('ar', 'Unknown')}"
                    else:
                        log_name = f"ID: {sid}"

                    if status == 'failed':
                        # 记录失败时，如果原数据不全，尝试更新（便于前端显示）
                        self.failed_songs.append(original_track)
                        self._emit('log', message=f"✗ 下载失败: {log_name}")
                    else:
                        icon = "✓" if status == 'downloaded' else "→"
                        self._emit('log', message=f"{icon} {status}: {log_name}")
                    
                    results.append(status)
                    
                except Exception as e:
                    self.failed_songs.append(original_track)
                    self._emit('log', message=f"✗ 线程异常: {e}")

                self._emit('progress', progress=(i / total) * 100, status_text=f"进度: {i}/{total}")

        success_cnt = results.count('downloaded') + results.count('skipped')
        fail_cnt = len(self.failed_songs)
        evt = 'stopped' if self.stop_event.is_set() else 'done'
        msg = f"任务{'停止' if evt=='stopped' else '完成'}。成功: {success_cnt}, 失败: {fail_cnt}"
        
        self._emit(evt, message=msg, has_failed=(fail_cnt > 0), 
                   failed_count=fail_cnt, success_count=success_cnt)

manager = DownloadManager()

# --- 辅助工具函数 ---

def find_target_directory(base_dir, folder_name):
    base = Path(base_dir)
    for sub in ['playlist', 'album']:
        path = base / sub / folder_name
        if path.is_dir():
            return path
    return None

# --- Flask 路由 ---

@app.route('/')
def index():
    if getattr(sys, 'frozen', False):
        app_base = Path(sys.executable).parent
    else:
        app_base = Path(__file__).parent
    default_dir = app_base / 'Music'
    return render_template('index.html', default_music_dir=str(default_dir))

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            try:
                message = manager.message_queue.get(timeout=20)
                yield f"data: {json.dumps(message)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/start-download', methods=['POST'])
def start_download_route():
    data = request.form
    success, msg = manager.start_task(
        save_dir=data.get('save_dir'),
        playlist_url=data.get('playlist_url'),
        parse_type=data.get('parse_method', 'playlist'),
        quality=data.get('quality', 'exhigh'),
        dl_lyrics=data.get('download_lyrics_original') == 'true',
        dl_trans=data.get('download_lyrics_translated') == 'true',
        api=data.get('download_api', 'vkeys')
    )
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/retry-failed-songs', methods=['POST'])
def retry_failed_songs_route():
    data = request.json
    songs = data.get('songs') or manager.failed_songs
    
    if not songs:
        return jsonify({'status': 'error', 'message': '没有需要重试的歌曲'})

    success, msg = manager.retry_task(
        songs_to_retry=list(songs),
        quality=data.get('quality', 'exhigh'),
        dl_lyrics=data.get('download_lyrics', True),
        dl_trans=data.get('download_lyrics_translated', False),
        api=data.get('download_api', 'vkeys')
    )
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/stop-download', methods=['POST'])
def stop_download_route():
    success, msg = manager.stop()
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/get-failed-songs')
def get_failed_songs():
    return jsonify({'failed_songs': list(manager.failed_songs)})

@app.route('/get-playlists')
def get_playlists():
    path = request.args.get('path')
    if not path or not Path(path).exists():
        return jsonify({'playlists': [], 'message': '目录无效'}), 400
    
    results = []
    base_path = Path(path)
    sorter = MusicSorter()
    
    for type_name in ['playlist', 'album']:
        target_dir = base_path / type_name
        if target_dir.is_dir():
            try:
                names = sorter.get_playlists(str(target_dir))
                results.extend([{'name': n, 'type': type_name} for n in names])
            except Exception:
                pass
    return jsonify({'playlists': results})

@app.route('/get-playlist-id')
def get_playlist_id_route():
    base_dir = request.args.get('path')
    pl_name = request.args.get('playlist')
    target_dir = find_target_directory(base_dir, pl_name)
    if not target_dir:
        return jsonify({'message': '未找到歌单目录'}), 404
    json_file = next(target_dir.glob('*.json'), None)
    if not json_file:
        return jsonify({'message': '未找到歌单JSON文件'}), 404
    try:
        data = json.loads(json_file.read_text(encoding='utf-8'))
        return jsonify({'playlist_id': str(data.get('id', ''))})
    except Exception as e:
        return jsonify({'message': f'读取JSON失败: {e}'}), 500

@app.route('/sort-playlist', methods=['POST'])
def sort_playlist_route():
    data = request.json
    base_dir = data.get('base_dir')
    pl_name = data.get('playlist_name')
    start_num = data.get('start_number', 500)
    target_dir = find_target_directory(base_dir, pl_name)
    if not target_dir:
        return jsonify({'status': 'error', 'message': f"未找到目录: {pl_name}"}), 404
    try:
        json_file = next(target_dir.glob('*.json'), None)
        if not json_file:
            return jsonify({'status': 'error', 'message': "缺少排序所需的JSON文件"}), 404
        pl_data = json.loads(json_file.read_text(encoding='utf-8'))
        tracks = pl_data.get('tracks', [])
        cnt = MusicSorter().sort_playlist(str(target_dir), tracks, start_num)
        return jsonify({'status': 'success', 'message': f"排序完成！处理了 {cnt} 首歌曲。"})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"排序异常: {e}"}), 500

@app.route('/remove-numbering', methods=['POST'])
def remove_numbering_route():
    data = request.json
    base_dir = data.get('base_dir')
    pl_name = data.get('playlist_name')
    target_dir = find_target_directory(base_dir, pl_name)
    if not target_dir:
        return jsonify({'status': 'error', 'message': f"未找到目录: {pl_name}"}), 404
    try:
        cnt = MusicSorter().remove_numbers(str(target_dir))
        return jsonify({'status': 'success', 'message': f"去序完成！处理了 {cnt} 个文件。"})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"去序异常: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)