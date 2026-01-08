# utils.py
import json
import re

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，替换操作系统不允许的字符。
    """
    if not isinstance(filename, str):
        filename = str(filename)
    replacements = {
        '/': '／', '\\': '＼', ':': '：', '*': '＊',
        '?': '？', '"': '＂', '<': '＜', '>': '＞', '|': '｜'
    }
    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)
    return filename.strip()

def normalize_artists(artists: str) -> str:
    replacement = ';'
    normalized_string = artists.replace('／', replacement)
    return normalized_string



def normalize_ncm_url(input_str: str, output_format: str = 'id', id_type: str = 'playlist') -> str:
    """
    标准化网易云音乐的歌单或单曲链接。
    可以从URL中提取ID，或将ID转换为标准的URL格式。
    参数:
        input_str: 输入字符串（可以是歌单/单曲的ID或URL）。
        output_format: 输出格式，'id' 或 'url'，默认为 'id'。
        id_type: 当输入为纯数字ID时，应将其视为的资源类型。
                   可选值为 'playlist' (默认) 或 'song'。
    返回:
        根据 output_format 返回格式化后的字符串。
    示例:
        # --- 处理歌单 ---
        >>> normalize_ncm_url("7096647187")
        '7096647187'
        >>> normalize_ncm_url("7096647187", output_format='url')
        'https://music.163.com/playlist?id=7096647187'
        >>> normalize_ncm_url("https://music.163.com/playlist?id=7096647187")
        '7096647187'
        >>> normalize_ncm_url("https://music.163.com/#/playlist?id=7096647187", output_format='url')
        'https://music.163.com/playlist?id=7096647187'
        # --- 处理单曲 (新增功能) ---
        >>> normalize_ncm_url("864311971", id_type='song')
        '864311971'
        >>> normalize_ncm_url("864311971", output_format='url', id_type='song')
        'https://music.163.com/song?id=864311971'
        >>> normalize_ncm_url("https://music.163.com/song?id=864311971")
        '864311971'
        >>> normalize_ncm_url("https://music.163.com/song?id=864311971&userid=250123544", 'url')
        'https://music.163.com/song?id=864311971'
    """
    # 定义更通用的正则模式，捕获 (song|playlist|album) 和 (\d+)
    # group 1: 资源类型 (song、playlist 或 album)
    # group 2: 资源ID (一串数字)
    URL_PATTERN = r'/(song|playlist|album)\?(?:.*&)?id=(\d+)'
    
    resource_id = None
    resource_type = None
    # 确保input_str是字符串类型
    if not isinstance(input_str, str):
        input_str = str(input_str)
    
    if input_str.isdigit():
        # 如果输入是纯数字，我们使用 id_type 参数来决定其类型
        resource_id = input_str
        if id_type not in ['playlist', 'song', 'album']:
            raise ValueError(f"无效的 id_type '{id_type}'，必须是 'playlist'、'song' 或 'album'")
        resource_type = id_type
    else:
        # 如果输入是URL，我们用正则来提取类型和ID
        match = re.search(URL_PATTERN, input_str)
        if not match:
            raise ValueError(f"无法从输入 '{input_str}' 中提取ID和类型")
        resource_type = match.group(1)
        resource_id = match.group(2)
    
    # 根据要求返回对应格式
    if output_format == 'id':
        return resource_id
    elif output_format == 'url':
        return f"https://music.163.com/{resource_type}?id={resource_id}"
    else:
        raise ValueError(f"无效的输出格式 '{output_format}'，必须是 'id' 或 'url'")