"""Deterministic conversation routing that never invents document facts."""

import re


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def is_capability_request(message: str) -> bool:
    text = _normalized(message)
    if text in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
        return True
    text = re.sub(r"^(?:hi|hello|hey)\s+", "", text)
    text = re.sub(r"^tell\s+me\s+", "", text)
    return bool(
        re.fullmatch(
            r"(?:please\s+)?(?:what\s+)?(?:can|could)\s+(?:you|i)\s+"
            r"(?:help\s+me\s+with(?:\s+it)?|help\s+with|ask\s+you(?:\s+about)?|do)",
            text,
        )
        or re.fullmatch(r"what\s+(?:do\s+you\s+know|are\s+you\s+able\s+to\s+answer)", text)
        or re.fullmatch(r"how\s+can\s+you\s+help(?:\s+me)?", text)
        or re.fullmatch(r"what\s+can\s+you\s+tell\s+me\s+about", text)
        or re.fullmatch(r"which\s+.+\s+(?:questions|topics)\s+can\s+you\s+(?:answer|explain)", text)
        or re.fullmatch(r"what\s+.+\s+topics\s+do\s+you\s+know\s+about", text)
        or re.fullmatch(r"which\s+parts\s+of\s+.+\s+can\s+you\s+explain", text)
    )


def is_dependent_followup(message: str) -> bool:
    text = _normalized(message)
    words = text.split()
    if not words or len(words) > 12:
        return False
    if re.match(r"^(?:and\s+)?what\s+(?:about|if)\b", text):
        return True
    if re.match(r"^(?:and\s+)?(?:how|when|why)\s+(?:long|much|many|soon|about)\b", text):
        return True
    return bool(set(words).intersection({"it", "its", "that", "those", "them", "they"}))


def retrieval_query(message: str, previous_user_messages: list[str]) -> str:
    if previous_user_messages and is_dependent_followup(message):
        return f"Previous subject: {previous_user_messages[-1]}\nFollow-up: {message}"
    return message


def needs_clarification(message: str, previous_user_messages: list[str]) -> bool:
    return not previous_user_messages and is_dependent_followup(message)


def clarification_answer(overview: dict) -> str:
    names = [str(topic.get("name", "")).strip() for topic in overview.get("topics", [])]
    names = [name for name in names if name]
    if names:
        return (
            "Which topic or item do you mean? For example, you can ask about "
            + ", ".join(names[:4])
            + "."
        )
    return "Which topic, item, or earlier question do you mean?"


def capability_answer(bot_name: str, overview: dict) -> str:
    topics = overview.get("topics", [])
    suggestions = overview.get("suggested_questions", [])
    if not topics:
        return (
            f"I’m {bot_name}. I answer questions from the documents currently indexed in this "
            "workspace. No topic overview is available yet; re-run ingestion after adding documents."
        )
    lines = [f"I’m {bot_name}. I can help with:"]
    for topic in topics[:8]:
        description = str(topic.get("description", "")).strip()
        suffix = f" — {description}" if description else ""
        lines.append(f"- {topic.get('name', 'Document topic')}{suffix}")
    if suggestions:
        lines.append("\nTry asking:")
        lines.extend(f"- “{question}”" for question in suggestions[:4])
    return "\n".join(lines)


def insufficient_answer(overview: dict) -> str:
    names = [str(topic.get("name", "")).strip() for topic in overview.get("topics", [])]
    names = [name for name in names if name]
    if names:
        available = ", ".join(names[:6])
        return (
            "I couldn’t find that information in the indexed documents. "
            f"I currently have information about: {available}."
        )
    return "I couldn’t find that information in the indexed documents."
