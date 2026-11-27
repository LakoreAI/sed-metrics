import pytest
from sedmetrics import SEDMetrics, psds


def test_one_configuration_and_envelope():
    refs = [(0, 0, 1.0, 2.0)]
    scores = {0: ([0., 1., 2., 3., 4.], {0: [0.1, 0.9, 0.1, 0.9]})}
    perfect = {0: ([0., 1., 2., 3., 4.], {0: [0.1, 0.9, 0.1, 0.1]})}
    kwargs = dict(recordings={0: 4.0}, dtc_threshold=0.5, gtc_threshold=0.5,
                  alpha_st=0.0, unit="second", max_efpr=1.0)
    one = psds.pipsds(refs, {"original": scores}, **kwargs)
    assert one.psds == pytest.approx(psds.psds(refs, scores, **kwargs).psds)
    result = psds.pipsds(refs, {"original": scores, "perfect": perfect}, **kwargs)
    assert result.psds == pytest.approx(1.0)
    via_api = SEDMetrics.eval(refs, metric="pipsds", scores={"original": scores, "perfect": perfect}, **kwargs)
    assert via_api.psds == result.psds
    with pytest.raises(ValueError, match="at least one"):
        psds.pipsds(refs, {}, **kwargs)
