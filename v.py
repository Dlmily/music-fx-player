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
import urllib3
from concurrent.futures import ThreadPoolExecutor

try:
    import effects
except ImportError:
    effects = None

SYSTEM = platform.system()

if SYSTEM == "Windows":
    import msvcrt
else:
    import tty
    import termios
    import select

current_player = None
should_play_next = True
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def cleanup():
    global current_player
    if current_player and current_player.poll() is None:
        try:
            current_player.terminate()
        except:
            pass
    if SYSTEM != "Windows":
        os.system('stty sane 2>/dev/null')

atexit.register(cleanup)

CONFIG_FILE = "app_settings.json"
CACHE_FILE = "playlists_cache.json"

CONFIG = {
    "play_mode": "列表顺序播放",
    "modes": ["单曲循环", "列表顺序播放", "随机播放"],
    "enable_effects": False,
    "debug_mode": False,
    "enable_preload": False,
    "remember_playlists": False,
}

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
                CONFIG["remember_playlists"] = data.get("remember_playlists", False)
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
    data["remember_playlists"] = CONFIG["remember_playlists"]
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def load_playlist_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_playlist_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        if CONFIG.get("debug_mode"):
            print(f"保存缓存失败: {e}")

def update_playlist_in_cache(playlist_id, songs, name=""):
    cache = load_playlist_cache()
    cache[playlist_id] = {"songs": songs, "name": name}
    save_playlist_cache(cache)

def delete_playlist_from_cache(playlist_id):
    cache = load_playlist_cache()
    if playlist_id in cache:
        del cache[playlist_id]
        save_playlist_cache(cache)
        return True
    return False

def get_cached_playlist_ids():
    return list(load_playlist_cache().keys())

def handle_error(e, context=""):
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
    print("欢迎使用网易云音乐播放器 v2.2")
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
            tty.setcbreak(sys.stdin.fileno())  # 关键修改
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

