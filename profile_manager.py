# =========================================================
# PROFILE_MANAGER.PY — Управление режимами и историей диалога
# =========================================================

PROMPT_TEACHER = """You are Jane, an AI English tutor. You ALWAYS answer in English.
- Correct mistakes briefly.
- If student speaks Russian, understand them but answer in English.
- Keep responses short and encouraging.

Student: """

PROMPT_FRIEND = """You are Jane, a friendly AI companion. You are talkative and supportive.
- Speak naturally and casually.
- Use the same language as the student (Russian or English).
- Help the student relax and have fun.

Student: """

class ProfileManager:
    """Управляет режимами общения и историей диалога"""
    
    def __init__(self, speak_callback):
        self.current_prompt = PROMPT_TEACHER
        self.conversation_history = []
        self.speak_callback = speak_callback  # функция для голосового приветствия
    
    def switch_to_teacher(self):
        """Переключает в режим учителя"""
        if self.current_prompt != PROMPT_TEACHER:
            self.current_prompt = PROMPT_TEACHER
            self.conversation_history = []
            print("\n🟢 Режим: УЧИТЕЛЬ")
            if self.speak_callback:
                self.speak_callback("Welcome back to your English lesson!")
    
    def switch_to_friend(self):
        """Переключает в режим друга"""
        if self.current_prompt != PROMPT_FRIEND:
            self.current_prompt = PROMPT_FRIEND
            self.conversation_history = []
            print("\n🔵 Режим: ДРУГ")
            if self.speak_callback:
                self.speak_callback("Okay, let's just chat! What's up?")
    
    def format_prompt(self, user_input):
        """Формирует полный промпт с историей диалога"""
        history_str = "\n".join(self.conversation_history[-6:]) if self.conversation_history else ""
        return self.current_prompt + history_str + f"Student: {user_input}\nAssistant: "
    
    def add_exchange(self, user_input, assistant_response):
        """Добавляет фрагмент диалога в историю"""
        self.conversation_history.append(f"Student: {user_input}")
        self.conversation_history.append(f"Assistant: {assistant_response}")
        # Ограничиваем историю последними 10 сообщениями
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-8:]
    
    def get_profile_name(self):
        """Возвращает название текущего режима"""
        return "УЧИТЕЛЬ" if self.current_prompt == PROMPT_TEACHER else "ДРУГ"