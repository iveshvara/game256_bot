from aiogram import Bot
from aiogram.dispatcher import Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from random import randrange
from asyncio import sleep
import sqlite3
import locale

from settings import TOKEN


bot = Bot(TOKEN)
dp = Dispatcher(bot)
connect = sqlite3.connect('base.db')
cursor = connect.cursor()

locale.setlocale(locale.LC_ALL, '')
SLEEP_TIME = 0.1
MAX_NUMBER = 1024
MAX_NUMBER_STEP = 10

in_progress = [False, '']
process_icon = ''


async def get_current_state(uid, undo_number, last_text='', last_inline_kb=''):
    global process_icon

    cursor.execute(f'SELECT i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    text = ''
    inline_kb = InlineKeyboardMarkup(row_width=1)
    massive = []
    massive_line = []
    massive_next = []
    current_score = 0
    max_score = 0
    uniqueness_button = 0
    mood = 0

    for line in matrix:
        if matrix.index(line) == 0:
            count = 0
            for i in line:
                count += 1
                if count == 1:
                    max_score = '🏆 ' + locale.format_string('%d', i, grouping=True) + ' '
                elif count == 2:
                    current_score = '🏅 ' + locale.format_string('%d', i, grouping=True) + ' '
                else:
                    massive_next.append(InlineKeyboardButton(text=str(i), callback_data='next ' + str(count)))
        else:
            column = 0
            for i in line:
                column += 1
                uniqueness_button += 1
                if i == 0:
                    meaning = ' '
                else:
                    meaning = i
                    mood += 1
                massive_line.append(InlineKeyboardButton(text=meaning, callback_data='column ' + str(uniqueness_button) + ' ' + str(column)))
            massive.append(massive_line)
            massive_line = []

    inline_kb.row(InlineKeyboardButton(text='undo ' + str(undo_number), callback_data='undo'), *massive_next)
    for massive_line in massive:
        inline_kb.row(*massive_line)

    if in_progress[0] and in_progress[1] == uid:
        process_icon += '\.'
    else:
        process_icon = ''

    if mood < 5:
        mood_icon = '😎'
    elif mood < 10:
        mood_icon = '🤣'
    elif mood < 12:
        mood_icon = '😂'
    elif mood < 15:
        mood_icon = '😆'
    elif mood < 17:
        mood_icon = '😃'
    elif mood < 20:
        mood_icon = '😀'
    elif mood < 22:
        mood_icon = '🤯'
    elif mood < 23:
        mood_icon = '😬'
    elif mood < 24:
        mood_icon = '😰'
    elif mood < 25:
        mood_icon = '😱'
    else:
        mood_icon = '😵'

    # f'{text:<33}'
    text = '`' + max_score + current_score + '   ' + mood_icon + ' ' + process_icon + '`'

    # changes = last_text != text or last_inline_kb != inline_kb
    changes = True

    return text, inline_kb, changes


async def find_coincidences_recursively(callback, uid, matrix, meaning, column, line, undo_number):
    text, inline_kb = '', ''

    if meaning == 0:
        return text, inline_kb

    if matrix[line][column] != meaning:
        matrix[line][column] = meaning
        cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {line} AND id = {uid}')
        connect.commit()
        await send_message(callback, uid, undo_number, text, inline_kb, False)

    new_line = line
    found = 0
    plucking_zero = []

    if column != 1 and matrix[line][column - 1] == meaning:
        found += 1
        matrix[line][column - 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column - 1} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()
        plucking_zero.append([line, column - 1])

        await send_message(callback, uid, undo_number, text, inline_kb)

    if column != len(matrix[line]) - 1 and matrix[line][column + 1] == meaning:
        found += 1
        matrix[line][column + 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column + 1} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()
        plucking_zero.append([line, column + 1])

        await send_message(callback, uid, undo_number, text, inline_kb)

    if line != len(matrix) - 1 and matrix[line + 1][column] == meaning:
        found += 1
        matrix[line][column] = 0
        new_line = line + 1
        cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()
        if line != 1 and matrix[line-1][column] != 0:
            plucking_zero.append([line, column])

    if found > 0:
        meaning *= 2 * found
        if meaning > MAX_NUMBER:
            meaning = 0
        matrix[new_line][column] = meaning
        cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {new_line} AND id = {uid}')
        connect.commit()

        await send_message(callback, uid, undo_number, text, inline_kb)

        text, inline_kb = await find_coincidences_recursively(callback, uid, matrix, meaning, column, new_line, undo_number)

    for point in plucking_zero:
        column = point[1]
        line = point[0]
        for i in range(point[0] + 1, 6):
            if matrix[i][column] == 0:
                line = i

        values = False
        for i in range(line, 0, -1):
            if matrix[i][column] != 0:
                values = True
                break

        if values:
            while matrix[line][column] == 0:
                for i in range(line, 1, -1):
                    matrix[i][column] = matrix[i - 1][column]
                    cursor.execute(f'UPDATE matrix SET i{column} = {matrix[i][column]} WHERE i = {i} AND id = {uid}')
                    connect.commit()
                if matrix[1][column] != 0:
                    matrix[1][column] = 0
                    cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = 1 AND id = {uid}')
                    connect.commit()
                await send_message(callback, uid, undo_number, text, inline_kb)

            for i in range(line, 1, -1):
                text, inline_kb = await find_coincidences_recursively(callback, uid, matrix, matrix[i][column], column, i, undo_number)

    return text, inline_kb


async def send_message(callback, uid, undo_number, text='', inline_kb='', need_sleep=True):
    text, inline_kb, changes = await get_current_state(uid, undo_number, text, inline_kb)
    if changes:
        if need_sleep:
            await sleep(SLEEP_TIME)
        try:
            await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)
        # except Exception as e:
        #     print(str(e))
        except Exception:
            pass


