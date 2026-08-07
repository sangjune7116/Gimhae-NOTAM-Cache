#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RKPK(김해공항) NOTAM 서버사이드 캐시 갱신 스크립트.
GitHub Actions 러너에서 실행되므로 브라우저 CORS 제약이 없음 — aim.koca.go.kr를 직접 호출해
notam.json으로 저장하면, 김해공항_항행비서 앱은 CORS 프록시 없이
raw.githubusercontent.com/.../notam.json 을 그냥 fetch()하면 됨(GitHub이 기본으로 CORS 허용).

원본 API: aim.koca.go.kr/xNotam/searchAllNotam.do (POST 폼과 동일 파라미터를 GET 쿼리스트링으로도 받음, 실측 확인됨)
"""
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


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


def main():
    url = build_url()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (GimhaeNavaidAssistant NOTAM cache bot)"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8")
    except Exception as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"JSON PARSE FAILED: {e}\nBody(head): {body[:300]}", file=sys.stderr)
        sys.exit(1)

    records = data.get("DATA")
    if not isinstance(records, list):
        print(f"UNEXPECTED SHAPE — no DATA array. Keys: {list(data.keys())}", file=sys.stderr)
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
