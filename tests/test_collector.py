from mlkem_leakage.collector import INVALID_STRATEGIES, _corrupt, collect_traces
from mlkem_leakage.collector import make_invalid_ciphertext


def test_corrupt_changes_exactly_one_bit():
    ciphertext = bytes(1088)
    altered = _corrupt(ciphertext, 3)
    assert len(altered) == len(ciphertext)
    assert sum(bin(a ^ b).count("1") for a, b in zip(ciphertext, altered)) == 1


def test_corrupt_varies_across_groups():
    ciphertext = bytes(1088)
    positions = set()
    for group_id in range(20):
        altered = _corrupt(ciphertext, group_id)
        for i, (a, b) in enumerate(zip(ciphertext, altered)):
            if a != b:
                positions.add(i)
    assert len(positions) > 1, "all groups corrupt the same byte — diversity check failed"


def test_invalid_strategies_preserve_ciphertext_length_and_change_content():
    ciphertext = bytes(range(256)) * 5
    for strategy in INVALID_STRATEGIES:
        altered = make_invalid_ciphertext(ciphertext, 7, strategy)
        assert len(altered) == len(ciphertext)
        assert altered != ciphertext


def test_collects_balanced_traces():
    traces, raw_timings = collect_traces(
        scenario="test",
        samples_per_class=4,
        repetitions=2,
        groups=2,
        warmup=1,
        seed=7,
        invalid_strategy="byte_flip",
    )
    assert len(traces) == 8
    assert sum(trace.label == 0 for trace in traces) == 4
    assert sum(trace.label == 1 for trace in traces) == 4
    assert {trace.invalid_strategy for trace in traces} == {"byte_flip"}


def test_raw_timings_count():
    traces, raw_timings = collect_traces(
        scenario="test",
        samples_per_class=4,
        repetitions=3,
        groups=2,
        warmup=1,
        seed=7,
        invalid_strategy="random_bytes",
    )
    assert len(raw_timings) == len(traces) * 3
    assert {row.invalid_strategy for row in raw_timings} == {"random_bytes"}
