"""System-audio (loopback) capture and sound matching for sound triggers.

Captures what the speakers play via WASAPI loopback (soundcard package).
Matching: log-magnitude spectrogram + normalized cross-correlation over time.
"""
from __future__ import annotations
import time
import wave
import threading
from typing import Optional

import numpy as np

try:
    import soundcard as sc
    _SC_OK = True
except Exception:
    _SC_OK = False

AUDIO_OK = _SC_OK
SAMPLERATE = 16000


def _coinit() -> None:
    """Initialize COM for the current thread (WASAPI requirement)."""
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
    except Exception:
        pass


def _to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        data = data.mean(axis=1)
    return data.astype(np.float32)


# ── WAV I/O (16-bit PCM mono @ SAMPLERATE) ───────────────────────────────────

def save_wav(path: str, samples: np.ndarray) -> None:
    x = np.clip(samples, -1.0, 1.0)
    pcm = (x * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLERATE)
        w.writeframes(pcm.tobytes())


def load_wav(path: str) -> Optional[np.ndarray]:
    try:
        with wave.open(path, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            raw = w.readframes(w.getnframes())
    except Exception:
        return None

    if sw == 2:
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32767.0
    elif sw == 4:
        x = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483647.0
    elif sw == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 127.0
    else:
        return None

    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)

    if sr != SAMPLERATE and sr > 0 and len(x) > 1:
        n_out = int(len(x) * SAMPLERATE / sr)
        x = np.interp(
            np.linspace(0, len(x) - 1, n_out),
            np.arange(len(x)), x,
        ).astype(np.float32)
    return x


def wav_duration_ms(path: str) -> int:
    x = load_wav(path)
    if x is None:
        return 0
    return int(len(x) * 1000 / SAMPLERATE)


def trim_silence(samples: np.ndarray, rel_thresh: float = 0.03,
                 pad_ms: int = 60) -> np.ndarray:
    """Cut leading/trailing silence (below rel_thresh of peak amplitude)."""
    if samples is None or len(samples) == 0:
        return samples
    energy = np.abs(samples)
    peak = float(energy.max())
    if peak <= 0:
        return samples
    idx = np.where(energy > rel_thresh * peak)[0]
    if len(idx) == 0:
        return samples
    pad = int(pad_ms * SAMPLERATE / 1000)
    start = max(int(idx[0]) - pad, 0)
    end = min(int(idx[-1]) + pad, len(samples))
    return samples[start:end]


# ── Recording (blocking — call from a worker thread) ─────────────────────────

def record_sample(seconds: float) -> Optional[np.ndarray]:
    """Record system audio (loopback) for N seconds. Blocking."""
    if not _SC_OK:
        return None
    _coinit()
    try:
        spk = sc.default_speaker()
        mic = sc.get_microphone(str(spk.name), include_loopback=True)
        data = mic.record(
            numframes=int(seconds * SAMPLERATE),
            samplerate=SAMPLERATE,
        )
        return _to_mono(np.asarray(data))
    except Exception:
        return None


# ── Spectrogram matching ─────────────────────────────────────────────────────

_N_FFT = 512
_HOP = 256


def _spectrogram(x: np.ndarray) -> Optional[np.ndarray]:
    """Log-magnitude STFT, shape (freq_bins, time_frames)."""
    if x is None or len(x) < _N_FFT:
        return None
    n_frames = 1 + (len(x) - _N_FFT) // _HOP
    if n_frames < 1:
        return None
    idx = np.arange(_N_FFT)[None, :] + _HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * np.hanning(_N_FFT)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    return np.log1p(mag).T


def match_audio(buffer: np.ndarray, template: np.ndarray) -> float:
    """Best normalized correlation of template inside buffer, 0..1."""
    S = _spectrogram(buffer)
    T = _spectrogram(template)
    if S is None or T is None or S.shape[1] < T.shape[1]:
        return 0.0
    Tn = T - T.mean()
    t_norm = float(np.linalg.norm(Tn))
    if t_norm == 0:
        return 0.0
    best = 0.0
    width = T.shape[1]
    for off in range(S.shape[1] - width + 1):
        W = S[:, off:off + width]
        Wn = W - W.mean()
        w_norm = float(np.linalg.norm(Wn))
        if w_norm == 0:
            continue
        c = float((Tn * Wn).sum() / (t_norm * w_norm))
        if c > best:
            best = c
    return best


# ── Live monitor (rolling buffer of recent system audio) ────────────────────

class AudioMonitor:
    """Background loopback capture into a rolling buffer."""

    def __init__(self, buffer_seconds: float = 4.0):
        self._buf = np.zeros(int(buffer_seconds * SAMPLERATE), np.float32)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started_ok = threading.Event()
        self._failed = threading.Event()

    def start(self, timeout: float = 3.0) -> bool:
        if not _SC_OK:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self._failed.is_set():
                return False
            if self._started_ok.is_set():
                return True
            time.sleep(0.05)
        return self._started_ok.is_set()

    def _work(self) -> None:
        _coinit()
        try:
            spk = sc.default_speaker()
            mic = sc.get_microphone(str(spk.name), include_loopback=True)
            chunk = SAMPLERATE // 10  # 100 ms
            with mic.recorder(samplerate=SAMPLERATE, channels=1) as rec:
                self._started_ok.set()
                while self._running:
                    data = rec.record(numframes=chunk)
                    mono = _to_mono(np.asarray(data))
                    with self._lock:
                        self._buf = np.roll(self._buf, -len(mono))
                        self._buf[-len(mono):] = mono
        except Exception:
            self._failed.set()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

    def get_buffer(self) -> np.ndarray:
        with self._lock:
            return self._buf.copy()

    def current_level(self) -> float:
        """RMS of the last ~200 ms, 0..1."""
        with self._lock:
            tail = self._buf[-SAMPLERATE // 5:].copy()
        return float(np.sqrt(np.mean(tail ** 2)))

    def clear(self) -> None:
        with self._lock:
            self._buf[:] = 0.0
