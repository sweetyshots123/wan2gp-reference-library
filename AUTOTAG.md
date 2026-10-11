# Auto-tagger (1.5.0)

Select images in the browser, click **Autoetiquetar / Auto-tag** (Ctrl+A first = all matching images). A background
job tags them with a local model; then the search box finds them by any tag, its synonyms (EN/ES) and its parent /
child terms ("arena" → hourglass, "curvilínea" → hourglass + pear…, "pelo corto"), and the **Auto tags** panel in
the sidebar filters by category with counts. Adults only: see *Safety*.

## Taxonomy

`reflib_core/taxonomy.json` — 396 nodes: 9 categories, 52 groups, 335 tags, 744 synonyms, every node in EN and ES.

| Category | Groups |
|---|---|
| Framing & camera | shot (ordinal: extreme close-up → wide), camera angle, image orientation |
| Pose | body pose (standing, contrapposto, sitting…, lying…, kneeling, walking…), body orientation, arms / hands |
| Clothing | coverage (clothed, partially clothed, implied nude, nude…), tops, bottoms, dresses, swimwear, lingerie, outerwear, footwear, accessories, main colour, pattern, fit |
| Hair | length (ordinal), colour, style, texture |
| Body | body type (slim, petite, athletic, muscular, average, curvy → hourglass / pear, apple, inverted triangle, rectangle, plus-size), height, bust, hips, **waist definition, overall build (very slim → plus-size), curvature, muscle tone, leg shape, thigh shape, inner-thigh gap (none / slight / moderate / wide), torso-leg proportion, measurement status**, skin tone (6-step neutral scale), apparent age (adult bands only), tattoos & piercings |
| Face & expression | expression, gaze, makeup, lips, eyewear |
| Setting | indoor/outdoor, location (bedroom, beach, studio, street…), lighting, background |
| Photo style | style (studio, selfie, mirror selfie, candid, professional, AI-generated look…), medium, colour grade, people count |
| Review | `appears_minor`, `needs_review` |

Exclusive groups take one label; multi-label groups several. Body wording is neutral ("full build", "wide hips").

## Safety

Every backend also estimates whether the person may be under 18. If so (≥ 0.2), the image keeps only non-body,
non-nudity tags, gets `appears_minor` + `needs_review`, no body measurements are taken, and the preview shows a
review banner. There are no tags describing minors. The body-shape pass runs only after this gate.

## Body shape (estimates)

`reflib_core/bodyshape.py`. A person silhouette (BiRefNet, MIT) and 17 keypoints (ViTPose-B, Apache-2.0) give the
silhouette **widths** at shoulder, bust, underbust, waist (narrowest), high hip, hip (widest), mid-thigh and knee,
plus the inner-thigh gap, normalised by torso height, and torso / leg / arm lengths as fractions of height. Arms are
removed from the silhouette using the keypoints. From these: waist/hip, waist/bust, shoulder/hip, bust/hip,
thigh/hip, thigh/knee and gap/hip ratios, waist-definition and curvature scores, and the shape tags (hourglass, pear,
inverted triangle, rectangle, apple; waist very defined / defined / straight; hips narrow / medium / wide; build;
thigh shape and gap; leg length; torso/leg proportion), each with a confidence.

Only **front or near-front, standing, half- or full-body** images are measured; anything else is stored as
"not measurable" with the reason (side view, sitting, legs hidden; thighs under a skirt or dress).

**Circumferences are estimates.** One 2D photo has no absolute scale and no depth: each width becomes an ellipse with
a typical adult depth/width ratio (or the measured depth when a side view of the same person is combined), scaled by
an assumed adult height of 165 cm ± 7 (or the height you enter, per image or for a whole collection). They are stored
as `[estimate, low, high]` with the uncertainty (about ±10 % with an assumed height, ±5–6 % with a known height and
a side view); clothing, posture and lens distortion move them further. The UI labels them **estimado** and never as
exact values. With a VLM in the pipeline (Qwen2.5-VL), it gives its own bust/waist/hip estimate and shape; the
two are combined (geometry weighted 2:1), the band widens when they disagree, and agreement is shown per value.

