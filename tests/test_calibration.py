from tradesight.automation.calibration import PriceAxis


def test_y_for_interpolates_between_anchors():
    axis = PriceAxis(anchors=[(4600.0, 210.0), (4400.0, 430.0)], plot={})
    assert axis.y_for(4500.0) == 320.0


def test_y_for_extrapolates_above_range():
    axis = PriceAxis(anchors=[(4600.0, 210.0), (4400.0, 430.0)], plot={})
    assert axis.y_for(4700.0) == 100.0


def test_y_for_uses_widest_price_separation_unsorted():
    axis = PriceAxis(anchors=[(4500.0, 320.0), (4600.0, 210.0),
                              (4400.0, 430.0)], plot={})
    assert axis.y_for(4500.0) == 320.0


def test_is_valid_requires_two_distinct_prices():
    assert PriceAxis([(4600.0, 210.0), (4400.0, 430.0)], {}).is_valid() is True
    assert PriceAxis([(4600.0, 210.0)], {}).is_valid() is False
    assert PriceAxis([(4600.0, 210.0), (4600.0, 400.0)], {}).is_valid() is False


def test_from_calibration_parses_json_shape():
    data = {
        "price_axis_anchors": [{"price": 4600, "pixel_y": 210},
                               {"price": 4400, "pixel_y": 430}],
        "plot_area": {"left": 60, "right": 980, "top": 80, "bottom": 560},
    }
    axis = PriceAxis.from_calibration(data)
    assert axis.is_valid() is True
    assert axis.plot["right"] == 980
    assert axis.y_for(4500.0) == 320.0
