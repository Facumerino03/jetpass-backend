# Flight Plan Design

## Context

JetPass backend currently uses FastAPI, Pydantic v2, SQLAlchemy async, repositories, services, routes, schemas, and async tests. The flight-plan module will follow that structure rather than a NestJS structure.

Existing domain pieces:

- `app/models/user.py` already defines `User` and `Role`.
- `app/models/aircraft.py` already defines `Aircraft` and `WakeTurbulenceCat`.
- Pilots already manage aircraft through `/pilot/aircraft`.
- `docs/class-diagram.puml` already defines the intended high-level domain for profiles, aircraft, and flight plans.

The flight-plan flow follows the pilot wizard in `docs/TLJ1Zjis5BpxAnvoie455jkYHM0V6iNLDafiov2zHZVeXPQU7HOKgPAKaA3eL_GxzfHRBmNg7-kGZW1xenmea_HmE3CUwvNpmlgsLYCllMAwNpoypMbUfCayE_szelKYMT7FAUqUqaLEutMsoBVvP3IAnqQZ1a_ffT7qOfriShgRKhgWNPQyJL_GdoEYwUlMbSAIO7lwN5bJ6wgOd52o4jGOIoMsvT5GDazoCgHDlRSy2oSpVRJiS3RD.png`.

## Scope

Implement a wizard-backed MVP for ICAO/ANAC flight-plan creation and manual approval.

In scope:

- Create a `draft` flight plan with Step 1 complete: departure, EOBT UTC, destination, alternate 1, and alternate 2.
- Complete later wizard steps through `PATCH` while the plan remains `draft`.
- Select an aircraft from the authenticated pilot's active aircraft.
- Copy a flight-plan snapshot from the selected aircraft instead of asking the pilot to re-enter aircraft-derived fields.
- Allow overrides of operational aircraft snapshot fields inside the plan only.
- Validate and submit the complete plan.
- Transition `draft -> filed -> pending_approval` during submit.
- Persist manual approval records for pilot, authority, and destination aerodrome operator.
- Auto-approve the pilot approval during submit.
- Allow manual approve/reject actions by authorized users.
- Store state transition history.
- Provide core endpoints that call `jetpass-intelligence` for real-time assistance without persisting intelligence responses.
- Add profile models needed to authorize approvals.

Out of scope for the MVP:

- `amend` / ICAO `CHG` enroute or post-filing amendments.
- `close` / arrival report / post-landing closure.
- Operational `active` flow.
- Autogeneration of ICAO item 18 indicators.
- Event outbox or real event publishing for blockchain or other modules.
- Local aerodrome catalog in core.
- Persisted `intelligence_context` on flight plans.
- Changing pilot in command away from the authenticated pilot.
- Dynamic configurable approval criteria.

## Architecture

Add the flight-plan feature using the current backend layering:

- Models in `app/models` define persistence.
- Schemas in `app/schemas` define API contracts and request validation.
- Repositories in `app/repositories` contain database operations.
- Services in `app/services` enforce business rules, ownership, state transitions, and approval policy.
- Routes in `app/routes` expose HTTP endpoints.
- Tests in `app/tests` cover repositories, services, routes, and intelligence-client behavior.

Keep `User` and `Aircraft` as existing models. Do not duplicate them. Add relationships only where needed.

## Data Model

### Existing Models To Reuse

`User` from `app/models/user.py` remains the identity and authorization anchor. `Role` controls broad access:

- `pilot`
- `atc_authority`
- `airport_operator`
- `admin`

`Aircraft` from `app/models/aircraft.py` remains the pilot-owned aircraft profile. Flight plans reference it through `aircraft_id` and copy operational snapshot fields from it.

### New `profiles.py`

Create `app/models/profiles.py` with:

- `PilotProfile`
- `AuthorityProfile`
- `AirportOperatorProfile`
- `AuthorityType`

`PilotProfile` fields:

- `id`
- `user_id`
- `license_number`
- `license_type`
- `license_country`
- `license_expiry`
- `signature`
- `created_at`
- `updated_at`

`AuthorityType` values:

- `ARO`
- `AIS`
- `ACC`
- `APP`
- `TWR`
- `EANA`
- `ANAC`

`AuthorityProfile` fields:

- `id`
- `user_id`
- `organization_name`
- `authority_type`
- `aerodrome_icao_code`
- `created_at`
- `updated_at`

`AirportOperatorProfile` fields:

- `id`
- `user_id`
- `organization_name`
- `aerodrome_icao_code`
- `created_at`
- `updated_at`

The MVP uses `AuthorityProfile` and `AirportOperatorProfile` to decide who may approve or reject a plan. `PilotProfile` is included because it is part of the domain and may be needed by later flight-plan presentation features, but pilot in command is derived from `User` in this MVP.

