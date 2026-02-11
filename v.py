import time
import subprocess
import json
import re
import os
import sys
import requests
import platform
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

# 检测系统平台
SYSTEM = platform.system()

# 跨平台按键处理适配
if SYSTEM == "Windows":
    import msvcrt
else:
    import tty
    import termios
    import select

# 环境配置自动适配
def get_default_paths():
    if SYSTEM == "Linux" and "com.termux" in os.environ.get("PREFIX", ""):
        return '/data/data/com.termux/files/usr/bin/chromium-browser', '/data/data/com.termux/files/usr/bin/chromedriver'
    return None, None

CHROME_BIN, CHROME_DRIVER = get_default_paths()

CONFIG = {
    "auto_next": True,
    "play_mode": "单曲循环", 
    "modes": ["单曲循环", "列表顺序播放", "随机播放"],
    "enable_effects": False  # 音效全局开关
}

def clear_screen():
    os.system('cls' if SYSTEM == "Windows" else 'clear')
    print("欢迎使用网易云音乐播放器 v1.1")
    print("开发者：Dlmily")
    print("-" * 50)
    print("[1] 搜索歌曲")
    print("[2] 通用设置")
    fx_status = "ON" if CONFIG["enable_effects"] else "OFF"
    print(f"[3] 音效设置 [{fx_status}]")
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
    s_dict = lrc_to_dict(sub_lrc)
    combined = []
    for t in sorted(m_dict.keys()):
        combined.append({'time': t, 'text': m_dict[t], 'trans': s_dict.get(t, "")})
    return combined

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
        except:
            print("评论加载失败，请检查网络。")
        while True:
            k = get_key()
            if k:
                if k.lower() == 'b': return
                if k.lower() == 'a' and page > 0: page -= 1; break
                if k.lower() == 'l': page += 1; break

def play_song(song_id):
    clear_screen()
    print("- 正在获取歌曲元数据...")
    
    # 临时文件
    raw_cache = ".cache_raw.mp3"
    fx_cache = ".cache_fx.mp3"
    
    try:
        res = requests.get(f"https://api.paugram.com/netease/?id={song_id}").json()
        audio_link = res.get('link')
        sub_lrc = res.get('sub_lyric', "")
        duration = 240
        
        metadata = {
            'title': res.get('title', '未知歌曲'),
            'artist': res.get('artist', '未知歌手'),
            'translator': res.get('translator', '未知翻译'),
            'cover': res.get('cover')
        }

        if metadata['cover']:
            img_data = requests.get(metadata['cover']).content
            with open('cover.jpg', 'wb') as f: f.write(img_data)
        
        lyrics = parse_full_lyrics(res.get('lyric', ""), sub_lrc)
        
        play_path = audio_link

        # 音效处理逻辑
        if CONFIG["enable_effects"] and effects:
            print("- 正在启用V6音效引擎渲染中，请稍候...")
            audio_raw = requests.get(audio_link).content
            with open(raw_cache, 'wb') as f: f.write(audio_raw)
            
            # 调用引擎处理
            tui_config = effects.UltimateTUI()
            engine = effects.UltimateAudioEngine(raw_cache)
            engine.process(fx_cache, tui_config.get_final_settings())
            
            play_path = fx_cache
            print("- 音效处理完成，准备播放。")
        
        # 调用播放器
        player = subprocess.Popen(['mpv', '--no-video', '--really-quiet', play_path])
        
        start_time = time.time()
        l_idx, is_paused, pause_at = 0, False, 0
        lyric_history = []
        need_refresh = True

        while player.poll() is None:
            if need_refresh:
                clear_screen()
                render_cover('cover.jpg')
                print(f"\n🎵 歌曲: {metadata['title']}")
                print(f"👤 歌手: {metadata['artist']}")
                print(f"✍️ 歌词翻译: {metadata['translator']}")
                print("\n暂停[K]   切换模式[G]   评论[C]   返回菜单[B]")
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
                        player.send_signal(sig)
                        pause_at = time.time()
                        print("\n" + "="*30)
                        print("- 已暂停。请选择您的操作：(任意键继续, B退出)")
                    else:
                        sig = subprocess.signal.SIGCONT if SYSTEM != "Windows" else 18
                        player.send_signal(sig)
                        start_time += (time.time() - pause_at)
                        need_refresh = True 
                elif k == 'c':
                    show_comment_ui(song_id, metadata)
                    need_refresh = True
                elif k == 'g':
                    idx = (CONFIG["modes"].index(CONFIG["play_mode"]) + 1) % 3
                    CONFIG["play_mode"] = CONFIG["modes"][idx]
                    print(f"\n- 切换至: {CONFIG['play_mode']}")
                elif k == 'b':
                    player.terminate()
                    break

        # 播放完毕清理缓存
        if os.path.exists(raw_cache): os.remove(raw_cache)
        if os.path.exists(fx_cache): os.remove(fx_cache)
        if os.path.exists('cover.jpg'): os.remove('cover.jpg')

        if not CONFIG["auto_next"]:
            clear_screen()
            if input("\n歌曲播放完毕。是否继续播放下一首？(y/n): ").lower() != 'y':
                return

    except Exception as e:
        print(f"播放出错: {e}")
        time.sleep(2)

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
            if song_id: play_song(song_id)
    except Exception as e:
        print(f"搜索过程出错: {e}")
        if 'driver' in locals(): driver.quit()

def main():
    while True:
        clear_screen()
        choice = input("\n请输入指令: ")
        if choice == '1':
            search_flow()
        elif choice == '2':
            clear_screen()
            print(f"[1] 自动播放下一首开关: {'ON' if CONFIG['auto_next'] else 'OFF'}")
            print("[B] 返回")
            c = input("\n通用设置: ")
            if c == '1': CONFIG["auto_next"] = not CONFIG["auto_next"]
        elif choice == '3':
            clear_screen()
            print(f"音效处理引擎: {'已就绪' if effects else '未找到(effects.py)'}")
            print(f"[1] 全局音效开关: {'ON' if CONFIG['enable_effects'] else 'OFF'}")
            print("[2] 进入音效参数设置 (4.py 界面)")
            print("[B] 返回")
            c = input("\n音效设置: ")
            if c == '1':
                CONFIG["enable_effects"] = not CONFIG["enable_effects"]
            elif c == '2':
                if effects:
                    # 调用 effects.py 的 TUI 运行函数
                    effects.UltimateTUI().run()
                else:
                    print("错误：缺少 effects.py 模块，请检查文件名！")
                    time.sleep(2)
        else:
            print("无效指令"); time.sleep(1)

if __name__ == "__main__":
    main()