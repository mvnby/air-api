from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.ha import postgres_pitr_wal_lineage as lineage


SEGMENT_SIZE = 256


def _name(timeline: int, position: int) -> str:
    return lineage.wal_name_for_position(
        timeline=timeline,
        position=position,
        segment_size_bytes=SEGMENT_SIZE,
    )


def _segment(timeline: int, position: int) -> lineage.WalObject:
    name = _name(timeline, position)
    return lineage.WalObject(f"segment-{timeline}-{position}", name, SEGMENT_SIZE)


def _history(timeline: int, payload: bytes) -> lineage.WalObject:
    return lineage.WalObject(
        f"history-{timeline}", f"{timeline:08X}.history", len(payload)
    )


def _failover_objects() -> tuple[list[lineage.WalObject], dict[str, bytes]]:
    history_3 = b"1\t0/300\tpromoted to timeline 3\n"
    history_5 = history_3 + b"3\t0/580\tpromoted to timeline 5\n"
    objects = [
        _history(3, history_3),
        _history(5, history_5),
        *(_segment(1, position) for position in (1, 2)),
        *(_segment(3, position) for position in (3, 4, 5)),
        *(_segment(5, position) for position in (5, 6)),
        _segment(7, 6),
    ]
    return objects, {
        "00000003.history": history_3,
        "00000005.history": history_5,
    }


def test_selects_strict_cross_timeline_chain_after_two_promotions():
    objects, payloads = _failover_objects()

    selected = lineage.select_wal_objects(
        objects,
        start_wal_name=_name(1, 1),
        start_lsn="0/100",
        required_end_wal=_name(5, 6),
        segment_size_bytes=SEGMENT_SIZE,
        history_loader=lambda item: payloads[item.filename],
    )

    assert [item.key for item in selected.segments] == [
        "segment-1-1",
        "segment-1-2",
        "segment-3-3",
        "segment-3-4",
        "segment-3-5",
        "segment-5-5",
        "segment-5-6",
    ]
    assert [item.filename for item in selected.history_files] == [
        "00000003.history",
        "00000005.history",
    ]
    assert "segment-7-6" not in [item.key for item in selected.objects]


def test_exact_segment_boundary_does_not_require_nonexistent_parent_segment():
    history = b"1\t0/300\tpromotion exactly at segment boundary\n"
    objects = [
        _history(3, history),
        _segment(1, 1),
        _segment(1, 2),
        _segment(3, 3),
    ]

    selected = lineage.select_wal_objects(
        objects,
        start_wal_name=_name(1, 1),
        start_lsn="0/100",
        required_end_wal=_name(3, 3),
        segment_size_bytes=SEGMENT_SIZE,
        history_loader=lambda _item: history,
    )

    assert [item.filename for item in selected.segments] == [
        _name(1, 1),
        _name(1, 2),
        _name(3, 3),
    ]


def test_rejects_basebackup_lsn_before_descendant_timeline_birth():
    objects, payloads = _failover_objects()
    objects.append(_segment(3, 2))

    with pytest.raises(SystemExit, match="precedes its timeline birth"):
        lineage.select_wal_objects(
            objects,
            start_wal_name=_name(3, 2),
            start_lsn="0/2FF",
            required_end_wal=_name(5, 6),
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda item: payloads[item.filename],
        )


def test_accepts_basebackup_lsn_at_exact_descendant_timeline_birth():
    objects, payloads = _failover_objects()

    selected = lineage.select_wal_objects(
        objects,
        start_wal_name=_name(3, 3),
        start_lsn="0/300",
        required_end_wal=_name(5, 6),
        segment_size_bytes=SEGMENT_SIZE,
        history_loader=lambda item: payloads[item.filename],
    )

    assert selected.segments[0].filename == _name(3, 3)


def test_rejects_gap_on_intermediate_timeline():
    objects, payloads = _failover_objects()
    missing = _name(3, 4)
    objects = [item for item in objects if item.filename != missing]

    with pytest.raises(SystemExit, match=f"gap at {missing}"):
        lineage.select_wal_objects(
            objects,
            start_wal_name=_name(1, 1),
            start_lsn="0/100",
            required_end_wal=_name(5, 6),
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda item: payloads[item.filename],
        )


def test_rejects_forked_intermediate_history():
    objects, payloads = _failover_objects()
    history_3 = next(item for item in objects if item.filename == "00000003.history")
    payloads[history_3.filename] = b"1\t0/400\tdifferent branch\n"
    objects[objects.index(history_3)] = replace(
        history_3, size_bytes=len(payloads[history_3.filename])
    )

    with pytest.raises(SystemExit, match="history fork detected"):
        lineage.select_wal_objects(
            objects,
            start_wal_name=_name(1, 1),
            start_lsn="0/100",
            required_end_wal=_name(5, 6),
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda item: payloads[item.filename],
        )


def test_rejects_required_timeline_on_an_unrelated_branch():
    history = b"1\t0/300\tdirect child\n"
    objects = [_history(5, history), _segment(2, 1), _segment(5, 3)]

    with pytest.raises(SystemExit, match="not a descendant"):
        lineage.select_wal_objects(
            objects,
            start_wal_name=_name(2, 1),
            start_lsn="0/100",
            required_end_wal=_name(5, 3),
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda _item: history,
        )


@pytest.mark.parametrize(
    "payload,error",
    [
        (b"2\t0/100\tmissing root\n", "does not start"),
        (b"1\t00/100\tnoncanonical\n", "line is invalid"),
        (b"1\t0/200\tone\n1\t0/300\tduplicate\n", "not monotonic"),
        (b"1\t0/300\tone\n2\t0/200\treversed\n", "not monotonic"),
        (b"1\t0/100\tcrlf\r\n", "payload is invalid"),
    ],
)
def test_rejects_malformed_timeline_history(payload: bytes, error: str):
    with pytest.raises(SystemExit, match=error):
        lineage.parse_timeline_history(payload, timeline=5)


def test_rejects_history_payload_that_differs_from_listed_size():
    history = b"1\t0/300\tdirect child\n"
    item = replace(_history(3, history), size_bytes=len(history) + 1)

    with pytest.raises(SystemExit, match="size mismatch"):
        lineage.select_wal_objects(
            [item, _segment(1, 1), _segment(1, 2), _segment(3, 3)],
            start_wal_name=_name(1, 1),
            start_lsn="0/100",
            required_end_wal=_name(3, 3),
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda _item: history,
        )
