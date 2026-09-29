import re

from habitual import create_app, db
from habitual.config import TestConfigWithCSRF


def test_home_renders_base_layout(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert "htmx.min.js" in html
    assert "alpinejs" in html
    assert "Habitual" in html


def test_htmx_header_satisfies_csrf():
    app = create_app(TestConfigWithCSRF)

    @app.post("/__test_csrf_echo")
    def _csrf_echo():
        return "ok"

    with app.app_context():
        db.create_all()

        client = app.test_client()

        # Real page load: this is what actually issues the session-bound token,
        # the same way base.html's meta tag would for a real HTMX request.
        html = client.get("/").get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

        rejected = client.post("/__test_csrf_echo")
        assert rejected.status_code == 400

        accepted = client.post("/__test_csrf_echo", headers={"X-CSRFToken": token})
        assert accepted.status_code == 200

        db.drop_all()
