from src.validation.classify import classify_result


def test_hemoglobin_outlier_low():
    assert classify_result("Hemoglobin", 0.1, "numeric", "numeric", 13, 17) == "Outlier"


def test_hemoglobin_outlier_high():
    assert classify_result("Hemoglobin", 999, "numeric", "numeric", 13, 17) == "Outlier"


def test_hemoglobin_below_range():
    assert classify_result("Hemoglobin", 12.0, "numeric", "numeric", 13, 17) == "Below Range"


def test_hemoglobin_within_range():
    assert classify_result("Hemoglobin", 14.0, "numeric", "numeric", 13, 17) == "Within Range"


def test_alt_above_range():
    assert classify_result("ALT", 91, "numeric", "numeric", 7, 56) == "Above Range"


def test_non_numeric_invalid():
    assert classify_result("Hemoglobin", None, "qualitative", "numeric", 13, 17) == "Invalid"


def test_widal_qualitative_ok():
    assert classify_result("Widal", None, "qualitative", "qualitative", None, None) == "Within Range"


def test_unmapped_invalid():
    assert classify_result("UNMAPPED", 1.0, "numeric", "numeric", None, None) == "Invalid"
