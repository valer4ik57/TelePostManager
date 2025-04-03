from aiogram.fsm.state import StatesGroup, State

class PostCreation(StatesGroup):
    SELECT_TEMPLATE = State()  # Новое состояние для выбора шаблона
    FILL_TEMPLATE = State()  # Новое состояние
    SELECT_CHANNEL = State()
    CONTENT = State()
    MEDIA = State()
    SCHEDULE = State()
    CONFIRM = State()