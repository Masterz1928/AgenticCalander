import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)
from ai import ask, resolve
from datetime import time
from zoneinfo import ZoneInfo
from brief import morning_brief
from groq import RateLimitError
from datetime import datetime, timedelta, date
from gcal import create_event
from multievent import clean_text, extract_events, preview, split_text, parse_until, create_all
from reminders import due_reminders
from settings import load as load_settings, save as save_settings, time_label



load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ Confirm", callback_data="yes"),
    InlineKeyboardButton("❌ Cancel", callback_data="no"),
]])


TZ = ZoneInfo("Asia/Kuala_Lumpur")
WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def parse_until(text):
    text = text.strip()
    today = datetime.now(TZ).date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B", "%d/%m"):
        try:
            d = datetime.strptime(text, fmt).date().replace(year=today.year)
            return d if d >= today else d.replace(year=today.year + 1)
        except ValueError:
            pass
    return None


def create_all(events, until):
    """Create every event in Google Calendar. Returns (created_count, failures)."""
    today = datetime.now(TZ).date()
    ok, failed = 0, []
    for e in events:
        try:
            if e.get("day"):
                d = today + timedelta(days=(WEEKDAYS[e["day"]] - today.weekday()) % 7)
                if until < d:
                    raise ValueError("last day is before the first class")
                rec = f"RRULE:FREQ=WEEKLY;UNTIL={until:%Y%m%d}T235959Z"
            else:
                d = date.fromisoformat(e["date"])
                rec = None
            create_event(
                e["title"],
                f"{d.isoformat()}T{e['start']}:00",
                f"{d.isoformat()}T{e['end']}:00",
                location=e.get("location"),
                recurrence=rec,
            )
            ok += 1
        except Exception as ex:
            failed.append(f"{e.get('title')}: {str(ex)[:80]}")
    return ok, failed

async def send(bot, chat_id, reply, needs_buttons):
    await bot.send_message(chat_id, reply, reply_markup=KEYBOARD if needs_buttons else None)


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: {update.effective_user.id}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    chat_id = update.effective_chat.id

    m = context.user_data.get("multi")
    if m and m["state"] == "collecting":
        m["chunks"].append(update.message.text)
        await update.message.reply_text("📥 got it, paste more or send /done")
        return

    if m and m["state"] == "awaiting_until":
        until = parse_until(update.message.text)
        if not until:
            await update.message.reply_text("Didn't get that date. Try like 20 Dec or 2026-12-20.")
            return
        await save_events(context.bot, chat_id, context, until)
        return

    if m and m["state"] == "review":
        await update.message.reply_text(
            "Tap ✅ Confirm all or ❌ Cancel on the list above (or /cancel). Editing comes next."
        )
        return

    try:
        reply, needs_buttons = await asyncio.to_thread(ask, chat_id, update.message.text)
    except RateLimitError:
        await update.message.reply_text("hit my rate limit gng, gimme a minute 😭")
        return
    await send(context.bot, chat_id, reply, needs_buttons)


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)  # remove the buttons
    chat_id = query.message.chat_id
    reply, needs_buttons = await asyncio.to_thread(resolve, chat_id, query.data == "yes")
    await send(context.bot, chat_id, reply, needs_buttons)

async def send_morning_brief(context: ContextTypes.DEFAULT_TYPE):
    text = await asyncio.to_thread(morning_brief)
    await context.bot.send_message(OWNER_ID, text)


async def brief_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    offset = int(context.args[0]) if context.args and context.args[0].lstrip("-").isdigit() else 0
    text = await asyncio.to_thread(morning_brief, offset)
    await update.message.reply_text(text)

async def multievent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.user_data["multi"] = {"state": "collecting", "chunks": []}
    await update.message.reply_text(
        "Paste the timetable or event text (text or HTML). It can be several messages. "
        "Send /done when you're finished, or /cancel to bail."
    )


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    m = context.user_data.get("multi")
    if not m or m["state"] != "collecting" or not m["chunks"]:
        await update.message.reply_text("Nothing collected yet. Start with /multievent.")
        return
    await update.message.reply_text("Reading it...")
    text = clean_text("\n".join(m["chunks"]))
    try:
        events = await asyncio.to_thread(extract_events, text)
    except RateLimitError:
        await update.message.reply_text("hit my rate limit gng, send /done again in a minute 😭")
        return
    except Exception as e:
        await update.message.reply_text(f"Couldn't read that: {str(e)[:500]}")
        return
    m["state"] = "review"
    m["draft"] = events
    parts = split_text(preview(events))
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm all", callback_data="me_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="me_cancel"),
        ]]) if last else None
        await update.message.reply_text(part, reply_markup=markup)
    await update.message.reply_text("(Edit and confirm are coming in the next chunk. Nothing is saved yet.)")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.user_data.pop("multi", None)
    await update.message.reply_text("Cancelled, nothing saved.")

