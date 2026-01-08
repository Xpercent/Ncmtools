# modules/downloader.py
import requests
import time
from pathlib import Path
from urllib.parse import urlparse
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import sanitize_filename, normalize_ncm_url, normalize_artists
from .Lyrics import merge_lyrics # 假设Lyrics.py在同级目录

HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0',
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Origin': 'https://wyapi.toubiec.cn',
    'Referer': 'https://wyapi.toubiec.cn/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}

def api_suxiaoqing_playlist(playlist_id: str):
    """获取歌单信息"""
    response = requests.post(
        'https://wyapi-1.toubiec.cn/api/music/playlist',#获取歌曲链接
        headers=HEADERS,
        json={"id": f"{playlist_id}"}, verify=False
    )
    source_data = response.json().get('data', {})
    formatted_data = {
        'id': source_data.get('id'),
        'name': source_data.get('name'),
        'coverImgUrl': source_data.get('coverImgUrl'),
        'trackCount': source_data.get('trackCount'),
        'creator': source_data.get('creator'),
        'tracks': source_data.get('tracks')
    }
    return formatted_data

def api_suxiaoqing_album(album_id: str):
    """获取专辑信息"""
    response = requests.post(
        'https://wyapi-1.toubiec.cn/api/music/album',#获取专辑链接
        headers=HEADERS,
        json={"id": f"{album_id}"}, verify=False
    )
    source_data = response.json().get('data', {})
    formatted_data = {
        'id': source_data.get('id'),
        'name': source_data.get('name'),
        'coverImgUrl': source_data.get('coverImgUrl'),
        'trackCount': source_data.get('trackCount'),
        'artist': source_data.get('artist'),
        'tracks': source_data.get('tracks')
    }
    return formatted_data

def api_suxiaoqing_music(song_id: str, level: str = 'exhigh') -> dict:
    try:
        BASE_URL = 'https://wyapi-1.toubiec.cn/api/music'
        # 1. 定义任务配置（只存变化的参数）
        api_tasks = {
            'detail': {'json': {'id': song_id}},
            'url':    {'json': {'id': song_id, 'level': level}},
            'lyric':  {'json': {'id': song_id}}
        }
        # 2. 使用 Session 并发执行
        with requests.Session() as session:
            session.headers.update(HEADERS)
            session.verify = False  # 继承你原来的设置，忽略SSL证书
            def fetch(item):
                key, params = item
                url = f"{BASE_URL}/{key}"
                # 执行 POST 请求
                resp = session.post(url, **params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                return key, data['data']

            with ThreadPoolExecutor(max_workers=3) as executor:
                # 使用 dict 直接将结果元组转换为字典
                responses = dict(executor.map(fetch, api_tasks.items()))
        # --- 数据整合 ---
        detail = responses.get('detail')
        url_info = (responses.get('url') or [{}])[0]
        lyric = responses.get('lyric') or {}

        # 如果连最基本的歌曲详情都没有，就返回错误
        print(responses)
        print("--------------------------------")
        if not detail:
            return {"status": 404, "error": "无法获取歌曲基本信息", "id": song_id}

        formatted_data = {
            "status": 200,
            "id": str(detail.get('id')),
            "name": detail.get('name'),
            "pic": detail.get('picimg'),
            "ar_name": detail.get('singer'),
            "al_name": detail.get('album'),
            "duration": detail.get('duration'),
            "level": url_info.get('level'),
            "size": str(url_info.get('size')),
            "url": url_info.get('url'),
            "lyric": lyric.get('lrc'),
            "tlyric": lyric.get('tlyric'),
            "romalrc": lyric.get('romalrc'),
            "klyric": lyric.get('klyric')
        }
        return formatted_data
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"suxiaoqingAPI请求失败: {e}")
        return None

def api_ss22y_music(song_num: str, level: str = 'exhigh'):
    base_url = "https://music.meorion.moe/api"
    # 定义任务映射：键名 -> 对应的 URL
    urls = {
        'detail': f"{base_url}/getSongInfo?id={song_num}",
        'url': f"{base_url}/getSongUrl?id={song_num}&level={level}",
        'lyric': f"{base_url}/getSongLyric?id={song_num}"
    }
    try:
        with requests.Session() as session:
            def fetch(key_url):
                key, url = key_url
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                return key, resp.json()

            # 使用线程池并行请求
            with ThreadPoolExecutor(max_workers=3) as executor:
                # map 会按顺序返回结果，这里直接构建字典
                responses = dict(executor.map(fetch, urls.items()))

        detail = responses.get('detail')
        url_info = responses.get('url')
        lyric = responses.get('lyric')

        # 如果连最基本的歌曲详情都没有，就返回错误
        print(responses)
        print("--------------------------------")
        if not detail:
            return {"status": 404, "error": "无法获取歌曲基本信息", "id": song_num}

        # 格式化并合并成最终结果
        formatted_data = {
            "status": 200,
            "id": str(detail.get('id')),
            "name": detail.get('name'),
            "pic": detail["album"]["cover"],
            "ar_name": "／".join([ar['name'] for ar in detail.get('author', [])]),
            "al_name": detail["album"]["name"],
            "duration": url_info.get('time'),
            "level": level,
            "size": str(url_info.get('size')),
            "url": url_info.get('url'),
            "lyric": lyric.get('lyric'),
            "tlyric": "",
            "romalrc": "",
            "klyric": ""
        }
        print(formatted_data)
        return formatted_data
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"ss22yAPI请求失败: {e}")
        return None


