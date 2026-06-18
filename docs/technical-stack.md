# Stack Tecnológico del Backend Core — Jetpass

## Introducción

El Backend Core de Jetpass es el núcleo transaccional del ecosistema. No es una capa de presentación ni un microservicio de datos: es el motor que centraliza la lógica de negocio, administra el ciclo de vida de los planes de vuelo, garantiza la coherencia del estado entre actores concurrentes y actúa como fuente de verdad para el resto de los componentes. La aplicación móvil del piloto, el dashboard multirol y el microservicio jetpass-intelligence interactúan todos con este núcleo a través de su API HTTP. La selección del stack tecnológico no fue arbitraria; cada decisión responde a restricciones concretas de dominio: asincronía requerida por la naturaleza colaborativa del sistema, fuerte tipado para un modelo de datos regulatorio complejo, y una arquitectura de capas que permita evolucionar el sistema sin romper los contratos existentes.

---

## 1. Lenguaje y runtime: Python 3.12

Python 3.12 fue elegido como lenguaje de implementación por razones que van más allá de la popularidad. En primer lugar, el ecosistema de Python para servicios web asíncronos —FastAPI, SQLAlchemy async, httpx, asyncio— alcanzó madurez de producción en las versiones 3.11 y 3.12, con mejoras de rendimiento medibles respecto a versiones anteriores (Python 3.12 introdujo optimizaciones al intérprete que reducen el overhead de llamadas a funciones). En segundo lugar, el sistema de type hints de Python, que desde la versión 3.10 permite sintaxis nativa como `str | None` y `dict[str, Any]`, permite expresar contratos de tipos que Pydantic valida en tiempo de ejecución. Este puente entre tipado estático voluntario y validación dinámica es el que hace posible que FastAPI genere documentación OpenAPI automáticamente a partir de las anotaciones de tipo.

La versión exacta está fijada en el archivo `.python-version` en la raíz del repositorio, lo que garantiza que cualquier entorno —local, CI, producción— use exactamente el mismo runtime sin depender de convenciones implícitas.

---

## 2. Framework web: FastAPI

### Justificación de la elección

FastAPI no es simplemente un framework ASGI rápido; es la intersección entre tres características que el Backend Core necesita de manera simultánea: **rendimiento asíncrono nativo**, **validación declarativa de datos** y **generación automática de contratos de API**. Las alternativas consideradas son instructivas:

- **Django REST Framework**: orientado a sincrónismo, con un ORM síncrono como pieza central. Adaptarlo a un modelo completamente asíncrono requiere workarounds significativos y sacrifica la coherencia del stack.
- **Flask**: minimalista y flexible, pero carece de validación integrada, no genera OpenAPI de forma nativa y requiere extensiones adicionales para cada capacidad, incrementando la superficie de dependencias sin un contrato claro de compatibilidad.
- **FastAPI**: construido sobre Starlette (framework ASGI de bajo nivel) y Pydantic (validación de datos), logra que el mismo código que define los endpoints sea también la fuente de la documentación OpenAPI, la validación de los payloads de entrada y la serialización de las respuestas de salida.

### Organización de la aplicación

La aplicación se ensambla mediante la función de fábrica `create_app()` en `app/main.py`, que registra los routers y el middleware:

```python
def create_app() -> FastAPI:
    application = FastAPI(title="Jetpass Backend Core", lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(aircraft.router)
    application.include_router(flight_plans.router)
    return application
```

El patrón de fábrica es deliberado: permite instanciar la aplicación de forma independiente en tests sin efectos secundarios globales.

### Lifespan y gestión del ciclo de vida

FastAPI expone un gestor de contexto `lifespan` que reemplaza a los eventos `on_startup`/`on_shutdown` de versiones anteriores. En el Backend Core, este mecanismo libera el pool de conexiones de SQLAlchemy al apagar la aplicación:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if database.engine is not None:
        await database.engine.dispose()
