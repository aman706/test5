
import asyncio
import os
import codecs
from datetime import datetime
from random import shuffle
from random import randint
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pykeyboard import InlineKeyboard
from pyrogram import filters
from pyrogram.errors.exceptions.bad_request_400 import (ChatAdminRequired,
                                                        UserNotParticipant)
from pyrogram.types import (ChatPermissions, InlineKeyboardButton,
                            InlineKeyboardMarkup, Message, User)

from MashaRoBot import pbot as app
from MashaRoBot.pyrogramee.errors import capture_err
from wbb.utils.dbfunctions import (captcha_off, captcha_on, del_welcome,
                                   get_captcha_cache, get_welcome,
                                   is_captcha_on, is_gbanned_user, set_welcome,
                                   update_captcha_cache)



from functools import wraps
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden


async def member_permissions(chat_id: int, user_id: int):
    perms = []
    member = await app.get_chat_member(chat_id, user_id)
    if member.can_post_messages:
        perms.append("can_post_messages")
    if member.can_edit_messages:
        perms.append("can_edit_messages")
    if member.can_delete_messages:
        perms.append("can_delete_messages")
    if member.can_restrict_members:
        perms.append("can_restrict_members")
    if member.can_promote_members:
        perms.append("can_promote_members")
    if member.can_change_info:
        perms.append("can_change_info")
    if member.can_invite_users:
        perms.append("can_invite_users")
    if member.can_pin_messages:
        perms.append("can_pin_messages")
    if member.can_manage_voice_chats:
        perms.append("can_manage_voice_chats")
    return perms


async def authorised(func, subFunc2, client, message, *args, **kwargs):
    chatID = message.chat.id
    try:
        await func(client, message, *args, **kwargs)
    except ChatWriteForbidden:
        await app.leave_chat(chatID)
    except Exception as e:
        try:
            await message.reply_text(str(e))
        except ChatWriteForbidden:
            await app.leave_chat(chatID)
    return subFunc2


async def unauthorised(message: Message, permission, subFunc2):
    chatID = message.chat.id
    text = (
        "You don't have the required permission to perform this action."
        + f"\n**Permission:** __{permission}__"
    )
    try:
        await message.reply_text(text)
    except ChatWriteForbidden:
        await app.leave_chat(chatID)
    return subFunc2


def adminsOnly(permission):
    def subFunc(func):
        @wraps(func)
        async def subFunc2(client, message: Message, *args, **kwargs):
            chatID = message.chat.id
            if not message.from_user:
                # For anonymous admins
                if message.sender_chat:
                    return await authorised(
                        func, subFunc2, client, message, *args, **kwargs
                    )
                return await unauthorised(message, permission, subFunc2)
            # For admins and sudo users
            userID = message.from_user.id
            permissions = await member_permissions(chatID, userID)
            if userID not in SUDOERS and permission not in permissions:
                return await unauthorised(message, permission, subFunc2)
            return await authorised(
                func, subFunc2, client, message, *args, **kwargs
            )

        return subFunc2

    return subFunc




def generate_captcha():
    # Generate one letter
    def gen_letter():
        return chr(randint(65, 90))

    def rndColor():
        return (randint(64, 255), randint(64, 255), randint(64, 255))

    def rndColor2():
        return (randint(32, 127), randint(32, 127), randint(32, 127))

    # Generate a 4 letter word
    def gen_wrong_answer():
        word = ""
        for _ in range(4):
            word += gen_letter()
        return word

    # Generate 8 wrong captcha answers
    wrong_answers = []
    for _ in range(8):
        wrong_answers.append(gen_wrong_answer())

    width = 80 * 4
    height = 100
    correct_answer = ""
    font = ImageFont.truetype("MashaRoBot/resources/arial.ttf", 55)
    file = f"assets/{randint(1000, 9999)}.jpg"
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Draw random points on image
    for x in range(width):
        for y in range(height):
            draw.point((x, y), fill=rndColor())

    for t in range(4):
        letter = gen_letter()
        correct_answer += letter
        draw.text((60 * t + 50, 15), letter, font=font, fill=rndColor2())
    image = image.filter(ImageFilter.BLUR)
    image.save(file, "jpeg")
    return [file, correct_answer, wrong_answers]




