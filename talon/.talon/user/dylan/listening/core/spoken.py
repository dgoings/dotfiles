import json
import re

from .store import Section

MIN_WORDS = 60
CODE_LINE = "There's a code block here; it's on screen."


class SpokenFormatError(ValueError):
    pass


def _candidates(raw: str):
    yield raw.strip()
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE):
        yield m.group(1).strip()
    # Prose around the object: try each "{" as the start of a JSON object.
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(raw, i)
            except ValueError:
                continue
            yield obj


def parse_sections(raw: str) -> list[Section]:
    for cand in _candidates(raw):
        obj = cand
        if isinstance(cand, str):
            try:
                obj = json.loads(cand)
            except ValueError:
                continue
        if isinstance(obj, dict) and isinstance(obj.get("sections"), list):
            return _build(obj["sections"])
    raise SpokenFormatError("no valid sections object found")


def _build(items: list) -> list[Section]:
    if not items:
        raise SpokenFormatError("sections list is empty")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise SpokenFormatError("section is not an object")
        text = item.get("text")
        title = item.get("title", "")
        if not isinstance(text, str) or not text.strip():
            raise SpokenFormatError("section text is empty")
        out.append(Section(title if isinstance(title, str) else "", text.strip()))
    return out


def _strip_inline(text: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    lines = []
    for line in text.splitlines():
        if re.fullmatch(r"[\s|:\-]*", line) and "|" in line:
            continue  # table separator row
        line = line.replace("|", " ")
        line = re.sub(r"^\s*(?:#+\s*|>\s*|[-+]\s+|\d+\.\s+)", "", line)
        line = re.sub(r"[*`#~]", "", line)  # keep underscores: snake_case is common
        lines.append(re.sub(r"[ \t]+", " ", line).strip())
    return "\n".join(lines)


def _words(text: str) -> int:
    return len(text.split())


def fallback_sections(written: str) -> list[Section]:
    text = re.sub(r"```.*?(?:```|\Z)", "\n\n" + CODE_LINE + "\n\n", written, flags=re.DOTALL)
    lines = text.splitlines()

    pieces: list[list] = []  # [title, [body lines]]
    has_heading = any(re.match(r"\s{0,3}#{1,6}\s+\S", ln) for ln in lines)
    if has_heading:
        cur = ["", []]
        for ln in lines:
            m = re.match(r"\s{0,3}#{1,6}\s+(.*\S)\s*$", ln)
            if m:
                pieces.append(cur)
                cur = [_strip_inline(m.group(1)), []]
            else:
                cur[1].append(ln)
        pieces.append(cur)
    else:
        for para in re.split(r"\n\s*\n", text):
            pieces.append(["", [para]])

    built: list[Section] = []
    for title, body in pieces:
        t = _strip_inline("\n".join(body))
        t = re.sub(r"\n{2,}", "\n", t).strip()
        t = re.sub(r"\s*\n\s*", " ", t)
        if t:
            built.append(Section(title, t))
        elif title:
            built.append(Section(title, title))

    merged: list[Section] = []
    carry: Section | None = None
    for s in built:
        if carry is not None:
            s = Section(carry.title or s.title, carry.text + " " + s.text)
            carry = None
        if _words(s.text) < MIN_WORDS:
            carry = s
        else:
            merged.append(s)
    if carry is not None:
        if merged:
            last = merged[-1]
            merged[-1] = Section(last.title, last.text + " " + carry.text)
        else:
            merged.append(carry)
    return merged
