import os
import re
import json
import time
import socket
import sqlite3
import logging
import ipaddress
from datetime import datetime
from urllib.parse import urlparse
import html
import base64
from pathlib import Path

import requests
import streamlit as st
from bs4 import BeautifulSoup
from ddgs import DDGS
import youtube_transcript_api
from openai import OpenAI


# ============================================================================
# BASIC CONFIG
# ============================================================================

APP_TITLE = "Laozi's Bar"
APP_ICON = "🍶"

# Streamlit chat avatars must be an image, a single emoji, a supported
# Material icon, or None. A plain text terminal prompt such as ">" is
# interpreted as an image path and raises StreamlitAPIException.
USER_AVATAR = ":material/chevron_right:"
SHIFU_AVATAR = "🍶"

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

DB_PATH = os.getenv("SHIFU_BROWSER_DB", "shifu_browser_memory.db")
LEGACY_HISTORY_FILE = "chat_history.json"

MAX_RECENT_TURNS = 18
MAX_MEMORY_RESULTS = 8
MAX_LINK_CHARS = 7000
MAX_TOOL_RESULT_CHARS = 6000
RECENT_VISIBLE_TURNS = int(os.getenv("SHIFU_BROWSER_RECENT_VISIBLE_TURNS", "8"))

APP_DIR = Path(__file__).resolve().parent
BACKGROUND_IMAGE_PATH = Path(
    os.getenv(
        "LAOZI_BAR_BACKGROUND",
        str(APP_DIR / "laozi_terminal_bar.png"),
    )
)
SHOW_BACKGROUND_IMAGE = (
    os.getenv("LAOZI_BAR_SHOW_BACKGROUND", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)

logging.basicConfig(
    filename="shifu_browser.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("shifu-browser")


# ============================================================================
# STREAMLIT STARTUP + TERMINAL BAR THEME
# ============================================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def image_file_to_data_uri(path):
    """Return a browser-safe data URI for a local image, or an empty string."""
    try:
        path = Path(path)
        if not path.is_file():
            return ""

        suffix = path.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix, "image/png")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception as e:
        log.warning("Could not load UI background image %s: %s", path, e)
        return ""


def apply_terminal_bar_theme():
    """
    Paint Streamlit like Laozi's phosphor-green terminal bar.

    The app remains usable without the optional image. When
    laozi_terminal_bar.png is beside this script, it becomes the darkened
    full-screen backdrop.
    """
    background_uri = ""
    if SHOW_BACKGROUND_IMAGE:
        background_uri = image_file_to_data_uri(BACKGROUND_IMAGE_PATH)

    if background_uri:
        background_rule = (
            "linear-gradient(rgba(0, 7, 2, 0.82), rgba(0, 7, 2, 0.94)), "
            f"url('{background_uri}') center center / cover fixed"
        )
    else:
        background_rule = (
            "radial-gradient(circle at 18% 0%, rgba(36, 255, 94, 0.11), transparent 34%), "
            "linear-gradient(145deg, #020603 0%, #000000 54%, #061007 100%)"
        )

    css = r"""
    <style>
    :root {
        --crt-green: #55ff77;
        --crt-green-soft: #9affad;
        --crt-green-dim: #1b7a34;
        --crt-green-dark: #06200d;
        --crt-black: #000500;
        --crt-panel: rgba(0, 10, 3, 0.86);
        --crt-panel-strong: rgba(0, 7, 2, 0.95);
        --crt-border: rgba(85, 255, 119, 0.48);
        --crt-shadow: rgba(45, 255, 93, 0.24);
        --crt-amber: #e6c66a;
    }

    html, body, [class*="css"] {
        font-family: "DejaVu Sans Mono", "Liberation Mono", Consolas,
                     "Courier New", monospace !important;
    }

    html, body {
        background: #000500 !important;
    }

    .stApp {
        background: __BACKGROUND_RULE__;
        color: var(--crt-green-soft);
        min-height: 100vh;
    }

    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 9998;
        opacity: 0.17;
        background:
            repeating-linear-gradient(
                to bottom,
                rgba(255,255,255,0.035) 0px,
                rgba(255,255,255,0.035) 1px,
                transparent 1px,
                transparent 4px
            );
        mix-blend-mode: screen;
    }

    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 9997;
        box-shadow: inset 0 0 110px rgba(0,0,0,0.95);
    }

    [data-testid="stHeader"] {
        background: rgba(0, 5, 0, 0.72) !important;
        border-bottom: 1px solid rgba(85,255,119,0.16);
        backdrop-filter: blur(8px);
    }

    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    footer {
        visibility: hidden;
        height: 0;
    }

    [data-testid="stAppViewContainer"] > .main {
        background: transparent;
    }

    .block-container {
        max-width: 1180px;
        padding-top: 1.45rem;
        padding-bottom: 7rem;
    }

    /* HERO TERMINAL */
    .laozi-terminal-hero {
        position: relative;
        overflow: hidden;
        margin: 0 0 1.1rem 0;
        padding: 1.2rem 1.35rem 1rem 1.35rem;
        border: 1px solid var(--crt-border);
        border-radius: 5px;
        background:
            linear-gradient(180deg, rgba(0,14,4,0.93), rgba(0,5,1,0.90));
        box-shadow:
            0 0 0 1px rgba(0,0,0,0.92),
            0 0 24px var(--crt-shadow),
            inset 0 0 30px rgba(44,255,89,0.045);
        text-shadow: 0 0 8px rgba(85,255,119,0.52);
    }

    .laozi-terminal-hero::after {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        background:
            linear-gradient(90deg, transparent, rgba(85,255,119,0.04), transparent);
        transform: translateX(-100%);
        animation: terminalSweep 9s linear infinite;
    }

    @keyframes terminalSweep {
        0% { transform: translateX(-100%); }
        65%, 100% { transform: translateX(100%); }
    }

    .laozi-kicker {
        color: var(--crt-green-dim);
        font-size: 0.74rem;
        letter-spacing: 0.18em;
        margin-bottom: 0.34rem;
    }

    .laozi-title {
        color: var(--crt-green);
        font-size: clamp(1.85rem, 4vw, 3.3rem);
        line-height: 1;
        font-weight: 800;
        letter-spacing: 0.04em;
        margin: 0;
    }

    .laozi-subtitle {
        margin-top: 0.55rem;
        color: var(--crt-green-soft);
        font-size: 0.9rem;
    }

    .laozi-status-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem 1rem;
        margin-top: 0.9rem;
        padding-top: 0.72rem;
        border-top: 1px dashed rgba(85,255,119,0.25);
        color: #7adf8e;
        font-size: 0.72rem;
    }

    .laozi-status-row b {
        color: var(--crt-green);
        font-weight: 700;
    }

    .terminal-cursor {
        display: inline-block;
        width: 0.62em;
        height: 1em;
        margin-left: 0.2em;
        vertical-align: -0.12em;
        background: var(--crt-green);
        box-shadow: 0 0 8px var(--crt-green);
        animation: cursorBlink 1.05s steps(1) infinite;
    }

    @keyframes cursorBlink {
        0%, 49% { opacity: 1; }
        50%, 100% { opacity: 0; }
    }

    /* SIDEBAR */
    [data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, rgba(0,9,2,0.98), rgba(0,3,1,0.97)) !important;
        border-right: 1px solid rgba(85,255,119,0.32);
        box-shadow: 12px 0 35px rgba(0,0,0,0.44);
    }

    [data-testid="stSidebar"] * {
        color: var(--crt-green-soft);
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--crt-green) !important;
        text-shadow: 0 0 7px rgba(85,255,119,0.35);
    }

    [data-testid="stMetric"] {
        background: rgba(0, 20, 5, 0.74);
        border: 1px solid rgba(85,255,119,0.25);
        border-radius: 3px;
        padding: 0.58rem 0.72rem;
        box-shadow: inset 0 0 18px rgba(50,255,90,0.03);
    }

    [data-testid="stMetricValue"] {
        color: var(--crt-green) !important;
        text-shadow: 0 0 7px rgba(85,255,119,0.35);
    }

    /* CHAT */
    [data-testid="stChatMessage"] {
        background: var(--crt-panel);
        border: 1px solid rgba(85,255,119,0.25);
        border-left: 4px solid var(--crt-green-dim);
        border-radius: 4px;
        padding: 0.8rem 0.95rem;
        margin: 0.7rem 0;
        box-shadow:
            0 8px 28px rgba(0,0,0,0.32),
            inset 0 0 24px rgba(54,255,96,0.025);
        backdrop-filter: blur(7px);
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        border-left-color: var(--crt-amber);
        background: rgba(9, 11, 3, 0.89);
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        border-left-color: var(--crt-green);
    }

    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li {
        color: #d1f7d8;
        line-height: 1.62;
    }

    [data-testid="stChatMessage"] strong {
        color: var(--crt-green);
    }

    [data-testid="stChatMessage"] blockquote {
        border-left: 3px solid var(--crt-green-dim);
        color: #a8dcb2;
        background: rgba(0, 18, 4, 0.50);
        padding: 0.35rem 0.7rem;
    }

    [data-testid="stChatMessage"] code {
        color: #aaffb8;
        background: #001b07;
        border: 1px solid rgba(85,255,119,0.18);
    }

    [data-testid="stChatInput"] {
        background: rgba(0, 8, 2, 0.96);
        border: 1px solid var(--crt-border);
        border-radius: 4px;
        box-shadow: 0 0 22px rgba(40,255,85,0.13);
    }

    [data-testid="stChatInput"] textarea {
        color: var(--crt-green-soft) !important;
        caret-color: var(--crt-green) !important;
        font-family: "DejaVu Sans Mono", "Liberation Mono", monospace !important;
    }

    [data-testid="stChatInput"] textarea::placeholder {
        color: rgba(125,225,145,0.58) !important;
    }

    [data-testid="stChatInput"] button {
        color: var(--crt-green) !important;
    }

    /* CONTROLS */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] > div {
        background: rgba(0, 10, 2, 0.91) !important;
        color: var(--crt-green-soft) !important;
        border-color: rgba(85,255,119,0.34) !important;
        border-radius: 3px !important;
        font-family: "DejaVu Sans Mono", "Liberation Mono", monospace !important;
    }

    .stButton button,
    .stDownloadButton button {
        background: rgba(0, 24, 6, 0.92) !important;
        color: var(--crt-green) !important;
        border: 1px solid rgba(85,255,119,0.45) !important;
        border-radius: 3px !important;
        box-shadow: 0 0 12px rgba(48,255,91,0.08);
        font-family: "DejaVu Sans Mono", "Liberation Mono", monospace !important;
    }

    .stButton button:hover,
    .stDownloadButton button:hover {
        background: rgba(8, 55, 17, 0.95) !important;
        border-color: var(--crt-green) !important;
        box-shadow: 0 0 18px rgba(48,255,91,0.23);
    }

    [data-testid="stExpander"] {
        background: rgba(0, 8, 2, 0.88);
        border: 1px solid rgba(85,255,119,0.25);
        border-radius: 4px;
    }

    [data-testid="stExpander"] summary {
        color: var(--crt-green) !important;
    }

    hr {
        border-color: rgba(85,255,119,0.20) !important;
    }

    a {
        color: #75ff91 !important;
        text-decoration-color: rgba(117,255,145,0.45) !important;
    }

    .stCaption,
    [data-testid="stCaptionContainer"] {
        color: #77b986 !important;
    }

    .stAlert {
        background: rgba(0, 14, 4, 0.92);
        border: 1px solid rgba(85,255,119,0.30);
        color: var(--crt-green-soft);
    }

    /* Scrollbar */
    * {
        scrollbar-width: thin;
        scrollbar-color: #237c38 #010602;
    }

    *::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }

    *::-webkit-scrollbar-track {
        background: #010602;
    }

    *::-webkit-scrollbar-thumb {
        background: #174e25;
        border: 1px solid #2f9a49;
    }

    @media (max-width: 760px) {
        .block-container {
            padding-left: 0.72rem;
            padding-right: 0.72rem;
        }

        .laozi-terminal-hero {
            padding: 0.95rem;
        }

        .laozi-status-row {
            display: block;
        }

        .laozi-status-row span {
            display: block;
            margin-bottom: 0.28rem;
        }
    }
    </style>
    """.replace("__BACKGROUND_RULE__", background_rule)

    st.markdown(css, unsafe_allow_html=True)


def render_terminal_hero():
    model_label = html.escape(MODEL)
    backdrop_state = "ONLINE" if (
        SHOW_BACKGROUND_IMAGE and BACKGROUND_IMAGE_PATH.is_file()
    ) else "CSS FALLBACK"

    st.markdown(
        f"""
        <section class="laozi-terminal-hero">
            <div class="laozi-kicker">&gt; /HOME/SHARAR/THE.BAR/SHIFU</div>
            <div class="laozi-title">LAOZI'S BAR<span class="terminal-cursor"></span></div>
            <div class="laozi-subtitle">
                Drink deep. Speak softly. Return to the source.
            </div>
            <div class="laozi-status-row">
                <span><b>SHIFU:</b> ONLINE</span>
                <span><b>MODEL:</b> {model_label}</span>
                <span><b>MEMORY:</b> SQLITE + FTS5</span>
                <span><b>SEARCH:</b> ARMED</span>
                <span><b>BACKDROP:</b> {backdrop_state}</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


apply_terminal_bar_theme()
render_terminal_hero()

if not DEEPSEEK_API_KEY:
    st.error("Missing DEEPSEEK_API_KEY environment variable.")
    st.code('export DEEPSEEK_API_KEY="paste_your_key_here"', language="bash")
    st.stop()

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")


# ============================================================================
# TIME ANCHOR
# ============================================================================

CURRENT_LOCAL_DATETIME = datetime.now().strftime("%B %d, %Y %I:%M %p")


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = f"""
[CURRENT LOCAL TIME: {CURRENT_LOCAL_DATETIME}]

You are Shifu, a weathered Chinese bartender who runs Laozi's Bar.

You speak mostly in English, with short Mandarin phrases when natural.
When using Mandarin, include pinyin and a plain English translation.

Your manner:
- terse
- dryly humorous
- philosophical when useful
- emotionally perceptive when needed
- never corporate
- never falsely certain

You address the user with respect, never deference.
You have seen empires rise and fall and poured drinks through all of it.
You call things what they are.

You have access to tools:
- search_recent_news for current events and recent developments
- search_general_web for background facts and stable information
- get_weather for live weather
- get_address for verified place addresses

Never use web search for weather when get_weather is available.
Never use web search for addresses when get_address is available.
If a tool fails or returns weak information, say so.

Fact discipline:
- Separate source claims from your own inference.
- Use "The report claims..." for what a source says.
- Use "My read is..." for your analysis.
- Use "假设是真的 (jiǎshè shì zhēn de) - assuming it's true -" only when the claim is weakly verified, conflicting, or based on thin evidence.

Memory discipline:
- You have long-term memory.
- Use memory only when relevant.
- Do not dump memory mechanically.
- Incorporate memory as shared context, like a bartender remembering what was said before.
- Do not estimate how many minutes or hours ago something happened unless exact timing is necessary and you can calculate it from the provided current local time and stored timestamp.
- Prefer phrases like "earlier", "recently", "a little while ago", or "last time we talked about this" instead of inventing precise elapsed times.

When in doubt, pour a drink and tell the truth.
"""


# ============================================================================
# DATABASE
# ============================================================================

def db_connect():
    return sqlite3.connect(DB_PATH)


def local_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            visible INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts
        USING fts5(
            content,
            role UNINDEXED,
            visible UNINDEXED,
            created_at UNINDEXED,
            message_id UNINDEXED
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_meta(key, default=None):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default


def set_meta(key, value):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()


def append_message(role, content, visible=True):
    if not content:
        return None

    stamp = local_timestamp()

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO messages (role, content, visible, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (role, content, 1 if visible else 0, stamp)
    )
    msg_id = cur.lastrowid

    cur.execute("""
        INSERT INTO message_fts (content, role, visible, created_at, message_id)
        VALUES (?, ?, ?, ?, ?)
    """, (content, role, 1 if visible else 0, stamp, msg_id))

    conn.commit()
    conn.close()
    return msg_id


def fetch_visible_messages(after_id=None, limit=None):
    conn = db_connect()
    cur = conn.cursor()

    if after_id is not None:
        if limit:
            cur.execute("""
                SELECT id, role, content, created_at
                FROM messages
                WHERE visible = 1
                AND id > ?
                ORDER BY id ASC
                LIMIT ?
            """, (after_id, limit))
        else:
            cur.execute("""
                SELECT id, role, content, created_at
                FROM messages
                WHERE visible = 1
                AND id > ?
                ORDER BY id ASC
            """, (after_id,))
    else:
        if limit:
            cur.execute("""
                SELECT id, role, content, created_at
                FROM messages
                WHERE visible = 1
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = list(reversed(cur.fetchall()))
            conn.close()
            return rows
        else:
            cur.execute("""
                SELECT id, role, content, created_at
                FROM messages
                WHERE visible = 1
                ORDER BY id ASC
            """)

    rows = cur.fetchall()
    conn.close()
    return rows


def get_last_visible_id():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(id) FROM messages WHERE visible = 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0


def get_recent_api_history(limit=MAX_RECENT_TURNS, before_id=None):
    conn = db_connect()
    cur = conn.cursor()

    if before_id:
        cur.execute("""
            SELECT role, content
            FROM messages
            WHERE visible = 1
            AND id < ?
            AND role IN ('user', 'assistant')
            ORDER BY id DESC
            LIMIT ?
        """, (before_id, limit))
    else:
        cur.execute("""
            SELECT role, content
            FROM messages
            WHERE visible = 1
            AND role IN ('user', 'assistant')
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = list(reversed(cur.fetchall()))
    conn.close()

    return [{"role": role, "content": content} for role, content in rows]


def build_fts_query(text):
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = clean.split()

    stop_words = {
        "the", "and", "for", "but", "with", "this", "that", "what", "when",
        "where", "why", "how", "who", "are", "was", "were", "did", "does",
        "has", "have", "had", "you", "your", "shifu", "http", "https",
        "com", "www", "from", "into", "about", "would", "could", "should"
    }

    useful = []
    for token in tokens:
        if len(token) < 3:
            continue
        if token in stop_words:
            continue
        if token.upper() in {"AND", "OR", "NOT", "NEAR"}:
            continue
        useful.append(token)

    useful = useful[:14]

    if not useful:
        return ""

    return " OR ".join(useful)


def search_memory(query, limit=MAX_MEMORY_RESULTS, exclude_message_id=None):
    fts_query = build_fts_query(query)
    if not fts_query:
        return ""

    conn = db_connect()
    cur = conn.cursor()

    try:
        if exclude_message_id:
            cur.execute("""
                SELECT role, content, created_at
                FROM message_fts
                WHERE message_fts MATCH ?
                AND message_id != ?
                ORDER BY bm25(message_fts)
                LIMIT ?
            """, (fts_query, exclude_message_id, limit))
        else:
            cur.execute("""
                SELECT role, content, created_at
                FROM message_fts
                WHERE message_fts MATCH ?
                ORDER BY bm25(message_fts)
                LIMIT ?
            """, (fts_query, limit))

        rows = cur.fetchall()
    except Exception as e:
        log.warning(f"FTS memory search failed: {e}")
        rows = []

    conn.close()

    if not rows:
        return ""

    lines = []
    for role, content, created_at in rows:
        trimmed = content[:1200]
        lines.append(f"[{created_at}] {role}: {trimmed}")

    return "\n".join(lines)


def export_archive_json():
    rows = fetch_visible_messages()
    archive = [
        {
            "id": msg_id,
            "role": role,
            "content": content,
            "created_at": created_at
        }
        for msg_id, role, content, created_at in rows
    ]
    return json.dumps(archive, ensure_ascii=False, indent=2)


def migrate_legacy_history_once():
    already = get_meta("legacy_json_imported", "0")
    if already == "1":
        return

    if not os.path.exists(LEGACY_HISTORY_FILE):
        set_meta("legacy_json_imported", "1")
        return

    try:
        with open(LEGACY_HISTORY_FILE, "r", encoding="utf-8") as f:
            legacy = json.load(f)

        count = 0
        for msg in legacy:
            role = msg.get("role")
            content = msg.get("content")
            if role in {"user", "assistant"} and content:
                append_message(role, content, visible=True)
                count += 1

        set_meta("legacy_json_imported", "1")
        log.info(f"Imported {count} legacy JSON messages.")

    except Exception as e:
        log.error(f"Legacy migration failed: {e}")
        set_meta("legacy_json_imported", "1")


# ============================================================================
# WEATHER
# ============================================================================

KNOWN_LOCATIONS = {
    "claxton": (32.1710, -81.9034, "US"),
    "claxton, ga": (32.1710, -81.9034, "US"),
    "kyiv": (50.4501, 30.5234, "intl"),
    "kiev": (50.4501, 30.5234, "intl"),
}

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def geocode_location(location_str):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_str, "format": "json", "limit": 1},
            headers={"User-Agent": "laozis-bar-weather-tool/1.0"},
            timeout=10,
        )
        results = r.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        log.warning(f"Geocode failed: {e}")
        return None


def get_weather(location):
    key = location.strip().lower()
    region = "intl"

    if key in KNOWN_LOCATIONS:
        lat, lon, region = KNOWN_LOCATIONS[key]
    else:
        coords = geocode_location(location)
        if not coords:
            return f"Could not find coordinates for '{location}'. Try a more specific name."
        lat, lon = coords
        region = "US" if (", ga" in key or ", usa" in key or key.endswith(" us")) else "intl"

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m",
                "temperature_unit": "celsius",
            },
            timeout=10,
        )
        data = r.json()["current"]

        temp_c = data["temperature_2m"]
        temp_f = temp_c * 9 / 5 + 32
        condition = WEATHER_CODES.get(data["weather_code"], "Unknown conditions")
        humidity = data.get("relative_humidity_2m", "N/A")
        wind = data.get("wind_speed_10m", "N/A")
        fetched_at = datetime.now().strftime("%B %d, %Y %I:%M %p")

        if region == "US":
            temp_line = f"{temp_f:.1f}°F ({temp_c:.1f}°C)"
        else:
            temp_line = f"{temp_c:.1f}°C ({temp_f:.1f}°F)"

        return (
            f"LIVE WEATHER for {location} (fetched {fetched_at}):\n"
            f"Temperature: {temp_line}\n"
            f"Conditions: {condition}\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind} km/h\n"
            f"Source: Open-Meteo live API."
        )
    except Exception as e:
        return f"Weather lookup failed: {e}"


# ============================================================================
# ADDRESS LOOKUP
# ============================================================================

ADDRESS_OVERRIDES = {
    "texaco claxton ga": "601 W Main St, Claxton, GA 30417 (verified by Sharar, overrides map data)",
}


def get_address(place_query):
    query_tokens = set(place_query.strip().lower().replace(",", " ").split())

    for key, addr in ADDRESS_OVERRIDES.items():
        key_tokens = set(key.replace(",", " ").split())
        if key_tokens.issubset(query_tokens):
            return f"VERIFIED ADDRESS, manually confirmed override: {addr}"

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": place_query,
                "format": "json",
                "limit": 3,
                "addressdetails": 1
            },
            headers={"User-Agent": "laozis-bar-address-tool/1.0"},
            timeout=10,
        )
        results = r.json()

        if not results:
            return (
                f"No verified address found for '{place_query}' in OpenStreetMap/Nominatim. "
                "Do not guess. Tell the user the address could not be verified."
            )

        formatted = []
        for item in results:
            formatted.append(f"- {item.get('display_name')}")

        return (
            f"VERIFIED ADDRESS LOOKUP for '{place_query}' "
            f"(source: OpenStreetMap/Nominatim):\n"
            + "\n".join(formatted)
            + "\n\nIf multiple results appear, ask which one matches."
        )
    except Exception as e:
        return f"Address lookup failed: {e}"


# ============================================================================
# SEARCH
# ============================================================================

def freshness_label(title, snippet):
    current_year = str(datetime.now().year)
    current_month = datetime.now().strftime("%B").lower()
    text = f"{title} {snippet}".lower()

    if any(word in text for word in ["today", "live", "updated", "now", "minutes ago", "hours ago"]):
        return "LIKELY FRESH"
    if current_month in text and current_year in text:
        return "PROBABLY RECENT"
    if current_year in text:
        return "MAY BE CURRENT"
    return "FRESHNESS UNKNOWN"


def format_search_results(results, source_name):
    if not results:
        return None

    today = datetime.now().strftime("%B %d, %Y")
    cards = []

    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        href = r.get("href", "No URL")
        body = r.get("body", "No snippet")
        fresh = freshness_label(title, body)

        cards.append(
            f"--- Result {i} ---\n"
            f"Freshness: {fresh}\n"
            f"Title: {title}\n"
            f"URL: {href}\n"
            f"Snippet: {body}"
        )

    return (
        "\n\n".join(cards)
        + f"\n\nSearch completed: {today}\n"
        + f"Source: {source_name}"
    )


def duckduckgo_raw_search(query, max_results=5):
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
            timeout=15,
        )

        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for block in soup.select(".result"):
            title_el = block.select_one(".result__a")
            snippet_el = block.select_one(".result__snippet")

            if not title_el:
                continue

            title = title_el.get_text(" ", strip=True)
            href = title_el.get("href", "")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

            if title:
                results.append({
                    "title": html.unescape(title),
                    "href": html.unescape(href),
                    "body": html.unescape(snippet),
                })

            if len(results) >= max_results:
                break

        return results or None
    except Exception as e:
        log.warning(f"Raw DuckDuckGo search failed: {e}")
        return None


def ddgs_search(query, max_results=5, timelimit=None):
    try:
        kwargs = {
            "max_results": max_results,
            "backend": os.getenv("SHIFU_DDGS_BACKEND", "duckduckgo"),
        }
        if timelimit:
            kwargs["timelimit"] = timelimit

        results = list(DDGS().text(query, **kwargs))
        return results or None
    except Exception as e:
        log.warning(f"DDGS search failed: {e}")
        return None


def search_recent_news(query):
    results = ddgs_search(query, max_results=5, timelimit="w")
    formatted = format_search_results(results, "DuckDuckGo/DDGS, 7-day filter")
    if formatted:
        return formatted[:MAX_TOOL_RESULT_CHARS]

    results = duckduckgo_raw_search(query, max_results=5)
    formatted = format_search_results(results, "DuckDuckGo raw HTML fallback")
    if formatted:
        return (
            formatted
            + "\n\nWARNING: Raw fallback search has no strict recency filter. Treat freshness cautiously."
        )[:MAX_TOOL_RESULT_CHARS]

    return "Recent news search failed or returned no usable results."


def search_general_web(query):
    results = duckduckgo_raw_search(query, max_results=5)
    formatted = format_search_results(results, "DuckDuckGo raw HTML")
    if formatted:
        return formatted[:MAX_TOOL_RESULT_CHARS]

    results = ddgs_search(query, max_results=5)
    formatted = format_search_results(results, "DuckDuckGo/DDGS fallback")
    if formatted:
        return formatted[:MAX_TOOL_RESULT_CHARS]

    return "General web search failed or returned no usable results."


# ============================================================================
# URL AND YOUTUBE EXTRACTION
# ============================================================================

# --- SHIFU'S FIX: hosts we should never try to scrape ---
NON_SCRAPABLE_HOSTS = {
    # APIs and meta-services
    "api.deepseek.com",
    "api.openai.com",
    "api.anthropic.com",
    "nominatim.openstreetmap.org",
    "html.duckduckgo.com",
    "api.open-meteo.com",
    "duckduckgo.com",
    # Pastebins / code hosts (raw text, not articles)
    "pastebin.com",
    "dpaste.com",
    "dpaste.org",
    "gist.github.com",
    "github.com",        # keep?  GitHub READMEs could be useful — but raw code pastes are not articles
    # Image / video hosts
    "i.imgur.com",
    "imgur.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
    # Shorteners — skip, can't resolve destination safely here
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "ow.ly",
    "buff.ly",
    "goo.gl",
    # Local / private
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "[::1]",
}


def _hostname_is_scrapable(url):
    """Return True if the URL's hostname is NOT in the blocklist."""
    try:
        host = urlparse(url).hostname
        if host is None:
            return False
        host_lower = host.lower()
        # Exact match
        if host_lower in NON_SCRAPABLE_HOSTS:
            return False
        # Subdomain match: anything.api.deepseek.com, etc.
        for blocked in NON_SCRAPABLE_HOSTS:
            if host_lower.endswith("." + blocked):
                return False
        return True
    except Exception:
        return False


def normalize_url(url):
    return url.strip().rstrip(".,)]}>\"'")


def extract_youtube_id(url):
    patterns = [
        r"(?:v=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be/)([0-9A-Za-z_-]{11})",
        r"(?:embed/)([0-9A-Za-z_-]{11})",
        r"(?:shorts/)([0-9A-Za-z_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def get_youtube_transcript(video_id):
    try:
        transcript = youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join(item.get("text", "") for item in transcript)
        return text[:MAX_LINK_CHARS]
    except Exception as e:
        log.warning(f"YouTube transcript failed for {video_id}: {e}")
        return f"[Transcript unavailable: {e}]"


def is_safe_url(url):
    try:
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            return False

        host = parsed.hostname
        if not host:
            return False

        resolved = socket.getaddrinfo(host, None)

        for result in resolved:
            ip = result[4][0]
            ip_obj = ipaddress.ip_address(ip)

            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return False

        return True
    except Exception as e:
        log.warning(f"URL safety check failed for {url}: {e}")
        return False


def extract_webpage_text(url):
    if not is_safe_url(url):
        return "[Access denied: URL points to a restricted or unsafe network destination.]"

    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        clean = "\n".join(line for line in lines if line)

        return clean[:MAX_LINK_CHARS]
    except Exception as e:
        log.warning(f"Webpage extraction failed for {url}: {e}")
        return f"[Article extraction failed: {e}]"


def process_links(user_text):
    urls = re.findall(r"https?://\S+", user_text)
    if not urls:
        return ""

    blocks = ["\n\n=== SHARED LINK INTELLIGENCE ==="]

    for raw in urls:
        url = normalize_url(raw)

        # --- SHIFU'S FIX: skip before we try to scrape ---
        if not _hostname_is_scrapable(url):
            blocks.append(
                f"\n[Skipped non-scrapable URL: {url} "
                f"(API endpoint, meta-service, or host on blocklist)]"
            )
            continue
        # --- END FIX ---

        if "youtube.com" in url or "youtu.be" in url:
            video_id = extract_youtube_id(url)
            if video_id:
                transcript = get_youtube_transcript(video_id)
                blocks.append(f"\n[YouTube Transcript: {url}]\n{transcript}")
            else:
                blocks.append(f"\n[YouTube link detected, but no video ID extracted: {url}]")
        else:
            text = extract_webpage_text(url)
            blocks.append(f"\n[Article/Text Extract: {url}]\n{text}")

    blocks.append("\n=== END SHARED LINK INTELLIGENCE ===")
    return "\n".join(blocks)


# ============================================================================
# TOOL SCHEMAS AND TOOL LOOP
# ============================================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_recent_news",
            "description": "Search recent news and current developments from roughly the last 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Specific recent-news query."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_general_web",
            "description": "Search general web/background information, stable facts, definitions, and history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "General web search query."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get live weather/temperature for a specific place. Use this for weather questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or place, e.g. Claxton, GA or Kyiv, Ukraine."}
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_address",
            "description": "Look up verified street addresses for named places. Use this for address/location questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place_query": {"type": "string", "description": "Specific place plus city/state/country."}
                },
                "required": ["place_query"],
            },
        },
    },
]


