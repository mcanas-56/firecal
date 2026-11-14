"""FireCal colour palette for the month x year calendar (T-03).

The page now uses the prototype's design colours (web/js/calendar.js, web/js/monthly.js),
keeping the T-03 rules that zero and no data look different and that unusual years get
an outline. This module keeps the T-03 palette for notebooks and analysis.

One place for every colour the calendar uses, so US-04a (sample grid), US-04
(real heatmap), US-06 (unusual-year flags) and US-07 (raw vs harmonized) all
look the same. Plain hex strings and small helpers, no plotting library, so it
works with whatever the calendar is drawn with (Altair, pandas Styler, HTML).

Design choices:
- Fill = burning activity. A 7-step sequential yellow -> orange -> dark red
  scale (ColorBrewer YlOrRd). It changes in lightness as well as hue, so it
  still reads as low -> high for colour-blind viewers and in greyscale.
- Zero detections and no data are different things: zero is a real
  measurement (near-white), no data means the sensor did not cover that month
  (neutral grey, e.g. VIIRS before 2012).
- Fire counts are very skewed (a peak month can be 100x a quiet one), so
  values are binned on a log scale; otherwise everything but the peak month
  would sit in the lightest bin.
- Unusual years (US-06) are marked with an outline, not a fill, so the
  activity colours stay readable underneath.
"""

from __future__ import annotations

import math

# Sequential scale for burning activity, lightest (least) to darkest (most).
ACTIVITY_SCALE: list[str] = [
    "#ffffb2",
    "#fed976",
    "#feb24c",
    "#fd8d3c",
    "#fc4e2a",
    "#e31a1c",
    "#b10026",
]

ZERO_COLOR = "#f7f4ee"  # month observed, no fire detections
NO_DATA_COLOR = "#bdbdbd"  # month not covered by the data

# Outlines for years flagged by US-06 (drawn around the whole year row).
FLAG_HIGH_COLOR = "#3f007d"  # abnormally high year
FLAG_LOW_COLOR = "#2166ac"  # abnormally low year

# Page chrome.
GRID_LINE_COLOR = "#ffffff"  # gap between calendar cells
TEXT_DARK = "#1f1f1f"
TEXT_LIGHT = "#ffffff"

MONTH_LABELS: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _log_position(value: float, vmax: float) -> float:
    """Where value sits between 0 and vmax on a log1p scale, from 0.0 to 1.0."""
    return math.log1p(value) / math.log1p(vmax)


def activity_color(value: float | None, vmax: float) -> str:
    """Fill colour for one calendar cell.

    value: the cell's fire count (or harmonized count); None or NaN = no data.
    vmax: the largest value on the calendar, so the darkest colour is the
    busiest month shown.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NO_DATA_COLOR
    if value <= 0 or vmax <= 0:
        return ZERO_COLOR
    steps = len(ACTIVITY_SCALE)
    position = _log_position(min(value, vmax), vmax)
    return ACTIVITY_SCALE[min(int(position * steps), steps - 1)]


def legend_bins(vmax: float) -> list[tuple[str, str]]:
    """(colour, label) pairs for the calendar legend, lightest first.

    Labels are the whole-count range each colour covers, e.g. "1", "2-3",
    "4-9", worked out with activity_color itself so legend and cells agree.
    Colours that cover no whole count (when vmax is small) are left out.
    """
    if vmax <= 0:
        return [(ZERO_COLOR, "0")]
    top = math.ceil(vmax)
    bins: list[tuple[str, str]] = []
    low = 1
    while low <= top:
        color = activity_color(low, vmax)
        high = low
        while high + 1 <= top and activity_color(high + 1, vmax) == color:
            high += 1
        bins.append((color, f"{low}" if high == low else f"{low}-{high}"))
        low = high + 1
    return bins


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a #rrggbb colour, 0 (black) to 1 (white)."""
    channels = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a: str, color_b: str) -> float:
    """WCAG contrast ratio between two colours, 1 to 21."""
    la, lb = sorted((relative_luminance(color_a), relative_luminance(color_b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_color_for(fill: str) -> str:
    """Dark or light text, whichever reads better on this fill colour."""
    if contrast_ratio(fill, TEXT_DARK) >= contrast_ratio(fill, TEXT_LIGHT):
        return TEXT_DARK
    return TEXT_LIGHT
