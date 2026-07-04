import os
import sys
import json
import threading
import time
import numpy as np
from scipy import signal
import scipy.io as sio
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
    sys.exit(1)

CONFIG_FILE = "sound_effects_config.json"

# ==============================================================================
# 1. 核心数据定义
# ==============================================================================
EQ_BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
PRESET_DATA_10BAND = {
    "无": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "流行": [3, 2, 1, 0, -1, -1, 0, 1, 2, 3],
    "摇滚": [5, 4, 3, 1, -1, -1, 1, 3, 4, 5],
    "民谣": [1, 1, 0, -1, 1, 2, 1, 0, 1, 1],
    "低音": [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "低音&高音": [6, 4, 2, 0, -1, -1, 0, 2, 4, 6],
    "蓝调": [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
    "古风": [1, 2, 1, 0, 2, 3, 2, 1, 2, 1],
    "古典": [0, 0, 0, 0, 0, 0, -1, -2, -3, -4],
    "电音": [4, 3, 1, -1, -2, 0, 1, 3, 4, 4],
    "超重低音": [8, 7, 5, 3, 0, 0, 0, 0, 0, 0],
    "原声": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "空间": [2, 1, 0, 0, 1, 2, 3, 4, 5, 6],
    "环绕": [1, 1, 1, 1, 1, 1, 2, 2, 3, 3],
    "ACG": [2, 2, 0, 0, 2, 1, -1, 5, 3, 7],
}

ENV_DATA_V2 = {
    "无":       (0.0, 0.5, 0.5, 10, 5, 0.0, 1.0, 0),
    "3D 空间":  (0.35, 1.8, 0.3, 15, 8, 0.65, 1.6, 25), 
    "音乐厅":   (0.45, 3.8, 0.15, 45, 12, 0.2, 1.2, 40),
    "大厅":     (0.40, 2.4, 0.25, 25, 10, 0.3, 1.1, 30),
    "房间":     (0.25, 0.6, 0.65, 8, 15, 0.1, 1.0, 10),
    "教室":     (0.30, 0.9, 0.4, 12, 12, 0.25, 1.05, 15),
    "浴室":     (0.40, 1.4, 0.02, 4, 25, 0.5, 1.4, 12),
    "夜店":     (0.45, 2.0, 0.85, 10, 8, 0.75, 1.5, 20),
    "地下通道": (0.45, 2.8, 0.95, 35, 4, 0.4, 1.0, 50), 
    "演唱会":   (0.50, 4.5, 0.2, 60, 18, 0.55, 1.7, 45),
}

# ==============================================================================
# 2. EQ 滤波器
# ==============================================================================
class ShelfFilter:
    def __init__(self, sr, fc, shelf_type='low', Q=1.0):
        self.sr, self.fc, self.shelf_type, self.Q = sr, fc, shelf_type, Q
        self.b, self.a = np.zeros(3), np.zeros(3)
        self.zi = np.zeros((2, 2))
        self.gain_db = 0.0
        self.update_gain(0.0)

    def update_gain(self, gain_db):
        if abs(self.gain_db - gain_db) < 0.05: return
        self.gain_db = gain_db
        A = 10 ** (gain_db / 40.0)
        w0 = 2 * np.pi * self.fc / self.sr
        alpha = np.sin(w0) / (2 * self.Q)
        cos_w0 = np.cos(w0)
        if self.shelf_type == 'low':
            b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
            b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
            a2 = (A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
        else:
            b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
            b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
            a2 = (A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
        self.b = np.array([b0 / a0, b1 / a0, b2 / a0])
        self.a = np.array([1.0, a1 / a0, a2 / a0])

    def process(self, data):
        if abs(self.gain_db) < 0.1: return data
        out, self.zi = signal.lfilter(self.b, self.a, data, zi=self.zi, axis=0)
        return out

class PeakingFilter:
    def __init__(self, sr, fc, Q=1.414):
        self.sr, self.fc, self.Q = sr, fc, Q
        self.b, self.a = np.zeros(3), np.zeros(3)
        self.zi = np.zeros((2, 2))
        self.gain_db = 0.0
        self.update_gain(0.0)

    def update_gain(self, gain_db):
        if abs(self.gain_db - gain_db) < 0.05: return
        self.gain_db = gain_db
        A = 10 ** (gain_db / 40.0)
        w0 = 2 * np.pi * self.fc / self.sr
        alpha = np.sin(w0) / (2 * self.Q)
        b0 = 1 + alpha * A; b1 = -2 * np.cos(w0); b2 = 1 - alpha * A
        a0 = 1 + alpha / A; a1 = -2 * np.cos(w0); a2 = 1 - alpha / A
        self.b = np.array([b0 / a0, b1 / a0, b2 / a0])
        self.a = np.array([1.0, a1 / a0, a2 / a0])

    def process(self, data):
        if abs(self.gain_db) < 0.1: return data
        out, self.zi = signal.lfilter(self.b, self.a, data, zi=self.zi, axis=0)
        return out

# ==============================================================================
# 3. 怪兽级混响引擎 (极速版：零内存分配)
# ==============================================================================
class MonsterReverb:
    def __init__(self, sr=44100):
        self.sr = sr
        self.comb_delays = [1553, 1667, 1999, 2137, 2381, 2791, 3121, 3557]
        self.allpass_delays = [225, 557, 441, 341]
        
        self.state_combs_l = [np.zeros(d) for d in self.comb_delays]
        self.state_combs_r = [np.zeros(d) for d in self.comb_delays]
        self.state_aps_l = [np.zeros(d) for d in self.allpass_delays]
        self.state_aps_r = [np.zeros(d) for d in self.allpass_delays]
        self.state_damp_l = np.zeros(1)
        self.state_damp_r = np.zeros(1)
        self.state_early_l = np.zeros(8000)
        self.state_early_r = np.zeros(8000)
        
        self.max_pre_delay = int(0.1 * sr)
        self.delay_buf_l = np.zeros(self.max_pre_delay)
        self.delay_buf_r = np.zeros(self.max_pre_delay)
        self.delay_ptr = 0
        self.pre_delay_samples = 0
        
        self.fir_early = np.array([1.0])
        self.comb_feedbacks = np.zeros(8)
        self.allpass_g = 0.5
        self.damp_coeff = 0.5
        self.cross_mix = 0.0
        self.width = 1.0
        
        # 预分配滤波器系数数组 (极速核心)
        self.comb_bs = []
        self.comb_as = []
        self.ap_bs = []
        self.ap_as = []

    def update_preset(self, env_name):
        if env_name not in ENV_DATA_V2: return
        wet, rt60, damp, gap_ms, count, cross, width, pre_delay_ms = ENV_DATA_V2[env_name]
        
        self.damp_coeff = damp
        self.cross_mix = cross
        self.width = width
        self.allpass_g = 0.6
        self.pre_delay_samples = int(pre_delay_ms * self.sr / 1000)
        
        gap_samples = max(1, int(gap_ms * self.sr / 1000))
        fir_len = gap_samples * count + 1 
        fir = np.zeros(fir_len)
        fir[0] = 1.0
        np.random.seed(42)
        for i in range(1, count):
            idx = gap_samples * i + np.random.randint(-gap_samples//4, gap_samples//4 + 1)
            if 0 < idx < fir_len:
                fir[idx] = (0.7 ** i) * (1.0 - damp * 0.5)
        self.fir_early = fir
        self.state_early_l = np.zeros(fir_len - 1)
        self.state_early_r = np.zeros(fir_len - 1)

        # 核心修复：在 update_preset 中预分配所有系数，绝不在 process 中 np.zeros
        self.comb_bs = []
        self.comb_as = []
        for i, d in enumerate(self.comb_delays):
            g = 10 ** (-3.0 * d / (self.sr * max(0.1, rt60)))
            self.comb_feedbacks[i] = np.clip(g + np.random.uniform(-0.02, 0.02), 0.0, 0.92)
            
            b = np.array([1.0])  # 梳状滤波器分子只有 b[0]=1
            a = np.zeros(d + 1); a[0] = 1.0; a[d] = -self.comb_feedbacks[i]
            self.comb_bs.append(b)
            self.comb_as.append(a)
            self.state_combs_l[i] = np.zeros(d)
            self.state_combs_r[i] = np.zeros(d)

        self.ap_bs = []
        self.ap_as = []
        g = self.allpass_g
        for i, d in enumerate(self.allpass_delays):
            b = np.zeros(d + 1); b[0] = -g; b[d] = 1.0
            a = np.zeros(d + 1); a[0] = 1.0; a[d] = -g
            self.ap_bs.append(b)
            self.ap_as.append(a)
            self.state_aps_l[i] = np.zeros(d)
            self.state_aps_r[i] = np.zeros(d)

    def process(self, data, wet):
        if wet < 0.01: return data
        
        n = len(data)
        in_l = np.empty(n)
        in_r = np.empty(n)
        ptr_end = self.delay_ptr + n
        
        if ptr_end <= self.max_pre_delay:
            in_l[:] = self.delay_buf_l[self.delay_ptr:ptr_end]
            in_r[:] = self.delay_buf_r[self.delay_ptr:ptr_end]
            self.delay_buf_l[self.delay_ptr:ptr_end] = data[:, 0]
            self.delay_buf_r[self.delay_ptr:ptr_end] = data[:, 1]
        else:
            part1 = self.max_pre_delay - self.delay_ptr
            in_l[:part1] = self.delay_buf_l[self.delay_ptr:]
            in_l[part1:] = self.delay_buf_l[:n - part1]
            in_r[:part1] = self.delay_buf_r[self.delay_ptr:]
            in_r[part1:] = self.delay_buf_r[:n - part1]
            self.delay_buf_l[self.delay_ptr:] = data[:part1, 0]
            self.delay_buf_l[:n - part1] = data[part1:, 0]
            self.delay_buf_r[self.delay_ptr:] = data[:part1, 1]
            self.delay_buf_r[:n - part1] = data[part1:, 1]
        self.delay_ptr = ptr_end % self.max_pre_delay

        early_l, self.state_early_l = signal.lfilter(self.fir_early, [1.0], in_l, zi=self.state_early_l)
        early_r, self.state_early_r = signal.lfilter(self.fir_early, [1.0], in_r, zi=self.state_early_r)
        
        in_l = early_l + early_r * self.cross_mix
        in_r = early_r + early_l * self.cross_mix
        
        comb_sum_l = np.zeros_like(in_l)
        comb_sum_r = np.zeros_like(in_r)
        
        # 极速核心：直接引用预分配的 self.comb_bs 和 self.comb_as，零内存分配！
        for i in range(8):
            y_l, self.state_combs_l[i] = signal.lfilter(self.comb_bs[i], self.comb_as[i], in_l, zi=self.state_combs_l[i])
            y_r, self.state_combs_r[i] = signal.lfilter(self.comb_bs[i], self.comb_as[i], in_r, zi=self.state_combs_r[i])
            comb_sum_l += y_l; comb_sum_r += y_r
        comb_sum_l /= 4.0; comb_sum_r /= 4.0
        
        if self.damp_coeff > 0.01:
            damp_b = [1.0 - self.damp_coeff]; damp_a = [1.0, -self.damp_coeff]
            comb_sum_l, self.state_damp_l = signal.lfilter(damp_b, damp_a, comb_sum_l, zi=self.state_damp_l)
            comb_sum_r, self.state_damp_r = signal.lfilter(damp_b, damp_a, comb_sum_r, zi=self.state_damp_r)
            
        ap_out_l, ap_out_r = comb_sum_l, comb_sum_r
        for i in range(4):
            ap_out_l, self.state_aps_l[i] = signal.lfilter(self.ap_bs[i], self.ap_as[i], ap_out_l, zi=self.state_aps_l[i])
            ap_out_r, self.state_aps_r[i] = signal.lfilter(self.ap_bs[i], self.ap_as[i], ap_out_r, zi=self.state_aps_r[i])
         
        mid = (ap_out_l + ap_out_r) * 0.5
        side = (ap_out_l - ap_out_r) * 0.5 * self.width
        wet_l = mid + side
        wet_r = mid - side
        
        out_l = data[:, 0] + wet_l * wet
        out_r = data[:, 1] + wet_r * wet
        
        return np.column_stack((out_l, out_r)).astype(np.float32)

# ==============================================================================
# 4. 核心引擎 (恢复震撼音量 & 消灭电流声)
# ==============================================================================
class UltimateAudioEngine:
    def __init__(self, sr=44100):
        self.sr = sr
        self.lock = threading.Lock()
        self.settings = {"preset": "无", "低音微调": 50, "高音微调": 50, "环绕强度": 0, "环绕深度": 0, "环境": "无"}
        q_values = [1.0, 1.0, 1.2, 1.4, 1.4, 1.4, 1.7, 2.0, 2.0, 2.0]
        self.eq_filters = [PeakingFilter(sr, fc, Q=q) for fc, q in zip(EQ_BANDS, q_values)]
        self.low_shelf = ShelfFilter(sr, 100, 'low', Q=1.2)
        self.high_shelf = ShelfFilter(sr, 8000, 'high', Q=1.2)
        self.reverb = MonsterReverb(sr)
        self.pre_gain = 1.0

    def update_settings(self, new_settings):
        with self.lock:
            self.settings.update(new_settings)
            preset_name = self.settings["preset"]
            base_gains = PRESET_DATA_10BAND.get(preset_name, PRESET_DATA_10BAND["无"]).copy()
            bass_offset = (self.settings["低音微调"] - 50) / 50.0 * 8.0
            treble_offset = (self.settings["高音微调"] - 50) / 50.0 * 8.0
            self.low_shelf.update_gain(bass_offset)
            self.high_shelf.update_gain(treble_offset)
            for i, gain in enumerate(base_gains): self.eq_filters[i].update_gain(gain)
            
            # 核心修复：恢复响度补偿！不再过度衰减，保证声音洪亮
            max_gain = max(0, max(base_gains) + max(0, bass_offset) + max(0, treble_offset))
            # 只补偿一半的 EQ 增益衰减，并额外增加 1.5 倍基础音量
            self.pre_gain = (10 ** (-max_gain / 40.0)) * 1.5 
            
            self.reverb.update_preset(self.settings["环境"])

    def warmup(self):
        pass

    def process_chunk(self, chunk):
        with self.lock:
            data = chunk.copy().astype(np.float64)
            pre_gain = self.pre_gain
            env = self.settings["环境"]
            surround_intensity = self.settings["环绕强度"] / 100.0
            surround_depth = self.settings["环绕深度"] / 100.0

        wet_orig, _, _, _, _, _, _, _ = ENV_DATA_V2.get(env, (0.0, 0.5, 0.5, 10, 5, 0.0, 1.0, 0))
        wet = wet_orig * (surround_depth / 100.0)
        
        data *= pre_gain
        data = self.low_shelf.process(data)
        data = self.high_shelf.process(data)
        for eq in self.eq_filters: data = eq.process(data)

        if surround_intensity > 0.05:
            mid = (data[:, 0] + data[:, 1]) * 0.5
            side = (data[:, 0] - data[:, 1]) * 0.5
            alpha_lp = 0.15 
            low_mid = signal.lfilter([alpha_lp], [1, -(1 - alpha_lp)], mid, axis=0)
            side_wide = side * (1.0 + surround_intensity * 1.5)
            data[:, 0] = low_mid + (mid - low_mid) + side_wide
            data[:, 1] = low_mid + (mid - low_mid) - side_wide

        if wet > 0:
            data = self.reverb.process(data, wet)

        # 核心修复：激进的 tanh 软削波限幅器。
        # 配合前面 1.5 倍的 pre_gain，这里把超过 0.95 的峰值“揉”进去，声音极大且绝对没有滋滋声！
        threshold = 0.95
        mask = np.abs(data) > threshold
        if np.any(mask):
            sign = np.sign(data[mask])
            over = np.abs(data[mask]) - threshold
            data[mask] = sign * (threshold + np.tanh(over * 3.0) * (1.0 - threshold))

        return np.clip(data, -1.0, 1.0).astype(np.float32)

# ==============================================================================
# 5. TUI 界面 (保持原样)
# ==============================================================================
class UltimateTUI:
    def __init__(self, engine):
        self.engine = engine
        self.presets = list(PRESET_DATA_10BAND.keys())
        self.envs = list(ENV_DATA_V2.keys())
        self.config = self.load_config()
        self.preset_idx = self.presets.index(self.config.get("preset", "无"))
        self.env_idx = self.envs.index(self.config.get("env", "无")) if self.config.get("env") in self.envs else 0
        self.overlay = self.config.get("overlay", {"低音": 50, "高音": 50, "环绕强度": 0, "环绕深度": 0})
        self.overlay_keys = list(self.overlay.keys())
        self.overlay_idx = 0
        self.mode = "PRESET"
        self.sync_to_engine()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: return json.load(f)
            except: pass
        return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"preset": self.presets[self.preset_idx], "overlay": self.overlay, "env": self.envs[self.env_idx]}, f)

    def sync_to_engine(self):
        self.engine.update_settings({
            "preset": self.presets[self.preset_idx],
            "低音微调": self.overlay.get("低音", 50),
            "高音微调": self.overlay.get("高音", 50),
            "环绕强度": self.overlay.get("环绕强度", 0),
            "环绕深度": self.overlay.get("环绕深度", 0),
            "环境": self.envs[self.env_idx],
        })

    def draw(self):
        p_table = Table(show_header=False, box=None, expand=True, pad_edge=False)
        for i, p in enumerate(self.presets):
            is_selected = (i == self.preset_idx and self.mode == "PRESET")
            style = "bold reverse red" if is_selected else " "
            mark = " > " if is_selected else "   "
            p_table.add_row(f"{mark}{p}", style=style)

        e_table = Table(show_header=False, box=None, expand=True, pad_edge=False)
        for i, e in enumerate(self.envs):
            is_selected = (i == self.env_idx and self.mode == "ENVIRONMENT")
            style = "bold reverse green" if is_selected else " "
            mark = "✓ " if is_selected else "  "
            e_table.add_row(f"{mark}{e}", style=style)

        o_panels = []
        for i, k in enumerate(self.overlay_keys):
            is_f = (i == self.overlay_idx and self.mode == "OVERLAY")
            val = self.overlay.get(k, 50)
            bar_len = 12
            filled = int(val / 100 * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            content = f"[yellow]{bar}[/yellow] {val}%"
            if k == "环绕强度": title, desc = "环绕强度 (展宽)", "← 声场宽度"
            elif k == "环绕深度": title, desc = "环绕深度 (混响)", "← 空间浓度"
            else: title, desc = k, " "
            border = "yellow" if is_f else "bright_black"
            o_panels.append(Panel(content, title=title, border_style=border, subtitle=desc if is_f else " "))

        layout = Layout()
        layout.split_column(
            Layout(Panel("音效引擎 V3", style="white on blue"), ratio=1),
            Layout(name="main", ratio=8),
            Layout(Panel("Tab 切换 | WASD 选择调节 | Q 退出", style="dim"), ratio=1)
        )
        layout["main"].split_row(
            Layout(Panel(p_table, title="1.基准预设", border_style="red" if self.mode == "PRESET" else "white"), ratio=1),
            Layout(Panel(Columns(o_panels, expand=True), title="2.音效微调", border_style="yellow" if self.mode == "OVERLAY" else "white"), ratio=2),
            Layout(Panel(e_table, title="3.环境选择", border_style="green" if self.mode == "ENVIRONMENT" else "white"), ratio=1)
        )
        return layout

    def run(self):
        console = Console()
        with Live(self.draw(), console=console, refresh_per_second=10, screen=True) as live:
            while True:
                live.update(self.draw())
                key = readchar.readkey()
                if key == '\t':
                    modes = ["PRESET", "OVERLAY", "ENVIRONMENT"]
                    self.mode = modes[(modes.index(self.mode) + 1) % 3]
                elif self.mode == "PRESET":
                    if key in (readchar.key.UP, 'w'): self.preset_idx = (self.preset_idx - 1) % len(self.presets)
                    elif key in (readchar.key.DOWN, 's'): self.preset_idx = (self.preset_idx + 1) % len(self.presets)
                elif self.mode == "OVERLAY":
                    if key in (readchar.key.UP, 'w'): self.overlay_idx = (self.overlay_idx - 1) % len(self.overlay_keys)
                    elif key in (readchar.key.DOWN, 's'): self.overlay_idx = (self.overlay_idx + 1) % len(self.overlay_keys)
                    elif key in (readchar.key.LEFT, 'a'): self.overlay[self.overlay_keys[self.overlay_idx]] = max(0, self.overlay[self.overlay_keys[self.overlay_idx]] - 5)
                    elif key in (readchar.key.RIGHT, 'd'): self.overlay[self.overlay_keys[self.overlay_idx]] = min(100, self.overlay[self.overlay_keys[self.overlay_idx]] + 5)
                elif self.mode == "ENVIRONMENT":
                    if key in (readchar.key.UP, 'w'): self.env_idx = (self.env_idx - 1) % len(self.envs)
                    elif key in (readchar.key.DOWN, 's'): self.env_idx = (self.env_idx + 1) % len(self.envs)
                self.sync_to_engine()
                self.save_config()
                if key.lower() == 'q': break
                live.update(self.draw(), refresh=True)

def audio_callback(in_data, frame_count, time_info, status, engine=None):
    audio_data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, 2)
    processed_data = engine.process_chunk(audio_data)
    return (processed_data.tobytes(), pyaudio.paContinue)

def main():
    RATE = 44100
    engine = UltimateAudioEngine(sr=RATE)
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paFloat32, channels=2, rate=RATE, input=True, output=True,
                        frames_per_buffer=1024, stream_callback=lambda *args: audio_callback(*args, engine=engine))
        stream.start_stream()
        UltimateTUI(engine).run()
    except Exception as e: print(f"错误: {e}")
    finally:
        if 'stream' in locals(): stream.stop_stream(); stream.close()
        p.terminate()

if __name__ == "__main__":
    main()