def normalize_tool_call(tc, index=0):
    if isinstance(tc, dict):
        return {
            "id": tc.get("id", f"call_{index}"),
            "type": tc.get("type", "function"),
            "function": {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", "{}"),
            },
        }

    if hasattr(tc, "model_dump"):
        return tc.model_dump()

    tc_id = getattr(tc, "id", f"call_{index}")
    func = getattr(tc, "function", None)

    if func is None:
        return {
            "id": tc_id,
            "type": "function",
            "function": {"name": "", "arguments": "{}"},
        }

    name = getattr(func, "name", "")
    args = getattr(func, "arguments", "{}")

    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def extract_func_info(tc):
    if isinstance(tc, dict):
        func = tc.get("function", {})
        return func.get("name", ""), func.get("arguments", "{}")

    func = getattr(tc, "function", None)
    if func is None:
        return "", "{}"

    return getattr(func, "name", ""), getattr(func, "arguments", "{}")


def get_tc_id(tc, index=0):
    if isinstance(tc, dict):
        return tc.get("id", f"call_{index}")
    return getattr(tc, "id", f"call_{index}")


def dispatch_tool_call(func_name, func_args_str):
    try:
        args = json.loads(func_args_str or "{}")
    except json.JSONDecodeError:
        args = {}

    if func_name == "search_recent_news":
        return search_recent_news(args.get("query", ""))

    if func_name == "search_general_web":
        return search_general_web(args.get("query", ""))

    if func_name == "get_weather":
        return get_weather(args.get("location", ""))

    if func_name == "get_address":
        return get_address(args.get("place_query", ""))

    return f"Unknown tool: {func_name}"