### New `flight_plan.py`

Create `app/models/flight_plan.py` with:

- `FlightPlan`
- `FlightPlanStatus`
- `FlightRules`
- `FlightType`

`FlightRules` values:

- `V`
- `I`
- `Y`
- `Z`

`FlightType` values:

- `G`
- `S`
- `N`
- `M`
- `X`

`FlightPlanStatus` values come from the class diagram:

- `draft`
- `filed`
- `pending_approval`
- `accepted`
- `rejected`
- `active`
- `closed`
- `cancelled`

The MVP actively uses `draft`, `filed`, `pending_approval`, `accepted`, and `rejected`. `cancelled`, `active`, and `closed` remain in the enum for future operational flow.

Core `FlightPlan` fields:

- `id`
- `pilot_user_id`
- `aircraft_id`
- `status`
- `flight_rules`
- `flight_type`
- `departure_aerodrome_icao`
- `departure_eobt_utc`
- `destination_aerodrome_icao`
- `alternate1_aerodrome_icao`
- `alternate2_aerodrome_icao`
- `cruising_speed`
- `cruising_level`
- `route`
- `rule_change_point`
- `total_eet`
- `other_information`
- `endurance`
- `persons_on_board`
- `created_at`
- `updated_at`

Aircraft snapshot fields copied into `FlightPlan`:

- `aircraft_identification_snapshot`
- `aircraft_type_designator_snapshot`
- `wake_turbulence_category_snapshot`
- `equipment_com_nav_snapshot`
- `equipment_surveillance_snapshot`
- `emergency_radio_snapshot`
- `survival_equipment_snapshot`
- `life_jackets_snapshot`
- `dinghies_number_snapshot`
- `dinghies_capacity_snapshot`
- `dinghies_cover_snapshot`
- `dinghies_color_snapshot`
- `color_and_markings_snapshot`
- `aircraft_snapshot_confirmed_at`

The snapshot preserves what was declared on the plan even if the pilot later edits the aircraft profile. Snapshot overrides update only the flight-plan snapshot and never update `Aircraft`.

### New `flight_plan_approval.py`

Create `app/models/flight_plan_approval.py` with:

- `FlightPlanApproval`
- `FlightPlanApprovalActor`
- `FlightPlanApprovalStatus`

Approval actors:

- `pilot`
- `authority`
- `destination_aerodrome_operator`

Approval statuses:

- `pending`
- `approved`
- `rejected`

Approval records contain:

- `id`
- `flight_plan_id`
- `actor`
- `criterion`
- `status`
- `approved_by_user_id`
- `rejected_by_user_id`
- `reason`
- `created_at`
- `updated_at`
- `decided_at`

Submit creates these records:

- `pilot_submission`, actor `pilot`, status `approved`.
- `authority_acceptance`, actor `authority`, status `pending`.
- `destination_aerodrome_acceptance`, actor `destination_aerodrome_operator`, status `pending`.

The table is intentionally simple for MVP but can support more criteria later.

### New `flight_plan_status_history.py`

Create `app/models/flight_plan_status_history.py` with `FlightPlanStatusHistory`.

Fields:

- `id`
- `flight_plan_id`
- `from_status`
- `to_status`
- `updated_by_user_id`
- `reason`
- `created_at`

Every status transition is recorded.

### Existing Model Updates

Modify `User` only to add relationships:

- `pilot_profile`
- `authority_profile`
- `airport_operator_profile`
- `flight_plans`
- approval relationships if useful for ORM navigation

Modify `Aircraft` only to add an optional `flight_plans` relationship if useful. The feature must not change existing aircraft ownership behavior.

Update `app/models/__init__.py` only if needed so tests using `Base.metadata.create_all` discover all models.

## API Design

Add `app/routes/flight_plans.py` with `APIRouter(prefix="/flight-plans", tags=["flight-plans"])`.

### Flight Plan Endpoints

`POST /flight-plans`

Creates a `draft` plan with Step 1 complete.

Required request fields:

- `departure_aerodrome_icao`
- `departure_eobt_utc`
- `destination_aerodrome_icao`
- `alternate1_aerodrome_icao`
- `alternate2_aerodrome_icao`

The authenticated user must be a pilot.

`GET /flight-plans`

Lists flight plans visible to the current user. For MVP, pilots see their own plans, admins see all plans, authorities see plans with pending authority approval that their profile can decide, and airport operators see plans whose destination aerodrome matches their profile.

`GET /flight-plans/{id}`

Returns the plan, aircraft snapshot, status history, and approvals if the current user is allowed to view it.

