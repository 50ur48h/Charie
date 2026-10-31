"""Calendar shape: zones, week starts, fiscal months (P09.4b)."""

import pytest

from charie.shared.knowledge.details import CalendarDetails, check_details


def test_zone_validation() -> None:
    assert CalendarDetails(time_zone="America/Chicago").time_zone == "America/Chicago"
    assert CalendarDetails(time_zone="").time_zone == ""
    with pytest.raises(ValueError, match="[Zz]one"):
        CalendarDetails(time_zone="Chicago/US")
    with pytest.raises(ValueError, match="[Zz]one"):
        check_details(
            "calendar",
            {"time_zone": "Mars/Olympus", "week_start": "monday", "fiscal_year_start": 1},
        )


def test_week_start() -> None:
    assert CalendarDetails(week_start="sunday").week_start == "sunday"
    assert CalendarDetails(week_start="monday").week_start == "monday"
    with pytest.raises(ValueError, match="week_start"):
        CalendarDetails(week_start="funday")


def test_fiscal_month() -> None:
    assert CalendarDetails(fiscal_year_start=4).fiscal_year_start == 4
    with pytest.raises(ValueError, match="1-12"):
        CalendarDetails(fiscal_year_start=0)
    with pytest.raises(ValueError, match="1-12"):
        CalendarDetails(fiscal_year_start=13)