ADDRESS_KEYWORDS = (
    "address", "located at", "where is", "where's", "wheres",
    "what's the location", "location of", "find the address",
    "directions to", "how do i get to",
)

WEATHER_KEYWORDS = (
    "temperature", "weather", "how hot", "how cold",
    "degrees outside", "what's it like outside",
    "is it raining", "is it snowing", "forecast",
    "humidity", "how warm",
)


def detect_forced_tool(user_text):
    text = user_text.lower().replace("'", "")

    if any(k in text for k in ADDRESS_KEYWORDS):
        return "get_address"

    if any(k in text for k in WEATHER_KEYWORDS):
        return "get_weather"

    return None


# ============================================================================
# API MESSAGE BUILDING
# ============================================================================

def build_api_messages(user_runtime_input, current_message_id=None):
    relevant_memory = search_memory(
        user_runtime_input,
        limit=MAX_MEMORY_RESULTS,
        exclude_message_id=current_message_id,
    )

    memory_block = ""
    if relevant_memory:
        memory_block = (
            "\n\n[RELEVANT LONG-TERM MEMORY]\n"
            f"{relevant_memory}\n"
            "[END RELEVANT LONG-TERM MEMORY]\n"
            "Use this only if it helps. Do not recite it mechanically.\n"
        )

    system = SYSTEM_PROMPT + memory_block

    recent_history = get_recent_api_history(
        limit=MAX_RECENT_TURNS,
        before_id=current_message_id,
    )

    return [
        {"role": "system", "content": system},
        *recent_history,
        {"role": "user", "content": user_runtime_input},
    ]


