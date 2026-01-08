import os
import json
import re
import difflib
from pathlib import Path
from .utils import sanitize_filename
class MusicSorter:
    """
    一个用于根据.json歌单文件对音乐文件进行排序和重命名的类。
    """
    def __init__(self):
        # 使用集合以提高成员检查速度
        self.audio_extensions = {'.mp3', '.flac', '.wav', '.ogg'}
        # 预编译正则表达式以提高性能
        self.number_pattern = re.compile(r'^\d+\.\s')

    def get_playlists(self, base_dir: str) -> list:
        """获取所有歌单目录"""
        playlists = []
        try:
            # 使用 os.scandir 提高性能
            for entry in os.scandir(base_dir):
                if entry.is_dir():
                    playlists.append(entry.name)
        except Exception as e:
            print(f"读取歌单目录时出错: {e}")
        return playlists
    
    def get_audio_files(self, playlist_dir: Path) -> dict:
        """获取目录中的音频文件，返回字典 {文件名无扩展名: 扩展名}"""
        audio_files = {}
        try:
            for entry in os.scandir(playlist_dir):
                if entry.is_file():
                    # 统一使用小写扩展名进行判断
                    name, ext = os.path.splitext(entry.name)
                    if ext.lower() in self.audio_extensions:
                        audio_files[name] = ext
        except Exception as e:
            print(f"读取音频文件时出错: {e}")
        return audio_files

    def find_best_match(self, title: str, audio_files: dict) -> tuple | None:
        """使用模糊匹配找到最匹配的音频文件"""
        if not audio_files:
            return None
        
        # 使用 difflib 找到最佳匹配，cutoff=0.6 是一个合理的阈值
        matches = difflib.get_close_matches(title, audio_files.keys(), n=1, cutoff=0.6)
        if matches:
            best_match = matches[0]
            # 返回匹配的文件名(无扩展名)和扩展名
            return best_match, audio_files.get(best_match)
        return None
    
    def is_already_sorted(self, filename: str) -> bool:
        """检查文件名是否已经有序号前缀"""
        return bool(self.number_pattern.match(filename))
    
    def remove_number_prefix(self, filename: str) -> str:
        """移除文件名中的编号前缀"""
        return self.number_pattern.sub('', filename)
    
    def sort_playlist(self, playlist_dir_str: str, tracks: list, start_number: int) -> dict:
        """
        根据歌单信息对目录中的歌曲文件进行排序和重命名。

        :param playlist_dir_str: 歌单目录的路径字符串。
        :param tracks: 从json文件中解析出的歌曲信息列表。
        :param start_number: 排序的起始编号（通常是歌曲总数）。
        :return: 一个包含处理结果的字典。
        """
        playlist_dir = Path(playlist_dir_str)
        audio_files = self.get_audio_files(playlist_dir)
        sorted_file = playlist_dir / ".sorted"
        
        current_number = start_number
        rename_operations = []
        renamed_files_log = []
        not_found_tracks = []

        print(f"\n开始排序歌单，共 {len(tracks)} 首歌曲...")

        # 逆序处理 tracks 列表，从末尾歌曲开始编号
        for track in reversed(tracks):
            #title = track.get('full_title', '')
            title = sanitize_filename(f"{track.get('name','')} - {track.get('artists')}")
            if not title:
                continue
            
            matched_result = self.find_best_match(title, audio_files)
            if matched_result:
                matched_name, matched_ext = matched_result
                current_file_name = f"{matched_name}{matched_ext}"
                current_file_path = playlist_dir / current_file_name
                
                # 从audio_files中删除已匹配项，防止重复匹配
                del audio_files[matched_name]
                
                # 构建新的带编号的文件名
                # 注意：这里使用json中的title，以防文件名被用户修改过
                new_name = f"{current_number}. {title}{matched_ext}"
                new_path = playlist_dir / new_name
                
                if current_file_path != new_path:
                    rename_operations.append(('audio', current_file_path, new_path))
                
                renamed_files_log.append(new_name)
                
                # 检查并处理对应的.lrc歌词文件
                lrc_file = current_file_path.with_suffix('.lrc')
                if lrc_file.exists():
                    new_lrc_name = f"{current_number}. {title}.lrc"
                    new_lrc_path = playlist_dir / new_lrc_name
                    rename_operations.append(('lrc', lrc_file, new_lrc_path))
            else:
                not_found_tracks.append(title)
            
            current_number -= 1
        
        # 批量执行重命名操作
        processed_count = 0
        error_count = 0
        for file_type, old_path, new_path in rename_operations:
            try:
                old_path.rename(new_path)
                print(f"成功重命名 ({file_type}): {old_path.name} -> {new_path.name}")
                if file_type == 'audio':
                    processed_count += 1
            except Exception as e:
                print(f"重命名文件失败: {old_path.name} -> {new_path.name}, 原因: {e}")
                error_count += 1
        
        # 仅在有成功重命名的文件时才更新.sorted文件
        if renamed_files_log:
            try:
                with open(sorted_file, 'w', encoding='utf-8') as f:
                    for name in sorted(renamed_files_log):  # 写入时可以排序，便于查看
                        f.write(name + '\n')
            except Exception as e:
                print(f"更新.sorted文件时出错: {e}")
        
        print("\n排序完成！")
        if not_found_tracks:
            print(f"未找到匹配文件的歌曲 ({len(not_found_tracks)} 首):")
            for t in not_found_tracks:
                print(f"- {t}")

        return {
            "processed": processed_count,
            "not_found": len(not_found_tracks),
            "errors": error_count
        }

    def remove_numbers(self, playlist_dir_str: str) -> dict:
        """
        移除所有已排序歌曲文件名中的编号前缀。

        :param playlist_dir_str: 歌单目录的路径字符串。
        :return: 一个包含处理结果的字典。
        """
        playlist_dir = Path(playlist_dir_str)
        sorted_file = playlist_dir / ".sorted"
        
        if not sorted_file.exists():
            print("错误: 未找到 .sorted 文件，无法确定哪些文件已排序。")
            return {"processed": 0, "errors": 0}
        
        try:
            with open(sorted_file, 'r', encoding='utf-8') as f:
                sorted_files = [line.strip() for line in f.readlines()]
        except Exception as e:
            print(f"读取.sorted文件时出错: {e}")
            return {"processed": 0, "errors": 0}
        
        if not sorted_files:
            print("没有找到已排序的文件记录。")
            return {"processed": 0, "errors": 0}

        print(f"\n开始移除编号，共 {len(sorted_files)} 个文件记录...")
        rename_operations = []
        
        for filename in sorted_files:
            file_path = playlist_dir / filename
            
            if not file_path.exists():
                print(f"文件不存在，跳过: {filename}")
                continue
            
            if not self.is_already_sorted(filename):
                print(f"文件没有编号，跳过: {filename}")
                continue
            
            new_name = self.remove_number_prefix(filename)
            new_path = playlist_dir / new_name
            rename_operations.append(('audio', file_path, new_path))
            
            # 处理对应的.lrc文件
            lrc_file = file_path.with_suffix('.lrc')
            if lrc_file.exists():
                new_lrc_name = self.remove_number_prefix(lrc_file.name)
                new_lrc_path = playlist_dir / new_lrc_name
                rename_operations.append(('lrc', lrc_file, new_lrc_path))

        # 批量执行重命名操作
        processed_count = 0
        error_count = 0
        for file_type, old_path, new_path in rename_operations:
            try:
                old_path.rename(new_path)
                print(f"成功移除编号 ({file_type}): {old_path.name} -> {new_path.name}")
                if file_type == 'audio':
                    processed_count += 1
            except Exception as e:
                print(f"移除编号失败: {old_path.name} -> {new_path.name}, 原因: {e}")
                error_count += 1
        
        # 只有在有成功处理的文件时才删除.sorted文件
        if processed_count > 0:
            try:
                sorted_file.unlink()
                print("已成功删除.sorted文件")
            except Exception as e:
                print(f"删除.sorted文件时出错: {e}")

        print("\n移除编号完成！")
        return {
            "processed": processed_count,
            "errors": error_count
        }

