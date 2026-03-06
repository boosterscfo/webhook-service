# EQQUALBERRY 메타 광고명 표준화 프로젝트

## 1. 프로젝트 개요

EQQUALBERRY(이퀄베리)의 Meta(Facebook/Instagram) 광고명이 현재 비표준 상태로 운영되고 있다. 광고명에서 정보를 기계적으로 파싱할 수 없고, Shopify URL/UTM 파라미터와의 연동도 불가능하다. 이 프로젝트는 **현재 Active인 광고들의 이름을 새 네이밍 규칙에 맞게 마이그레이션**하는 것이 목표다.

### 작업 범위
- Meta 광고 관리자에서 Active 상태인 광고 약 200~300개
- 캠페인명, 세트명, 광고명 3개 레벨 모두 대상
- 최종적으로 Meta Marketing API를 통해 이름을 일괄 변경

---

## 2. 현재 상태

### 2.1 기존 광고명 예시 (비표준)
```
260128_v-crm_ao_da_vd_kp_psy_20260128-1
260129_v-crm_ao_da_ig_bumpglow_belly_jyj_20260129-1
260202_v-crm_ao_da_vd_strawberrylegs_lsb_20260129-5
```

**문제점:**
- 세팅일자가 앞에 붙어있음 (불변이 아닌 값이 광고명에 포함)
- `ao` (상시/프모)가 광고명에 포함 (캠페인에 있어야 할 값)
- USP가 자유형: `kp`, `strawberrylegs`, `bumpglow_belly` 등 코드화 안 됨
- 제작자 번호 없음: `psy` → `psy01`이어야 함
- 언어 코드 없음
- 크리에이터명 위치 불명확

### 2.3 현재 마이그레이션 시트 상태
기존 288개 광고가 파싱되어 있으나, 구체계 기준:
- **J열(USP)**: 자유형 텍스트 (`kp`, `strawberrylegs`, `bumpglow_belly` 등 113개 유니크값)
- **Q열(신규 광고명)**: USP가 구체계 그대로 들어가 있어 신체계 규칙 미달
- **언어 필드**: 없음 (마이그레이션 시트 M열에 헤더는 있으나 대부분 비어있음)
- **제품 코드**: `v-crm`, `v-srm`만 있음 (신체계 `vt-crm`, `bk-crm` 등과 불일치 가능)

### 2.4 보유 인프라
- **DB**: MySQL, `facebook_id_*` (마스터) + `facebook_data_*` (성과) 테이블
- **API 수집**: Facebook Marketing API로 일별 성과 데이터 자동 수집 중
- **COO 서버**: 웹훅 엔드포인트 운영 중 (배포용, 무거운 쿼리 금지)
- **n8n**: Google Sheets 연동 등 자동화 워크플로 운영 중

---

## 3. 목표 상태 (신규 네이밍 규칙)

### 3.1 설계 원칙
> **광고명(소재ID)에는 "소재가 뭔지"만. "어디서 어떻게 쓰는지"는 캠페인/세트에.**

| 필드 | 변동성 | 넣을 곳 | 이유 |
|------|--------|---------|------|
| 캠페인 목표 (cv/tf/rt) | 변동 | 캠페인명 | 같은 소재를 전환→트래픽으로 옮길 수 있음 |
| 상시/프모 (ao/pm) | 변동 | 캠페인명 | 상시 소재를 프모에 재활용 가능 |
| 세팅일자 | 변동 | 세트명 | 같은 소재를 다른 날 재세팅 |
| 제품/제작유형/소재유형/USP/제작자/제작일/크리에이터 | **불변** | **소재ID(=광고명)** | 소재에 종속 |

### 3.2 소재ID(= 광고명) 구조

**소재 마스터 P열 수식 (=ground truth):**
```
{제품}_{제작유형}_{소재유형}_{USP1(카테고리)}_{제작자}_{제작일-버전}_{언어}[_{크리에이터}]
```

| 위치 | 필드 | 예시 | 파싱 | 비고 |
|------|------|------|------|------|
| [0] | 제품 | `bk-crm` | `parts[0]` | 제품 코드 시트 참조 |
| [1] | 제작유형 | `pa` | `parts[1]` | da/pa/ugc |
| [2] | 소재유형 | `vd` | `parts[2]` | ig/vd/hvd/crs/rl |
| [3] | USP1 (카테고리) | `Body` | `parts[3]` | body/face. **대문자 시작** |
| [4] | 제작자 | `lsb01` | `parts[4]` | 이니셜+번호 |
| [5] | 제작일-버전 | `260218-01` | `parts[5]` | YYMMDD-N |
| [6] | 언어 | `en` | `parts[6]` | en/es/ko/pt |
| [7:] | 크리에이터 | `brooke-burke` | `"_".join(parts[7:])` | PA만. DA는 없음 |