def api_vkeys_music(song_num: str, level: str = 'exhigh'):
    level_map = {
        "standard": 2, "exhigh": 4, "lossless": 5, "hires": 6, "jymaster": 9
    }
    quality = level_map.get(level)
    base_url = "https://api.vkeys.cn/v2/music/netease"
    api_tasks = {
        'url': f"{base_url}?id={song_num}&quality={quality}",
        'lyric': f"{base_url}/lyric?id={song_num}"
    }
    try:
        with requests.Session() as session:
            def fetch(task):
                key, url = task
                try:
                    resp = session.get(url, timeout=30)
                    resp.raise_for_status()
                    # 按照你原来的逻辑，直接取 .json().get('data', {})
                    return key, resp.json().get('data', {})
                except Exception as e:
                    print(f"请求 {key} 失败: {e}")
                    return key, {}

            # 3. 并行执行
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = dict(executor.map(fetch, api_tasks.items()))
        
        url_info = responses.get('url')
        lyric = responses.get('lyric')
        print(responses)
        print("--------------------------------")
        formatted_data = {
            "status": 200,
            "id": str(song_num),
            "name": url_info.get('song'),
            "pic": url_info.get('cover'),
            "ar_name": url_info.get('singer'),
            "al_name": url_info.get('album'),
            "duration": url_info.get('interval'),
            "level": url_info.get('quality'),
            "size": str(url_info.get('size')) if url_info.get('size') is not None else None,
            "url": url_info.get('url'),
            "lyric": lyric.get('lrc'),
            "tlyric": lyric.get('trans'),
            "romalrc": lyric.get('roma'),
            "klyric": ""
        }
        return formatted_data
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"落月API请求失败: {e}")
        return None

def api_kxzjoker_music(song_num: str, level: str = 'exhigh'):
    """看戏仔API - 获取歌曲数据"""
    api_url = f"https://api.kxzjoker.cn/api/163_music?url=https://music.163.com/song?id={song_num}&level={level}&type=json"
    try:
        response = requests.Session().get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(data)
        print("--------------------------------")
        if isinstance(data, dict) and data.get("url"):
            # 格式化返回数据，使其与其他API格式一致
            formatted_data = {
                "status": 200,
                "id": str(song_num),
                "name": data.get("name"),
                "pic": data.get("pic"),
                "ar_name": data.get("ar_name"),
                "al_name": data.get("al_name"),
                "duration": data.get("duration"),
                "level": data.get("level"),
                "size": str(data.get("size")) if data.get("size") is not None else None,
                "url": data.get("url"),
                "lyric": data.get("lyric"),
                "tlyric": data.get("tlyric"),
                "romalrc": data.get("romalrc"),
                "klyric": data.get("klyric")
            }
            return formatted_data
        return None
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"看戏仔API请求失败: {e}")
        return None

def parse_music_source(parse_type: str, source_url: str):
    """
    根据解析类型解析音乐源
    
    Args:
        parse_type: 解析类型 ('playlist', 'link', 'album')
        source_url: 源URL或ID
    
    Returns:
        解析后的数据，格式统一为包含tracks列表的字典
    """
    
    if parse_type == 'playlist':
        # 歌单解析
        playlist_id = normalize_ncm_url(source_url, "id", "playlist")
        return api_suxiaoqing_playlist(playlist_id)
    
    elif parse_type == 'album':
        # 专辑解析
        album_id = normalize_ncm_url(source_url, "id", "album")
        return api_suxiaoqing_album(album_id)
    
    elif parse_type == 'link':
        # 链接解析（单曲）
        song_id = normalize_ncm_url(source_url, "id", "song")
        # 返回单曲格式的数据
        return {
            'id': song_id,
            'name': f'单曲_{song_id}',
            'tracks': [{'id': song_id}]
        }
    
    else:
        raise ValueError(f"不支持的解析类型: {parse_type}")

