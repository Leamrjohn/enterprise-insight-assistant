from app.modules.reporting.qualification import number_sentences


def test_number_sentences_keeps_each_sentence_with_its_chunk():
    evidences = [
        {"chunk_id": 17, "content": "王。把。"},
        {"chunk_id": 42, "content": "乔"},
    ]
    numbered = number_sentences(evidences)
    assert numbered["17.1"] == (17, "王。")
    assert numbered["17.2"] == (17, "把。")
    assert numbered["42.1"] == (42, "乔")
    empty = number_sentences([{"chunk_id": 1, "content": ""}])
    assert empty == {}
