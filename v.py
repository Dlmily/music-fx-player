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
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import ssl
import struct
import text as gd_decrypt

ssl._create_default_https_context = ssl._create_unverified_context
try:
    import effects
except ImportError:
    effects = None

# -------------------- 随机 User-Agent --------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def get_default_headers():
    return {"User-Agent": get_random_user_agent()}

# -------------------- music.gdstudio.org 直链获取 --------------------
import hashlib
from urllib.parse import urlencode

GD_BASE_URL = "https://music.gdstudio.org"
GD_API_PATH = "/api.php"
GD_TIME_PATH = "/time"

def build_api_url_gd(song_id, source="netease", br=320, s=None):
    """构建 API URL，s 参数由外部传入"""
    rand = ''.join(str((int(time.time() * 1000) % 10000) + i) for i in range(15))
    callback = f"jQuery{rand}_{int(time.time() * 1000)}"
    params = {
        "callback": callback,
        "types": "url",
        "id": song_id,
        "source": source,
        "br": br,
        "s": s,
    }
    return GD_BASE_URL + GD_API_PATH + "?" + urlencode(params)

def fetch_song_url_gd(song_id, source="netease", br=320):
    """
    使用 text.py 模块生成 s 参数，并请求直链。
    若 s 参数生成失败或 API 请求失败，自动重试最多 3 次。
    """
    domain = GD_BASE_URL.replace("https://", "").replace("http://", "")
    last_error = None

    for attempt in range(3):
        session = requests.Session()
        session.headers.update({"User-Agent": get_random_user_agent()})
        # 先访问首页建立会话（text.py 中的函数依赖此会话）
        try:
            session.get(GD_BASE_URL, timeout=5)
        except Exception as e:
            last_error = e
            continue

        # 获取时间前缀
        time_prefix = gd_decrypt.get_server_time_prefix(session)
        if time_prefix is None:
            last_error = "获取时间前缀失败"
            continue

        # 获取版本号
        version = gd_decrypt.get_version(session)
        if version is None:
            last_error = "获取版本号失败"
            continue

        # 生成 s 参数
        s_param = gd_decrypt.generate_s_param(time_prefix, domain, version, song_id)
        if s_param is None:
            last_error = "生成 s 参数失败"
            continue

        # 构建完整 API URL
        api_url = build_api_url_gd(song_id, source, br, s_param)
        headers = {
            "User-Agent": get_random_user_agent(),
            "Referer": GD_BASE_URL + "/",
            "Accept": "*/*"
        }

        try:
            resp = session.get(api_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue

            match = re.search(r'\(({.*})\)', resp.text, re.DOTALL)
            if not match:
                last_error = "无法解析 JSONP 响应"
                continue

            data = json.loads(match.group(1))
            url = data.get("url")
            if url:
                return url
            else:
                last_error = "响应中无 url 字段"
        except Exception as e:
            last_error = str(e)
            continue

    # 所有重试均失败
    if CONFIG.get("debug_mode"):
        print(f"[fetch_song_url_gd] 重试 3 次后失败，最后错误: {last_error}")
    return None

# -------------------- 从 xingon.chat 获取元数据和 fee --------------------
def get_song_metadata_from_xingon(song_id):
    """
    获取歌曲元数据，失败时自动重试 3 次。
    返回 {'title','artist','cover','fee','duration_sec'} 或 None
    """
    url = f"https://www.xingon.chat/song/detail?ids={song_id}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10, headers=get_default_headers())
            resp.raise_for_status()
            data = resp.json()
            songs = data.get('songs', [])
            if not songs:
                continue
            song = songs[0]
            title = song.get('name', '未知歌曲')
            if song.get('alia'):
                title += f" ({','.join(song['alia'])})"
            artists = song.get('ar', [])
            artist = ', '.join([a['name'] for a in artists]) if artists else '未知歌手'
            cover = song.get('al', {}).get('picUrl', '')
            fee = song.get('fee', 0)
            duration_ms = song.get('dt', 0)
            duration_sec = duration_ms / 1000.0
            return {
                'title': title,
                'artist': artist,
                'cover': cover,
                'fee': fee,
                'duration_sec': duration_sec
            }
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"获取 xingon 元数据尝试 {attempt+1}/3 失败: {e}")
            time.sleep(0.5)
    return None

