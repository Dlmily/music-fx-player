import time
import subprocess
import json
import re
import os
import sys
import requests
import platform
import atexit
import traceback
import io
import threading
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# 导入音效引擎模块
try:
    import effects
except ImportError:
    effects = None

SYSTEM = platform.system()

# 跨平台按键处理适配
if SYSTEM == "Windows":
    import msvcrt
else:
    import tty
    import termios
    import select

# 全局变量控制和清理
current_player = None
should_play_next = True  # 控制是否继续播放下一首

def cleanup():
    """退出程序时强行杀死未关闭的 mpv 进程并恢复终端"""
    global current_player
    if current_player and current_player.poll() is None:
        try:
            current_player.terminate()
        except:
            pass
    if SYSTEM != "Windows":
        os.system('stty sane 2>/dev/null')

atexit.register(cleanup)

def get_default_paths():
    if SYSTEM == "Linux" and "com.termux" in os.environ.get("PREFIX", ""):
        return '/data/data/com.termux/files/usr/bin/chromium-browser', '/data/data/com.termux/files/usr/bin/chromedriver'
    return None, None

CHROME_BIN, CHROME_DRIVER = get_default_paths()

CONFIG_FILE = "sound_effects_config.json"
CONFIG = {
    "play_mode": "列表顺序播放", 
    "modes": ["单曲循环", "列表顺序播放", "随机播放"],
    "enable_effects": False,
    "debug_mode": False,
    "enable_preload": False  # 预加载开关
}

# 全局播放列表
current_playlist = []
current_song_idx = 0

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                CONFIG["debug_mode"] = data.get("debug_mode", False)
                CONFIG["enable_effects"] = data.get("enable_effects", False)
                CONFIG["play_mode"] = data.get("play_mode", "列表顺序播放")
                CONFIG["enable_preload"] = data.get("enable_preload", False)
    except:
        pass

def save_config():
    data = {}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
    except:
        pass
    data["debug_mode"] = CONFIG["debug_mode"]
    data["enable_effects"] = CONFIG["enable_effects"]
    data["play_mode"] = CONFIG["play_mode"]
    data["enable_preload"] = CONFIG["enable_preload"]
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def handle_error(e, context=""):
    """集中处理错误信息，根据 debug 模式决定显示层级"""
    if SYSTEM != "Windows": os.system('stty sane 2>/dev/null')
    print(f"\n[!] {context}")
    if CONFIG.get("debug_mode", False):
        traceback.print_exc()
    else:
        print(f"报错详情: {e}\n(提示: 可在通用设置中开启 Debug 模式以查看完整报错堆栈)")
    input("\n按回车键继续...")

def clear_screen():
    if SYSTEM != "Windows":
        os.system('stty sane 2>/dev/null')
    os.system('cls' if SYSTEM == "Windows" else 'clear')
    print("欢迎使用网易云音乐播放器 v2.0")
    print("开发者：Dlmily")
    print("-" * 50)
    print("[1] 获取歌单内歌曲")
    print("[2] 搜索歌曲")
    print("[3] 通用设置")
    fx_status = "ON" if CONFIG["enable_effects"] else "OFF"
    print(f"[4] 音效设置 [{fx_status}]")
    print("-" * 50)

def get_key():
    if SYSTEM == "Windows":
        if msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', errors='ignore')
        return None
    else:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                key = sys.stdin.read(1)
                return key
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def format_time(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def draw_progress_bar(current, total):
    if total <= 0: return ""
    width = 30
    percent = min(current / total, 1.0)
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)
    return f"进度: [{bar}] {format_time(current)} / {format_time(total)}"

