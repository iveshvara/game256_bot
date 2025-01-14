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
MAX_NUMBER = 1024
MAX_NUMBER_STEP = 10

in_progress = [False, '']
process_icon = ''
mood = 0
zero_buns_are_active = False
zero_buns_meaning = 0


@dp.callback_query_handler(lambda x: x.data and x.data.startswith('column '))
async def callback_query_handler(callback: CallbackQuery):
    global in_progress, zero_buns_are_active, zero_buns_meaning
    uid = callback.from_user.id

    if in_progress[0] and in_progress[1] == uid:
        await callback.answer()
        return
    in_progress[0], in_progress[1] = True, uid

    await save_recover_undo(uid)

    if zero_buns_are_active:
        zero_buns_are_active = False
        cursor.execute(f'UPDATE matrix SET i5 = {zero_buns_meaning} WHERE i = 0 AND id = {uid}')
        connect.commit()

    cursor.execute(f'SELECT i, i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    # max_score = matrix[0][1]
    # current_score = matrix[0][2] + 1
    # cursor.execute(f'UPDATE matrix SET i1 = {max_score}, i2 = {current_score} WHERE i = 0 AND id = {uid}')
    # connect.commit()

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

    if new_meaning > 0 and current_line == 0:
        if new_meaning == current_meaning:
            current_line = 1
            new_meaning *= 2
            if new_meaning > MAX_NUMBER:
                new_meaning = 0
                cursor.execute(f'UPDATE matrix SET i{current_column} = 0 WHERE i = 1 AND id = {uid}')
                connect.commit()
        else:
            await callback.answer()
            in_progress[0], in_progress[1] = False, ''
            return

    cursor.execute(f'UPDATE matrix SET i5 = 0 WHERE i = 0 AND id = {uid}')
    connect.commit()

    matrix_list = list()
    for line in matrix:
        matrix_list.append(list(line))

    undo_number = await get_undo(uid)
    text, inline_kb = await find_coincidences_recursively(callback, uid, matrix_list, new_meaning, current_column,
                                                          current_line, undo_number)

    meaning = await generate_meaning(True)
    line = matrix[0]
    for i in range(3, 6):
        cursor.execute(f'UPDATE matrix SET i{i} = {meaning} WHERE i = 0 AND id = {uid}')
        connect.commit()
        meaning = line[i]

    in_progress[0], in_progress[1] = False, ''
    await send_message(callback, uid, undo_number, text, inline_kb, False)
    await callback.answer()


@dp.callback_query_handler(lambda x: x.data and x.data.startswith('next '))
async def undo(callback: CallbackQuery):
    if not zero_buns_are_active:
        await callback.answer()
        return

    global zero_buns_meaning

    uid = callback.from_user.id

    i = callback.data.replace('next ', '')
    # cursor.execute(f'SELECT i5 FROM matrix WHERE i = 0 AND id = {uid}')
    # old_meaning = cursor.fetchone()[0]
    if zero_buns_meaning == 0:
        zero_buns_meaning = await generate_meaning()
    old_meaning = zero_buns_meaning
    new_meaning = 0

    if i == '5':
        new_meaning = old_meaning
        while new_meaning == old_meaning:
            new_meaning = await generate_meaning()
    elif i == '4':
        if old_meaning == MAX_NUMBER:
            new_meaning = 2
        else:
            new_meaning = int(old_meaning * 2)
    elif i == '3':
        if old_meaning == 2:
            new_meaning = MAX_NUMBER
        else:
            new_meaning = int(old_meaning / 2)

    # cursor.execute(f'UPDATE matrix SET i5 = {new_meaning} WHERE i = 0 AND id = {uid}')
    # connect.commit()
    zero_buns_meaning = new_meaning

    undo_number = await get_undo(uid)
    await send_message(callback, uid, undo_number, '', '', False)
    await callback.answer()


@dp.callback_query_handler(text='undo')
async def undo(callback: CallbackQuery):
    global in_progress, zero_buns_are_active, zero_buns_meaning

    in_progress[0], in_progress[1] = False, ''
    zero_buns_are_active = False
    zero_buns_meaning = 0

    uid = callback.from_user.id

    undo_number = await get_undo(uid)

    if undo_number == '00':
        await callback.answer()
        return

    await save_recover_undo(uid, save=False)

    undo_number = await get_undo(uid)
    await send_message(callback, uid, undo_number, '', '', False)
    await callback.answer()


async def generate_meaning(use_buns=False):
    maximum_limit = (25 - mood) ** 3 + 25
    minimum_limit = -mood
    its_bun = randrange(minimum_limit, maximum_limit, 1)
    if its_bun > 0:
        meaning = 2 ** randrange(1, MAX_NUMBER_STEP, 1)
    else:
        minimum_limit_buns = mood // 5 * -1
        meaning = randrange(minimum_limit_buns, 1, 1)
        # print(f'minimum_limit_buns: {minimum_limit_buns}')
    # print(f'minimum_limit: {minimum_limit}, maximum_limit: {maximum_limit}, its_bun: {its_bun}, meaning: {meaning}, mood: {mood}')
    return meaning


async def get_current_state(uid, undo_number, last_text='', last_inline_kb=''):
    global process_icon, in_progress, mood, zero_buns_are_active, zero_buns_meaning
    mood = 0

    cursor.execute(f'SELECT i, i1, i2, i3, i4, i5 FROM matrix WHERE id = {uid}')
    matrix = cursor.fetchall()

    inline_kb = InlineKeyboardMarkup(row_width=1)
    massive = []
    massive_line = []
    massive_next = []
    current_score = 0
    max_score = 0

    for line in matrix:
        if line[0] == 0:
            count = -1
            for i in line:
                count += 1
                if count == 0:
                    continue
                elif count == 1:
                    max_score = '🏆 ' + locale.format_string('%d', i, grouping=True) + ' '
                elif count == 2:
                    current_score = '🏅 ' + locale.format_string('%d', i, grouping=True) + ' '
                elif count == len(line) - 1:
                    if in_progress[0] and in_progress[1] == uid:
                        if len(process_icon) == 6:
                            process_icon = ''
                        process_icon += '.'
                        text_button = process_icon
                    else:
                        if zero_buns_are_active or i == 0:
                            zero_buns_are_active = True
                            if zero_buns_meaning == 0:
                                zero_buns_meaning = await generate_meaning()
                            text_button = zero_buns_meaning
                            massive_next.clear()
                            massive_next.append(InlineKeyboardButton(text='➖', callback_data='next 3'))
                            massive_next.append(InlineKeyboardButton(text='➕', callback_data='next 4'))
                        else:
                            process_icon = ''
                            text_button = await get_icon(i)
                    massive_next.append(InlineKeyboardButton(text=text_button, callback_data='next ' + str(count)))
                elif not zero_buns_are_active:
                    massive_next.append(InlineKeyboardButton(text=await get_icon(i), callback_data='next ' + str(count)))
        else:
            column = -1
            for i in line:
                column += 1
                if column == 0:
                    continue
                if i == 0:
                    meaning = ' '
                else:
                    meaning = await get_icon(i)
                    mood += 1
                massive_line.append(InlineKeyboardButton(text=meaning, callback_data='column ' + str(line[0]) + ' ' + str(column)))
            massive.append(massive_line)
            massive_line = []

    inline_kb.row(InlineKeyboardButton(text='undo ' + str(undo_number), callback_data='undo'), *massive_next)
    for massive_line in massive:
        inline_kb.row(*massive_line)

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
        mood_icon = '😳'
    elif mood < 22:
        mood_icon = '😬'
    elif mood < 23:
        mood_icon = '🤯'
    elif mood < 24:
        mood_icon = '😰'
    elif mood < 25:
        mood_icon = '😱'
    else:
        mood_icon = '😵'

    # f'{text:<33}'
    mode = ''
    if zero_buns_are_active:
        mode = ': ' + await get_icon(0)
    text = '`' + max_score + current_score + '   ' + mood_icon + mode + '`'

    # changes = last_text != text or last_inline_kb != inline_kb
    changes = True

    return text, inline_kb, changes


async def get_icon(meaning):
    if meaning == 0:
        result = '🎛'
    elif meaning == -1:
        result = '✖️'
    elif meaning == -2:
        result = '🎱'
    elif meaning == -3:
        result = '🧨'
    elif meaning == -4:
        result = '🎳'
    elif meaning == -5:
        result = '🪓' 
    else:
        result = str(meaning)

    return result


async def find_coincidences_recursively(callback, uid, matrix, meaning, column, line, undo_number):
    text, inline_kb = '', ''

    if meaning == 0:
        return text, inline_kb

    plucking_zero = []
    new_line = line

    if meaning > 0:

        if matrix[line][column] != meaning:
            matrix[line][column] = meaning
            cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {line} AND id = {uid}')
            connect.commit()
            await send_message(callback, uid, undo_number, text, inline_kb, False)

        found = 0

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
            if line != 1 and matrix[line - 1][column] != 0:
                plucking_zero.append([line, column])
            
        if line != 1 and matrix[line - 1][column] != 0 and matrix[line - 1][column] == meaning:
            found += 1
            matrix[line - 1][column] = 0
            plucking_zero.append([line - 1, column])
            cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = {line - 1} AND id = {uid}')
            connect.commit()
            new_line = line
            if line != 1 and matrix[line-1][column] != 0:
                plucking_zero.append([line, column])

        if found > 0:
            for _ in range(found):
                meaning *= 2
                matrix[0][2] += 1

            if meaning > MAX_NUMBER:
                meaning = 0
                plucking_zero.append([new_line, column])
                matrix[0][2] += 1

            matrix[new_line][column] = meaning

            cursor.execute(f'UPDATE matrix SET i{column} = {meaning} WHERE i = {new_line} AND id = {uid}')
            connect.commit()

            cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
            connect.commit()

            await send_message(callback, uid, undo_number, text, inline_kb)

            text, inline_kb = await find_coincidences_recursively(callback, uid, matrix, meaning, column, new_line, undo_number)
            
    else:  # buns mode

        selected_line = int(callback.data[-3])
        if selected_line == 0:
            pass
        elif meaning == -1:
            desired_value = matrix[selected_line][column]
            for i in range(5, 0, -1):
                for ii in range(1, 6):
                    if matrix[i][ii] == desired_value:
                        new_meaning = desired_value * 2
                        matrix[0][2] += 1
                        if new_meaning > MAX_NUMBER:
                            new_meaning = 0
                            plucking_zero.append([i, ii])
                            matrix[0][2] += 1
                        matrix[i][ii] = new_meaning
                        cursor.execute(f'UPDATE matrix SET i{ii} = {new_meaning} WHERE i = {i} AND id = {uid}')
                        connect.commit()

                        cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
                        connect.commit()

                        await send_message(callback, uid, undo_number, text, inline_kb)

                        text, inline_kb = await find_coincidences_recursively(callback, uid, matrix, new_meaning, ii, i, undo_number)

        elif meaning == -2:
            desired_value = matrix[selected_line][column]
            for i in range(5, 0, -1):
                for ii in range(1, 6):
                    if matrix[i][ii] == desired_value:
                        plucking_zero.append([i, ii])
                        matrix[i][ii] = 0
                        cursor.execute(f'UPDATE matrix SET i{ii} = 0 WHERE i = {i} AND id = {uid}')
                        connect.commit()
                        matrix[0][2] += 1

            cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
            connect.commit()

        elif meaning == -3:
            for i in range(-1, 2):
                for ii in range(-1, 2):
                    current_line = selected_line + i
                    current_column = column + ii
                    if 0 < current_line < 6 and 0 < current_column < 6:
                        matrix[current_line][current_column] = 0
                        plucking_zero.append([selected_line + i, current_column])
                        cursor.execute(f'UPDATE matrix SET i{current_column} = 0 WHERE i = {current_line} AND id = {uid}')
                        connect.commit()
                        matrix[0][2] += 1

            cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
            connect.commit()
                        
        elif meaning == -4:
            selected_line = int(callback.data[-3])
            if selected_line > 0:
                for i in range(1, 6):
                    matrix[selected_line][i] = 0
                    plucking_zero.append([selected_line, i])
                    matrix[0][2] += 1

                cursor.execute(f'UPDATE matrix SET i1 = 0, i2 = 0, i3 = 0, i4 = 0, i5 = 0 WHERE i = {selected_line} AND id = {uid}')
                connect.commit()

                cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
                connect.commit()
            
        elif meaning == -5:
            for i in range(1, 6):
                matrix[i][column] = 0
                plucking_zero.append([i, column])
                cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = {i} AND id = {uid}')
                connect.commit()
                matrix[0][2] += 1

            cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
            connect.commit()
                
    for point in plucking_zero:
        column = point[1]
        new_line = point[0]
        for i in range(point[0] + 1, 6):
            if matrix[i][column] == 0:
                new_line = i

        values = False
        for i in range(new_line, 0, -1):
            if matrix[i][column] != 0:
                values = True
                break

        if values:
            while matrix[new_line][column] == 0:
                for i in range(new_line, 1, -1):
                    matrix[i][column] = matrix[i - 1][column]
                    cursor.execute(f'UPDATE matrix SET i{column} = {matrix[i][column]} WHERE i = {i} AND id = {uid}')
                    connect.commit()
                    matrix[0][2] += 1

                if matrix[1][column] != 0:
                    matrix[1][column] = 0
                    cursor.execute(f'UPDATE matrix SET i{column} = 0 WHERE i = 1 AND id = {uid}')
                    connect.commit()
                    matrix[0][2] += 1

                cursor.execute(f'UPDATE matrix SET i2 = {matrix[0][2]} WHERE i = 0 AND id = {uid}')
                connect.commit()

                await send_message(callback, uid, undo_number, text, inline_kb)

            for i in range(new_line, 1, -1):
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
    cursor.execute(f'SELECT i2_1, i2_2, i2_3, i2_4, i2_5, i2_6, i2_7, i2_8, i2_9, i2_10 FROM matrix WHERE i = 0 AND id = {uid}')
    result = cursor.fetchall()[0]

    undo_number = 0
    for i in result:
        if i != 0:
            undo_number += 1

    if undo_number == 10:
        undo_number = str(undo_number)
    else:
        undo_number = '0' + str(undo_number)

    return undo_number


@dp.message_handler(commands=['start'])
async def command_start(message: Message):
    global in_progress, zero_buns_are_active, zero_buns_meaning

    in_progress[0], in_progress[1] = False, ''
    zero_buns_are_active = False
    zero_buns_meaning = 0

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
        meaning = await generate_meaning()
        cursor.execute(f'UPDATE matrix SET i{i} = {meaning} WHERE i = 0 AND id = {uid}')
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
