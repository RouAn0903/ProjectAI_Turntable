#!/usr/bin/env python3
"""
今天吃什麼？- 測試 & Debug 腳本
使用方式：
  1. 先啟動 server.py（python server.py）
  2. 再開另一個終端機執行本腳本（python test_server.py）
"""

import requests
import json
import time
import sys
import threading
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"

# ── 顏色輸出 ──────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):    print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg):  print(f"  {RED}❌ FAIL{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}⚠️  WARN{RESET}  {msg}")
def info(msg):  print(f"  {CYAN}ℹ️  INFO{RESET}  {msg}")
def title(msg): print(f"\n{BOLD}{BLUE}{'='*55}{RESET}\n{BOLD}{BLUE}  {msg}{RESET}\n{BOLD}{BLUE}{'='*55}{RESET}")
def sep():      print(f"  {BLUE}{'─'*50}{RESET}")

PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0

def record(result, msg):
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    if result == "pass":
        PASS_COUNT += 1; ok(msg)
    elif result == "fail":
        FAIL_COUNT += 1; fail(msg)
    elif result == "warn":
        WARN_COUNT += 1; warn(msg)


# ══════════════════════════════════════════════════
# TEST 1：伺服器是否啟動
# ══════════════════════════════════════════════════
def test_server_alive():
    title("TEST 1｜伺服器連線")
    try:
        r = requests.get(BASE_URL, timeout=5)
        if r.status_code == 200:
            record("pass", f"伺服器回應正常（HTTP {r.status_code}）")
        else:
            record("warn", f"伺服器回應異常（HTTP {r.status_code}）")
    except requests.exceptions.ConnectionError:
        record("fail", "無法連線到伺服器，請確認 python server.py 已啟動")
        print(f"\n{RED}  ⛔ 伺服器未啟動，終止測試{RESET}\n")
        sys.exit(1)
    except Exception as e:
        record("fail", f"連線錯誤：{e}")
        sys.exit(1)


# ══════════════════════════════════════════════════
# TEST 2：Favicon 路由
# ══════════════════════════════════════════════════
def test_favicon():
    title("TEST 2｜Favicon 路由")
    r = requests.get(f"{BASE_URL}/favicon.ico", timeout=5)
    if r.status_code == 204:
        record("pass", "favicon.ico 回傳 204（不報 404）")
    else:
        record("fail", f"favicon.ico 回傳 {r.status_code}（應為 204）")


# ══════════════════════════════════════════════════
# TEST 3：API 基本回傳格式
# ══════════════════════════════════════════════════
def test_api_format():
    title("TEST 3｜API 回傳格式驗證")
    url = f"{BASE_URL}/api/nearby-restaurants?category=中式"
    try:
        r = requests.get(url, timeout=35)
        if r.status_code != 200:
            record("fail", f"HTTP 狀態碼異常：{r.status_code}")
            return

        data = r.json()
        required_keys = ["category", "count", "results", "using_test_location"]
        for key in required_keys:
            if key in data:
                record("pass", f"回傳包含欄位：{key}")
            else:
                record("fail", f"缺少必要欄位：{key}")

        # 驗證 results 為陣列
        if isinstance(data.get("results"), list):
            record("pass", f"results 為陣列格式，共 {data['count']} 筆")
        else:
            record("fail", "results 不是陣列格式")

        # 驗證 count 與 results 長度一致
        if data.get("count") == len(data.get("results", [])):
            record("pass", f"count（{data['count']}）與實際筆數一致")
        else:
            record("fail", f"count（{data['count']}）與實際筆數（{len(data.get('results',[]))}）不一致")

    except Exception as e:
        record("fail", f"API 請求失敗：{e}")


# ══════════════════════════════════════════════════
# TEST 4：各餐廳類別搜尋
# ══════════════════════════════════════════════════
def test_all_categories():
    title("TEST 4｜所有類別搜尋")
    categories = ["中式", "日式", "韓式", "西式", "泰式", "義式", "越式", "印度", "素食", "墨西哥"]

    for cat in categories:
        url = f"{BASE_URL}/api/nearby-restaurants?category={requests.utils.quote(cat)}&radius=1000"
        try:
            start = time.time()
            r = requests.get(url, timeout=90)
            elapsed = time.time() - start
            data = r.json()
            count = data.get("count", 0)
            status = "✓" if count > 0 else "查無結果"
            info(f"{cat:4s}｜{count:3d} 間｜{elapsed:.1f}s｜{status}")
        except Exception as e:
            record("fail", f"{cat} 搜尋失敗：{e}")
        time.sleep(3)  # 避免打爆 Overpass API


# ══════════════════════════════════════════════════
# TEST 5：定位失敗時使用測試座標
# ══════════════════════════════════════════════════
def test_fallback_location():
    title("TEST 5｜定位 Fallback（無座標時用測試座標）")
    url = f"{BASE_URL}/api/nearby-restaurants?category=中式"  # 不帶 lat/lng
    r = requests.get(url, timeout=35)
    data = r.json()

    if data.get("using_test_location") is True:
        record("pass", "未帶座標時正確使用測試座標（輔仁大學）")
    else:
        record("fail", "未帶座標但 using_test_location 不為 True")

    # 帶座標時不應使用測試座標
    url2 = f"{BASE_URL}/api/nearby-restaurants?category=中式&lat=25.05&lng=121.53"
    r2 = requests.get(url2, timeout=35)
    data2 = r2.json()
    if data2.get("using_test_location") is False:
        record("pass", "帶入座標時正確使用真實定位")
    else:
        record("fail", "帶入座標但仍使用測試座標")

