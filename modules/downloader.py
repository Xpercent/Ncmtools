# modules/downloader.py
import requests
import time
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import urllib3

# 音频元数据处理
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC

# 本地模块
from .utils import sanitize_filename, normalize_ncm_url, normalize_artists
from .Lyrics import merge_lyrics

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== API 定义区域 (保留原风格) ====================

def api_xpercent_playlist(playlist_id: str):
    """获取歌单信息"""
    api_url = f"https://ncmapi.xpercent.dpdns.org/playlist?id={playlist_id}"
    try:
        response = requests.get(api_url, timeout=30)
        source_data = response.json()
        formatted_data = {
            'id': source_data.get('id'),
            'name': source_data.get('name'),
            'coverImgUrl': source_data.get('coverImgUrl'),
            'trackCount': source_data.get('trackCount'),
            'creator': source_data.get('creator'),
            'tracks': [
                {
                    'name': song['name'],
                    'id': song['id'],
                    'ar': "/".join(song['ar']) if isinstance(song['ar'], list) else str(song['ar']),
                    'album': song['album'],
                    'picUrl': song['picUrl'],
                    'duration': song['duration']
                } 
                for song in source_data.get('songs', [])
            ]
        }
        return formatted_data
    except Exception as e:
        print(f"获取歌单失败: {e}")
        return {}

def api_xpercent_album(album_id: str):
    """获取专辑信息"""
    api_url = f"https://ncmapi.xpercent.dpdns.org/album?id={album_id}"
    try:
        response = requests.get(api_url, timeout=30)
        source_data = response.json()
        formatted_data = {
            'id': album_id,
            'name': source_data.get('name'),
            'coverImgUrl': source_data.get('picUrl'),
            'trackCount': source_data.get('size'),
            'tracks': [
                {
                    'name': song['name'],
                    'id': song['id'],
                    'ar': "/".join(song['ar']) if isinstance(song['ar'], list) else str(song['ar']),
                    'album': song['album'],
                    'picUrl': song.get('picUrl'),
                    'duration': song['duration']
                } 
                for song in source_data.get('songs', [])
            ]
        }
        return formatted_data
    except Exception as e:
        print(f"获取专辑失败: {e}")
        return {}

def api_lyrics(song_num: str):
    api_url = f"https://music.163.com/api/song/lyric?os=pc&id={song_num}&rv=-1&lv=-1&tv=-1"
    try:
        response = requests.get(api_url, timeout=30)
        data = response.json()
        return {
            "lrc": data.get("lrc")['lyric'],
            "tlyric": data.get("tlyric")['lyric'],
            "romalrc": data.get("romalrc")['lyric']  
        }
    except Exception as e:
        print(f"获取歌词失败: {e}")
        return {"lrc": None, "tlyric": None, "romalrc": None}

def api_song_detail(song_num: str):
    api_url = f"https://music.163.com/api/song/detail?ids=[{song_num}]"
    try:
        response = requests.get(api_url, timeout=30)
        data = response.json()
        if data.get("songs"):
            song_info = data["songs"][0]
            return {
                "id": str(song_info.get("id")),
                "name": song_info.get("name"),
                "ar" : "/".join([artist.get('name', '') for artist in song_info['artists']]),
                "album": song_info.get("album").get("name"),
                "picUrl": song_info.get("album").get("picUrl") if song_info.get("album") else None,
                "duration": song_info.get("duration")
            }
        return None
    except Exception as e:
        print(f"获取歌曲详情失败: {e}")
        return None

def api_vkeys_music(song_num: str, level: str = 'exhigh'):
    level_map = {"standard": 2, "exhigh": 4, "lossless": 5, "hires": 6, "jymaster": 9}
    quality = level_map.get(level, 4)
    base_url = f"https://api.vkeys.cn/v2/music/netease?id={song_num}&quality={quality}"
    try:
        response = requests.get(base_url, timeout=30)
        data = response.json()["data"]
        formatted_data = {
            "level": data.get('quality'),
            "size": str(data.get('size')) if data.get('size') else None,
            "url": data.get('url')
        }
        return formatted_data
    except Exception as e:
        print(f"Vkeys API请求失败: {e}")
        return None

def api_bugpk_music(song_num: str, level: str = 'exhigh'):
    api_url = f"https://api.bugpk.com/api/163_music/song?ids={song_num}&level={level}&type=json"
    try:
        response = requests.get(api_url, timeout=30)
        data = response.json()
        formatted_data = {
            "level": data.get("level"),
            "size": str(data.get("size")) if data.get("size") else None,
            "url": data.get("url")
        }
        return formatted_data
    except Exception as e:
        print(f"BugPK API请求失败: {e}")
        return None

def api_ss22y_music(song_num: str, level: str = 'exhigh'):
    base_url = f"https://music.meorion.moe/api/getSongUrl?id={song_num}&level={level}"
    try:
        response = requests.get(base_url, timeout=30)
        data = response.json()
        formatted_data = {
            "level": level,
            "size": str(data.get('size')),
            "url": data.get('url')
        }
        return formatted_data
    except Exception as e:
        print(f"ss22y API请求失败: {e}")
        return None

def api_iwenwiki_music(song_num: str, level: str = 'exhigh'):
    api_url = f"http://iwenwiki.com:3000/song/url/v1?id={song_num}&level={level}"
    try:
        response = requests.get(api_url, timeout=30)
        data = response.json()["data"][0]
        formatted_data = {
            "level": data.get("quality"),
            "size": str(data.get("size")) if data.get("size") else None,
            "url": data.get("url")
        }
        return formatted_data
    except Exception as e:
        print(f"iwenwiki API请求失败: {e}")
        return None

