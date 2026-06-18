# Pilot Aircraft Management Design

## Context

The class diagram defines `User` as the owner of zero or more `Aircraft` records through `Aircraft.owner_user_id`. Pilots need authenticated endpoints to manage only their own aircraft. Deleting an aircraft must preserve auditability for current and future flight-plan history, so deletion will be implemented as a soft delete using `is_active = False`.

The current backend follows an MVC-style structure with `routes`, `services`, `repositories`, `models`, `schemas`, and async tests using SQLite in memory. The aircraft feature will follow the same structure.

## Scope

Implement CRUD-style aircraft management for the authenticated pilot:

- Create an aircraft owned by the current pilot.
- List active aircraft owned by the current pilot.
- Get one active aircraft owned by the current pilot.
- Edit one active aircraft owned by the current pilot.
- Soft-delete one active aircraft owned by the current pilot.

Out of scope for this iteration:

- Admin-level aircraft management.
- Flight-plan integration beyond preserving aircraft records for auditability.
- Hard deletion of aircraft records.
- Pagination, sorting, or filtering beyond active aircraft for the current pilot.

## API Design

Use a pilot-scoped router because the current user identity already comes from the bearer token and the client should not provide a pilot id.

- `POST /pilot/aircraft`
- `GET /pilot/aircraft`
- `GET /pilot/aircraft/{aircraft_id}`
- `PATCH /pilot/aircraft/{aircraft_id}`
- `DELETE /pilot/aircraft/{aircraft_id}`

All endpoints require an authenticated active user. The service will reject non-pilot users with `403 Forbidden`.

`DELETE /pilot/aircraft/{aircraft_id}` will set `is_active = False` and return a small response such as `{ "deleted": true }`. Soft-deleted aircraft will not appear in `GET /pilot/aircraft` and cannot be fetched or updated through the pilot endpoints.

## Data Model

Add `app/models/aircraft.py` with fields from `docs/class-diagram.puml`:

- `id`
- `owner_user_id`
- `alias`
- `is_active`
- `identification`
- `icao_type_designator`
- `wake_turbulence_category`
- `equipment_com_nav`
- `equipment_surveillance`
- `pbn_capabilities`
- `emergency_radio`
- `survival_equipment`
- `life_jackets`
- `dinghies_number`
- `dinghies_capacity`
- `dinghies_cover`
- `dinghies_color`
- `color_and_markings`
- `created_at`
- `updated_at`

Add `WakeTurbulenceCat` as a `StrEnum` with values `L`, `M`, `H`, and `J`. Add a `User.aircraft` relationship with `cascade="all, delete-orphan"` at the ORM level, while API deletion remains soft delete.

## Schemas

Add `app/schemas/aircraft.py`:

- `AircraftCreate` for required and optional request fields.
- `AircraftUpdate` with optional editable fields for partial updates.
- `AircraftPublic` for serialized responses.
- `AircraftDeleteResponse` with `deleted: bool`.

Validation will stay close to the diagram and existing project style. String fields will use reasonable max lengths matching aviation identifiers and current schema patterns. Required fields should include the core flight-plan aircraft fields: `identification`, `icao_type_designator`, `wake_turbulence_category`, `equipment_com_nav`, `equipment_surveillance`, and `color_and_markings`. Optional equipment and dinghy fields may be omitted.

## Repository

Add `AircraftRepository` with async methods:

- `create(db, owner_user_id, **fields)`
- `list_active_by_owner(db, owner_user_id)`
- `get_active_by_owner_and_id(db, owner_user_id, aircraft_id)`
- `update(aircraft, **fields)`
- `soft_delete(aircraft)`

Repository methods will only handle persistence concerns. Ownership and role policy will live in the service layer.

## Service

Add `AircraftService` with methods matching the endpoints:

- `create_for_pilot`
- `list_for_pilot`
- `get_for_pilot`
- `update_for_pilot`
- `delete_for_pilot`

The service will verify `current_user.role == Role.PILOT`. Missing or already-deleted aircraft owned by the pilot will return `404 Not Found`. Aircraft owned by another user will also return `404 Not Found` to avoid leaking resource existence.

## Routing

Add `app/routes/aircraft.py` with `APIRouter(prefix="/pilot/aircraft", tags=["pilot-aircraft"])` and include it in `app/main.py`.

Use the existing dependency style:

- `CurrentActiveUserDep` for authentication.
- `Annotated[AsyncSession, Depends(get_db)]` for database access.

Each HTTP operation will have its own route function.

## Error Handling

- `401 Unauthorized`: missing or invalid bearer token, handled by existing auth dependency.
- `403 Forbidden`: authenticated user is not a pilot.
- `404 Not Found`: aircraft does not exist, is inactive, or is owned by another user.
- `422 Unprocessable Entity`: request validation errors from Pydantic.

## Testing

Use test-driven development. Add failing tests before production code.

Endpoint tests should cover:

- A pilot can create an aircraft and receives the public aircraft payload.
- A pilot can list only active aircraft they own.
- A pilot can get one active aircraft they own.
- A pilot can patch editable aircraft fields.
- Deleting an aircraft soft-deletes it and removes it from pilot list/get results.
- Missing token returns `401` through existing auth behavior.
- Non-owned aircraft returns `404`.

Repository tests should cover:

- Creating and fetching active aircraft by owner.
- Soft-deleted aircraft are excluded from active owner queries.

## Implementation Notes

Existing tests import model modules before `Base.metadata.create_all`; aircraft tests must import `app.models.aircraft` so SQLite creates the table. If `app/models/__init__.py` is used as a central import location later, keep the change minimal and avoid unrelated model refactors.