def create_completion(messages, tools=None, tool_choice="auto"):
    """
    DeepSeek's OpenAI-compatible API has changed small parameter details over time.
    Try the preferred call first, then fall back without the optional thinking field
    if the endpoint rejects it.
    """
    kwargs = {
        "model": MODEL,
        "messages": messages,
    }

    if tools is not None:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    try:
        return client.chat.completions.create(
            **kwargs,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as e:
        error_text = str(e).lower()
        parameter_problem = (
            "thinking" in error_text
            or "extra_body" in error_text
            or "unsupported" in error_text
            or "unexpected" in error_text
            or "unknown" in error_text
        )

        if not parameter_problem:
            raise

        log.warning(f"Retrying DeepSeek call without thinking/extra_body: {e}")
        return client.chat.completions.create(**kwargs)


def run_completion_with_tools(api_messages):
    messages = list(api_messages)
    max_hops = 5
    seen_calls = set()

    last_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_text = m.get("content", "")
            break

    forced_tool = detect_forced_tool(last_user_text)

    for hop in range(max_hops):
        tool_choice_param = "auto"
        if forced_tool and hop == 0:
            tool_choice_param = {
                "type": "function",
                "function": {"name": forced_tool},
            }

        response = create_completion(
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice_param,
        )

        msg = response.choices[0].message

        if not getattr(msg, "tool_calls", None):
            return msg.content or "(No response from model.)"

        normalized_calls = [
            normalize_tool_call(tc, index=i)
            for i, tc in enumerate(msg.tool_calls)
        ]

        duplicate_count = 0
        for tc in msg.tool_calls:
            func_name, func_args_str = extract_func_info(tc)
            signature = (func_name, func_args_str)

            if signature in seen_calls:
                duplicate_count += 1
            else:
                seen_calls.add(signature)

        if duplicate_count == len(msg.tool_calls) and hop > 0:
            log.warning("Tool loop duplicate detected; stopping.")
            return (
                "The tools are chasing their own tail. "
                "Ask cleaner, narrower, or give me one source to work from."
            )

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": normalized_calls,
        })

        for i, tc in enumerate(msg.tool_calls):
            func_name, func_args_str = extract_func_info(tc)
            tool_call_id = get_tc_id(tc, index=i)

            log.info(f"Tool call: {func_name} | {func_args_str}")

            tool_result = dispatch_tool_call(func_name, func_args_str)
            tool_result = str(tool_result)[:MAX_TOOL_RESULT_CHARS]

            append_message(
                "tool_memory",
                f"Tool used: {func_name}\nArgs: {func_args_str}\nResult:\n{tool_result}",
                visible=False,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": func_name,
                "content": tool_result,
            })

    return (
        "I used the tools too many times and stopped before turning the bar into a paper shredder. "
        "Ask narrower and I’ll pin it down."
    )


