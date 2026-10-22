# Windows PC 포트폴리오 운영 인수인계

작성 기준: 2026-10-22. 기존 사이트에서 완료한 작업과 같은 PC에 두 번째 사이트를 구성할 때 필요한 내용을 정리했다. 실행 명령의 최신 기준은 [README.md](README.md), 실제 설정값은 각 구성 파일이다.

## 1. 기존 사이트와 완료한 작업

| 항목 | 현재 구성 |
| --- | --- |
| 작업 폴더 | `C:\Users\Administrator\code\Home-261022` |
| 공개 주소 | `https://hongzi.us` |
| 보조 주소 | `https://www.hongzi.us` → 기본 주소로 301 이동 |
| GitHub | https://github.com/behong/hongzi-portfolio · 공개 저장소 · `main` |
| 운영 장비 | 사용자 Windows PC, Docker Desktop의 Linux 컨테이너 |
| 사이트 | `site/`의 정적 HTML, 별도 DB 없음 |
| 웹 서버 | Caddy, `caddy:2-alpine` |
| 외부 연결 | Cloudflare Tunnel, `cloudflare/cloudflared:latest` |
| 자동 반영 | GitHub `main`을 60초마다 확인하여 작업 파일 동기화 |

완료한 작업:

- 도메인과 www 리디렉션을 구성하고 Docker 실행 스크립트를 만들었다.
- 전용 터널 `hongzi-portfolio`를 생성했다. 실제 ID와 ingress 규칙은 [cloudflared.yml](cloudflared.yml)을 참고한다.
- 두 도메인의 DNS를 이 터널로 연결했다. 사용자 요청에 따라 기존 Hongzi Lab 블로그의 기본 도메인 연결을 포트폴리오로 교체했다.
- 기존 블로그 데이터와 `Home` 터널 자체는 삭제하지 않았다. 전환 전 기본 도메인의 DNS 정보는 로컬 `.secrets/dns-before-portfolio.json`에 보관했다.
- 외부에서 기본 페이지와 추가 HTML 두 개의 HTTP 200, www의 경로·쿼리 유지 301, HTTP→HTTPS 전환을 확인했다.
- GitHub 공개 저장소에 소스와 운영 파일을 올렸다. 터널 인증 파일은 올리지 않았다.
- 사이트 이름을 `HongSungIn`으로 변경한 원격 커밋을 내려받아 실제 사이트 반영을 확인했다.
- 자동 감시 프로세스를 시작했고 원격에만 추가한 커밋을 감시 프로세스가 직접 내려받는 것까지 검증했다.

위 상태는 이 작업에서 확인한 결과다. 이후 세션에서는 아래 명령으로 실행 상태와 마지막 동기화 시각을 다시 확인한다.

## 2. 요청이 들어와 화면에 도달하는 경로

```text
방문자 → Cloudflare HTTPS → 암호화된 Tunnel → cloudflared 컨테이너
       → Docker 내부 http://web:80 → Caddy → site/ HTML
```

기본 운영 구성은 PC의 호스트 포트를 바인딩하지 않는다. 처음에는 `127.0.0.1:8080`을 사용했지만 Windows에서 포트 바인딩이 거부되어 제거했다. 다른 포트로 바꾸는 대신 Tunnel 운영에서 불필요한 포트 공개를 없앴다.

Caddy는 Docker 내부에서 HTTP를 제공한다. 공유기 포트 포워딩과 원본 서버용 공개 HTTPS 인증서 발급은 이 구성에 필요 없다. 기본 도메인의 HTTP→HTTPS 처리는 Cloudflare에서 확인했다.

## 3. 주요 파일

| 파일 | 용도 |
| --- | --- |
| [docker-compose.yml](docker-compose.yml) | 웹 서버와 터널, 내부 healthcheck, 재시작 정책, 인증 파일 마운트 |
| [Caddyfile](Caddyfile) | 정적 파일 제공, www→기본 도메인 이동, 압축 |
| [cloudflared.yml](cloudflared.yml) | 터널 ID와 두 도메인의 ingress, 마지막 404 규칙 |
| [Start-Portfolio.ps1](Start-Portfolio.ps1) | Docker 연결·Compose·Caddy 검증 후 기동 |
| [docker-compose.preview.yml](docker-compose.preview.yml) | 선택적인 로컬 미리보기 포트 추가 |
| [AutoSync.py](AutoSync.py) | GitHub 감시와 파일 동기화 |
| [Start-AutoSync.ps1](Start-AutoSync.ps1) | 감시 시작·상태·중지, 로그인 자동 시작 등록 |
| [checks/test_autosync.py](checks/test_autosync.py) | 동기화와 충돌·실패·파일 구조 전환 테스트 |
| [checks/github-actions.yml](checks/github-actions.yml) | GitHub Actions 검사 예제, 자동 실행은 미활성화 |
| `.secrets/tunnel.json` | 해당 터널의 비밀 인증 파일, 로컬 보관·별도 비공개 백업 |
| `.tools/autosync/` | 감시 상태·로그·잠금·변경 전 파일 백업, Git 제외 |

