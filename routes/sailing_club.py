import json
import logging

from flask import request

from routes import app

logger = logging.getLogger(__name__)


def merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort(key=lambda x: (x[0], x[1]))
    merged = [intervals[0][:]]
    for s, e in intervals[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            merged[-1][1] = max(last_e, e)
        else:
            merged.append([s, e])
    return merged


def min_boats(intervals):
    events = []
    for s, e in intervals:
        events.append((s, 1))
        events.append((e, -1))
    events.sort(key=lambda x: (x[0], x[1]))
    cur = 0
    peak = 0
    for _, delta in events:
        cur += delta
        if cur > peak:
            peak = cur
    return peak


@app.route('/sailing-club', methods=['POST'])
def evaluate():
    data = request.get_json()
    logging.info("data sent for evaluation {}".format(data))

    test_cases = data.get("testCases", [])
    solutions = []

    for tc in test_cases:
        tc_id = tc.get("id")
        intervals = tc.get("input", [])

        merged = merge_intervals([list(pair) for pair in intervals])
        boats = min_boats(intervals) if intervals else 0

        solution = {
            "id": tc_id,
            "sortedMergedSlots": merged,
            "minBoatsNeeded": boats
        }
        logging.info("Solution for id %s : %s", tc_id, solution)
        solutions.append(solution)

    result = {"solutions": solutions}
    logging.info("My result :{}".format(result))
    return json.dumps(result)