def render_cover(path):
    """显示封面图"""
    if not os.path.exists(path):
        return

    # 尝试使用 chafa
    try:
        # 检查 chafa
        result = subprocess.run(
            ['chafa', '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            subprocess.run(['chafa', '--size', '40x20', path])
            return
    except FileNotFoundError:
        pass   # chafa 未安装，走 Pillow 回退

    # 回退到 Pillow
    try:
        from PIL import Image
    except ImportError:
        return   # 也没有 Pillow，什么也不显示

    try:
        img = Image.open(path).convert('RGB')
        term_width = 40
        aspect = img.height / img.width
        # 终端中每个“▄”字符占用 1 列宽 x 2 行高，因此需要将实际像素高度映射为
        # new_height 个字符行，每行对应 2 个像素高度。
        # 公式：new_height = term_width * aspect / 2
        new_height = max(1, int(term_width * aspect * 0.5))
        # 将图片缩放到 (term_width x new_height*2) 的实际像素
        img = img.resize((term_width, new_height * 2), Image.LANCZOS)
        pixels = img.load()

        for y in range(new_height):
            line_chars = []
            for x in range(term_width):
                r1, g1, b1 = pixels[x, y * 2]                     # 上半部
                r2, g2, b2 = pixels[x, y * 2 + 1]                 # 下半部
                # 前景色 = 上半部颜色，背景色 = 下半部颜色，使用半块字符“▄”
                line_chars.append(
                    f'\033[38;2;{r1};{g1};{b1}m'
                    f'\033[48;2;{r2};{g2};{b2}m'
                    '▄'
                )
            # 输出该行后重置颜色
            print(''.join(line_chars) + '\033[0m')
    except Exception:
        pass

def parse_full_lyrics(main_lrc, sub_lrc):
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
    if not m_dict and main_lrc:
        return [{'time': 0, 'text': line, 'trans': ''} for line in main_lrc.split('\n') if line.strip()]

    s_dict = lrc_to_dict(sub_lrc)
    combined = []
    for t in sorted(m_dict.keys()):
        combined.append({'time': t, 'text': m_dict[t], 'trans': s_dict.get(t, "")})
    return combined

def extract_translator(sub_lrc):
    if not sub_lrc:
        return "未知翻译"
    match = re.search(r'\[by:([^\]]+)\]', sub_lrc)
    if match:
        return match.group(1)
    return "未知翻译"

def get_audio_duration(audio_data):
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        try:
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
            res = requests.get(url, timeout=5, verify=False).json()
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
    def __init__(self, raw_audio_data, engine=None):
        self.raw_audio = io.BytesIO(raw_audio_data)
        self.engine = engine
        self.chunk_size = 4096
        self.is_running = False
        self.queue = []
        self.lock = threading.Lock()

    def process_stream(self):
        import numpy as np
        from scipy.io import wavfile
        self.raw_audio.seek(0)
        try:
            self.raw_audio.seek(0)
            sr, audio_data = wavfile.read(self.raw_audio)
            if audio_data.ndim == 1:
                audio_data = np.stack([audio_data, audio_data], axis=1)
            audio_data = audio_data.astype(np.float32) / 32768.0
        except:
            self.raw_audio.seek(0)
            return self.raw_audio.getvalue()

        output_chunks = []
        for i in range(0, len(audio_data), self.chunk_size):
            chunk = audio_data[i:i+self.chunk_size]
            if self.engine:
                processed_chunk = self.engine.process_chunk(chunk)
            else:
                processed_chunk = chunk
            output_chunks.append(processed_chunk)

        processed_audio = np.concatenate(output_chunks, axis=0)
        processed_audio = np.clip(processed_audio * 32768, -32768, 32767).astype(np.int16)
        output_buffer = io.BytesIO()
        wavfile.write(output_buffer, sr, processed_audio)
        output_buffer.seek(0)
        return output_buffer.getvalue()

def play_song(song_id, preload_next_song_id=None):
    global current_player, current_song_idx, should_play_next
    should_play_next = True
    clear_screen()
    print("- 正在并行获取歌曲资源...")

    # -------- 并行准备阶段 --------
    def fetch_metadata():
        res = requests.get(f"https://api.paugram.com/netease/?id={song_id}").json()
        sub_lrc = res.get('sub_lyric', "")
        metadata = {
            'title': res.get('title', '未知歌曲'),
            'artist': res.get('artist', '未知歌手'),
            'translator': extract_translator(sub_lrc),
            'cover': res.get('cover')
        }
        lyrics = parse_full_lyrics(res.get('lyric', ""), sub_lrc)
        audio_link = res.get('link')
        return metadata, lyrics, audio_link

    def download_cover(cover_url):
        if cover_url:
            img_data = requests.get(cover_url).content
            with open('cover.jpg', 'wb') as f:
                f.write(img_data)
            return True
        return False

    def download_audio(audio_link):
        return requests.get(audio_link).content

    def probe_duration(audio_data):
        return get_audio_duration(audio_data)

    # 第一步：获取元数据（必须，因为需要 audio_link）
    metadata, lyrics, audio_link = fetch_metadata()

    # 第二步：并行下载封面、音频，同时探测时长（必须先拿到音频数据）
    with ThreadPoolExecutor(max_workers=3) as executor:
        cover_future = executor.submit(download_cover, metadata['cover']) if metadata['cover'] else None
        audio_future = executor.submit(download_audio, audio_link)
        # 音频下载完成后立即开始探测时长（仍在线程池内顺序依赖）
        audio_raw = audio_future.result()
        duration_future = executor.submit(probe_duration, audio_raw)

    # 等待剩余任务
    cover_downloaded = cover_future.result() if cover_future else False
    duration = duration_future.result()
    print(f"- 音频时长: {format_time(duration)}")

    # -------- 预加载下一首（后台线程，不影响启动）--------
    next_audio_cache = {'data': None, 'lock': threading.Lock()}
    preload_stop = {'flag': False}

    def preload_next_audio():
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

    # -------- 初始化音效引擎 --------
    engine = None
    if CONFIG["enable_effects"] and effects:
        print("- 正在初始化V7音效引擎...")
        engine = effects.UltimateAudioEngine(sr=44100)
        print("- 音效引擎已就绪，准备实时处理。")

    # -------- 播放器控制函数 --------
    def start_player(start_sec):
        global current_player
        if current_player and current_player.poll() is None:
            current_player.terminate()
            time.sleep(0.2)
        return subprocess.Popen(
            ['mpv', '--no-video', '--really-quiet', f'--start={int(start_sec)}', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # 脱离终端会话，防止熄屏暂停
        )

    def feed_audio_with_effects(player, audio_data, engine_ref):
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

    # -------- 启动播放 --------
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

    # ---------- 工具函数 ----------
    def get_term_width():
        try:
            return os.get_terminal_size().columns
        except:
            return 80

    def build_bar(sec, dur):
        w = get_term_width()
        bar_len = max(5, w - 35)
        bar_len = min(30, bar_len)
        percent = min(sec / dur, 1.0) if dur > 0 else 0
        filled = int(bar_len * percent)
        bar = "█" * filled + "░" * (bar_len - filled)
        return f"进度: [{bar}] {format_time(sec)} / {format_time(dur)}"

    def build_lyric_line(lyric_item):
        line = f"    {lyric_item['text']}"
        if lyric_item['trans']:
            line += f"\n    {lyric_item['trans']}"
        return line

    def store_lyric(lyric_item):
        lyric_history.append(build_lyric_line(lyric_item))

    def rebuild_history_until(target_time):
        nonlocal l_idx
        lyric_history.clear()
        l_idx = 0
        while l_idx < len(lyrics) and lyrics[l_idx]['time'] < target_time:
            store_lyric(lyrics[l_idx])
            l_idx += 1

    def write_lyric(lyric_str):
        sys.stdout.write(lyric_str.replace('\n', '\r\n') + "\r\n\r\n")

    # 初始绘制
    clear_screen()
    if cover_downloaded:
        render_cover('cover.jpg')
    print(f"\n🎵 歌曲: {metadata['title']}")
    print(f"👤 歌手: {metadata['artist']}")
    print(f"✍️ 歌词翻译: {metadata['translator']}")
    print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
    print("\n暂停[K]  模式[G]  评论[C]  音效[E]  跳转[J]  上一首[A]  下一首[L]  返回[B]")
    print("=" * 50)

    for stored in lyric_history:
        write_lyric(stored)
    bar = build_bar(elapsed, duration)
    sys.stdout.write(bar)
    sys.stdout.flush()
    need_refresh = False

    # 主循环
    while current_player.poll() is None:
        if need_refresh:
            clear_screen()
            if cover_downloaded:
                render_cover('cover.jpg')
            print(f"\n🎵 歌曲: {metadata['title']}")
            print(f"👤 歌手: {metadata['artist']}")
            print(f"✍️ 歌词翻译: {metadata['translator']}")
            print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
            print("\n暂停[K]  模式[G]  评论[C]  音效[E]  跳转[J]  上一首[A]  下一首[L]  返回[B]")
            print("=" * 50)
            for stored in lyric_history:
                write_lyric(stored)
            bar = build_bar(elapsed, duration)
            sys.stdout.write(bar)
            sys.stdout.flush()
            need_refresh = False

        if not is_paused:
            elapsed = time.time() - start_time

            sys.stdout.write("\r" + build_bar(elapsed, duration))
            sys.stdout.flush()

            while l_idx < len(lyrics) and elapsed >= lyrics[l_idx]['time']:
                sys.stdout.write("\r" + " " * (get_term_width() - 1) + "\r")
                lyric_str = build_lyric_line(lyrics[l_idx])
                write_lyric(lyric_str)
                store_lyric(lyrics[l_idx])
                l_idx += 1
                sys.stdout.write(build_bar(elapsed, duration))
                sys.stdout.flush()

        key = get_key()
        if key:
            k = key.lower()
            if k == 'k':
                is_paused = not is_paused
                if is_paused:
                    sig = subprocess.signal.SIGSTOP if SYSTEM != "Windows" else 19
                    current_player.send_signal(sig)
                    pause_at = time.time()
                    print("\n" + "=" * 30)
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

                    if current_player and current_player.poll() is None:
                        try:
                            current_player.terminate()
                            current_player.wait(timeout=2)
                        except:
                            pass

                    time.sleep(0.5)
                    current_player = start_player(new_elapsed)
                    audio_thread_new = threading.Thread(
                        target=feed_audio_with_effects,
                        args=(current_player, audio_raw, engine_ref),
                        daemon=True
                    )
                    audio_thread_new.start()

                    elapsed = new_elapsed
                    start_time = time.time() - new_elapsed
                    rebuild_history_until(new_elapsed)
                    need_refresh = True
                    time.sleep(0.5)

                except ValueError:
                    print("- 格式错误，请输入 数字*数字 或纯秒数。")
                    time.sleep(1)
                    need_refresh = True

            elif k == 'a':
                if len(current_playlist) > 1:
                    current_song_idx = (current_song_idx - 1) % len(current_playlist)
                    manual_next_song_id = current_playlist[current_song_idx]['id']
                    manual_skip = True
                    break
            elif k == 'l':
                if len(current_playlist) > 1:
                    current_song_idx = (current_song_idx + 1) % len(current_playlist)
                    manual_next_song_id = current_playlist[current_song_idx]['id']
                    manual_skip = True
                    break

            elif k == 'b':
                should_play_next = False
                preload_stop['flag'] = True
                current_player.terminate()
                break

    if os.path.exists('cover.jpg'):
        os.remove('cover.jpg')

    preload_stop['flag'] = True
    time.sleep(0.5)

    if not should_play_next or len(current_playlist) <= 1:
        return

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

def fetch_playlist_songs(playlist_id):
    """通过 API 获取歌单歌曲列表，返回统一格式列表，失败返回 None"""
    try:
        clear_screen()
        print(f"- 正在获取歌单内歌曲... (ID: {playlist_id})")
        api_url = f"https://oiapi.net/api/NeteasePlaylistDetail&id={playlist_id}"
        response = requests.get(api_url, timeout=10)
        data = response.json()

        if data.get('code') != 1:
            print(f"获取失败: {data.get('message', '未知错误')}")
            time.sleep(2)
            return None

        songs = data.get('data', [])
        if not songs:
            print("歌单为空或获取失败")
            time.sleep(2)
            return None

        result = []
        for s in songs:
            artists = s.get('artists', [])
            artist_names = ', '.join([a.get('name', '未知') for a in artists]) if artists else '未知歌手'
            result.append({
                'id': s.get('id'),
                'name': s.get('name', '未知歌曲'),
                'artist': artist_names
            })
        return result
    except Exception as e:
        handle_error(e, "获取歌单失败")
        return None

def show_songs_and_play(playlist_id, songs):
    global current_playlist, current_song_idx

    page = 0
    page_size = 15
    total = len(songs)

    while True:
        clear_screen()
        total_pages = (total + page_size - 1) // page_size
        start = page * page_size
        end = min(start + page_size, total)

        print(f"\n- 歌单 ID: {playlist_id}，共 {total} 首歌曲 (第 {page+1} 页，共 {total_pages} 页)")
        print("=" * 60)

        for i in range(start, end):
            song = songs[i]
            print(f"[{i+1:<3}] {song['name']}")
            print(f"      歌手: {song['artist']}")
            print("-" * 60)

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
            if 0 <= target_idx < total:
                current_playlist = [{'id': s['id'], 'name': s['name']} for s in songs]
                current_song_idx = target_idx

                song_id = songs[target_idx]['id']
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

def manage_playlist_cache():
    while True:
        clear_screen()
        print("--- 歌单缓存管理 ---")
        cached_ids = get_cached_playlist_ids()
        if cached_ids:
            print("已缓存的歌单ID:")
            for pid in cached_ids:
                cache = load_playlist_cache().get(pid, {})
                name = cache.get('name', '')
                display = pid
                if name:
                    display += f" ({name})"
                print(f"  {display}")
        else:
            print("暂无缓存歌单")
        print("\n[1] 添加/更新歌单")
        print("[2] 删除已存歌单")
        print("[B] 返回")
        choice = input("请选择: ").strip().lower()

        if choice == 'b':
            return
        elif choice == '1':
            pid = input("请输入歌单 ID: ").strip()
            if not pid:
                continue
            songs = fetch_playlist_songs(pid)
            if songs:
                update_playlist_in_cache(pid, songs, name="")
                print(f"歌单 {pid} 已缓存。")
                time.sleep(1)
        elif choice == '2':
            if not cached_ids:
                print("没有可删除的歌单")
                time.sleep(1)
                continue
            print("输入要删除的歌单序号 (或 B 返回):")
            for idx, pid in enumerate(cached_ids, 1):
                print(f"[{idx}] {pid}")
            del_choice = input("> ").strip()
            if del_choice.lower() == 'b':
                continue
            try:
                idx = int(del_choice) - 1
                if 0 <= idx < len(cached_ids):
                    pid_to_delete = cached_ids[idx]
                    confirm = input(f"确认删除歌单 {pid_to_delete} ? (y/n): ").strip().lower()
                    if confirm == 'y':
                        delete_playlist_from_cache(pid_to_delete)
                        print("已删除。")
                        time.sleep(1)
                else:
                    print("序号无效")
                    time.sleep(1)
            except ValueError:
                print("无效输入")
                time.sleep(1)

def playlist_flow():
    global current_playlist, current_song_idx
    clear_screen()

    use_cache = CONFIG.get("remember_playlists", False)
    cached_ids = get_cached_playlist_ids() if use_cache else []

    if use_cache and cached_ids:
        print("已存储的歌单：")
        for idx, pid in enumerate(cached_ids, 1):
            cache_data = load_playlist_cache().get(pid, {})
            name = cache_data.get('name', '')
            display = pid
            if name:
                display += f" ({name})"
            print(f"[{idx}] {display}")
        print("[C] 管理歌单缓存")
        print("[N] 输入新歌单 ID")
        print("[B] 返回主菜单")
        choice = input("\n请选择: ").strip()

        if choice.lower() == 'b':
            return
        elif choice.lower() == 'c':
            manage_playlist_cache()
            return
        elif choice.lower() == 'n':
            playlist_id = input("请输入新歌单 ID: ").strip()
            if not playlist_id:
                return
            songs = fetch_playlist_songs(playlist_id)
            if not songs:
                return
            if use_cache:
                save = input("是否将此歌单保存到缓存？(y/n): ").strip().lower()
                if save == 'y':
                    update_playlist_in_cache(playlist_id, songs, name="")
                    print("已保存。")
            show_songs_and_play(playlist_id, songs)
            return
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(cached_ids):
                    playlist_id = cached_ids[idx]
                    cache_entry = load_playlist_cache().get(playlist_id, {})
                    songs = cache_entry.get('songs', [])
                    if not songs:
                        print("缓存中没有歌曲数据，请重新获取。")
                        time.sleep(2)
                        return
                    show_songs_and_play(playlist_id, songs)
                    return
                else:
                    print("无效序号")
                    time.sleep(2)
                    return
            except ValueError:
                playlist_id = choice
                if not playlist_id.isdigit():
                    print("无效输入")
                    time.sleep(2)
                    return
                songs = fetch_playlist_songs(playlist_id)
                if not songs:
                    return
                if use_cache:
                    save = input("是否将此歌单保存到缓存？(y/n): ").strip().lower()
                    if save == 'y':
                        update_playlist_in_cache(playlist_id, songs, name="")
                show_songs_and_play(playlist_id, songs)
                return
    else:
        playlist_id = input("- 请输入歌单 ID: ").strip()
        if not playlist_id:
            print("歌单 ID 不能为空")
            time.sleep(2)
            return
        songs = fetch_playlist_songs(playlist_id)
        if not songs:
            return
        if use_cache:
            save = input("是否将此歌单保存到缓存？(y/n): ").strip().lower()
            if save == 'y':
                update_playlist_in_cache(playlist_id, songs, name="")
        show_songs_and_play(playlist_id, songs)

def search_flow():
    """使用 no0a API 搜索歌曲并播放"""
    clear_screen()
    keyword = input("- 搜歌名: ").strip()
    if not keyword:
        print("搜索关键词不能为空")
        time.sleep(2)
        return

    print("- 正在搜索...")
    try:
        api_url = f"https://api.no0a.cn/api/cloudmusic/search/{keyword}"
        resp = requests.get(api_url, timeout=10)
        data = resp.json()
    except Exception as e:
        handle_error(e, "搜索请求失败，请检查网络。")
        return

    if data.get("status") != 1:
        print(f"搜索失败: {data.get('message', '未知错误')}")
        time.sleep(2)
        return

    results = data.get("results", [])
    if not results:
        print("未找到相关歌曲。")
        time.sleep(2)
        return

    # 构建当前播放列表（将搜索结果作为歌单，支持上下曲切换）
    global current_playlist, current_song_idx
    current_playlist = []
    for item in results:
        song_id = item.get("id")
        song_name = item.get("name", "未知歌曲")
        artists = [a.get("name", "未知") for a in item.get("artist", [])]
        artist_str = ", ".join(artists) if artists else "未知歌手"
        current_playlist.append({"id": song_id, "name": song_name})

    # 显示搜索结果
    clear_screen()
    print(f"\n- 搜索结果（{len(results)} 首歌曲）:")
    print("=" * 60)
    for idx, item in enumerate(results):
        song_name = item.get("name", "未知歌曲")
        artists = [a.get("name", "未知") for a in item.get("artist", [])]
        artist_str = ", ".join(artists) if artists else "未知歌手"
        print(f"[{idx+1:<3}] {song_name}")
        print(f"      歌手: {artist_str}")
        print("-" * 60)

    choice = input("\n- 输入序号播放 (B 返回): ").strip()
    if choice.lower() == 'b':
        return

    try:
        target_idx = int(choice) - 1
        if 0 <= target_idx < len(results):
            current_song_idx = target_idx
            song_id = current_playlist[target_idx]['id']

            # 预加载下一首（如果开启且有多首）
            if CONFIG["enable_preload"] and len(current_playlist) > 1:
                next_idx = (target_idx + 1) % len(current_playlist)
                next_song_id = current_playlist[next_idx]['id']
            else:
                next_song_id = None

            play_song(song_id, next_song_id)
        else:
            print("序号无效")
            time.sleep(2)
    except ValueError:
        print("请输入有效的数字")
        time.sleep(2)

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
                    print(f"[1] Debug模式: {'ON' if CONFIG['debug_mode'] else 'OFF'}")
                    print(f"[2] 预加载下一首: {'ON' if CONFIG['enable_preload'] else 'OFF'}")
                    print(f"[3] 歌单记忆: {'ON' if CONFIG['remember_playlists'] else 'OFF'} (缓存{len(get_cached_playlist_ids())}个)")
                    print("[4] 清空歌单缓存")
                    print("[B] 返回")
                    c = input("\n- 请选择: ")
                    if c == '1':
                        CONFIG["debug_mode"] = not CONFIG["debug_mode"]
                        save_config()
                    elif c == '2':
                        CONFIG["enable_preload"] = not CONFIG["enable_preload"]
                        save_config()
                    elif c == '3':
                        CONFIG["remember_playlists"] = not CONFIG["remember_playlists"]
                        save_config()
                    elif c == '4':
                        confirm = input("确定清空所有缓存歌单？(y/n): ").strip().lower()
                        if confirm == 'y':
                            save_playlist_cache({})
                            print("缓存已清空。")
                            time.sleep(1)
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