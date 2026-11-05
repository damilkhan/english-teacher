# -*- coding: utf-8 -*-
"""stt_compare.py - прогнать запись через две модели Whisper и сравнить.

Зачем: живой случай 05.11.2026 - Whisper услышал "otherwise" вместо "advise".
На синтезированной речи base и small дают одинаковый текст, значит спорное
место надо проверять на РЕАЛЬНОЙ записи ученика. Записи теперь сохраняются
(см. config.STT_SAVE_AUDIO, папка logs/stt).

  python tools/stt_compare.py              - последняя запись
  python tools/stt_compare.py logs/stt/X.wav - конкретный файл

Печать только ASCII (консоль Windows: cp1251), поэтому транскрипт пишется
в logs/_stt_compare.txt.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import numpy as np                                     # noqa: E402
from faster_whisper import WhisperModel                # noqa: E402

FOLDER = ROOT / "logs" / "stt"
OUT = ROOT / "logs" / "_stt_compare.txt"


def pick_file(argv):
    if argv:
        return Path(argv[0])
    files = sorted(FOLDER.glob("*.wav"))
    if not files:
        return None
    return files[-1]


def load_wav(path):
    from scipy.io import wavfile
    rate, data = wavfile.read(str(path))
    audio = data.astype(np.float32) / 32768.0
    return rate, audio


def main(argv):
    path = pick_file(argv)
    if path is None or not path.exists():
        print("no recordings in %s" % FOLDER)
        return 1
    rate, audio = load_wav(path)
    lines = ["file: %s" % path.name,
             "rate: %d Hz, duration: %.1f s" % (rate, audio.size / float(rate))]
    if rate != 16000:
        lines.append("WARNING: expected 16000 Hz")
    for size in ("base", "small"):
        model = WhisperModel(size, device="cpu", compute_type="int8")
        for lang in (None, "en"):
            t0 = time.time()
            segs, info = model.transcribe(audio, language=lang, beam_size=1,
                                          without_timestamps=True,
                                          condition_on_previous_text=False)
            text = " ".join(s.text for s in segs).strip()
            lines.append("%-6s lang=%-4s %5.2f s [%s] %s"
                         % (size, lang, time.time() - t0, info.language, text))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("saved %s" % OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
