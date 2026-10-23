# -*- coding: utf-8 -*-
# =========================================================
# TOOLS/FETCH_PICTURES.PY — картинки для задания «опиши картинку»
# =========================================================
#   python tools\fetch_pictures.py             # скачать недостающие
#   python tools\fetch_pictures.py --list      # показать, что есть
#   python tools\fetch_pictures.py --force KEY # перекачать одну (например
#                                              # --force a1/house-outside)
#
# Источник — Wikimedia Commons, только свободные лицензии (Public domain,
# CC0, CC BY, CC BY-SA). Автор и лицензия каждого файла пишутся в
# assets/pictures/CREDITS.txt — этого требуют сами лицензии.
#
# ЧЕМУ НАУЧИЛСЯ ПЕРВЫЙ ПРОГОН (23.10.2026):
#   * thumb-ссылки Commons кончаются на «…/1024px-thumbnail», БЕЗ «.jpg».
#     Фильтр по расширению отбрасывал все картинки — ни одной находки;
#   * поиск по «Public domain» вытаскивает СКАНЫ книг, статей и документов.
#     Из 20 скачанных 7 оказались мусором: «The Effect of Football Basic
#     Technical Training…», документ ЕС про стандарт «Ramandolo», ч/б
#     рисунок средневекового города вместо реки с мостом;
#   * исходники мельче 1000 px не годятся: на 500–512 px модель начинает
#     ЛОЖНО браковать верные ответы (замер).
# Поэтому теперь: исходник >= 1000 px, чёрный список слов в заголовке,
# проверка самих пикселей (доля белого, насыщенность) и перебор кандидатов,
# пока не найдётся нормальная фотография.
# =========================================================

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICTURE_DIR = os.path.join(BASE_DIR, "assets", "pictures")
CREDITS = os.path.join(PICTURE_DIR, "CREDITS.txt")
META = os.path.join(PICTURE_DIR, "pictures.json")

WIDTH = 1024
MIN_SOURCE = 1000               # исходник уже этого — не берём (замер: ложный брак)
PAUSE = 3.0                     # пауза между запросами к API, секунды
USER_AGENT = ("VerbotEnglishTeacher/1.0 "
              "(local offline study project; contact: local user)")

GOOD_LICENSES = ("cc0", "public domain", "pd", "cc by 4.0", "cc by 3.0",
                 "cc by 2.0", "cc by-sa 4.0", "cc by-sa 3.0", "cc by-sa 2.0")

# Заголовки, которые почти всегда означают скан, схему или рисунок
BAD_TITLE_WORDS = (
    "map", "diagram", "drawing", "engraving", "etching", "lithograph", "print",
    "sketch", "illustration", "chart", "poster", "document", "manuscript",
    "stamp", "logo", "coat of arms", "seal", "plaque", "sign", "cover", "page",
    "book", "letter", "certificate", "patent", "form", "report", "article",
    "journal", "title", "disclaimer", "plan of", "schematic", "graph",
    # сканы книг и журналов: Commons отдаёт их как картинку, и по цвету
    # они проходят проверку (замер: «East gate edition - USACE.pdf»,
    # «Barn doors and byways (IA barndoorsbyways00eato).pdf»)
    ".pdf", ".djvu", ".tif", ".tiff", "(ia ", "usace", "corps",
)

