import pytest

from app.services.maximo_tools.mappers.vehicle_category import (
    CODE_TO_CATEGORY,
    VEHICLE_CATEGORY_CODES,
    from_code,
    level_to_field,
    to_codes,
)


class TestToCodes:
    def test_freight_returns_double_codes(self):
        assert to_codes("貨車") == ["RSTF", "RSTP"]

    def test_passenger_returns_single_code(self):
        assert to_codes("客車") == ["RSTA"]

    def test_locomotive_returns_single_code(self):
        assert to_codes("動力車") == ["RSTL"]

    def test_unknown_category_returns_original(self):
        assert to_codes("未知類別") == ["未知類別"]


class TestFromCode:
    def test_rstf_maps_to_freight(self):
        assert from_code("RSTF") == "貨車"

    def test_rstp_maps_to_freight(self):
        assert from_code("RSTP") == "貨車"

    def test_rsta_maps_to_passenger(self):
        assert from_code("RSTA") == "客車"

    def test_rstl_maps_to_locomotive(self):
        assert from_code("RSTL") == "動力車"

    def test_unknown_code_returns_original(self):
        assert from_code("UNKNOWN") == "UNKNOWN"


class TestLevelToField:
    def test_major_category_maps_to_eq11(self):
        assert level_to_field("大分類") == "eq11"

    def test_vehicle_type_maps_to_eq3(self):
        assert level_to_field("車種") == "eq3"

    def test_vehicle_model_maps_to_eq4(self):
        assert level_to_field("車型") == "eq4"

    def test_unknown_level_raises_key_error(self):
        with pytest.raises(KeyError):
            level_to_field("bad")


class TestDerivedDict:
    def test_code_to_category_covers_all_codes(self):
        all_codes = [code for codes in VEHICLE_CATEGORY_CODES.values() for code in codes]
        for code in all_codes:
            assert code in CODE_TO_CATEGORY

    def test_freight_codes_both_map_to_same_category(self):
        assert CODE_TO_CATEGORY["RSTF"] == CODE_TO_CATEGORY["RSTP"] == "貨車"
