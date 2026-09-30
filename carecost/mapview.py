"""Small, public-data-only hospital map for the comparison page."""

from __future__ import annotations

import pydeck as pdk


def map_points(rows):
    """One marker per hospital, using the lowest visible amount there."""
    by_hospital = {}
    for row in rows:
        hospital = row["hospital"]
        hospital_id = row["price"].hospital_id
        value = float(row["display"])
        previous = by_hospital.get(hospital_id)
        if previous is None or value < previous["amount"]:
            by_hospital[hospital_id] = {
                "hospital_id": hospital_id,
                "name": hospital["name"],
                "address": hospital.get("address", ""),
                "latitude": float(hospital["latitude"]),
                "longitude": float(hospital["longitude"]),
                "amount": value,
                "price": f"${value:,.2f}",
                "distance": f"{row['distance']:.1f} miles",
                "subtitle": f"${value:,.2f} · {row['distance']:.1f} miles",
                "color": [19, 125, 113, 225],
                "radius": 550,
            }
    return list(by_hospital.values())


def hospital_map_points(hospitals):
    """Public hospital locations, available before a patient searches for care."""
    return [
        {
            "hospital_id": hospital_id,
            "name": hospital["name"],
            "address": hospital.get("address", ""),
            "latitude": float(hospital["latitude"]),
            "longitude": float(hospital["longitude"]),
            "subtitle": hospital.get("city", "Boston"),
            "color": [19, 125, 113, 225],
            "radius": 550,
        }
        for hospital_id, hospital in sorted(hospitals.items(), key=lambda item: item[1]["name"])
        if hospital.get("latitude") is not None and hospital.get("longitude") is not None
    ]


def comparison_map(points, origin=None, focused_hospital=None):
    if focused_hospital:
        focused = next((p for p in points if p["hospital_id"] == focused_hospital), None)
    else:
        focused = None
    center_lat = focused["latitude"] if focused else sum(p["latitude"] for p in points) / len(points)
    center_lon = focused["longitude"] if focused else sum(p["longitude"] for p in points) / len(points)
    colored_points = [
        {
            **point,
            "color": [16, 85, 79, 255]
            if focused and point["hospital_id"] == focused_hospital
            else point["color"],
            "radius": 780 if focused and point["hospital_id"] == focused_hospital else point["radius"],
        }
        for point in points
    ]
    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            id="hospitals",
            data=colored_points,
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_line_color=[255, 255, 255],
            line_width_min_pixels=2,
            radius_min_pixels=9,
            radius_max_pixels=17,
            get_radius="radius",
            pickable=True,
            auto_highlight=True,
        )
    ]
    if origin:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                id="starting-area",
                data=[{"latitude": origin[0], "longitude": origin[1]}],
                get_position="[longitude, latitude]",
                get_fill_color=[29, 63, 63, 170],
                radius_min_pixels=5,
                radius_max_pixels=7,
                get_radius=280,
                pickable=False,
            )
        )
    return pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        initial_view_state=pdk.ViewState(
            latitude=center_lat, longitude=center_lon, zoom=12 if focused else 10.4, pitch=0, controller=True
        ),
        layers=layers,
        tooltip={
            "html": "<b>{name}</b><br>{subtitle}<br>{address}",
            "style": {"color": "#173A37", "backgroundColor": "#ffffff"},
        },
    )
