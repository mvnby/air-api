#!/usr/bin/env python3
"""Strict PostgreSQL timeline-history and contiguous WAL-chain selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence


WAL_NAME_RE = re.compile(
    r"^(?:[0-9A-F]{24}|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
WAL_SEGMENT_RE = re.compile(r"^[0-9A-F]{24}$")
WAL_HISTORY_RE = re.compile(r"^[0-9A-F]{8}\.history$")
WAL_BACKUP_HISTORY_RE = re.compile(r"^[0-9A-F]{24}\.[0-9A-F]{8}\.backup$")
LSN_RE = re.compile(rb"(?:0|[1-9A-F][0-9A-F]{0,7})/(?:0|[1-9A-F][0-9A-F]{0,7})")
HISTORY_LINE_RE = re.compile(
    rb"([1-9][0-9]{0,9})\t(" + LSN_RE.pattern + rb")\t[^\r\n]*"
)
MAX_TIMELINE_HISTORY_BYTES = 64 * 1024
MAX_TIMELINE_HISTORY_FILES = 1024
MAX_TIMELINE_HISTORY_ENTRIES = 1024
MAX_SELECTED_WAL_SEGMENTS = 131072


@dataclass(frozen=True)
class WalObject:
    key: str
    filename: str
    size_bytes: int


@dataclass(frozen=True)
class TimelineHistoryEntry:
    timeline: int
    switch_lsn: int


@dataclass(frozen=True)
class WalSelection:
    segments: tuple[WalObject, ...]
    history_files: tuple[WalObject, ...]
    backup_history_files: tuple[WalObject, ...]

    @property
    def objects(self) -> tuple[WalObject, ...]:
        return (*self.history_files, *self.backup_history_files, *self.segments)


def list_wal_objects(
    client: object,
    *,
    bucket: str,
    prefix: str,
    max_objects: int,
) -> list[WalObject]:
    paginator = client.get_paginator("list_objects_v2")
    objects: list[WalObject] = []
    seen_names: set[str] = set()
    history_count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for raw in page.get("Contents", []):
            key = str(raw.get("Key") or "")
            filename = key.rsplit("/", 1)[-1]
            if not WAL_NAME_RE.fullmatch(filename):
                continue
            if key != f"{prefix}{filename[:8]}/{filename}":
                raise SystemExit(f"Noncanonical PITR WAL object key: {key}")
            if filename in seen_names:
                raise SystemExit(f"Duplicate PITR WAL filename: {filename}")
            size = raw.get("Size")
            if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
                raise SystemExit(f"Invalid PITR WAL object size: {key}")
            if WAL_HISTORY_RE.fullmatch(filename):
                history_count += 1
                if history_count > MAX_TIMELINE_HISTORY_FILES:
                    raise SystemExit("Too many PostgreSQL timeline history files")
                if size > MAX_TIMELINE_HISTORY_BYTES:
                    raise SystemExit(f"PostgreSQL timeline history is too large: {key}")
            elif WAL_BACKUP_HISTORY_RE.fullmatch(filename) and size > MAX_TIMELINE_HISTORY_BYTES:
                raise SystemExit(f"PostgreSQL backup history is too large: {key}")
            seen_names.add(filename)
            objects.append(WalObject(key=key, filename=filename, size_bytes=size))
            if len(objects) > max_objects:
                raise SystemExit("Too many PITR WAL objects")
    return sorted(objects, key=lambda item: item.filename)


def _parse_lsn(value: bytes) -> int:
    if not LSN_RE.fullmatch(value):
        raise SystemExit("PostgreSQL timeline history contains a noncanonical LSN")
    high_raw, low_raw = value.split(b"/", 1)
    high = int(high_raw, 16)
    low = int(low_raw, 16)
    canonical = f"{high:X}/{low:X}".encode("ascii")
    if value != canonical:
        raise SystemExit("PostgreSQL timeline history contains a noncanonical LSN")
    return (high << 32) | low


def parse_timeline_history(payload: bytes, *, timeline: int) -> tuple[TimelineHistoryEntry, ...]:
    if timeline <= 1 or timeline > 0xFFFFFFFF:
        raise SystemExit("PostgreSQL timeline history filename is invalid")
    if not payload or len(payload) > MAX_TIMELINE_HISTORY_BYTES or b"\r" in payload:
        raise SystemExit("PostgreSQL timeline history payload is invalid")
    entries: list[TimelineHistoryEntry] = []
    for line in payload.split(b"\n"):
        if not line or line.startswith(b"#"):
            continue
        match = HISTORY_LINE_RE.fullmatch(line)
        if match is None:
            raise SystemExit("PostgreSQL timeline history line is invalid")
        ancestor = int(match.group(1))
        switch_lsn = _parse_lsn(match.group(2))
        if ancestor >= timeline or switch_lsn <= 0:
            raise SystemExit("PostgreSQL timeline history lineage is invalid")
        if entries and (
            ancestor <= entries[-1].timeline
            or switch_lsn < entries[-1].switch_lsn
        ):
            raise SystemExit("PostgreSQL timeline history lineage is not monotonic")
        entries.append(TimelineHistoryEntry(ancestor, switch_lsn))
        if len(entries) > MAX_TIMELINE_HISTORY_ENTRIES:
            raise SystemExit("PostgreSQL timeline history has too many entries")
    if not entries or entries[0].timeline != 1:
        raise SystemExit("PostgreSQL timeline history does not start at timeline 1")
    return tuple(entries)


def validate_segment_size(segment_size_bytes: int) -> int:
    if (
        segment_size_bytes <= 0
        or segment_size_bytes > 0x100000000
        or 0x100000000 % segment_size_bytes != 0
    ):
        raise SystemExit(
            "WAL segment size must be a positive divisor of 2^32 bytes; "
            f"got {segment_size_bytes}"
        )
    return 0x100000000 // segment_size_bytes


def _validate_timeline(timeline: int) -> int:
    if isinstance(timeline, bool) or not isinstance(timeline, int) or not 1 <= timeline <= 0xFFFFFFFF:
        raise SystemExit("WAL timeline is invalid")
    return timeline


def _parse_canonical_lsn(lsn: str) -> int:
    try:
        encoded = lsn.encode("ascii")
    except (AttributeError, UnicodeEncodeError) as exc:
        raise SystemExit("WAL LSN is invalid") from exc
    return _parse_lsn(encoded)


def wal_segment_name(*, timeline: int, lsn: str, segment_size_bytes: int) -> str:
    segments_per_log = validate_segment_size(segment_size_bytes)
    segment_number = _parse_canonical_lsn(lsn) // segment_size_bytes
    return (
        f"{_validate_timeline(timeline):08X}{segment_number // segments_per_log:08X}"
        f"{segment_number % segments_per_log:08X}"
    )


def wal_segment_position(filename: str, *, segment_size_bytes: int) -> tuple[int, int]:
    if not WAL_SEGMENT_RE.fullmatch(filename):
        raise SystemExit(f"Invalid WAL segment filename: {filename}")
    segments_per_log = validate_segment_size(segment_size_bytes)
    timeline = int(filename[:8], 16)
    log = int(filename[8:16], 16)
    segment = int(filename[16:24], 16)
    if timeline <= 0 or segment >= segments_per_log:
        raise SystemExit(f"Invalid WAL segment filename: {filename}")
    return timeline, log * segments_per_log + segment


def wal_name_for_position(*, timeline: int, position: int, segment_size_bytes: int) -> str:
    segments_per_log = validate_segment_size(segment_size_bytes)
    return (
        f"{timeline:08X}{position // segments_per_log:08X}"
        f"{position % segments_per_log:08X}"
    )


def _history_lineage(
    objects: Sequence[WalObject],
    *,
    start_timeline: int,
    end_timeline: int,
    history_loader: Callable[[WalObject], bytes] | None,
) -> tuple[tuple[int, ...], tuple[TimelineHistoryEntry, ...], tuple[WalObject, ...]]:
    if end_timeline == 1:
        if start_timeline != 1:
            raise SystemExit("Required end WAL is not a descendant of the basebackup timeline")
        return (1,), (), ()
    if history_loader is None:
        raise SystemExit("A verified PostgreSQL timeline history loader is required")
    histories = {
        int(item.filename[:8], 16): item
        for item in objects
        if WAL_HISTORY_RE.fullmatch(item.filename)
    }
    cache: dict[int, tuple[TimelineHistoryEntry, ...]] = {}

    def load(timeline: int) -> tuple[TimelineHistoryEntry, ...]:
        if timeline in cache:
            return cache[timeline]
        item = histories.get(timeline)
        if item is None:
            raise SystemExit(f"Missing PostgreSQL timeline history: {timeline:08X}.history")
        payload = history_loader(item)
        if len(payload) != item.size_bytes:
            raise SystemExit(f"PostgreSQL timeline history size mismatch: {item.filename}")
        cache[timeline] = parse_timeline_history(payload, timeline=timeline)
        return cache[timeline]

    target_entries = load(end_timeline)
    lineage = tuple(entry.timeline for entry in target_entries) + (end_timeline,)
    if start_timeline not in lineage:
        raise SystemExit("Required end WAL is not a descendant of the basebackup timeline")
    selected_histories: list[WalObject] = []
    for index, timeline in enumerate(lineage[1:], start=1):
        if load(timeline) != target_entries[:index]:
            raise SystemExit(f"PostgreSQL timeline history fork detected at {timeline:08X}")
        selected_histories.append(histories[timeline])
    return lineage, target_entries, tuple(selected_histories)


def select_wal_objects(
    objects: Sequence[WalObject],
    *,
    start_wal_name: str,
    start_lsn: str,
    required_end_wal: str,
    segment_size_bytes: int,
    history_loader: Callable[[WalObject], bytes] | None = None,
) -> WalSelection:
    start_timeline, start_position = wal_segment_position(
        start_wal_name, segment_size_bytes=segment_size_bytes
    )
    start_lsn_value = _parse_canonical_lsn(start_lsn)
    if start_lsn_value // segment_size_bytes != start_position:
        raise SystemExit("Basebackup start LSN does not match its WAL segment")
    end_timeline, end_position = wal_segment_position(
        required_end_wal, segment_size_bytes=segment_size_bytes
    )
    lineage, history_entries, histories = _history_lineage(
        objects,
        start_timeline=start_timeline,
        end_timeline=end_timeline,
        history_loader=history_loader,
    )
    start_index = lineage.index(start_timeline)
    if start_index and start_lsn_value < history_entries[start_index - 1].switch_lsn:
        raise SystemExit("Basebackup start LSN precedes its timeline birth")
    active_lineage = lineage[start_index:]
    switches = {entry.timeline: entry.switch_lsn for entry in history_entries}
    ranges: list[tuple[int, int, int]] = []
    range_start = start_position
    for timeline in active_lineage[:-1]:
        switch_lsn = switches[timeline]
        range_end = (switch_lsn - 1) // segment_size_bytes
        if range_end < range_start:
            raise SystemExit("Basebackup WAL start is after its timeline switchpoint")
        ranges.append((timeline, range_start, range_end))
        range_start = switch_lsn // segment_size_bytes
    if end_position < range_start:
        raise SystemExit("Required end WAL precedes the descendant timeline start")
    ranges.append((end_timeline, range_start, end_position))
    selected_count = sum(end - start + 1 for _, start, end in ranges)
    if selected_count > MAX_SELECTED_WAL_SEGMENTS:
        raise SystemExit("Required PITR WAL sequence is unreasonably large")
    by_timeline = {timeline: (start, end) for timeline, start, end in ranges}
    segments: dict[tuple[int, int], WalObject] = {}
    backup_histories: list[WalObject] = []
    for item in objects:
        if WAL_HISTORY_RE.fullmatch(item.filename):
            continue
        timeline = int(item.filename[:8], 16)
        selected_range = by_timeline.get(timeline)
        if selected_range is None:
            continue
        segment_name = item.filename[:24]
        _, position = wal_segment_position(
            segment_name, segment_size_bytes=segment_size_bytes
        )
        if not selected_range[0] <= position <= selected_range[1]:
            continue
        if WAL_BACKUP_HISTORY_RE.fullmatch(item.filename):
            backup_histories.append(item)
            continue
        if item.size_bytes != segment_size_bytes:
            raise SystemExit(f"WAL segment has an invalid size: {item.filename}")
        segments[(timeline, position)] = item
    selected: list[WalObject] = []
    for timeline, range_start, range_end in ranges:
        for position in range(range_start, range_end + 1):
            item = segments.get((timeline, position))
            if item is None:
                missing = wal_name_for_position(
                    timeline=timeline,
                    position=position,
                    segment_size_bytes=segment_size_bytes,
                )
                raise SystemExit(f"PITR WAL sequence has a gap at {missing}")
            selected.append(item)
    return WalSelection(
        segments=tuple(selected),
        history_files=histories,
        backup_history_files=tuple(sorted(backup_histories, key=lambda item: item.filename)),
    )
