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


def test_styleguide_shows_the_planet_scale_building_section():
    # The sprites actually wired into /colony (habitual.colony.
    # BUILDING_SLOTS) - shown here too so the developer can still see the
    # live art without opening the real page. Round 4 promoted the LV1-
    # readability fix straight into these filenames (no separate
    # candidate section any more - see git history for that review step).
    class DevTestConfig(TestConfig):
        HABITUAL_DEV = True

    app = create_app(DevTestConfig)
    with app.app_context():
        db.create_all()
        client = app.test_client()

        response = client.get("/dev/styleguide")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "PLANET-SCALE BUILDINGS" in html
        assert "Defense Tower" in html
        # Every building type's all 3 levels, at both x1 and x4.
        assert "planet_building_defense_tower_lv1.png" in html
        assert "planet_building_defense_tower_lv3.png" in html
        assert "planet_building_custom_module_lv1.png" in html
        # The planet variant comparison (original vs antenna/debris-free).
        assert "PLANET VARIANT" in html
        assert "planet_render_rust.png" in html
        assert "planet_render_rust_clean.png" in html
        # All five full-planet preview composites.
        assert "planet_preview_empty.png" in html
        assert "planet_preview_lv1.png" in html
        assert "planet_preview_lv3.png" in html
        assert "planet_preview_mixed_bare.png" in html
        assert "planet_preview_mixed_dot.png" in html
        # No leftover candidate-only section/filenames from the review step.
        assert "CANDIDATE" not in html
        assert "_candidate.png" not in html

        db.drop_all()
