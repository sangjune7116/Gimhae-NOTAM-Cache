#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RKPK(김해공항) NOTAM 서버사이드 캐시 갱신 스크립트.
GitHub Actions 러너에서 실행되므로 브라우저 CORS 제약이 없음 — aim.koca.go.kr를 직접 호출해
notam.json으로 저장하면, 김해공항_항행비서 앱은 CORS 프록시 없이
raw.githubusercontent.com/.../notam.json 을 그냥 fetch()하면 됨(GitHub이 기본으로 CORS 허용).

원본 API: aim.koca.go.kr/xNotam/searchAllNotam.do (POST 폼과 동일 파라미터를 GET 쿼리스트링으로도 받음, 실측 확인됨)

v2 (2026-08-09): 배포 후 실측 결과 약 1/3 확률로 이 요청이 실패함을 확인(30회 실행 중 10회 실패,
실패 원인은 특정 시점부터 영구 차단이 아니라 성공/실패가 뒤섞여 나타나는 패턴 — GitHub Actions 호스티드
러너가 매 실행마다 Azure의 넓은 IP 풀에서 무작위 IP를 배정받는데, aim.koca.go.kr WAF가 그 풀의 일부
대역만 차단해서 "이번 실행이 어떤 IP를 뽑았는지"에 따라 확률적으로 성공/실패가 갈리는 것으로 추정됨
(동일 요청을 UTC 우회 없이 실행한 Claude WebFetch 도구에서는 항상 정상 응답을 받아 aim.koca.go.kr 자체가
막힌 건 아님을 확인). 이 정도 확률이면 20분 주기 스케줄 자체는 평균적으로 30분 안팎 간격으로 계속
갱신되어 실사용에 문제가 없지만, 실패할 때마다 GitHub이 실패 이메일을 보내 사용자에게 불필요한 스트레스를
줬음 — 그래서 ① 같은 실행 안에서 재시도(백오프) ② 그래도 실패해도 최근에(STALE_THRESHOLD_HOURS 이내)
성공 갱신된 데이터가 있으면 "이번 회차만 건너뜀"으로 조용히 넘어가고(exit 0, notam.json 미변경 → 커밋 안 됨,
실패 메일 없음) ③ 정말로 오래(그 이상) 갱신이 안 된 경우에만 진짜 경보로 실패 처리(exit 1, 실패 메일 발송)
하도록 변경 — 일시적 확률성 실패와 "진짜 문제"를 구분해서 알림.
"""
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
STALE_THRESHOLD_HOURS = 3  # 이 시간 이상 갱신이 안 됐을 때만 "진짜 실패"로 알림(실패 메일 발송)
MAX_ATTEMPTS = 3
RETRY_DELAY_SEC = [5, 15]  # 1차 실패 후 5초, 2차 실패 후 15초 대기 후 재시도


def build_url():
    now = datetime.now(KST)
    frm = now - timedelta(days=60)
    qs = {
        "sch_snow_series": "", "sch_select": "", "sch_inorout": "D",
        "sch_from_date": frm.strftime("%Y-%m-%d"), "sch_from_time": "0000",
        "sch_to_date": now.strftime("%Y-%m-%d"), "sch_to_time": "2359",
        "sch_series": "", "sch_notam_no": "", "sch_elevation_min": "", "sch_elevation_max": "",
        "sch_airport": "RKPK", "sch_qcode": "", "sch_fir": "", "sch_full_text": "", "iborderby": "",
    }
    return "https://aim.koca.go.kr/xNotam/searchAllNotam.do?ibpage=1&" + urllib.parse.urlencode(qs)


def fetch_once(url):
    """1회 시도. 성공 시 records 리스트 반환, 실패 시 예외를 그대로 던짐(호출부에서 재시도 판단)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://aim.koca.go.kr/xNotam/?language=ko_KR",
    })
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    records = data.get("DATA")
    if not isinstance(records, list):
        raise ValueError(f"UNEXPECTED SHAPE — no DATA array. Keys: {list(data.keys())}")
    return records


def fetch_with_retry(url):
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fetch_once(url)
        except Exception as e:
            last_err = e
            print(f"시도 {attempt}/{MAX_ATTEMPTS} 실패: {type(e).__name__}: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC[attempt - 1])
    raise last_err


def existing_fetched_at():
    """이미 커밋된 notam.json(체크아웃된 상태)이 있으면 그 fetchedAtUTC를 datetime으로 반환, 없으면 None."""
    try:
        with open("notam.json", encoding="utf-8") as f:
            prev = json.load(f)
        return datetime.fromisoformat(prev["fetchedAtUTC"])
    except Exception:
        return None


def main():
    url = build_url()
    try:
        records = fetch_with_retry(url)
    except Exception as e:
        prev_ts = existing_fetched_at()
        now_utc = datetime.now(timezone.utc)
        if prev_ts is not None:
            age_hours = (now_utc - prev_ts).total_seconds() / 3600
            if age_hours < STALE_THRESHOLD_HOURS:
                # 일시적 실패로 판단 — 조용히 이번 회차만 건너뜀(notam.json 미변경 → 커밋 없음 → 실패 메일 없음)
                print(f"::warning::{MAX_ATTEMPTS}회 재시도 모두 실패했지만 마지막 성공 갱신이 {age_hours:.1f}시간 전(임계값 {STALE_THRESHOLD_HOURS}시간 이내)이라 일시적 문제로 보고 이번 회차는 건너뜁니다. 최종 오류: {e}")
                sys.exit(0)
        # 최초 실행이거나(이전 데이터 없음) STALE_THRESHOLD_HOURS 이상 갱신이 안 된 경우만 진짜 실패로 알림
        print(f"::error::NOTAM 캐시 갱신이 {STALE_THRESHOLD_HOURS}시간 이상 계속 실패 중입니다 — 실제 점검이 필요할 수 있습니다. 최종 오류: {e}")
        sys.exit(1)

    out = {
        "fetchedAt": datetime.now(KST).isoformat(),
        "fetchedAtUTC": datetime.now(timezone.utc).isoformat(),
        "source": "aim.koca.go.kr/xNotam (server-side, GitHub Actions)",
        "airport": "RKPK",
        "windowDays": 60,
        "count": len(records),
        "DATA": records,
    }
    with open("notam.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"OK - {len(records)} RKPK NOTAM records saved.")


if __name__ == "__main__":
    main()
