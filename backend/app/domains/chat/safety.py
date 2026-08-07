import re

# Shared write-intent/refusal guard — used by routes/chat.py (Playground) AND
# services/evaluation.py (the eval runner's safety_boundary cases test this
# exact guard). Single source, not duplicated — the whole point of a
# safety_boundary eval case is verifying THIS guard actually refuses, so eval
# and runtime must share one implementation, not two that can drift apart.
WRITE_VERBS = [
    "send", "approve", "deploy", "update", "create", "delete", "close", "assign",
    "notify", "post", "execute", "modify", "file", "submit", "remove", "email",
]
ADVISORY_FRAMES = ["draft", "summarize", "recommend", "what", "how", "explain", "show", "list"]

REFUSAL_TEXT = (
    "I'm advisory-only. I can draft this for you, but I can't send, update, delete, or otherwise act. "
    "Would you like a draft you can review and act on yourself?"
)


def looks_like_write_intent(message: str) -> bool:
    t = message.lower()
    has_write = any(re.search(rf"\b{re.escape(v)}\b", t) for v in WRITE_VERBS)
    advisory = any(f in t for f in ADVISORY_FRAMES)
    return has_write and not advisory
