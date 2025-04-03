class ContentFilter:
    def __init__(self, words_file):
        with open(words_file, 'r') as f:
            self.banned_words = [word.strip().lower() for word in f.readlines()]

    def check_text(self, text):
        found_words = []
        for word in self.banned_words:
            if word in text.lower():
                found_words.append(word)
        return found_words