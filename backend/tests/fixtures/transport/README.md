# Transport fixtures

Recorded on 2026-11-19 for the public address Ringvägen 12, Stockholm (and Drottninggatan 1 for a street-level match).

- `nominatim_house.json`, `nominatim_street_only.json`, `nominatim_not_found.json`: real responses from
  `nominatim.openstreetmap.org/search` with a structured query (`street`, `city`, `countrycodes=se`, `format=jsonv2`).
- `valhalla_matrix.json`, `valhalla_error.json`: real responses from `valhalla1.openstreetmap.de/sources_to_targets`
  (pedestrian), from Ringvägen 12 to Zinkensdamm and Stockholms södra.
- `resrobot_nearbystops_recorded.json`: a real response from ResRobot v2.1 `location.nearbystops` (`r=2000`,
  `maxNo=1000`) for Ringvägen 12. It doesn't contain the key.
- `resrobot_nearbystops.json`: **constructed**, not recorded (no key was available). It follows the documented
  ResRobot v2.1 `location.nearbystops` format. Station names, positions and product classes are real (positions
  from OpenStreetMap); `extId`, `weight` and `requestId` are placeholders, and `dist` is the straight-line distance.
  It keeps the API tests small and in step with `valhalla_matrix.json`; the recorded file checks the real format.

Address choice (#21), recorded 2026-11-19 from the same Nominatim search with `accept-language=sv`:

- `nominatim_choice_pilotgatan.json`: `street=Pilotgatan 16`, no city, `limit=10`. Two hits: Stockholms kommun and Uppsala kommun.
- `nominatim_choice_storgatan.json`: `street=Storgatan 3`, no city, `limit=10`. Ten hits (the cap), with duplicates.
- `nominatim_choice_parkvagen_wrong_municipality.json`: `street=Parkvägen 3&city=Stockholms kommun`, `limit=5`. Shows that
  `city` does not filter: the hits are in Solna, Sundbyberg, Haninge and Nacka, none in Stockholm.
- `nominatim_choice_umea_letters.json`: `street=Storgatan 1&city=Umeå kommun`, `limit=5`. Only 1A, 1b and 1c (different
  house numbers) and street-level hits.