def parse_music_source(parse_type: str, source_url: str):
    """根据类型调用不同的解析函数"""
    if parse_type == 'playlist':
        pid = normalize_ncm_url(source_url, "id", "playlist")
        return api_xpercent_playlist(pid)
    elif parse_type == 'album':
        aid = normalize_ncm_url(source_url, "id", "album")
        return api_xpercent_album(aid)
    elif parse_type == 'link':
        sid = normalize_ncm_url(source_url, "id", "song")
        return {'id': sid}
    else:
        raise ValueError(f"不支持的解析类型: {parse_type}")

# ==================== 下载器类 ====================

class MusicDownloader:
    def __init__(self, save_dir, quality='standard', api_name='bugpk'):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality
        self.api_name = api_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.session.verify = False

    def _download_file(self, url, filepath, max_retries=3):
        if not url or not str(url).startswith('http'):
            return False
        
        for attempt in range(max_retries):
            try:
                with self.session.get(url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                return True
            except Exception:
                if attempt == max_retries - 1: return False
                time.sleep(1)
        return False

    def _embed_metadata(self, audio_path, cover_data, title, artist, album):
        try:
            ext = audio_path.suffix.lower()
            if ext == '.mp3':
                audio = MP3(str(audio_path), ID3=ID3)
                if audio.tags is None: audio.add_tags()
                audio.tags.clear()
                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=normalize_artists(artist)))
                audio.tags.add(TALB(encoding=3, text=album))
                if cover_data:
                    audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
                audio.save(v2_version=3)
            elif ext == '.flac':
                audio = FLAC(str(audio_path))
                audio.clear_pictures()
                audio.delete()
                audio['title'] = title
                audio['artist'] = normalize_artists(artist)
                audio['album'] = album
                if cover_data:
                    p = Picture()
                    p.type = 3
                    p.mime = 'image/jpeg'
                    p.desc = 'Cover'
                    p.data = cover_data
                    audio.add_picture(p)
                audio.save()
            return True
        except Exception as e:
            print(f"元数据嵌入失败: {e}")
            return False

    def get_song_url(self, song_id, api_name=None):
        target_api = api_name or self.api_name
        api_func_map = {
            'vkeys': api_vkeys_music,
            'bugpk': api_bugpk_music,
            'iwenwiki': api_iwenwiki_music,
            'ss22y': api_ss22y_music,
        }
        func = api_func_map.get(target_api, api_bugpk_music)
        return func(song_id, self.quality)

    def download_song(self, song_url, download_lyrics=True, api_name=None, track_info=None, download_lyrics_translated=False):
        song_id = normalize_ncm_url(song_url, "id", "song")
        if track_info:
            songs = track_info  # 保持和歌单模式一致的结构
        else:
            songs = api_song_detail(song_id)
                
        # --- 1. 本地文件预检 ---
        filename_base = sanitize_filename(f"{songs['name']} - {songs['ar']}")
        for ext in ['.mp3', '.flac', '.wav', '.ogg']:
            if (self.save_dir / f"{filename_base}{ext}").exists():
                return "skipped", filename_base, song_id

        # --- 2. 调用 API 获取详情 (URL, 歌词等) ---
        song_url = self.get_song_url(song_id, api_name)
        print(f"调试信息 - 歌曲详情 - API{api_name} :-------------------------------")
        print(songs)
        print(song_url)
        if not song_url or not song_url.get("url"):
            return "failed", filename_base, song_id
        
        # --- 3. 确定文件扩展名 ---
        parsed = urlparse(song_url["url"])
        # 如果 URL 带有后缀则使用，否则根据音质猜测
        ext = Path(parsed.path).suffix or (".flac" if self.quality in ['lossless', 'hires', 'jymaster'] else ".mp3")
        audio_path = self.save_dir / f"{filename_base}{ext}"

        # API 确认后的二次检查
        if audio_path.exists():
            return "skipped", filename_base, song_id

        # --- 4. 下载音频 ---
        if not self._download_file(song_url["url"], audio_path):
            return "failed", filename_base, song_id

        # --- 5. 下载封面并嵌入元数据 ---
        # 优先使用 track_info 里的名字写入标签，防止 API 返回的名字与歌单不一致
        if songs.get("picUrl"):
            cover_path = self.save_dir / f"{filename_base}_cv.tmp"
            if self._download_file(songs["picUrl"], cover_path):
                try:
                    with open(cover_path, 'rb') as f:
                        cover_bytes = f.read()
                    self._embed_metadata(audio_path, cover_bytes, sanitize_filename(songs["name"]), sanitize_filename(songs["ar"]), songs["album"])
                finally:
                    if cover_path.exists(): cover_path.unlink()

        # --- 6. 处理歌词 ---
        if download_lyrics:
            lyrics_data = api_lyrics(song_id)
            try:
                lrc_content = merge_lyrics(
                    lyrics_data.get("lrc", ""), 
                    lyrics_data.get("tlyric", "") if download_lyrics_translated else ""
                )
                if lrc_content:
                    (self.save_dir / f"{filename_base}.lrc").write_text("\n".join(lrc_content), encoding="utf-8")
            except Exception:
                pass

        return "downloaded", filename_base, song_id
    
if __name__ == "__main__":
    # 简单测试下载器
    #b = api_xpercent_playlist("14467442486")
    #a = api_xpercent_album("358640968")
    #a = api_lyrics("3335544260")
    a = api_song_detail("3335544260")
    #print(a)
    #调用下载函数
    

    print(a)