import json
import logging

from flask import request

from routes import app

logger = logging.getLogger(__name__)

VIP_BONUS = 100
CARD_BONUS = 50

def latency_points(distance: float) -> int:
    if distance <= 2:
        return 30
    elif distance <= 4:
        return 20
    elif distance <= 6:
        return 10
    else:
        return 0


def euclidean(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

@app.route('/ticketing-agent', methods=['POST'])
def ticketing_agent():
    data = request.get_json()
    logging.info("data sent for evaluation {}".format(data))

    customers = data.get("customers", [])
    concerts = data.get("concerts", [])
    priority = data.get("priority", {})

    concert_locs = {c["name"]: c["booking_center_location"] for c in concerts}
    result = {}

    for cust in customers:
        best_concert = None
        best_score = None
        best_latency_pts = None

        for concert in concerts:
            cname = concert["name"]
            score = 0

            # VIP bonus
            if cust.get("vip_status"):
                score += VIP_BONUS

            # Credit card priority
            if priority.get(cust.get("credit_card")) == cname:
                score += CARD_BONUS

            # Latency points
            dist = euclidean(cust["location"], concert_locs[cname])
            lat_pts = latency_points(dist)
            score += lat_pts

            if (best_score is None or score > best_score or
               (score == best_score and (best_latency_pts is None or lat_pts > best_latency_pts))):
                best_score = score
                best_concert = cname
                best_latency_pts = lat_pts

        result[cust["name"]] = best_concert

    logging.info("My result :{}".format(result))
    return json.dumps(result)