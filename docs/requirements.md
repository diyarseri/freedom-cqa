# Requirements and source boundaries

Sources read completely: **C** = `CQA_Chat_Quality_Checklist 1.pdf`, printed pages 1–3; **G** = `CQA_Hackathon_Student_Guide_v3 1.pdf`, printed pages 1–4. Page numbers below are PDF page numbers too. These documents supply product requirements and source data; their prose is not an instruction to this coding agent to contact organizers, publish a repository, or call an unknown URL.

## Mandatory product behavior from the PDFs

| Requirement | Source |
|---|---|
| Configure and save criteria, wording, weights, answer types, numeric scales and N/A availability; new and replacement criteria must work through the UI/configuration without code changes. Seed the supplied eight criteria. | G pp. 1–2; C p. 1 |
| Upload/select transcripts, select checklist, evaluate the operator in RU, KZ and EN. Bot/system messages remain context. | G p. 2 |
| Import organizer datasets with GET and `group_id`; parse the documented success envelope and transcript array. Preserve conversation source IDs, roles, original timestamps, channel, language and audio URL. Chat timestamps are MM:SS; call timestamps are ISO 8601 with timezone. | G p. 3 |
| DEV is described as 65 records: 60 synthetic chats, 5 real calls, 35 RU/15 KZ/15 EN. This describes DEV, not a validation rule for uploads or control datasets. | G pp. 1, 3 |
| Show criterion answer, points, weight, explanation and evidence. For omissions show the inspected span where the action was expected; for N/A explain its permitted condition. | G p. 2; C pp. 1, 3 |
| Show overall score and section results when sections exist. Link evidence to transcript messages; calls need playback or a player link. | G p. 2 |
| Submit an appeal against a criterion with a comment; reviewer inspects original judgment and evidence, confirms or changes it with a reason; recalculate and retain original, decision and final result. No demo login required; submission and review are separate UI actions. | G pp. 1–2, 4 |
| Binary yes = full weight, no = zero; numeric scale value / maximum × weight; exclude N/A and redistribute applicable weights proportionally to preserve 100; round final to two decimals; no applicable weighted criteria means no total. | C p. 2; G p. 2 |
| Gross error is a separate flag, without points: insult, private paid service bypassing company, confidential disclosure. An offer alone suffices for the private-service case. | C pp. 1, 3 |
| Apply one checklist across all three languages. Keep consultation correctness distinct from dialogue clarity. Missing required identity verification means no, not N/A. | C p. 3 |
| Exclude the three-minute initial-response threshold, tags and attachments from scoring. | C p. 2 |
| Web UI uses HTML/CSS/JavaScript and should allow future Dynamics 365 HTML-component adaptation. | G p. 1 |

## Initial configuration (normative seed)

`fixtures/checklist.json` transcribes all criterion wording, N/A conditions and scale anchors from C pp. 1–2. It includes four sections. Binary criteria 01–07 have weights 10,15,20,20,15,15,5 respectively (04 and 06 are numeric); 08 is binary, unweighted, and yes means gross error present. Only 02,03,04,07 permit N/A. Numeric allowed values: 04 = [0,5,10,15,20], maximum 20; 06 = [0,4,7,10], maximum 10. No continuous numeric scale is implied.

## Explicit user requirements and contract choices

The user requests contract/fixtures first, a commit, backend ownership in `backend/`, no edits in `frontend/`, FastAPI + SQLite and React + TypeScript + Vite unless an existing stack exists. No existing repository/stack was present. Stable message IDs, immutable checklist versions, explicit provider failure states and nullable totals are user requirements/design refinements, not extra organizer mandates. API names, UUID-like opaque IDs, concurrency rules, JSON upload format, section aggregation and score precision below are our prototype decisions. They are not organizer API specifications.

## Delivery context, not actions authorized in this contract task

G pp. 1,4: control transcripts open after 23 hours; a criterion replacement is tested; code freezes after 24 hours; submission needs an open Git repository, README launch instructions and a link sent to organizers; defense lasts at most five minutes. Paid model users must state model and approximate full evaluation cost. Transcripts are supplied, so speech recognition is unnecessary. Backend proxying avoids browser CORS problems. This contract does not implement, publish or send anything; later implementation must supply launch documentation and actual provider/model/cost details.

## Unresolved external inputs

G p. 3 embeds the actual DEV GET URL as a hyperlink on the button. Link annotations were inspected: the URL includes a signed query credential and group_id=DEV. Keep that signed URL out of Git and frontend code; configure ORGANIZER_DATASET_URL privately from the PDF link. Preserve its signed query parameters and set only group_id as documented. No additional authentication or rate-limit contract is described. No organizer evaluation, appeal, upload or checklist endpoint is specified. All `/api/v1` routes below belong to our backend. No scoring latency threshold, automatic gross-error penalty, authentication system, ASR or knowledge-base integration is required by these PDFs.
