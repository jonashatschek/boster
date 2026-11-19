from datetime import date

import pytest

from app.listings.text_extraction import extract_from_text
from app.services.properties import normalize_cooperative_name
from tests.listing_samples import AGENT_STYLE, BOOLI_STYLE, HEMNET_STYLE


def values(facts):
    return {name: extracted.value for name, extracted in facts.fields.items()}


def test_hemnet_layout_with_labels_and_values_on_separate_lines():
    facts = values(extract_from_text(HEMNET_STYLE))
    assert facts["address"] == "Ringvägen 12, 3 tr"
    assert facts["neighborhood"] == "Södermalm"
    assert facts["municipality"] == "Stockholms kommun"
    assert facts["asking_price"] == 4_250_000
    assert facts["rooms"] == 2
    assert facts["living_area"] == 54.5
    assert facts["balcony"] is True
    assert facts["floor"] == "3 av 5, hiss finns"
    assert facts["elevator"] is True
    assert facts["construction_year"] == 1929
    assert facts["cooperative_name"] == "BRF Segelflygaren"
    assert facts["monthly_fee"] == 3_245
    assert facts["energy_class"] == "D"


def test_unlabelled_hemnet_price_is_noted_as_interpreted():
    facts = extract_from_text(HEMNET_STYLE)
    assert "Kontrollera" in facts.fields["asking_price"].note


def test_yearly_running_cost_and_price_per_sqm_are_not_mistaken_for_fee_or_price():
    facts = values(extract_from_text(HEMNET_STYLE))
    assert facts["monthly_fee"] == 3_245  # Not "Driftkostnad 4 800 kr/år".
    assert facts["asking_price"] == 4_250_000  # Not "Pris/m² 77 982 kr/m²".


def test_booli_layout_on_one_line():
    facts = values(extract_from_text(BOOLI_STYLE))
    assert facts["asking_price"] == 3_950_000
    assert facts["living_area"] == 41
    assert facts["rooms"] == 1.5
    assert facts["monthly_fee"] == 2_410
    assert facts["floor"] == "1 tr"
    assert facts["cooperative_name"] == "Brf Byamännen 2"
    assert facts["elevator"] is False
    assert facts["balcony"] is False
    assert facts["listing_date"] == date(2025, 10, 12)


def test_agent_layout_with_colons():
    facts = values(extract_from_text(AGENT_STYLE))
    assert facts["address"] == "Storgatan 3A"
    assert facts["neighborhood"] == "Bagarmossen"
    assert facts["asking_price"] == 2_995_000
    assert facts["rooms"] == 3
    assert facts["living_area"] == 71
    assert facts["balcony"] is True  # "Uteplats i söderläge" states that there is one.
    assert facts["balcony_description"] == "Uteplats i söderläge"
    assert facts["monthly_fee"] == 4_102
    assert facts["fee_includes"] == "värme, vatten, bredband"
    assert facts["construction_year"] == 1953
    assert facts["energy_class"] == "C"


def test_features_are_not_inferred_when_not_stated():
    facts = values(extract_from_text(AGENT_STYLE))
    assert "elevator" not in facts  # Ground floor says nothing about an elevator.


def test_description_is_the_agents_prose():
    facts = values(extract_from_text(HEMNET_STYLE))
    assert facts["description"].startswith("Välkommen till denna ljusa")


def test_every_value_keeps_its_evidence():
    for extracted in extract_from_text(HEMNET_STYLE).fields.values():
        assert extracted.excerpt
        assert extracted.method


def test_prose_starting_with_a_label_word_is_not_a_label():
    facts = values(extract_from_text("Föreningen har nyligen bytt stammar och renoverat tvättstugan i källaren.\n"))
    assert "cooperative_name" not in facts


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("HSB Bostadsrättsförening Segelflygaren i Stockholm", "segelflygaren"),
        ("BRF Segelflygaren", "segelflygaren"),
        ("Brf Byamännen 2", "byamännen 2"),
        ("Brf Byamännen", "byamännen"),
        ("Bostadsrättsförening Friheten Bagarmossen", "friheten bagarmossen"),
    ],
)
def test_cooperative_name_normalization_keeps_distinguishing_words(name, normalized):
    assert normalize_cooperative_name(name) == normalized


# --- Real listings for the same apartment on Booli and Hemnet -----------------------------

from tests.real_listings import AGENT_PILOTGATAN, BOOLI_RUSTHALLARVAGEN, HEMNET_RUSTHALLARVAGEN  # noqa: E402

