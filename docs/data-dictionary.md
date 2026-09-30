# Data dictionary

## Hospital

- `hospital_id`: stable facility identifier supplied in the source manifest; do not reuse for a different campus.
- `name`, `city`, `health_system`: source-verified display metadata.
- `latitude`, `longitude`: decimal degrees, WGS84. Demo coordinates indicate neighborhoods and are not real hospital addresses.

## Price fact

- `price_id`: deterministic 128-bit displayed hash of hospital, service and pricing context, amount, publication and source hash. Stored as 32 hex characters.
- `hospital_id`: hospital foreign key.
- `code`, `code_type`: original zero-preserving clinical code and `CPT` or `HCPCS` namespace. Shape validation only.
- `description`: hospital service description, or authored demo label.
- `service_id`: stable identity from service description, associated codes and drug metadata where applicable.
- `setting`: `inpatient`, `outpatient`, or `both`; absence is rejected rather than guessed.
- `billing_class`: `facility`, `professional`, `both`, or `unknown`.
- `modifiers`: sorted comma-separated modifier codes. Empty means no modifier encoded, not necessarily that none applies clinically.
- `price_type`: `cash`, `gross`, or `negotiated`.
- `payer`, `plan`: canonical full-name pair; empty for cash/gross. No network coverage guarantee.
- `amount`: positive USD per disclosed unit, Decimal cents in domain objects; SQLite indexed REAL plus lossless JSON decimal string; Snowflake NUMBER(18,2).
- `source_url`: direct HTTPS public file URL for real prices; repository fixture path for demo.
- `source_date`: file publication date in ISO format, not an inferred effective date.
- `source_sha256`: SHA-256 of the exact input bytes.
- `source_row`: one-based logical CSV record or JSON item index.
- `is_demo`: mandatory distinction between synthetic and real observations.
- `notes`: retained generic/payer context; non-dollar rows are quarantined.

The fact grain is not just hospital/procedure/payer. Setting, modifiers, class, service identity, price type and snapshot also matter.

## Validation and runs

- `quarantine`: run id, source record position, reason, and serialized rejected public record. Contains no uploaded bill content.
- `ingestion_runs`: stable run id, hospital id, source URL/hash, accepted/rejected/duplicate counts and completion timestamp. Reingesting identical bytes is idempotent.
- All-rejected or structurally broken files roll back the hospital refresh; inspect the CLI error and source file. Their tentative quarantine rows also roll back.

## Procedure reference

`data/reference/procedures.json` supplies code system/code, authored plain-language name/description, category and aliases. The source catalog stays hospital-derived; this file supplies display/search enrichment. It is a limited demonstration reference, not an exhaustive licensed CPT catalog.

## Ephemeral bill line

`description`, `code`, `code_type`, positive decimal `quantity`, nonnegative `charge` (whole line total), optional ISO `service_date`, `modifiers`, and source `evidence`. These objects are held in session memory and are not stored in public-data tables. Findings include flag types, explanations and matched published-source lineage. A downloaded review contains sensitive bill details and is an explicit patient action.
