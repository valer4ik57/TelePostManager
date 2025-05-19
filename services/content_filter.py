import os
import logging  # Добавим logging

logger = logging.getLogger(__name__)


class ContentFilter:
    def __init__(self, words_file):
        self.banned_words = set()  # Используем set для более быстрой проверки наличия слова
        self.words_file = words_file
        self.load_words()

    def load_words(self):
        try:
            if not os.path.exists(self.words_file):
                logger.warning(
                    f"Файл запрещенных слов {self.words_file} не найден. Будет создан пустой файл при первом добавлении слова.")
                # Создаем пустой файл, если его нет, чтобы избежать ошибок при первой записи
                with open(self.words_file, 'a', encoding='utf-8') as f:
                    pass
                self.banned_words = set()
                return

            with open(self.words_file, 'r', encoding='utf-8') as f:
                # Используем set() для удаления дубликатов и более быстрой проверки
                self.banned_words = {word.strip().lower() for word in f if word.strip()}
            logger.info(f"Загружено {len(self.banned_words)} запрещенных слов из {self.words_file}")
        except Exception as e:
            logger.error(f"Ошибка загрузки запрещенных слов из {self.words_file}: {e}", exc_info=True)
            self.banned_words = set()

    def check_text(self, text: str) -> list:
        if not text:
            return []
        text_lower = text.lower()
        # Находим все вхождения слов из banned_words в text_lower
        # Можно использовать более сложный поиск по словам, но для простоты оставим так
        found_words = [word for word in self.banned_words if word in text_lower]
        return found_words

    def _save_words_to_file(self):
        """Приватный метод для сохранения текущего набора слов в файл."""
        try:
            with open(self.words_file, 'w', encoding='utf-8') as f:
                for word in sorted(list(self.banned_words)):  # Сохраняем отсортированный список для порядка в файле
                    f.write(f"{word}\n")
            return True
        except Exception as e:
            logger.error(f"Ошибка записи списка запрещенных слов в файл {self.words_file}: {e}", exc_info=True)
            return False

    def add_word(self, word: str) -> bool:
        word_lower = word.strip().lower()
        if not word_lower:
            logger.warning("Попытка добавить пустое запрещенное слово.")
            return False

        if word_lower not in self.banned_words:
            self.banned_words.add(word_lower)
            if self._save_words_to_file():
                logger.info(f"Запрещенное слово '{word_lower}' добавлено и сохранено.")
                return True
            else:
                # Если сохранить не удалось, откатываем добавление в память
                self.banned_words.discard(word_lower)
                logger.error(f"Не удалось сохранить слово '{word_lower}' в файл, изменение отменено.")
                return False
        else:
            logger.info(f"Запрещенное слово '{word_lower}' уже в списке.")
            return False  # Слово уже было, но это не ошибка, просто не добавили заново

    def remove_word(self, word: str) -> bool:
        word_lower = word.strip().lower()
        if not word_lower:
            logger.warning("Попытка удалить пустое запрещенное слово.")
            return False

        if word_lower in self.banned_words:
            self.banned_words.discard(word_lower)  # Используем discard, чтобы не было ошибки, если слова вдруг нет
            if self._save_words_to_file():
                logger.info(f"Запрещенное слово '{word_lower}' удалено и файл обновлен.")
                return True
            else:
                # Если сохранить не удалось, возвращаем слово в память
                self.banned_words.add(word_lower)
                logger.error(f"Не удалось обновить файл после удаления слова '{word_lower}', изменение отменено.")
                return False
        else:
            logger.info(f"Запрещенное слово '{word_lower}' не найдено в списке для удаления.")
            return False  # Слова не было, это не ошибка, просто не удалили