`site/index.html`이 첫 화면이며 추가 페이지는 `site/seedance.html`, `site/fpv.html`이다. HTML은 읽기 전용 디렉터리 마운트로 제공하므로 PC에서 파일을 갱신하면 실행 중인 사이트에 반영된다.

## 4. 기존 사이트 운영 명령

프로젝트 폴더의 일반 PowerShell에서 실행한다.

```powershell
Set-Location C:\Users\Administrator\code\Home-261022

# 사이트 기동과 상태
.\Start-Portfolio.ps1
docker compose ps
docker compose logs --tail=100 web tunnel

# 선택적인 미리보기: http://localhost:18080
.\Start-Portfolio.ps1 -LocalOnly
# 미리보기 포트도 사용 불가할 때
.\Start-Portfolio.ps1 -LocalOnly -PreviewPort 28080

# GitHub 감시 시작과 로그인 자동 시작 등록
.\Start-AutoSync.ps1 -Install
.\Start-AutoSync.ps1 -Status
Get-Content .tools\autosync\watcher.log -Tail 20
Get-Content .tools\autosync\heartbeat.json

# 동기화 동작 테스트
python -m unittest discover -s checks -p 'test_*.py'

# 외부 접속 확인
curl.exe -I https://hongzi.us
curl.exe -I 'https://www.hongzi.us/fpv.html?from=www'
curl.exe -I http://hongzi.us
```

`-LocalOnly`는 웹 서버만 시작하며 이미 실행 중인 터널을 중지하지 않는다. 감시 중지는 `.\Start-AutoSync.ps1 -Stop`이며 로그인 자동 시작 작업도 해제한다. 전체 컨테이너 중지는 `docker compose down`이다.

## 5. 자동 감시의 정확한 동작과 범위

이 폴더의 로컬 Git 저장소는 초기화만 되었고, 이 작업 환경의 `.git` 쓰기 제한 때문에 정상적인 clone/pull 상태로 연결하지 못했다. 따라서 **자동 반영은 실제 `git pull`이 아니라 GitHub API로 작업 파일을 동기화하는 방식**이다. 로컬 Git 브랜치·인덱스·커밋 이력은 갱신하지 않는다.

- Python 3.9 이상과 로그인된 GitHub CLI가 필요하다. `gh auth status`로 확인한다.
- `main` 커밋이 바뀌면 트리를 조회하고 변경된 파일만 다운로드한다. 다운로드한 파일의 Git blob 해시를 검증한다.
- HTML 변경은 즉시 반영한다. Docker·Caddy·터널 설정 변경은 파일을 받고 재실행 안내를 로그에 남기며, 사용자가 운영 스크립트로 적용한다.
- 감시 프로그램 자체의 새 코드는 감시를 중지하고 다시 시작해야 적용된다.
- 로컬 수정과 원격 변경이 충돌하면 로컬 내용을 보존하고 전체 동기화를 중단한다. 로그를 확인해 파일을 정리하면 다음 주기에 재시도한다.
- 변경 전 파일은 `.tools/autosync/backups/커밋ID/`에 백업한다. 네트워크 실패 시 기존 파일을 유지하고 재시도한다.
- `.git`, `.secrets`, `.tools`, `.env` 계열 보호 경로는 덮어쓰지 않는다. 원격 트리에 보호 경로가 들어오면 업데이트를 중단한다.
- `state.json`은 마지막 반영 커밋과 파일 해시, `heartbeat.json`은 최근 확인 시각과 성공 여부다. `.tools`를 다른 사이트에 복사하지 않는다.

파일 추가·삭제·백업, 로컬 충돌, 다운로드 실패, 경로 보호, 중간 적용 복구, 다운로드 중 수정, 파일↔디렉터리 전환과 미추적 파일 보존을 포함한 테스트 11개를 통과했다.

## 6. 권한 제한과 확인하지 못한 항목

이 Codex 작업 환경에서는 다음 제한이 실제로 발생했다. 다른 세션의 권한도 같다고 가정하지 말고 먼저 확인한다.

| 제한 | 처리 |
| --- | --- |
| Docker named pipe 접근 `permission denied` | 사용자 일반 PowerShell에서 실행 스크립트를 돌려 기동했다. 컨테이너 상태는 사용자 출력과 Cloudflare 연결·외부 응답으로 확인했다. |
| `.git/index.lock`, `.git/FETCH_HEAD` 쓰기 거부 | GitHub API로 업로드·다운로드했다. Git 작업 성공으로 보고하면 안 된다. |
| 작업 스케줄러 CIM 접근 거부 | 현재 세션의 감시 프로세스는 시작했다. 로그인 자동 시작 등록 완료는 확인하지 못했으므로 일반 PowerShell에서 `Start-AutoSync.ps1 -Install` 후 확인해야 한다. |
| GitHub 인증에 `workflow` 쓰기 권한 없음 | `.github/workflows/` 업로드는 거부됐다. 실행 가능한 검사 예제는 `checks/github-actions.yml`에 보관했다. |
| Windows `curl.exe`의 Schannel 인증 오류 | Python 표준 라이브러리의 HTTPS 요청으로 외부 응답을 검증했다. TLS 검증을 끄지는 않았다. |

