import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from app.modules.runtime.tools.wire import decode, encode

# What SQLTool really returns: the driver gives tuples of Decimal, date and datetime.
SQL_RESULT = {
    "columns": ["region", "revenue", "day", "updated_at", "note", "orders", "rate"],
    "rows": [
        (
            "华东",
            Decimal("12.50"),
            date(2025, 8, 1),
            datetime(2025, 8, 1, 9, 30, tzinfo=timezone.utc),
            None,
            3,
            0.5,
        ),
        ("华南", Decimal("0.10"), date(2025, 8, 2), None, "补录", 0, 1.0),
    ],
}


def test_a_sql_result_comes_back_exactly_as_it_left():
    back = decode(json.loads(json.dumps(encode(SQL_RESULT))))

    assert back == SQL_RESULT
    row = back["rows"][0]
    assert type(row) is tuple
    assert [type(value) for value in row] == [
        str,
        Decimal,
        date,
        datetime,
        type(None),
        int,
        float,
    ]


def test_the_marked_form_is_plain_json():
    assert encode({"rows": [("华东", Decimal("12.50"), date(2025, 8, 1))]}) == {
        "rows": [
            {
                "__type__": "tuple",
                "items": [
                    "华东",
                    {"__type__": "decimal", "value": "12.50"},
                    {"__type__": "date", "value": "2025-08-01"},
                ],
            }
        ]
    }


def test_a_datetime_stays_a_datetime_not_a_date():
    moment = datetime(2025, 8, 1, 9, 30, tzinfo=timezone.utc)

    assert encode(moment) == {
        "__type__": "datetime",
        "value": "2025-08-01T09:30:00+00:00",
    }
    assert decode(encode(moment)) == moment


def test_decimal_keeps_its_exact_digits():
    # A float would turn 0.10 into 0.1 and 12.50 into 12.5.
    assert decode(encode(Decimal("0.10"))).as_tuple() == Decimal("0.10").as_tuple()


@pytest.mark.parametrize(
    "plain",
    [
        {"status": "ready", "evidences": [{"chunk_id": 7, "score": 0.82}]},
        ["a", 1, 2.5, True, None],
        "文本",
        None,
    ],
)
def test_plain_json_passes_through_unchanged(plain):
    assert encode(plain) == plain
    assert decode(plain) == plain


def test_a_dict_that_already_uses_the_marker_is_refused():
    with pytest.raises(ValueError):
        encode({"__type__": "decimal", "value": "1"})
