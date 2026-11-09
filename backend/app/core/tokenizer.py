"""One place that counts tokens (C1).

Budgets, history trimming, memory selection and the model gateways all count
with the same tokenizer, so a prompt measured in one place has the same size
everywhere.  Encodings are cached per process.  The images download the
encoding files at build time into ``TIKTOKEN_CACHE_DIR``, so counting works in
a container with no network; elsewhere tiktoken fetches and caches them once.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

DEFAULT_ENCODING = "o200k_base"
# Every encoding the images bake in: the default and the older OpenAI family.
BUNDLED_ENCODINGS = ("o200k_base", "cl100k_base")


@lru_cache
def get_encoding(name: str = DEFAULT_ENCODING) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def encoding_for_model(model_name: str, *, fallback: bool = True) -> tiktoken.Encoding:
    """The model's own encoding; models tiktoken does not know (DeepSeek) use
    the default unless ``fallback`` is False, which raises KeyError instead."""
    try:
        name = tiktoken.encoding_name_for_model(model_name)
    except KeyError:
        if not fallback:
            raise
        name = DEFAULT_ENCODING
    return get_encoding(name)


def count_tokens(text: str, *, model_name: str | None = None) -> int:
    encoding = get_encoding() if model_name is None else encoding_for_model(model_name)
    return len(encoding.encode(text))


def preload() -> None:
    """Download every bundled encoding (run at image build time)."""
    for name in BUNDLED_ENCODINGS:
        get_encoding(name).encode("warm")


if __name__ == "__main__":
    preload()