SAME_FACTS = {
    "address": "Rusthållarvägen 151",
    "neighborhood": "Bagarmossen",
    "asking_price": 1_650_000,
    "living_area": 27,
    "rooms": 1,
    "monthly_fee": 3_348,
    "construction_year": 1954,
    "cooperative_name": "BRF Gästfriheten",
}


@pytest.mark.parametrize("text", [BOOLI_RUSTHALLARVAGEN, HEMNET_RUSTHALLARVAGEN], ids=["booli", "hemnet"])
def test_real_listings_give_the_same_facts(text):
    facts = values(extract_from_text(text))
    for name, expected in SAME_FACTS.items():
        assert facts[name] == expected, name


def test_booli_sentences_and_location_line():
    facts = values(extract_from_text(BOOLI_RUSTHALLARVAGEN))
    assert facts["floor"] == "3 av 3"  # "Den ligger på våning 3 av 3".
    assert facts["municipality"] == "Stockholm"  # "Lägenhet · Bagarmossen · Stockholm".
    assert "description" not in facts  # Booli's pasted text has no agent description.


def test_hemnet_no_elevator_is_not_read_as_elevator():
    facts = values(extract_from_text(HEMNET_RUSTHALLARVAGEN))
    assert facts["floor"] == "3 av 3, hiss finns ej"
    assert facts["elevator"] is False


def test_hemnet_description_starts_at_the_first_sentence_and_keeps_paragraphs():
    description = values(extract_from_text(HEMNET_RUSTHALLARVAGEN))["description"]
    assert description.startswith("Välkommen till en ljus")
    assert "Tunnelbanan ligger" in description
    assert "\n\n" in description


def test_french_balcony_in_description_is_not_a_balcony():
    assert "balcony" not in values(extract_from_text(HEMNET_RUSTHALLARVAGEN))


def test_fee_includes_from_sentence():
    facts = values(extract_from_text(HEMNET_RUSTHALLARVAGEN))
    assert facts["fee_includes"].startswith("värme, vatten samt bredband")


def test_contact_label_is_not_taken_as_address():
    facts = values(extract_from_text("Adress:\nMobil:\nE-post:\n"))
    assert "address" not in facts


def test_planned_fee_changes():
    text = "Kommande avgiftsförändringar:\nUnder 2026 höjs avgiften med 10 procent och under 2027 med 5 procent.\n"
    assert values(extract_from_text(text))["fee_changes"].startswith("Under 2026 höjs avgiften med 10 procent")


def test_cooperative_name_from_link_text_is_trimmed():
    facts = extract_from_text("Dokument\nBrf Gästfriheten - Årsredovisning 2024\nStadgar\n")
    assert facts.fields["cooperative_name"].value == "Brf Gästfriheten"
    assert "Kontrollera" in facts.fields["cooperative_name"].note


@pytest.mark.parametrize("line", [
    "Rusthållarvägen 151 lgh 1102",  # Flat number without a comma.
    "Ringvägen 12 3 tr",  # Floor without a comma.
    "Götgatan 8 nb",
    "Sveavägen 40 2 vån",
    "Kungsholms Strand 5",  # Street word with a capital letter.
    "RINGVÄGEN 12",  # All capitals.
    "Tegnérlunden 4",
    "Medborgarplatsen 3",
    "Rålambshovsparken 2",
    "Danvikshöjden 7",
    "Storgatan 3 A",  # House letter after a space.
])
def test_more_address_forms(line):
    facts = values(extract_from_text(f"{line}\nSödermalm, Stockholms kommun\nPris\n1 000 000 kr\n"))
    assert facts["address"] == line


@pytest.mark.parametrize("line", [
    "Ringvägen 12 rum och kök",  # Words after the number that are not a floor or flat.
    "Parkeringsplats 2",  # Not a street word.
    "ringvägen 12",  # A street name starts with a capital letter.
])
def test_lines_that_are_not_addresses(line):
    facts = values(extract_from_text(f"{line}\nSödermalm, Stockholms kommun\nPris\n1 000 000 kr\n"))
    assert "address" not in facts


def test_address_after_a_long_menu_and_image_captions():
    # HusmanHagberg: the address comes after about 75 lines of menu and image captions.
    facts = values(extract_from_text(AGENT_PILOTGATAN))
    assert facts["address"] == "Pilotgatan 16, 1tr"


def test_address_is_never_taken_from_other_listings_or_the_footer():
    # Without the listing's own address, "Korphoppsgatan 22" (another listing) and
    # "Nybrogatan 12, 2 tr" (the agency's office) must not be taken instead.
    text = AGENT_PILOTGATAN.replace("Pilotgatan 16, 1tr", "")
    assert "address" not in values(extract_from_text(text))