def render_cover(path):
    try:
        if os.path.exists(path):
            subprocess.run(['chafa', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['chafa', '--size', '40x20', path])
    except Exception:
        pass

def parse_full_lyrics(main_lrc, sub_lrc):
    """解析歌词"""
    def lrc_to_dict(lrc):
        d = {}
        if not lrc: return d
        for line in lrc.split('\n'):
            match = re.match(r'\[(\d+):(\d+\.\d+)\](.*)', line)
            if match:
                t = int(match.group(1)) * 60 + float(match.group(2))
                txt = match.group(3).strip()
                if txt: d[t] = txt
        return d
    
    m_dict = lrc_to_dict(main_lrc)
    
    # 如果主歌词没有时间戳，返回原始内容
    if not m_dict and main_lrc:
        return [{'time': 0, 'text': line, 'trans': ''} for line in main_lrc.split('\n') if line.strip()]
    
    s_dict = lrc_to_dict(sub_lrc)
    combined = []
    for t in sorted(m_dict.keys()):
        combined.append({'time': t, 'text': m_dict[t], 'trans': s_dict.get(t, "")})
    return combined

def extract_translator(sub_lrc):
    """提取歌词翻译者名称"""
    if not sub_lrc:
        return "未知翻译"
    match = re.search(r'\[by:([^\]]+)\]', sub_lrc)
    if match:
        return match.group(1)
    return "未知翻译"

def get_audio_duration(audio_data):
    """使用 mpv 获取音频时长"""
    try:
        import subprocess
        import tempfile
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            # 使用 ffprobe
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                 '-of', 'default=noprint_wrappers=1:nokey=1', tmp_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                os.unlink(tmp_path)
                return duration
        except:
            pass
        
        os.unlink(tmp_path)
        return 240
        
    except Exception as e:
        if CONFIG.get("debug_mode"):
            print(f"获取音频时长失败: {e}")
        return 240

def show_comment_ui(song_id, metadata):
    page = 0
    limit = 15
    while True:
        clear_screen()
        render_cover('cover.jpg')
        print(f"\n🎵 歌曲: {metadata['title']} | {metadata['artist']}")
        print(f"上一页[a]     下一页[l]       返回[B] (第 {page+1} 页)")
        print("="*50)
        url = f"https://zm.armoe.cn/comment/music?id={song_id}&limit={limit}&offset={page*limit}"
        try:
            res = requests.get(url, timeout=5).json()
            comments = res.get('hotComments', []) if page == 0 else res.get('comments', [])
            if not comments: print("\n> 暂无更多评论。")
            for c in comments:
                user = c.get('user', {}).get('nickname', '未知')
                content = c.get('content', '')
                t_str = c.get('timeStr', '')
                print(f"👤 {user}【{t_str}】:\n💬 {content}\n")
        except Exception as e:
            handle_error(e, "评论加载失败，请检查网络。")
            return
        while True:
            k = get_key()
            if k:
                if k.lower() == 'b': return
                if k.lower() == 'a' and page > 0: page -= 1; break
                if k.lower() == 'l': page += 1; break

class RealtimeAudioProcessor:
    """实时音频处理器，在后台线程中处理"""
    def __init__(self, raw_audio_data, engine=None):
        self.raw_audio = io.BytesIO(raw_audio_data)
        self.engine = engine
        self.chunk_size = 4096
        self.is_running = False
        self.queue = []
        self.lock = threading.Lock()
        
    def process_stream(self):
        """处理音频流并返回处理后的字节数据"""
        import numpy as np
        from scipy.io import wavfile
        
        self.raw_audio.seek(0)
        
        # 尝试读取wav格式
        try:
            self.raw_audio.seek(0)
            sr, audio_data = wavfile.read(self.raw_audio)
            if audio_data.ndim == 1:
                audio_data = np.stack([audio_data, audio_data], axis=1)
            audio_data = audio_data.astype(np.float32) / 32768.0
        except:
            self.raw_audio.seek(0)
            return self.raw_audio.getvalue()
        
        # 实时处理音频块
        output_chunks = []
        for i in range(0, len(audio_data), self.chunk_size):
            chunk = audio_data[i:i+self.chunk_size]
            if self.engine:
                processed_chunk = self.engine.process_chunk(chunk)
            else:
                processed_chunk = chunk
            output_chunks.append(processed_chunk)
        
        # 合并所有块
        processed_audio = np.concatenate(output_chunks, axis=0)
        processed_audio = np.clip(processed_audio * 32768, -32768, 32767).astype(np.int16)
        
        # 转换为字节
        output_buffer = io.BytesIO()
        wavfile.write(output_buffer, sr, processed_audio)
        output_buffer.seek(0)
        return output_buffer.getvalue()

def play_song(song_id, preload_next_song_id=None):
    """
    播放歌曲
    song_id: 当前歌曲ID
    preload_next_song_id: 预加载下一首的ID（仅在预加载开启时使用）
    """
    global current_player, current_song_idx, should_play_next
    should_play_next = True  # 重置播放控制标志
    clear_screen()
    print("- 正在获取歌曲元数据...")
    
    try:
        res = requests.get(f"https://api.paugram.com/netease/?id={song_id}").json()
        audio_link = res.get('link')
        sub_lrc = res.get('sub_lyric', "")
        
        metadata = {
            'title': res.get('title', '未知歌曲'),
            'artist': res.get('artist', '未知歌手'),
            'translator': extract_translator(sub_lrc),
            'cover': res.get('cover')
        }

        if metadata['cover']:
            img_data = requests.get(metadata['cover']).content
            with open('cover.jpg', 'wb') as f: f.write(img_data)
        
        lyrics = parse_full_lyrics(res.get('lyric', ""), sub_lrc)
        
        print("- 正在加载音频...")
        audio_raw = requests.get(audio_link).content
        
        # 获取音频时长
        print("- 正在获取音频时长...")
        duration = get_audio_duration(audio_raw)
        print(f"- 音频时长: {format_time(duration)}")
        
        # 预加载功能
        next_audio_cache = {'data': None, 'lock': threading.Lock()}
        preload_stop = {'flag': False}
        
        def preload_next_audio():
            """后台预加载下一首"""
            if preload_next_song_id and CONFIG["enable_preload"]:
                try:
                    next_res = requests.get(f"https://api.paugram.com/netease/?id={preload_next_song_id}").json()
                    next_link = next_res.get('link')
                    if next_link and not preload_stop['flag']:
                        next_audio = requests.get(next_link).content
                        with next_audio_cache['lock']:
                            if not preload_stop['flag']:
                                next_audio_cache['data'] = next_audio
                except:
                    pass
        
        preload_thread = threading.Thread(target=preload_next_audio, daemon=True)
        preload_thread.start()
        
        # 音效引擎初始化
        engine = None
        if CONFIG["enable_effects"] and effects:
            print("- 正在初始化V7音效引擎...")
            engine = effects.UltimateAudioEngine(sr=44100)
            print("- 音效引擎已就绪，准备实时处理。")
        
        def start_player(start_sec):
            """启动 mpv 播放器，支持从指定位置开始"""
            global current_player
            if current_player and current_player.poll() is None:
                current_player.terminate()
                time.sleep(0.2)
            
            return subprocess.Popen(
                ['mpv', '--no-video', '--really-quiet', f'--start={int(start_sec)}', '-'],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        def feed_audio_with_effects(player, audio_data, engine_ref):
            """在后台线程中处理并送流音频"""
            try:
                audio_buffer = io.BytesIO(audio_data)
                
                if engine_ref['engine']:
                    processor = RealtimeAudioProcessor(audio_data, engine_ref['engine'])
                    processed_data = processor.process_stream()
                    audio_buffer = io.BytesIO(processed_data)
                
                audio_buffer.seek(0)
                while True:
                    chunk = audio_buffer.read(8192)
                    if not chunk:
                        break
                    try:
                        player.stdin.write(chunk)
                        player.stdin.flush()
                    except:
                        break
                
                try:
                    player.stdin.close()
                except:
                    pass
            except Exception as e:
                if CONFIG.get("debug_mode"):
                    print(f"音频送流错误: {e}")

        elapsed = 0
        current_player = start_player(elapsed)
        
        engine_ref = {'engine': engine}
        
        audio_thread = threading.Thread(
            target=feed_audio_with_effects,
            args=(current_player, audio_raw, engine_ref),
            daemon=True
        )
        audio_thread.start()
        
        start_time = time.time()
        l_idx, is_paused, pause_at = 0, False, 0
        lyric_history = []
        need_refresh = True

        while current_player.poll() is None:
            if need_refresh:
                clear_screen()
                render_cover('cover.jpg')
                print(f"\n🎵 歌曲: {metadata['title']}")
                print(f"👤 歌手: {metadata['artist']}")
                print(f"✍️ 歌词翻译: {metadata['translator']}")
                print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
                print("\n暂停[K]  模式[G]  评论[C]  音效[E]  跳转[J]  返回[B]")
                print("="*50)
                for h_lrc in lyric_history:
                    print(h_lrc)
                need_refresh = False

            if not is_paused:
                elapsed = time.time() - start_time
                sys.stdout.write(f"\r{draw_progress_bar(elapsed, duration)}   ")
                sys.stdout.flush()

                if l_idx < len(lyrics) and elapsed >= lyrics[l_idx]['time']:
                    sys.stdout.write("\r" + " " * 60 + "\r")
                    l_line = f"    {lyrics[l_idx]['text']}"
                    if lyrics[l_idx]['trans']:
                        l_line += f"\n    {lyrics[l_idx]['trans']}"
                    
                    print(l_line + "\n")
                    lyric_history.append(l_line + "\n")
                    l_idx += 1

            key = get_key()
            if key:
                k = key.lower()
                if k == 'k':
                    is_paused = not is_paused
                    if is_paused:
                        sig = subprocess.signal.SIGSTOP if SYSTEM != "Windows" else 19
                        current_player.send_signal(sig)
                        pause_at = time.time()
                        print("\n" + "="*30)
                        print("- 已暂停。请选择您的操作：(任意键继续, B退出)")
                    else:
                        sig = subprocess.signal.SIGCONT if SYSTEM != "Windows" else 18
                        current_player.send_signal(sig)
                        start_time += (time.time() - pause_at)
                        need_refresh = True 
                
                elif k == 'c':
                    show_comment_ui(song_id, metadata)
                    need_refresh = True
                
                elif k == 'g':
                    idx = (CONFIG["modes"].index(CONFIG["play_mode"]) + 1) % 3
                    CONFIG["play_mode"] = CONFIG["modes"][idx]
                    save_config()
                    need_refresh = True
                
                elif k == 'e':
                    if CONFIG["enable_effects"] and engine and effects:
                        if SYSTEM != "Windows": 
                            os.system('stty sane 2>/dev/null')
                        
                        print("\n- 进入音效实时调整模式...")
                        time.sleep(0.5)
                        
                        try:
                            tui = effects.UltimateTUI(engine)
                            tui.run()
                            
                            print("\n- 音效参数已更新，继续播放...")
                            time.sleep(1)
                            need_refresh = True
                        except Exception as e:
                            if CONFIG.get("debug_mode"):
                                print(f"音效调整错误: {e}")
                            time.sleep(1)
                            need_refresh = True
                    else:
                        print("\n- 未开启全局音效或缺失 effects 模块。")
                        time.sleep(1.5)
                        need_refresh = True

                elif k == 'j':
                    # 移动歌曲进度
                    if SYSTEM != "Windows": 
                        os.system('stty sane 2>/dev/null')
                    
                    target = input(f"\n- 当前进度 {format_time(elapsed)}，请输入跳转时间 (分*秒，如 2*20): ")
                    
                    try:
                        if '*' in target:
                            m, s = target.split('*')
                            new_elapsed = int(m) * 60 + float(s)
                        else:
                            new_elapsed = float(target)
                        
                        new_elapsed = min(new_elapsed, duration)
                        new_elapsed = max(new_elapsed, 0)
                        
                        # 处理进度跳转
                        if current_player and current_player.poll() is None:
                            try:
                                current_player.terminate()
                                current_player.wait(timeout=2)
                            except:
                                pass
                        
                        time.sleep(0.5)  # 确保进程完全关闭
                        
                        # 重启播放器从新位置开始
                        current_player = start_player(new_elapsed)
                        
                        # 重启音频送流线程
                        audio_thread_new = threading.Thread(
                            target=feed_audio_with_effects,
                            args=(current_player, audio_raw, engine_ref),
                            daemon=True
                        )
                        audio_thread_new.start()
                        
                        # 同步时间，确保 elapsed 与 mpv 的实际播放位置一致
                        elapsed = new_elapsed
                        start_time = time.time() - new_elapsed
                        
                        time.sleep(0.5)
                        
                        clear_screen()
                        render_cover('cover.jpg')
                        print(f"\n🎵 歌曲: {metadata['title']}")
                        print(f"👤 歌手: {metadata['artist']}")
                        print(f"✍️ 歌词翻译: {metadata['translator']}")
                        print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
                        print(f"\n--- 跳转至 {format_time(new_elapsed)} ---")
                        print("="*50)
                        
                        lyric_history.clear()
                        l_idx = 0
                        while l_idx < len(lyrics) and lyrics[l_idx]['time'] < new_elapsed:
                            l_line = f"    {lyrics[l_idx]['text']}"
                            if lyrics[l_idx]['trans']:
                                l_line += f"\n    {lyrics[l_idx]['trans']}"
                            print(l_line)
                            lyric_history.append(l_line + "\n")
                            l_idx += 1
                        
                        time.sleep(1)
                        need_refresh = True
                        
                    except ValueError:
                        print("- 格式错误，请输入 数字*数字 或纯秒数。")
                        time.sleep(1)
                        need_refresh = True

                elif k == 'b':
                    # 停止预加载并中止下一首播放
                    should_play_next = False
                    preload_stop['flag'] = True
                    current_player.terminate()
                    break

        # 清理
        if os.path.exists('cover.jpg'): 
            os.remove('cover.jpg')
        
        # 停止预加载
        preload_stop['flag'] = True
        time.sleep(0.5)
        
        # 仅在 should_play_next 为 True 时播放下一首
        if not should_play_next or len(current_playlist) <= 1:
            return
        
        # 处理列表播放模式
        if CONFIG['play_mode'] == '单曲循环':
            play_song(song_id, preload_next_song_id)
        elif CONFIG['play_mode'] == '列表顺序播放':
            next_idx = (current_song_idx + 1) % len(current_playlist)
            current_song_idx = next_idx
            next_song_id = current_playlist[next_idx]['id']
            next_next_idx = (next_idx + 1) % len(current_playlist)
            next_next_song_id = current_playlist[next_next_idx]['id'] if CONFIG["enable_preload"] and len(current_playlist) > 1 else None
            play_song(next_song_id, next_next_song_id)
        elif CONFIG['play_mode'] == '随机播放':
            random_idx = random.randint(0, len(current_playlist) - 1)
            current_song_idx = random_idx
            random_song_id = current_playlist[random_idx]['id']
            next_random_idx = random.randint(0, len(current_playlist) - 1)
            next_random_song_id = current_playlist[next_random_idx]['id'] if CONFIG["enable_preload"] and len(current_playlist) > 1 else None
            play_song(random_song_id, next_random_song_id)

    except Exception as e:
        handle_error(e, "播放过程出错")

def playlist_flow():
    """获取歌单功能"""
    global current_playlist, current_song_idx
    clear_screen()
    playlist_id = input("- 请输入歌单 ID: ").strip()
    
    if not playlist_id:
        print("歌单 ID 不能为空")
        time.sleep(2)
        return
    
    try:
        clear_screen()
        print(f"- 正在获取歌单内歌曲... (ID: {playlist_id})")
        
        api_url = f"https://oiapi.net/api/NeteasePlaylistDetail&id={playlist_id}"
        response = requests.get(api_url, timeout=10)
        data = response.json()
        
        if data.get('code') != 1:
            print(f"获取失败: {data.get('message', '未知错误')}")
            time.sleep(2)
            return
        
        songs = data.get('data', [])
        if not songs:
            print("歌单为空或获取失败")
            time.sleep(2)
            return
        
        # 分页显示歌曲
        page = 0
        page_size = 15
        
        while True:
            clear_screen()
            total_pages = (len(songs) + page_size - 1) // page_size
            start_idx = page * page_size
            end_idx = min(start_idx + page_size, len(songs))
            
            print(f"\n- 歌单内共有 {len(songs)} 首歌曲 (第 {page+1} 页，共 {total_pages} 页)")
            print("="*60)
            
            valid_songs = []
            for idx, song in enumerate(songs[start_idx:end_idx], start_idx + 1):
                song_name = song.get('name', '未知歌曲')
                song_id = song.get('id')
                
                artists = song.get('artists', [])
                if artists:
                    artist_names = ', '.join([artist.get('name', '未知') for artist in artists])
                else:
                    artist_names = '未知歌手'
                
                print(f"[{idx:<3}] {song_name}")
                print(f"      歌手: {artist_names}")
                print("-" * 60)
                
                valid_songs.append({'id': song_id, 'name': song_name, 'artist': artist_names})
            
            # 分页控制
            print(f"\n上一页[a]  下一页[l]  选择歌曲[序号]  返回[B]")
            choice = input("\n请选择: ").strip()
            
            if choice.lower() == 'b':
                return
            elif choice.lower() == 'a' and page > 0:
                page -= 1
                continue
            elif choice.lower() == 'l' and page < total_pages - 1:
                page += 1
                continue
            
            try:
                target_idx = int(choice) - 1
                if 0 <= target_idx < len(songs):
                    # 设置全局播放列表
                    current_playlist = [{'id': s.get('id'), 'name': s.get('name')} for s in songs]
                    current_song_idx = target_idx
                    
                    song_id = songs[target_idx]['id']
                    # 获取下一首用于预加载
                    if CONFIG["enable_preload"] and len(current_playlist) > 1:
                        next_idx = (target_idx + 1) % len(current_playlist)
                        next_song_id = current_playlist[next_idx]['id']
                    else:
                        next_song_id = None
                    
                    play_song(song_id, next_song_id)
                    return
                else:
                    print("序号无效")
                    time.sleep(2)
            except ValueError:
                print("请输入有效的序号")
                time.sleep(2)
            
    except Exception as e:
        handle_error(e, "获取歌单失败")

def search_flow():
    clear_screen()
    options = Options()
    if CHROME_BIN: options.binary_location = CHROME_BIN
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    service = Service(CHROME_DRIVER) if CHROME_DRIVER else Service()
    try:
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)
        driver.get("https://music.gdstudio.org/")
        
        search_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '歌曲搜索')]")))
        driver.execute_script("arguments[0].click();", search_btn)

        keyword = input("\n- 搜歌名: ")
        search_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input.search-input, .layui-layer-content input")))
        search_input.send_keys(keyword + Keys.ENTER)

        try:
            agree = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '同意并继续')]")))
            driver.execute_script("arguments[0].click();", agree)
        except: pass

        time.sleep(3)
        
        rows = driver.find_elements(By.CSS_SELECTOR, ".list-item, tr")
        valid_songs = []
        print("\n" + "="*40)
        idx = 1
        for row in rows:
            text = row.text.strip()
            if not text or "歌曲" in text: continue
            parts = [p.strip() for p in text.split('\n') if p.strip()]
            if len(parts) >= 4:
                print(f"[{idx:<2}] {parts[2]} - {parts[3]}")
                valid_songs.append(row)
                idx += 1

        choice = input("\n- 输入序号播放: ")
        target_idx = int(choice) - 1
        
        if 0 <= target_idx < len(valid_songs):
            print("- 正在抓取 ID 并获取元数据...")
            driver.execute_script("arguments[0].click();", valid_songs[target_idx])
            
            song_id = None
            for _ in range(20):
                logs = driver.get_log('performance')
                for entry in logs:
                    log_data = json.loads(entry['message'])['message']
                    if log_data.get('method') == 'Network.requestWillBeSent':
                        post_data = log_data['params']['request'].get('postData', '')
                        match = re.search(r'id=(\d+)', post_data)
                        if match:
                            song_id = match.group(1); break
                if song_id: break
                time.sleep(0.5)

            driver.quit()
            if song_id: 
                current_playlist = []
                current_song_idx = 0
                play_song(song_id, None)
    except Exception as e:
        handle_error(e, "搜索流程出错")
        if 'driver' in locals(): driver.quit()

