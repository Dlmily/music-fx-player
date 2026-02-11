import os
import sys
import json
import numpy as np
from scipy import signal
from scipy.io import wavfile
from pydub import AudioSegment
# 尝试导入 UI 组件，如果被 v.py 调用时没装这些库也不影响核心处理
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.table import Table
    import readchar
except ImportError:
    pass

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
    def __init__(self, file_path=None):
        self.samples = None
        self.sr = 44100
        if file_path and os.path.exists(file_path):
            self.audio = AudioSegment.from_file(file_path)
            self.sr = self.audio.frame_rate
            samples = np.array(self.audio.get_array_of_samples())
            if self.audio.channels == 2:
                self.samples = samples.reshape((-1, 2)).astype(np.float32)
            else:
                self.samples = samples.astype(np.float32)
                self.samples = np.stack((self.samples, self.samples), axis=1)
        
        self.lookahead_ms = 10
        self.lookahead_samples = int(self.lookahead_ms * self.sr / 1000)

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

    def apply_limiter(self, data, threshold_db=-0.1):
        threshold = 32768 * (10**(threshold_db / 20))
        abs_data = np.abs(data)
        peak_env = np.max(abs_data, axis=1)
        
        def numpy_max_filter(x, window):
            padded = np.pad(x, (0, window - 1), mode='edge')
            shape = (x.size, window)
            strides = (padded.strides[0], padded.strides[0])
            views = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
            return np.max(views, axis=1)

        future_peaks = numpy_max_filter(peak_env, self.lookahead_samples)
        gain_reduction = np.ones_like(future_peaks)
        mask = future_peaks > threshold
        gain_reduction[mask] = threshold / future_peaks[mask]
        
        alpha_rel = np.exp(-1.0 / (100 * self.sr / 1000.0)) # 缩短释放时间增加动态
        smooth_gain = np.ones_like(gain_reduction)
        curr_g = 1.0
        for i in range(len(gain_reduction)):
            g = gain_reduction[i]
            if g < curr_g: curr_g = g
            else: curr_g = alpha_rel * curr_g + (1 - alpha_rel) * g
            smooth_gain[i] = curr_g
        return data * smooth_gain[:, np.newaxis]

    def process(self, output_path, final_settings):
        if self.samples is None: return "未加载音频"
        data = self.samples.copy()
        
        # 1. 低音增强 (改为 85Hz，避开人声频段，消除沉闷感)
        bass_gain = (final_settings["低音"] - 50) / 4.0
        if abs(bass_gain) > 0.1:
            sos = self._get_lowshelf_sos(85, bass_gain)
            data = signal.sosfilt(sos, data, axis=0)
            
        # 2. 高音增强 (改为 10000Hz，增加清澈度)
        treble_gain = (final_settings["高音"] - 50) / 4.0
        if abs(treble_gain) > 0.1:
            sos = self._get_highshelf_sos(10000, treble_gain)
            data = signal.sosfilt(sos, data, axis=0)

        # 3. 空间环绕
        intensity = final_settings["环绕强度"] / 100.0
        depth = final_settings["环绕深度"]
        if intensity > 0:
            left, right = data[:, 0], data[:, 1]
            mid = (left + right) / 2.0
            side = (left - right) / 2.0
            side = side * (1.0 + intensity * 2.2)
            delay_samples = int((depth / 100.0) * 0.025 * self.sr)
            if delay_samples > 0:
                delayed = np.zeros_like(side)
                delayed[delay_samples:] = side[:-delay_samples]
                side = side + delayed * 0.45
            data = np.stack((mid + side, mid - side), axis=1)

        # 4. 增益补偿与限幅 (提升至1.4倍，解决音量小的问题)
        data = data * 1.4 
        data = self.apply_limiter(data)
        
        processed = np.clip(data, -32768, 32767).astype(np.int16)
        self.audio._spawn(processed.tobytes()).export(output_path, format="mp3", bitrate="320k")
        return f"处理成功"

class UltimateTUI:
    def __init__(self, input_file=None):
        self.input_file = input_file
        self.engine = UltimateAudioEngine(input_file) if input_file else None
        self.presets = list(PRESET_DATA.keys())
        
        # 加载持久化配置
        self.config = self.load_config()
        self.preset_idx = self.presets.index(self.config.get("preset", "无"))
        self.overlay = self.config.get("overlay", {"低音": 50, "高音": 50, "环绕强度": 50, "环绕深度": 50})
        
        self.overlay_keys = list(self.overlay.keys())
        self.overlay_idx = 0
        self.mode = "PRESET"
        self.msg = "Tab: 切换 | WASD: 调节 | Enter: 保存并应用"

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
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

    def draw(self):
        p_table = Table(show_header=False, box=None, expand=True)
        for i, p in enumerate(self.presets):
            style = "bold reverse red" if (i == self.preset_idx and self.mode == "PRESET") else ""
            p_table.add_row(f" {'> ' if style else '  '}{p} ", style=style)
        
        o_panels = []
        final = self.get_final_settings()
        for i, k in enumerate(self.overlay_keys):
            is_f = (i == self.overlay_idx and self.mode == "OVERLAY")
            val = self.overlay[k]
            f_val = final[k]
            bar = "█" * int(val / 8.3) + "░" * (12 - int(val / 8.3))
            o_panels.append(Panel(f"\n [yellow]{bar}[/yellow] {val}% \n [dim]输出: {f_val}%[/dim]", title=f"[bold]{k}[/bold]" if is_f else k, border_style="yellow" if is_f else "bright_black"))

        layout = Layout()
        layout.split_column(
            Layout(Panel(f"🎵 音效 V6 设置中心 | 请调整您的专属听感", style="white on blue"), size=3),
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
                
                if key == readchar.key.ENTER:
                    self.save_config()
                    if self.input_file:
                        self.engine.process(".cache_fx.mp3", self.get_final_settings())
                    break
                if key.lower() == 'q': break

if __name__ == "__main__":
    file = sys.argv[1] if len(sys.argv) > 1 else None
    UltimateTUI(file).run()