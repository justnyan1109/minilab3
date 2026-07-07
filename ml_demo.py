#!/usr/bin/env python3
"""
Arturia MiniLab 3 -- Demo Playground.
Два режима:
  1. ANIM  -- чистые визуальные эффекты на экране и кнопках.
  2. LIVE  -- интерактив: экран реагирует на крутилки, фейдеры и пэды в реальном времени.

Использование:
  python3 minilab3_demo.py anim        # Запустить все анимации по кругу
  python3 minilab3_demo.py rainbow     # Только радуга
  python3 minilab3_demo.py live        # Живой интерактив (крути контролы)
  python3 minilab3_demo.py --help      # Посмотреть все команды
"""
import sys
import time
import argparse
from ml3 import Minilab3, hsv_to_rgb127, note_to_name, BUTTON_IDS, ICON_IDS

# Порядок кнопок для анимаций (визуальный "трек")
CHAIN = ["Shift", "Oct-", "Hold", "Oct+", "pad0", "pad1", "pad2", "pad3",
         "pad4", "pad5", "pad6", "pad7"]

# ============================== АНИМАЦИИ ====================================
def rainbow(m: Minilab3, seconds: float = 6.0, fps: float = 15.0):
    print(f"🌈 Радуга по {len(CHAIN)} кнопкам ({seconds} сек)...")
    frame_delay = 1.0 / fps
    start = time.perf_counter()
    offset = 0.0
    while time.perf_counter() - start < seconds:
        for i, name in enumerate(CHAIN):
            hue = (offset + i / len(CHAIN)) % 1.0
            m.light_up(name, hsv_to_rgb127(hue))
        offset += 0.02
        time.sleep(frame_delay)
    m.all_buttons_off()

def chase(m: Minilab3, cycles: int = 3, delay: float = 0.08, color=(0, 127, 127)):
    print(f"🏃 Бегущий огонь ({cycles} круга)...")
    for _ in range(cycles):
        for name in CHAIN:
            m.light_up(name, color)
            time.sleep(delay)
            m.light_off(name)

def breathe(m: Minilab3, button: str = "Oct-", color=(127, 0, 80), cycles: int = 2, steps: int = 20):
    print(f"🫁 Дыхание кнопки '{button}'...")
    r0, g0, b0 = color
    for _ in range(cycles):
        for i in list(range(steps)) + list(range(steps, 0, -1)):
            k = i / steps
            m.light_up(button, (int(r0 * k), int(g0 * k), int(b0 * k)))
            time.sleep(0.03)
    m.light_off(button)

def typewriter_demo(m: Minilab3):
    print("⌨️  Печатная машинка...")
    m.typewriter("Hello Linux MIDI", label="typing...")
    time.sleep(1)

def scroll_demo(m: Minilab3):
    print("📜 Программный скролл текста...")
    m.scroll_main("This text is definitely longer than twelve characters",
                  label="Scrolling", char_delay=0.25)

def icons_demo(m: Minilab3):
    print("🎨 Карусель иконок...")
    names = list(ICON_IDS.keys())
    for i, name in enumerate(names):
        right = names[(i + 1) % len(names)]
        m.show_icons(left=name, right=right, label=name, main=right)
        time.sleep(1.0)
    m.clear_screen()

def anim_all(m: Minilab3):
    m.show_text("playground", "anim mode")
    time.sleep(1)
    rainbow(m)
    chase(m)
    breathe(m)
    typewriter_demo(m)
    scroll_demo(m)
    icons_demo(m)
    m.show_text("playground", "done!")
    time.sleep(1.5)

