"""
Telegram Chat Listener for Bingo365 Monitoring
Polls getUpdates API and stores messages in SQLite.

Usage:
    python chat_listener.py              # Run polling loop (blocking)
    python chat_listener.py --test       # Test connection and exit
    python chat_listener.py --stats      # Show DB stats and exit
"""
import os
import sys
import time
import sqlite3
import argparse
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    CHAT_LISTENER_BOT_TOKEN,
    CHAT_LISTENER_CHAT_ID,
    CHAT_LISTENER_DB,
    CHAT_LISTENER_POLL_INTERVAL,
)

PH_TZ = timezone(timedelta(hours=8))
API_BASE = f"https://api.telegram.org/bot{CHAT_LISTENER_BOT_TOKEN}"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CHAT_LISTENER_DB)


def init_db():
    """Create SQLite tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            date INTEGER NOT NULL,
            date_ph TEXT NOT NULL,
            text TEXT,
            message_type TEXT DEFAULT 'text',
            reply_to_message_id INTEGER,
            raw_json TEXT,
            UNIQUE(message_id, chat_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_date_ph ON messages(date_ph)")
    conn.commit()
    conn.close()
    print(f"[OK] Database initialized: {DB_PATH}")


def get_last_offset():
    """Get the last processed update offset from metadata."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM metadata WHERE key = 'last_offset'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def set_last_offset(offset):
    """Save the last processed update offset."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_offset', ?)",
        (str(offset),)
    )
    conn.commit()
    conn.close()


def determine_message_type(msg):
    """Determine the type of message."""
    if 'text' in msg:
        return 'text'
    elif 'photo' in msg:
        return 'photo'
    elif 'document' in msg:
        return 'document'
    elif 'sticker' in msg:
        return 'sticker'
    elif 'video' in msg:
        return 'video'
    elif 'voice' in msg:
        return 'voice'
    elif 'audio' in msg:
        return 'audio'
    elif 'animation' in msg:
        return 'animation'
    elif 'new_chat_members' in msg:
        return 'new_member'
    elif 'left_chat_member' in msg:
        return 'left_member'
    elif 'pinned_message' in msg:
        return 'pinned'
    else:
        return 'other'


def extract_text(msg):
    """Extract text content from a message."""
    if 'text' in msg:
        return msg['text']
    elif 'caption' in msg:
        return msg['caption']
    elif 'new_chat_members' in msg:
        names = [m.get('first_name', 'Unknown') for m in msg['new_chat_members']]
        return f"[Joined: {', '.join(names)}]"
    elif 'left_chat_member' in msg:
        name = msg['left_chat_member'].get('first_name', 'Unknown')
        return f"[Left: {name}]"
    elif 'pinned_message' in msg:
        return "[Pinned a message]"
    elif 'sticker' in msg:
        emoji = msg['sticker'].get('emoji', '')
        return f"[Sticker {emoji}]"
    return None


def store_message(msg):
    """Store a single message in SQLite. Returns True if new, False if duplicate."""
    import json

    message_id = msg.get('message_id')
    chat_id = msg.get('chat', {}).get('id')
    from_user = msg.get('from', {})
    user_id = from_user.get('id')
    username = from_user.get('username', '')
    first_name = from_user.get('first_name', '')
    last_name = from_user.get('last_name', '')
    date_unix = msg.get('date', 0)
    date_ph = datetime.fromtimestamp(date_unix, tz=PH_TZ).strftime('%Y-%m-%d %H:%M:%S')
    text = extract_text(msg)
    message_type = determine_message_type(msg)
    reply_to = msg.get('reply_to_message', {}).get('message_id')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO messages
            (message_id, chat_id, user_id, username, first_name, last_name,
             date, date_ph, text, message_type, reply_to_message_id, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id, chat_id, user_id, username, first_name, last_name,
            date_unix, date_ph, text, message_type, reply_to,
            json.dumps(msg, ensure_ascii=False)
        ))
        conn.commit()
        inserted = c.rowcount > 0
    except Exception as e:
        print(f"[ERROR] Failed to store message {message_id}: {e}")
        inserted = False
    finally:
        conn.close()
    return inserted


def poll_updates():
    """Poll Telegram getUpdates API and store new messages."""
    offset = get_last_offset()
    params = {
        'offset': offset + 1 if offset else 0,
        'timeout': 30,
        'allowed_updates': ['message'],
    }

    try:
        resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=35)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return 0
    except Exception as e:
        print(f"[ERROR] getUpdates failed: {e}")
        return 0

    if not data.get('ok'):
        print(f"[ERROR] API returned error: {data}")
        return 0

    results = data.get('result', [])
    new_count = 0

    for update in results:
        update_id = update.get('update_id', 0)
        msg = update.get('message')

        if msg:
            if store_message(msg):
                new_count += 1
                user = msg.get('from', {})
                name = user.get('first_name', 'Unknown')
                text = extract_text(msg) or ''
                preview = text[:60] + '...' if len(text) > 60 else text
                msg_type = determine_message_type(msg)
                print(f"  [{msg_type}] {name}: {preview}")

        if update_id > offset:
            offset = update_id

    if results:
        set_last_offset(offset)

    return new_count


def test_connection():
    """Test bot connection and print bot info."""
    print("Testing bot connection...")
    try:
        resp = requests.get(f"{API_BASE}/getMe", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('ok'):
            bot = data['result']
            print(f"[OK] Bot: @{bot.get('username')} ({bot.get('first_name')})")
            print(f"     ID: {bot.get('id')}")
            print(f"     Can join groups: {bot.get('can_join_groups')}")
            print(f"     Can read group messages: {bot.get('can_read_all_group_messages')}")
        else:
            print(f"[ERROR] {data}")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")


def show_stats():
    """Show database statistics."""
    if not os.path.exists(DB_PATH):
        print("No database found. Run the listener first.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM messages")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
    users = c.fetchone()[0]

    c.execute("SELECT MIN(date_ph), MAX(date_ph) FROM messages")
    date_range = c.fetchone()

    c.execute("""
        SELECT COALESCE(first_name, username, 'Unknown') as name, COUNT(*) as cnt
        FROM messages GROUP BY user_id ORDER BY cnt DESC LIMIT 10
    """)
    top_users = c.fetchall()

    c.execute("""
        SELECT message_type, COUNT(*) as cnt
        FROM messages GROUP BY message_type ORDER BY cnt DESC
    """)
    types = c.fetchall()

    conn.close()

    print(f"\n{'='*50}")
    print(f"  Chat Listener Database Stats")
    print(f"{'='*50}")
    print(f"  Total messages: {total:,}")
    print(f"  Unique users:   {users}")
    print(f"  Date range:     {date_range[0] or 'N/A'} - {date_range[1] or 'N/A'}")
    print(f"\n  Top users:")
    for name, cnt in top_users:
        print(f"    {name}: {cnt:,}")
    print(f"\n  Message types:")
    for mtype, cnt in types:
        print(f"    {mtype}: {cnt:,}")
    print(f"{'='*50}\n")


def get_agent_reporting_scores():
    """Get reporting accuracy scores per agent from chat data.

    Returns dict: {agent_name: {'score': int, 'avg_minute': float, 'report_count': int}}
    Used by KPI Monitoring page to auto-fill the 'reporting' KPI.
    """
    from config import TELEGRAM_MENTIONS, REPORT_KEYWORDS, REPORTING_ACCURACY_SCORING

    if not os.path.exists(DB_PATH):
        return {}

    # Reverse mapping: username -> agent name
    username_to_agent = {v.lower(): k.title() for k, v in TELEGRAM_MENTIONS.items()}
    agent_usernames = list(username_to_agent.keys())

    if not agent_usernames:
        return {}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    placeholders = ','.join(['?' for _ in agent_usernames])
    c.execute(f"""
        SELECT LOWER(username) as username, text, date_ph
        FROM messages
        WHERE LOWER(username) IN ({placeholders})
        AND text IS NOT NULL
        ORDER BY date ASC
    """, agent_usernames)

    rows = c.fetchall()
    conn.close()

    # Group report messages by agent
    agent_minutes = {}
    for username, text, date_ph in rows:
        text_lower = text.lower()
        if not any(kw in text_lower for kw in REPORT_KEYWORDS):
            continue

        agent = username_to_agent.get(username)
        if not agent:
            continue

        try:
            minute = int(date_ph[14:16])
        except (ValueError, IndexError):
            continue

        if agent not in agent_minutes:
            agent_minutes[agent] = []
        agent_minutes[agent].append(minute)

    # Calculate scores
    results = {}
    for agent, minutes in agent_minutes.items():
        avg_min = sum(minutes) / len(minutes)
        # Score based on average minute
        score = 1
        for s, low, high in REPORTING_ACCURACY_SCORING:
            if low <= avg_min <= high:
                score = s
                break
        results[agent] = {
            'score': score,
            'avg_minute': round(avg_min, 1),
            'report_count': len(minutes),
        }

    return results


def run_listener():
    """Main polling loop."""
    print(f"\n{'='*50}")
    print(f"  Telegram Chat Listener")
    print(f"  Bot: @chatdetector_juan365_bot")
    print(f"  Chat ID: {CHAT_LISTENER_CHAT_ID}")
    print(f"  Poll interval: {CHAT_LISTENER_POLL_INTERVAL}s")
    print(f"  Database: {DB_PATH}")
    print(f"{'='*50}\n")

    init_db()
    test_connection()

    print(f"\n[START] Listening for messages... (Ctrl+C to stop)\n")

    try:
        while True:
            new = poll_updates()
            if new > 0:
                print(f"[+] Stored {new} new message(s)")
            time.sleep(CHAT_LISTENER_POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[STOP] Listener stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Chat Listener")
    parser.add_argument('--test', action='store_true', help='Test bot connection')
    parser.add_argument('--stats', action='store_true', help='Show database stats')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.stats:
        show_stats()
    else:
        run_listener()