Search: `cintura<65`, `cadera 90-100`, `muslo>=50`, `altura>170`, `90-60-90 ±5` (bust-waist-hip, ±3 if omitted),
`ratio cintura/cadera<0.72`, `ratio muslo/rodilla>1.5`, `cadera:media`, `cintura:muy_marcada` (field:value tag
terms). English field names work too (waist, hip, bust, thigh, height…). The sidebar has range filters for the main
values.

## Backends and the pick

All local options were checked against WanGP's own stack (torch 2.10 / CUDA 13.0 wheels, which include Blackwell
sm_120; transformers **4.54.0** pinned; onnxruntime-gpu present).

| Model | Licence | Download | Fits WanGP venv | Strengths / weaknesses for this taxonomy |
|---|---|---|---|---|
| WD-EVA02-Large tagger v3 | Apache-2.0 | 1.26 GB (ONNX) | yes | Fast (~1 s/img CPU, ms on GPU), NSFW-tolerant, good for garments, hair, pose, framing, coverage. No real body-shape vocabulary; booru terms mapped to the taxonomy. Correctly said "no people" on our synthetic figures. |
| JoyTag | Apache-2.0 | 0.73 GB | yes | Similar to WD, smaller tag set; WD-EVA02 is more accurate. |
| SigLIP2 so400m zero-shot | Apache-2.0 | 4.5 GB | yes | Open vocabulary, EN prompts; weak and poorly calibrated on fine attributes. |
| **Jev / jevimage 0.1.20** | MIT | 0.4–4.5 GB (SigLIP2 encoder) | **client yes; `[local]` no** (needs transformers ≥ 4.56) | One encode, the whole taxonomy as typed questions, deterministic, calibrated confidences; trainable linear heads. Same zero-shot limits as SigLIP2 on fine attributes (see eval). |
| Florence-2-large | MIT | 3.1 GB | yes (remote code) | Captions / detection; no structured attributes, weak on body/clothing detail. |
| **Qwen2.5-VL-7B-Instruct** | Apache-2.0 | 16.6 GB (bf16) | yes (≥ 4.49) | Best fine-grained reading (body type, coverage, pose, fit, style) with JSON constrained to the taxonomy; describes nudity neutrally; ~1–2 s/img on a 5090. |
| Qwen3-VL-8B | Apache-2.0 | ~17 GB | no (needs transformers ≥ 4.57) | Stronger, but would require upgrading WanGP's transformers. |
| InternVL3-8B / MiniCPM-V 2.6 | MIT+Qwen / MiniCPM licence | ~16 GB | partly (remote code) | Comparable; MiniCPM's licence is not Apache/MIT. |
| JoyCaption Beta One | Llama 3.1 community | 17 GB | yes | Best NSFW captions, but free text and a non-Apache licence. |
| ViTPose-B + BiRefNet (body shape) | Apache-2.0 + MIT | 0.34 + 0.44 GB | yes (+ `kornia`) | Geometry for the body-shape groups and measurements. |

**Default pipeline: `wd+qwen` + body shape.** WD-EVA02 does the broad pass (garments, hair, pose, framing, coverage,
setting); Qwen2.5-VL-7B re-reads the fine groups with a JSON schema; the geometry pass decides the body-shape
groups and measurements (it wins over the zero-shot/VLM guesses for its own groups); Qwen cross-checks the
measurements. Per-group thresholds are in the settings. VRAM: Qwen bf16 ~17 GB + WD ~1.5 GB + body 1 GB, inside
the 24 GB default cap on the 32 GB card; the job never runs while WanGP generates and unloads everything when it
yields, when idle (2 min) or with **Liberar GPU**.

