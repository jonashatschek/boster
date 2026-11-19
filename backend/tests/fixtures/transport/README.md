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
