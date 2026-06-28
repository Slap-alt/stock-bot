import discord
import finnhub
import yfinance as yf
import asyncio
import pytz
from datetime import datetime, time

# ==================== CONFIG - FILL THESE IN ====================
DISCORD_TOKEN = "MTUxOTMzNTg3MzYzOTA4ODE2OA.Ggaeyi.9hfnwMG119JjaJenSDqIeQySKQRBqEiQtF9-Po"
CHANNEL_ID = 1519335401813442792
FINNHUB_KEY = "d8tu1v9r01qinhuehgj0d8tu1v9r01qinhuehgjg"

SCAN_START = time(9, 30)
SCAN_END = time(9, 40)

MIN_PRICE = 6.0
MIN_MARKET_CAP = 150_000_000
MIN_AVG_VOLUME = 250_000

SCAN_INTERVAL = 40
MAX_DETAILED_ALERTS = 6
# ============================================================

intents = discord.Intents.default()
client = discord.Client(intents=intents)
finnhub_client = finnhub.Client(api_key=FINNHUB_KEY)
tz = pytz.timezone('US/Eastern')

leaderboard_msg_id = None
alerted = set()
detailed_count = 0

def is_in_window():
    now = datetime.now(tz).time()
    return SCAN_START <= now <= SCAN_END

def get_momentum_score(pct_change, rel_volume, above_open, above_vwap):
    score = 5.0
    if pct_change >= 4: score += 1.5
    elif pct_change >= 2.5: score += 1.0
    
    if rel_volume >= 3: score += 1.5
    elif rel_volume >= 2: score += 1.0
    
    if above_open: score += 1.0
    if above_vwap: score += 0.5
    
    return round(min(max(score, 1), 10), 1)

async def get_stock_data(ticker):
    try:
        quote = finnhub_client.quote(ticker)
        price = quote.get('c', 0)
        prev_close = quote.get('pc', 0)
        volume = quote.get('v', 0)

        if price < MIN_PRICE or prev_close <= 0:
            return None

        pct_from_prev = ((price - prev_close) / prev_close) * 100

        stock = yf.Ticker(ticker)
        info = stock.info
        mkt_cap = info.get('marketCap', 0) or 0
        avg_vol = info.get('averageVolume', 0) or 0

        if mkt_cap < MIN_MARKET_CAP or avg_vol < MIN_AVG_VOLUME:
            return None

        today = stock.history(period="1d", interval="1m")
        if today.empty:
            return None

        open_price = today['Open'].iloc[0]
        pct_from_open = ((price - open_price) / open_price) * 100 if open_price > 0 else 0

        avg_price_since_open = today['Close'].mean()
        above_vwap = price > avg_price_since_open
        above_open = price > open_price
        rel_vol = volume / (avg_vol / 390 * 10) if avg_vol > 0 else 1

        score = get_momentum_score(pct_from_prev, rel_vol, above_open, above_vwap)

        return {
            'ticker': ticker,
            'price': round(price, 2),
            'pct_from_prev': round(pct_from_prev, 2),
            'pct_from_open': round(pct_from_open, 2),
            'volume': volume,
            'score': score,
            'above_open': above_open,
            'above_vwap': above_vwap
        }
    except:
        return None

async def update_leaderboard(channel, top5):
    global leaderboard_msg_id

    embed = discord.Embed(
        title="🚀 Opening Momentum Scanner (9:30–9:40 ET)",
        description="Strong volume + momentum right after the open",
        color=0x00ff9f
    )

    for i, s in enumerate(top5, 1):
        status = ""
        if s['above_open'] and s['above_vwap']:
            status = "✅ Holding Open + Above VWAP"
        elif s['above_open']:
            status = "↗️ Above Open"
        else:
            status = "⚠️ Below Open"

        embed.add_field(
            name=f"{i}. {s['ticker']}  |  Score: {s['score']}/10",
            value=f"**{s['pct_from_prev']}%** from prev close | **{s['pct_from_open']}%** from open\nVol: {s['volume']:,} | {status}",
            inline=False
        )

    embed.set_footer(text="Momentum + Volume Focus • Not financial advice")

    if leaderboard_msg_id:
        try:
            msg = await channel.fetch_message(leaderboard_msg_id)
            await msg.edit(embed=embed)
        except:
            pass
    else:
        msg = await channel.send(embed=embed)
        leaderboard_msg_id = msg.id

@client.event
async def on_ready():
    print("Bot online - Scanning 9:30-9:40 AM ET")
    channel = client.get_channel(CHANNEL_ID)

    while True:
        if is_in_window():
            candidates = []
            for t in ["AAPL", "TSLA", "NVDA", "AMD", "SMCI", "PLTR", "SOFI", "LCID", "F", "INTC"]:
                data = await get_stock_data(t)
                if data and data['pct_from_prev'] > 1.8:
                    candidates.append(data)

            candidates.sort(key=lambda x: x['score'], reverse=True)
            top5 = candidates[:5]

            if top5:
                await update_leaderboard(channel, top5)

            await asyncio.sleep(SCAN_INTERVAL)
        else:
            await asyncio.sleep(300)

client.run(DISCORD_TOKEN)