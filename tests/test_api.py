import pytest

from kanban import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), "WIP_LIMIT": 2})
    return app.test_client()


def make(client, **fields):
    res = client.post("/api/cards", json={"title": "Task", **fields})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_index_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Kanban Board" in res.data


def test_create_and_list(client):
    card = make(client, title="Write README", priority="high", points=3)
    assert card["status"] == "backlog"
    assert card["priority"] == "high"
    cards = client.get("/api/cards").get_json()
    assert [c["title"] for c in cards] == ["Write README"]


def test_title_required(client):
    res = client.post("/api/cards", json={"title": "   "})
    assert res.status_code == 400
    assert "Title" in res.get_json()["error"]


@pytest.mark.parametrize("field,value", [
    ("priority", "urgent"),
    ("points", "lots"),
    ("points", -1),
    ("due_date", "13/11/2026"),
    ("status", "blocked"),
])
def test_invalid_fields_rejected(client, field, value):
    res = client.post("/api/cards", json={"title": "x", field: value})
    assert res.status_code == 400


def test_update_card(client):
    card = make(client)
    res = client.patch(f"/api/cards/{card['id']}", json={"assignee": "Victor", "due_date": "2026-12-01"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["assignee"] == "Victor"
    assert body["due_date"] == "2026-12-01"


def test_move_reorders_positions(client):
    a, b, c = (make(client, title=t) for t in "ABC")
    client.post(f"/api/cards/{c['id']}/move", json={"status": "backlog", "position": 0})
    cards = client.get("/api/cards").get_json()
    assert [x["title"] for x in sorted(cards, key=lambda x: x["position"])] == ["C", "A", "B"]


def test_wip_limit_enforced(client):
    cards = [make(client, title=str(i)) for i in range(3)]
    for card in cards[:2]:
        assert client.post(f"/api/cards/{card['id']}/move", json={"status": "in_progress"}).status_code == 200
    res = client.post(f"/api/cards/{cards[2]['id']}/move", json={"status": "in_progress"})
    assert res.status_code == 409
    # Reordering within In Progress is still allowed at the limit
    res = client.post(f"/api/cards/{cards[1]['id']}/move", json={"status": "in_progress", "position": 0})
    assert res.status_code == 200


def test_delete_card(client):
    card = make(client)
    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.delete(f"/api/cards/{card['id']}").status_code == 404


def test_stats(client):
    a = make(client, points=5)
    make(client, points=3)
    client.post(f"/api/cards/{a['id']}/move", json={"status": "done"})
    stats = client.get("/api/stats").get_json()
    assert stats["total_points"] == 8
    assert stats["done_points"] == 5
    assert stats["percent_complete"] == 62