> ⚠️ USP2(부위)와 USP3(고민)는 소재ID에 포함되지 않음. 소재 마스터의 E열, F열에만 기록되며, 분석 시 소재 마스터를 참조.
> ⚠️ USP1(카테고리)는 `Body`, `Face`처럼 대문자로 시작 (USP 코드 시트의 영문명 기준).

**완성 예시 (실제 생성값):**
```
PA (크리에이터 있음): bk-crm_pa_vd_Body_lsb01_260218-01_en_brooke-burke
PA (스페인어):       bk-crm_pa_vd_Body_psy01_260218-02_es_dr-farzan
DA (크리에이터 없음): vt-srm_da_ig_Body_lsb01_260220-01_en
```

### 3.3 캠페인명 구조
```
[이퀄베리][Amazon(USA)][US]_{제품}_{목표}_{상시/프모}
```
예: `[이퀄베리][Amazon(USA)][US]_vt-srm_cv_ao`

수식: `="[이퀄베리][Amazon(USA)][US]_" & 제품 & "_" & 목표 & "_" & 상시프모`

### 3.4 세트명 구조
```
{제품}_{세팅일자(YYMMDD)}
```
예: `vt-srm_260221`

수식: `=제품 & "_" & 세팅일자`

### 3.4b 광고 이름
```
광고 이름 = 소재ID (그대로)
```
광고 세팅 시트 N열 수식: `=A` (소재ID를 그대로 사용)

### 3.4c 쇼피파이 태그
```
{제품}_{상시/프모}_{세팅일자}
```
예: `vt-srm_ao_260221`

### 3.4d UTM 구조
- 베이스 URL: `https://eqqualberryglobal.com/products/{소재ID}`
- 최종 URL: `{베이스URL}?utm_source={UTM Source}`
- UTM Source: 광고 세팅 시트 P열에서 수동 선택 (IG/FB 등)

### 3.5 구분자 규칙
- **언더바(`_`)**: 필드 간 구분자
- **하이픈(`-`)**: 필드 내 단어 연결 (제품코드의 `bk-crm`, 제작일의 `260218-01` 등)
- 크리에이터가 마지막 위치: 크리에이터 핸들에 언더바가 있어도 `"_".join(parts[7:])`로 안전하게 복원

### 3.6 소재 마스터 P열 수식 (실제 소재ID 생성 로직)
```
=A & "_" & B & "_" & C & "_" & D & "_" & G & "_" & H & "_" & I & IF(O<>"", "_" & O, "")
```
즉: `{제품}_{제작유형}_{소재유형}_{USP1}_{제작자}_{제작일-버전}_{언어}[_{크리에이터(변환)}]`

> ⚠️ 설계 원칙 시트(row 18~32)는 USP 3분류 도입 전 버전이라 언어 필드가 빠져있고, USP 위치가 `[3]`에 `dark-circles` 같은 자유형으로 되어 있음. **소재 마스터 수식이 현재 ground truth.**

---

## 4. 코드 레지스트리 (유효한 값 목록)

### 4.1 제품 코드
| alias | 제품명 |
|-------|--------|
| bk-srm | 바쿠치올플럼핑세럼 |
| vt-srm | 비타민일루미네이팅세럼 |
| bk-crm | 바쿠치올플럼핑캡슐크림 |
| bk-tnr | 바쿠치올플럼핑캡슐토너 |
| al-srm | 알로에PDRN카밍세럼 |
| ht-srm | 히알토인플러딩세럼 |
| nd-srm | NAD+펩타이드부스팅세럼 |
| vt-tnr | 비타민일루미네이팅토너 |
| vt-crm | 비타민일루미네이팅크림 |
| al-tnr | 알로에PDRN카밍토너 |
| nd-tnr | 엔에이디플러스펩타이드부스팅토너 |
| nd-crm | 엔에이디플러스펩타이드부스팅크림 |
| ht-tnr | 히알토인플러딩토너 |

**참고**: 기존 광고에서 쓰이던 `v-crm`, `v-srm` 코드는 제품 코드 시트에 등록되어 있지 않다. 현재 시트에 등록된 코드는 `vt-crm`, `vt-srm`, `bk-crm` 등이다. 마이그레이션 시 기존 코드 → 신규 코드 매핑이 필요할 수 있음.

