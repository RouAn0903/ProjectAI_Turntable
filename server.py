#!/usr/bin/env python3
"""
今天吃什麼？ - 後端伺服器
使用 OpenStreetMap Overpass API 查詢附近餐廳（完全免費，無需 API Key）
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder='.')
CORS(app)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

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
    regex = "|".join(cuisines)
    return f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"]["cuisine"~"{regex}",i](around:{radius},{lat},{lng});
  node["amenity"="fast_food"]["cuisine"~"{regex}",i](around:{radius},{lat},{lng});
  way["amenity"="restaurant"]["cuisine"~"{regex}",i](around:{radius},{lat},{lng});
);
out center 20;
"""


def build_fallback_query(lat, lng, radius):
    return f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"](around:{radius},{lat},{lng});
  way["amenity"="restaurant"](around:{radius},{lat},{lng});
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

    name = tags.get("name:zh") or tags.get("name") or tags.get("name:en") or "（無名稱）"
    cuisine = tags.get("cuisine", "").replace(";", "、").replace("_", " ")
    phone = tags.get("phone") or tags.get("contact:phone") or ""
    website = tags.get("website") or tags.get("contact:website") or ""
    opening_hours = tags.get("opening_hours", "")
    addr = (tags.get("addr:full")
            or (tags.get("addr:city", "") + tags.get("addr:street", "") + tags.get("addr:housenumber", ""))
            or "")

    osm_id = el.get("id")
    osm_type = el.get("type", "node")
    osm_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    maps_search = f"https://www.google.com/maps/search/{requests.utils.quote(name)}/@{lat},{lng},17z" if lat and lng else ""

    return {
        "name": name,
        "cuisine": cuisine,
        "phone": phone,
        "website": website,
        "opening_hours": opening_hours,
        "address": addr,
        "lat": lat,
        "lng": lng,
        "osm_url": osm_url,
        "maps_search": maps_search,
    }


def overpass_post(query):
    return requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "WhatToEatToday/1.0"},
        timeout=28,
    )


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/nearby-restaurants', methods=['GET'])
def nearby_restaurants():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    category = request.args.get('category', '中式')
    radius = request.args.get('radius', 1500, type=int)

    if lat is None or lng is None:
        return jsonify({"error": "缺少定位資訊（lat, lng）"}), 400

    cuisines = CATEGORY_MAP.get(category, [category.lower()])
    results = []
    is_fallback = False

    try:
        # 精確搜尋
        resp = overpass_post(build_query(lat, lng, cuisines, radius))
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        results = [parse_element(el) for el in elements if el.get("tags", {}).get("name")]

        # 結果不足時擴大半徑
        if len(results) < 3:
            resp2 = overpass_post(build_query(lat, lng, cuisines, min(radius * 2, 5000)))
            if resp2.ok:
                seen = {r["osm_url"] for r in results}
                for el in resp2.json().get("elements", []):
                    r = parse_element(el)
                    if el.get("tags", {}).get("name") and r["osm_url"] not in seen:
                        results.append(r)
                        seen.add(r["osm_url"])

        # 仍為空 → 回退查詢所有餐廳
        if not results:
            is_fallback = True
            resp3 = overpass_post(build_fallback_query(lat, lng, radius))
            if resp3.ok:
                results = [parse_element(el) for el in resp3.json().get("elements", [])
                           if el.get("tags", {}).get("name")]

        return jsonify({
            "category": category,
            "count": len(results),
            "results": results[:15],
            "is_fallback": is_fallback,
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
    print("🍽️  今天吃什麼？後端伺服器啟動中...")
    print("✅  使用 OpenStreetMap Overpass API（完全免費，無需 API Key）")
    print("🌐  開啟瀏覽器前往 http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
