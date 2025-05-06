# models/content_filter.py
import os

class ContentFilter:
    def __init__(self, words_file):
        self.banned_words = []
        self.words_file = words_file
        self.load_words()

    def load_words(self):
        try:
            if not os.path.exists(self.words_file):
                # Создаем пустой файл, если он не существует
                with open(self.words_file, 'w', encoding='utf-8') as f:
                    pass # Просто создаем файл
                self.banned_words = []
                print(f"Файл {self.words_file} не найден. Создан пустой файл.")
                return

            with open(self.words_file, 'r', encoding='utf-8') as f:
                self.banned_words = [word.strip().lower() for word in f.readlines() if word.strip()]
        except Exception as e:
            print(f"Ошибка загрузки запрещенных слов из {self.words_file}: {e}")
            self.banned_words = [] # В случае ошибки работаем с пустым списком

    def check_text(self, text: str) -> list:
        """
        Проверяет текст на наличие запрещенных слов.
        Возвращает список найденных запрещенных слов.
        """
        if not text: # Проверка на пустой текст
            return []
        text_lower = text.lower()
        found_words = [word for word in self.banned_words if word in text_lower]
        return found_words

    def add_word(self, word: str):
        """Добавляет слово в список и файл."""
        word_lower = word.strip().lower()
        if word_lower and word_lower not in self.banned_words:
            self.banned_words.append(word_lower)
            try:
                with open(self.words_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{word_lower}") # Добавляем с новой строки для чистоты
                return True
            except Exception as e:
                print(f"Ошибка записи слова в {self.words_file}: {e}")
                # Откатываем добавление в память, если запись не удалась
                if word_lower in self.banned_words:
                    self.banned_words.remove(word_lower)
                return False
        return False # Слово пустое или уже существует

    def remove_word(self, word: str):
        """Удаляет слово из списка и файла."""
        word_lower = word.strip().lower()
        if word_lower in self.banned_words:
            self.banned_words.remove(word_lower)
            try:
                # Перезаписываем файл без удаленного слова
                with open(self.words_file, 'w', encoding='utf-8') as f:
                    for w in self.banned_words:
                        f.write(f"{w}\n")
                return True
            except Exception as e:
                print(f"Ошибка удаления слова из {self.words_file}: {e}")
                # Возвращаем слово в память, если удаление из файла не удалось
                self.banned_words.append(word_lower)
                return False
        return False # Слова нет в списке