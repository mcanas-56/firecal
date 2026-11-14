# FireCal rough demo

A standalone concept, separate from the FireCal repository. No dependencies to install.

Run from this folder:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Open http://localhost:8765. Globe rendering and Natural Earth coastlines are bundled locally; internet access is used only for optional web fonts. The archive JSON must be served over HTTP rather than opening the HTML directly.

Features: animated risk bar with pause control, Home/Report navigation, dark/light theme, draggable and zoomable globe with date slider and playback, region and historical date controls, hotspot details, optional geolocation, automatic editable observation time, photo preview, reporter fields, and a local report receipt/map marker.

Live hotspots and all risk levels are **simulated**. The archive uses real NASA FIRMS VIIRS S-NPP 2023 Canada/Argentina practice CSVs, covering January 1–December 31, type 0, confidence n/h. Up to 60 points per day/area are deterministically sampled for rendering; counts describe the full filtered day. Globe marker colours describe radiative power, not danger or burned area. A live feed, verified risk model, report backend, moderation and emergency-service integration are outside this demo.

Report contacts and photos are never transmitted or saved to disk. Only location, observation type/time and generated ID are retained in the tab's memory for demo markers; reload clears them. Optional geolocation sends no coordinates to a reporting backend. Fonts load from Google Fonts; geographic rendering stays local. Theme preference alone is saved in localStorage. Use fictional reporter information for demos.

The globe uses bundled D3 v7 (ISC license, copyright Mike Bostock) and Natural Earth public-domain land geometry. Drag to rotate, zoom with the buttons or wheel, and move the timeline slider or play the daily observations. Slider and calendar are synchronized.

The daily heatmap uses full filtered daily counts (not the rendered sample), grouped into nonzero activity quartiles per area/year. Zero detections and absent coverage have separate colours. This is an activity/severity proxy, not a danger rating. The date scale selects individual days, Monday–Sunday weeks clipped at the year boundary, or calendar months. Weekly/monthly counts sum their daily counts, with at most 300 sampled markers shown on the globe. Calendar cells always retain their daily colour and highlight the selected period. The complete 2023 yearly source archives establish coverage, so days without rows are recorded as zero detections; this does not prove no fire occurred.


Latest layout: calendar appears first; click its year control to select 2022 or 2023 (both complete yearly practice archives). Time Explorer scale buttons sit directly above the slider. Heatmap thresholds are recomputed for the selected area/year. Clicking a calendar day forces daily view and immediately reveals the globe.
