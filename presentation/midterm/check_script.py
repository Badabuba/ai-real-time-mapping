"""Estimate spoken duration of MIDTERM_SCRIPT_UA.md (full and short versions).

Counts words in the <!-- notes:N --> / <!-- short:N --> blocks, converts at a
fixed speaking rate and adds fixed pauses for speaker changes and video start.
An estimate, not a recording: confirm with a timed rehearsal.
"""
import re
import sys
from pathlib import Path

WPM = 125  # deliberate presentation pace for Ukrainian technical speech
SYLLABLES_PER_S = 4.6  # cross-check: vowels ~ syllables (overcounts English terms); calm speech ~4.5–5.5/s
HANDOVER_S = 1.5  # per speaker change
VIDEO_START_S = 2.0
VIDEO_S = 31.0
SPEAKER_CHANGES = 5  # N→Y, Y→N, N→Y (slide 3), Y→Yu, Yu→N
TEXT = (Path(__file__).with_name("MIDTERM_SCRIPT_UA.md")).read_text(encoding="utf-8")


def blocks(kind):
    found = {int(n): body for n, body in re.findall(rf"<!-- {kind}:(\d+) -->\n(.*?)<!-- /{kind} -->", TEXT, re.S)}
    return [found[n] for n in sorted(found)]


def words(text):
    return len(re.findall(r"[\w’'.\-]+", re.sub(r"\[[^\]]*\]", "", text)))


def syllables(text):
    return len(re.findall(r"[аеєиіїоуюяaeiouy]", re.sub(r"\[[^\]]*\]", "", text.lower())))


def report(kind):
    total_words, total_s = 0, 0.0
    for number, body in enumerate(blocks(kind), 1):
        count = words(body)
        seconds = max(count / WPM * 60, syllables(body) / SYLLABLES_PER_S)  # the slower of two estimates
        if number == 4:  # narration runs over the video; slide lasts at least the video
            seconds = max(seconds, VIDEO_S) + VIDEO_START_S
        total_words, total_s = total_words + count, total_s + seconds
        print(f"{kind} slide {number}: {count:3d} words, {seconds:5.1f} s")
    total_s += SPEAKER_CHANGES * HANDOVER_S
    print(f"{kind} total: {total_words} words, {int(total_s // 60)}:{total_s % 60:04.1f} "
          f"(max of {WPM} wpm and {SYLLABLES_PER_S} syllables/s per slide; + {SPEAKER_CHANGES} x {HANDOVER_S} s handovers, "
          f"+ {VIDEO_START_S} s video start)")
    return total_s


if __name__ == "__main__":
    full, short = report("notes"), report("short")
    ok = full <= 290 and short <= 255
    print("OK" if ok else "OVER LIMIT")
    sys.exit(0 if ok else 1)
