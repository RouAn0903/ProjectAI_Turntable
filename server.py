#!/usr/bin/env python3
"""
今天吃什麼？ - 後端伺服器
使用 OpenStreetMap Overpass API 查詢附近餐廳（完全免費，無需 API Key）

本版整合所有修改：
  1. 定位失敗時自動使用測試座標（輔仁大學）
  2. 排除飲料/甜點類餐廳
  3. 搜尋流程：精確 → 擴大半徑 → 回退所有餐廳（原始半徑）
  4. 移除 name 過濾，避免「😢 找不到」誤觸發
  5. favicon 路由，消除 404 警告
  6. PORT 環境變數支援（Render / Railway 部署用）
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__, static_folder='.')
CORS(app)

OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# 測試用預設座標（輔大）—— 定位失敗時自動使用
TEST_LAT = 25.0337
TEST_LNG = 121.4340

# 排除飲料 / 甜點 / 酒吧類
EXCLUDE_CUISINE = (
    "coffee|bubble_tea|tea|juice|smoothie|drinks|beverage"
    "|ice_cream|dessert|bakery|bar|cocktail|wine|beer"
)

# 餐廳類別 → OSM cuisine tag 關鍵字
CATEGORY_MAP = {
    "中式":   ["chinese", "dim_sum", "noodle", "hotpot", "taiwanese"],
    "日式":   ["japanese", "sushi", "ramen", "udon", "tempura", "yakitori", "tonkatsu"],
    "韓式":   ["korean", "korean_bbq"],
    "西式":   ["burger", "american", "steak", "sandwich", "fish_and_chips"],
    "泰式":   ["thai"],
    "義式":   ["italian", "pizza", "pasta"],
    "越式":   ["vietnamese"],
    "印度":   ["indian", "curry"],
    "素食":   ["vegetarian", "vegan"],
    "墨西哥": ["mexican", "tex-mex"],
}


def build_query(lat, lng, cuisines, radius):
    """精確搜尋：指定 cuisine + 排除飲料類"""
    regex = "|".join(cuisines)
    return f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"]["cuisine"~"{regex}",i]["cuisine"!~"{EXCLUDE_CUISINE}",i](around:{radius},{lat},{lng});
  node["amenity"="fast_food"]["cuisine"~"{regex}",i]["cuisine"!~"{EXCLUDE_CUISINE}",i](around:{radius},{lat},{lng});
  way["amenity"="restaurant"]["cuisine"~"{regex}",i]["cuisine"!~"{EXCLUDE_CUISINE}",i](around:{radius},{lat},{lng});
);
out center 20;
"""


def build_fallback_query(lat, lng, radius):
    """回退搜尋：拿掉 cuisine 條件，找所有餐廳（仍排除飲料類）"""
    return f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"]["cuisine"!~"{EXCLUDE_CUISINE}",i](around:{radius},{lat},{lng});
  node["amenity"="restaurant"][!"cuisine"](around:{radius},{lat},{lng});
  way["amenity"="restaurant"]["cuisine"!~"{EXCLUDE_CUISINE}",i](around:{radius},{lat},{lng});
  way["amenity"="restaurant"][!"cuisine"](around:{radius},{lat},{lng});
);
out center 15;
"""


def parse_element(el):
    tags = el.get("tags", {})
    if el.get("type") == "way":
        center = el.get("center", {})
        lat, lng = center.get("lat"), center.get("lon")
    else:
        lat, lng = el.get("lat"), el.get("lon")

    name         = tags.get("name:zh") or tags.get("name") or tags.get("name:en") or "（無名稱）"
    cuisine      = tags.get("cuisine", "").replace(";", "、").replace("_", " ")
    phone        = tags.get("phone") or tags.get("contact:phone") or ""
    website      = tags.get("website") or tags.get("contact:website") or ""
    opening_hours = tags.get("opening_hours", "")
    addr = (
        tags.get("addr:full")
        or (tags.get("addr:city", "") + tags.get("addr:street", "") + tags.get("addr:housenumber", ""))
        or ""
    )
    osm_id   = el.get("id")
    osm_type = el.get("type", "node")
    osm_url  = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    maps_search = (
        f"https://www.google.com/maps/search/{requests.utils.quote(name)}/@{lat},{lng},17z"
        if lat and lng else ""
    )
    return {
        "name": name,
        "phone": phone, "website": website,
        "opening_hours": opening_hours, "address": addr,
        "lat": lat, "lng": lng,
        "osm_url": osm_url, "maps_search": maps_search,
    }


def overpass_post(query):
    return requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "WhatToEatToday/1.0"},
        timeout=28,
    )


# ── 路由 ──────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    return '', 204  # 消除瀏覽器 favicon 404 警告


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/nearby-restaurants', methods=['GET'])
def nearby_restaurants():
    lat      = request.args.get('lat', type=float)
    lng      = request.args.get('lng', type=float)
    category = request.args.get('category', '中式')
    radius   = request.args.get('radius', 1500, type=int)

    # 定位失敗時使用測試座標
    using_test_location = False
    if lat is None or lng is None:
        lat, lng = TEST_LAT, TEST_LNG
        using_test_location = True

    cuisines    = CATEGORY_MAP.get(category, [category.lower()])
    results     = []

    try:
        # 第一次搜尋：原始半徑 + 精確 cuisine
        resp = overpass_post(build_query(lat, lng, cuisines, radius))
        resp.raise_for_status()
        results = [parse_element(el) for el in resp.json().get("elements", [])]

        # # 第二次搜尋：結果 < 3 → 擴大半徑 ×2，仍用精確 cuisine
        # if len(results) < 3:
        #     resp2 = overpass_post(build_query(lat, lng, cuisines, min(radius * 2, 5000)))
        #     if resp2.ok:
        #         seen = {r["osm_url"] for r in results}
        #         for el in resp2.json().get("elements", []):
        #             r = parse_element(el)
        #             if r["osm_url"] not in seen:
        #                 results.append(r)
        #                 seen.add(r["osm_url"])
        
        # 找不到就直接回傳空結果，不再回退搜尋所有餐廳
        return jsonify({
            "category": category,
            "count": len(results),
            "results": results,
            "using_test_location": using_test_location,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "Overpass API 請求逾時，請稍後再試"}), 504
    except Exception as e:
        return jsonify({"error": f"錯誤：{str(e)}"}), 500


@app.route('/api/geocode', methods=['GET'])
def geocode():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    if lat is None or lng is None:
        return jsonify({"error": "缺少 lat/lng"}), 400
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lng, "format": "json", "accept-language": "zh-TW"},
            headers={"User-Agent": "WhatToEatToday/1.0"},
            timeout=10,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🍽️  今天吃什麼？後端伺服器啟動中...")
    print("✅  OpenStreetMap Overpass API（免費，無需 API Key）")
    print(f"🌐  http://localhost:{port}")
    app.run(debug=True, host='0.0.0.0', port=port, threaded=True)