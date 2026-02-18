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

class UltimateAudioEngine:
    def __init__(self, sr=44100):
        self.sr = sr
        self.settings = {"低音": 50, "高音": 50, "环绕强度": 0, "环绕深度": 0}
        self.lock = threading.Lock()
        
        # 实时处理状态维护
        self.bass_zi = None
        self.treble_zi = None
        self.current_bass_sos = None
        self.current_treble_sos = None
        self.side_buffer = np.zeros((int(0.05 * sr),), dtype=np.float32)
        self.limiter_gain = 1.0
        self.alpha_rel = np.exp(-1.0 / (100 * self.sr / 1000.0))

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
        """实时处理音频块 (numpy array, shape=(N, 2), float32)"""
        with self.lock:
            settings = self.settings.copy()
        
        data = chunk.copy()
        
        # 1. 低音增强 (85Hz)
        bass_gain = (settings["低音"] - 50) / 4.0
        if abs(bass_gain) > 0.1:
            sos = self._get_lowshelf_sos(85, bass_gain)
            if self.bass_zi is None or not np.array_equal(sos, self.current_bass_sos):
                if self.bass_zi is None:
                    self.bass_zi = np.stack([signal.sosfilt_zi(sos)] * 2, axis=1)
                self.current_bass_sos = sos
            data, self.bass_zi = signal.sosfilt(sos, data, axis=0, zi=self.bass_zi)
            
        # 2. 高音增强 (10000Hz)
        treble_gain = (settings["高音"] - 50) / 4.0
        if abs(treble_gain) > 0.1:
            sos = self._get_highshelf_sos(10000, treble_gain)
            if self.treble_zi is None or not np.array_equal(sos, self.current_treble_sos):
                if self.treble_zi is None:
                    self.treble_zi = np.stack([signal.sosfilt_zi(sos)] * 2, axis=1)
                self.current_treble_sos = sos
            data, self.treble_zi = signal.sosfilt(sos, data, axis=0, zi=self.treble_zi)

        # 3. 空间环绕
        intensity = settings["环绕强度"] / 100.0
        depth = settings["环绕深度"]
        if intensity > 0:
            left, right = data[:, 0], data[:, 1]
            mid, side = (left + right) / 2.0, (left - right) / 2.0
            side = side * (1.0 + intensity * 2.2)
            delay_samples = int((depth / 100.0) * 0.025 * self.sr)
            if delay_samples > 0:
                combined_side = np.concatenate([self.side_buffer[-delay_samples:], side])
                side = side + combined_side[:len(side)] * 0.45
                if len(side) >= len(self.side_buffer): self.side_buffer = side[-len(self.side_buffer):].copy()
                else:
                    self.side_buffer = np.roll(self.side_buffer, -len(side))
                    self.side_buffer[-len(side):] = side
            data = np.stack((mid + side, mid - side), axis=1)

        # 4. 增益补偿与实时限幅
        data = data * 1.4
        threshold = 1.0
        for i in range(len(data)):
            peak = np.max(np.abs(data[i]))
            target_gain = threshold / peak if peak > threshold else 1.0
            if target_gain < self.limiter_gain: self.limiter_gain = target_gain
            else: self.limiter_gain = self.alpha_rel * self.limiter_gain + (1 - self.alpha_rel) * target_gain
            data[i] *= self.limiter_gain
            
        return np.clip(data, -1.0, 1.0)

class UltimateTUI:
    def __init__(self, engine):
        self.engine = engine
        self.presets = list(PRESET_DATA.keys())
        self.config = self.load_config()
        self.preset_idx = self.presets.index(self.config.get("preset", "无"))
        self.overlay = self.config.get("overlay", {"低音": 50, "高音": 50, "环绕强度": 50, "环绕深度": 50})
        self.overlay_keys = list(self.overlay.keys())
        self.overlay_idx = 0
        self.mode = "PRESET"
        self.msg = "Tab: 切换 | WASD: 调节 | Q: 退出"
        self.sync_to_engine()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: return json.load(f)
            except: pass
        return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"preset": self.presets[self.preset_idx], "overlay": self.overlay}, f)

    def get_final_settings(self):
        p_name = self.presets[self.preset_idx]
        b, t, s, d = PRESET_DATA[p_name]
        return {
            "低音": b + (self.overlay["低音"] - 50),
            "高音": t + (self.overlay["高音"] - 50),
            "环绕强度": s + (self.overlay["环绕强度"] - 50),
            "环绕深度": d + (self.overlay["环绕深度"] - 50),
        }

    def sync_to_engine(self):
        self.engine.update_settings(self.get_final_settings())

    def draw(self):
        p_table = Table(show_header=False, box=None, expand=True)
        for i, p in enumerate(self.presets):
            style = "bold reverse red" if (i == self.preset_idx and self.mode == "PRESET") else ""
            p_table.add_row(f" {'> ' if style else '  '}{p} ", style=style)
        
        o_panels = []
        final = self.get_final_settings()
        for i, k in enumerate(self.overlay_keys):
            is_f = (i == self.overlay_idx and self.mode == "OVERLAY")
            val, f_val = self.overlay[k], final[k]
            bar = "█" * int(val / 8.3) + "░" * (12 - int(val / 8.3))
            o_panels.append(Panel(f"\n [yellow]{bar}[/yellow] {val}% \n [dim]输出: {f_val}%[/dim]", title=f"[bold]{k}[/bold]" if is_f else k, border_style="yellow" if is_f else "bright_black"))

        layout = Layout()
        layout.split_column(
            Layout(Panel(f"🎵 音效 V7 设置中心 | 请调整您的专属听感", style="white on blue"), size=3),
            Layout(name="main")
        )
        layout["main"].split_row(
            Layout(Panel(p_table, title="1. 选择基准", border_style="red" if self.mode=="PRESET" else "white"), ratio=1),
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
                if key == '\t': self.mode = "OVERLAY" if self.mode == "PRESET" else "PRESET"
                if self.mode == "PRESET":
                    if key in (readchar.key.UP, 'w'): self.preset_idx = (self.preset_idx - 1) % len(self.presets)
                    elif key in (readchar.key.DOWN, 's'): self.preset_idx = (self.preset_idx + 1) % len(self.presets)
                else:
                    if key in (readchar.key.UP, 'w'): self.overlay_idx = (self.overlay_idx - 1) % len(self.overlay_keys)
                    elif key in (readchar.key.DOWN, 's'): self.overlay_idx = (self.overlay_idx + 1) % len(self.overlay_keys)
                    elif key in (readchar.key.LEFT, 'a'): self.overlay[self.overlay_keys[self.overlay_idx]] = max(0, self.overlay[self.overlay_keys[self.overlay_idx]] - 5)
                    elif key in (readchar.key.RIGHT, 'd'): self.overlay[self.overlay_keys[self.overlay_idx]] = min(100, self.overlay[self.overlay_keys[self.overlay_idx]] + 5)
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