def get_audio_url_by_fee(song_id, fee):
    """根据 fee 返回可播放的直链（下载地址）"""
    if fee == 1:
        return fetch_song_url_gd(song_id)
    else:
        # 备用接口
        return f"http://v.api.aa1.cn/api/wymusic/index.php?id={song_id}"

def fetch_lyrics_only(song_id):
    """
    仅获取歌词（按 h 时调用），失败时自动重试 3 次。
    返回 (lyrics列表, translator)
    """
    url = f"https://api.paugram.com/netease/?id={song_id}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10, verify=False, headers=get_default_headers())
            resp.raise_for_status()
            data = resp.json()
            main_lrc = data.get('lyric', '')
            sub_lrc = data.get('sub_lyric', '')
            lyrics = parse_full_lyrics(main_lrc, sub_lrc)
            translator = extract_translator(sub_lrc)
            return lyrics, translator
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"获取歌词尝试 {attempt+1}/3 失败: {e}")
            time.sleep(0.5)
    return [], "未知翻译"

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
    for f in os.listdir('.'):
        if f.startswith('cover_') and f.endswith('.jpg'):
            try:
                os.remove(f)
            except:
                pass

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

preload_cache = {}
preload_cache_lock = threading.Lock()
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
    print("欢迎使用网易云音乐播放器 v3.0")
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
            tty.setcbreak(sys.stdin.fileno())
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
    if not os.path.exists(path):
        return
    try:
        result = subprocess.run(
            ['chafa', '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            subprocess.run(['chafa', '--size', '40x20', path])
            return
    except FileNotFoundError:
        pass
    try:
        from PIL import Image
    except ImportError:
        return
    try:
        img = Image.open(path).convert('RGB')
        term_width = 40
        aspect = img.height / img.width
        new_height = max(1, int(term_width * aspect * 0.5))
        img = img.resize((term_width, new_height * 2), Image.LANCZOS)
        pixels = img.load()
        for y in range(new_height):
            line_chars = []
            for x in range(term_width):
                r1, g1, b1 = pixels[x, y * 2]
                r2, g2, b2 = pixels[x, y * 2 + 1]
                line_chars.append(
                    f'\033[38;2;{r1};{g1};{b1}m'
                    f'\033[48;2;{r2};{g2};{b2}m'
                    '▄'
                )
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

def show_comment_ui(song_id, metadata, cover_path=None):
    page = 0
    limit = 15
    while True:
        clear_screen()
        if cover_path and os.path.exists(cover_path):
            render_cover(cover_path)
        print(f"\n🎵 歌曲: {metadata['title']} | {metadata['artist']}")
        print(f"上一页[a]     下一页[l]       返回[B] (第 {page+1} 页)")
        print("="*50)
        url = f"https://www.xingon.chat/comment/music?id={song_id}&limit={limit}&offset={page*limit}"
        try:
            res = requests.get(url, timeout=5, verify=False, headers=get_default_headers()).json()
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

def get_wav_header_f32le(sr=44100, channels=2):
    """生成流式 WAV Header，声明后续数据为 32位浮点 PCM，长度未知(0xFFFFFFFF)"""
    byte_rate = sr * channels * 4
    block_align = channels * 4
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 0xFFFFFFFF, b'WAVE',
        b'fmt ', 16, 3, channels, sr, byte_rate, block_align, 32, # 3 = IEEE Float
        b'data', 0xFFFFFFFF)
    return header

class RealtimeAudioProcessor:
    def __init__(self, raw_audio_data, engine=None):
        self.raw_audio_data = raw_audio_data
        self.engine = engine
        # 4096 frames (约 92ms)，既能保证 IIR 滤波器状态稳定，又不会引起明显延迟
        self.chunk_size = 4096 
        self.is_running = False
        self.queue = []
        self.lock = threading.Lock()

    def process_stream(self):
        import numpy as np
        import io
        
        # 1. 使用 pydub 解码 MP3/FLAC/WAV 等任意格式
        try:
            from pydub import AudioSegment
            # 从内存字节流读取音频 (自动识别 MP3 格式)
            audio_segment = AudioSegment.from_file(io.BytesIO(self.raw_audio_data))
            sr = audio_segment.frame_rate
            
            # 强制转换为双声道，以匹配我们的音效引擎
            audio_segment = audio_segment.set_channels(2)
            
            # 提取 PCM 数据并转换为 float32 (-1.0 到 1.0)
            samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
            max_val = float(2**(audio_segment.sample_width * 8 - 1))
            samples /= max_val
            
            # 重塑为 (N, 2) 的立体声矩阵
            audio_data = samples.reshape(-1, 2)
            
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"[!] 音频解码失败 (请确保已安装 pydub 和 ffmpeg): {e}")
            # 解码失败时，直接返回原始 MP3 数据给 mpv 播放，保证至少能出声
            return self.raw_audio_data

        # 2. 分块送入音效引擎
        output_chunks = []
        for i in range(0, len(audio_data), self.chunk_size):
            chunk = audio_data[i:i+self.chunk_size]
            
            # 如果末尾数据不足一个 chunk，补零以防止 IIR 滤波器状态异常
            if len(chunk) < self.chunk_size:
                pad = np.zeros((self.chunk_size - len(chunk), 2), dtype=np.float32)
                chunk = np.vstack([chunk, pad])
                
            if self.engine:
                processed_chunk = self.engine.process_chunk(chunk)
                # 切除补零的部分
                processed_chunk = processed_chunk[:len(audio_data) - i]
            else:
                processed_chunk = chunk
                
            output_chunks.append(processed_chunk)
            
        processed_audio = np.concatenate(output_chunks, axis=0)
        
        # 3. 将处理后的音频重新编码为 WAV 格式喂给 mpv
        try:
            from scipy.io import wavfile
            # 限制在 -1.0 到 1.0 之间，防止混响过大导致爆音
            processed_audio = np.clip(processed_audio, -1.0, 1.0)
            # 转换为 int16 以获得最大的兼容性
            audio_int16 = (processed_audio * 32767).astype(np.int16)
            
            output_buffer = io.BytesIO()
            wavfile.write(output_buffer, sr, audio_int16)
            output_buffer.seek(0)
            return output_buffer.getvalue()
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"[!] 音频重编码失败: {e}")
            return self.raw_audio_data

