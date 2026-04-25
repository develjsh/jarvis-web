"""
Keyword Router — 단순 명령을 Gemini 호출 없이 즉시 처리.

match() 가 (response_text, actions) 를 반환하면 Gemini 스킵.
None 을 반환하면 Gemini 로 넘김.
"""

from __future__ import annotations

import re
from datetime import datetime

from actions import get_volume, open_app, open_chrome, open_terminal, set_volume


# ── 패턴 테이블 ───────────────────────────────────────────────────────────────

_VOL_UP   = re.compile(r"volume\s+up|turn\s+(?:it\s+)?up|louder|increase\s+volume", re.I)
_VOL_DOWN = re.compile(r"volume\s+down|turn\s+(?:it\s+)?down|quieter|decrease\s+volume|lower\s+volume", re.I)
_VOL_MUTE = re.compile(r"\bmute\b|silence\s+(?:it|please)?", re.I)
_VOL_MAX  = re.compile(r"max(?:imum)?\s+volume|full\s+volume|volume\s+(?:to\s+)?max", re.I)
_VOL_NUM  = re.compile(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})", re.I)

_TIME     = re.compile(r"what(?:'s|\s+is)\s+the\s+time|current\s+time|what\s+time\s+is\s+it", re.I)
_DATE     = re.compile(r"what(?:'s|\s+is)\s+(?:the\s+)?(?:date|day)|today(?:'s)?\s+date", re.I)

_TERMINAL = re.compile(r"open\s+terminal|launch\s+terminal", re.I)
_CHROME   = re.compile(r"open\s+(?:google\s+)?chrome|launch\s+(?:google\s+)?chrome", re.I)
_OPEN_APP = re.compile(r"open\s+([a-zA-Z][a-zA-Z\s]{1,30}?)(?:\s+(?:app|application))?$", re.I)

_WEB_APPS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "gmail":   "https://mail.google.com",
    "google":  "https://www.google.com",
    "netflix": "https://www.netflix.com",
    "github":  "https://www.github.com",
    "spotify": "https://open.spotify.com",
    "twitter": "https://www.twitter.com",
    "x":       "https://www.x.com",
    "reddit":  "https://www.reddit.com",
    "notion":  "https://www.notion.so",
}

_TASKS    = re.compile(r"(?:show|list|what\s+are)\s+(?:my\s+)?tasks?|my\s+tasks?", re.I)

_SEARCH   = re.compile(
    r"(?:(?:can\s+you\s+)?(?:search|look\s+up|google|find)\s+(?:for\s+)?)"
    r"(.+)",
    re.I,
)


async def match(
    text: str,
    address: str = "Master",
    get_tasks_fn=None,
    search_fn=None,
) -> tuple[str, list[dict]] | None:
    """
    Gemini 없이 처리할 수 있으면 (response_text, actions) 반환.
    처리 불가면 None 반환 → 호출자가 Gemini 로 넘김.
    """
    t = text.strip()

    # ── 볼륨 ─────────────────────────────────────────────────────────────────

    if _VOL_MAX.search(t):
        await set_volume(100)
        return f"Volume at maximum, {address}.", [_act("VOLUME", "100", "Volume set to 100")]

    if m := _VOL_NUM.search(t):
        vol = min(100, max(0, int(m.group(1))))
        await set_volume(vol)
        return f"Volume set to {vol}, {address}.", [_act("VOLUME", str(vol), f"Volume set to {vol}")]

    if _VOL_MUTE.search(t):
        await set_volume(0)
        return f"Muted, {address}.", [_act("VOLUME", "0", "Volume set to 0")]

    if _VOL_UP.search(t):
        current = await get_volume()
        new_vol = min(100, current + 15)
        await set_volume(new_vol)
        return f"Volume up to {new_vol}, {address}.", [_act("VOLUME", str(new_vol), f"Volume set to {new_vol}")]

    if _VOL_DOWN.search(t):
        current = await get_volume()
        new_vol = max(0, current - 15)
        await set_volume(new_vol)
        return f"Volume down to {new_vol}, {address}.", [_act("VOLUME", str(new_vol), f"Volume set to {new_vol}")]

    # ── 시간 / 날짜 ──────────────────────────────────────────────────────────

    if _TIME.search(t):
        now = datetime.now().strftime("%I:%M %p").lstrip("0")
        return f"It is {now}, {address}.", []

    if _DATE.search(t):
        today = datetime.now().strftime("%A, %B %d")
        return f"Today is {today}, {address}.", []

    # ── 앱 실행 ───────────────────────────────────────────────────────────────

    if _TERMINAL.search(t):
        result = await open_terminal()
        return f"Opening Terminal, {address}.", [_act("TERMINAL", None, result)]

    if _CHROME.search(t):
        result = await open_chrome()
        return f"Opening Chrome, {address}.", [_act("CHROME", None, result)]

    if m := _OPEN_APP.search(t):
        raw = m.group(1).strip()
        words = raw.split()
        # 관사 제거 (a, an, the)
        if words and words[0].lower() in {"a", "an", "the"}:
            words = words[1:]
        if not words:
            return None
        # 웹 서비스는 첫 단어로 판별 (e.g. "youtube on browser" → "youtube")
        first_word = words[0].lower()
        if first_word in _WEB_APPS:
            url = _WEB_APPS[first_word]
            result = await open_chrome(url)
            return f"Opening {first_word.title()}, {address}.", [_act("CHROME", url, result)]
        # 일반 macOS 앱
        app_name = " ".join(words).title()
        _skip = {"Terminal", "Chrome", "Google Chrome"}
        if app_name not in _skip and len(app_name) > 1:
            result = await open_app(app_name)
            return f"Opening {app_name}, {address}.", [_act("APP", app_name, result)]

    # ── 웹 검색 ─────────────────────────────────────────────────────────────

    if (m := _SEARCH.search(t)) and search_fn:
        query = m.group(1).strip()
        result = await search_fn(query)
        if result and result != "No results found.":
            return "", [_act("SEARCH", query, result)]
        return f"I couldn't find anything for that, {address}.", []

    # ── 할 일 목록 ───────────────────────────────────────────────────────────

    if _TASKS.search(t) and get_tasks_fn:
        tasks = get_tasks_fn()
        if not tasks:
            return f"You have no tasks at the moment, {address}.", []
        lines = "\n".join(f"{tk['id']}. [{tk['status']}] {tk['title']}" for tk in tasks)
        spoken = f"You have {len(tasks)} task{'s' if len(tasks) != 1 else ''}, {address}."
        return spoken, [_act("TASKS", None, lines)]

    return None


def _act(name: str, args: str | None, result: str) -> dict:
    return {"name": name, "args": args, "result": result}
