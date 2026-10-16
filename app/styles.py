"""Everything a card may look like: the single source of truth for the AI, the server and the page.

The AI picks only keys from here; the server repairs anything else; the page renders only these.
"""

# ASSUMPTION: 6 soft palettes and 6 vibrant ones in v0. Each works with dark ink.
PALETTES = {
    "peach": {"paper": "#ffe9dc", "tape": "#f6b89a", "highlight": "#ffb08a", "ink": "#3d2a22", "accent": "#e07a52"},
    "sage": {"paper": "#e7f0e1", "tape": "#b7cfa8", "highlight": "#b9dba3", "ink": "#24321f", "accent": "#6f9a5b"},
    "lavender": {"paper": "#ece6fa", "tape": "#c6b6ef", "highlight": "#cbb8ff", "ink": "#2b2440", "accent": "#8a6fd1"},
    "butter": {"paper": "#fff6d1", "tape": "#f5dc7a", "highlight": "#ffe066", "ink": "#3a3218", "accent": "#d9a91a"},
    "sky": {"paper": "#e3f1fb", "tape": "#a9d3f0", "highlight": "#9fd6ff", "ink": "#1d2f3d", "accent": "#4b98cf"},
    "rose": {"paper": "#fde6ec", "tape": "#f3b3c4", "highlight": "#ffadc2", "ink": "#3d1f28", "accent": "#d9688a"},
    # vibrant: plain bright sticky notes, still with dark ink
    "sunflower": {"paper": "#ffd93b", "tape": "#5ec8f2", "highlight": "#ffffff", "ink": "#2a2208", "accent": "#e0a800"},
    "tangerine": {"paper": "#ffa94d", "tape": "#7b6cf6", "highlight": "#fff3b0", "ink": "#2e1806", "accent": "#e8590c"},
    "coral": {"paper": "#ff8787", "tape": "#ffe066", "highlight": "#fff3b0", "ink": "#2e0d0d", "accent": "#e03131"},
    "magenta": {"paper": "#f783ac", "tape": "#69db7c", "highlight": "#fff3b0", "ink": "#2e0a1a", "accent": "#d6336c"},
    "lime": {"paper": "#a9e34b", "tape": "#f783ac", "highlight": "#ffffff", "ink": "#1b2a06", "accent": "#5c940d"},
    "aqua": {"paper": "#3bc9db", "tape": "#ffd43b", "highlight": "#ffffff", "ink": "#06262b", "accent": "#0c8599"},
}
VIBRANT = ("sunflower", "tangerine", "coral", "magenta", "lime", "aqua")

# title fonts (handwriting); the body is always the calm, readable one
FONTS = {
    "caveat": {"family": "'Caveat', cursive", "label": "Caveat"},
    "patrick": {"family": "'Patrick Hand', cursive", "label": "Patrick Hand"},
    "kalam": {"family": "'Kalam', cursive", "label": "Kalam"},
    "marker": {"family": "'Permanent Marker', cursive", "label": "Marker"},
    "gloria": {"family": "'Gloria Hallelujah', cursive", "label": "Gloria"},
}
BODY_FONT = "'Nunito', system-ui, sans-serif"
GOOGLE_FONTS = "Caveat:wght@500;700&family=Patrick+Hand&family=Kalam:wght@400;700&family=Permanent+Marker&family=Gloria+Hallelujah&family=Nunito:wght@400;600;700"

STICKERS = {
    "star": "⭐",
    "heart": "💛",
    "sparkle": "✨",
    "flower": "🌸",
    "moon": "🌙",
    "bolt": "⚡",
    "leaf": "🌿",
    "music": "🎵",
    "bulb": "💡",
    "coffee": "☕",
    "ghost": "👻",
    "fire": "🔥",
}

DEFAULT_PALETTE = "butter"
DEFAULT_FONT = "caveat"

# the AI's limits on a card
MAX_TITLE_WORDS = 6
MAX_BODY_WORDS = 60
MAX_HIGHLIGHTS = 3
MAX_OPS_PER_TURN = 6  # one idea may become several notes

# the board, in pixels: a card and where new ones go
CARD_W, CARD_H = 250, 200
BOARD_W = 2400


def public():
    """What the page needs to render (and nothing else)."""
    return {
        "palettes": PALETTES,
        "fonts": {k: v["family"] for k, v in FONTS.items()},
        "font_labels": {k: v["label"] for k, v in FONTS.items()},
        "body_font": BODY_FONT,
        "stickers": STICKERS,
        "google_fonts": GOOGLE_FONTS,
        "card": {"w": CARD_W, "h": CARD_H},
    }