`PATCH /flight-plans/{id}`

Updates wizard fields only while status is `draft`.

Allowed update groups:

- Step 2 operation fields: `flight_rules`, `flight_type`.
- Step 3 aircraft selection: `aircraft_id`.
- Step 3 aircraft snapshot overrides: operational snapshot fields only.
- Step 4 flight fields: `cruising_speed`, `cruising_level`, `route`, `rule_change_point`, `total_eet`.
- Step 5 day-of-operation fields: `endurance`, `persons_on_board`.
- Step 6 review fields: `other_information`.

If `aircraft_id` changes, core validates that the aircraft is active and owned by the pilot, then regenerates the snapshot from `Aircraft`.

`POST /flight-plans/{id}/submit`

Validates the complete plan, records `draft -> filed`, creates approval records, auto-approves the pilot record, and records `filed -> pending_approval`.

`POST /flight-plans/{id}/approve`

Approves the pending approval that the current user is authorized to decide. `admin` may approve any pending approval as an operational override.

`POST /flight-plans/{id}/reject`

Rejects the pending approval that the current user is authorized to decide. A rejection reason is required. The plan transitions to `rejected`.

The MVP does not include:

- `POST /flight-plans/{id}/amend`
- `POST /flight-plans/{id}/close`
- `GET /flight-plans/{id}/intelligence-context`

### Intelligence Endpoints

Core owns plan-oriented intelligence endpoints so the frontend only communicates with `jetpass-core`.

`POST /flight-plans/intelligence/aerodrome`

Validates ICAO format and calls `POST {INTELLIGENCE_BASE_URL}/intelligence/run` with:

```json
{
  "aerodrome": {
    "icao": "SAEZ",
    "force_refresh": false
  }
}
```

`POST /flight-plans/intelligence/notam`

Validates ICAO format and calls `POST {INTELLIGENCE_BASE_URL}/intelligence/run` with:

```json
{
  "notam": {
    "icao": "SAEZ",
    "force_refresh": false
  }
}
```

`POST /flight-plans/intelligence/run`

Allows a combined aerodrome and NOTAM request using the real `jetpass-intelligence` `OrchestratorRequest` shape.

Core does not persist these responses.

## Validation Rules

### Step 1 Creation

- `departure_aerodrome_icao`, `destination_aerodrome_icao`, `alternate1_aerodrome_icao`, and `alternate2_aerodrome_icao` are required.
- Aerodrome codes are normalized to uppercase.
- Aerodrome codes must have ICAO format: exactly 4 alphanumeric characters.
- Departure, destination, alternate 1, and alternate 2 must all be distinct.
- `departure_eobt_utc` is required and is received from the frontend already converted to UTC.

### Draft Updates

- `PATCH` is allowed only while status is `draft`.
- `flight_rules` must be `V`, `I`, `Y`, or `Z`.
- `flight_type` must be `G`, `S`, `N`, `M`, or `X`.
- Selected `aircraft_id` must belong to the authenticated pilot and must be active.
- Aircraft snapshot overrides must not update the source `Aircraft` record.
- `pilot_in_command` is not accepted as an editable input in MVP. It is derived from the authenticated user.

### Submit

Submit requires a complete plan:

- Step 1 travel fields are present and valid.
- `flight_rules` and `flight_type` are present.
- `aircraft_id` is present.
- Aircraft snapshot exists and has been confirmed.
- `cruising_speed`, `cruising_level`, `route`, and `total_eet` are present.
- `endurance` and `persons_on_board` are present.
- `persons_on_board` is greater than or equal to 1 and includes the pilot.
- `endurance` must be greater than `total_eet`.
- If `flight_rules` is `Y` or `Z`, `rule_change_point` is required and must appear in `route`.
- `other_information` is free text. Core does not autogenerate ICAO item 18 indicators in MVP.
- Both destination alternates are always required. `ALTNNIL` is not supported as an exception in MVP.

Time fields such as `total_eet` and `endurance` use HHMM strings and are parsed for comparison during submit.

## State Machine

MVP flow:

```text
draft -> filed -> pending_approval -> accepted
                           |
                           v
                        rejected
```

Rules:

- Only pilots can submit their own `draft` plans.
- Submit records both `draft -> filed` and `filed -> pending_approval` in the same operation.
- Plans outside `draft` cannot be edited by `PATCH`.
- Rejecting any pending approval transitions the plan to `rejected`.
- Approving all approvals transitions the plan to `accepted`.
- `cancelled`, `active`, and `closed` are future operational states.

## Approval Policy

On submit, create three approvals:

- Pilot submission: auto-approved by the pilot.
- Authority acceptance: pending.
- Destination aerodrome acceptance: pending.

