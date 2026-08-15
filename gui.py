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
        self.window.geometry("1000x700")
        self.window.minsize(800, 600)

        self.current_theme = "dark"
        self.panel_visible = False
        self.is_recording = False
        self.mode = "lesson"
        self.current_lang = "en"
        self.llm_url = "http://127.0.0.1:8080/completion"
        self.conversation_history = []
        self.waiting_for_translation = False

        # Голосовые модули
        self.vad = audio_vad.AudioVAD()
        self.stt = stt_engine.STTEngine()

        # UI
        self.main_container = ctk.CTkFrame(self.window)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.left_frame = ctk.CTkFrame(self.main_container)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.title_label = ctk.CTkLabel(self.left_frame, text="🎙️ ИИ-ПРЕПОДАВАТЕЛЬ АНГЛИЙСКОГО", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=10)

        self.visualizer = AudioVisualizer(self.left_frame, width=400, height=80)
        self.visualizer.pack(pady=10)

        self.chat_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.chat_frame.pack(fill="both", expand=True)

        self.chat_text = ctk.CTkTextbox(self.chat_frame, wrap="word", fg_color="#1e1e1e")
        self.chat_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.chat_text.insert("0.0", "Джейн: Привет! Я твой преподаватель английского.\nЯ буду запоминать твои ошибки и подстраивать уроки под тебя.\n\n")
        self.chat_text.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self.left_frame)
        self.input_frame.pack(fill="x", pady=5)

        self.input_text = ctk.CTkTextbox(self.input_frame, height=60, wrap="word")
        self.input_text.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.send_btn = ctk.CTkButton(self.input_frame, text="📎 Отправить", fg_color="#8C43EB", command=self.send_text, width=100, cursor="hand2", text_color="black")
        self.send_btn.pack(side="right")

        self.button_frame = ctk.CTkFrame(self.left_frame)
        self.button_frame.pack(fill="x", pady=10)

        self.record_btn = ctk.CTkButton(self.button_frame, text="🎤 Запись", fg_color="green", command=self.toggle_recording, width=120, cursor="hand2")
        self.record_btn.pack(side="left", padx=5)

        self.settings_btn = ctk.CTkButton(self.button_frame, text="⚙️ Настройки", fg_color="#8C43EB", command=self.open_panel, width=120, cursor="hand2", text_color="black")
        self.settings_btn.pack(side="right", padx=5)

        self.clear_btn = ctk.CTkButton(self.button_frame, text="🗑️ Очистить чат", fg_color="#8C43EB", command=self.clear_chat, width=120, cursor="hand2", text_color="black")
        self.clear_btn.pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(self.left_frame, text="Статус: Готов", font=ctk.CTkFont(size=9))
        self.status_label.pack(pady=5)

        # Правая панель
        self.right_panel = ctk.CTkFrame(self.main_container, width=220, fg_color="#2b2b2b", border_width=2, border_color="#8C43EB")
        self.panel_title = ctk.CTkLabel(self.right_panel, text="⚙️ НАСТРОЙКИ", font=ctk.CTkFont(size=14, weight="bold"))
        self.panel_title.pack(pady=15)

        self.mode_label = ctk.CTkLabel(self.right_panel, text="Режим:", font=ctk.CTkFont(size=12))
        self.mode_label.pack(pady=(10, 5))
        self.mode_var = ctk.StringVar(value=self.mode)
        self.mode_lesson = ctk.CTkRadioButton(self.right_panel, text="🎓 Урок (исправляет ошибки)", variable=self.mode_var, value="lesson", cursor="hand2")
        self.mode_lesson.pack(pady=5, padx=10, anchor="w")
        self.mode_free = ctk.CTkRadioButton(self.right_panel, text="💬 Свободное общение", variable=self.mode_var, value="free", cursor="hand2")
        self.mode_free.pack(pady=5, padx=10, anchor="w")

        self.theme_label = ctk.CTkLabel(self.right_panel, text="Тема:", font=ctk.CTkFont(size=12))
        self.theme_label.pack(pady=(15, 5))
        self.theme_var = ctk.StringVar(value=self.current_theme)
        self.theme_dark = ctk.CTkRadioButton(self.right_panel, text="🌙 Темная", variable=self.theme_var, value="dark", cursor="hand2")
        self.theme_dark.pack(pady=5, padx=10, anchor="w")
        self.theme_light = ctk.CTkRadioButton(self.right_panel, text="☀️ Светлая", variable=self.theme_var, value="light", cursor="hand2")
        self.theme_light.pack(pady=5, padx=10, anchor="w")

        self.save_btn = ctk.CTkButton(self.right_panel, text="Сохранить", command=self.save_settings, fg_color="#8C43EB", width=180, cursor="hand2", text_color="black")
        self.save_btn.pack(pady=(20, 8), padx=8)
        self.close_panel_btn = ctk.CTkButton(self.right_panel, text="✖️ Закрыть", command=self.close_panel, fg_color="#4a4a4a", width=180, cursor="hand2", text_color="white")
        self.close_panel_btn.pack(pady=(0, 15), padx=8)

        self.check_server()
        self.init_profile()

    def init_profile(self):
        """Создаёт файл профиля, если его нет"""
        profile_path = "student_profile.json"
        if not os.path.exists(profile_path):
            default_profile = {
                "student_name": "Student",
                "first_lesson": datetime.now().isoformat(),
                "last_lesson": None,
                "mistakes": {
                    "grammar": [],
                    "vocabulary": [],
                    "pronunciation": []
                },
                "topics_passed": [],
                "strengths": [],
                "total_lessons": 0,
                "last_week_mistakes": []
            }
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(default_profile, f, indent=4, ensure_ascii=False)
            self.add_message("Джейн", "📊 Создан новый профиль ученика. Я буду запоминать твой прогресс!")

    def get_student_profile(self):
        """Загружает профиль ученика из JSON-файла"""
        profile_path = "student_profile.json"
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []}, "topics_passed": [], "strengths": []}

    def save_student_profile(self, profile):
        """Сохраняет профиль ученика в JSON-файл"""
        profile["last_lesson"] = datetime.now().isoformat()
        profile["total_lessons"] = profile.get("total_lessons", 0) + 1
        with open("student_profile.json", 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=4, ensure_ascii=False)

    def update_profile_from_dialogue(self, user_text, jane_response):
        """Анализирует диалог и обновляет профиль"""
        profile = self.get_student_profile()
        
        # Простейший анализ: ищем индикаторы ошибок в ответе Джейн
        mistake_indicators = ["mistake", "error", "incorrect", "wrong", "неправильно", "ошибка"]
        is_mistake = any(indicator in jane_response.lower() for indicator in mistake_indicators)
        
        if is_mistake:
            # Пытаемся извлечь тип ошибки (очень упрощённо)
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
            
            # Добавляем ошибку в профиль
            error_entry = {
                "date": datetime.now().isoformat(),
                "user_text": user_text[:100],
                "jane_response": jane_response[:200],
                "type": mistake_type
            }
            profile["mistakes"][mistake_type].append(error_entry)
            
            # Ограничиваем историю ошибок (последние 20)
            for key in profile["mistakes"]:
                if len(profile["mistakes"][key]) > 20:
                    profile["mistakes"][key] = profile["mistakes"][key][-20:]
            
            # Обновляем статистику за последнюю неделю
            profile["last_week_mistakes"].append({"date": datetime.now().isoformat(), "type": mistake_type})
            if len(profile["last_week_mistakes"]) > 50:
                profile["last_week_mistakes"] = profile["last_week_mistakes"][-50:]
            
            self.add_message("Джейн", f"📝 *Записано в профиль: ошибка типа '{mistake_type}'*")
        
        # Проверяем, есть ли похвала (сильные стороны)
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
        # Упрощаем промпт — убираем всё, что может заставить модель думать
        return """You are Jane, an AI English tutor. The student is Russian-speaking.
- Keep responses short and helpful (2-3 sentences).
- Do not use emojis."""

    def check_server(self):
        try:
            requests.get("http://127.0.0.1:8080/health", timeout=2)
            self.status_label.configure(text="Статус: Готов ✅", text_color="white")
        except:
            self.status_label.configure(text="Статус: Сервер не запущен ❌", text_color="red")

    def ask_jane(self, user_text):
        try:
            system_prompt = self.get_dynamic_prompt()
            
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
                "n_predict": 200,
                "temperature": 0.7,
                "stop": ["<|thought|>", "<end_of_turn>"],
                "chat_template_kwargs": {"enable_thinking": False}  # ОТКЛЮЧАЕМ МЫШЛЕНИЕ!
            }, timeout=60)
            
            if response.status_code == 200:
                content = response.json().get("content", "").strip()
                content = content.replace("<end_of_turn>", "").strip()
                if content:
                    return content
                else:
                    return "Извините, я не могу ответить на это." if self.current_lang == "ru" else "Sorry, I can't respond."
            else:
                print(f"❌ Ошибка: {response.status_code}")
                return f"Error: {response.status_code}"
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return f"Connection error: {e}"

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_btn.configure(state="normal", text="🔴 Запись...", fg_color="red")
            self.status_label.configure(text="Статус: Говорите...", text_color="green")
            self.vad.set_stop_callback(self.on_recording_stopped)
            self.vad.start_recording()
        else:
            self.vad.stop_recording()

    def on_recording_stopped(self, audio_data):
        self.is_recording = False
        self.record_btn.configure(state="normal", text="🎤 Запись", fg_color="green")
        
        if len(audio_data) > 8000:
            self.status_label.configure(text="Статус: Распознаю...", text_color="orange")
            
            import numpy as np
            silence = np.zeros(8000, dtype=np.int16)
            audio_with_silence = audio_data + silence.tobytes()
            
            result = self.stt.recognize(audio_with_silence)
            if result:
                text, detected_lang = result
                print(f"Язык: {detected_lang}")
                self.current_lang = detected_lang
                self.add_message("Вы (голос)", text)
                self._process_input(text)
            else:
                self.status_label.configure(text="Статус: Не распознано", text_color="red")
        else:
            self.status_label.configure(text="Статус: Слишком коротко", text_color="red")

    def send_text(self):
        text = self.input_text.get("0.0", "end").strip()
        if not text:
            return
        self.input_text.delete("0.0", "end")
        self.add_message("Вы", text)
        self._process_input(text)

    def _process_input(self, text):
        self.send_btn.configure(state="disabled", text="⏳ Думаю...")
        self.status_label.configure(text="Статус: Джейн думает...", text_color="orange")
        threading.Thread(target=self._get_response, args=(text,), daemon=True).start()

    def _get_response(self, user_text):
        response = self.ask_jane(user_text)
        self.window.after(0, lambda: self._display_response(response, user_text))

    def _display_response(self, response, user_text):
        if not response or response.startswith("Error") or response.startswith("Connection error"):
            self.add_message("Джейн", f"[Ошибка] {response}")
            self.status_label.configure(text="Статус: Ошибка", text_color="red")
            self.send_btn.configure(state="normal", text="📎 Отправить")
            return
        
        self.add_message("Джейн", response)
        # Воспроизводим голос в отдельном потоке, чтобы не блокировать GUI
        threading.Thread(target=tts.speak, args=(response,), daemon=True).start()
        
        self.update_profile_from_dialogue(user_text, response)
        
        self.conversation_history.append(f"Student: {user_text}")
        self.conversation_history.append(f"Assistant: {response}")
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-8:]
        
        self.send_btn.configure(state="normal", text="📎 Отправить")
        self.status_label.configure(text="Статус: Готов", text_color="white")
        self.visualizer.reset()

    def add_message(self, sender, text):
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", f"{sender}: {text}\n\n")
        self.chat_text.see("end")
        self.chat_text.configure(state="disabled")

    def save_settings(self):
        self.mode = self.mode_var.get()
        new_theme = self.theme_var.get()
        if new_theme != self.current_theme:
            ctk.set_appearance_mode(new_theme)
            self.current_theme = new_theme
        self.close_panel()
        self.add_message("Джейн", f"⚙️ Режим изменён на {'Урок' if self.mode == 'lesson' else 'Свободное общение'}")

    def clear_chat(self):
        self.chat_text.configure(state="normal")
        self.chat_text.delete("0.0", "end")
        self.chat_text.insert("0.0", "Джейн: Чат очищен. Твой профиль сохранён, продолжим с того же места!\n\n")
        self.chat_text.configure(state="disabled")
        self.conversation_history = []

    def open_panel(self):
        if not self.panel_visible:
            self.right_panel.pack(side="right", fill="y", padx=(0, 0))
            self.settings_btn.pack_forget()
            self.panel_visible = True

    def close_panel(self):
        if self.panel_visible:
            self.right_panel.pack_forget()
            self.settings_btn.pack(side="right", padx=5)
            self.panel_visible = False

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