Docker Desktop의 로그인 시 자동 시작 설정과 Windows 절전 설정은 안내했지만 실제 설정 변경 완료는 확인하지 못했다. PC 전원·로그인·인터넷과 Docker Desktop이 유지되어야 사이트와 감시가 동작한다.

## 7. 두 번째 사이트에서 반드시 분리할 값

기존 사이트의 설정을 그대로 실행하면 컨테이너 충돌이나 잘못된 도메인 연결이 생길 수 있다. 새 프로젝트의 실제 도메인·폴더·저장소를 확인하고 다음을 바꾼다.

| 항목 | 새 사이트 처리 |
| --- | --- |
| 작업 폴더와 GitHub 저장소 | 새 사이트 전용으로 사용. 공개 여부도 해당 요청에 맞춘다. |
| Compose 프로젝트 | 기존과 다른 프로젝트 이름 사용. 현재 고정 `container_name`인 `portfolio-web`, `portfolio-tunnel`도 변경하거나 제거한다. |
| Caddy 도메인 | `@www` 호스트와 리디렉션 목적지를 새 도메인으로 변경한다. |
| Cloudflare Tunnel | 새 사이트 전용 이름·ID·인증 파일을 만든다. 기존 터널 ID나 인증 파일을 재사용하지 않는다. |
| 터널 ingress와 DNS | 새 도메인만 새 터널에 연결한다. 같은 Compose 내부라면 `http://web:80`은 유지할 수 있다. |
| 자동 감시 | `AutoSync.py`의 `REPOSITORY`를 새 저장소로 변경. 다른 브랜치를 사용하면 `head()`의 `main`도 변경한다. |
| 로그인 자동 시작 | `Start-AutoSync.ps1`의 `$taskName`을 새 이름으로 변경하여 기존 작업과 분리한다. |
| 감시 상태와 백업 | 새 폴더에서 새로 생성한다. 기존 `.tools`를 가져오지 않는다. |
| 미리보기 포트 | 두 사이트를 동시에 미리볼 경우 서로 다른 포트를 선택한다. 운영 모드에는 호스트 포트가 없다. |

새 사이트용으로 기존 `hongzi.us`·`www.hongzi.us` DNS, 기존 저장소, 컨테이너, 자동 시작 작업을 수정하지 않는다. 기존 DNS 대상이 있는 새 도메인을 전환해야 하면 기존 서비스를 확인하고 변경 전 레코드를 비공개 백업한다.

## 8. 다른 Codex에 전달할 업무 지시문

아래 내용을 새 프로젝트 폴더의 Codex에 전달하고, 대괄호를 실제 값으로 바꾼다.

> 이 문서는 같은 Windows PC에서 먼저 구축한 사이트의 인수인계다. 기존 사이트는 유지하고, 현재 폴더의 새 사이트를 같은 방식으로 운영할 수 있게 구성해줘. 기존 사이트의 파일·설정·실행 상태는 변경하지 말고 참조만 해줘.
>
> 새 사이트 폴더: [절대 경로]
> 새 도메인: [기본 도메인과 www 사용 여부]
> GitHub 저장소: [주소 또는 새 저장소 이름·공개 여부]
>
> Docker Desktop의 Caddy와 Cloudflare Tunnel을 사용하고, 운영용 호스트 포트는 공개하지 마. 컨테이너 이름·Compose 프로젝트·터널·DNS·감시 대상 저장소·자동 시작 작업을 기존 사이트와 분리해줘. 인증 파일과 감시 상태는 복사하거나 GitHub에 올리지 마.
>
> 새 사이트를 기동하고 사용하기로 한 도메인의 외부 HTTPS 응답과 HTTP→HTTPS 전환을 검증해줘. www도 사용한다면 기본 도메인으로 경로·쿼리를 유지해 이동하는지 확인해줘. GitHub 커밋을 60초마다 감시해 HTML 변경이 자동 반영되도록 구성하고, 원격에만 만든 변경을 실제 감시 프로세스가 내려받는지 확인해줘. 로컬 수정과 충돌하면 보존하고 로그에 남겨줘.
>
> Docker·Git·작업 스케줄러 접근 권한을 먼저 확인해줘. 실제 git pull이 가능한 환경이면 그 상태를 확인하고 사용해도 되며, API 파일 동기화를 사용한다면 Git 이력은 갱신되지 않는다는 점을 명시해줘. 실행·등록·검증이 막힌 항목은 완료로 보고하지 말고, 만들어진 실행 스크립트와 필요한 사용자 명령을 구체적으로 알려줘.
