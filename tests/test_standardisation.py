from src.standardisation.names import resolve_test_name
from src.standardisation.numeric import parse_numeric, parse_range
from src.standardisation.units import convert_value
from src.standardisation.demographics import parse_age, parse_date, parse_gender
from src.standardisation.medicines import map_medicine
from src.standardisation.composites import split_combined


def test_aemoglobin_alias():
    result = resolve_test_name("aemoglobin")
    assert result["test_name_canonical"] == "Hemoglobin"
    assert result["normalization_method"] == "alias"


def test_haemoglobin_alias():
    assert resolve_test_name("HAEMOGLOBIN")["test_name_canonical"] == "Hemoglobin"


def test_tal_wbc_count():
    assert resolve_test_name("tal WBC Count")["test_name_canonical"] == "WBC"


def test_numeric_cells_string():
    parsed = parse_numeric("120000 cells/cu.mm")
    assert parsed["result_value"] == 120000
    assert parsed["parse_status"] == "numeric"


def test_numeric_comma():
    parsed = parse_numeric("4,290 cells/cu.mm")
    assert parsed["result_value"] == 4290


def test_qualitative_positive():
    parsed = parse_numeric("POSITIVE")
    assert parsed["result_value"] is None
    assert parsed["parse_status"] == "qualitative"


def test_range_hyphen():
    parsed = parse_range("4000-10000")
    assert parsed["range_low"] == 4000
    assert parsed["range_high"] == 10000


def test_range_lt():
    parsed = parse_range("<50")
    assert parsed["range_high"] == 50


def test_lakhs_to_cells():
    value, unit = convert_value(1.90, "lakhs/cumm", "cells/cu.mm")
    assert value == 190000
    assert unit == "cells/cu.mm"


def test_age_compound():
    age = parse_age("33Y11M265D")
    assert age["age_years"] is not None
    assert age["age_years"] > 33


def test_gender_male():
    assert parse_gender("M") == "male"
    assert parse_gender("Male") == "male"


def test_date_oct():
    assert parse_date("07-Oct-2025") == "2025-10-07"


def test_date_placeholder():
    assert parse_date("DD/MM/YYYY") is None


def test_pan_generic():
    assert map_medicine("Inj. Pan")["generic"] == "Pantoprazole"
    assert map_medicine("Tab. PCM")["generic"] == "Paracetamol"


def test_skip_na_medicine():
    assert map_medicine("N/A")["skipped"] is True


def test_split_dlc():
    rows = split_combined(
        "Differential Leukocyte Counts",
        "Neutrophil - 72.4, Lymphocyte - 23.5, Eosinophils - 0.7, Monocytes - 3.2, Basophils - 0.2",
        "%",
        None,
    )
    names = {r["test_name_canonical"] for r in rows}
    assert "Neutrophils" in names
    assert "Lymphocytes" in names
    assert len(rows) >= 4