class MusicDownloader:
    # 关键修复：将 init 重命名为 __init__
    def __init__(self, save_dir, quality='standard', api_name='suxiaoqing'):
        """
        初始化下载器。
        """
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality
        self.api_name = api_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def download_file(self, url, filepath, max_retries=3):
        """下载文件，支持重试。"""
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            print(f"无效的URL，跳过下载: {url}")
            return False
        for attempt in range(max_retries):
            try:
                with self.session.get(url, stream=True, timeout=30) as response:
                    response.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                return True
            except requests.exceptions.RequestException as e:
                print(f"下载文件失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        return False

    def get_song_data(self, song_id, api_name=None):
        """根据API名称获取歌曲数据。"""
        api_to_use = api_name or self.api_name
        api_map = {
            'suxiaoqing': api_suxiaoqing_music,
            'ss22y': api_ss22y_music,
            'vkeys': api_vkeys_music,
            'kxzjoker': api_kxzjoker_music
        }
        api_func = api_map.get(api_to_use, api_suxiaoqing_music)
        
        try:
            data = api_func(song_id, self.quality)
            if isinstance(data, dict) and data.get("url"):
                return data
            return None
        except Exception as e:
            print(f"获取歌曲数据时出错 (API: {api_to_use}): {e}")
            return None

    def embed_metadata(self, audio_path, cover_path, title, artist, album):
        """自动识别文件类型并嵌入元数据。"""
        try:
            if not cover_path.exists():
                return False

            with open(cover_path, 'rb') as f:
                cover_data = f.read()

            file_extension = audio_path.suffix.lower()

            if file_extension == '.mp3':
                audio = MP3(str(audio_path), ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
                audio.tags.clear()
                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=normalize_artists(artist)))
                audio.tags.add(TALB(encoding=3, text=album))
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
                audio.save(v2_version=3)

            elif file_extension == '.flac':
                audio = FLAC(str(audio_path))
                audio.clear_pictures()
                audio.delete()
                audio['title'] = title
                audio['artist'] = normalize_artists(artist)
                audio['album'] = album
                picture = Picture()
                picture.type = 3
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = cover_data
                audio.add_picture(picture)
                audio.save()
            else:
                print(f"不支持的音频格式，无法嵌入元数据: {file_extension}")
                return False
            
            print(f"成功为 {audio_path.name} 写入元数据")
            return True
        except Exception as e:
            print(f"写入元数据时发生错误: {e}")
            return False

    def download_song(self, song_url, download_lyrics=True, api_name=None, track_info=None, download_lyrics_translated=False):
        """
        下载单首歌曲。本版本回归原始代码的清晰逻辑，修复所有已知问题。
        """
        song_id = normalize_ncm_url(song_url, "id", "song")

        # 步骤 1: [歌单/专辑模式] 基于track_info进行高效的本地预检查。
        # 这个检查只用于跳过，不用于生成最终文件名。
        if track_info:
            pre_check_title = track_info.get('name')
            pre_check_artist = track_info.get('artists', '')
            pre_check_filename = sanitize_filename(f"{pre_check_title} - {pre_check_artist}")
            
            for ext in ['.mp3', '.flac', '.wav', '.ogg']:
                audio_path = self.save_dir / f"{pre_check_filename}{ext}"
                if audio_path.exists():
                    print(f"✓ 文件已存在 (本地匹配)，跳过: {audio_path.name}")
                    return "skipped", pre_check_filename, song_id

        song_data = self.get_song_data(song_id, api_name)

        # 如果API调用失败，则终止
        if not song_data or not song_data.get("url"):
            print(f"✗ 获取歌曲数据失败或URL为空 (API: {api_name}): {song_id}")
            return "failed", None, song_id
            
        # 步骤 3: [所有模式] 基于权威的 song_data 生成最终的文件名和元数据。
        # 这是唯一的数据来源，确保了所有模式下的一致性。
        # 使用 .get(key, default) 来优雅地处理任何API可能缺失的字段。
        title = sanitize_filename(song_data.get("name", "Unknown Title"))
        artist = sanitize_filename(song_data.get("ar_name", "Unknown Artist"))
        album = sanitize_filename(song_data.get("al_name", "Unknown Album"))
        filename_base = f"{title} - {artist}"

        # 步骤 4: 使用最终确定的文件名执行下载流程。
        parsed_url = urlparse(song_data.get("url"))
        file_extension = Path(parsed_url.path).suffix or \
                         (".flac" if self.quality in ['lossless', 'hires', 'jymaster'] else ".mp3")
        
        audio_path = self.save_dir / f"{filename_base}{file_extension}"
        
        # API检查后再次确认文件是否存在
        if audio_path.exists():
            return "skipped", filename_base, song_id

        if not self.download_file(song_data.get("url"), audio_path):
            return "failed", None, song_id

        # 步骤 5: 嵌入元数据。
        cover_path = self.save_dir / f"{filename_base}_cover.tmp.jpg"
        if self.download_file(song_data.get("pic"), cover_path):
            self.embed_metadata(audio_path, cover_path, title, artist, album)
            cover_path.unlink()

        # 步骤 6: 下载歌词。
        if download_lyrics:
            try:
                original_lrc = song_data.get("lyric", "")
                translated_lrc = song_data.get("tlyric", "") if download_lyrics_translated else ""
                lyrics_content = merge_lyrics(original_lrc, translated_lrc)
                if lyrics_content:
                    lrc_path = self.save_dir / f"{filename_base}.lrc"
                    lrc_path.write_text("\n".join(lyrics_content), encoding="utf-8")
            except Exception as e:
                print(f"处理歌词时出错: {e}")

        return "downloaded", filename_base, song_id
    
if __name__ == '__main__':
    a = api_suxiaoqing_music("3313253205", "exhigh")
    print(a)