async def save_events(bot, chat_id, context, until):
    m = context.user_data.pop("multi", None)
    await bot.send_message(chat_id, f"Creating {len(m['draft'])} events...")
    ok, failed = await asyncio.to_thread(create_all, m["draft"], until)
    text = f"Done ✅ created {ok} of {len(m['draft'])}."
    if failed:
        text += "\nFailed:\n" + "\n".join(failed)
    await bot.send_message(chat_id, text)

async def multi_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        return
    await query.answer()
    chat_id = query.message.chat_id
    m = context.user_data.get("multi")
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "me_cancel":
        context.user_data.pop("multi", None)
        await context.bot.send_message(chat_id, "Cancelled, nothing saved.")
        return

    if query.data == "me_confirm":
        if not m or m.get("state") != "review":
            await context.bot.send_message(chat_id, "Nothing to confirm. Start with /multievent.")
            return
        if any(e.get("day") for e in m["draft"]):
            m["state"] = "awaiting_until"
            await context.bot.send_message(chat_id, "Last day of classes? (like 20 Dec or 2026-12-20)")
        else:
            await save_events(context.bot, chat_id, context, None)

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    from ai import histories, pending
    histories.pop(update.effective_chat.id, None)
    pending.pop(update.effective_chat.id, None)
    await update.message.reply_text("Chat memory cleared 🧹")

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    text = await asyncio.to_thread(due_reminders)
    if text:
        await context.bot.send_message(OWNER_ID, text)

async def send_evening_preview(context: ContextTypes.DEFAULT_TYPE):
    text = await asyncio.to_thread(morning_brief, 1)
    await context.bot.send_message(OWNER_ID, "Tomorrow's lineup 🌙\n" + text)

CHOICES = {
    "brief": [("6:30 AM", "630"), ("7:00 AM", "700"), ("7:30 AM", "730"), ("8:00 AM", "800"), ("9:00 AM", "900")],
    "class": [("15 min", "15"), ("30 min", "30"), ("45 min", "45"), ("60 min", "60")],
    "other": [("30 min", "30"), ("60 min", "60"), ("90 min", "90"), ("2 hours", "120")],
}


def schedule_brief(application):
    for job in application.job_queue.get_jobs_by_name("morning_brief"):
        job.schedule_removal()
    s = load_settings()
    application.job_queue.run_daily(
        send_morning_brief,
        time=time(s["brief_hour"], s["brief_min"], tzinfo=ZoneInfo("Asia/Kuala_Lumpur")),
        name="morning_brief",
    )


def settings_menu():
    s = load_settings()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"☀️ Morning brief: {time_label(s['brief_hour'], s['brief_min'])}", callback_data="st_menu_brief")],
        [InlineKeyboardButton(f"🎓 Class reminder: {s['lead_class']} min before", callback_data="st_menu_class")],
        [InlineKeyboardButton(f"📌 Other reminders: {s['lead_other']} min before", callback_data="st_menu_other")],
    ])


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("Settings ⚙️", reply_markup=settings_menu())


async def settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != OWNER_ID:
        return
    await q.answer()
    parts = q.data.split("_")  # st_menu_brief | st_brief_730 | st_back

    if parts[1] == "menu":
        kind = parts[2]
        btns = [InlineKeyboardButton(l, callback_data=f"st_{kind}_{v}") for l, v in CHOICES[kind]]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="st_back")])
        await q.edit_message_text("Pick one:", reply_markup=InlineKeyboardMarkup(rows))
        return
    if parts[1] == "back":
        await q.edit_message_text("Settings ⚙️", reply_markup=settings_menu())
        return

    kind, val = parts[1], parts[2]
    s = load_settings()
    if kind == "brief":
        s["brief_hour"], s["brief_min"] = int(val[:-2]), int(val[-2:])
    elif kind == "class":
        s["lead_class"] = int(val)
    elif kind == "other":
        s["lead_other"] = int(val)
    save_settings(s)
    if kind == "brief":
        schedule_brief(context.application)
    await q.edit_message_text("Saved ✅", reply_markup=settings_menu())


app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
app.add_handler(CommandHandler("id", show_id))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("brief", brief_now))
app.add_handler(CallbackQueryHandler(handle_button, pattern="^(yes|no)$"))
app.add_handler(CallbackQueryHandler(multi_button, pattern="^me_"))
app.add_handler(CommandHandler("multievent", multievent_cmd))
app.add_handler(CommandHandler("done", done_cmd))
app.add_handler(CommandHandler("cancel", cancel_cmd))
app.add_handler(CommandHandler("reset", reset_cmd))
app.add_handler(CommandHandler("settings", settings_cmd))
app.add_handler(CallbackQueryHandler(settings_button, pattern="^st_"))
app.job_queue.run_repeating(send_reminders, interval=300, first=15)
schedule_brief(app)
app.run_polling()