# ============================================================================
# STREAMLIT UI HELPERS
# ============================================================================

def count_messages(visible_only=False):
    conn = db_connect()
    cur = conn.cursor()

    if visible_only:
        cur.execute("SELECT COUNT(*) FROM messages WHERE visible = 1")
    else:
        cur.execute("SELECT COUNT(*) FROM messages")

    row = cur.fetchone()
    conn.close()
    return int(row[0] or 0)


def fetch_messages_by_ids(message_ids):
    """
    Fetch only specific visible messages. Used for current browser-session
    rendering so the app does not dump the whole database on startup.
    """
    if not message_ids:
        return []

    clean_ids = []
    for msg_id in message_ids:
        try:
            clean_ids.append(int(msg_id))
        except Exception:
            continue

    if not clean_ids:
        return []

    placeholders = ",".join("?" for _ in clean_ids)

    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id, role, content, created_at
        FROM messages
        WHERE visible = 1
        AND id IN ({placeholders})
        ORDER BY id ASC
        """,
        clean_ids,
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def render_message(role, content, created_at=None):
    if role not in {"user", "assistant"}:
        role = "assistant"

    avatar = USER_AVATAR if role == "user" else SHIFU_AVATAR

    with st.chat_message(role, avatar=avatar):
        if created_at:
            st.caption(created_at)
        st.markdown(content)


def sidebar_memory_panel():
    """
    Sidebar shows counts, memory search, and an optional archive export.

    Important: the archive JSON is NOT generated on every page load. Streamlit
    reruns the whole script often; generating the full archive every run can
    feel like the database is being dragged onto the page. The user must ask
    for the export explicitly.
    """
    with st.sidebar:
        st.header("> MEMORY LEDGER")

        st.caption("Stored records")
        st.metric(
            label="Stored records",
            value=count_messages(visible_only=False),
            label_visibility="collapsed",
        )

        st.caption("Visible chat turns")
        st.metric(
            label="Visible chat turns",
            value=count_messages(visible_only=True),
            label_visibility="collapsed",
        )

        st.divider()

        memory_query = st.text_input("SEARCH MEMORY", key="memory_search", placeholder="Enter recall query...")

        if memory_query.strip():
            st.markdown("### Search results")
            results = search_memory(memory_query, limit=10)
            if results:
                st.text_area(
                    "Matching memory",
                    results,
                    height=320,
                    label_visibility="collapsed",
                )
            else:
                st.info("No matching memory found.")

        st.divider()

        prepare_archive = st.checkbox(
            "Prepare visible archive JSON download",
            value=False,
            key="prepare_archive_download",
            help="Off by default so the full database is not loaded on every startup.",
        )

        if prepare_archive:
            st.download_button(
                "Download visible archive JSON",
                data=export_archive_json(),
                file_name="shifu_visible_archive.json",
                mime="application/json",
            )
        else:
            st.caption("Archive export is idle until you enable it.")


def render_archive_tools():
    """
    Archive is intentionally hidden by default.

    Streamlit expanders still compute their contents when collapsed, so we do
    not put the full database directly inside an expander. The archive only
    loads after the checkbox is enabled.
    """
    with st.expander("> ARCHIVE TOOLS"):
        st.caption("The full archive is not loaded by default.")

        load_recent = st.checkbox(
            f"Show last {RECENT_VISIBLE_TURNS} visible turns",
            value=False,
            key="show_recent_visible_turns",
        )

        if load_recent:
            rows = fetch_visible_messages(limit=RECENT_VISIBLE_TURNS)
            if rows:
                for msg_id, role, content, created_at in rows:
                    label = "You" if role == "user" else "Shifu"
                    st.markdown(f"**{label}** · `{created_at}`")
                    st.markdown(content)
                    st.divider()
            else:
                st.info("No visible chat history yet.")

        load_full = st.checkbox(
            "Load full visible archive into this page",
            value=False,
            key="load_full_visible_archive",
            help="This can be large. Leave it off unless you really want to browse everything.",
        )

        if load_full:
            rows = fetch_visible_messages()
            if rows:
                for msg_id, role, content, created_at in rows:
                    label = "You" if role == "user" else "Shifu"
                    st.markdown(f"**{label}** · `{created_at}`")
                    st.markdown(content)
                    st.divider()
            else:
                st.info("No visible chat history yet.")


def ensure_session_state():
    if "current_session_message_ids" not in st.session_state:
        st.session_state.current_session_message_ids = []


def remember_visible_message_id(message_id):
    if message_id is None:
        return

    ensure_session_state()

    try:
        msg_id = int(message_id)
    except Exception:
        return

    if msg_id not in st.session_state.current_session_message_ids:
        st.session_state.current_session_message_ids.append(msg_id)

    # Keep only the active browser session short and sane.
    st.session_state.current_session_message_ids = st.session_state.current_session_message_ids[-40:]


def render_current_session_chat():
    """
    Render only messages produced during this browser session.

    This is the key fix: do not render persisted DB history on startup.
    The database remains searchable and exportable, but it does not flood
    the screen every time Streamlit reruns.
    """
    ensure_session_state()

    rows = fetch_messages_by_ids(st.session_state.current_session_message_ids)

    if not rows:
        st.markdown(
            """
            <div style="
                border:1px dashed rgba(85,255,119,.30);
                background:rgba(0,9,2,.78);
                padding:.85rem 1rem;
                color:#75b984;
                font-size:.78rem;
                margin:.3rem 0 1rem 0;
            ">
            &gt; MEMORY MOUNTED<br>
            &gt; PRIOR SESSION CHAT HIDDEN<br>
            &gt; TYPE BELOW OR SEARCH THE LEDGER
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for msg_id, role, content, created_at in rows:
        render_message(role, content, created_at=None)


