import re
from typing import List, Dict, Optional

class LRCParser:
    """LRC歌词解析器（增强兼容版）"""
    
    # 修复后的正则：支持 [mm:ss.xx] 或 [mm:ss:xx] 格式
    # [(\d+):(\d+)[.:](\d+)] 分别匹配 分:秒[点或冒号]毫秒
    TIME_PATTERN = re.compile(r'\[(\d+):(\d+)[.:](\d+)\]')
    
    @staticmethod
    def parse_lrc_time(time_str: str) -> int:
        """
        解析LRC时间格式 [mm:ss.xx] 或 [mm:ss:xx] 为毫秒
        """
        try:
            # 统一将冒号替换为点，方便拆分，或者直接正则提取
            time_str = time_str.strip('[]')
            # 查找分隔符：可能是最后一个冒号或者点
            parts = re.split(r'[:.]', time_str)
            
            if len(parts) < 3:
                return 0
            
            minutes = int(parts[0])
            seconds = int(parts[1])
            ms_part = parts[2]
            
            # 处理毫秒/百分秒位
            if len(ms_part) == 2:
                milliseconds = int(ms_part) * 10  # [00:22:25] -> 250ms
            else:
                milliseconds = int(ms_part[:3])   # 取前三位
            
            return minutes * 60000 + seconds * 1000 + milliseconds
            
        except (ValueError, IndexError) as e:
            raise ValueError(f"无效的时间格式: {time_str}") from e
    
    @staticmethod
    def format_lrc_time(milliseconds: int) -> str:
        minutes = milliseconds // 60000
        seconds = (milliseconds % 60000) // 1000
        millis = milliseconds % 1000
        return f"[{minutes:02d}:{seconds:02d}.{millis:03d}]"
    
    def parse_lrc_content(self, text: str) -> List[Dict]:
        if not text or not text.strip():
            return []
        
        lines = text.strip().split('\n')
        lyrics = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 重点修复：允许匹配 [00:00:00] 或 [00:00.00]
            time_matches = self.TIME_PATTERN.findall(line)
            if time_matches:
                # 提取纯内容：移除所有形如 [xx:xx.xx] 或 [xx:xx:xx] 的标签
                content = self.TIME_PATTERN.sub('', line).strip()
                
                for match in time_matches:
                    # match 是一个元组 (分, 秒, 毫秒)
                    time_str = f"{match[0]}:{match[1]}.{match[2]}"
                    try:
                        time_ms = self.parse_lrc_time(time_str)
                        # 即使只有时间标签没有内容，也记录（用于占位/空行）
                        lyrics.append({
                            'time': time_ms,
                            'content': content
                        })
                    except ValueError:
                        continue
        
        lyrics.sort(key=lambda x: x['time'])
        return lyrics

# 歌词合并逻辑保持不变...
class LyricsMerger:
    def __init__(self):
        self.parser = LRCParser()
    
    def merge_lyrics(self, original_text: str, translated_text: str) -> List[str]:
        original_lyrics = self.parser.parse_lrc_content(original_text)
        translated_lyrics = self.parser.parse_lrc_content(translated_text)
        
        original_dict = {lyric['time']: lyric['content'] for lyric in original_lyrics}
        translated_dict = {lyric['time']: lyric['content'] for lyric in translated_lyrics}
        
        all_times = sorted(set(original_dict.keys()) | set(translated_dict.keys()))
        
        merged_lines = []
        for time_ms in all_times:
            original_content = original_dict.get(time_ms, '')
            translated_content = translated_dict.get(time_ms, '')
            
            # 格式化输出
            time_tag = self.parser.format_lrc_time(time_ms)
            if original_content and translated_content:
                merged_line = f"{time_tag}{original_content} / {translated_content}"
            else:
                merged_line = f"{time_tag}{original_content or translated_content}"
            merged_lines.append(merged_line)
        
        return merged_lines

# 创建全局实例用于向后兼容
_lyrics_merger = LyricsMerger()

def merge_lyrics(original_text: str, translated_text: str) -> List[str]:
    """
    合并原文和译文歌词（兼容旧版本）
    
    Args:
        original_text: 原文歌词文本
        translated_text: 译文歌词文本
        
    Returns:
        合并后的歌词行列表
    """
    return _lyrics_merger.merge_lyrics(original_text, translated_text)


def parse_lrc_time(time_str: str) -> int:
    """解析LRC时间（兼容旧版本）"""
    return LRCParser.parse_lrc_time(time_str)


def format_lrc_time(milliseconds: int) -> str:
    """格式化LRC时间（兼容旧版本）"""
    return LRCParser.format_lrc_time(milliseconds)


# 测试代码
if __name__ == "__main__":
    # 测试时间解析和格式化
    test_time = "[01:30.500]"
    milliseconds = parse_lrc_time(test_time)
    formatted = format_lrc_time(milliseconds)
    print(f"测试: {test_time} -> {milliseconds}ms -> {formatted}")
    
    # 测试歌词合并
    original = "[00:01.00]Hello world\n[00:05.00]This is a test"
    translated = "[00:01.00]你好世界\n[00:05.00]这是一个测试"
    
    merged = merge_lyrics(original, translated)
    print("\n合并结果:")
    for line in merged:
        print(line)