def main():
    load_config()
    while True:
        try:
            clear_screen()
            choice = input("\n- 请输入指令: ")
            if choice == '1':
                playlist_flow()
            elif choice == '2':
                search_flow()
            elif choice == '3':
                while True:
                    clear_screen()
                    print("--- 通用设置 ---")
                    print(f"[1] Debug模式): {'ON' if CONFIG['debug_mode'] else 'OFF'}")
                    print(f"[2] 预加载下一首: {'ON' if CONFIG['enable_preload'] else 'OFF'}")
                    print("[B] 返回")
                    c = input("\n- 请选择: ")
                    if c == '1':
                        CONFIG["debug_mode"] = not CONFIG["debug_mode"]
                        save_config()
                    elif c == '2':
                        CONFIG["enable_preload"] = not CONFIG["enable_preload"]
                        save_config()
                    elif c.lower() == 'b':
                        break
            elif choice == '4':
                clear_screen()
                print(f"音效处理引擎: {'已就绪' if effects else '未找到(effects.py)'}")
                print(f"[1] 全局音效开关: {'ON' if CONFIG['enable_effects'] else 'OFF'}")
                print("[2] 进入音效参数设置 (effects.py 界面)")
                print("[B] 返回")
                c = input("\n- 音效设置: ")
                if c == '1':
                    CONFIG["enable_effects"] = not CONFIG["enable_effects"]
                    save_config()
                elif c == '2':
                    if effects:
                        temp_engine = effects.UltimateAudioEngine(sr=44100)
                        tui = effects.UltimateTUI(temp_engine)
                        tui.run()
                    else:
                        print("错误：缺少 effects.py 模块，请检查文件名！")
                        time.sleep(2)
            else:
                print("无效指令"); time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在退出系统...")
            break

if __name__ == "__main__":
    main()