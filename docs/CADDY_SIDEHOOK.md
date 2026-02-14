# Caddy sidehook 등록

웹훅 서비스를 `sidehook.boosters-labs.com`으로 Caddy 리버스 프록시에 등록하는 방법입니다.

## 사전 조건

- `~/caddy`에서 Caddy가 실행 중 (bi-lab, exolyt 등과 동일한 구성)
- `coo-network` Docker 네트워크 존재

## 1. Caddyfile에 sidehook 블록 추가

`~/caddy/Caddyfile`을 열고 다음 블록을 추가합니다 (기존 bi-lab, exolyt 블록과 같은 수준에):

```caddy
sidehook.boosters-labs.com {
	reverse_proxy webhooks:9000
}
```

## 2. webhooks 컨테이너를 coo-network에 연결

webhooks 프로젝트에서 프로덕션 compose로 기동:

```bash
cd ~/webhooks  # 또는 webhooks 프로젝트 경로
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml docker compose up -d
```

## 3. Caddy 재시작

```bash
cd ~/caddy
docker compose restart caddy
```

## 4. DNS 설정

`sidehook.boosters-labs.com` CNAME이 Caddy 서버(또는 로드밸런서)를 가리키도록 설정합니다.  
bi-lab.boosters-labs.com과 동일한 레코드 타입/대상이면 됩니다.

## 확인

- https://sidehook.boosters-labs.com/health → `{"status":"ok"}`
- 웹훅 엔드포인트: https://sidehook.boosters-labs.com/webhooks/...
