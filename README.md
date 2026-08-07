# Gimhae-NOTAM-Cache

김해공항(RKPK) NOTAM 실시간 캐시 — [김해공항 항행비서](https://github.com/sangjune7116/Gimhae-Navi-Assistance) 앱의 「실시간 NOTAM 확인」 기능이 사용하는 데이터 소스입니다.

## 왜 필요한가

브라우저에서 직접 `aim.koca.go.kr`(항공정보통합관리, AIM)를 호출하면 CORS(교차출처) 정책에 막혀 무료 프록시 서비스를 거쳐야 하는데, 이런 무료 프록시는 자주 다운되거나 차단됩니다. 그래서 GitHub Actions(서버사이드, CORS 제약 없음)가 20분마다 직접 조회해서 `notam.json`에 저장해두면, 앱은 `raw.githubusercontent.com`에서 이 파일을 그냥 읽기만 하면 됩니다 — GitHub 자체가 CORS를 기본 허용하고 인프라도 안정적이라 훨씬 신뢰할 수 있습니다.

## 데이터

- `notam.json` — RKPK(김해공항) 최근 60일 NOTAM 전체(원본 API 그대로), 20분마다 자동 갱신
- 원본: [xNOTAM](https://aim.koca.go.kr/xNotam/) — 국토교통부 항공정보통합관리 공식 공개 데이터(항공고시보, 민감정보 아님)

## 갱신 주기

`.github/workflows/update.yml` — 20분 간격 스케줄 + 수동 실행(Actions 탭 → Run workflow) 지원.
