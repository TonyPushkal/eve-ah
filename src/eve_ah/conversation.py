"""Deterministic conversation routing that never invents document facts."""

import re
from typing import Literal

Intent = Literal["capability", "small_talk", "action", "live_data", "factual"]

_ACTION_VERBS = (
    "book",
    "buy",
    "cancel",
    "change",
    "create",
    "delete",
    "download",
    "email",
    "enroll",
    "issue",
    "order",
    "pay",
    "place",
    "purchase",
    "refund",
    "register",
    "reset",
    "reserve",
    "schedule",
    "send",
    "submit",
    "update",
)
_ACTION_PATTERN = "|".join(_ACTION_VERBS)


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


def classify_intent(message: str) -> Intent:
    """Route intents that do not need document retrieval or a model call."""
    if is_capability_request(message):
        return "capability"
    text = _normalized(message)
    if text in {
        "thanks",
        "thank you",
        "thank you very much",
        "got it",
        "okay",
        "ok",
        "bye",
        "goodbye",
        "see you",
        "how are you",
        "hows it going",
    }:
        return "small_talk"
    if _is_live_data_request(text):
        return "live_data"
    if _is_action_request(text):
        return "action"
    return "factual"


def _is_live_data_request(text: str) -> bool:
    if re.search(r"\b(?:weather|temperature|forecast)\b", text) and re.search(
        r"\b(?:current|currently|now|today|tonight|tomorrow)\b", text
    ):
        return True
    if re.search(
        r"\b(?:where is|track|tracking|status of|current status|right now)\b", text
    ) and re.search(
        r"\b(?:account|appointment|delivery|order|parcel|payment|request|shipment)\b", text
    ):
        return True
    if re.search(
        r"\b(?:in stock|stock level|seats?\s+(?:are\s+)?left|available right now)\b", text
    ):
        return True
    if re.search(r"\b(?:order|parcel|shipment)\b", text) and re.search(
        r"\b(?:has|have|is|are|was|were)\b.{0,80}\b(?:dispatched|shipped|delivered)\b", text
    ):
        return True
    if (
        re.search(r"\b(?:platform|service|site)\b", text)
        and re.search(r"\b(?:down|outage|offline)\b", text)
        and re.search(r"\b(?:current|currently|now|today)\b", text)
    ):
        return True
    return bool(
        re.search(r"\b(?:have i|did i|show me my|check my|what is my)\b", text)
        and re.search(
            r"\b(?:account|attendance|balance|grade|marks|order|passed|payment|record|result|status)\b",
            text,
        )
    )


def _is_action_request(text: str) -> bool:
    return _action_verb(text) is not None


def _action_verb(message: str) -> str | None:
    text = _normalized(message)
    if re.match(
        r"^(?:(?:can|could|will|would) you\s+(?:please\s+)?|please\s+)?"
        r"update me\s+(?:on|about)\b",
        text,
    ):
        return None
    direct = re.match(
        rf"^(?:(?:can|could|will|would) you\s+(?:please\s+)?|please\s+)?(?P<verb>{_ACTION_PATTERN})\b",
        text,
    )
    if direct:
        return direct.group("verb")
    indirect = re.search(
        rf"\bi\s+(?:have|need|want|would like)\b.{{0,80}}\bto\s+(?P<verb>{_ACTION_PATTERN})\b",
        text,
    )
    return indirect.group("verb") if indirect else None


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
    names = _topic_names(overview)
    if names:
        return (
            "Which topic or item do you mean? For example, you can ask about "
            + ", ".join(names[:4])
            + "."
        )
    return "Which topic, item, or earlier question do you mean?"


def _topic_names(overview: dict) -> list[str]:
    names = [str(topic.get("name", "")).strip() for topic in overview.get("topics", [])]
    return [name for name in names if name]


def _relevant_topic_names(message: str, overview: dict, limit: int = 3) -> list[str]:
    message_tokens = set(_normalized(message).split())
    ranked = []
    for position, topic in enumerate(overview.get("topics", [])):
        name = str(topic.get("name", "")).strip()
        if not name:
            continue
        topic_text = f"{name} {topic.get('description', '')}".lower()
        topic_tokens = set(re.findall(r"[a-z0-9]+", topic_text))
        overlap = len(message_tokens.intersection(topic_tokens))
        ranked.append((-overlap, position, name))
    ranked.sort()
    return [name for _, _, name in ranked[:limit]]


def _topic_help(message: str, overview: dict) -> str:
    names = _relevant_topic_names(message, overview)
    if not names:
        return "the information provided to this workspace"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f", or {names[-1]}"


def _action_limit(message: str) -> str:
    verb = _action_verb(message)
    words = set(_normalized(message).split())
    if verb in {"change", "create", "delete", "update"}:
        return "change records or account data"
    if verb in {"book", "reserve", "schedule"}:
        return "book or schedule appointments"
    if verb in {"issue", "refund"} and "refund" in words:
        return "issue refunds"
    if verb == "cancel":
        return "cancel orders or requests"
    if verb == "reset":
        return "reset passwords or account access"
    if verb == "download":
        return "download private files or records"
    if verb in {"buy", "order", "place", "purchase"}:
        return "place orders or complete purchases"
    return "perform actions in external systems"


def _live_data_limit(message: str) -> str:
    words = set(_normalized(message).split())
    if words.intersection({"forecast", "temperature", "weather"}):
        return "live weather or forecasts"
    if words.intersection({"stock", "availability", "available", "seats"}):
        return "live availability or stock levels"
    if words.intersection({"grade", "grades", "marks", "passed", "result", "results"}):
        return "personal grades or records"
    if words.intersection({"delivery", "order", "orders", "parcel", "payment", "shipment"}):
        return "live order, delivery, or payment status"
    if words.intersection({"down", "offline", "outage", "platform", "service", "site"}):
        return "current service status or outages"
    return "live or personal information"


def action_answer(message: str, overview: dict) -> str:
    topics = _topic_help(message, overview)
    return (
        f"I can’t {_action_limit(message)}. I can still help with {topics}. I can also help you "
        "prepare what you need. What would you like to know?"
    )


def live_data_answer(message: str, overview: dict) -> str:
    topics = _topic_help(message, overview)
    return (
        f"I can’t check {_live_data_limit(message)}. I can only use the information provided in "
        f"this workspace, but I can still help with {topics}."
    )


def small_talk_answer(message: str, overview: dict) -> str:
    text = _normalized(message)
    topics = _topic_help(message, overview)
    if text in {"bye", "goodbye", "see you"}:
        return f"Take care. Come back anytime if you want help with {topics}."
    if text.startswith("thank"):
        return f"You’re welcome. Ask me anytime about {topics}."
    return f"I’m ready to help. You can ask me about {topics}."


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
    names = _topic_names(overview)
    if names:
        available = ", ".join(names[:6])
        return (
            "I found related information, but not enough detail to answer that safely. "
            f"Try rephrasing your question or ask about: {available}."
        )
    return "I found related information, but not enough detail to answer that safely."


def out_of_scope_answer(overview: dict) -> str:
    names = _topic_names(overview)
    suggestions = [str(item).strip() for item in overview.get("suggested_questions", []) if item]
    if names:
        answer = "That’s outside the information available to me. I can help with: " + ", ".join(
            names[:6]
        )
        if suggestions:
            answer += f". Try asking: “{suggestions[0]}”"
        return answer + "."
    return "That’s outside the information available to me in this workspace."
