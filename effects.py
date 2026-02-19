import os
import sys
import json
import threading
import time
import numpy as np
from scipy import signal
from scipy.io import wavfile
from pydub import AudioSegment

# 尝试导入 UI 和音频库
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.table import Table
    import readchar
    import pyaudio
except ImportError as e:
    print(f"缺少依赖库: {e}")
    print("请运行: pip install rich readchar pyaudio numpy scipy pydub")

# 配置持久化路径
CONFIG_FILE = "sound_effects_config.json"

PRESET_DATA = {
    "无": (50, 50, 0, 0),
    "ACG": (60, 75, 40, 20),
    "民谣": (45, 60, 20, 10),
    "低音": (85, 40, 30, 20),
    "低音&高音": (80, 80, 40, 30),
    "蓝调": (65, 55, 30, 25),
    "古风": (40, 70, 50, 40),
    "古典": (55, 65, 45, 30),
    "电音": (90, 70, 60, 50),
    "流行": (60, 60, 30, 20),
    "超重低音": (100, 30, 45, 30),
    "原声": (50, 50, 0, 0),
    "鲸云空间": (65, 60, 80, 40),
    "沉浸环绕": (55, 70, 90, 30),
    "清澈人声": (40, 85, 20, 10),
}

# 优化后参数（更明亮、空灵、长尾；低damping防沉闷）
ENV_DATA = {
    "无": (0.0, 0.5, 0.5),
    "大厅": (0.80, 6.2, 0.08),      # 超长空灵尾音
    "房间": (0.58, 2.8, 0.25),
    "教室": (0.60, 3.0, 0.22),
    "声乐板": (0.75, 3.5, 0.12),    # 明亮密集闪烁
    "弹簧": (0.65, 2.2, 0.38),      # 金属弹飞感增强
    "夜店": (0.75, 3.8, 0.18),
    "浴室": (0.72, 3.2, 0.06),      # 瓷砖明亮反射 + 弹飞
    "地下通道": (0.82, 7.0, 0.05),  # 极长轻盈隧道
    "演唱会": (0.85, 5.2, 0.15),
    "音乐厅": (0.88, 6.0, 0.10),    # 豪华空灵包围
}

class AdvancedReverb:
    """增强版混响（8梳 + 4全通 + 精确decay + 低damping明亮优化）——防沉闷、空灵弹飞感"""
    def __init__(self, sr=44100):
        self.sr = sr
        # 8梳滤波器（密度高，长尾）
        self.comb_delays = [int(sr * t) for t in [0.031, 0.039, 0.042, 0.048, 0.055, 0.062, 0.068, 0.075]]
        self.comb_bufs = [np.zeros(d + 1, dtype=np.float32) for d in self.comb_delays]  # +1防越界
        self.comb_pos = [0] * len(self.comb_delays)
        self.comb_lp = np.zeros((2, len(self.comb_delays)), dtype=np.float32)
        
        # 4全通滤波器（扩散增强，明亮闪烁）
        self.ap_delays = [int(sr * t) for t in [0.0048, 0.0035, 0.0024, 0.0019]]
        self.ap_bufs = [np.zeros(d + 1, dtype=np.float32) for d in self.ap_delays]
        self.ap_pos = [0] * len(self.ap_delays)

    def process(self, data, wet, decay_time, damping):
        if wet <= 0.01:
            return data.copy()
        
        out = data.copy()
        n = len(data)
        
        for i in range(n):
            for ch in range(2):
                inp = data[i, ch]
                reverb = 0.0
                
                # 1. 8梳滤波器（长尾 + 低damping明亮）
                for c in range(len(self.comb_delays)):
                    delay = self.comb_delays[c]
                    pos = self.comb_pos[c]
                    delayed = self.comb_bufs[c][(pos - delay) % (delay + 1)]
                    
                    # 低通阻尼（低damping = 高频保留多，防闷）
                    filtered = self.comb_lp[ch, c] * damping + delayed * (1.0 - damping)
                    self.comb_lp[ch, c] = filtered
                    
                    # 精确反馈（decay_time秒级长尾，轻盈衰减）
                    fb = 10 ** (-3.0 * delay / (decay_time * self.sr + 1e-8))
                    self.comb_bufs[c][pos] = inp + filtered * fb * 0.92  # 轻衰减防爆
                    
                    reverb += filtered
                    self.comb_pos[c] = (pos + 1) % (delay + 1)
                
                reverb /= len(self.comb_delays)
                
                # 2. 4全通滤波器（增强扩散 + 瓷器弹飞闪烁）
                for a in range(len(self.ap_delays)):
                    delay = self.ap_delays[a]
                    pos = self.ap_pos[a]
                    delayed = self.ap_bufs[a][(pos - delay) % (delay + 1)]
                    
                    ap_out = -0.65 * reverb + delayed  # 调整g=0.65，更明亮
                    self.ap_bufs[a][pos] = reverb + ap_out * 0.65
                    reverb = ap_out
                    self.ap_pos[a] = (pos + 1) % (delay + 1)
                
                # 干湿混合（更通透，保留人声清晰，防闷）
                out[i, ch] = data[i, ch] * (1.0 - wet * 0.42) + reverb * wet * 1.35
                
        return np.clip(out, -1.0, 1.0)

