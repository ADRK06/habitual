from habitual import create_app, db
from habitual.config import TestConfig


def test_styleguide_404s_without_the_dev_flag(client):
    # The default test app (see conftest.py) never sets HABITUAL_DEV, so
    # the dev blueprint isn't even registered - this must behave like any
    # other unknown route, not a gated-but-reachable one.
    response = client.get("/dev/styleguide")

    assert response.status_code == 404


def test_styleguide_renders_with_the_dev_flag_enabled():
    class DevTestConfig(TestConfig):
        HABITUAL_DEV = True

    app = create_app(DevTestConfig)
    with app.app_context():
        db.create_all()
        client = app.test_client()

        response = client.get("/dev/styleguide")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "STYLE GUIDE" in html
        assert "PALETTE" in html
        assert "#FFB238" in html

        db.drop_all()