# Что качаем: (уровень, ключ файла, запросы по очереди, тема, что должно быть)
TASKS = [
    ("a0", "people-greeting", ["people talking outdoors meeting handshake",
                               "two men shaking hands street photo"],
     "Saying Hi", ["people", "hands", "talking", "outside"]),
    ("a0", "family-photo", ["family walking in a park together",
                            "parents with children outdoors sunny day",
                            "group of friends sitting on a bench talking"],
     "Family & People", ["people", "adults", "children", "together"]),
    ("a0", "classroom", ["modern classroom with desks and whiteboard",
                         "school classroom with chairs and tables",
                         "empty classroom with desks"],
     "Classroom objects", ["desks", "chairs", "board", "room"]),
    ("a0", "breakfast-table", ["breakfast eggs bacon toast plate photo",
                               "breakfast table with coffee and food"],
     "Food & Drinks", ["food", "cup", "table", "breakfast"]),
    ("a0", "market-stall", ["fruit market stall colorful photo",
                            "vegetable market stall outdoor"],
     "Colors", ["fruit", "stall", "colors", "market"]),
    ("a1", "house-outside", ["detached house with front garden photo",
                             "residential house exterior with windows",
                             "cottage with garden in england photo"],
     "House & Rooms", ["house", "garden", "roof", "door"]),
    ("a1", "clothes-rack", ["clothes on rack in shop photo",
                            "clothes hanging in a store"],
     "Clothes", ["clothes", "rack", "colors", "shop"]),
    ("a1", "autumn-park", ["autumn park trees leaves path photo",
                           "park in autumn alley of trees"],
     "Weather & Seasons", ["trees", "leaves", "path", "autumn"]),
    ("a1", "bicycle-street", ["bicycle parked on a street photo",
                              "bike leaning against wall street"],
     "Transport", ["bicycle", "street", "wall", "wheels"]),
    ("a1", "forest-path", ["forest path tall trees sunlight photo",
                           "trail through a forest"],
     "Nature", ["trees", "path", "forest", "light"]),
    ("a1", "river-bridge", ["river with stone bridge landscape photo",
                            "bridge over a river in the countryside"],
     "Nature", ["river", "bridge", "water", "trees"]),
    ("a2", "city-street", ["city street shops people walking photo",
                           "pedestrian street with shops"],
     "Getting around town", ["street", "shops", "people", "buildings"]),
    ("a2", "cafe-inside", ["cafe interior tables chairs window photo",
                           "restaurant inside with tables"],
     "At the Restaurant", ["tables", "chairs", "window", "cafe"]),
    ("a2", "mountain-village", ["village houses on mountainside landscape photo",
                                "mountain village with houses and roofs"],
     "Describing Places", ["village", "houses", "mountains", "sky"]),
    ("a2", "bus-stop", ["bus stop people waiting photo",
                        "tram station platform with people"],
     "Transport", ["bus", "people", "stop", "street"]),
    ("a2", "seashore", ["sandy beach sea waves photo",
                        "beach with sand and blue sea"],
     "Nature", ["sea", "sand", "waves", "sky"]),
    ("a2", "night-market", ["night market stalls lights food photo",
                            "street food market at night"],
     "At the Store", ["market", "lights", "stalls", "night"]),
    ("a2", "store-inside", ["supermarket shelves products photo",
                            "grocery store aisle with food"],
     "At the Store", ["shelves", "products", "food", "store"]),
    ("a2", "football-field", ["children playing soccer on grass field photo",
                              "football players on a field"],
     "Sport & Fitness", ["field", "ball", "players", "grass"]),
    ("a2", "railway-station", ["railway station platform train photo",
                               "train at a station platform"],
     "Vacation & Trips", ["train", "platform", "station", "rails"]),
]


def _get(url: str, tries: int = 3) -> bytes:
    """Запрос с повторами: Commons отвечает 429 без паузы."""
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as exc:                 # noqa: BLE001
            last = exc
            time.sleep(PAUSE * (attempt + 2))
    raise last


def _plain(value: str) -> str:
    """HTML из метаданных → простой текст."""
    import re
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def candidates(query: str):
    """Кандидаты по запросу: сначала свободные лицензии, крупные, не сканы."""
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
           "&generator=search&gsrnamespace=6&gsrlimit=12"
           "&gsrsearch=%s&prop=imageinfo&iiprop=url|extmetadata|size"
           "&iiurlwidth=%d" % (urllib.parse.quote(query), WIDTH))
    raw = _get(api).decode("utf-8", "replace")
    if not raw.lstrip().startswith("{"):
        raise RuntimeError("Commons ответил не JSON: %s" % raw[:120].strip())
    data = json.loads(raw)
    pages = list((data.get("query") or {}).get("pages", {}).values())
    out = []
    for page in pages:
        title = page.get("title", "")
        low_title = title.lower()
        if any(word in low_title for word in BAD_TITLE_WORDS):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _plain(meta.get("LicenseShortName", {}).get("value", ""))
        if not any(good in license_name.lower() for good in GOOD_LICENSES):
            continue
        if int(info.get("width") or 0) < MIN_SOURCE:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        out.append({
            "title": title,
            "url": url,
            "license": license_name,
            # «Public domain» на Commons — это чаще всего старые сканы
            # из библиотек. Современные фотографии почти всегда CC —
            # их и ставим первыми.
            "_prefer": 0 if license_name.lower().startswith("cc") else 1,
            "artist": _plain(meta.get("Artist", {}).get("value", ""))[:80],
            "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(
                title.replace(" ", "_")),
        })
    return out


