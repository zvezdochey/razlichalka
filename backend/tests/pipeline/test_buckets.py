"""Тесты бакетизации. Значения выдуманные."""

import pytest

from pipeline.buckets import bucket_label, make_adjuster

B = [0.3, 0.6]
PD = "decisionResult.product_trials[].scoring.pd.value"


def test_inside_bucket():
    assert bucket_label(0.42, B) == "(0.3 – 0.6]"


def test_upper_bound_included():
    assert bucket_label(0.6, B) == "(0.3 – 0.6]"


def test_lowest_bound_goes_to_first_bucket():
    assert bucket_label(0.3, B) == "≤ 0.3"


def test_below_and_above():
    assert bucket_label(-1, B) == "≤ 0.3"
    assert bucket_label(0.61, B) == "> 0.6"


def test_single_bound():
    assert bucket_label(5, [5]) == "≤ 5"
    assert bucket_label(5.1, [5]) == "> 5"


def test_big_numbers_shortened():
    b = [100000, 250000]
    assert bucket_label(117325, b) == "(100K – 250K]"
    assert bucket_label(96500, b) == "≤ 100K"
    assert bucket_label(1_500_000, [100000, 1_500_000]) == "(100K – 1.5M]"
    assert bucket_label(2_000_000, [100000, 1_500_000]) == "> 1.5M"
    assert bucket_label(1, [1500]) == "≤ 1.5K"


def test_negative_bounds():
    assert bucket_label(-5, [-10, 0]) == "(-10 – 0]"


def test_adjust_number_string():
    adjust = make_adjuster({PD: B})
    assert adjust("decisionResult.product_trials[].scoring.pd.value", "0.42") == "(0.3 – 0.6]"


def test_adjust_leaves_non_numbers():
    adjust = make_adjuster({PD: B})
    for v in ["APPROVE", "null", "true", "false", "[]", "{}", "nan", "inf", "1_0", ""]:
        assert adjust(PD, v) == v


def test_adjust_path_without_buckets_unchanged():
    adjust = make_adjuster({PD: B})
    assert adjust("decisionResult.other", "0.42") == "0.42"


def test_adjust_path_without_brackets_in_config():
    adjust = make_adjuster({"decisionResult.product_trials.scoring.pd.value": B})
    assert adjust(PD, "0.42") == "(0.3 – 0.6]"


def test_empty_config_and_empty_bounds():
    assert make_adjuster({})(PD, "0.42") == "0.42"
    assert make_adjuster({PD: []})(PD, "0.42") == "0.42"


def test_same_bucket_before_and_after():
    # 0.42 и 0.58 лежат в одном бакете, но это РАЗНЫЕ значения.
    # Поэтому DIFF_FLAG надо считать по VALUE, а не по ADJUSTED_VALUE — иначе изменение потеряется.
    adjust = make_adjuster({PD: B})
    assert adjust(PD, "0.42") == adjust(PD, "0.58") == "(0.3 – 0.6]"


@pytest.mark.parametrize("bounds", [[0.6, 0.3], [0.3, 0.3], [1, 2, 2]])
def test_bad_order_is_value_error_with_path(bounds):
    with pytest.raises(ValueError) as e:
        make_adjuster({PD: bounds})
    assert PD in str(e.value) and str(bounds) in str(e.value)


@pytest.mark.parametrize("bounds", ["0.3", [0.3, "x"], [True], [float("nan")], None])
def test_bad_bounds_type(bounds):
    with pytest.raises(ValueError):
        make_adjuster({PD: bounds})
