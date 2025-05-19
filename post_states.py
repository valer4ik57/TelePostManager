from aiogram.fsm.state import StatesGroup, State

class PostCreation(StatesGroup):
    SELECT_TEMPLATE = State()
    FILL_CUSTOM_VARIABLES = State() # Новое состояние для заполнения кастомных переменных
    SELECT_CHANNEL = State()
    CONTENT = State() 
    MEDIA = State()
    SCHEDULE = State()
    CONFIRM = State()

class TemplateStates(StatesGroup):
    AWAITING_NAME = State()
    AWAITING_CONTENT = State()
