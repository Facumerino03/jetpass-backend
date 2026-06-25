from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models import aircraft as _aircraft_model
from app.models import aerodrome as _aerodrome_model
from app.models import flight_plan as _fp_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models import validation_block as _vb_model
from app.models import validation_criterion as _vc_model
from app.models.user import Role
from app.models.validation_criterion import CriterionOperator, CriterionResult
from app.tests.aerodrome_fixtures import seed_flight_plan_aerodromes
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.repositories.user_repository import UserRepository
from app.repositories.validation_criterion_repository import ValidationCriterionRepository
from app.services.validation_service import ValidationService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client_with_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def create_authority(db_session, *, email: str = "authority@example.com"):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Torre",
        last_name="Ezeiza",
        phone=None,
        role=Role.ATC_AUTHORITY,
    )


async def token_for_role(session_factory, *, email: str, role: Role) -> str:
    async with session_factory() as session:
        user = await UserRepository.create(
            session,
            email=email,
            password_hash="hashed",
            first_name="Test",
            last_name="User",
            phone=None,
            role=role,
        )
        await session.commit()
        return create_access_token(subject=str(user.id), role=user.role.value)


async def seed_aerodromes(db_session):
    await seed_flight_plan_aerodromes(db_session)
    await db_session.commit()


async def create_plan(db_session, pilot):
    await seed_aerodromes(db_session)
    return await FlightPlanRepository.create_draft(
        db_session,
        pilot_user_id=pilot.id,
        pilot_in_command="Amelia Earhart",
        departure_aerodrome_icao="SABE",
        departure_time_utc="1430",
        flight_date=date(2026, 5, 18),
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
    )


# --- Repository tests ---

@pytest.mark.asyncio
async def test_validation_criterion_crud(db_session):
    authority = await create_authority(db_session)

    criterion = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Altitud mínima corredor",
        field_path="cruising_level",
        operator=CriterionOperator.GTE,
        expected_value="A045",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
        pass_message="Altitud suficiente.",
        fail_message="Altitud insuficiente. Rechazar.",
    )
    await db_session.commit()

    fetched = await ValidationCriterionRepository.get_by_id(db_session, criterion_id=criterion.id)
    assert fetched is not None
    assert fetched.name == "Altitud mínima corredor"
    assert fetched.operator == CriterionOperator.GTE
    assert fetched.result_on_pass == CriterionResult.APPROVE

    await ValidationCriterionRepository.update(fetched, name="Corredor actualizado")
    await db_session.commit()

    refreshed = await ValidationCriterionRepository.get_by_id(db_session, criterion_id=criterion.id)
    assert refreshed.name == "Corredor actualizado"

    await ValidationCriterionRepository.soft_delete(refreshed)
    await db_session.commit()

    deleted = await ValidationCriterionRepository.get_by_id(db_session, criterion_id=criterion.id)
    assert deleted.is_active is False


@pytest.mark.asyncio
async def test_validation_criterion_list_by_owner(db_session):
    authority = await create_authority(db_session)
    await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Criterio 1",
        field_path="departure_aerodrome_icao",
        operator=CriterionOperator.EQ,
        expected_value="SABE",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Criterio 2",
        field_path="persons_on_board",
        operator=CriterionOperator.GT,
        expected_value="0",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.WARN,
    )
    await db_session.commit()

    criteria = await ValidationCriterionRepository.list_active_by_user(db_session, user_id=authority.id)
    assert len(criteria) == 2
    assert criteria[0].name == "Criterio 2"


# --- Evaluation tests ---

@pytest.mark.asyncio
async def test_evaluation_returns_results_for_multiple_criteria(db_session):
    authority = await create_authority(db_session)
    pilot = await create_authority(db_session, email="pilot@example.com")
    plan = await create_plan(db_session, pilot)

    c1 = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Salida debe ser SABE",
        field_path="departure_aerodrome_icao",
        operator=CriterionOperator.EQ,
        expected_value="SABE",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    c2 = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Destino no es SABE",
        field_path="destination_aerodrome_icao",
        operator=CriterionOperator.NEQ,
        expected_value="SABE",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    await db_session.commit()

    result = ValidationService.evaluate(plan, [c1, c2])

    assert result.overall == CriterionResult.APPROVE
    assert len(result.results) == 2
    assert result.results[0].passed is True
    assert result.results[1].passed is True


