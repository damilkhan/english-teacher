import customtkinter as ctk
import tkinter as tk
import threading
import time
import requests
import json
import numpy as np
import os
from datetime import datetime
import audio_vad
import stt_engine
import tts
import emoji
import re
from chat_webview import ChatWebView

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class AudioVisualizer(ctk.CTkFrame):
    def __init__(self, parent, width=400, height=80):
        super().__init__(parent, fg_color="transparent")
        self.width = width
        self.height = height
        self.bars = 20
        self.bar_width = max(2, width // self.bars - 2)
        self.canvas = tk.Canvas(self, width=width, height=height, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack()
        self.rects = []
        self.create_bars()

    def create_bars(self):
        for i in range(self.bars):
            x = i * (self.bar_width + 2) + 2
            rect = self.canvas.create_rectangle(x, self.height, x + self.bar_width, self.height, fill="#8C43EB", outline="")
            self.rects.append(rect)

    def update_level(self, level):
        h = self.height
        for i, rect in enumerate(self.rects):
            bar_height = int((level / 100) * h * ((i + 1) / self.bars))
            bar_height = max(2, min(h, bar_height))
            x = i * (self.bar_width + 2) + 2
            self.canvas.coords(rect, x, h - bar_height, x + self.bar_width, h)

    def reset(self):
        for i, rect in enumerate(self.rects):
            x = i * (self.bar_width + 2) + 2
            self.canvas.coords(rect, x, self.height, x + self.bar_width, self.height)

class EnglishTeacherApp:
    def __init__(self):
        self.window = ctk.CTk()
        self.window.title("English Teacher — Jane")
        self.window.geometry("1100x750")
        self.window.minsize(900, 650)
        self.window.configure(fg_color="#121212")

        self.current_theme = "dark"
        self.panel_visible = False
        self.is_recording = False
        self.mode = "lesson"
        self.current_lang = "en"
        self.llm_url = "http://127.0.0.1:8080/completion"
        self.conversation_history = []
        self.waiting_for_translation = False

        self.vad = audio_vad.AudioVAD()
        self.stt = stt_engine.STTEngine()

        # ---------- ОСНОВНОЙ КОНТЕЙНЕР ----------
        self.main_container = ctk.CTkFrame(self.window, fg_color="#121212", corner_radius=0)
        self.main_container.pack(fill="both", expand=True, padx=15, pady=15)

        # ---------- ЛЕВАЯ ПАНЕЛЬ (ЧАТ) ----------
        self.left_frame = ctk.CTkFrame(self.main_container, fg_color="#1a1a1a", corner_radius=16)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Заголовок
        self.title_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.title_frame.pack(fill="x", pady=(15, 5))

        self.title_label = ctk.CTkLabel(
            self.title_frame,
            text="🎙️ ИИ-ПРЕПОДАВАТЕЛЬ",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ffffff"
        )
        self.title_label.pack(side="left", padx=15)

        self.status_badge = ctk.CTkLabel(
            self.title_frame,
            text="● Готов",
            font=ctk.CTkFont(size=12),
            text_color="#4CAF50"
        )
        self.status_badge.pack(side="right", padx=15)

        # Визуализатор
        self.visualizer = AudioVisualizer(self.left_frame, width=400, height=40)
        self.visualizer.pack(pady=(0, 10), padx=15, fill="x")

        # ---------- ЧАТ ----------
        self.chat_frame = ctk.CTkFrame(self.left_frame, fg_color="#1e1e1e", corner_radius=12, height=400)
        self.chat_frame.pack(fill="x", padx=15, pady=(0, 10))
        self.chat_frame.pack_propagate(False)
        self.chat_text_frame = ctk.CTkFrame(self.chat_frame, fg_color="#1e1e1e")
        self.chat_text_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.chat_text = tk.Text(
            self.chat_text_frame,
            wrap="word",
            font=("Segoe UI Emoji", 14),
            bg="#1e1e1e",
            fg="#e0e0e0",
            borderwidth=0,
            highlightthickness=0,
            relief="flat"
        )
        self.chat_text.pack(side="left", fill="both", expand=True)

        self.chat_scrollbar = ctk.CTkScrollbar(self.chat_text_frame, command=self.chat_text.yview)
        self.chat_scrollbar.pack(side="right", fill="y")
        self.chat_text.configure(yscrollcommand=self.chat_scrollbar.set)

        self.chat_text.insert("0.0", "Джейн: Привет! Я твой преподаватель английского.\nЯ буду запоминать твои ошибки и подстраивать уроки под тебя.\n\n")
        self.chat_text.configure(state="disabled")
        # ---------- ПОЛЕ ВВОДА ----------
        self.input_frame = ctk.CTkFrame(self.left_frame, fg_color="#1a1a1a", corner_radius=12)
        self.input_frame.pack(fill="both", padx=15, pady=(0, 10))

        self.input_text = ctk.CTkTextbox(
            self.input_frame,
            height=50,
            wrap="word",
            fg_color="#1a1a1a",
            border_width=0,
            corner_radius=8,
            font=ctk.CTkFont(size=14)
        )
        self.input_text.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=5)

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="📎 Отправить",
            fg_color="#8C43EB",
            hover_color="#6b2fb8",
            command=lambda: self.send_text(),
            width=100,
            height=40,
            cursor="hand2",
            text_color="white",
            corner_radius=8
        )
        self.send_btn.pack(side="right", padx=5, pady=5)

        # ---------- ПАНЕЛЬ УПРАВЛЕНИЯ ----------
        self.control_frame = ctk.CTkFrame(self.left_frame, fg_color="#1a1a1a", corner_radius=12)
        self.control_frame.pack(fill="x", padx=15, pady=(0, 15))

        # Кнопки управления
        self.record_btn = ctk.CTkButton(
            self.control_frame,
            text="🎤 Запись",
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            command=lambda: self.toggle_recording(),
            width=120,
            height=40,
            cursor="hand2",
            text_color="#ffffff",
            corner_radius=8,
            border_width=1,
            border_color="#3a3a3a"
        )
        self.record_btn.pack(side="left", padx=10, pady=10)

        self.settings_btn = ctk.CTkButton(
            self.control_frame,
            text="⚙️ Настройки",
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            command=lambda: self.open_panel(),
            width=120,
            height=40,
            cursor="hand2",
            text_color="#ffffff",
            corner_radius=8,
            border_width=1,
            border_color="#3a3a3a"
        )
        self.settings_btn.pack(side="right", padx=10, pady=10)

        self.clear_btn = ctk.CTkButton(
            self.control_frame,
            text="🗑️ Очистить",
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            command=lambda: self.clear_chat(),
            width=120,
            height=40,
            cursor="hand2",
            text_color="#ffffff",
            corner_radius=8,
            border_width=1,
            border_color="#3a3a3a"
        )
        self.clear_btn.pack(side="right", padx=10, pady=10)

        # ---------- ПРАВАЯ ПАНЕЛЬ ----------
        self.right_panel = ctk.CTkFrame(self.main_container, width=260, fg_color="#1a1a1a", corner_radius=16)
        # НЕ пакуем изначально

        self.panel_title = ctk.CTkLabel(self.right_panel, text="⚙️ НАСТРОЙКИ", font=ctk.CTkFont(size=16, weight="bold"), text_color="#ffffff")
        self.panel_title.pack(pady=(25, 15))

        self.mode_frame = ctk.CTkFrame(self.right_panel, fg_color="#222222", corner_radius=10)
        self.mode_frame.pack(fill="x", padx=15, pady=5)

        self.mode_label = ctk.CTkLabel(self.mode_frame, text="Режим:", font=ctk.CTkFont(size=12), text_color="#888888")
        self.mode_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.mode_var = ctk.StringVar(value=self.mode)
        self.mode_lesson = ctk.CTkRadioButton(
            self.mode_frame,
            text="🎓 Урок",
            variable=self.mode_var,
            value="lesson",
            cursor="hand2",
            text_color="#ffffff",
            fg_color="#8C43EB"
        )
        self.mode_lesson.pack(pady=5, padx=15, anchor="w")

        self.mode_free = ctk.CTkRadioButton(
            self.mode_frame,
            text="💬 Свободное общение",
            variable=self.mode_var,
            value="free",
            cursor="hand2",
            text_color="#ffffff",
            fg_color="#8C43EB"
        )
        self.mode_free.pack(pady=5, padx=15, anchor="w")

        self.theme_frame = ctk.CTkFrame(self.right_panel, fg_color="#222222", corner_radius=10)
        self.theme_frame.pack(fill="x", padx=15, pady=5)

        self.theme_label = ctk.CTkLabel(self.theme_frame, text="Тема:", font=ctk.CTkFont(size=12), text_color="#888888")
        self.theme_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.theme_var = ctk.StringVar(value=self.current_theme)
        self.theme_dark = ctk.CTkRadioButton(
            self.theme_frame,
            text="🌙 Тёмная",
            variable=self.theme_var,
            value="dark",
            cursor="hand2",
            text_color="#ffffff",
            fg_color="#8C43EB"
        )
        self.theme_dark.pack(pady=5, padx=15, anchor="w")

        self.theme_light = ctk.CTkRadioButton(
            self.theme_frame,
            text="☀️ Светлая",
            variable=self.theme_var,
            value="light",
            cursor="hand2",
            text_color="#ffffff",
            fg_color="#8C43EB"
        )
        self.theme_light.pack(pady=5, padx=15, anchor="w")

        self.save_btn = ctk.CTkButton(
            self.right_panel,
            text="Сохранить",
            command=lambda: self.save_settings(),
            fg_color="#8C43EB",
            hover_color="#6b2fb8",
            width=200,
            height=40,
            cursor="hand2",
            text_color="white",
            corner_radius=8
        )
        self.save_btn.pack(pady=(20, 10))

        self.close_panel_btn = ctk.CTkButton(
            self.right_panel,
            text="✖️ Закрыть",
            command=lambda: self.close_panel(),
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            width=200,
            height=40,
            cursor="hand2",
            text_color="#ffffff",
            corner_radius=8,
            border_width=1,
            border_color="#3a3a3a"
        )
        self.close_panel_btn.pack(pady=(0, 20))

        self.check_server()
        self.init_profile()

    # ---------- ВСЕ МЕТОДЫ ----------
    def init_profile(self):
        profile_path = "student_profile.json"
        if not os.path.exists(profile_path):
            default_profile = {
                "student_name": "Student",
                "first_lesson": datetime.now().isoformat(),
                "last_lesson": None,
                "mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []},
                "topics_passed": [],
                "strengths": [],
                "total_lessons": 0,
                "last_week_mistakes": []
            }
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(default_profile, f, indent=4, ensure_ascii=False)
            self.add_message("Джейн", "📊 Создан новый профиль ученика. Я буду запоминать твой прогресс!")

    def get_student_profile(self):
        profile_path = "student_profile.json"
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []}, "topics_passed": [], "strengths": []}

    def save_student_profile(self, profile):
        profile["last_lesson"] = datetime.now().isoformat()
        profile["total_lessons"] = profile.get("total_lessons", 0) + 1
        with open("student_profile.json", 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=4, ensure_ascii=False)

    def update_profile_from_dialogue(self, user_text, jane_response):
        profile = self.get_student_profile()
        mistake_indicators = ["mistake", "error", "incorrect", "wrong", "неправильно", "ошибка"]
        is_mistake = any(indicator in jane_response.lower() for indicator in mistake_indicators)
        if is_mistake:
            grammar_keywords = ["grammar", "tense", "verb", "noun", "adjective", "past", "future", "present"]
            vocab_keywords = ["vocabulary", "word", "spelling", "meaning", "definition"]
            mistake_type = "general"
            for kw in grammar_keywords:
                if kw in jane_response.lower():
                    mistake_type = "grammar"
                    break
            for kw in vocab_keywords:
                if kw in jane_response.lower():
                    mistake_type = "vocabulary"
                    break
            error_entry = {
                "date": datetime.now().isoformat(),
                "user_text": user_text[:100],
                "jane_response": jane_response[:200],
                "type": mistake_type
            }
            profile["mistakes"][mistake_type].append(error_entry)
            for key in profile["mistakes"]:
                if len(profile["mistakes"][key]) > 20:
                    profile["mistakes"][key] = profile["mistakes"][key][-20:]
            profile["last_week_mistakes"].append({"date": datetime.now().isoformat(), "type": mistake_type})
            if len(profile["last_week_mistakes"]) > 50:
                profile["last_week_mistakes"] = profile["last_week_mistakes"][-50:]
            self.add_message("Джейн", f"📝 *Записано в профиль: ошибка типа '{mistake_type}'*")
        praise_indicators = ["good", "excellent", "great", "perfect", "well done", "correct", "правильно", "отлично"]
        is_praise = any(indicator in jane_response.lower() for indicator in praise_indicators)
        if is_praise and len(user_text) > 10:
            profile["strengths"].append({
                "date": datetime.now().isoformat(),
                "user_text": user_text[:100],
                "jane_response": jane_response[:100]
            })
            if len(profile["strengths"]) > 20:
                profile["strengths"] = profile["strengths"][-20:]
        self.save_student_profile(profile)

    def get_dynamic_prompt(self):
        lang = self.current_lang
        lang_instruction = "Ответь на русском языке, кратко." if lang == "ru" else "Answer in English, keep responses short."
        
        profile = self.get_student_profile()
        grammar_mistakes = profile.get("mistakes", {}).get("grammar", [])
        vocab_mistakes = profile.get("mistakes", {}).get("vocabulary", [])
        
        recent_grammar = [err.get("jane_response", "")[:50] for err in grammar_mistakes[-5:]]
        recent_vocab = [err.get("jane_response", "")[:50] for err in vocab_mistakes[-5:]]
        
        strengths = profile.get("strengths", [])[-3:]
        strengths_text = "\n".join([f"- {s.get('jane_response', '')[:50]}" for s in strengths]) if strengths else "Not enough data yet."
        
        topics_passed = profile.get("topics_passed", [])
        topics_str = ", ".join(topics_passed[-5:]) if topics_passed else "None yet."
        
        # ОБЩАЯ ИНСТРУКЦИЯ ДЛЯ ВСЕХ РЕЖИМОВ
        female_identity = """IMPORTANT: You are Jane, a female AI assistant. When speaking in Russian, ALWAYS refer to yourself in the FEMININE GENDER:
    - Use "я сказала", "я сделала", "я была", "я преподавательница", "я ответила" instead of masculine forms.
    - Use feminine forms of verbs and adjectives (e.g., "я готова", "я уверена", "я думала", "я хотела").
    - This applies to ALL your responses in Russian, regardless of the mode (lesson or free)."""
        
        if self.mode == "lesson":
            prompt = f"""You are Jane, a helpful AI assistant.
    {lang_instruction}
    {female_identity}
    The student is Russian-speaking, but respond in the language they use.

    📊 STUDENT PROGRESS PROFILE:
    Topics covered: {topics_str}
    Recent grammar mistakes: {', '.join(recent_grammar) if recent_grammar else 'None'}
    Recent vocabulary issues: {', '.join(recent_vocab) if recent_vocab else 'None'}
    Strengths: {strengths_text}
    Total lessons: {profile.get('total_lessons', 0)}

    Your task: help the student improve their English. If they speak Russian, answer in Russian. If they speak English, answer in English.
    Keep responses short (2-3 sentences). Use colorful emojis to make conversation more engaging and friendly (like in messengers): 😊👍❤️🎉🔥💪🤗✨🌟🎯📚💡💬👏🙌💖
    Do NOT use thought tags (like <|thought|>).
    """
        else:
            prompt = f"""You are Jane, a friendly AI companion.
    {lang_instruction}
    {female_identity}
    Respond naturally in the same language as the student.
    The student has completed {profile.get('total_lessons', 0)} lessons.
    Be supportive and helpful. Use emojis freely: 😊👍❤️🎉🔥💪🤗✨🌟🎯📚💡💬👏🙌💖
    """
        
        return prompt

    def check_server(self):
        try:
            requests.get("http://127.0.0.1:8080/health", timeout=2)
            self.status_badge.configure(text="● Готов", text_color="#4CAF50")
        except:
            self.status_badge.configure(text="● Сервер не запущен", text_color="#f44336")

    def ask_jane(self, user_text):
        russian_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
        if any(c in russian_chars for c in user_text.lower()):
            self.current_lang = "ru"
        try:
            system_prompt = self.get_dynamic_prompt()
            
            # Определяем язык ответа
            if self.current_lang == "ru":
                user_prompt = f"{user_text}\n\nОТВЕТЬ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. НЕ ИСПОЛЬЗУЙ АНГЛИЙСКИЙ."
            else:
                user_prompt = f"{user_text}\n\nAnswer ONLY in English. Do NOT use Russian."
            
            history_str = "\n".join(self.conversation_history[-6:])
            if history_str:
                history_str += "\n"
            
            prompt = f"<start_of_turn>system\n{system_prompt}<end_of_turn>\n"
            if history_str:
                prompt += history_str
            prompt += f"<start_of_turn>user\n{user_prompt}<end_of_turn>\n<start_of_turn>model\n"
            
            print(f"📤 Язык ответа: {'РУССКИЙ' if self.current_lang == 'ru' else 'ENGLISH'}")
            
            response = requests.post(self.llm_url, json={
                "prompt": prompt,
                "n_predict": 120,
                "temperature": 0.5,
                "stop": ["<|thought|>", "<end_of_turn>"]
            }, timeout=60)
            
            if response.status_code == 200:
                content = response.json().get("content", "").strip()
                # Очищаем от тегов
                content = re.sub(r'<end_of_turn>.*$', '', content, flags=re.DOTALL).strip()
                content = content.replace("<end_of_turn>", "").strip()
                if content:
                    return content
                else:
                    return "Извините, я не могу ответить на это." if self.current_lang == "ru" else "Sorry, I can't respond."
            else:
                print(f"❌ Сервер вернул ошибку: {response.status_code}")
                return f"Error: {response.status_code}"
        except Exception as e:
            print(f"❌ Исключение в ask_jane: {e}")
            return f"Connection error: {e}"

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_btn.configure(state="normal", text="🔴 Запись...", fg_color="red")
            self.status_badge.configure(text="● Запись...", text_color="#FF9800")
            self.vad.set_stop_callback(self.on_recording_stopped)
            self.vad.start_recording()
        else:
            self.vad.stop_recording()

    def on_recording_stopped(self, audio_data):
        self.is_recording = False
        self.record_btn.configure(state="normal", text="🎤 Запись", fg_color="green")
        self.status_badge.configure(text="● Распознаю...", text_color="#FF9800")
        
        if len(audio_data) > 8000:
            result = self.stt.recognize(audio_data)
            if result:
                text, detected_lang = result
                self.current_lang = detected_lang
                self.add_message("Вы (голос)", text)
                self._process_input(text)
            else:
                self.status_badge.configure(text="● Не распознано", text_color="#f44336")
        else:
            self.status_badge.configure(text="● Слишком коротко", text_color="#f44336")

    def send_text(self):
        text = self.input_text.get("0.0", "end").strip()
        if not text:
            return
        self.input_text.delete("0.0", "end")
        self.add_message("Вы", text)
        self._process_input(text)

    def _process_input(self, text):
        self.send_btn.configure(state="disabled", text="⏳ Думаю...")
        self.status_badge.configure(text="● Джейн думает...", text_color="#FF9800")
        threading.Thread(target=self._get_response, args=(text,), daemon=True).start()

    def _get_response(self, user_text):
        response = self.ask_jane(user_text)
        self.window.after(0, lambda: self._display_response(response, user_text))

    def _display_response(self, response, user_text):
        import re
        # Удаляем теги и служебные символы
        response = re.sub(r'<\|thought\|>.*?(\n|$)', '', response, flags=re.DOTALL)
        response = re.sub(r'<\|.*?\|>', '', response)
        response = re.sub(r'<end_of_turn>', '', response)
        response = re.sub(r'RU$', '', response).strip()
        
        if not response or response.startswith("Error") or response.startswith("Connection error"):
            self.add_message("Джейн", f"[Ошибка] {response}")
            self.status_badge.configure(text="● Ошибка", text_color="#f44336")
            self.send_btn.configure(state="normal", text="📎 Отправить")
            return
        
        self.add_message("Джейн", response)
        threading.Thread(target=tts.speak, args=(response,), daemon=True).start()
        self.update_profile_from_dialogue(user_text, response)
        self.conversation_history.append(f"Student: {user_text}")
        self.conversation_history.append(f"Assistant: {response}")
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-8:]
        self.send_btn.configure(state="normal", text="📎 Отправить")
        self.status_badge.configure(text="● Готов", text_color="#4CAF50")
        self.visualizer.reset()

    def add_message(self, sender, text):
        """Добавляет сообщение в чат (WebView)"""
        is_user = sender == "Вы" or sender == "Вы (голос)"
        if hasattr(self, 'chat_webview'):
            self.chat_webview.add_message(sender, text, is_user)
        else:
            # Фолбек для старого чата (если webview не загрузился)
            pass

    def open_panel(self):
        if not self.panel_visible:
            self.right_panel.pack(side="right", fill="y", padx=(0, 0))
            self.panel_visible = True

    def close_panel(self):
        if self.panel_visible:
            self.right_panel.pack_forget()
            self.panel_visible = False

    def save_settings(self):
        self.mode = self.mode_var.get()
        new_theme = self.theme_var.get()
        
        if new_theme != self.current_theme:
            ctk.set_appearance_mode(new_theme)
            self.current_theme = new_theme
            
            if new_theme == "dark":
                self.window.configure(fg_color="#121212")
                self.main_container.configure(fg_color="#121212")
                self.left_frame.configure(fg_color="#1a1a1a")
                self.right_panel.configure(fg_color="#1a1a1a")
                self.control_frame.configure(fg_color="#1a1a1a")
                self.input_frame.configure(fg_color="#1a1a1a")
                self.input_text.configure(fg_color="#1a1a1a", text_color="#e0e0e0")
                self.chat_frame.configure(fg_color="#1e1e1e")
                self.chat_text.configure(bg="#1e1e1e", fg="#e0e0e0")
                self.mode_frame.configure(fg_color="#222222")
                self.theme_frame.configure(fg_color="#222222")
                self.status_badge.configure(text_color="#4CAF50")
                self.record_btn.configure(fg_color="#2a2a2a", hover_color="#3a3a3a", text_color="#ffffff")
                self.settings_btn.configure(fg_color="#2a2a2a", hover_color="#3a3a3a", text_color="#ffffff")
                self.clear_btn.configure(fg_color="#2a2a2a", hover_color="#3a3a3a", text_color="#ffffff")
                self.send_btn.configure(fg_color="#8C43EB", hover_color="#6b2fb8", text_color="white")
                self.visualizer.canvas.configure(bg="#1e1e1e")
                for rect in self.visualizer.rects:
                    self.visualizer.canvas.itemconfig(rect, fill="#8C43EB")
            else:
                self.window.configure(fg_color="#f0f0f0")
                self.main_container.configure(fg_color="#f0f0f0")
                self.left_frame.configure(fg_color="#ffffff")
                self.right_panel.configure(fg_color="#ffffff")
                self.control_frame.configure(fg_color="#ffffff")
                self.input_frame.configure(fg_color="#e0e0e0")
                self.input_text.configure(fg_color="#ffffff", text_color="#1a1a1a")
                self.chat_frame.configure(fg_color="#f5f5f5")
                self.chat_text.configure(bg="#f5f5f5", fg="#1a1a1a")
                self.mode_frame.configure(fg_color="#e8e8e8")
                self.theme_frame.configure(fg_color="#e8e8e8")
                self.status_badge.configure(text_color="#4CAF50")
                self.record_btn.configure(fg_color="#e0e0e0", hover_color="#d0d0d0", text_color="#1a1a1a")
                self.settings_btn.configure(fg_color="#e0e0e0", hover_color="#d0d0d0", text_color="#1a1a1a")
                self.clear_btn.configure(fg_color="#e0e0e0", hover_color="#d0d0d0", text_color="#1a1a1a")
                self.send_btn.configure(fg_color="#8C43EB", hover_color="#6b2fb8", text_color="white")
                self.visualizer.canvas.configure(bg="#f0f0f0")
                for rect in self.visualizer.rects:
                    self.visualizer.canvas.itemconfig(rect, fill="#8C43EB")
        
        self.close_panel()
        self.add_message("Джейн", f"⚙️ Режим изменён на {'Урок' if self.mode == 'lesson' else 'Свободное общение'}")

    def clear_chat(self):
        if hasattr(self, 'chat_webview'):
            self.chat_webview.clear()
        self.conversation_history = []

    def run(self):
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.window.mainloop()

    def on_closing(self):
        if self.is_recording:
            self.vad.stop_recording()
        self.window.destroy()

if __name__ == "__main__":
    app = EnglishTeacherApp()
    app.run()