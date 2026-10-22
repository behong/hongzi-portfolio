# hongzi.us 포트폴리오

이 Windows PC에서 Docker Desktop과 Cloudflare Tunnel로 운영하는 정적 HTML 사이트입니다. 기본 주소는 `https://hongzi.us`, `www.hongzi.us`는 경로와 쿼리를 유지해 기본 주소로 301 이동합니다. 공유기 포트 포워딩이나 공인 IP 고정은 필요 없습니다.

## 구성

- [docker-compose.yml](docker-compose.yml): Caddy 웹 서버와 cloudflared 터널을 실행합니다. 웹 서버가 정상 응답한 뒤 터널이 시작됩니다.
- [Caddyfile](Caddyfile): HTML 제공과 www 리디렉션을 설정합니다.
- [cloudflared.yml](cloudflared.yml): 두 도메인을 Docker 내부의 `http://web:80`으로 연결합니다.
- `site/index.html`: 첫 화면. 추가 페이지는 `/seedance.html`, `/fpv.html`로 열립니다.
- `.secrets/tunnel.json`: 이 PC에서 생성한 터널 인증 파일입니다. GitHub 업로드에서 제외되며 별도 비공개 백업이 필요합니다.

외부 방문자는 Cloudflare HTTPS로 접속하고, Cloudflare와 PC 사이는 암호화된 Tunnel을 사용합니다. Caddy는 Docker 내부 HTTP를 제공하므로 원본 서버용 공개 인증서 발급이나 TCP 80·443 개방은 필요 없습니다. PC 미리보기는 `http://localhost:8080`이며 이 포트는 루프백에만 바인딩합니다.

## 이 PC에서 실행

Docker Desktop을 열고 Linux 컨테이너 엔진이 준비된 상태에서 이 폴더의 PowerShell로 실행합니다.

```powershell
.\Start-Portfolio.ps1
```

스크립트는 엔진 연결, Compose 구성, Caddy 설정을 검증한 뒤 컨테이너를 시작합니다. 실행 정책으로 차단되는 경우 이번 실행에만 다음과 같이 지정할 수 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Portfolio.ps1
```

터널 없이 로컬 미리보기만 시작하려면 다음을 사용합니다. 이미 실행 중인 터널을 중지하는 명령은 아닙니다.

```powershell
.\Start-Portfolio.ps1 -LocalOnly
```

Docker 명령이 `permission denied`로 실패하면 일반 PowerShell에서 `docker info`가 성공하는지 먼저 확인합니다. 제한된 작업 환경에서만 거부되면 일반 PowerShell에서 실행해야 합니다.

## Cloudflare 도메인 연결

이 프로젝트용 `hongzi-portfolio` 터널을 생성했습니다. 터널 ID와 로컬 라우팅 규칙은 [cloudflared.yml](cloudflared.yml)에 있습니다. 기존 `Home` 터널은 변경하지 않았습니다.

1. 컨테이너를 시작한 뒤 `docker compose logs --tail=100 tunnel`에서 연결 성공을 확인합니다.
2. 아래 명령으로 도메인을 연결합니다. 이 명령은 Cloudflare 로그인 인증서가 있는 PC에서 실행해야 합니다.

```powershell
cloudflared tunnel route dns hongzi-portfolio hongzi.us
cloudflared tunnel route dns hongzi-portfolio www.hongzi.us
```

기존 A·AAAA·CNAME 레코드가 있으면 명령이 충돌로 실패할 수 있습니다. 기존 서비스의 대상을 먼저 확인한 뒤 포트폴리오로 전환할 레코드만 Cloudflare DNS 화면에서 정리하고 재실행합니다. 다른 서브도메인과 기존 터널은 유지합니다. 이 프로젝트는 로컬 관리 터널이므로 ingress 규칙은 대시보드가 아닌 `cloudflared.yml`에서 관리합니다.

3. Cloudflare에서 두 주소의 Edge 인증서가 활성 상태인지 확인합니다.
4. **SSL/TLS → Edge Certificates → Always Use HTTPS**를 켭니다. 기본 주소의 HTTP→HTTPS 전환은 Cloudflare에서 처리합니다. SSL 암호화 모드는 Flexible을 사용하지 않습니다. Tunnel의 내부 HTTP 서비스는 Caddy 공개 인증서 발급 없이 동작합니다.
5. 외부 네트워크에서 접속을 확인합니다.

```powershell
curl.exe -I https://hongzi.us
curl.exe -I 'https://www.hongzi.us/fpv.html?from=www'
curl.exe -I http://hongzi.us
```

기본 주소는 200, www는 `https://hongzi.us/fpv.html?from=www`로 301, HTTP는 HTTPS로 이동해야 합니다.

## PC 상시 운영

Docker Desktop의 **Settings → General → Start Docker Desktop when you sign in to your computer**를 켭니다. 컨테이너는 `restart: unless-stopped`로 Docker 엔진 시작 시 복구됩니다. 직접 중지한 컨테이너는 시작 스크립트를 다시 실행합니다. Windows 로그인 후 Docker Desktop이 실행되어야 하며, PC가 꺼지거나 절전 상태이거나 인터넷이 끊기면 사이트에 접속할 수 없습니다. 전원 연결 상태의 절전 설정을 운영 목적에 맞게 조정합니다.

## 수정과 운영

```powershell
# 상태와 로그
docker compose ps
docker compose logs --tail=100 web tunnel

# Caddy 설정 검증과 반영
docker compose exec web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose exec web caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

# 터널 라우팅 수정 반영
docker compose restart tunnel

# 전체 중지
docker compose down
```

HTML은 `site/` 파일 교체만으로 반영됩니다. Cloudflare 캐시 규칙을 설정했다면 해당 캐시도 갱신합니다. 이미지는 자동 업데이트하지 않으므로 업데이트할 때 `docker compose pull` 후 시작 스크립트를 실행합니다.

## GitHub에서 복원

저장소를 복제한 뒤 `.secrets` 폴더를 만들고 비공개 백업의 `tunnel.json`을 `.secrets/tunnel.json`으로 복원합니다. 그 다음 시작 스크립트를 실행합니다. GitHub에는 터널 인증 파일과 Cloudflare 로그인 인증서를 올리지 않습니다. 터널을 새로 생성한 경우 `cloudflared.yml`의 ID와 DNS 연결도 새 터널에 맞춰 변경해야 합니다.

## 자동 검사 예제

[checks/github-actions.yml](checks/github-actions.yml)은 Compose·Caddy 설정과 실제 페이지 응답, www 리디렉션을 검사하는 GitHub Actions 예제입니다. 현재 GitHub 인증에 workflow 쓰기 권한이 없어 자동 실행은 활성화하지 않았습니다. 활성화하려면 GitHub에서 `.github/workflows/validate.yml` 경로에 이 내용을 저장합니다. 검사에서는 웹 서버만 실행하며 터널 인증 파일은 사용하지 않습니다.

## 공식 문서

- [Cloudflare Tunnel 설정](https://developers.cloudflare.com/tunnel/get-started/)
- [로컬 관리 터널 설정 파일](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/)
- [Docker Desktop 자동 시작 설정](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