async def save_recover_undo(uid, save=True):
    for i in range(7):
        text = 'UPDATE matrix SET '
        for ii in range(1, 6):
            if save:
                for iii in range(10, 1, -1):
                    text += f'i{ii}_{iii} = i{ii}_{iii - 1}, '
                text += f'i{ii}_1 = i{ii}, '
            else:
                for iii in range(0, 10):
                    if iii == 0:
                        text += f'i{ii} = i{ii}_{iii + 1}, '
                    else:
                        text += f'i{ii}_{iii} = i{ii}_{iii + 1}, '
                text += f'i{ii}_10 = 0, '
        text = text[:-2]
        text += f' WHERE i = {i} AND id = {uid}'
        cursor.execute(text)
        connect.commit()


async def get_undo(uid):
    cursor.execute(f'SELECT i1_1, i1_2, i1_3, i1_4, i1_5, i1_6, i1_7, i1_8, i1_9, i1_10 FROM matrix WHERE i = 0 AND id = {uid}')
    result = cursor.fetchall()[0]

    undo_number = 0
    for i in result:
        if i != 0:
            undo_number += 1

    # undo_number = f'{str(undo_number):>2}'
    if undo_number == 10:
        undo_number = str(undo_number)
    else:
        undo_number = '0' + str(undo_number)

    return undo_number


@dp.callback_query_handler(lambda x: x.data and x.data.startswith('next '))
async def undo(callback: CallbackQuery):
    uid = callback.from_user.id

    i = callback.data.replace('next ', '')
    # cursor.execute(f'SELECT i{i} FROM matrix WHERE i = 0 AND id = {uid}')
    cursor.execute(f'SELECT i5 FROM matrix WHERE i = 0 AND id = {uid}')
    old_meaning = cursor.fetchone()[0]

    if i == '5':
        new_meaning = old_meaning
        while new_meaning == old_meaning:
            new_meaning = 2 ** randrange(1, MAX_NUMBER_STEP)
    elif i == '4':
        if old_meaning == MAX_NUMBER:
            new_meaning = 2
        else:
            new_meaning = old_meaning * 2
    elif i == '3':
        if old_meaning == 2:
            new_meaning = MAX_NUMBER
        else:
            new_meaning = old_meaning / 2

    # cursor.execute(f'UPDATE matrix SET i{i} = {new_meaning} WHERE i = 0 AND id = {uid}')
    cursor.execute(f'UPDATE matrix SET i5 = {new_meaning} WHERE i = 0 AND id = {uid}')
    connect.commit()

    undo_number = await get_undo(uid)
    await send_message(callback, uid, undo_number, '', '', False)
    await callback.answer()


@dp.callback_query_handler(text='undo')
async def undo(callback: CallbackQuery):
    uid = callback.from_user.id

    await save_recover_undo(uid, save=False)
    
    undo_number = await get_undo(uid)
    await send_message(callback, uid, undo_number, '', '', False)
    await callback.answer()


