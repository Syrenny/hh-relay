from hh_relay.monitor import _plain_detail, _plausible_title


def test_title_prefilter_keeps_backend_and_drops_obvious_noise() -> None:
    assert _plausible_title("Junior Python Backend Developer")
    assert not _plausible_title("Frontend-разработчик")
    assert not _plausible_title("Системный администратор")


def test_plain_detail_removes_html_without_losing_text() -> None:
    detail = {"id": "101", "description": "<p>Python &amp; <b>Django</b></p>"}

    result = _plain_detail(detail)

    assert result["description"] == "Python & Django"
    assert detail["description"].startswith("<p>")
