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
SLEEP_TIME = 0.2

in_progress = False


async def get_current_state(uid, undo_number):

    cursor.execute(f'SELECT i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    text = ''
    inline_kb = InlineKeyboardMarkup(row_width=1)
    massive = []
    massive_line = []
    massive_next = []
    current_score = 0
    max_score = 0

    for line in matrix:
        if matrix.index(line) == 0:
            count = 0
            for i in line:
                count += 1
                if count == 1:
                    max_score = locale.format_string('%d', i, grouping=True) + ': '
                elif count == 2:
                    current_score = '*' + locale.format_string('%d', i, grouping=True) + '*'
                else:
                    massive_next.append(InlineKeyboardButton(text=str(i), callback_data='next ' + str(count)))
        else:
            column = 0
            for i in line:
                column += 1
                if i == 0:
                    meaning = ' '
                else:
                    meaning = i
                massive_line.append(InlineKeyboardButton(text=meaning, callback_data=str(column)))
            massive.append(massive_line)
            massive_line = []

    inline_kb.row(InlineKeyboardButton(text='undo ' + str(undo_number), callback_data='undo'),
                  # InlineKeyboardButton(text='new', callback_data='new'),
                  *massive_next)
    for massive_line in massive:
        inline_kb.row(*massive_line)

    text = f'{str(max_score) + str(current_score):<51}' + f'{str(text):>19}'

    return text, inline_kb


async def find_coincidences_recursively(callback, uid, matrix, meaning, column, line, undo_number):
    if meaning == 0:
        return

    if matrix[line][column] != meaning:
        matrix[line][column] = meaning
        cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {line} AND id = {uid}')
        connect.commit()
        text, inline_kb = await get_current_state(uid, undo_number)
        await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)

    new_line = line
    found = 0

    if column != 1 and matrix[line][column - 1] == meaning:
        found += 1
        matrix[line][column - 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column - 1} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()
        for i in range(line, 1, -1):
            matrix[i][column - 1] = matrix[i - 1][column - 1]
            cursor.execute(f'UPDATE matrix SET i{column - 1} = {matrix[i - 1][column - 1]} WHERE i = {i} AND id = {uid}')
            connect.commit()
            await find_coincidences_recursively(callback, uid, matrix, matrix[i - 1][column - 1], column - 1, i, undo_number)
        matrix[1][column - 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column - 1} = 0 WHERE i = 1 AND id = {uid}')
        connect.commit()

    if column != len(matrix[line]) - 1 and matrix[line][column + 1] == meaning:
        found += 1
        matrix[line][column + 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column + 1} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()
        for i in range(line, 1, -1):
            matrix[i][column + 1] = matrix[i - 1][column + 1]
            cursor.execute(f'UPDATE matrix SET i{column + 1} = {matrix[i - 1][column + 1]} WHERE i = {i} AND id = {uid}')
            connect.commit()
            await find_coincidences_recursively(callback, uid, matrix, matrix[i - 1][column + 1], column + 1, i, undo_number)
        matrix[1][column + 1] = 0
        cursor.execute(f'UPDATE matrix SET i{column + 1} = 0 WHERE i = 1 AND id = {uid}')
        connect.commit()

    if line != len(matrix) - 1 and matrix[line + 1][column] == meaning:
        found += 1
        matrix[line][column] = 0
        new_line = line + 1
        cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = {line} AND id = {uid}')
        connect.commit()

    if found > 0:
        meaning *= 2 * found
        if meaning > 256:
            meaning = 0
        matrix[new_line][column] = meaning

        cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {new_line} AND id = {uid}')
        connect.commit()

        text, inline_kb = await get_current_state(uid, undo_number)
        await sleep(SLEEP_TIME)
        await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)

        await find_coincidences_recursively(callback, uid, matrix, meaning, column, new_line, undo_number)


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

    undo_number = f'{str(undo_number):>2}'
    return undo_number


@dp.callback_query_handler(lambda x: x.data and x.data.startswith('next '))
async def undo(callback: CallbackQuery):
    uid = callback.from_user.id

    i = callback.data.replace('next ', '')
    cursor.execute(f'SELECT i{i} FROM matrix WHERE i = 0 AND id = {uid}')
    old_meaning = cursor.fetchone()[0]
    new_meaning = old_meaning
    while new_meaning == old_meaning:
        new_meaning = 2 ** randrange(1, 9)
    cursor.execute(f'UPDATE matrix SET i{i} = {new_meaning} WHERE i = 0 AND id = {uid}')
    connect.commit()

    undo_number = await get_undo(uid)
    text, inline_kb = await get_current_state(uid, undo_number)
    await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)


@dp.callback_query_handler(text='undo')
async def undo(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id

    await save_recover_undo(uid, save=False)

    undo_number = await get_undo(uid)
    text, inline_kb = await get_current_state(uid, undo_number)
    await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)


@dp.callback_query_handler(text=['1', '2', '3', '4', '5'])
async def callback_query_handler(callback: CallbackQuery):
    await callback.answer()

    global in_progress

    if in_progress:
        return
    in_progress = True

    uid = callback.from_user.id

    await save_recover_undo(uid)

    cursor.execute(f'SELECT i, i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    max_score = matrix[0][1]
    current_score = matrix[0][2] + 1
    if current_score > max_score:
        max_score = current_score
    cursor.execute(f'UPDATE matrix SET i1 = {max_score}, i2 = {current_score} WHERE i = 0 AND id = {uid}')
    connect.commit()

    current_column = int(callback.data)
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
    await find_coincidences_recursively(callback, uid, matrix_list, new_meaning, current_column, current_line, undo_number)

    meaning = 2 ** randrange(1, 9)
    line = matrix[0]
    for i in range(3, 6):
        cursor.execute(f'UPDATE matrix SET i{i} = {meaning} WHERE i = 0 AND id = {uid}')
        connect.commit()
        meaning = line[i]

    text, inline_kb = await get_current_state(uid, undo_number)
    # await sleep(SLEEP_TIME)
    await callback.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=inline_kb)

    in_progress = False


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
        cursor.execute(f'UPDATE matrix SET i{i} = {2 ** randrange(1, 9)} WHERE i = 0 AND id = {uid}')
        connect.commit()
    cursor.execute(f'UPDATE matrix SET i1 = {max_score} WHERE i = 0 AND id = {uid}')
    connect.commit()

    undo_number = await get_undo(uid)
    text, inline_kb = await get_current_state(uid, undo_number)
    await message.answer(text, parse_mode="MarkdownV2", reply_markup=inline_kb)


@dp.message_handler()
async def delete_other(message: Message):
    await message.delete()


executor.start_polling(dp, skip_updates=True)
