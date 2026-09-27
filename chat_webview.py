import webview
import threading
import emoji

class ChatWebView:
    def __init__(self, parent_window=None):
        self.parent = parent_window
        self.messages = []
        self.webview_window = None
        self.is_ready = False
        
        # Создаем HTML-шаблон
        self.html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { background: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI Emoji', Arial; font-size: 16px; padding: 15px; }
                .msg { margin-bottom: 10px; }
                .user { color: #8C43EB; }
                .jane { color: #4CAF50; }
                .timestamp { color: #666; font-size: 10px; margin-left: 10px; }
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <script>
                function addMessage(sender, text, isUser) {
                    var chat = document.getElementById('chat');
                    var div = document.createElement('div');
                    div.className = 'msg';
                    div.innerHTML = '<b class="' + (isUser ? 'user' : 'jane') + '">' + sender + ':</b> ' + text;
                    chat.appendChild(div);
                    window.scrollTo(0, document.body.scrollHeight);
                }
                function clearChat() {
                    document.getElementById('chat').innerHTML = '';
                }
            </script>
        </body>
        </html>
        """
        
        # Создаем окно
        self.webview_window = webview.create_window(
            "Чат (цветные эмодзи)",
            html=self.html_template,
            width=500,
            height=400,
            resizable=True
        )
        
        # Запускаем в отдельном потоке
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        """Запускает WebView"""
        webview.start(debug=True)
    
    def add_message(self, sender, text, is_user=False):
        """Добавляет сообщение в чат"""
        if self.webview_window:
            text_with_emoji = emoji.emojize(text, language='alias')
            # Экранируем кавычки
            text_with_emoji = text_with_emoji.replace('"', '\\"').replace("'", "\\'")
            js_code = f'addMessage("{sender}", "{text_with_emoji}", {str(is_user).lower()});'
            self.webview_window.evaluate_js(js_code)
    
    def clear(self):
        """Очищает чат"""
        if self.webview_window:
            self.webview_window.evaluate_js('clearChat();')