"""Maintenance questions the user answers on the cooperative page, and how they count in the score (#46)."""

from tests.report_factory import make_report_pdf
from tests.test_backup import export, import_
from tests.uploads import upload_pdf


def add_cooperative(client, **report) -> int:
    response = upload_pdf(client, make_report_pdf(**report), "rapport.pdf")
    assert response.status_code == 201, response.text
    return response.json()["cooperative_id"]


def answer(client, cooperative_id, name, value):
    return client.put(f"/api/cooperatives/{cooperative_id}/maintenance/{name}", json={"answer": value})


def overview(client, cooperative_id):
    return client.get(f"/api/cooperatives/{cooperative_id}").json()


def part(score, name):
    return next((p for p in score["parts"] if p["key"] == f"maintenance:{name}"), None)


def test_overview_lists_the_questions_unanswered(client):
    data = overview(client, add_cooperative(client))
    assert [(q["name"], q["label"], q["answer"]) for q in data["maintenance"]] == [
        ("stambyte", "Stambyte", None), ("tak", "Takrenovering", None), ("fasad", "Fasadrenovering", None)]
    assert data["maintenance"][0]["question"] == "Står föreningen inför stambyte de närmaste fem åren?"
    assert data["maintenance"][0]["topic"] == "Stambyte"  # Report passages with this topic are the evidence.
    reasons = {m["key"]: m["reason"] for m in data["score"]["missing"]}
    assert reasons["maintenance:stambyte"] == "Inte besvarat."
    assert data["score"]["score"] == 41  # Unanswered questions count neither as good nor as bad.


def test_answer_yes_counts_as_a_large_cost_ahead(client):
    # Default report: 3 500 points over 85 weight (41). Stambyte Ja: 0 points, weight 5: 3500 / 90 = 38.9 → 39.
    cooperative_id = add_cooperative(client)
    response = answer(client, cooperative_id, "stambyte", "yes")
    assert response.status_code == 200
    data = response.json()
    stambyte = part(data["score"], "stambyte")
    assert (stambyte["label"], stambyte["value_text"], stambyte["part_score"], stambyte["weight"]) == (
        "Stambyte, kommande", "Ja", 0, 5)
    assert stambyte["status"] == "user_entered"
    assert stambyte["source_text"].startswith("Angivet av dig (")
    assert stambyte["rule"] == "Ja (stambyte de närmaste fem åren) ger 0 poäng, Nej ger 100 poäng. Vet inte eller inget svar räknas inte."
    assert data["score"]["score"] == 39
    assert data["maintenance"][0]["answer"] == "yes"


def test_answer_can_be_changed(client):
    # Nej: 100 points, weight 5: (3500 + 500) / 90 = 44.4 → 44.
    cooperative_id = add_cooperative(client)
    answer(client, cooperative_id, "stambyte", "yes")
    data = answer(client, cooperative_id, "stambyte", "no").json()
    assert part(data["score"], "stambyte")["value_text"] == "Nej"
    assert data["score"]["score"] == 44


def test_dont_know_is_a_missing_part(client):
    cooperative_id = add_cooperative(client)
    data = answer(client, cooperative_id, "tak", "unknown").json()
    assert part(data["score"], "tak") is None
    assert {m["key"]: m["reason"] for m in data["score"]["missing"]}["maintenance:tak"] == "Besvarat med Vet inte."
    assert data["maintenance"][1]["answer"] == "unknown"
    assert data["score"]["score"] == 41


def test_invalid_question_or_answer_is_rejected(client):
    cooperative_id = add_cooperative(client)
    assert answer(client, cooperative_id, "hiss", "yes").status_code == 422
    assert answer(client, cooperative_id, "stambyte", "kanske").status_code == 422
    assert client.put("/api/cooperatives/999/maintenance/stambyte", json={"answer": "yes"}).status_code == 404


def test_answer_survives_a_new_report_for_the_cooperative(client):
    cooperative_id = add_cooperative(client)
    answer(client, cooperative_id, "stambyte", "yes")
    upload_pdf(client, make_report_pdf(period=("2024-01-01", "2024-12-31"), previous_period_end="2023-12-31"),
               "2024.pdf")
    assert overview(client, cooperative_id)["maintenance"][0]["answer"] == "yes"


def test_answers_go_with_their_cooperative(client):
    cooperative_id = add_cooperative(client)
    answer(client, cooperative_id, "stambyte", "yes")
    client.delete(f"/api/cooperatives/{cooperative_id}")
    again = add_cooperative(client)  # Same report again: a new cooperative without old answers.
    assert overview(client, again)["maintenance"][0]["answer"] is None


def test_answers_are_kept_by_export_and_import(client):
    cooperative_id = add_cooperative(client)
    answer(client, cooperative_id, "fasad", "no")
    backup = export(client)
    answer(client, cooperative_id, "fasad", "yes")
    assert import_(client, backup).status_code == 204
    [cooperative] = client.get("/api/cooperatives").json()
    assert overview(client, cooperative["id"])["maintenance"][2]["answer"] == "no"