@pytest.mark.asyncio
async def test_evaluation_overall_is_worst_case(db_session):
    authority = await create_authority(db_session)
    pilot = await create_authority(db_session, email="pilot@example.com")
    plan = await create_plan(db_session, pilot)

    c1 = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Pasa",
        field_path="departure_aerodrome_icao",
        operator=CriterionOperator.EQ,
        expected_value="SABE",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.WARN,
    )
    c2 = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="Falla con reject",
        field_path="destination_aerodrome_icao",
        operator=CriterionOperator.EQ,
        expected_value="SABE",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    await db_session.commit()

    result = ValidationService.evaluate(plan, [c1, c2])

    assert result.overall == CriterionResult.REJECT
    assert result.results[0].passed is True
    assert result.results[1].passed is False


@pytest.mark.asyncio
async def test_operator_is_present_and_is_absent(db_session):
    authority = await create_authority(db_session)
    pilot = await create_authority(db_session, email="pilot@example.com")
    plan = await create_plan(db_session, pilot)

    c_present = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="remarks ausentes",
        field_path="remarks",
        operator=CriterionOperator.IS_ABSENT,
        expected_value=None,
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.WARN,
    )
    await db_session.commit()

    result = ValidationService.evaluate(plan, [c_present])
    assert result.results[0].passed is True


@pytest.mark.asyncio
async def test_numeric_operators_gt_gte_lt_lte(db_session):
    authority = await create_authority(db_session)
    pilot = await create_authority(db_session, email="pilot@example.com")
    plan = await create_plan(db_session, pilot)
    plan.persons_on_board = 3
    plan.aircraft_number = 1
    await db_session.commit()

    c_gt = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="persons > 0",
        field_path="persons_on_board",
        operator=CriterionOperator.GT,
        expected_value="0",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    c_lt = await ValidationCriterionRepository.create(
        db_session,
        created_by_user_id=authority.id,
        name="persons < 2",
        field_path="persons_on_board",
        operator=CriterionOperator.LT,
        expected_value="2",
        result_on_pass=CriterionResult.APPROVE,
        result_on_fail=CriterionResult.REJECT,
    )
    await db_session.commit()

    result = ValidationService.evaluate(plan, [c_gt, c_lt])

    assert result.results[0].passed is True
    assert result.results[1].passed is False
    assert result.overall == CriterionResult.REJECT


# --- Route tests ---

