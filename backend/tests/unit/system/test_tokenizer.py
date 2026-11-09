"""C1: every token count goes through one tokenizer with the old results."""

import pytest
import tiktoken
from app.core import tokenizer
from app.modules.conversations.service import estimate_conversation_tokens
from app.modules.runtime.context_budget import count_tokens as budget_tokens

SAMPLES = ["", "华东区2025年8月销售额是多少？", '{"rows": [[1, "a"]]}', "x" * 500]


@pytest.mark.parametrize("text", SAMPLES)
def test_counts_match_the_o200k_encoding_used_before(text):
    expected = len(tiktoken.get_encoding("o200k_base").encode(text))

    assert tokenizer.count_tokens(text) == expected
    assert estimate_conversation_tokens(text) == expected
    assert budget_tokens(text) == expected


def test_models_tiktoken_does_not_know_use_the_default():
    assert tokenizer.encoding_for_model("deepseek-chat").name == "o200k_base"
    assert tokenizer.encoding_for_model("gpt-4").name == "cl100k_base"
    with pytest.raises(KeyError):
        tokenizer.encoding_for_model("deepseek-chat", fallback=False)


def test_encodings_are_loaded_once():
    assert tokenizer.get_encoding() is tokenizer.get_encoding("o200k_base")
