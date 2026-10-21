# -*- coding: utf-8 -*-
"""Сборка учебного плана: 13 локаций × 9 блоков × (3 урока + проверка).

Запускать из корня проекта:
    python tools\\build_curriculum.py

Файл knowledge_base/curriculum.json ПЕРЕЗАПИСЫВАЕТСЯ (он в git, история цела).
Координаты точек берутся из раскладки «Пустыни» — она уже проверена на
картинке 1248×832; для новых локаций их можно сдвинуть под свою картинку.
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "knowledge_base", "curriculum.json")

# раскладка точек по тропе карты (низ-слева → вверх)
POINTS_XY = [(252, 676), (235, 530), (637, 623), (910, 646), (1024, 542),
             (860, 414), (482, 321), (237, 288), (311, 159)]


def point(number, title, lessons, prefix=""):
    """Блок: заголовок + список (название, тип) для трёх уроков.

    Четвёртый урок — ПРОВЕРОЧНОЕ занятие — добавляется автоматически.
    """
    out = {
        # id блока тоже уникален во всём плане (в каждой локации свои 9 блоков)
        "id": "%spoint_%d" % (prefix, number),
        "number": number,
        "point": list(POINTS_XY[number - 1]),
        "block_title": title,
        "lessons": [],
    }
    for i, (name, ltype) in enumerate(lessons, start=1):
        out["lessons"].append({
            # id УНИКАЛЕН ВО ВСЕМ ПЛАНЕ (иначе повтор «1.1» в разных
            # локациях съедался как дубликат), code — то, что видит ученик
            "id": "%s%d.%d" % (prefix, number, i),
            "code": "%d.%d" % (number, i),
            "title": name, "type": ltype})
    out["lessons"].append({"id": "%s%d.4" % (prefix, number),
                           "code": "%d.4" % number,
                           "title": "Проверка: " + title,
                           "type": "check"})
    return out


def location(loc_id, title, level, image, points):
    # «Пустыня» — историческая локация: её уроки остаются с простыми id
    # (1.1, 1.2 …), чтобы НЕ потерять уже пройденное в профиле ученика.
    # Все остальные локации получают префикс: "forest/1.1".
    prefix = "" if loc_id == "desert" else loc_id + "/"
    return {
        "id": loc_id,
        "title": title,
        "level": level,
        "image": image,
        "size": [1248, 832],
        "points": [point(n, t, l, prefix)
                   for n, (t, l) in enumerate(points, start=1)],
    }


def build():
    locations = []

    # ---------- A0 ----------
    locations.append(location("desert", "Пустыня", "A0", "assets/map/desert.png", [
        ("Saying Hi", [("Hello / Hi", "speaking"),
                               ("Good morning / Good evening", "speaking"),
                               ("How are you?", "chat")]),
        ("Introducing Yourself", [("My name is…", "speaking"),
                                  ("I'm from…", "speaking"),
                                  ("Nice to meet you", "chat")]),
        ("Numbers 0–10", [("Counting 1–10", "speaking"),
                          ("How many?", "speaking"),
                          ("Phone numbers", "chat")]),
        ("Numbers 11–100 & Age", [("11–20", "speaking"),
                                  ("Tens: 20–100", "speaking"),
                                  ("How old are you?", "chat")]),
        ("Colors", [("Basic colors", "speaking"),
                    ("What color is it?", "speaking"),
                    ("Colors I like", "chat")]),
        ("Objects & This is…", [("This is a pen", "speaking"),
                                ("Classroom objects", "speaking"),
                                ("My things", "chat")]),
        ("Family & People", [("This is my mother", "speaking"),
                             ("He / She is…", "speaking"),
                             ("Who is this?", "chat")]),
        ("Days & Time", [("Days of the week", "speaking"),
                         ("What's the time?", "speaking"),
                         ("Today is…", "chat")]),
        ("Likes & My Day", [("I like tea", "speaking"),
                            ("Do you like…?", "speaking"),
                            ("My day: I get up at 7", "chat")]),
    ]))

    # ---------- A1 ----------
    locations.append(location("forest", "Лесная тропа", "A1", "assets/map/forest.jpg", [
        ("Daily Routine", [("My morning", "speaking"),
                           ("What time do you…?", "speaking"),
                           ("My usual day", "chat")]),
        ("Food & Drinks", [("I eat…", "speaking"),
                           ("At breakfast", "speaking"),
                           ("What do you like to eat?", "chat")]),
        ("At the Store", [("How much is it?", "speaking"),
                         ("I'd like…", "speaking"),
                         ("Shopping list", "chat")]),
        ("Clothes", [("What are you wearing?", "speaking"),
                     ("This shirt is blue", "speaking"),
                     ("My favorite clothes", "chat")]),
        ("House & Rooms", [("There is / There are", "speaking"),
                           ("Where is the kitchen?", "speaking"),
                           ("Describe your home", "chat")]),
        ("Weather & Seasons", [("It's sunny today", "speaking"),
                               ("Seasons and months", "speaking"),
                               ("Weather in my city", "chat")]),
        ("Hobbies & Free Time", [("I like playing…", "speaking"),
                                 ("Free time questions", "speaking"),
                                 ("My hobby", "chat")]),
        ("Transport", [("By bus or by car?", "speaking"),
                       ("How do you get to school?", "speaking"),
                       ("Getting around town", "chat")]),
        ("My Weekend (Past Simple)", [("What did you do?", "speaking"),
                                      ("Yesterday I went…", "speaking"),
                                      ("My last weekend", "chat")]),
    ]))

    locations.append(location("river", "Речная долина", "A1", "assets/map/river.jpg", [
        ("Directions & Places", [("Where is the bank?", "speaking"),
                                 ("Turn left / go straight", "speaking"),
                                 ("My town", "chat")]),
        ("Health & Doctor", [("I have a headache", "speaking"),
                             ("At the doctor", "speaking"),
                             ("Healthy habits", "chat")]),
        ("Phone Calls", [("Hello, it's Damil", "speaking"),
                         ("Can I speak to…?", "speaking"),
                         ("Texting a friend", "chat")]),
        ("Invitations & Plans", [("Are you free on Friday?", "speaking"),
                                 ("Let's meet at…", "speaking"),
                                 ("Weekend plans", "chat")]),
        ("Feelings & Opinions", [("I feel happy", "speaking"),
                                 ("I think that…", "speaking"),
                                 ("How do you feel today?", "chat")]),
        ("Describing People", [("She is tall and kind", "speaking"),
                               ("What does he look like?", "speaking"),
                               ("My best friend", "chat")]),
        ("School & Studies", [("My favorite subject", "speaking"),
                              ("In the classroom", "speaking"),
                              ("My school day", "chat")]),
        ("Vacation & Trips", [("Last summer I…", "speaking"),
                              ("Where did you go?", "speaking"),
                              ("My best trip", "chat")]),
        ("Future Plans", [("I'm going to…", "speaking"),
                          ("What will you do?", "speaking"),
                          ("Next year", "chat")]),
    ]))

    # ---------- A2 ----------
    locations.append(location("city", "Городские улицы", "A2", "assets/map/city.jpg", [
        ("Making Arrangements", [("Shall we meet at six?", "speaking"),
                                 ("Sorry, I can't — I'm busy", "speaking"),
                                 ("Agreeing on a time", "chat")]),
        ("At the Restaurant", [("Can I have the menu?", "speaking"),
                               ("I'd like a coffee, please", "speaking"),
                               ("Ordering food", "chat")]),
        ("Shopping & Money", [("It's too expensive", "speaking"),
                              ("Can I pay by card?", "speaking"),
                              ("A good buy", "chat")]),
        ("Comparing Things", [("Bigger than / the biggest", "speaking"),
                              ("Better or worse?", "speaking"),
                              ("Two phones: which one?", "chat")]),
        ("Experiences (Present Perfect)", [("Have you ever been…?", "speaking"),
                                           ("I have never tried…", "speaking"),
                                           ("My life experiences", "chat")]),
        ("Rules & Obligations", [("You must / You have to", "speaking"),
                                 ("At school we can't…", "speaking"),
                                 ("House rules", "chat")]),
        ("Technology", [("My phone is broken", "speaking"),
                        ("How do I use this app?", "speaking"),
                        ("Phones and me", "chat")]),
        ("Work & Jobs", [("What do you do?", "speaking"),
                         ("My dream job", "speaking"),
                         ("Jobs in my family", "chat")]),
        ("Telling a Story (Past Continuous)", [("I was walking when…", "speaking"),
                                               ("What happened next?", "speaking"),
                                               ("A funny story", "chat")]),
    ]))

    locations.append(location("mountain", "Горный перевал", "A2", "assets/map/mountain.jpg", [
        ("Travel & Booking", [("I'd like to book a room", "speaking"),
                              ("At the airport", "speaking"),
                              ("Planning a trip", "chat")]),
        ("Problems & Complaints", [("Excuse me, there is a problem", "speaking"),
                                   ("Could you help me?", "speaking"),
                                   ("A bad hotel", "chat")]),
        ("Advice & Suggestions", [("You should…", "speaking"),
                                  ("Why don't you…?", "speaking"),
                                  ("Asking for advice", "chat")]),
        ("Possibility", [("It might rain", "speaking"),
                         ("Maybe / perhaps", "speaking"),
                         ("What could happen?", "chat")]),
        ("Preferences", [("I'd rather…", "speaking"),
                         ("I prefer tea to coffee", "speaking"),
                         ("What do you prefer?", "chat")]),
        ("Describing Places", [("It's a quiet town", "speaking"),
                               ("What is it like?", "speaking"),
                               ("My favorite place", "chat")]),
        ("Sport & Fitness", [("I play football", "speaking"),
                             ("How often do you…?", "speaking"),
                             ("Sport in my life", "chat")]),
        ("Media & Entertainment", [("What's on TV?", "speaking"),
                                   ("I watched a great movie", "speaking"),
                                   ("Movies and music", "chat")]),
        ("First Conditional", [("If it rains, I will…", "speaking"),
                               ("What will happen if…?", "speaking"),
                               ("If I have time…", "chat")]),
    ]))

    # ---------- B1 ----------
    locations.append(location("coast", "Морской берег", "B1", "assets/map/coast.jpg", [
        ("Ambitions & Dreams", [("I've always wanted to…", "speaking"),
                                ("My goals for this year", "speaking"),
                                ("Dreams and plans", "chat")]),
        ("Relationships", [("We've known each other for…", "speaking"),
                           ("Friendship matters", "speaking"),
                           ("People in my life", "chat")]),
        ("Environment", [("We should recycle", "speaking"),
                         ("Problems in my city", "speaking"),
                         ("Being eco-friendly", "chat")]),
        ("News & Current Events", [("Did you hear about…?", "speaking"),
                                   ("In my opinion, the news…", "speaking"),
                                   ("A story I read", "chat")]),
        ("Past Habits (used to)", [("I used to play…", "speaking"),
                                   ("How things have changed", "speaking"),
                                   ("When I was a child", "chat")]),
        ("Present Perfect Continuous", [("I've been learning English for…", "speaking"),
                                        ("How long have you been…?", "speaking"),
                                        ("What have you been doing?", "chat")]),
        ("Reported Speech", [("She said that…", "speaking"),
                             ("He told me to…", "speaking"),
                             ("What did they say?", "chat")]),
        ("Agreeing & Disagreeing", [("I completely agree", "speaking"),
                                    ("I'm afraid I disagree", "speaking"),
                                    ("A friendly argument", "chat")]),
        ("Giving Opinion", [("From my point of view…", "speaking"),
                            ("The pros and cons", "speaking"),
                            ("Should students wear uniforms?", "chat")]),
    ]))

    locations.append(location("bazaar", "Ночной рынок", "B1", "assets/map/bazaar.jpg", [
        ("Negotiating", [("Could you lower the price?", "speaking"),
                         ("That's my final offer", "speaking"),
                         ("Bargaining politely", "chat")]),
        ("Food Culture", [("Traditional dishes", "speaking"),
                          ("How is it cooked?", "speaking"),
                          ("Food from my country", "chat")]),
        ("Festivals & Traditions", [("We celebrate…", "speaking"),
                                    ("A festival I love", "speaking"),
                                    ("Traditions in my family", "chat")]),
        ("Fashion & Style", [("It suits you", "speaking"),
                             ("What's in fashion now?", "speaking"),
                             ("My style", "chat")]),
        ("Money & Budget", [("I save money for…", "speaking"),
                            ("Spending or saving?", "speaking"),
                            ("My monthly budget", "chat")]),
        ("City vs Countryside", [("Living in the city", "speaking"),
                                 ("Advantages and drawbacks", "speaking"),
                                 ("Where would you live?", "chat")]),
        ("Anecdotes", [("You won't believe this…", "speaking"),
                       ("A funny thing happened", "speaking"),
                       ("Tell me a story", "chat")]),
        ("Speculation (Modals)", [("It must be…", "speaking"),
                                  ("It can't be true", "speaking"),
                                  ("What do you think happened?", "chat")]),
        ("Making Decisions", [("I've decided to…", "speaking"),
                              ("It's a difficult choice", "speaking"),
                              ("A decision I made", "chat")]),
    ]))

    locations.append(location("aurora", "Северное сияние", "B1", "assets/map/aurora.jpg", [
        ("Nature & Wildlife", [("Animals in my region", "speaking"),
                               ("Protecting nature", "speaking"),
                               ("The wild world", "chat")]),
        ("Science & Discovery", [("A discovery I find amazing", "speaking"),
                                 ("How does it work?", "speaking"),
                                 ("Science in everyday life", "chat")]),
        ("Learning & Memory", [("How I learn best", "speaking"),
                               ("Tricks to remember words", "speaking"),
                               ("My learning habits", "chat")]),
        ("Cultural Differences", [("In my culture…", "speaking"),
                                  ("What surprised me abroad", "speaking"),
                                  ("Culture and manners", "chat")]),
        ("Phrasal Verbs", [("Get up, give up, look after", "speaking"),
                           ("Using phrasal verbs in speech", "speaking"),
                           ("Phrasal verbs in a story", "chat")]),
        ("Everyday Idioms", [("It's a piece of cake", "speaking"),
                             ("Break the ice", "speaking"),
                             ("Idioms I like", "chat")]),
        ("Detailed Storytelling", [("Setting the scene", "speaking"),
                                   ("Adding details and feelings", "speaking"),
                                   ("A story with a twist", "chat")]),
        ("Debating", [("I'd like to argue that…", "speaking"),
                      ("Counter-arguments", "speaking"),
                      ("Two sides of one question", "chat")]),
        ("Fluency Review", [("Speaking about anything", "speaking"),
                            ("Keeping the talk going", "speaking"),
                            ("Free conversation", "chat")]),
    ]))

    # ---------- B2 ----------
    locations.append(location("ruins", "Заброшенные руины", "B2", "assets/map/ruins.jpg", [
        ("Second Conditional", [("If I had more time…", "speaking"),
                                ("What would you do?", "speaking"),
                                ("Imaginary situations", "chat")]),
        ("Third Conditional", [("If I had known…", "speaking"),
                               ("Looking back with regret", "speaking"),
                               ("What might have been", "chat")]),
        ("Wishes & Regrets", [("I wish I could…", "speaking"),
                              ("I should have…", "speaking"),
                              ("Regrets and lessons", "chat")]),
        ("Hypothetical Situations", [("Suppose you were…", "speaking"),
                                     ("What if…?", "speaking"),
                                     ("A difficult choice", "chat")]),
        ("Past Perfect", [("By the time I arrived…", "speaking"),
                          ("Sequencing past events", "speaking"),
                          ("A complicated day", "chat")]),
        ("Passive Voice", [("It was built in…", "speaking"),
                           ("The story was told by…", "speaking"),
                           ("News in the passive", "chat")]),
        ("Reported Speech (advanced)", [("She claimed that…", "speaking"),
                                        ("He denied doing it", "speaking"),
                                        ("Retelling a conversation", "chat")]),
        ("Relative Clauses", [("The man who…", "speaking"),
                              ("Defining and non-defining", "speaking"),
                              ("Describing precisely", "chat")]),
        ("Complex Narrative", [("Building tension", "speaking"),
                               ("Ending with impact", "speaking"),
                               ("Tell a complete story", "chat")]),
    ]))

    locations.append(location("volcano", "Вулкан", "B2", "assets/map/volcano.jpg", [
        ("Arguments & Persuasion", [("Convincing someone", "speaking"),
                                    ("Handling objections", "speaking"),
                                    ("Persuasive speaking", "chat")]),
        ("Register", [("Formal or informal?", "speaking"),
                      ("Choosing the right tone", "speaking"),
                      ("An email and a message", "chat")]),
        ("Work & Career", [("Career paths", "speaking"),
                           ("A job interview", "speaking"),
                           ("My professional plans", "chat")]),
        ("Business Communication", [("Meetings and deadlines", "speaking"),
                                    ("Negotiating a deal", "speaking"),
                                    ("A business call", "chat")]),
        ("Risk & Decisions", [("Weighing risks", "speaking"),
                              ("Taking a chance", "speaking"),
                              ("A risky decision", "chat")]),
        ("Media & Bias", [("How news shapes opinion", "speaking"),
                          ("Fake news and trust", "speaking"),
                          ("Analysing an article", "chat")]),
        ("Academic Discussion", [("Presenting an argument", "speaking"),
                                 ("Referring to sources", "speaking"),
                                 ("A short academic talk", "chat")]),
        ("Presentations", [("Structuring a talk", "speaking"),
                           ("Handling questions", "speaking"),
                           ("My mini presentation", "chat")]),
        ("Debating Complex Topics", [("A structured debate", "speaking"),
                                     ("Rebuttals and evidence", "speaking"),
                                     ("A controversial question", "chat")]),
    ]))

    locations.append(location("ice", "Ледяные пещеры", "B2", "assets/map/ice.jpg", [
        ("Nuanced Emotions", [("Expressing how you really feel", "speaking"),
                              ("Empathy and support", "speaking"),
                              ("A difficult conversation", "chat")]),
        ("Abstract Ideas", [("Freedom, success, happiness", "speaking"),
                            ("Defining an idea", "speaking"),
                            ("What success means to me", "chat")]),
        ("Ethics & Dilemmas", [("What is the right thing?", "speaking"),
                               ("A moral dilemma", "speaking"),
                               ("Right and wrong", "chat")]),
        ("Emphasis (Cleft Sentences)", [("What I really need is…", "speaking"),
                                        ("It was him who…", "speaking"),
                                        ("Emphasising a point", "chat")]),
        ("Inversion", [("Never have I…", "speaking"),
                       ("Rarely does she…", "speaking"),
                       ("Dramatic emphasis", "chat")]),
        ("Advanced Modals", [("It might have been…", "speaking"),
                             ("He must have forgotten", "speaking"),
                             ("Deducing the past", "chat")]),
        ("Cohesion & Linking", [("Connecting ideas smoothly", "speaking"),
                                ("However, moreover, therefore", "speaking"),
                                ("A coherent answer", "chat")]),
        ("Precision in Vocabulary", [("Choosing the exact word", "speaking"),
                                     ("Avoiding repetition", "speaking"),
                                     ("Rich descriptions", "chat")]),
        ("Fluency Under Pressure", [("Thinking on your feet", "speaking"),
                                    ("Speaking without preparation", "speaking"),
                                    ("A spontaneous answer", "chat")]),
    ]))

    # ---------- C1 ----------
    locations.append(location("sky", "Небесные острова", "C1", "assets/map/sky.jpg", [
        ("Idiomatic Fluency", [("Idioms in natural speech", "speaking"),
                               ("Using idioms sparingly and well", "speaking"),
                               ("A story full of idioms", "chat")]),
        ("Nuance & Register", [("Shades of meaning", "speaking"),
                               ("Speaking appropriately", "speaking"),
                               ("Formal and colloquial versions", "chat")]),
        ("Discourse Markers", [("Structuring a long answer", "speaking"),
                               ("Signposting and linking", "speaking"),
                               ("A well-organized opinion", "chat")]),
        ("Mixed Conditionals", [("If I had taken that job…", "speaking"),
                               ("Complex hypotheticals", "speaking"),
                               ("Looking back and forward", "chat")]),
        ("Advanced Phrasal Verbs", [("Put up with, come across", "speaking"),
                                    ("Natural phrasal usage", "speaking"),
                                    ("Phrasal verbs in context", "chat")]),
        ("Collocations & Chunks", [("Words that go together", "speaking"),
                                   ("Speaking in chunks", "speaking"),
                                   ("Fluent formulations", "chat")]),
        ("Professional Speaking", [("Interviews and meetings", "speaking"),
                                   ("Presenting with confidence", "speaking"),
                                   ("A professional discussion", "chat")]),
        ("Implicit Meaning", [("Reading between the lines", "speaking"),
                              ("Sarcasm, irony, hints", "speaking"),
                              ("What did they really mean?", "chat")]),
        ("Long Turns", [("Speaking for two minutes", "speaking"),
                        ("Developing an argument", "speaking"),
                        ("A monologue on any topic", "chat")]),
    ]))

    locations.append(location("space", "Космическая станция", "C1", "assets/map/space.jpg", [
        ("Speculating About the Future", [("Where we are heading", "speaking"),
                                          ("Technology in 2050", "speaking"),
                                          ("My vision of the future", "chat")]),
        ("Philosophical Debate", [("What makes us human?", "speaking"),
                                  ("Arguing a philosophical point", "speaking"),
                                  ("A deep question", "chat")]),
        ("Persuasive Rhetoric", [("Building a persuasive case", "speaking"),
                                 ("Rhetorical devices", "speaking"),
                                 ("A speech", "chat")]),
        ("Storytelling Masterclass", [("Voice, pace, detail", "speaking"),
                                      ("A story that holds attention", "speaking"),
                                      ("Your best story", "chat")]),
        ("Humour & Cultural Nuance", [("Jokes that travel", "speaking"),
                                      ("Understanding humour", "speaking"),
                                      ("A funny misunderstanding", "chat")]),
        ("High-level Negotiation", [("Finding common ground", "speaking"),
                                    ("Handling disagreement", "speaking"),
                                    ("A difficult negotiation", "chat")]),
        ("Public Speaking", [("Managing nerves and delivery", "speaking"),
                             ("Engaging an audience", "speaking"),
                             ("A short public talk", "chat")]),
        ("Precision & Hedging", [("Softeners and qualifiers", "speaking"),
                                 ("Saying exactly what you mean", "speaking"),
                                 ("Careful but clear", "chat")]),
        ("Exam Simulation", [("Picture description", "speaking"),
                             ("Discussion questions", "speaking"),
                             ("A long turn on a topic", "chat")]),
    ]))

    return {"version": 2, "locations": locations}


def main():
    data = build()
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    total_points = sum(len(l["points"]) for l in data["locations"])
    total_lessons = sum(len(p["lessons"]) for l in data["locations"]
                        for p in l["points"])
    checks = sum(1 for l in data["locations"] for p in l["points"]
                 for les in p["lessons"] if les["type"] == "check")
    print("записано: %s" % OUT)
    print("локаций: %d | блоков: %d | уроков: %d (из них проверок: %d)"
          % (len(data["locations"]), total_points, total_lessons, checks))
    for loc in data["locations"]:
        n = sum(len(p["lessons"]) for p in loc["points"])
        print("  %-4s %-20s точек %d, уроков %d"
              % (loc["level"], loc["title"], len(loc["points"]), n))


if __name__ == "__main__":
    main()
