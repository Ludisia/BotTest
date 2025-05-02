from aiogram.fsm.state import StatesGroup, State

class LaundryStates(StatesGroup):
    choosing_date = State()
    choosing_machine = State()
    choosing_time = State()

class RestroomStates(StatesGroup):
    choosing_date = State()
    choosing_start = State()
    choosing_duration = State()

class AdminStates(StatesGroup):
    editing_setting = State()
    managing_machines = State()