### 4.2 일반 코드
| 카테고리 | 코드 | 의미 |
|---------|------|------|
| 캠페인 목표 | `cv` | 전환 (Conversion) |
| | `tf` | 트래픽 (Traffic) |
| | `rt` | 리타겟 (Retargeting) |
| | `aw` | 인지도 (Awareness) |
| | `eg` | 참여 (Engagement) |
| 상시/프모 | `ao` | 상시 (Always-on) |
| | `pm` | 프로모션 (Promotion) |
| 제작유형 | `da` | DA - 직접 제작 |
| | `pa` | PA - 파트너/크리에이터 |
| | `ugc` | UGC (향후) |
| 소재유형 | `ig` | 이미지 |
| | `vd` | 영상 |
| | `hvd` | 분할영상 |
| | `crs` | 캐러셀 |
| | `rl` | 릴스전용 |
| 언어 | `en` | 영어 |
| | `es` | 스페인어 |
| | `ko` | 한국어 |
| | `pt` | 포르투갈어 |

### 4.3 USP 코드 (3분류 체계)
USP는 소재 마스터에서 3개 열(D, E, F)로 관리되지만, **소재ID에는 USP1(카테고리)만 포함**된다.

**USP1: 카테고리 (소재ID [3]번 위치에 들어감):**
| 코드 | 한글 | 소재ID 표기 |
|------|------|------------|
| body | 몸 | `Body` (대문자) |
| face | 얼굴 | `Face` (대문자) |

**USP2: 부위 (소재 마스터 E열에만 기록, 소재ID에는 미포함):**
| 코드 | 한글 | 카테고리 |
|------|------|---------|
| armp | 겨드랑이 | body |
| elbow | 팔꿈치 | body |
| hip | 엉덩이 | body |
| groin | 사타구니 | body |
| chest | 가슴 | body |
| back | 등 | body |
| farm | 팔뚝 | body |
| calf | 종아리 | body |
| thigh | 허벅지 | body |
| hand | 손 | body |
| belly | 배 | body |
| neck | 목 | body |
| knee | 무릎 | body |
| ankle | 복숭아뼈 | body |
| heel | 발꿈치 | body |
| toe | 발가락 | body |
| eye | 눈 | face |
| lip | 입술 | face |
| phlm | 인중 | face |
| cheek | 볼 | face |
| glbla | 미간 | face |

**USP3: 고민 (소재 마스터 F열에만 기록, 소재ID에는 미포함):**
| 코드 | 한글 |
|------|------|
| color | 착색 |
| krtpl | 모공각화증 (Keratosis Pilaris) |
| wrnk | 주름 |
| elst | 탄력 |
| white | 미백 |
| hydr | 수분 |
| glow | 광채 |
| pacne | 포스트아크네 |
| spot | 기미 (Dark Spot) |

### 4.4 제작자 코드
`{이니셜}{번호}` 형태. 예: `lsb01`, `psy01`, `jyj01`
- 동명이인 시 번호 증가 (`lsb02`)

### 4.5 크리에이터 매핑
| 원본 (인스타 핸들) | 변환 | 규칙 |
|-------------------|------|------|
| dr.farzan | dr-farzan | `.` → `-` |
| makeup_mabell | makeup_mabell | 유지 |
| milkydew_ | milkydew_ | 유지 |
| _lilyis | _lilyis | 유지 |
| eman__ar1 | eman__ar1 | 유지 |
| __bexbeauty__ | __bexbeauty__ | 유지 |

기본 규칙: `.`만 `-`로 변환, 언더바는 유지 (마지막 필드라 파싱에 문제없음)

---

## 5. 데이터 소스 (DB 스키마)

### 5.1 테이블 관계
```
facebook_id_campaigns (캠페인 마스터)
  └─ facebook_id_adsets (세트 마스터, FK: campaign_id → campaigns.id)
      └─ facebook_id_ads (광고 마스터, FK: adset_id → adsets.id)
          └─ facebook_data_ads (일별 성과, FK: facebook_id_ad_id → ads.id)
```

### 5.2 ⚠️ 중요: ID 매핑 주의
- `facebook_data_ads.facebook_id_ad_id` → `facebook_id_ads.id` (내부 auto_increment, 1~26000 범위)
- `facebook_id_ads.ad_id` → Meta의 실제 광고 ID (예: `'120243562759290592'`)
- **이 두 개를 혼동하면 조회 결과가 0건이 됨!**

### 5.3 주요 컬럼
**facebook_id_ads:**
- `id`: 내부 PK (성과 테이블 조인 키)
- `ad_id`: Meta 광고 ID (API 호출 시 사용)
- `name`: 현재 광고명
- `status`: ACTIVE / PAUSED 등
- `start_time`: 광고 세팅일

**facebook_id_adsets:**
- `id`: 내부 PK
- `adset_id`: Meta 세트 ID
- `name`: 세트명
- `status`: ACTIVE / PAUSED 등
- `start_time`: 세트 세팅일

**facebook_id_campaigns:**
- `id`: 내부 PK
- `campaign_id`: Meta 캠페인 ID
- `name`: 캠페인명
- `status`: ACTIVE / PAUSED 등

