#!/usr/bin/env python3
"""
Arturia MiniLab 3 Python API.
Финальная, стабильная версия библиотеки для управления MIDI-контроллером.
"""
import threading
import time
import mido
from typing import Optional, Tuple, List, Dict, Callable

# ========================== КОНСТАНТЫ И МАППИНГИ ==============================
SYSEX_HEADER = [0x00, 0x20, 0x6B, 0x7F, 0x42]
MIDI_PORT_HINT = "Minilab3 MIDI"
ALV_PORT_HINT = "Minilab3 ALV"
SCREEN_WIDTH = 12  # Подтвержденная эмпирически ширина главного экрана

# ID кнопок для SysEx-команд подсветки
BUTTON_IDS = {
    "Shift": 0x00, "Oct-": 0x01, "Hold": 0x02, "Oct+": 0x03,
    "pad0": 0x04, "pad1": 0x05, "pad2": 0x06, "pad3": 0x07,
    "pad4": 0x08, "pad5": 0x09, "pad6": 0x0A, "pad7": 0x0B,
    "Metro": 0x54, "Loop": 0x57, "Stop": 0x58, "Play": 0x59,
    "Rec": 0x5A, "Tap": 0x5B,
}

# Реальные MIDI-номера физических контролов
MAIN_ENCODER_CC = 28
# Главный энкодер шлёт относительные тики (61/62 = назад, 65/66 = вперёд)
MAIN_ENCODER_STEPS = {61: -5, 62: -1, 65: +1, 66: +5}
ENCODER_CCS = {86, 87, 89, 90, 110, 111, 116, 117}
FADER_CCS = {14, 15, 30, 31}
PAD_NOTE_RANGE_A = range(36, 44)
PAD_NOTE_RANGE_B = range(44, 52)
IGNORED_CCS = {1}  # Mod wheel

# Иконки для экрана (используются в левом и правом слотах)
ICON_IDS = {
    "heart": 0x01, "arrow": 0x02, "rec": 0x03,
    "note": 0x04, "check": 0x05, "knob": 0x06,
}

# Ноты: C, C#, D, D#, E, F, F#, G, G#, A, A#, B
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# ============================== УТИЛИТЫ =====================================

