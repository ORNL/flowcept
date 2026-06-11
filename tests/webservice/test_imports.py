"""Basic import smoke test for webservice package."""


def test_webservice_imports():
    from flowcept.webservice.main import app

    assert app is not None
