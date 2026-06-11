"""Timing trace collection for ML-KEM decapsulation."""

from __future__ import annotations

import csv
import hashlib
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
from scipy.stats import kurtosis as _kurtosis
from scipy.stats import skew as _skew
from scipy.stats import trim_mean as _trim_mean
from pqcrypto.kem import ml_kem_768

INVALID_STRATEGIES = ("single_bit", "byte_flip", "random_bytes", "zero")


@dataclass(frozen=True)
class Trace:
    scenario: str
    invalid_strategy: str
    trace_id: int
    group_id: int
    label: int
    mean_ns: float
    median_ns: float
    std_ns: float
    min_ns: float
    max_ns: float
    p10_ns: float
    p90_ns: float
    iqr_ns: float
    mad_ns: float
    trimmed_mean_ns: float
    skewness: float
    kurtosis: float
    cv: float


@dataclass(frozen=True)
class RawTiming:
    scenario: str
    invalid_strategy: str
    trace_id: int
    group_id: int
    label: int
    rep: int
    time_ns: int


def _busy_wait_ns(delay_ns: int) -> None:
    deadline = time.perf_counter_ns() + delay_ns
    while time.perf_counter_ns() < deadline:
        pass


def _corrupt(ciphertext: bytes, group_id: int) -> bytes:
    """Derive byte index and bit position from group_id via SHA-256.

    This gives each group a distinct (position, bit) pair spread across the
    full ciphertext rather than the predictable linear pattern of the old
    group_id * constant formula.
    """
    digest = hashlib.sha256(group_id.to_bytes(4, "little")).digest()
    byte_index = int.from_bytes(digest[:4], "little") % len(ciphertext)
    bit_pos = digest[4] % 8
    altered = bytearray(ciphertext)
    altered[byte_index] ^= 1 << bit_pos
    return bytes(altered)


def _random_invalid(ciphertext: bytes, group_id: int) -> bytes:
    seed = hashlib.sha256(b"mlkem-random-invalid" + group_id.to_bytes(4, "little")).digest()
    rng = random.Random(int.from_bytes(seed, "little"))
    return bytes(rng.randrange(256) for _ in range(len(ciphertext)))


def make_invalid_ciphertext(ciphertext: bytes, group_id: int, strategy: str) -> bytes:
    if strategy not in INVALID_STRATEGIES:
        raise ValueError(f"invalid strategy must be one of {', '.join(INVALID_STRATEGIES)}")
    if strategy == "single_bit":
        return _corrupt(ciphertext, group_id)
    if strategy == "byte_flip":
        digest = hashlib.sha256(b"mlkem-byte-flip" + group_id.to_bytes(4, "little")).digest()
        byte_index = int.from_bytes(digest[:4], "little") % len(ciphertext)
        altered = bytearray(ciphertext)
        altered[byte_index] ^= 0xFF
        return bytes(altered)
    if strategy == "random_bytes":
        return _random_invalid(ciphertext, group_id)
    return bytes(len(ciphertext))


def _summarize(
    scenario: str,
    invalid_strategy: str,
    trace_id: int,
    group_id: int,
    label: int,
    timings: List[int],
) -> Trace:
    values = np.asarray(timings, dtype=np.float64)
    median = float(np.median(values))
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    return Trace(
        scenario=scenario,
        invalid_strategy=invalid_strategy,
        trace_id=trace_id,
        group_id=group_id,
        label=label,
        mean_ns=mean,
        median_ns=median,
        std_ns=std,
        min_ns=float(np.min(values)),
        max_ns=float(np.max(values)),
        p10_ns=float(np.percentile(values, 10)),
        p90_ns=float(np.percentile(values, 90)),
        iqr_ns=float(np.percentile(values, 75) - np.percentile(values, 25)),
        mad_ns=float(np.median(np.abs(values - median))),
        trimmed_mean_ns=float(_trim_mean(values, 0.05)),
        skewness=float(_skew(values)),
        kurtosis=float(_kurtosis(values)),
        cv=float(std / mean) if mean != 0 else 0.0,
    )


def collect_traces(
    *,
    scenario: str,
    samples_per_class: int,
    repetitions: int,
    groups: int,
    warmup: int,
    seed: int,
    control_delay_ns: int = 0,
    invalid_strategy: str = "single_bit",
    kem=None,
) -> Tuple[List[Trace], List[RawTiming]]:
    if kem is None:
        kem = ml_kem_768
    if samples_per_class < groups:
        raise ValueError("samples_per_class must be at least the number of groups")
    if repetitions < 2:
        raise ValueError("repetitions must be at least 2")
    if invalid_strategy not in INVALID_STRATEGIES:
        raise ValueError(f"invalid_strategy must be one of {', '.join(INVALID_STRATEGIES)}")

    rng = random.Random(seed)
    public_key, private_key = kem.generate_keypair()
    paired_ciphertexts = []
    for group_id in range(groups):
        ciphertext, _ = kem.encrypt(public_key)
        paired_ciphertexts.append(
            (ciphertext, make_invalid_ciphertext(ciphertext, group_id, invalid_strategy))
        )

    # Alternate between valid and altered ciphertexts during warmup so neither
    # label enters the measurement window with a systematically colder CPU state.
    for i in range(warmup):
        pair = rng.choice(paired_ciphertexts)
        kem.decrypt(private_key, pair[i % 2])

    cases = []
    for label in (0, 1):
        for sample_index in range(samples_per_class):
            group_id = sample_index % groups
            ciphertext = paired_ciphertexts[group_id][label]
            cases.append((group_id, label, ciphertext))
    rng.shuffle(cases)

    traces: List[Trace] = []
    raw_timings: List[RawTiming] = []
    for trace_id, (group_id, label, ciphertext) in enumerate(cases):
        timings: List[int] = []
        for rep in range(repetitions):
            started = time.perf_counter_ns()
            kem.decrypt(private_key, ciphertext)
            if label == 1 and control_delay_ns:
                _busy_wait_ns(control_delay_ns)
            elapsed = time.perf_counter_ns() - started
            timings.append(elapsed)
            raw_timings.append(
                RawTiming(
                    scenario=scenario,
                    invalid_strategy=invalid_strategy,
                    trace_id=trace_id,
                    group_id=group_id,
                    label=label,
                    rep=rep,
                    time_ns=elapsed,
                )
            )
        traces.append(
            _summarize(scenario, invalid_strategy, trace_id, group_id, label, timings)
        )
    return traces, raw_timings


def write_csv(traces: Iterable[Trace], path: Path) -> None:
    rows = [asdict(trace) for trace in traces]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_raw_csv(raw_timings: Iterable[RawTiming], path: Path) -> None:
    rows = [asdict(r) for r in raw_timings]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
