# post_states.py
from aiogram.fsm.state import StatesGroup, State

class PostCreation(StatesGroup):
    SELECT_TEMPLATE = State()
    FILL_TEMPLATE = State()
    SELECT_CHANNEL = State()
    CONTENT = State() # Для ввода текста, когда шаблон не используется или после выбора "без шаблона"
    MEDIA = State()
    SCHEDULE = State()
    CONFIRM = State()

class TemplateStates(StatesGroup): # Было у вас в templates.py, логично вынести сюда или оставить там
    AWAITING_NAME = State()
    AWAITING_CONTENT = State()
    # Можно добавить AWAITING_MEDIA если делаем сложный шаблон