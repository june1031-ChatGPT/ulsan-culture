# 울산컬처

아이를 둔 부모가 울산의 문화 프로그램을 미리 발견하고 접수 일정을 놓치지 않도록 돕는 서비스입니다. 현재 울산모아는 DB 저장 없는 단일 페이지 dry-run과 PostgreSQL 단일 페이지 ingest를 지원합니다. 전체 페이지 수집과 운영 scheduler는 포함하지 않습니다.

## 구성

- `frontend`: Next.js, TypeScript, Tailwind CSS
- `backend`: FastAPI, Pydantic, SQLAlchemy, Alembic
- `db`: PostgreSQL + PostGIS (Docker Compose)
- API: `GET /health`, `GET /api/events`

## Windows 설치 및 실행

필수 프로그램:

- Git
- Docker Desktop (실행된 상태)
- Python 3.11 이상
- Node.js 20.9 이상

PowerShell에서 저장소 루트를 기준으로 실행합니다. PowerShell 실행 정책 때문에 `npm.ps1`이 차단되는 환경에서도 동작하도록 아래 명령은 `npm.cmd`를 사용합니다.

### 1. 환경변수 준비

```powershell
Copy-Item .env.example .env
```

개발 환경이라도 `.env`의 `POSTGRES_PASSWORD`와 `DATABASE_URL` 비밀번호는 같은 값으로 변경하는 것을 권장합니다.

### 2. PostgreSQL + PostGIS 실행

```powershell
docker compose up -d db
docker compose ps
```

DB를 중지할 때는 다음을 실행합니다. 데이터 볼륨은 유지됩니다.

```powershell
docker compose down
```

### 3. Backend 설치 및 실행

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

확인 주소:

- Health: <http://localhost:8000/health>
- Events: <http://localhost:8000/api/events>
- API 문서: <http://localhost:8000/docs>

신규 DB에는 행사 데이터가 없으므로 `/api/events`의 `items`가 빈 배열인 것이 정상입니다.

### 울산모아 단일 페이지 dry-run

다음 명령은 실제 울산모아 목록 한 페이지만 읽고 내부 상세와 활성 날짜의 EXP/DAY 슬롯을 파싱합니다. DB 세션을 만들거나 저장하지 않으며, 실제 HTTP 요청 수를 결과에 표시합니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m app.crawlers.ulsan_moa.cli dry-run --source F300 --page 1
.\.venv\Scripts\python.exe -m app.crawlers.ulsan_moa.cli dry-run --source F400 --page 1
```

`--page-size`는 안전한 dry-run 범위인 1~12만 허용합니다. 단위 테스트는 fixture/mock만 사용하므로 실제 사이트를 호출하지 않습니다.

### 울산모아 단일 페이지 ingest

`ingest`는 F300 또는 F400 중 하나의 지정한 한 페이지만 수집해 `Source`, `Event`, `EventOccurrence`를 PostgreSQL에 upsert합니다. `--page-size`는 1~12만 허용하고 전체 페이지 옵션이나 반복 수집은 제공하지 않습니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m app.crawlers.ulsan_moa.cli ingest --source F300 --page 1
.\.venv\Scripts\python.exe -m app.crawlers.ulsan_moa.cli ingest --source F400 --page 1
```

각 Event와 그 회차는 하나의 트랜잭션으로 저장됩니다. 한 Event가 실패해도 다른 Event의 성공분은 유지하고, Source의 마지막 확인/성공/오류 통계는 배치 결과를 별도 트랜잭션에서 기록합니다. 부분 응답에서 누락된 회차는 삭제하지 않습니다.

### 4. Frontend 설치 및 실행

새 PowerShell 창에서 실행합니다.

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

브라우저에서 <http://localhost:3000>을 엽니다. 기본 API 주소는 `http://localhost:8000`입니다. 다른 주소를 사용할 때는 실행 전에 현재 PowerShell 세션에 환경변수를 지정합니다.

```powershell
$env:BACKEND_URL="http://localhost:8000"
npm.cmd run dev
```

## 테스트

Backend 테스트는 Docker 없이 메모리 SQLite에서 API 구조를 검증합니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
```

Frontend 테스트와 정적 검사는 다음과 같이 실행합니다.

```powershell
Set-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

## 데이터 원칙

행사 기간인 `event_start`/`event_end`와 접수 기간인 `registration_start`/`registration_end`는 DB 모델, API 응답, 화면에서 서로 다른 필드로 유지합니다. 프론트엔드에서 두 기간을 추정하거나 혼용하지 않습니다.