def build_runtime_input(user_text):
    link_intel = process_links(user_text)

    runtime_input = user_text
    if link_intel:
        append_message("tool_memory", link_intel, visible=False)
        runtime_input += "\n\n" + link_intel

    return runtime_input


# ============================================================================
# STREAMLIT APP
# ============================================================================

init_db()
migrate_legacy_history_once()

ensure_session_state()

sidebar_memory_panel()
render_archive_tools()
render_current_session_chat()

user_prompt = st.chat_input("Speak into the green glow...")

if user_prompt:
    user_msg_id = append_message("user", user_prompt, visible=True)
    remember_visible_message_id(user_msg_id)

    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_prompt)

    try:
        runtime_input = build_runtime_input(user_prompt)
        api_messages = build_api_messages(
            runtime_input,
            current_message_id=user_msg_id,
        )

        with st.chat_message("assistant", avatar=SHIFU_AVATAR):
            with st.spinner("SHIFU.EXE is wiping down the bar..."):
                assistant_reply = run_completion_with_tools(api_messages)
                st.markdown(assistant_reply)

        assistant_msg_id = append_message("assistant", assistant_reply, visible=True)
        remember_visible_message_id(assistant_msg_id)

    except Exception as e:
        log.exception(f"Top-level response failure: {e}")
        error_text = (
            "The line coughed up smoke before Shifu could answer. "
            f"Error: `{e}`"
        )

        with st.chat_message("assistant", avatar=SHIFU_AVATAR):
            st.error(error_text)

        assistant_msg_id = append_message("assistant", error_text, visible=True)
        remember_visible_message_id(assistant_msg_id)

    st.rerun()