Manual approval authorization:

- `Role.ATC_AUTHORITY` may approve or reject `authority_acceptance` if their `AuthorityProfile` applies.
- `Role.AIRPORT_OPERATOR` may approve or reject `destination_aerodrome_acceptance` if their `AirportOperatorProfile.aerodrome_icao_code` matches `FlightPlan.destination_aerodrome_icao`.
- `Role.ADMIN` may approve or reject any pending approval as an override.

Authority profile applicability:

- `AuthorityType.ANAC` and `AuthorityType.EANA` are national and may approve authority acceptance regardless of aerodrome code.
- Other authority types require `AuthorityProfile.aerodrome_icao_code` to match an aerodrome relevant to the plan. For MVP, match against `departure_aerodrome_icao`, `destination_aerodrome_icao`, `alternate1_aerodrome_icao`, or `alternate2_aerodrome_icao`.

Reject requires a non-empty reason and stores who rejected it and when.

## Intelligence Integration

`jetpass-intelligence` already exposes:

- `GET /api/v1/aerodromes`
- `GET /api/v1/aerodromes/{icao}`
- `GET /api/v1/aerodromes/{icao}/sections/{section_id}`
- `POST /intelligence/run`
- `GET /intelligence/notam-sync/status`

Flight-plan MVP integrates through `POST /intelligence/run` via core endpoints. Core acts as an adapter and does not access intelligence MongoDB directly.

Configuration:

- Add `INTELLIGENCE_BASE_URL` to settings.
- Use short HTTP timeouts so assistance cannot stall plan creation.

Behavior:

- Core validates ICAO format before calling intelligence.
- Intelligence responses are returned to the frontend but not stored on `FlightPlan`.
- Intelligence failures return a controlled unavailable-assistance response.
- Alerts with `level = "error"` are returned to the frontend but do not block submit.
- Flight-plan business validation remains in core.

## Error Handling

- `401 Unauthorized`: missing or invalid bearer token, handled by existing auth dependencies.
- `403 Forbidden`: authenticated user has the wrong role or lacks the required profile/aerodrome authority.
- `404 Not Found`: plan or aircraft does not exist, is not visible, or is not owned by the current pilot.
- `409 Conflict`: invalid state transition or attempt to edit a non-draft plan.
- `422 Unprocessable Entity`: schema validation errors.

Ownership and visibility should avoid leaking another pilot's plan or aircraft existence. Pilot-owned resources not owned by the current pilot should return `404`.

## Testing

Use test-driven development during implementation.

Repository/model tests:

- Create and fetch flight plans.
- Create profile records.
- Create status-history records.
- Create approval records.
- Query approvals by plan and status.

Service tests:

- Create plan with Step 1 complete.
- Reject repeated aerodrome codes.
- Reject malformed aerodrome codes.
- Allow `PATCH` only in `draft`.
- Select active owned aircraft and generate snapshot.
- Reject inactive or non-owned aircraft.
- Override snapshot without changing `Aircraft`.
- Block submit when required sections are missing.
- Submit complete plan and record `draft -> filed -> pending_approval`.
- Create approvals with pilot auto-approved.
- Approve as valid authority.
- Approve as valid destination aerodrome operator.
- Approve as admin override.
- Reject with required reason and transition to `rejected`.
- Transition to `accepted` when all approvals are approved.
- Enforce profile/aerodrome checks for approvals.
- Enforce `endurance > total_eet`.
- Enforce `rule_change_point` for `Y` and `Z`.

Route tests:

- Auth is required.
- Pilots can create, view, patch, and submit their own plans.
- Pilots cannot access other pilots' plans.
- Non-pilot users cannot create pilot flight plans.
- Approval endpoints respect role and profile policy.

Intelligence tests:

- Aerodrome assistance sends the expected `/intelligence/run` request.
- NOTAM assistance sends the expected `/intelligence/run` request.
- Combined run sends the expected request shape.
- Intelligence `error` alerts are returned without blocking.
- HTTP timeout or upstream failure returns controlled unavailable response.

## Implementation Notes

- Keep the MVP minimal. Do not add dynamic approval-criteria configuration until there is a concrete need.
- Keep item 18 as user-provided free text for MVP.
- Do not add a core aerodrome table. Intelligence owns aerodrome enrichment and its MongoDB storage.
- Do not persist intelligence responses in the flight plan.
- Keep aircraft snapshot override fields explicit in schemas so clients cannot accidentally edit source aircraft data through flight-plan endpoints.
- Use UTC for stored EOBT. The frontend is responsible for converting from local time to UTC before sending the request.
- Consider adding Alembic migrations for the new tables because the repository already contains Alembic setup.