# ============================== ЖИВОЙ ИНТЕРАКТИВ =============================
def live_demo(m: Minilab3, seconds: float = 60.0):
    """
    Реактивный режим. Крути энкодеры/фейдеры/пэды на контроллере.
    Экран будет мгновенно отображать соответствующий page_type.
    """
    from minilab3 import (MAIN_ENCODER_CC, MAIN_ENCODER_STEPS, ENCODER_CCS, 
                          FADER_CCS, PAD_NOTE_RANGE_A, PAD_NOTE_RANGE_B, IGNORED_CCS)

    print(f"\n🎛  ЖИВОЙ ИНТЕРАКТИВ ({seconds} сек)")
    print("   🎚  Энкодеры  -> шкала энкодера")
    print("   🎚  Фейдеры   -> шкала фейдера")
    print("   🥁 Пэды       -> статус пэда (velocity + aftertouch)")
    print("   ⚠️  Mod/Pitch -> игнорируются\n")

    main_encoder_pos = {"v": 64}

    def handle(msg):
        if msg.type == "control_change":
            cc = msg.control
            if cc in IGNORED_CCS: return
            
            if cc == MAIN_ENCODER_CC:
                step = MAIN_ENCODER_STEPS.get(msg.value, 0)
                main_encoder_pos["v"] = max(0, min(127, main_encoder_pos["v"] + step))
                m.show_encoder(main_encoder_pos["v"], "Main enc", str(main_encoder_pos["v"]))
            elif cc in ENCODER_CCS:
                m.show_encoder(msg.value, "Encoder", f"cc{cc}={msg.value}")
            elif cc in FADER_CCS:
                m.show_fader(msg.value, "Fader", f"cc{cc}={msg.value}")
                
        elif msg.type in ("note_on", "note_off"):
            note = msg.note
            velocity = msg.velocity if msg.type == "note_on" else 0
            
            # Обработка физических пэдов (Velocity при ударе)
            #if note in PAD_NOTE_RANGE_A:
            #    m.show_pad(value=velocity, label="Pad A Hit", main=f"pad{note-36} v{velocity}")
            #elif note in PAD_NOTE_RANGE_B:
            #    m.show_pad(value=velocity, label="Pad B Hit", main=f"pad{note-44} v{velocity}")
            #else:
            #    # Обычные ноты (если подключена клавиатура)
            m.show_text(label="Note", main=f"{note_to_name(note)} v{velocity}")
                
        elif msg.type == "polytouch":
            # Обработка давления на пэд (Aftertouch при удержании)
            note = msg.note
            pressure = msg.value
            if note in PAD_NOTE_RANGE_A:
                m.show_pad(value=pressure, label="Pad A Hold", main=f"pad{note-36} pr{pressure}")
            elif note in PAD_NOTE_RANGE_B:
                m.show_pad(value=pressure, label="Pad B Hold", main=f"pad{note-44} pr{pressure}")

    m.on_message(handle)
    if not m._running:
        m.start_listening()
    
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass

# ============================== ТОЧКА ВХОДА =================================
def main():
    parser = argparse.ArgumentParser(description="Arturia MiniLab 3 Playground", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("mode", nargs="?", default="anim", 
                        choices=["anim", "rainbow", "chase", "breathe", "typewriter", "scroll", "icons", "live"],
                        help="Режим запуска (по умолчанию: anim)")
    parser.add_argument("--verbose", action="store_true", help="Выводить SysEx-дампы в консоль")
    
    args = parser.parse_args()
    needs_listen = args.mode == "live"

    print(f"🚀 Запуск режима: {args.mode}")
    
    try:
        with Minilab3(verbose=args.verbose, auto_daw=True, listen=needs_listen) as m:
            actions = {
                "anim": lambda: anim_all(m),
                "rainbow": lambda: rainbow(m),
                "chase": lambda: chase(m),
                "breathe": lambda: breathe(m),
                "typewriter": lambda: typewriter_demo(m),
                "scroll": lambda: scroll_demo(m),
                "icons": lambda: icons_demo(m),
                "live": lambda: live_demo(m),
            }
            actions[args.mode]()
    except KeyboardInterrupt:
        print("\n🛑 Прервано пользователем.")
    finally:
        print("✅ Сброшено, DAW-режим отключён, порты закрыты.")

if __name__ == "__main__":
    main()