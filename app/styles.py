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

# stickers: small line drawings (SVG paths on a 24x24 grid), drawn in the card's own colors
STICKERS = {
    "star": "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z",
    "heart": "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z",
    "sparkle": "M12 3c.6 4.2 2.8 6.4 7 7-4.2.6-6.4 2.8-7 7-.6-4.2-2.8-6.4-7-7 4.2-.6 6.4-2.8 7-7z",
    "flower": "M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM12 3.5a3 3 0 0 1 0 6 3 3 0 0 1 0-6zM12 14.5a3 3 0 0 1 0 6 3 3 0 0 1 0-6zM3.5 12a3 3 0 0 1 6 0 3 3 0 0 1-6 0zM14.5 12a3 3 0 0 1 6 0 3 3 0 0 1-6 0z",
    "moon": "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "leaf": "M5 19C5 10 10 5 20 4c-1 10-6 15-15 15zM5 19l8-8",
    "music": "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    "bulb": "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.3 1 2.1h5c0-.8.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    "coffee": "M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3v3M12 3v3",
    "ghost": "M6 20V10a6 6 0 0 1 12 0v10l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5zM10 10h.01M14 10h.01",
    "fire": "M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-1 3-3 4-3 4s-1-2-1-3c-3 2-4 5-4 9a6 6 0 0 0 6 6z",
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
