import re
from typing import List, Dict, Optional


class LRCParser:
    """LRC歌词解析器"""
    
    TIME_PATTERN = re.compile(r'\[(\d+):(\d+)\.(\d+)\]')
    
    @staticmethod
    def parse_lrc_time(time_str: str) -> int:
        """
        解析LRC时间格式 [mm:ss.xx] 为毫秒
        
        Args:
            time_str: LRC时间字符串
            
        Returns:
            毫秒数
        """
        try:
            time_str = time_str.strip('[]')
            minutes, rest = time_str.split(':', 1)
            
            if '.' in rest:
                seconds, milliseconds = rest.split('.', 1)
                # 处理不同精度的毫秒
                if len(milliseconds) == 2:
                    milliseconds = int(milliseconds) * 10  # 转换为3位毫秒
                else:
                    milliseconds = int(milliseconds[:3])   # 取前3位
            else:
                seconds = rest
                milliseconds = 0
            
            return (int(minutes) * 60000 + 
                   int(seconds) * 1000 + 
                   int(milliseconds))
            
        except (ValueError, AttributeError) as e:
            raise ValueError(f"无效的时间格式: {time_str}") from e
    
    @staticmethod
    def format_lrc_time(milliseconds: int) -> str:
        """
        将毫秒格式化为LRC时间格式
        
        Args:
            milliseconds: 毫秒数
            
        Returns:
            LRC格式时间字符串
        """
        minutes = milliseconds // 60000
        seconds = (milliseconds % 60000) // 1000
        millis = milliseconds % 1000
        return f"[{minutes:02d}:{seconds:02d}.{millis:03d}]"
    
    def parse_lrc_content(self, text: str) -> List[Dict]:
        """
        解析LRC歌词内容
        
        Args:
            text: 原始歌词文本
            
        Returns:
            解析后的歌词列表，每个元素包含时间和内容
        """
        if not text or not text.strip():
            return []
        
        lines = text.strip().split('\n')
        lyrics = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 查找所有时间标签
            time_matches = re.findall(r'\[(\d+:\d+\.\d+)\]', line)
            if time_matches:
                # 移除时间标签获取纯内容
                content = re.sub(r'\[(\d+:\d+\.\d+)\]', '', line).strip()
                if content:
                    for time_match in time_matches:
                        try:
                            time_ms = self.parse_lrc_time(time_match)
                            lyrics.append({
                                'time': time_ms,
                                'content': content
                            })
                        except ValueError as e:
                            print(f"警告: 跳过无效时间标签 '{time_match}': {e}")
                            continue
        
        # 按时间排序
        lyrics.sort(key=lambda x: x['time'])
        return lyrics


class LyricsMerger:
    """歌词合并器"""
    
    def __init__(self):
        self.parser = LRCParser()
    
    def merge_lyrics(self, original_text: str, translated_text: str) -> List[str]:
        """
        合并原文和译文歌词
        
        Args:
            original_text: 原文歌词文本
            translated_text: 译文歌词文本
            
        Returns:
            合并后的歌词行列表
        """
        # 解析歌词
        original_lyrics = self.parser.parse_lrc_content(original_text)
        translated_lyrics = self.parser.parse_lrc_content(translated_text)
        
        # 创建时间到内容的映射
        original_dict = {lyric['time']: lyric['content'] for lyric in original_lyrics}
        translated_dict = {lyric['time']: lyric['content'] for lyric in translated_lyrics}
        
        # 获取所有时间点并排序
        all_times = sorted(set(original_dict.keys()) | set(translated_dict.keys()))
        
        # 合并歌词
        merged_lines = []
        for time_ms in all_times:
            original_content = original_dict.get(time_ms, '')
            translated_content = translated_dict.get(time_ms, '')
            
            if original_content and translated_content:
                merged_line = f"{self.parser.format_lrc_time(time_ms)} {original_content} / {translated_content}"
            elif original_content:
                merged_line = f"{self.parser.format_lrc_time(time_ms)} {original_content}"
            elif translated_content:
                merged_line = f"{self.parser.format_lrc_time(time_ms)} {translated_content}"
            else:
                continue
                
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