**Jev.** Implemented as a backend (`jev`, `jev+qwen`): exclusive groups → `choice`, ordinal groups (shot, hair length,
height, bust, hips, skin tone, age band) → `score`, multi-label tags → `noul` contrast pairs, groups with a trained
head → `head`; descriptive English captions generated from the taxonomy; 179 questions in 3 asks of ≤ 64 per image
(one encode). Heads can be trained later from your accepted tags (`AutoTagService.training_examples()` →
`JevBackend.train_heads`, ≥ 8 images per class). Measured on the box with the real package (CPU,
siglip2-base-224, benign synthetic images): the question set is accepted as generated; 0.2 s/image after the first
(caption cache); but zero-shot answered person attributes with high confidence (e.g. "three-quarter body 0.9",
"straight hair 0.8") on images with no person, and the adult/minor choice leaned "minor" on drawings, while WD said
"no people". So the backend adds a person-present question that drops person tags when no real person is seen.
Recommendation: use Jev as a fast first pass or with trained heads, not alone for the fine groups: keep the VLM for
body type, coverage, fit and pose detail. Because `jevimage[local]` needs transformers ≥ 4.56, run it as a sidecar:
`python -m venv jev && jev\Scripts\pip install "jevimage[serve]==0.1.20"` then `jevimage serve` and set the
**Jev server URL** (the WanGP side only needs `pip install jevimage==0.1.20`, which pulls just Pillow). Visual Jev
(Qwen3-VL backbone, arXiv 2609.25845) was not tested: no weights were checked here.

## Paid cloud backends (1.5.3)

See README → "Paid cloud models (1.5.3)": `reflib_core/cloud.py` (Gemini 3.8 Flash, GPT-6.1 Sol, Claude Opus/Sonnet 5.5), gate in `jobs.TagQueue._cloud_preds`.

## Cloud backends (off by default)

OpenAI-compatible (`/chat/completions` + `response_format: json_schema`; also vLLM / LM Studio), Google Gemini
(`responseSchema`), xAI Grok (OpenAI-compatible), and OpenRouter:

* **(a) Jev Router** — `typesafe/jev-router` with the image and a strict JSON schema derived from the taxonomy. It
  routes to another model per request, so price and behaviour vary; the real cost comes from `usage.cost`.
* **(b) Cascade (recommended of the two)** — a local describer (Qwen2.5-VL, or WD) turns the image into a neutral
  text description; `typesafe/jev-1.13` (Decisions API, `POST /api/alpha/decisions`, text-only, $0.042 per M input
  tokens, output free) answers the taxonomy as typed decisions (choice / noul / score, ≤ 64 per request). The image
  never leaves the PC; about 15 k input tokens per image (the questions dominate) ≈ $0.0006 per image, ~$0.62 per 1,000. Pinned to `jev-1.13`; option for
  `~typesafe/jev-latest`.

Cloud needs **Allow cloud** in the settings; the size / cost estimate is shown before the job starts and the running
cost is in the job bar. Keys come from `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY` (or
`REFLIB_*` variants) or the settings; they are never logged or sent back to the page. Some services filter nudity:
a refusal, a safety block or an empty answer falls back to the local backend for that image.

## Install on the PC (WanGP's own venv)

```
cd Wan2GP
venv\Scripts\activate                      (or your env)
pip install kornia                         # body shape (BiRefNet); everything else is already in WanGP
pip install jevimage==0.1.20               # optional: only to use a Jev server
```

Models download on first use into `plugins/wan2gp-reference-library/models/` (the browser asks first and shows
the size): WD-EVA02 1.3 GB, Qwen2.5-VL-7B 16.6 GB, ViTPose 0.34 GB, BiRefNet 0.44 GB (≈ 18.7 GB for the default).
To pre-download: `huggingface-cli download SmilingWolf/wd-eva02-large-tagger-v3 model.onnx selected_tags.csv
--cache-dir plugins/wan2gp-reference-library/models` (same for the others). Then tick **Offline** in the settings.