def download_cover(song_id, cover_url):
    if not cover_url:
        return None
    cover_path = f"cover_{song_id}.jpg"
    try:
        img_data = requests.get(cover_url, headers=get_default_headers()).content
        with open(cover_path, 'wb') as f:
            f.write(img_data)
        return cover_path
    except Exception as e:
        if CONFIG.get("debug_mode"):
            print(f"下载封面失败: {e}")
        return None

def download_audio(audio_link):
    if not audio_link:
        return None
    headers = {"Referer": "https://music.163.com/", "User-Agent": get_random_user_agent()}
    try:
        return requests.get(audio_link, headers=headers, timeout=15).content
    except Exception as e:
        if CONFIG.get("debug_mode"):
            print(f"下载音频失败: {e}")
        return None

# -------------------- 核心播放函数 --------------------
def play_song(song_id, preload_next_song_id=None, preloaded_data=None):
    global current_player, current_song_idx, should_play_next
    should_play_next = True
    clear_screen()
    print("- 正在准备歌曲资源...")

    cover_path = None
    if preloaded_data:
        print("✓ 使用预加载数据，快速切换...")
        metadata = preloaded_data['metadata']
        audio_raw = preloaded_data['audio_raw']
        cover_path = preloaded_data.get('cover_path')
        duration = preloaded_data['duration']
        lyrics = []
        lyrics_loaded = False
        translator = "未知翻译"
        with preload_cache_lock:
            if song_id in preload_cache:
                del preload_cache[song_id]
    else:
        # 1. 从 xingon 获取元数据
        meta = get_song_metadata_from_xingon(song_id)
        if not meta:
            print("[-] 无法获取歌曲基本信息（已重试3次）")
            time.sleep(2)
            return
        metadata = {
            'title': meta['title'],
            'artist': meta['artist'],
            'cover': meta['cover'],
        }
        duration = meta['duration_sec']
        fee = meta['fee']
        # 2. 根据 fee 获取音频直链并下载
        audio_link = get_audio_url_by_fee(song_id, fee)
        if not audio_link:
            print("[-] 无法获取音频直链")
            time.sleep(2)
            return
        # 并行下载封面和音频
        with ThreadPoolExecutor(max_workers=2) as executor:
            cover_future = executor.submit(download_cover, song_id, metadata['cover']) if metadata['cover'] else None
            audio_future = executor.submit(download_audio, audio_link)
            audio_raw = audio_future.result()
            if not audio_raw:
                print("[-] 下载音频失败")
                return
            if cover_future:
                cover_path = cover_future.result()
        lyrics = []
        lyrics_loaded = False
        translator = "未知翻译"

    print(f"- 音频时长: {format_time(duration)}")

    # ------------------- 预加载下一首 -------------------
    def preload_full_next_song(next_id):
        with preload_cache_lock:
            if next_id in preload_cache:
                return
        try:
            meta = get_song_metadata_from_xingon(next_id)
            if not meta:
                return
            audio_link = get_audio_url_by_fee(next_id, meta['fee'])
            if not audio_link:
                return
            with ThreadPoolExecutor(max_workers=2) as ex:
                cover_future = ex.submit(download_cover, next_id, meta['cover']) if meta['cover'] else None
                audio_future = ex.submit(download_audio, audio_link)
                audio_raw = audio_future.result()
                if not audio_raw:
                    return
                duration = get_audio_duration(audio_raw)
                cover_path = cover_future.result() if cover_future else None
            with preload_cache_lock:
                preload_cache[next_id] = {
                    'metadata': {'title': meta['title'], 'artist': meta['artist'], 'cover': meta['cover']},
                    'audio_raw': audio_raw,
                    'cover_path': cover_path,
                    'duration': duration,
                }
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"预加载下一首失败: {e}")

    # ------------------- 播放器相关变量 -------------------
    engine = None
    if CONFIG["enable_effects"] and effects:
        print("- 正在初始化音效引擎...")
        try:
            engine = effects.UltimateAudioEngine(sr=44100)
            engine.warmup() 
            print("✓ 引擎预热完成")
        except Exception as e:
            print(f"✗ 音效引擎初始化失败: {e}")
            engine = None

    def start_player():
        global current_player
        if current_player and current_player.poll() is None:
            current_player.terminate()
            time.sleep(0.2)
        # 增加 --cache=yes 和 --cache-secs=10，防止流式输入延迟导致 mpv 饿死回退
        return subprocess.Popen(
            ['mpv', '--no-video', '--really-quiet', '--cache=yes', '--cache-secs=10', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    
    def feed_audio_with_effects(player, audio_data, engine_ref, start_sec=0):
        # 每次开始播放或跳转前，重置引擎状态，防止 IIR 残留导致爆音
        if engine_ref['engine']:
            engine_ref['engine'].reset_state()
            
        try:
            # -ss 必须放在 -i 后面，否则 ffmpeg 会对 pipe 进行无效的 seek 导致卡死
            ffmpeg_cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-i', 'pipe:0',
                '-ss', str(start_sec),  
                '-f', 'f32le', '-acodec', 'pcm_f32le', '-ar', '44100', '-ac', '2',
                'pipe:1'
            ]
            
            decoder = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
    
            def feed_ffmpeg():
                try:
                    decoder.stdin.write(audio_data)
                    decoder.stdin.close()
                except:
                    pass
            threading.Thread(target=feed_ffmpeg, daemon=True).start()
    
            if engine_ref['engine']:
                header = get_wav_header_f32le(44100, 2)
                player.stdin.write(header)
                player.stdin.flush()
    
                chunk_frames = 4096
                chunk_bytes = chunk_frames * 2 * 4 
                
                while True:
                    raw_pcm = decoder.stdout.read(chunk_bytes)
                    if not raw_pcm:
                        break
                    
                    original_len = len(raw_pcm)
                    if original_len < chunk_bytes:
                        raw_pcm += b'\x00' * (chunk_bytes - original_len)
                        
                    pcm_array = np.frombuffer(raw_pcm, dtype=np.float32).reshape(-1, 2)
                    
                    # 送入极速版音效引擎
                    processed_pcm = engine_ref['engine'].process_chunk(pcm_array)
                    
                    # 核心防破音保险：在写入 mpv 前，强制限制在 [-1.0, 1.0]
                    processed_pcm = np.clip(processed_pcm, -1.0, 1.0)
                    
                    out_bytes = processed_pcm.tobytes()
                    player.stdin.write(out_bytes[:original_len])
                    player.stdin.flush()
            else:
                chunk_size = 8192
                for i in range(0, len(audio_data), chunk_size):
                    player.stdin.write(audio_data[i:i+chunk_size])
                    player.stdin.flush()
    
            try:
                player.stdin.close()
            except:
                pass
            
            decoder.wait()
    
        except FileNotFoundError:
            if CONFIG.get("debug_mode"):
                print("[!] 未找到 ffmpeg，跳过音效处理，直接播放原始 MP3。")
            chunk_size = 8192
            for i in range(0, len(audio_data), chunk_size):
                try:
                    player.stdin.write(audio_data[i:i+chunk_size])
                    player.stdin.flush()
                except:
                    break
        except Exception as e:
            if CONFIG.get("debug_mode"):
                print(f"音频送流错误: {e}")

    # ------------------- 歌词相关 -------------------
    lyric_history = []
    l_idx = 0
    show_lyrics = False
    lyrics_data = []
    translator_name = "按H显示"
    lyrics_fetched = False

    def fetch_lyrics_on_demand():
        nonlocal lyrics_data, translator_name, lyrics_fetched, l_idx, lyric_history
        if lyrics_fetched:
            return
        print("\n- 正在获取歌词...")
        lyrics_data, translator_name = fetch_lyrics_only(song_id)  # 自带重试
        lyrics_fetched = True
        if not lyrics_data:
            print("- 没有歌词")
        else:
            print("- 歌词获取成功")
        time.sleep(0.5)

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
        nonlocal l_idx, lyric_history
        lyric_history.clear()
        l_idx = 0
        if not lyrics_data:
            return
        while l_idx < len(lyrics_data) and lyrics_data[l_idx]['time'] < target_time:
            store_lyric(lyrics_data[l_idx])
            l_idx += 1

    def write_lyric(lyric_str):
        sys.stdout.write(lyric_str.replace('\n', '\r\n') + "\r\n\r\n")

    # ------------------- 开始播放 -------------------
    elapsed = 0
    current_player = start_player()  # <--- 去掉 elapsed 参数
    engine_ref = {'engine': engine}
    audio_thread = threading.Thread(
        target=feed_audio_with_effects,
        args=(current_player, audio_raw, engine_ref, elapsed),  # <--- 把 elapsed 传到这里
        daemon=True
    )
    audio_thread.start()

    start_time = time.time()
    is_paused = False
    pause_at = 0
    need_refresh = True

    clear_screen()
    if cover_path and os.path.exists(cover_path):
        render_cover(cover_path)
    print(f"\n🎵 歌曲: {metadata['title']}")
    print(f"👤 歌手: {metadata['artist']}")
    print(f"✍️ 歌词翻译: {translator_name}")
    print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
    print("\n暂停[K]  模式[G]  评论[C]  音效[E]  跳转[J]  上一首[A]  下一首[L]  显示歌词[H]  返回[B]")
    print("=" * 50)
    bar = build_bar(elapsed, duration)
    sys.stdout.write(bar)
    sys.stdout.flush()
    need_refresh = False

    preload_triggered = False

    while current_player.poll() is None:
        if need_refresh:
            clear_screen()
            if cover_path and os.path.exists(cover_path):
                render_cover(cover_path)
            print(f"\n🎵 歌曲: {metadata['title']}")
            print(f"👤 歌手: {metadata['artist']}")
            print(f"✍️ 歌词翻译: {translator_name}")
            print(f"⚙️  当前歌曲模式：{CONFIG['play_mode']}")
            print("\n暂停[K]  模式[G]  评论[C]  音效[E]  跳转[J]  上一首[A]  下一首[L]  显示歌词[H]  返回[B]")
            print("=" * 50)
            if show_lyrics and lyrics_fetched:
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

            if show_lyrics and lyrics_fetched and lyrics_data:
                while l_idx < len(lyrics_data) and elapsed >= lyrics_data[l_idx]['time']:
                    sys.stdout.write("\r" + " " * (get_term_width() - 1) + "\r")
                    lyric_str = build_lyric_line(lyrics_data[l_idx])
                    write_lyric(lyric_str)
                    store_lyric(lyrics_data[l_idx])
                    l_idx += 1
                    sys.stdout.write(build_bar(elapsed, duration))
                    sys.stdout.flush()

            if CONFIG["enable_preload"] and preload_next_song_id and not preload_triggered:
                remaining = duration - elapsed
                if remaining <= 30.0:
                    preload_triggered = True
                    threading.Thread(target=preload_full_next_song, args=(preload_next_song_id,), daemon=True).start()

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
                show_comment_ui(song_id, metadata, cover_path)
                need_refresh = True

            elif k == 'g':
                idx = (CONFIG["modes"].index(CONFIG["play_mode"]) + 1) % 3
                CONFIG["play_mode"] = CONFIG["modes"][idx]
                save_config()
                need_refresh = True

            elif k == 'h':
                if not lyrics_fetched:
                    fetch_lyrics_on_demand()
                show_lyrics = not show_lyrics
                if show_lyrics and lyrics_fetched:
                    rebuild_history_until(elapsed)
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
                    current_player = start_player()  # <--- 去掉 new_elapsed 参数
                    audio_thread_new = threading.Thread(
                        target=feed_audio_with_effects,
                        args=(current_player, audio_raw, engine_ref, new_elapsed),  # <--- 传 new_elapsed
                        daemon=True
                    )
                    audio_thread_new.start()

                    elapsed = new_elapsed
                    start_time = time.time() - new_elapsed
                    if lyrics_fetched:
                        rebuild_history_until(new_elapsed)
                    else:
                        lyric_history.clear()
                        l_idx = 0
                    need_refresh = True
                    time.sleep(0.5)

                except ValueError:
                    print("- 格式错误，请输入 数字*数字 或纯秒数。")
                    time.sleep(1)
                    need_refresh = True

            elif k == 'a':
                if len(current_playlist) > 1:
                    current_song_idx = (current_song_idx - 1) % len(current_playlist)
                    next_song_id = current_playlist[current_song_idx]['id']
                    next_next_idx = (current_song_idx - 1) % len(current_playlist) if CONFIG["enable_preload"] and len(current_playlist) > 1 else None
                    next_next_song_id = current_playlist[next_next_idx]['id'] if next_next_idx is not None else None
                    should_play_next = True
                    current_player.terminate()
                    time.sleep(0.2)
                    play_song(next_song_id, next_next_song_id)
                    return
            elif k == 'l':
                if len(current_playlist) > 1:
                    current_song_idx = (current_song_idx + 1) % len(current_playlist)
                    next_song_id = current_playlist[current_song_idx]['id']
                    next_next_idx = (current_song_idx + 1) % len(current_playlist) if CONFIG["enable_preload"] and len(current_playlist) > 1 else None
                    next_next_song_id = current_playlist[next_next_idx]['id'] if next_next_idx is not None else None
                    should_play_next = True
                    current_player.terminate()
                    time.sleep(0.2)
                    play_song(next_song_id, next_next_song_id)
                    return

            elif k == 'b':
                should_play_next = False
                current_player.terminate()
                break

    if cover_path and os.path.exists(cover_path):
        try:
            os.remove(cover_path)
        except:
            pass
    time.sleep(0.5)

    if not should_play_next or len(current_playlist) <= 1:
        return

    # 下一首切换逻辑（优先使用缓存）
    if CONFIG['play_mode'] == '单曲循环':
        play_song(song_id, preload_next_song_id)
    elif CONFIG['play_mode'] == '列表顺序播放':
        next_idx = (current_song_idx + 1) % len(current_playlist)
        current_song_idx = next_idx
        next_song_id = current_playlist[next_idx]['id']
        next_next_idx = (next_idx + 1) % len(current_playlist)
        next_next_song_id = current_playlist[next_next_idx]['id'] if CONFIG["enable_preload"] and len(current_playlist) > 1 else None

        preloaded = None
        with preload_cache_lock:
            if next_song_id in preload_cache:
                preloaded = preload_cache[next_song_id]
        if preloaded:
            play_song(next_song_id, next_next_song_id, preloaded_data=preloaded)
        else:
            play_song(next_song_id, next_next_song_id)

    elif CONFIG['play_mode'] == '随机播放':
        random_idx = random.randint(0, len(current_playlist) - 1)
        current_song_idx = random_idx
        random_song_id = current_playlist[random_idx]['id']
        next_random_idx = random.randint(0, len(current_playlist) - 1)
        next_random_song_id = current_playlist[next_random_idx]['id'] if CONFIG["enable_preload"] and len(current_playlist) > 1 else None

        preloaded = None
        with preload_cache_lock:
            if random_song_id in preload_cache:
                preloaded = preload_cache[random_song_id]
        if preloaded:
            play_song(random_song_id, next_random_song_id, preloaded_data=preloaded)
        else:
            play_song(random_song_id, next_random_song_id)

# -------------------- 歌单及搜索流程 --------------------
def fetch_playlist_songs(playlist_id):
    try:
        clear_screen()
        print(f"- 正在获取歌单内歌曲... (ID: {playlist_id})")
        api_url = f"https://oiapi.net/api/NeteasePlaylistDetail&id={playlist_id}"
        response = requests.get(api_url, timeout=10, headers=get_default_headers())
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
    clear_screen()
    keyword = input("- 搜歌名: ").strip()
    if not keyword:
        return

    print("- 正在搜索...")
    try:
        resp = requests.get(
            "https://music.gdstudio.org/api.php",
            params={
                "types": "search",
                "key": keyword,
                "source": "netease"
            },
            timeout=10,
            headers=get_default_headers()
        )
        data = resp.json()
    except Exception as e:
        handle_error(e, "搜索失败")
        return

    if not data or len(data) == 0:
        print("未找到相关歌曲")
        time.sleep(2)
        return

    global current_playlist, current_song_idx
    current_playlist = []
    results = []

    for item in data:
        if isinstance(item, dict) and 'id' in item:
            results.append(item)
            current_playlist.append({
                'id': item['id'],
                'name': item.get('name', '未知'),
                'artist': item.get('artist', '未知'),
                'cover': item.get('pic', ''),
                'lyric_id': item.get('lyric_id', item['id'])
            })

    clear_screen()
    print(f"\n- 搜索结果（{len(results)} 首）:")
    print("=" * 60)
    for idx, item in enumerate(results):
        print(f"[{idx+1:<3}] {item.get('name', '未知')}")
        print(f"      歌手: {item.get('artist', '未知')}")
        print(f"      专辑: {item.get('album', '未知')}")
        print("-" * 60)

    choice = input("\n- 输入序号播放 (B 返回): ").strip()
    if choice.lower() == 'b':
        return

    try:
        target_idx = int(choice) - 1
        if 0 <= target_idx < len(results):
            current_song_idx = target_idx
            song_id = current_playlist[target_idx]['id']

            if CONFIG["enable_preload"] and len(current_playlist) > 1:
                next_idx = (target_idx + 1) % len(current_playlist)
                next_song_id = current_playlist[next_idx]['id']
            else:
                next_song_id = None

            play_song(song_id, next_song_id)
    except ValueError:
        print("序号无效")
        time.sleep(2)

# -------------------- 主函数 --------------------
def main():
    for f in os.listdir('.'):
        if f.startswith('cover_') and f.endswith('.jpg'):
            try:
                os.remove(f)
            except:
                pass
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
                    print(f"[2] 预加载下一首（Beta）: {'ON' if CONFIG['enable_preload'] else 'OFF'}")
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