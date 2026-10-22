import pytest

from app.domain.provenance import VerificationStatus
from app.domain.resolution import Observation, resolve


def observation(value, status=VerificationStatus.EXTRACTED, observation_id=None, metric="residential_area", year=2025):
    return Observation(metric, year, value, status, observation_id)


def test_single_observation_is_used_as_is():
    result = resolve([observation(15_575)])
    assert result.value == 15_575
    assert result.status == VerificationStatus.EXTRACTED


def test_agreeing_sources_are_combined_and_the_first_is_shown():
    # A newer report restating the same figure, rounded differently.
    result = resolve([observation(-2_802_579, observation_id=2), observation(-2_802_580, observation_id=1)])
    assert result.value == -2_802_579
    assert result.status == VerificationStatus.EXTRACTED
    assert len(result.candidates) == 2


def test_conflicting_sources_keep_all_candidates_and_choose_none():
    # Brf Söderbysjön's report gives two different residential areas.
    result = resolve([observation(26_688, observation_id=1), observation(21_311, observation_id=2)])
    assert result.value is None
    assert result.status == VerificationStatus.CONFLICTING
    assert [c.value for c in result.candidates] == [26_688, 21_311]
    assert "olika värden" in result.note


def test_user_value_resolves_a_conflict():
    result = resolve([
        observation(26_688, observation_id=1),
        observation(21_311, observation_id=2),
        observation(21_311, VerificationStatus.USER_ENTERED, observation_id=3),
    ])
    assert result.value == 21_311
    assert result.status == VerificationStatus.USER_ENTERED
    assert result.note is not None  # The disagreeing extracted value is mentioned.


def test_latest_user_value_wins():
    result = resolve([
        observation(100, VerificationStatus.USER_ENTERED, observation_id=5),
        observation(200, VerificationStatus.USER_ENTERED, observation_id=9),
    ])
    assert result.value == 200


def test_verified_counts_as_a_user_decision():
    result = resolve([observation(15_575, observation_id=1), observation(15_575, VerificationStatus.VERIFIED, 2)])
    assert result.status == VerificationStatus.VERIFIED
    assert result.note is None


def test_rejects_mixed_metrics():
    with pytest.raises(ValueError):
        resolve([observation(1, metric="cash"), observation(1, metric="equity")])


def test_rejects_empty_input():
    with pytest.raises(ValueError):
        resolve([])
