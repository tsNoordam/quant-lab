import math

import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest.walkforward import make_folds, neighbourhood_scores, parameter_grid

DATES = pd.bdate_range("2000-01-03", "2007-12-31")


def folds(**overrides):
    kw = {"anchored": True, "train_years": 3, "test_months": 12, "embargo_days": 5} | overrides
    return make_folds(DATES, DATES[0], DATES[-1], **kw)


def test_folds_cover_the_range_after_the_first_training_window():
    fs = folds()
    assert [f.test.start.year for f in fs] == [2003, 2004, 2005, 2006, 2007]
    assert fs[-1].test.end <= DATES[-1]


def test_train_and_test_never_overlap_and_respect_the_embargo():
    for f in folds(embargo_days=5):
        assert f.train.end < f.test.start
        gap = DATES[(f.train.end < DATES) & (f.test.start > DATES)]
        assert len(gap) == 5


def test_test_windows_do_not_overlap_each_other():
    fs = folds()
    for prev, nxt in zip(fs, fs[1:], strict=False):
        assert prev.test.end < nxt.test.start


def test_anchored_folds_grow_and_rolling_folds_slide():
    anchored = folds(anchored=True)
    assert {f.train.start for f in anchored} == {DATES[0]}
    rolling = folds(anchored=False)
    lengths = [(f.train.end - f.train.start).days for f in rolling]
    assert max(lengths) - min(lengths) < 10  # ~3 years each
    assert rolling[-1].train.start > DATES[0]


def test_short_final_window_is_dropped():
    short = make_folds(
        DATES,
        DATES[0],
        pd.Timestamp("2003-01-20"),
        anchored=True,
        train_years=3,
        test_months=12,
        embargo_days=5,
    )
    assert short == []  # only ~7 test days after the embargo


def test_grid_must_be_increasing():
    with pytest.raises(ValueError, match="increasing"):
        parameter_grid(OmegaConf.create({"window": [60, 40]}))


def test_neighbourhood_mean_prefers_stable_regions():
    grid = OmegaConf.create({"window": [1, 2, 3, 4, 5], "entry_z": [1.0]})
    names, combos = parameter_grid(grid)
    # An isolated spike at window=1 next to a collapse, versus a plateau at 3-5.
    raw = dict(zip(combos, [3.0, -2.0, 1.0, 1.0, 1.0], strict=True))
    score = neighbourhood_scores(names, grid, raw)
    assert score[(1, 1.0)] == pytest.approx(0.5)  # (3 - 2) / 2
    assert score[(4, 1.0)] == pytest.approx(1.0)  # (1 + 1 + 1) / 3
    assert max(raw, key=raw.get) == (1, 1.0)  # "best" picks the spike
    assert max(score, key=score.get) == (4, 1.0)  # neighbourhood picks the plateau


def test_neighbourhood_mean_ignores_invalid_points():
    grid = OmegaConf.create({"window": [1, 2]})
    names, combos = parameter_grid(grid)
    score = neighbourhood_scores(names, grid, {(1,): math.nan, (2,): 2.0})
    assert score[(1,)] == 2.0 and score[(2,)] == 2.0