### 5.4 데이터 조회 쿼리
별첨 `변경대상광고_쿼리_v1.2.sql` 참조. 3개 쿼리를 순서대로 실행 후 Python에서 merge.

---

## 6. 작업 단계

### Phase 1: 데이터 추출 + 파싱 (Python, 로컬)

**Step 1.1**: DB에서 Active 광고 목록 추출
- `변경대상광고_쿼리_v1.2.sql`의 Step 1 실행
- 결과: `internal_ad_id`, `meta_ad_id`, `ad_name`, `campaign_name`, `adset_name`, `adset_start_time` 등

**Step 1.2**: 성과 데이터 추출 + merge
- Step 2 (30일), Step 3 (전체) 실행
- `internal_ad_id` 기준 pandas merge

**Step 1.3**: 기존 광고명 파싱
- 기존 광고명에서 추출 가능한 필드를 자동 파싱
- 제품, 제작유형, 소재유형, 제작자, 제작일-버전은 비교적 규칙적
- 구체계 USP는 원본 그대로 보존 (별도 열)

### Phase 2: USP 매핑 (AI 활용)

**Step 2.1**: 구체계 USP → 신체계 USP 매핑
- 기존 마이그레이션 시트의 J열에는 구체계 USP가 자유형으로 들어가 있음 (예: `kp`, `strawberrylegs`, `bumpglow_belly`)
- 이것을 신체계 3분류(USP1: 카테고리, USP2: 부위, USP3: 고민)로 매핑
- 단, 소재ID에는 USP1(카테고리, Body/Face)만 들어가고, USP2/USP3는 소재 마스터에만 기록
- 매핑 불가능한 항목 식별 (프로모 카피, 크리에이터명이 USP에 들어간 경우 등)

**Step 2.2**: 매핑 결과를 엑셀로 출력
- 자동 매핑된 항목: 녹색
- 수동 확인 필요: 노란색
- 매핑 불가: 빨간색
- 실무자가 검토 + 보정

### Phase 3: 마이그레이션 시트 생성

**Step 3.1**: 신규 이름 생성
- 파싱된 필드 + 매핑된 USP로 신규 소재ID 자동 생성
- 신규 캠페인명, 세트명도 자동 생성

**Step 3.2**: 변경 전/후 비교
- 기존 이름 vs 신규 이름 나란히 표시
- 차이가 없는 항목은 SKIP 플래그
- spend 기준 우선순위 표시

### Phase 4: Meta API 변경 실행 (COO 서버)

**Step 4.1**: dry-run (로컬)
- 실제 API 호출 없이 변경 대상 목록만 출력
- 최종 검토

**Step 4.2**: 실제 변경 (COO 서버 배포)
- Meta Marketing API POST로 이름 변경
- `POST https://graph.facebook.com/v22.0/{ad-id}?name={new_name}`
- 캠페인, 세트, 광고 순서로 변경
- 변경 성공/실패 로그 기록

### Phase 5: 운영 자동화 (n8n, 이후)

- 신규 광고 생성 시 네이밍 규칙 준수 여부 자동 체크
- 규칙 위반 시 슬랙 알림
- 정기적으로 Active 광고 전수 검사

---

## 7. 제약조건 및 주의사항

### 절대 하지 말 것
- ❌ 운영 서버에서 무거운 쿼리 실행 (서버 다운 경험 있음)
- ❌ `facebook_data_ads`를 여러 번 직접 JOIN (카디널리티 폭발)
- ❌ `facebook_id_ads.ad_id`와 `facebook_data_ads.facebook_id_ad_id`를 혼동
- ❌ 검증 없이 Meta API로 이름 변경 실행

### 반드시 지킬 것
- ✅ 무거운 쿼리는 로컬에서 실행
- ✅ 성과 데이터는 서브쿼리 대신 별도 쿼리 → Python merge
- ✅ 모든 변경은 dry-run 후 실행
- ✅ 변경 전/후 비교 데이터를 반드시 보존
- ✅ spend 높은 광고일수록 신중하게 (임팩트 큼)

### 기술 스택
- **개발**: Python (pandas, openpyxl, requests)
- **DB 접속**: pymysql 또는 mysql-connector
- **API**: Meta Marketing API v22.0
- **배포**: COO 서버 (웹훅 엔드포인트 기구축)
- **자동화**: n8n (Phase 5)

---

## 8. 참조 파일

| 파일 | 설명 |
|------|------|
| `_EQB__US_Parameter_Rebuild.xlsx` | 네이밍 규칙, 코드 레지스트리, 소재 마스터, 마이그레이션 시트 포함 |
| `변경대상광고_쿼리_v1.2.sql` | DB 조회 쿼리 (3단계 분리) |
| 본 문서 (`PROJECT_SPEC.md`) | AI 코드 작업 지시서 |
