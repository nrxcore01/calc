import os
import asyncio
import asyncpg
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
)
from aiogram.filters import Command
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- DATABASE ---------- #

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            group_id TEXT,
            date TIMESTAMP,
            amount INTEGER,
            description TEXT
        )
        """)

# ---------- ADD TRANSACTION ---------- #

@dp.message(F.text.startswith("+") | F.text.startswith("-"))
async def add_transaction(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split(" ", 1)
        amount = int(parts[0])
        description = parts[1] if len(parts) > 1 else "No description"
    except:
        await message.reply("Use: +200 bank OR -100 cash")
        return

    now = datetime.now()

    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO transactions (group_id, date, amount, description)
        VALUES ($1,$2,$3,$4)
        """, str(message.chat.id), now, amount, description)

    await message.reply(
        f"✅ Transaction Recorded\n\n"
        f"📅 {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"💰 {amount}\n"
        f"📝 {description}"
    )

# ---------- TOTAL BALANCE ---------- #

@dp.message(Command("tt"))
async def total_balance(message: Message):
    async with pool.acquire() as conn:
        total = await conn.fetchval("""
        SELECT COALESCE(SUM(amount),0)
        FROM transactions WHERE group_id=$1
        """, str(message.chat.id))

    await message.reply(f"📊 Current Balance: ₹{total}")

# ---------- TOTAL + FULL LIST ---------- #

@dp.message(Command("trns"))
async def total_transactions(message: Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id,date,amount,description
        FROM transactions
        WHERE group_id=$1
        ORDER BY id DESC
        """, str(message.chat.id))

    if not rows:
        await message.reply("No transactions.")
        return

    turnover = sum(abs(r["amount"]) for r in rows)

    text = f"📈 Total Transactions: {len(rows)}\n"
    text += f"💰 Total Turnover: ₹{turnover}\n\n"

    for r in rows:
        text += f"{r['date'].strftime('%Y-%m-%d %H:%M')} | {r['amount']} | {r['description']}\n"

    await message.reply(text[:4000])

# ---------- HISTORY ---------- #

@dp.message(Command("his"))
async def history(message: Message):
    args = message.text.split()
    group_id = str(message.chat.id)

    async with pool.acquire() as conn:

        if len(args) == 1:
            today = datetime.now().date()
            rows = await conn.fetch("""
            SELECT date,amount,description
            FROM transactions
            WHERE group_id=$1 AND DATE(date)=$2
            """, group_id, today)

        elif args[1].endswith("d"):
            days = int(args[1][:-1])
            since = datetime.now() - timedelta(days=days)
            rows = await conn.fetch("""
            SELECT date,amount,description
            FROM transactions
            WHERE group_id=$1 AND date >= $2
            """, group_id, since)

        else:
            try:
                day, month = map(int, args[1].split("/"))
                year = datetime.now().year
                target = datetime(year, month, day).date()
                rows = await conn.fetch("""
                SELECT date,amount,description
                FROM transactions
                WHERE group_id=$1 AND DATE(date)=$2
                """, group_id, target)
            except:
                await message.reply("Use /his OR /his dd/mm OR /his 3d")
                return

    if not rows:
        await message.reply("No transactions found.")
        return

    text = "📜 History:\n\n"
    for r in rows:
        text += f"{r['date'].strftime('%Y-%m-%d %H:%M')} | {r['amount']} | {r['description']}\n"

    await message.reply(text[:4000])

# ---------- REMOVE ---------- #

@dp.message(Command("remove"))
async def remove_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id,amount
        FROM transactions
        WHERE group_id=$1
        ORDER BY id DESC
        LIMIT 10
        """, str(message.chat.id))

    if not rows:
        await message.reply("No transactions to remove.")
        return

    keyboard = [
        [InlineKeyboardButton(text=f"{r['id']} | {r['amount']}",
         callback_data=f"del_{r['id']}")]
        for r in rows
    ]

    await message.reply(
        "Select transaction to delete:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(F.data.startswith("del_"))
async def delete_transaction(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    txn_id = int(callback.data.split("_")[1])

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM transactions WHERE id=$1", txn_id)

    await callback.message.edit_text("❌ Transaction Deleted")
    await callback.answer()

# ---------- PDF EXPORT ---------- #

@dp.message(Command("export"))
async def export_pdf(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT date,amount,description
        FROM transactions
        WHERE group_id=$1
        ORDER BY id ASC
        """, str(message.chat.id))

    file_name = "ledger_report.pdf"
    doc = SimpleDocTemplate(file_name)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>Ledger Report</b>", styles["Title"]))
    elements.append(Spacer(1, 12))

    for r in rows:
        line = f"{r['date']} | {r['amount']} | {r['description']}"
        elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 6))

    doc.build(elements)

    await message.reply_document(FSInputFile(file_name))

# ---------- START ---------- #

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