```

### Sistema de inyección de dependencias

FastAPI implementa inversión de dependencias a través del sistema `Depends`. Esto permite que la sesión de base de datos, el usuario autenticado y las validaciones de rol se compongan de forma declarativa en la firma de cada endpoint sin lógica repetida. La dependencia `CurrentActiveUserDep` es un tipo anotado que encapsula toda la cadena de autenticación:

```python
CurrentActiveUserDep = Annotated[object, Depends(get_current_active_user)]
```

Un endpoint que require un usuario activo simplemente declara ese tipo en su firma, y FastAPI resuelve la cadena completa: extrae el Bearer token, valida el JWT, consulta la base de datos y verifica el estado activo.

---

## 3. Gestor de dependencias: uv

El proyecto utiliza `uv` como gestor de dependencias y entornos virtuales en lugar de la combinación tradicional de `pip` + `virtualenv` + `pip-tools`. Esta decisión se justifica en tres dimensiones:

**Rendimiento**: `uv` está implementado en Rust y es entre 10 y 100 veces más rápido que `pip` en la resolución e instalación de dependencias. En un contexto donde el entorno puede reconstruirse frecuentemente (CI, despliegues, onboarding de desarrolladores), esta diferencia es operacionalmente relevante.

**Determinismo**: Las dependencias transitivas se fijan en `uv.lock`, un archivo de bloqueo de formato estructurado que garantiza que `uv sync` produce exactamente el mismo entorno en cualquier máquina, sin importar cuándo se ejecute. Esto elimina la clase de errores "funciona en mi máquina" causados por versiones resueltas diferentes en distintos momentos.

**Unificación**: `uv` reemplaza simultáneamente a `pip`, `virtualenv`, `pip-tools` y en parte a `pyenv`. Un único comando (`uv sync`) recrea el entorno completo desde cero. El archivo `pyproject.toml` cumple el estándar PEP 517/518 y declara tanto las dependencias de producción como las de desarrollo en grupos diferenciados:

```toml
[dependency-groups]
dev = [
    "aiosqlite>=0.21.0",
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
]
```

---

## 4. Validación y serialización: Pydantic v2

Pydantic v2 es la columna vertebral de la capa de contratos del Backend Core. Su función trasciende la validación de datos: es el mecanismo por el cual se definen los contratos de entrada y salida de la API, y FastAPI los transforma en documentación OpenAPI que otros clientes (la app móvil, el dashboard) pueden consumir para generar sus propios clientes tipados.

### Separación de schemas por intención

El proyecto separa de forma explícita los schemas según su dirección en el flujo de datos:

- `AircraftCreate` / `FlightPlanCreate`: datos que entran desde el cliente, con validaciones estrictas.
- `AircraftUpdate` / `FlightPlanUpdate`: datos parciales para modificaciones (todos los campos opcionales).
- `AircraftPublic` / `FlightPlanDetailPublic`: datos que salen hacia el cliente, incluyendo relaciones cargadas.

Esta separación previene la exposición accidental de campos internos (como `password_hash`) y obliga a que cada operación tenga un contrato explícito.

### Validación de dominio aeronáutico

La validación de códigos ICAO —identificadores de cuatro caracteres alfanuméricos en mayúsculas que identifican aeródromos en la nomenclatura aeronáutica internacional— está centralizada en `app/services/flight_plan_validations.py` y se invoca desde los schemas de Pydantic. Esto garantiza que ningún plan de vuelo con códigos de aeródromo inválidos llegue siquiera a la capa de servicio.

---

## 5. Base de datos: PostgreSQL + SQLAlchemy 2.x async + asyncpg

### PostgreSQL

La elección de PostgreSQL sobre alternativas como MySQL o SQLite responde a características específicas del dominio:

**Tipos nativos UUID**: todas las entidades del sistema usan UUIDs como clave primaria. PostgreSQL soporta el tipo `UUID` de forma nativa, con índices eficientes y sin el overhead de almacenar UUIDs como strings de 36 caracteres.

**Tipos ENUM nativos**: el modelo de datos del Backend Core hace uso extensivo de enumeraciones (`FlightPlanStatus`, `FlightRules`, `FlightType`, `Role`, `WakeTurbulenceCat`, `AuthorityType`). PostgreSQL permite definirlos como tipos nativos en el schema, lo que garantiza integridad referencial a nivel de base de datos y no solo a nivel de aplicación.

**Transacciones ACID completas**: el flujo de aprobación de un plan de vuelo involucra múltiples escrituras que deben ser atómicas (crear el plan, crear los registros de aprobación, crear el primer evento de historial). PostgreSQL garantiza que si cualquiera de esas escrituras falla, el estado de la base de datos permanece consistente.

**Soporte para `DateTime with timezone`**: todos los campos temporales del sistema usan `DateTime(timezone=True)`, fundamental para un sistema de aviación donde los horarios se expresan en UTC y la ambigüedad de zona horaria puede tener consecuencias operativas.

### SQLAlchemy 2.x con AsyncSession

SQLAlchemy 2.x introdujo una API completamente nueva para el acceso asíncrono, basada en `AsyncSession` y `create_async_engine`. La elección de la interfaz async no es cosmética: un servidor ASGI como Uvicorn puede manejar miles de conexiones concurrentes mediante un event loop único. Si las consultas a la base de datos son síncronas, cada consulta bloquea el event loop y el servidor pierde toda su capacidad de concurrencia. Con `AsyncSession`, las consultas suspenden la coroutine actual mientras esperan la respuesta de la base de datos, permitiendo que el event loop atienda otras solicitudes mientras tanto.

La configuración en `app/core/database.py` refleja este diseño:

```python
engine = create_async_engine(_db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
```

El parámetro `expire_on_commit=False` es importante: sin él, SQLAlchemy marcaría todos los atributos como expirados después de un commit, forzando una nueva consulta al acceder a cualquier campo. En un contexto async donde los objetos se devuelven en la respuesta HTTP inmediatamente después del commit, esto causaría errores de sesión cerrada.

### DeclarativeBase y el patrón de modelos

Todos los modelos heredan de `Base`, que a su vez hereda de `DeclarativeBase` —la API moderna de SQLAlchemy 2.x. Esto permite usar `Mapped[T]` para declarar columnas con tipos Python nativos, y `mapped_column()` para especificar propiedades de la columna. El resultado es código que expresa el schema de la base de datos en términos Python sin sacrificar la expresividad:

```python
class FlightPlan(Base):
    __tablename__ = "flight_plans"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[FlightPlanStatus] = mapped_column(
        Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False, default=FlightPlanStatus.DRAFT, index=True,
    )
```

### asyncpg

El driver de conexión a PostgreSQL es `asyncpg`, una implementación nativa del protocolo de comunicación de PostgreSQL en Python async. La alternativa más común, `psycopg2`, es síncrona y requiere una capa de adaptación para funcionar con SQLAlchemy async. `asyncpg` elimina esa capa de adaptación, reduce la latencia de cada operación de base de datos y es consistentemente más rápido en benchmarks de alto volumen de queries. La cadena de conexión `postgresql+asyncpg://` en las variables de entorno especifica explícitamente este driver.

---

## 6. Migraciones de schema: Alembic

Alembic es la herramienta de migraciones de SQLAlchemy. Su adopción en este proyecto responde a la necesidad de evolucionar el schema de base de datos de forma controlada y reversible en un sistema que está en desarrollo activo.

### Migraciones como código versionado

Cada cambio al schema de la base de datos se representa como un archivo Python en `alembic/versions/`, con un identificador único, una referencia al estado previo (`down_revision`) y dos funciones: `upgrade()` y `downgrade()`. Esta estructura permite reproducir el estado exacto del schema en cualquier punto de la historia del proyecto, lo que es esencial para mantener la coherencia entre ambientes (desarrollo, test, producción) y para facilitar el rollback ante un despliegue fallido.

La evolución del schema del proyecto ilustra el crecimiento orgánico del sistema:

| Revisión | Cambio |
|---|---|
| `357a662aee93` | Schema inicial: `users`, `aircraft`, `auth_sessions` |
| `c51de2d7e5e7` | Agregar `image_url` a `aircraft` |
| `1f415d96c495` | Tablas de planes de vuelo, aprobaciones, historial y perfiles |
| `7b2c9d4e6f10` | Tabla `controlled_aerodromes` |
| `a1b2c3d4e5f6` | Agregar `latitude`, `longitude` a aeródromos |
| `c3d4e5f6a1b2` | Agregar `traffic_type`, `flight_rules`, `category` |

### Configuración asíncrona de env.py

El archivo `alembic/env.py` configura Alembic para ejecutar migraciones usando el mismo engine asíncrono que usa la aplicación. Esto requiere un patrón específico donde las operaciones de migración se ejecutan dentro de `asyncio.run()`. Esta configuración garantiza que las migraciones y la aplicación siempre usen el mismo driver y la misma URL de base de datos, derivada de `settings.DATABASE_URL`.

---

## 7. Autenticación y seguridad

### Esquema dual: JWT de acceso + token de refresco opaco

El sistema de autenticación implementa un esquema de dos tokens con propiedades complementarias, diseñado para balancear rendimiento, seguridad y capacidad de revocación:

**Access token (JWT, HS256, 15 minutos)**: un JSON Web Token firmado con `SECRET_KEY` que contiene los claims `sub` (user ID), `role` y `type=access`. Es stateless: el servidor puede validarlo sin consultar la base de datos, simplemente verificando la firma y la expiración. Su corta vida útil limita la ventana de exposición si es comprometido. El payload incluye el `role` del usuario para que la capa de servicio pueda tomar decisiones de autorización sin una consulta adicional a la base de datos en cada request:

```python
payload = {"sub": subject, "role": role, "type": token_type, "exp": expires_at}
return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

**Refresh token (opaco, 30 días)**: generado con `secrets.token_urlsafe(64)`, produce 86 caracteres URL-safe derivados de 64 bytes de entropía criptográfica. Solo su hash SHA-256 se almacena en la tabla `auth_sessions`. Esta separación es crítica: si la base de datos es comprometida, el atacante obtiene hashes que no pueden revertirse al token original. El token en sí solo existe en el cliente. Cada uso del refresh token lo rota: el token anterior se revoca y se emite uno nuevo, limitando el daño de un token interceptado.

**`AuthSession` como capa de auditoría**: cada sesión activa tiene un registro en la tabla `auth_sessions` con campos de metadata (dispositivo, user agent, IP). Esto permite revocar sesiones individuales, detectar accesos sospechosos desde ubicaciones inesperadas y auditar el historial de autenticación de un usuario.

### Argon2 para hashing de contraseñas

El hashing de contraseñas utiliza `pwdlib` con el algoritmo Argon2 (`PasswordHash.recommended()`). La elección de Argon2 sobre bcrypt no es de conveniencia sino de seguridad demostrada: Argon2 ganó el Password Hashing Competition en 2015 precisamente por su resistencia a ataques con hardware especializado (GPU y ASICs). A diferencia de bcrypt, cuyo parámetro de costo solo controla el tiempo de CPU, Argon2 permite configurar simultáneamente el tiempo de CPU, el uso de memoria y el paralelismo, haciendo que los ataques de fuerza bruta con hardware paralelo sean exponencialmente más costosos.

```python
password_hash = PasswordHash.recommended()
```

El método `recommended()` selecciona automáticamente los parámetros óptimos de Argon2 para el hardware disponible, garantizando que el factor de trabajo se ajuste a las capacidades del servidor sin intervención manual.

---

## 8. Roles y control de acceso basado en perfiles

### El modelo de roles

El sistema define cuatro roles en el enum `Role` del modelo `User`:

- `pilot`: el actor que origina el plan de vuelo desde la aplicación móvil.
- `atc_authority`: la autoridad del espacio aéreo (ATC), responsable de la aceptación regulatoria.
- `airport_operator`: el operador del aeródromo de destino, responsable de la disponibilidad en tierra.
- `admin`: acceso transversal a todos los recursos.

### Perfiles como extensión de dominio

El rol solo indica la categoría del usuario. Las responsabilidades específicas de cada actor se modelan como perfiles separados: `PilotProfile`, `AuthorityProfile` y `AirportOperatorProfile`. Esta separación sigue el principio de que un `User` es una entidad de autenticación, mientras que los perfiles son entidades de dominio que describen las capacidades operativas del usuario dentro del sistema aeronáutico.

Por ejemplo, un `AuthorityProfile` incluye el campo `authority_type` (enum `AuthorityType`: ARO, AIS, ACC, APP, TWR, EANA, ANAC) y `aerodrome_icao_code`. Esta información determina qué planes de vuelo son visibles para una autoridad específica y qué tipo de aprobación puede otorgar. Una autoridad de tipo `ANAC` o `EANA` tiene visibilidad sobre todos los planes, mientras que una autoridad de aeródromo solo ve los planes que involucran su aeródromo.

### Autorización en la capa de servicio

La autorización no se implementa como middleware general sino en la capa de servicio, lo que permite decisiones de acceso contextualmente informadas. La visibilidad de los planes de vuelo, por ejemplo, no es una regla simple de rol sino una función del rol más el perfil del usuario más el estado del plan:

```python
if current_user.role == Role.AIRPORT_OPERATOR:
    profile = await ProfileRepository.get_airport_operator_profile_by_user_id(db, ...)
    return await FlightPlanRepository.list_pending_for_destination(
        db, destination_aerodrome_icao=profile.aerodrome_icao_code,
    )
```

Este nivel de granularidad sería imposible de implementar correctamente en middleware sin acoplarlo a la lógica de negocio.

---

## 9. Arquitectura en capas

El Backend Core implementa una arquitectura de cuatro capas con responsabilidades bien delimitadas:

```
HTTP Request
      │
      ▼
┌─────────────┐
│   Routes    │  Validación Pydantic, serialización HTTP, codes de respuesta
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Services   │  Lógica de negocio, autorización, transacciones, excepciones HTTP
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  Repositories    │  Queries SQLAlchemy, sin lógica de negocio
└──────┬───────────┘
       │
       ▼
┌─────────────┐
│   Models    │  Entidades ORM, relaciones, defaults
└──────┬──────┘
       │
       ▼
   PostgreSQL
```

### Responsabilidades de cada capa

**Routes**: reciben la request HTTP, delegan en el servicio y devuelven la respuesta con el código HTTP apropiado. No contienen lógica de negocio. Su única responsabilidad es la traducción entre el protocolo HTTP y las llamadas al servicio.

**Services**: contienen toda la lógica de negocio. Son la única capa que conoce las reglas del dominio aeronáutico. Coordinan múltiples operaciones de repositorio dentro de una transacción y lanzan `HTTPException` cuando se viola una regla de negocio.

**Repositories**: abstraen las queries a la base de datos. Son clases con métodos estáticos async que aceptan una `AsyncSession` y devuelven modelos ORM. No conocen la lógica de negocio; su única responsabilidad es la persistencia.

**Models**: definen las tablas y relaciones. No contienen lógica de negocio.

### El patrón Repository con métodos estáticos

El proyecto usa repositorios implementados como clases con métodos estáticos, en lugar de instancias con estado. Esto simplifica la inyección de dependencias: los servicios simplemente llaman `RepositoryClass.method(db, ...)` sin necesidad de instanciar el repositorio. La sesión de base de datos (`AsyncSession`) fluye desde el endpoint hacia abajo a través de todas las capas como parámetro explícito, lo que hace el flujo de datos completamente trazable sin magia implícita.

---

## 10. Ciclo de vida del plan de vuelo

### Máquina de estados

El plan de vuelo es el recurso central del sistema. Su ciclo de vida está modelado como una máquina de estados explícita mediante el enum `FlightPlanStatus`:

```
DRAFT
  │
  │ (submit: validación completa del piloto)
  ▼
FILED
  │
  │ (creación automática de registros de aprobación)
  ▼
PENDING_APPROVAL
  │           │
  │ (todos    │ (cualquier actor
  │  aprueban)│  rechaza)
  ▼           ▼
ACCEPTED   REJECTED
```

Los estados `ACTIVE`, `CLOSED` y `CANCELLED` están definidos en el enum anticipando las siguientes etapas del ciclo operativo del vuelo (inicio, cierre y cancelación), pero sus transiciones aún no están implementadas en la capa de servicio.

### Aircraft snapshot: inmutabilidad del registro técnico

Cuando el piloto asocia una aeronave a un plan de vuelo en edición, el servicio captura un snapshot de todos los campos técnicos relevantes de la aeronave en ese momento:

```python
fields.update(FlightPlanService._snapshot_from_aircraft(aircraft))
```

Esta decisión resuelve un problema de integridad referencial de dominio: si el piloto modifica los datos técnicos de su aeronave después de presentar un plan, el plan debe conservar los datos que estaban vigentes al momento de la presentación. El snapshot garantiza que el plan de vuelo es un documento autocontenido e inmutable en lo que respecta a los datos técnicos de la aeronave.

### Aprobación multiactor

Al presentar un plan, el sistema crea automáticamente tres registros de aprobación:

1. **Piloto** (`pilot_submission`): auto-aprobado en el momento de la presentación. Documenta que el piloto tomó la decisión consciente de presentar el plan.
2. **Autoridad ATC** (`authority_acceptance`): pendiente. La autoridad del espacio aéreo correspondiente debe evaluar la viabilidad regulatoria.
3. **Operador de aeródromo destino** (`destination_aerodrome_acceptance`): pendiente. El operador del aeródromo de destino debe confirmar disponibilidad en tierra.

El plan pasa a `ACCEPTED` solo cuando los tres registros están en estado `APPROVED`. Cualquier rechazo de cualquier actor lo lleva a `REJECTED` inmediatamente. Cada transición de estado queda registrada en `flight_plan_status_history` con el usuario responsable, el motivo y los timestamps, construyendo un audit trail completo.

El historial de estados cumple adicionalmente el rol de preparar la información que eventualmente se certificará en la capa blockchain: cuando el plan alcanza `ACCEPTED`, el documento definitivo junto con su cadena de custodia completa es el candidato a ser registrado en la red blockchain como prueba de inmutabilidad.

---

## 11. Integración con jetpass-intelligence

### httpx como cliente HTTP async

La comunicación con el microservicio jetpass-intelligence se implementa mediante `httpx`, la librería HTTP de facto para Python asíncrono. La elección de `httpx` sobre `requests` responde a un criterio arquitectónico: `requests` es síncrona y bloquearía el event loop de Uvicorn. `httpx` implementa la misma API pero de forma completamente async, permitiendo que mientras se espera la respuesta del microservicio de inteligencia, el servidor siga atendiendo otras solicitudes.

### Degradación graciosa como decisión de diseño

El cliente de inteligencia está diseñado para fallar silenciosamente. Si `INTELLIGENCE_BASE_URL` no está configurado, o si el microservicio está caído, la llamada retorna una respuesta predefinida con `"intent": "unavailable"` en lugar de propagar un error:

```python
async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
    if not self.base_url:
        return self.unavailable_response()
    try:
        async with httpx.AsyncClient(...) as client:
            response = await client.post("/intelligence/run", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        return self.unavailable_response()
```

Esta decisión es arquitectónicamente correcta: jetpass-intelligence es un servicio de valor agregado que provee contexto y recomendaciones, pero no es un prerequisito para la operación del sistema transaccional. El piloto puede crear y presentar un plan de vuelo incluso si el microservicio de inteligencia está temporalmente indisponible. Los datos del plan son válidos con o sin las recomendaciones de inteligencia.

---

## 12. Configuración y gestión de entornos: pydantic-settings

La configuración de la aplicación está centralizada en una única clase `Settings` que hereda de `BaseSettings` de `pydantic-settings`. Esta elección ofrece tres ventajas sobre el manejo manual de variables de entorno con `os.environ`:

**Tipado y validación en startup**: los tipos de los campos (`str`, `int`, `float`, `str | None`) son validados por Pydantic al instanciar `Settings`. Si una variable de entorno requerida está ausente o tiene un formato incorrecto, la aplicación falla inmediatamente al arrancar con un error descriptivo, en lugar de fallar silenciosamente en tiempo de ejecución cuando se intenta usar el valor.

**Multi-entorno desde una única fuente**: en lugar de múltiples archivos `.env.dev`, `.env.test`, `.env.prod`, el sistema usa una única variable `APP_ENV` para seleccionar qué URL de base de datos y Redis usar:

```python
@property
def DATABASE_URL(self) -> str | None:
    if self.APP_ENV == "prod":
        return self.PROD_DATABASE_URL
    if self.APP_ENV == "test":
        return self.TEST_DATABASE_URL
    return self.DEV_DATABASE_URL
```

Esto simplifica la gestión de configuración y elimina el riesgo de apuntar accidentalmente al ambiente de producción en tests.

**Defaults explícitos como documentación**: los valores por defecto en la clase `Settings` documentan el comportamiento esperado en ausencia de configuración. El `ACCESS_TOKEN_EXPIRE_MINUTES: int = 15` no es solo un default; es una declaración de intención sobre la política de seguridad del sistema.

---

## 13. Testing: pytest + pytest-asyncio + aiosqlite

### Estrategia de testing por capas

El proyecto implementa tres niveles de cobertura de tests:

- **Tests unitarios de validaciones** (`test_flight_plan_validations.py`): funciones puras sin dependencias externas. Validan la lógica de negocio aeronáutica (formato ICAO, parsing HHMM, reglas Y/Z) en aislamiento total.
- **Tests de repositorios** (`test_*_repositories.py`): verifican que las queries SQLAlchemy producen el resultado correcto contra una base de datos real (SQLite en memoria).
- **Tests de integración API** (`test_flight_plans.py`, `test_auth.py`, etc.): ejercitan el stack completo desde la request HTTP hasta la base de datos usando `httpx.AsyncClient` con `ASGITransport`.

### SQLite en memoria como base de datos de test

La elección de SQLite en memoria para los tests es pragmática: elimina la necesidad de un servidor PostgreSQL real para ejecutar el suite de tests, lo que reduce la fricción del ciclo de desarrollo y facilita la ejecución en CI sin infraestructura adicional. El driver `aiosqlite` provee la interfaz async necesaria para compatibilidad con el resto del stack async.

La base de datos de test se crea fresh para cada test mediante `Base.metadata.create_all()` y se destruye al finalizar, garantizando el aislamiento entre tests:

```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

### Inyección de la base de datos de test

FastAPI expone `app.dependency_overrides`, un diccionario que permite reemplazar cualquier dependencia registrada con una implementación alternativa. En los tests, `get_db` se reemplaza por una función que devuelve la sesión de SQLite en memoria:

```python
app.dependency_overrides[get_db] = override_get_db
```

Este mecanismo permite testear el comportamiento real del stack de routing y validación sin modificar el código de producción.

### pytest-asyncio en modo automático

El archivo `pyproject.toml` configura `asyncio_mode = "auto"`, lo que elimina la necesidad de decorar cada test con `@pytest.mark.asyncio`. Todas las funciones de test `async def` son automáticamente reconocidas como coroutines y ejecutadas en el event loop de pytest-asyncio.

---

## 14. Servidor ASGI: Uvicorn

Uvicorn es el servidor ASGI que ejecuta la aplicación. La elección de un servidor ASGI (Asynchronous Server Gateway Interface) en lugar de WSGI (Web Server Gateway Interface) es consecuencia directa de la decisión de construir el stack de forma completamente asíncrona. WSGI es fundamentalmente síncrono; ASGI es el estándar Python para servidores y aplicaciones web asíncronos.

Uvicorn está instalado con el extra `[standard]`, que incluye `uvloop` en sistemas Unix y `httptools` como parser HTTP de alto rendimiento. `uvloop` es una implementación del event loop de Python basada en `libuv` (la misma biblioteca que usa Node.js), con mejoras de rendimiento de hasta 2-4x sobre el event loop estándar de `asyncio`. El punto de entrada del servidor es el módulo raíz `main.py`:

```python
# main.py (raíz del proyecto)
from app.main import app
```

Este archivo de un renglón actúa como adaptador entre la convención de `uvicorn main:app` y la ubicación real de la aplicación en `app/main.py`.

---

## 15. Redis: dependencia declarada, capacidad futura

El cliente `redis` está declarado como dependencia de producción en `pyproject.toml` y su URL de conexión está tipada en `Settings`, pero no hay ningún uso activo de Redis en el código actual. Esta presencia es una decisión de diseño deliberada que anticipa capacidades específicas:

**Rate limiting**: los endpoints públicos de autenticación (`/auth/login`, `/auth/register`) son candidatos naturales para rate limiting basado en IP o email. Redis es la solución estándar para este patrón por su soporte nativo de contadores con TTL.

**Caché de sesiones de acceso**: aunque los JWT son stateless por diseño, en escenarios de alto tráfico puede ser conveniente cachear la información del usuario (resultado de la query a `users` por `sub`) en Redis con un TTL igual a la vida del access token, eliminando la consulta a PostgreSQL en cada request autenticada.

**Pub/Sub para notificaciones en tiempo real**: el flujo de aprobación multiactor genera eventos de negocio (plan presentado, plan aprobado, plan rechazado) que son candidatos naturales a notificaciones push hacia la aplicación móvil del piloto y el dashboard. Redis Pub/Sub o Redis Streams proveen la infraestructura para este patrón sin introducir un broker de mensajes completo como Kafka o RabbitMQ.

---

## 16. Decisiones de diseño transversales

### UUIDs como claves primarias

Todas las entidades usan `UUID` como clave primaria generado con `uuid4`. Esta decisión tiene implicaciones de seguridad y escalabilidad. Los IDs secuenciales (enteros autoincrementales) exponen información sobre el volumen de datos (un atacante puede inferir cuántos planes de vuelo existen observando el ID del último plan creado) y son predecibles (facilitan la enumeración de recursos). Los UUIDs v4 son criptográficamente aleatorios, eliminan ambas vulnerabilidades y simplifican la generación de IDs en sistemas distribuidos donde múltiples nodos pueden crear entidades sin coordinación.

### Soft delete en recursos operativos

Las aeronaves (`aircraft`) y los aeródromos controlados (`controlled_aerodromes`) implementan soft delete mediante el campo `is_active: bool`. La aeronave nunca se elimina físicamente de la base de datos porque puede estar referenciada por planes de vuelo históricos. Un plan de vuelo archivado debe poder mostrar los datos de la aeronave que registró en su momento, aunque esa aeronave ya no esté operativa. El soft delete preserva la integridad referencial histórica sin necesidad de restricciones de FK complejas.

### CORS abierto en fase de desarrollo

La configuración `allow_origins=["*"]` es explícitamente un artefacto de la fase de desarrollo temprano. Esta configuración simplifica el ciclo de integración con los clientes (app móvil, dashboard) que pueden estar corriendo en múltiples orígenes durante el desarrollo. La restricción a orígenes específicos en producción es una tarea pendiente documentada en la arquitectura.

### Timestamps con timezone en todos los modelos

Todos los campos de fecha y hora usan `DateTime(timezone=True)`, almacenando los valores en UTC en PostgreSQL. Esto es esencial en un sistema de aviación: los horarios de los planes de vuelo (EOBT — Estimated Off-Block Time) se expresan en UTC por convención internacional (ICAO Doc 4444). Almacenar timestamps sin información de zona horaria introduciría ambigüedad que podría tener consecuencias operativas directas.