WELCOME_DELAY_KICK_SEC = 300
SUDOERS = 1513257955

welcome_captcha_group = 6

answers_dicc = []
loop = asyncio.get_running_loop()


async def get_initial_captcha_cache():
    global answers_dicc
    answers_dicc = await get_captcha_cache()
    return answers_dicc


loop.create_task(get_initial_captcha_cache())


@app.on_message(filters.new_chat_members, group=welcome_captcha_group)
@capture_err
async def welcome(_, message: Message):
    global answers_dicc
    """ Get cached answers from mongodb in case of bot's been restarted or crashed. """
    answers_dicc = await get_captcha_cache()
    """Mute new member and send message with button"""
    if not await is_captcha_on(message.chat.id):
        return
    for member in message.new_chat_members:
        try:
            if member.id in SUDOERS:
                continue  # ignore sudos
            if await is_gbanned_user(member.id):
                await message.chat.kick_member(member.id)
                await message.reply_text(
                    f"{member.mention} was globally banned, and got removed,"
                    + " if you think this is a false gban, you can appeal"
                    + " for this ban in support chat."
                )
                continue
            if member.is_bot:
                continue  # ignore bots
            await message.chat.restrict_member(member.id, ChatPermissions())
            text = (
                f"{(member.mention())} Are you human?\n"
                f"Solve this captcha in {WELCOME_DELAY_KICK_SEC} seconds and 4 attempts or you'll be kicked."
            )
        except ChatAdminRequired:
            return
        # Generate a captcha image, answers and some wrong answers
        captcha = generate_captcha()
        captcha_image = captcha[0]
        captcha_answer = captcha[1]
        wrong_answers = captcha[2]  # This consists of 8 wrong answers
        correct_button = InlineKeyboardButton(
            f"{captcha_answer}",
            callback_data=f"pressed_button {captcha_answer} {member.id}",
        )
        temp_keyboard_1 = [correct_button]  # Button row 1
        temp_keyboard_2 = []  # Botton row 2
        temp_keyboard_3 = []
        for i in range(2):
            temp_keyboard_1.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
                )
            )
        for i in range(2, 5):
            temp_keyboard_2.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
                )
            )
        for i in range(5, 8):
            temp_keyboard_3.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
                )
            )

        shuffle(temp_keyboard_1)
        keyboard = [temp_keyboard_1, temp_keyboard_2, temp_keyboard_3]
        shuffle(keyboard)
        verification_data = {
            "chat_id": message.chat.id,
            "user_id": member.id,
            "answer": captcha_answer,
            "keyboard": keyboard,
            "attempts": 0,
        }
        keyboard = InlineKeyboardMarkup(keyboard)
        # Append user info, correct answer and
        answers_dicc.append(verification_data)
        # keyboard for later use with callback query
        button_message = await message.reply_photo(
            photo=captcha_image,
            caption=text,
            reply_markup=keyboard,
            quote=True,
        )
        os.remove(captcha_image)
        """ Save captcha answers etc in mongodb in case bot gets crashed or restarted. """
        await update_captcha_cache(answers_dicc)
        asyncio.create_task(
            kick_restricted_after_delay(
                WELCOME_DELAY_KICK_SEC, button_message, member
            )
        )
        await asyncio.sleep(0.5)


async def send_welcome_message(callback_query, pending_user_id):
    try:
        raw_text = await get_welcome(callback_query.message.chat.id)
    except TypeError:
        return
    raw_text = raw_text.strip().replace("`", "")
    if not raw_text:
        return
    text = raw_text.split("~")[0].strip()
    buttons_text_list = raw_text.split("~")[1].strip().splitlines()
    if "{chat}" in text:
        text = text.replace("{chat}", callback_query.message.chat.title)
    if "{name}" in text:
        text = text.replace(
            "{name}", (await app.get_users(pending_user_id)).mention
        )
    buttons = InlineKeyboard(row_width=2)
    list_of_buttons = []
    for button_string in buttons_text_list:
        button_string = button_string.strip().split("=")[1].strip()
        button_string = button_string.replace("[", "").strip()
        button_string = button_string.replace("]", "").strip()
        button_string = button_string.split(",")
        button_text = button_string[0].strip()
        button_url = button_string[1].strip()
        list_of_buttons.append(
            InlineKeyboardButton(text=button_text, url=button_url)
        )
    buttons.add(*list_of_buttons)
    await app.send_message(
        callback_query.message.chat.id,
        text=text,
        reply_markup=buttons,
        disable_web_page_preview=True,
    )