# ══════════════════════════════════════════════════
# TEST 6：回傳資料欄位完整性
# ══════════════════════════════════════════════════
def test_result_fields():
    title("TEST 8｜回傳資料欄位完整性")
    url = f"{BASE_URL}/api/nearby-restaurants?category=日式&radius=3000"
    r = requests.get(url, timeout=40)
    data = r.json()
    results = data.get("results", [])

    if not results:
        record("warn", "無搜尋結果，跳過欄位驗證")
        return

    expected_fields = ["name", "opening_hours", "address", "lat", "lng", "osm_url", "maps_search"]
    sample = results[0]
    info(f"以第一筆資料（{sample.get('name')}）驗證欄位：")

    for field in expected_fields:
        if field in sample:
            val = str(sample[field])[:40] if sample[field] else "（空）"
            record("pass", f"{field}: {val}")
        else:
            record("fail", f"缺少欄位：{field}")

    # maps_search 應包含正確格式
    if sample.get("maps_search", "").startswith("https://www.google.com/maps"):
        record("pass", "maps_search URL 格式正確")
    else:
        record("warn", "maps_search URL 格式異常或為空")

    # osm_url 應包含正確格式
    if sample.get("osm_url", "").startswith("https://www.openstreetmap.org"):
        record("pass", "osm_url URL 格式正確")
    else:
        record("warn", "osm_url URL 格式異常或為空")


# ══════════════════════════════════════════════════
# TEST 7：Concurrent 多人同時搜尋
# ══════════════════════════════════════════════════
def test_concurrent():
    title("TEST 9｜多人同時搜尋（模擬 5 人同時）")
    categories = ["中式", "日式", "韓式", "西式", "泰式"]
    results_log = []
    lock = threading.Lock()

    def worker(cat, idx):
        start = time.time()
        try:
            url = f"{BASE_URL}/api/nearby-restaurants?category={requests.utils.quote(cat)}&radius=1000"
            r = requests.get(url, timeout=45)
            elapsed = time.time() - start
            status = "ok" if r.status_code == 200 else f"HTTP {r.status_code}"
            with lock:
                results_log.append((idx, cat, elapsed, status))
        except Exception as e:
            elapsed = time.time() - start
            with lock:
                results_log.append((idx, cat, elapsed, f"ERROR: {e}"))

    threads = [threading.Thread(target=worker, args=(cat, i)) for i, cat in enumerate(categories)]
    start_all = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    total = time.time() - start_all

    results_log.sort(key=lambda x: x[0])
    all_ok = True
    for idx, cat, elapsed, status in results_log:
        if status == "ok":
            info(f"使用者{idx+1}（{cat}）：{elapsed:.1f}s → {status}")
        else:
            record("fail", f"使用者{idx+1}（{cat}）：{elapsed:.1f}s → {status}")
            all_ok = False

    if all_ok:
        record("pass", f"5 人同時搜尋全部成功，總耗時 {total:.1f}s")
    else:
        record("warn", "部分使用者搜尋失敗，建議加上 threaded=True")


# ══════════════════════════════════════════════════
# TEST 8：Geocode API
# ══════════════════════════════════════════════════
def test_geocode():
    title("TEST 10｜Geocode API（座標轉地址）")
    url = f"{BASE_URL}/api/geocode?lat=25.0337&lng=121.4340"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if "error" in data:
            record("warn", f"Geocode API 回傳錯誤：{data['error']}")
        elif "display_name" in data:
            record("pass", f"地址：{data['display_name'][:60]}...")
        else:
            record("warn", "Geocode 回傳格式異常")
    except Exception as e:
        record("fail", f"Geocode API 失敗：{e}")


# ══════════════════════════════════════════════════
# 總結報告
# ══════════════════════════════════════════════════
def print_summary():
    total = PASS_COUNT + FAIL_COUNT + WARN_COUNT
    title("測試結果總覽")
    print(f"  {GREEN}✅ PASS：{PASS_COUNT}{RESET}")
    print(f"  {RED}❌ FAIL：{FAIL_COUNT}{RESET}")
    print(f"  {YELLOW}⚠️  WARN：{WARN_COUNT}{RESET}")
    print(f"  {BLUE}📊 總計：{total} 項{RESET}")
    print()
    if FAIL_COUNT == 0:
        print(f"  {GREEN}{BOLD}🎉 所有測試通過！{RESET}")
    else:
        print(f"  {RED}{BOLD}⛔ 有 {FAIL_COUNT} 項測試失敗，請檢查上方紅色項目{RESET}")
    print()


# ══════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{BOLD}🍽️  今天吃什麼？系統測試 & Debug{RESET}")
    print(f"  測試目標：{CYAN}{BASE_URL}{RESET}")
    print(f"  開始時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    test_server_alive()
    test_favicon()
    test_api_format()
    test_all_categories()
    test_fallback_location()
    test_result_fields()
    test_concurrent()
    test_geocode()

    print_summary()
