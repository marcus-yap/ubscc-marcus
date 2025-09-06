import json
import logging

from flask import request, Response, jsonify, redirect

from routes import app

logger = logging.getLogger(__name__)


@app.route('/sailing-club', methods=['POST'])
def sailing_club_compat():
    return sailing_club_submission()

@app.route('/', methods=['POST'])
def root_post_hint():
    return jsonify({
        "error": "Wrong endpoint. Use POST /sailing-club/submission with JSON body."
    }), 404

@app.errorhandler(400)
def handle_400(e):
    return jsonify({"error": "Bad Request", "detail": getattr(e, "description", str(e))}), 400

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Not Found", "detail": "Use POST /sailing-club/submission"}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method Not Allowed", "detail": "Check method and path"}), 405

@app.route('/sailing-club/submission', methods=['POST'])
def sailing_club_submission():
    try:
        data = request.get_json(force=False, silent=False)
    except Exception:
        err = {"error": "Invalid JSON. Ensure Content-Type: application/json and a valid body."}
        return Response(json.dumps(err), status=400, mimetype="application/json")

    logging.info("data sent for evaluation %s", data)

    test_cases = (data or {}).get("testCases", [])
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
    logging.info("My result :%s", result)
    return Response(json.dumps(result), mimetype="application/json")