@pytest.mark.asyncio
async def test_authority_can_create_list_update_and_delete_criterion(client_with_factory):
    client, session_factory = client_with_factory
    token = await token_for_role(session_factory, email="auth@example.com", role=Role.ATC_AUTHORITY)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/validation/criteria",
        json={
            "name": "Altitud mínima",
            "field_path": "cruising_level",
            "operator": "gte",
            "expected_value": "A045",
            "result_on_pass": "approve",
            "result_on_fail": "reject",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Altitud mínima"
    criterion_id = created["id"]

    list_response = await client.get("/validation/criteria", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [criterion_id]

    patch_response = await client.patch(
        f"/validation/criteria/{criterion_id}",
        json={"name": "Altitud mínima corredor"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Altitud mínima corredor"

    delete_response = await client.delete(f"/validation/criteria/{criterion_id}", headers=headers)
    assert delete_response.status_code == 200

    list_after = await client.get("/validation/criteria", headers=headers)
    assert list_after.json() == []


@pytest.mark.asyncio
async def test_pilot_cannot_manage_criteria(client_with_factory):
    client, session_factory = client_with_factory
    token = await token_for_role(session_factory, email="pilot@example.com", role=Role.PILOT)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/validation/criteria",
        json={
            "name": "Test",
            "field_path": "departure_aerodrome_icao",
            "operator": "eq",
            "expected_value": "SABE",
            "result_on_pass": "approve",
            "result_on_fail": "reject",
        },
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_run_validation_endpoint_evaluates_criteria_against_plan(client_with_factory):
    client, session_factory = client_with_factory
    auth_token = await token_for_role(session_factory, email="auth@example.com", role=Role.ATC_AUTHORITY)
    pilot_token = await token_for_role(session_factory, email="pilot@example.com", role=Role.PILOT)
    auth_headers = {"Authorization": f"Bearer {auth_token}"}
    pilot_headers = {"Authorization": f"Bearer {pilot_token}"}

    async with session_factory() as session:
        await seed_flight_plan_aerodromes(session)
        await session.commit()

    plan_response = await client.post(
        "/flight-plans",
        json={
            "departure_aerodrome_icao": "SABE",
            "departure_time_utc": "1430",
            "flight_date": "2026-05-18",
            "destination_aerodrome_icao": "SAEZ",
            "alternate1_aerodrome_icao": "SADP",
            "alternate2_aerodrome_icao": "SADF",
        },
        headers=pilot_headers,
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    criterion_response = await client.post(
        "/validation/criteria",
        json={
            "name": "Salida debe ser SABE",
            "field_path": "departure_aerodrome_icao",
            "operator": "eq",
            "expected_value": "SABE",
            "result_on_pass": "approve",
            "result_on_fail": "reject",
        },
        headers=auth_headers,
    )
    assert criterion_response.status_code == 201
    criterion_id = criterion_response.json()["id"]

    run_response = await client.post(
        "/validation/run",
        json={
            "flight_plan_id": plan_id,
            "criterion_ids": [criterion_id],
        },
        headers=auth_headers,
    )
    assert run_response.status_code == 200
    run_result = run_response.json()
    assert run_result["overall"] == "approve"
    assert len(run_result["results"]) == 1
    assert run_result["results"][0]["passed"] is True


@pytest.mark.asyncio
async def test_fields_endpoint_returns_fpl_mapping(client_with_factory):
    client, session_factory = client_with_factory
    token = await token_for_role(session_factory, email="auth@example.com", role=Role.ATC_AUTHORITY)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/validation/fields", headers=headers)
    assert response.status_code == 200
    fields = response.json()
    assert len(fields) > 10
    assert any(f["field_path"] == "departure_aerodrome_icao" for f in fields)


from app.repositories.validation_block_repository import ValidationBlockRepository


@pytest.mark.asyncio
async def test_authority_can_create_run_and_delete_block(client_with_factory):
    client, session_factory = client_with_factory
    auth_token = await token_for_role(session_factory, email="auth@example.com", role=Role.ATC_AUTHORITY)
    pilot_token = await token_for_role(session_factory, email="pilot@example.com", role=Role.PILOT)
    auth_headers = {"Authorization": f"Bearer {auth_token}"}
    pilot_headers = {"Authorization": f"Bearer {pilot_token}"}

    async with session_factory() as session:
        await seed_aerodromes(session)

    plan_response = await client.post(
        "/flight-plans",
        json={
            "departure_aerodrome_icao": "SABE",
            "departure_time_utc": "1430",
            "flight_date": "2026-05-18",
            "destination_aerodrome_icao": "SAEZ",
            "alternate1_aerodrome_icao": "SADP",
            "alternate2_aerodrome_icao": "SADF",
        },
        headers=pilot_headers,
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    c1 = await client.post(
        "/validation/criteria",
        json={
            "name": "Salida SABE",
            "field_path": "departure_aerodrome_icao",
            "operator": "eq",
            "expected_value": "SABE",
            "result_on_pass": "approve",
            "result_on_fail": "reject",
        },
        headers=auth_headers,
    )
    c2 = await client.post(
        "/validation/criteria",
        json={
            "name": "Destino SAEZ",
            "field_path": "destination_aerodrome_icao",
            "operator": "eq",
            "expected_value": "SAEZ",
            "result_on_pass": "approve",
            "result_on_fail": "reject",
        },
        headers=auth_headers,
    )
    c1_id = c1.json()["id"]
    c2_id = c2.json()["id"]

    block_response = await client.post(
        "/validation/blocks",
        json={"name": "Corredor SABE-SAEZ", "criterion_ids": [c1_id, c2_id]},
        headers=auth_headers,
    )
    assert block_response.status_code == 201
    block = block_response.json()
    assert block["name"] == "Corredor SABE-SAEZ"
    assert block["criteria_count"] == 2
    block_id = block["id"]

    list_response = await client.get("/validation/blocks", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    run_response = await client.post(
        "/validation/run",
        json={"flight_plan_id": plan_id, "block_id": block_id},
        headers=auth_headers,
    )
    assert run_response.status_code == 200
    assert run_response.json()["overall"] == "approve"

    delete_response = await client.delete(f"/validation/blocks/{block_id}", headers=auth_headers)
    assert delete_response.status_code == 200

    list_after = await client.get("/validation/blocks", headers=auth_headers)
    assert list_after.json() == []