class UltimateAudioEngine:
    def __init__(self, sr=44100):
        self.sr = sr
        self.settings = {"低音": 50, "高音": 50, "环绕强度": 0, "环绕深度": 0, "环境": "无"}
        self.lock = threading.Lock()
        
        self.bass_zi = None
        self.treble_zi = None
        self.current_bass_sos = None
        self.current_treble_sos = None
        self.side_buffer = np.zeros((int(0.05 * sr),), dtype=np.float32)
        self.limiter_gain = 1.0
        self.alpha_rel = np.exp(-1.0 / (100 * self.sr / 1000.0))

        self.reverb = AdvancedReverb(sr)

    def update_settings(self, new_settings):
        with self.lock:
            self.settings.update(new_settings)

    def _get_lowshelf_sos(self, fc, gain_db, Q=0.707):
        A = 10**(gain_db / 40)
        omega = 2 * np.pi * fc / self.sr
        sn, cs = np.sin(omega), np.cos(omega)
        alpha = sn / (2 * Q)
        b0 = A * ((A + 1) - (A - 1) * cs + 2 * np.sqrt(A) * alpha)
        b1 = 2 * A * ((A - 1) - (A + 1) * cs)
        b2 = A * ((A + 1) - (A - 1) * cs - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) + (A - 1) * cs + 2 * np.sqrt(A) * alpha
        a1 = -2 * ((A - 1) + (A + 1) * cs)
        a2 = (A + 1) + (A - 1) * cs - 2 * np.sqrt(A) * alpha
        return np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]])

    def _get_highshelf_sos(self, fc, gain_db, Q=0.707):
        A = 10**(gain_db / 40)
        omega = 2 * np.pi * fc / self.sr
        sn, cs = np.sin(omega), np.cos(omega)
        alpha = sn / (2 * Q)
        b0 = A * ((A + 1) + (A - 1) * cs + 2 * np.sqrt(A) * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * cs)
        b2 = A * ((A + 1) + (A - 1) * cs - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) - (A - 1) * cs + 2 * np.sqrt(A) * alpha
        a1 = 2 * ((A - 1) + (A + 1) * cs)
        a2 = (A + 1) - (A - 1) * cs - 2 * np.sqrt(A) * alpha
        return np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]])

    def process_chunk(self, chunk):
        with self.lock:
            settings = self.settings.copy()
        
        data = chunk.copy()
        sr = self.sr
        
        # 1. 蝰蛇分轨 (M/S 矩阵) - 实现多音效并发的基础
        left, right = data[:, 0], data[:, 1]
        mid = (left + right) / 2.0   # 中置 (负责低音和人声)
        side = (left - right) / 2.0  # 侧置 (负责空间和环境)

        # 2. 蝰蛇超重低音 (Psychoacoustic Bass)
        bass_intensity = settings["低音"]
        if bass_intensity > 50:
            gain = (bass_intensity - 50) / 50.0
            b_low, a_low = signal.butter(2, 100 / (sr / 2), btype='low')
            bass_core = signal.lfilter(b_low, a_low, mid)
            # 非线性谐波生成
            harmonics = np.tanh(bass_core * (1.0 + gain * 2.0)) - bass_core
            mid += harmonics * (gain * 0.5) 

        # 3. 蝰蛇 3D 环绕 (VHS+ Surround)
        intensity = settings["环绕强度"] / 100.0
        depth = settings["环绕深度"] / 100.0
        if intensity > 0:
            side *= (1.0 + intensity * 2.0)
            delay_samples = int(depth * 0.03 * sr) 
            if delay_samples > 0:
                delayed_side = np.concatenate([self.side_buffer[-delay_samples:], side])[:len(side)]
                self.side_buffer = np.roll(self.side_buffer, -len(side))
                self.side_buffer[-len(side):] = side
                side = side * 0.7 + delayed_side * 0.3
            phase = np.sin(np.linspace(0, np.pi * intensity, len(side)))
            side += phase * side * 0.15

        # 4. 蝰蛇清晰度 (Exciter / Clarity)
        if settings["高音"] > 60:
            t_gain = (settings["高音"] - 60) / 40.0
            b_hi, a_hi = signal.butter(2, 4000 / (sr / 2), btype='high')
            highs = signal.lfilter(b_hi, a_hi, mid)
            clarity = np.abs(highs) * highs * (t_gain * 0.1)
            mid += clarity

        # 5. 重组与环境混响 (Environment)
        data[:, 0] = mid + side 
        data[:, 1] = mid - side 
        data *= 1.4 
        
        env = settings.get("环境", "无")
        wet, d_time, damp = ENV_DATA.get(env, (0.0, 0.5, 0.5))
        if wet > 0:
            data = self.reverb.process(data, wet, d_time, damp)
            
        return np.clip(data, -1.0, 1.0)