def _looks_like_photo(im) -> str:
    """Грубая проверка пикселей: скан документа или ч/б рисунок — отсечь.

    Возвращает причину отказа или пустую строку.
    """
    small = im.convert("RGB").resize((160, 160))
    px = list(small.getdata())
    n = len(px)
    white = sum(1 for r, g, b in px if r > 235 and g > 235 and b > 235) / n
    if white > 0.45:
        return "много белого — похоже на скан или документ"
    saturation = sum(max(r, g, b) - min(r, g, b) for r, g, b in px) / n
    if saturation < 26:
        return "почти без цвета — ч/б рисунок или печать"
    return ""


def _store(blob: bytes, path: str) -> str:
    """Байты → JPEG шириной WIDTH. Возвращает причину отказа или пусто."""
    try:
        from io import BytesIO
        from PIL import Image
        im = Image.open(BytesIO(blob))
        im.load()
        if im.width < 400 or im.height < 300:
            return "слишком маленькая (%dx%d)" % (im.width, im.height)
        reason = _looks_like_photo(im)
        if reason:
            return reason
        if im.width > WIDTH:
            im = im.resize((WIDTH, max(1, round(im.height * WIDTH / im.width))),
                           Image.LANCZOS)
        im = im.convert("RGB")
        out = BytesIO()
        im.save(out, "JPEG", quality=88, optimize=True)
        with open(path, "wb") as fh:
            fh.write(out.getvalue())
        return ""
    except Exception as exc:                     # noqa: BLE001
        return "не читается как картинка (%s)" % exc


def main() -> None:
    force = set()
    if "--force" in sys.argv:
        idx = sys.argv.index("--force")
        force = set(sys.argv[idx + 1:])

    os.makedirs(PICTURE_DIR, exist_ok=True)
    meta = {}
    if os.path.exists(META):
        try:
            with open(META, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:
            meta = {}
    cards = meta.get("pictures") if isinstance(meta.get("pictures"), dict) else {}

    if "--list" in sys.argv:
        for level, key, _queries, topic, _points in TASKS:
            path = os.path.join(PICTURE_DIR, level, key + ".jpg")
            print("%s/%s  %s  %s" % (level, key,
                                     "ЕСТЬ" if os.path.exists(path) else "нет",
                                     topic))
        return

    done = skipped = failed = 0
    for level, key, queries, topic, points in TASKS:
        name = "%s/%s" % (level, key)
        folder = os.path.join(PICTURE_DIR, level)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, key + ".jpg")
        if not (force and name in force):
            if os.path.exists(path) and os.path.getsize(path) > 20000:
                skipped += 1
                continue
        saved = None
        for query in queries:
            if saved:
                break
            try:
                found = candidates(query)
            except Exception as exc:             # noqa: BLE001
                print("  ❌ %s: запрос не удался (%s)" % (key, exc))
                time.sleep(PAUSE)
                continue
            if not found:
                print("  · %s: по запросу «%s» подходящих нет" % (key, query))
                time.sleep(PAUSE)
                continue
            for candidate in found[:5]:
                try:
                    blob = _get(candidate["url"])
                except Exception:                # noqa: BLE001
                    time.sleep(PAUSE)
                    continue
                reason = _store(blob, path)
                if reason:
                    print("  · %s: отказ — %s (%s)"
                          % (key, reason, candidate["title"][:50]))
                    time.sleep(PAUSE)
                    continue
                saved = candidate
                break
            time.sleep(PAUSE)
        if not saved:
            print("  ⚠️ %s: не нашлось нормальной фотографии" % key)
            failed += 1
            continue
        cards[name] = {
            "file": "%s/%s.jpg" % (level, key),
            "level": level.upper(),
            "topic": topic,
            "points": points,
            "credit": "%s — %s — %s" % (saved["artist"] or "unknown",
                                        saved["license"], saved["page"]),
            "source_title": saved["title"],
        }
        done += 1
        print("  ✅ %s (%d КБ, %s) — %s" % (key, os.path.getsize(path) // 1024,
                                            saved["license"],
                                            saved["title"][:60]))

    meta["pictures"] = cards
    with open(META, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    lines = ["Картинки для задания «опиши картинку».",
             "Источник — Wikimedia Commons. Автор и лицензия каждой:",
             ""]
    for name in sorted(cards):
        lines.append("%s — %s" % (cards[name]["file"], cards[name]["credit"]))
    with open(CREDITS, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\nскачано: %d, уже было: %d, не удалось: %d"
          % (done, skipped, failed))


if __name__ == "__main__":
    main()
