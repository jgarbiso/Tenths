"""Tyre edge orientation.

iRacing reports per-tyre temperature, wear and carcass channels as L/M/R: the
left, middle and right edges *as seen from behind the car*. On a right-side tyre
the left edge is inboard, but on a left-side tyre (LF, LR) the left edge is the
outboard one. iRacing's own garage shows this: left tyres read "O M I" and right
tyres "I M O".

Every inner/outer label in Tenths must go through `inner_middle_outer` so the
mapping lives in one place.
"""

CORNERS = ("LF", "RF", "LR", "RR")
LEFT_SIDE = ("LF", "LR")


def inner_middle_outer(corner, left, middle, right):
    """Map iRacing's left/middle/right edge values to (inner, middle, outer)."""
    if corner in LEFT_SIDE:          # left-side tyres: the left edge is outboard
        return right, middle, left
    return left, middle, right
