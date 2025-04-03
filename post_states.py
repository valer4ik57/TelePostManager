from aiogram.fsm.state import StatesGroup, State

class PostCreation(StatesGroup):
    SELECT_CHANNEL = State()
    CONTENT = State()
    MEDIA = State()
    SCHEDULE = State()
    CONFIRM = State()