def hsv_to_rgb127(h: float, s: float = 1.0, v: float = 1.0) -> Tuple[int, int, int]:
    """Конвертирует HSV (0.0-1.0) в RGB (0-127) для MIDI."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 127), int(g * 127), int(b * 127)

def note_to_name(note: int) -> str:
    """
    Конвертирует MIDI-номер ноты (0-127) в человекочитаемое название.
    Нота 0 = C0, нота 12 = C1, ..., нота 60 = C5, ..., нота 120 = C10.
    Примеры: 0 -> 'C0', 60 -> 'C5', 69 -> 'A5', 120 -> 'C10'.
    """
    if not (0 <= note <= 127):
        return f"?{note}"
    name = NOTE_NAMES[note % 12]
    octave = note // 12
    return f"{name}{octave}"

def _find_port(names: List[str], hint: str) -> Optional[str]:
    for n in names:
        if hint in n:
            return n
    return None

# ============================== КЛАСС УСТРОЙСТВА ============================
class Minilab3:
    """Основной класс для управления Arturia MiniLab 3."""
    
    def __init__(self, verbose: bool = False, auto_daw: bool = True, listen: bool = False):
        self.verbose = verbose
        self._running = False
        self._callback: Optional[Callable] = None
        self._daw_connected = False
        self._threads: List[threading.Thread] = []

        # Инициализация портов
        out_names = mido.get_output_names()
        in_names = mido.get_input_names()
        
        self.midi_out = self._open_port(mido.open_output, _find_port(out_names, MIDI_PORT_HINT))
        self.alv_out = self._open_port(mido.open_output, _find_port(out_names, ALV_PORT_HINT))
        
        if listen:
            self.midi_in = self._open_port(mido.open_input, _find_port(in_names, MIDI_PORT_HINT))
            self.alv_in = self._open_port(mido.open_input, _find_port(in_names, ALV_PORT_HINT))
        else:
            self.midi_in = self.alv_in = None

        if auto_daw:
            self.connect_daw()
        if listen:
            self.start_listening()

    def _open_port(self, opener, name: Optional[str]):
        if not name:
            return None
        try:
            return opener(name)
        except Exception as e:
            if self.verbose: print(f"Ошибка открытия порта {name}: {e}")
            return None

    def _send_sysex(self, port, data: List[int]):
        if port is None: return
        if self.verbose:
            print(f"TX: {' '.join(f'{b:02X}' for b in data)}")
        port.send(mido.Message("sysex", data=data))

    # --- Управление DAW-режимом ---
    def connect_daw(self):
        self._send_sysex(self.alv_out, SYSEX_HEADER + [0x02, 0x02, 0x40, 0x6A, 0x21])
        self._daw_connected = True

    def disconnect_daw(self):
        self._send_sysex(self.alv_out, SYSEX_HEADER + [0x02, 0x02, 0x40, 0x6A, 0x20])
        self._daw_connected = False

    # --- Управление подсветкой ---
    def set_led(self, button_name: str, rgb: Tuple[int, int, int]):
        if button_name not in BUTTON_IDS:
            raise ValueError(f"Неизвестная кнопка: {button_name}")
        r, g, b = (v & 0x7F for v in rgb)
        self._send_sysex(self.midi_out, SYSEX_HEADER + [0x02, 0x02, 0x16, BUTTON_IDS[button_name], r, g, b])

    def light_up(self, button_name: str, rgb: Tuple[int, int, int]):
        """Алиас для set_led (для совместимости и наглядности)."""
        self.set_led(button_name, rgb)

    def light_off(self, button_name: str):
        self.set_led(button_name, (0, 0, 0))

    def all_buttons_off(self):
        for name in BUTTON_IDS:
            self.light_off(name)

    # --- Управление экраном (Статические режимы) ---
    def _build_screen_msg(self, control_block: List[int], label: str, main: str) -> List[int]:
        data = SYSEX_HEADER + [0x04, 0x02, 0x60] + control_block
        data += [0x01] + to_ascii_bytes(label) + [0x00]
        data += [0x02] + to_ascii_bytes(main) + [0x00]
        return data

    def show_text(self, label: str = "", main: str = ""):
        """page_type 1. Обычный текст. Работает всегда, без физического взаимодействия."""
        self._send_sysex(self.alv_out, self._build_screen_msg([], label, main))

    def show_icons(self, left: Optional[str] = None, right: Optional[str] = None, label: str = "", main: str = ""):
        """page_type 10. Показ иконок в левом и правом слотах."""
        left_id = ICON_IDS.get(left, 0x00) if left else 0x00
        right_id = ICON_IDS.get(right, 0x00) if right else 0x00
        block = [0x1F, 0x07, 0x01, left_id, right_id, 0x01, 0x00]
        self._send_sysex(self.alv_out, self._build_screen_msg(block, label, main))

    def clear_screen(self):
        self.show_text("", "")

    # --- Управление экраном (Реактивные режимы) ---
    def show_encoder(self, value: int, label: str = "", main: str = ""):
        """page_type 3. Шкала энкодера. Отрисовывается только при физическом вращении."""
        self._send_sysex(self.alv_out, self._build_screen_msg([0x1F, 0x03, 0x01, value & 0x7F, 0x00, 0x00], label, main))

    def show_fader(self, value: int, label: str = "", main: str = ""):
        """page_type 4. Шкала фейдера. Отрисовывается только при физическом движении."""
        self._send_sysex(self.alv_out, self._build_screen_msg([0x1F, 0x04, 0x01, value & 0x7F, 0x00, 0x00], label, main))

    def show_pad(self, value: int = 0, label: str = "", main: str = ""):
        """page_type 5. Статус пэда. Отрисовывается только при физическом нажатии."""
        self._send_sysex(self.alv_out, self._build_screen_msg([0x1F, 0x05, 0x01, value & 0x7F, 0x00, 0x00], label, main))

    # --- Программные эффекты (Работают всегда) ---
    def typewriter(self, text: str, label: str = "", char_delay: float = 0.12):
        for i in range(1, len(text) + 1):
            self.show_text(label, text[:i])
            time.sleep(char_delay)

    def scroll_main(self, text: str, label: str = "", window: int = SCREEN_WIDTH, char_delay: float = 0.3, cycles: int = 1):
        if len(text) <= window:
            self.show_text(label, text)
            return
        padded = text + " " * window
        total = len(padded) - window + 1
        for _ in range(cycles):
            for pos in range(total):
                self.show_text(text[pos:pos+24], text[pos:pos+18])
                print(text[pos:pos+24], text[pos:pos+18])
                time.sleep(char_delay)

    # --- MIDI Listener ---
    def on_message(self, callback: Callable):
        self._callback = callback

    def start_listening(self):
        self._running = True
        for inport in (self.midi_in, self.alv_in):
            if inport:
                t = threading.Thread(target=self._listen_loop, args=(inport,), daemon=True)
                t.start()
                self._threads.append(t)

    def _listen_loop(self, inport):
        for msg in inport:
            if not self._running: break
            if self._callback:
                try: self._callback(msg)
                except Exception as e:
                    if self.verbose: print(f"Callback error: {e}")

    # --- Ресурсы и сброс ---
    def reset(self):
        self.all_buttons_off()
        self.clear_screen()

    def close(self):
        self._running = False
        for p in (self.midi_out, self.alv_out, self.midi_in, self.alv_in):
            if p: p.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.reset()
        if self._daw_connected: self.disconnect_daw()
        self.close()
        return False
