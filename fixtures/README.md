# Shared fixtures

All JSON files are UTF-8 synthetic examples. Seed wording/weights/scales come from checklist PDF pp. 1–2. No real DEV records or organizer URL are included.

| File | Purpose |
|---|---|
| checklist.json | Exact ChecklistVersion v1; editable configuration seed |
| conversation.json | Transcript with stable message IDs, source timestamps and system context |
| upload-request.json | Exact POST /conversations JSON request |
| organizer-response.json | Documented external dataset envelope, group DEMO |
| evaluation-original.json | Successful result, N/A, omitted-action range, 92.31 total |
| evaluation-reviewed.json | Original preserved, resolved appeal/decision and final 100 total |
| evaluation-failed.json | Provider timeout; both results null, never zero |
| error.json | Normalized 422 invalid_judgment response |

Original and reviewed represent successive snapshots of eval_demo. Failed is a separate attempt. No audio is supplied; call UI should use a provided audio_url from future imported call records. Range links are inclusive message IDs. Review example is illustrative, not a gold-standard interpretation of this invented chat.

For loading/failed states, check status before accessing result. For a successful result check total for null separately from zero. For numeric criteria render only allowed scale values. For N/A hide points and display its rationale. Show original and final results alongside the reviewer decision; do not overwrite original.