class UltimateTUI:
    def __init__(self, engine):
        self.engine = engine
        self.presets = list(PRESET_DATA.keys())
        self.envs = list(ENV_DATA.keys())
        self.config = self.load_config()
        self.preset_idx = self.presets.index(self.config.get("preset", "无"))
        self.env_idx = self.envs.index(self.config.get("env", "无")) if self.config.get("env") in self.envs else 0
        self.overlay = self.config.get("overlay", {"低音": 50, "高音": 50, "环绕强度": 50, "环绕深度": 50})
        self.overlay_keys = list(self.overlay.keys())
        self.overlay_idx = 0
        self.mode = "PRESET"
        self.msg = "Tab: 切换模式 | WASD/↑↓: 选择 | ←→: 微调 | Q: 退出"
        self.sync_to_engine()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: return json.load(f)
            except: pass
        return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "preset": self.presets[self.preset_idx], 
                "overlay": self.overlay,
                "env": self.envs[self.env_idx]
            }, f)

    def get_final_settings(self):
        p_name = self.presets[self.preset_idx]
        b, t, s, d = PRESET_DATA[p_name]
        return {
            "低音": b + (self.overlay["低音"] - 50),
            "高音": t + (self.overlay["高音"] - 50),
            "环绕强度": s + (self.overlay["环绕强度"] - 50),
            "环绕深度": d + (self.overlay["环绕深度"] - 50),
            "环境": self.envs[self.env_idx],
        }

    def sync_to_engine(self):
        self.engine.update_settings(self.get_final_settings())

    def draw(self):
        p_table = Table(show_header=False, box=None, expand=True)
        for i, p in enumerate(self.presets):
            style = "bold reverse red" if (i == self.preset_idx and self.mode == "PRESET") else ""
            p_table.add_row(f" {'> ' if style else '  '}{p} ", style=style)

        e_table = Table(show_header=False, box=None, expand=True)
        for i, e in enumerate(self.envs):
            style = "bold reverse green" if (i == self.env_idx and self.mode == "ENVIRONMENT") else ""
            mark = "✓ " if i == self.env_idx else "  "
            e_table.add_row(f"{mark}{e}", style=style)

        o_panels = []
        final = self.get_final_settings()
        for i, k in enumerate(self.overlay_keys):
            is_f = (i == self.overlay_idx and self.mode == "OVERLAY")
            val, f_val = self.overlay[k], final[k]
            bar = "█" * int(val / 8.3) + "░" * (12 - int(val / 8.3))
            o_panels.append(Panel(f"\n [yellow]{bar}[/yellow] {val}% \n [dim]输出: {f_val}%[/dim]", 
                                title=f"[bold]{k}[/bold]" if is_f else k, 
                                border_style="yellow" if is_f else "bright_black"))

        layout = Layout()
        layout.split_column(
            Layout(Panel(f"🎵 音效 V7 + 环境音效 | Tab 切换模式", style="white on blue"), size=3),
            Layout(name="main")
        )
        layout["main"].split_row(
            Layout(Panel(p_table, title="1. 基准预设", border_style="red" if self.mode=="PRESET" else "white"), ratio=1),
            Layout(Panel(e_table, title="3. 环境音效", border_style="green" if self.mode=="ENVIRONMENT" else "white"), ratio=1),
            Layout(name="right", ratio=2)
        )
        layout["right"].split_column(
            Layout(Columns(o_panels), ratio=2),
            Layout(Panel(f"\n[bold green]操作:[/bold green] {self.msg}", title="2. 微调叠加", border_style="yellow" if self.mode=="OVERLAY" else "white"), size=5)
        )
        return layout

    def run(self):
        console = Console()
        with Live(self.draw(), console=console, refresh_per_second=10) as live:
            while True:
                live.update(self.draw())
                key = readchar.readkey()
                if key == '\t':
                    modes = ["PRESET", "OVERLAY", "ENVIRONMENT"]
                    idx = modes.index(self.mode)
                    self.mode = modes[(idx + 1) % 3]

                if self.mode == "PRESET":
                    if key in (readchar.key.UP, 'w'): self.preset_idx = (self.preset_idx - 1) % len(self.presets)
                    elif key in (readchar.key.DOWN, 's'): self.preset_idx = (self.preset_idx + 1) % len(self.presets)
                elif self.mode == "OVERLAY":
                    if key in (readchar.key.UP, 'w'): self.overlay_idx = (self.overlay_idx - 1) % len(self.overlay_keys)
                    elif key in (readchar.key.DOWN, 's'): self.overlay_idx = (self.overlay_idx + 1) % len(self.overlay_keys)
                    elif key in (readchar.key.LEFT, 'a'): 
                        self.overlay[self.overlay_keys[self.overlay_idx]] = max(0, self.overlay[self.overlay_keys[self.overlay_idx]] - 5)
                    elif key in (readchar.key.RIGHT, 'd'): 
                        self.overlay[self.overlay_keys[self.overlay_idx]] = min(100, self.overlay[self.overlay_keys[self.overlay_idx]] + 5)
                elif self.mode == "ENVIRONMENT":
                    if key in (readchar.key.UP, 'w'): self.env_idx = (self.env_idx - 1) % len(self.envs)
                    elif key in (readchar.key.DOWN, 's'): self.env_idx = (self.env_idx + 1) % len(self.envs)

                self.sync_to_engine()
                self.save_config()
                if key.lower() == 'q': break

def audio_callback(in_data, frame_count, time_info, status, engine=None):
    audio_data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, 2)
    processed_data = engine.process_chunk(audio_data)
    return (processed_data.tobytes(), pyaudio.paContinue)

def main():
    RATE = 44100
    engine = UltimateAudioEngine(sr=RATE)
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paFloat32, channels=2, rate=RATE, input=True, output=True, 
                    frames_per_buffer=1024, stream_callback=lambda *args: audio_callback(*args, engine=engine))
    
    stream.start_stream()
    try:
        UltimateTUI(engine).run()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()