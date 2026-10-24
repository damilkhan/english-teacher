# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_VOCAB_ANSWER_INFO.PY — что окно узнаёт о неудачном ответе
# =========================================================
#   python tests\test_vocab_answer_info.py   (Tk и микрофон НЕ нужны)
#
# Причина появления (24.10.2026): ученик говорил «hello»/«hi» на карточку
# «привет → Hey», а окно отвечало «Не расслышал слово». Распознавание было
# верным — сверка синоним не принимает. Чтобы окно могло сказать правду,
# контроллер обязан вернуть и то, что услышал, и то, что ожидалось.
#
# Проверяем:
#   1) ответ «сказал своё» отдаёт heard + en + example;
#   2) точный ответ по-прежнему good (и это не сломали);
#   3) выбор микрофона: системный по умолчанию, а не первый в списке;
#   4) битое умолчание → первый входной;
#   5) имя устройства для лога (и пустая строка, если не узнать).
# =========================================================

import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import vocabulary                                          # noqa: E402
import audio_vad                                           # noqa: E402
from controllers.vocabulary_controller import VocabularyController  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("  ✅ %s" % name)
    else:
        print("  ❌ %s  →  %s" % (name, detail))
        FAILED.append(name)


class FakeStore:
    """Профиль-подделка: одна карточка, без файлов."""

    def __init__(self, cards):
        self.cards = cards

    def vocabulary_cards(self, user_id=None):
        return self.cards

    def update_vocabulary_card(self, word, en, success, user_id=None):
        """Уровень как в профиле: успех +1, промах −1 (не ниже 0)."""
        for card in self.cards:
            if card.get("word") == word and card.get("en") == en:
                level = int(card.get("level") or 0)
                card["level"] = max(0, level + (1 if success else -1))
                return card
        return None

    def mark_vocab_session(self, user_id=None):
        return None


def make_controller():
    card = vocabulary.new_card("привет", "Hey", "Hey, what's up?", today=date(2026, 10, 24))
    ctrl = VocabularyController(store=FakeStore([card]),
                                today=date(2026, 10, 24), cards=None)
    ctrl.start(cards=[card])
    return ctrl


def test_unrelated_gives_both_words():
    """[1] «hello» вместо «Hey» → сказано ЧТО услышали и ЧТО ждали."""
    print("\n[1] ответ «сказал своё» отдаёт heard + en + example")
    # «hello»/«hi» на карточку «привет → Hey» с 24.10 считаются верными
    # (решение ученика, синонимы — см. test_vocab_synonyms.py), поэтому
    # «сказал своё» проверяем на постороннем слове.
    ctrl = make_controller()
    res = ctrl.answer("banana")
    check("статус unrelated", res.get("status") == "unrelated", res)
    check("услышанное слово отдано", res.get("heard") == "banana", res)
    check("ожидаемое слово отдано", res.get("en") == "Hey", res)
    check("пример отдан", res.get("example") == "Hey, what's up?", res)


def test_exact_answer_still_good():
    """[2] точное слово — по-прежнему удачный ответ."""
    print("\n[2] точный ответ — good (поведение не сломано)")
    ctrl = make_controller()
    res = ctrl.answer("hey")
    check("статус good", res.get("status") == "good", res)
    check("уровень вырос", res.get("level_to") == 1, res)
    check("в good лишних полей нет", "heard" not in res or res.get("heard") == "hey", res)


class FakeSD:
    """Подделка sounddevice: список устройств и «системное» умолчание."""

    def __init__(self, devices, default):
        self._devices = devices
        self.default = type("D", (), {"device": default})()

    def query_devices(self, device=None):
        if device is None:
            return self._devices
        if isinstance(device, int) and 0 <= device < len(self._devices):
            return self._devices[device]
        raise ValueError("нет такого устройства")

    def __getattr__(self, name):
        raise AttributeError(name)


DEVICES = [
    {"name": "Переназначение устр.", "max_input_channels": 2},
    {"name": "Микрофон (USB)", "max_input_channels": 1},
    {"name": "Колонки", "max_input_channels": 0},
]


def with_fake_sd(default, devices=None):
    vad = audio_vad.AudioVAD()
    real = audio_vad.sd
    audio_vad.sd = FakeSD(devices if devices is not None else DEVICES, default)
    return vad, real


def test_mic_prefers_system_default():
    """[3] берём устройство из настроек Windows, а не №0."""
    print("\n[3] микрофон = системный по умолчанию")
    vad, real = with_fake_sd([1, 3])
    try:
        got = vad._find_input_device()
    finally:
        audio_vad.sd = real
    check("выбран №1 (системный), не №0", got == 1, got)


def test_mic_falls_back_to_first_input():
    """[4] умолчание битое/выходное → первый входной."""
    print("\n[4] битое умолчание → первый входной")
    for bad in (99, -1, None, "бла"):
        vad, real = with_fake_sd(bad)
        try:
            got = vad._find_input_device()
        finally:
            audio_vad.sd = real
        check("умолчание %r → 0" % (bad,), got == 0, got)
    vad, real = with_fake_sd([2, 3])
    try:
        got = vad._find_input_device()
    finally:
        audio_vad.sd = real
    check("умолчание указывает на выход → 0", got == 0, got)


def test_mic_name_for_log():
    """[5] имя устройства для лога."""
    print("\n[5] имя устройства в логе")
    vad, real = with_fake_sd([1, 3])
    try:
        name = vad._device_name(1)
        broken = vad._device_name(42)
    finally:
        audio_vad.sd = real
    check("имя прочитано", name == "Микрофон (USB)", name)
    check("битое устройство → пусто", broken == "", broken)


def main():
    print("=" * 60)
    print("ТЕСТ: что окно повторения знает о неудачном ответе + выбор микрофона")
    print("=" * 60)
    test_unrelated_gives_both_words()
    test_exact_answer_still_good()
    test_mic_prefers_system_default()
    test_mic_falls_back_to_first_input()
    test_mic_name_for_log()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
