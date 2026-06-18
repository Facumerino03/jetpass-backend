# Jetpass Auth Design

## Context

Jetpass backend is a FastAPI project organized with an MVC-style structure:

- `controllers`: HTTP routes.
- `services`: business rules and orchestration.
- `repositories`: database access.
- `models`: SQLAlchemy persistence models.
- `schemas`: Pydantic request and response contracts.
- `core`: shared infrastructure such as settings, database, and security utilities.

The current domain diagram defines a `User` with roles and a future `PilotProfile`. The first authentication scope targets the mobile app used by pilots.

## Goals

- Implement pilot registration without requiring pilot license/profile data yet.
- Implement JSON login for the mobile app.
- Use JWT access tokens for protected API calls.
- Use opaque persisted refresh tokens with rotation for mobile session continuity.
- Keep `is_verified` available for future authorization checks without enforcing it now.
- Preserve the existing MVC project structure.

## Non-Goals

- Email verification.
- Password reset.
- MFA.
- Admin approval flows.
- Pilot license verification.
- Full OAuth2 authorization server behavior.
- Implementing role-specific non-auth features.

## Authentication Strategy

Use an access-token plus refresh-token model:

- Access tokens are signed JWTs.
- Refresh tokens are opaque random strings.
- Refresh tokens are stored only as hashes in the database.
- Refresh tokens are rotated on every refresh request.
- Logout revokes the active refresh token session.

This gives the mobile app persistent sessions without forcing pilots to log in frequently, while keeping revocation and token reuse detection straightforward.

## User Registration

Endpoint: `POST /auth/register/pilot`

The request creates a `User` with:

- `role = pilot`
- `is_active = true`
- `is_verified = false`

The request does not include pilot license fields. `PilotProfile` creation is deferred until a future profile-completion endpoint exists.

Registration should return the public user plus tokens, so the pilot is logged in immediately after sign-up.

## Login

Endpoint: `POST /auth/login`

The mobile client sends JSON with email and password. The service verifies the password hash and creates a new auth session.

Successful response includes:

- `access_token`
- `refresh_token`
- `token_type = bearer`
- `expires_in`
- public `user`

Failed login returns `401` with a generic invalid-credentials message.

## Refresh

Endpoint: `POST /auth/refresh`

The client sends the opaque `refresh_token`. The backend hashes it, finds a matching non-revoked, non-expired session, revokes the old session/token, and returns a new access token plus a new refresh token.

Reusing an already-rotated refresh token must fail.

## Logout

Endpoint: `POST /auth/logout`

The client sends the current refresh token. The backend revokes the matching active auth session.

Existing access tokens remain valid until their short expiration. This is acceptable because access tokens are intentionally short-lived.

## Current User

Endpoint: `GET /auth/me`

The client sends `Authorization: Bearer <access_token>`. The backend decodes the JWT, validates token type and expiration, loads the user, and returns the public user representation.

## Data Model

### User

Fields aligned with `docs/class-diagram.puml`:

- `id: UUID`
- `email: str`, unique
- `password_hash: str`
- `first_name: str`
- `last_name: str`
- `phone: str | None`
- `role: enum`, initially `pilot`
- `is_verified: bool`, default `false`
- `is_active: bool`, default `true`
- `created_at`
- `updated_at`

### AuthSession

Fields:

- `id: UUID`
- `user_id: UUID`
- `refresh_token_hash: str`, unique
- `expires_at: datetime`
- `revoked_at: datetime | None`
- `created_at`
- `updated_at`
- `device_name: str | None`
- `user_agent: str | None`
- `ip_address: str | None`

`device_name`, `user_agent`, and `ip_address` are optional metadata for future session management.

## Token Details

Access token JWT claims:

- `sub`: user id as string
- `role`: user role
- `type`: `access`
- `exp`: expiration timestamp

Recommended lifetimes:

- Access token: 15 minutes.
- Refresh token: 30 days.

The exact durations should be configurable through settings.

## FastAPI Security Dependencies

Use the FastAPI security pattern documented for OAuth2 bearer tokens:

- `OAuth2PasswordBearer` reads `Authorization: Bearer <token>`.
- `get_current_user` decodes and validates the access JWT, then loads the user.
- `get_current_active_user` additionally requires `is_active = true`.
- Future dependency `get_current_verified_pilot` can require `role = pilot` and `is_verified = true` when protected features need verification.

Although login uses JSON instead of `OAuth2PasswordRequestForm`, bearer-token protection remains compatible with FastAPI's OpenAPI security model.

## MVC File Layout

Planned files:

- `app/routes/auth.py`
- `app/services/auth_service.py`
- `app/repositories/user_repository.py`
- `app/repositories/auth_session_repository.py`
- `app/models/user.py`
- `app/models/auth_session.py`
- `app/schemas/auth.py`
- `app/core/security.py`

Existing files to update:

- `app/main.py` to include the auth router.
- `app/core/config.py` to include token settings.
- `pyproject.toml` to include password hashing and JWT dependencies.

## Error Handling

- Duplicate email returns `409 Conflict`.
- Invalid login returns `401 Unauthorized` with a generic message.
- Missing or invalid access token returns `401 Unauthorized` with `WWW-Authenticate: Bearer`.
- Inactive user returns `403 Forbidden`.
- Invalid, expired, or reused refresh token returns `401 Unauthorized`.

## Testing Scope

Initial tests should cover:

- Pilot registration succeeds and returns tokens.
- Duplicate email is rejected.
- Login succeeds with valid credentials.
- Login fails with invalid credentials.
- `/auth/me` succeeds with a valid access token.
- `/auth/me` fails without a token.
- Refresh succeeds with a valid refresh token.
- Refresh rotates the token and rejects reuse of the old token.
- Logout revokes the refresh token.

## Future Extensions

- `PilotProfile` completion endpoint.
- Verification-only dependencies for flight-plan submission or other regulated actions.
- Password reset flow.
- Email verification.
- Session listing and remote revocation per device.
- Token family reuse detection if stricter refresh-token compromise handling is needed.