@dp.callback_query_handler(lambda x: x.data and x.data.startswith('column '))
async def callback_query_handler(callback: CallbackQuery):
    global in_progress
    uid = callback.from_user.id

    if in_progress[0] and in_progress[1] == uid:
        return
    in_progress[0], in_progress[1] = True, uid

    await save_recover_undo(uid)

    cursor.execute(f'SELECT i, i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    max_score = matrix[0][1]
    current_score = matrix[0][2] + 1
    cursor.execute(f'UPDATE matrix SET i1 = {max_score}, i2 = {current_score} WHERE i = 0 AND id = {uid}')
    connect.commit()

    current_column = int(callback.data[-1])
    current_line = 5
    new_meaning = 0
    current_meaning = 0

    index = -1
    for line in matrix:
        index += 1
        current_meaning = line[current_column]
        if index == 0:
            new_meaning = line[-1]
        elif current_meaning != 0:
            current_line = index - 1
            break

    if current_line == 0:
        if new_meaning == current_meaning:
            current_line = 1
            new_meaning *= 2
        else:
            return

    matrix_list = list()
    for line in matrix:
        matrix_list.append(list(line))

    undo_number = await get_undo(uid)
    text, inline_kb = await find_coincidences_recursively(callback, uid, matrix_list, new_meaning, current_column, current_line, undo_number)

    meaning = 2 ** randrange(1, MAX_NUMBER_STEP)
    line = matrix[0]
    for i in range(3, 6):
        cursor.execute(f'UPDATE matrix SET i{i} = {meaning} WHERE i = 0 AND id = {uid}')
        connect.commit()
        meaning = line[i]

    in_progress[0], in_progress[1] = False, ''
    await send_message(callback, uid, undo_number, text, inline_kb, False)
    await callback.answer()


@dp.message_handler(commands=['start'])
async def command_start(message: Message):
    uid = message.from_user.id

    connect.execute('CREATE TABLE IF NOT EXISTS matrix(id INTEGER, i INTEGER, '
                    'i1 INTEGER, i2 INTEGER, i3 INTEGER, i4 INTEGER, i5 INTEGER,'
                    'i1_1 INTEGER, i2_1 INTEGER, i3_1 INTEGER, i4_1 INTEGER, i5_1 INTEGER,'
                    'i1_2 INTEGER, i2_2 INTEGER, i3_2 INTEGER, i4_2 INTEGER, i5_2 INTEGER,'
                    'i1_3 INTEGER, i2_3 INTEGER, i3_3 INTEGER, i4_3 INTEGER, i5_3 INTEGER,'
                    'i1_4 INTEGER, i2_4 INTEGER, i3_4 INTEGER, i4_4 INTEGER, i5_4 INTEGER,'
                    'i1_5 INTEGER, i2_5 INTEGER, i3_5 INTEGER, i4_5 INTEGER, i5_5 INTEGER,'
                    'i1_6 INTEGER, i2_6 INTEGER, i3_6 INTEGER, i4_6 INTEGER, i5_6 INTEGER,'
                    'i1_7 INTEGER, i2_7 INTEGER, i3_7 INTEGER, i4_7 INTEGER, i5_7 INTEGER,'
                    'i1_8 INTEGER, i2_8 INTEGER, i3_8 INTEGER, i4_8 INTEGER, i5_8 INTEGER,'
                    'i1_9 INTEGER, i2_9 INTEGER, i3_9 INTEGER, i4_9 INTEGER, i5_9 INTEGER,'
                    'i1_10 INTEGER, i2_10 INTEGER, i3_10 INTEGER, i4_10 INTEGER, i5_10 INTEGER)')
    connect.commit()

    cursor.execute(f'SELECT i, i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()
    max_score = 0
    if len(matrix) != 0:
        max_score = matrix[0][1]
        current_score = matrix[0][2]
        if current_score > max_score:
            max_score = current_score

        cursor.execute(f'DELETE FROM matrix WHERE id = {uid}')
        connect.commit()
    for i in range(6):
        cursor.execute(f'INSERT INTO matrix (id, i, '
                       'i1, i2, i3, i4, i5,'
                       'i1_1, i2_1, i3_1, i4_1, i5_1, '
                       'i1_2, i2_2, i3_2, i4_2, i5_2, '
                       'i1_3, i2_3, i3_3, i4_3, i5_3, '
                       'i1_4, i2_4, i3_4, i4_4, i5_4, '
                       'i1_5, i2_5, i3_5, i4_5, i5_5, '
                       'i1_6, i2_6, i3_6, i4_6, i5_6, '
                       'i1_7, i2_7, i3_7, i4_7, i5_7, '
                       'i1_8, i2_8, i3_8, i4_8, i5_8, '
                       'i1_9, i2_9, i3_9, i4_9, i5_9, '
                       'i1_10, i2_10, i3_10, i4_10, i5_10) '
                       f' VALUES ({uid}, {i}, '
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0,'
                       '0, 0, 0, 0, 0)')
        connect.commit()
    for i in range(3, 6):
        cursor.execute(f'UPDATE matrix SET i{i} = {2 ** randrange(1, MAX_NUMBER_STEP)} WHERE i = 0 AND id = {uid}')
        connect.commit()
    cursor.execute(f'UPDATE matrix SET i1 = {max_score} WHERE i = 0 AND id = {uid}')
    connect.commit()

    undo_number = await get_undo(uid)
    text, inline_kb, changes = await get_current_state(uid, undo_number)
    await message.answer(text, parse_mode="MarkdownV2", reply_markup=inline_kb)


@dp.message_handler()
async def delete_other(message: Message):
    await message.delete()


executor.start_polling(dp, skip_updates=True)
