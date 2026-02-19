import os
import asyncio
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
from aiogram.filters import Command
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_FILE = "data.db"

# ---------------- DATABASE ---------------- #

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            date TEXT,
            amount INTEGER,
            description TEXT
        )
        """)
        await db.commit()

# ---------------- ADD TRANSACTION ---------------- #

@dp.message(F.text.startswith("+") | F.text.startswith("-"))
async def handle_transaction(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split(" ", 1)
        amount = int(parts[0])
        description = parts[1] if len(parts) > 1 else "No description"
    except:
        await message.reply("Use: +200 bank OR -100 cash")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO transactions (group_id, date, amount, description)
        VALUES (?, ?, ?, ?)
        """, (str(message.chat.id), now, amount, description))
        await db.commit()

    await message.reply(
        f"✅ Transaction Recorded\n\n"
        f"📅 {now}\n"
        f"💰 Amount: {amount}\n"
        f"📝 Description: {description}"
    )

# ---------------- TOTAL + LIST ---------------- #

@dp.message(Command("trns"))
async def total_transactions(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT id, date, amount, description
        FROM transactions WHERE group_id=?
        ORDER BY id DESC
        """, (str(message.chat.id),))
        rows = await cursor.fetchall()

    if not rows:
        await message.reply("No transactions found.")
        return

    turnover = sum(abs(r[2]) for r in rows)

    text = f"📈 Total Transactions: {len(rows)}\n"
    text += f"💰 Total Turnover: ₹{turnover}\n\n"
    text += "📜 All Transactions:\n\n"

    for r in rows:
        text += f"{r[1]} | {r[2]} | {r[3]}\n"

    await message.reply(text[:4000])

# ---------------- REMOVE (SHOW BUTTONS) ---------------- #

@dp.message(Command("remove"))
async def remove_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT id, date, amount, description
        FROM transactions WHERE group_id=?
        ORDER BY id DESC
        """, (str(message.chat.id),))
        rows = await cursor.fetchall()

    if not rows:
        await message.reply("No transactions to remove.")
        return

    keyboard = []
    for r in rows[:10]:  # show latest 10 only
        btn_text = f"{r[0]} | {r[2]}"
        keyboard.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"del_{r[0]}"
            )
        ])

    await message.reply(
        "Select transaction to delete:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

# ---------------- DELETE CALLBACK ---------------- #

@dp.callback_query(F.data.startswith("del_"))
async def delete_transaction(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    txn_id = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM transactions WHERE id=?", (txn_id,))
        await db.commit()

    await callback.message.edit_text("❌ Transaction Deleted")
    await callback.answer()

# ---------------- PDF EXPORT ---------------- #

@dp.message(Command("export"))
async def export_pdf(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    file_name = "ledger_report.pdf"

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT date, amount, description
        FROM transactions WHERE group_id=?
        ORDER BY id ASC
        """, (str(message.chat.id),))
        rows = await cursor.fetchall()

    doc = SimpleDocTemplate(file_name)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>Ledger Report</b>", styles["Title"]))
    elements.append(Spacer(1, 12))

    for r in rows:
        line = f"{r[0]} | {r[1]} | {r[2]}"
        elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 6))

    doc.build(elements)

    await message.reply_document(FSInputFile(file_name))

# ---------------- START ---------------- #

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