@app.on_callback_query(filters.regex("pressed_button"))
async def callback_query_welcome_button(_, callback_query):
    """After the new member presses the correct button,
    set his permissions to chat permissions,
    delete button message and join message.
    """
    global answers_dicc
    data = callback_query.data
    pressed_user_id = callback_query.from_user.id
    pending_user_id = int(data.split(None, 2)[2])
    button_message = callback_query.message
    answer = data.split(None, 2)[1]
    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if (
                i["user_id"] == pending_user_id
                and i["chat_id"] == button_message.chat.id
            ):
                correct_answer = i["answer"]
                keyboard = i["keyboard"]
    if pending_user_id == pressed_user_id:
        if answer != correct_answer:
            await callback_query.answer("Yeah, It's Wrong.")
            for iii in answers_dicc:
                if (
                    iii["user_id"] == pending_user_id
                    and iii["chat_id"] == button_message.chat.id
                ):
                    attempts = iii["attempts"]
                    if attempts >= 3:
                        answers_dicc.remove(iii)
                        await button_message.chat.kick_member(pending_user_id)
                        await asyncio.sleep(1)
                        await button_message.chat.unban_member(pending_user_id)
                        await button_message.delete()
                        await update_captcha_cache(answers_dicc)
                        return
                    else:
                        iii["attempts"] += 1
                        break
            shuffle(keyboard[0])
            shuffle(keyboard[1])
            shuffle(keyboard[2])
            shuffle(keyboard)
            keyboard = InlineKeyboardMarkup(keyboard)
            await button_message.edit(
                text=button_message.caption.markdown, reply_markup=keyboard
            )
            return
        await callback_query.answer("Captcha passed successfully!")
        await button_message.chat.unban_member(pending_user_id)
        await button_message.delete()
        if len(answers_dicc) != 0:
            for ii in answers_dicc:
                if (
                    ii["user_id"] == pending_user_id
                    and ii["chat_id"] == button_message.chat.id
                ):
                    answers_dicc.remove(ii)
                    await update_captcha_cache(answers_dicc)
        """ send welcome message """
        await send_welcome_message(callback_query, pending_user_id)
        return
    else:
        await callback_query.answer("This is not for you")
        return


async def kick_restricted_after_delay(
    delay, button_message: Message, user: User
):
    """If the new member is still restricted after the delay, delete
    button message and join message and then kick him
    """
    global answers_dicc
    await asyncio.sleep(delay)
    join_message = button_message.reply_to_message
    group_chat = button_message.chat
    user_id = user.id
    await join_message.delete()
    await button_message.delete()
    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if i["user_id"] == user_id:
                answers_dicc.remove(i)
                await update_captcha_cache(answers_dicc)
    await _ban_restricted_user_until_date(group_chat, user_id, duration=delay)


async def _ban_restricted_user_until_date(
    group_chat, user_id: int, duration: int
):
    try:
        member = await group_chat.get_member(user_id)
        if member.status == "restricted":
            until_date = int(datetime.utcnow().timestamp() + duration)
            await group_chat.kick_member(user_id, until_date=until_date)
    except UserNotParticipant:
        pass


@app.on_message(filters.command("captcha") & ~filters.private)
@adminsOnly("can_restrict_members")
async def captcha_state(_, message):
    usage = "**Usage:**\n/captcha [ENABLE|DISABLE]"
    if len(message.command) != 2:
        await message.reply_text(usage)
        return
    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await captcha_on(chat_id)
        await message.reply_text("Enabled Captcha For New Users.")
    elif state == "disable":
        await captcha_off(chat_id)
        await message.reply_text("Disabled Captcha For New Users.")
    else:
        await message.reply_text(usage)
