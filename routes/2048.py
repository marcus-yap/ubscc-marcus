import json
import logging
import uuid
import random
from copy import deepcopy

from flask import request

from routes import app

logger = logging.getLogger(__name__)

def _cors_headers(resp):
    origin = request.headers.get("Origin", "*")
    resp_headers = {
        "Access-Control-Allow-Origin": origin,
        "Vary": "Origin",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    for k, v in resp_headers.items():
        resp.headers[k] = v
    return resp

@app.route("/2048", methods=["OPTIONS"])
def _cors_preflight_2048():
    from flask import Response
    return _cors_headers(Response(status=204))

GAMES = {}

def new_grid(size):
    grid = [[0 for _ in range(size)] for _ in range(size)]
    return spawn_tile(spawn_tile(grid))

def spawn_tile(grid):
    empties = [(r, c) for r in range(len(grid)) for c in range(len(grid)) if grid[r][c] == 0]
    if empties:
        r, c = random.choice(empties)
        grid[r][c] = 4 if random.random() < 0.1 else 2
    return grid

def compress(line):
    tiles = [x for x in line if x != 0]
    out, score_gain = [], 0
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i+1]:
            merged = tiles[i] * 2
            out.append(merged)
            score_gain += merged
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    out += [0] * (len(line) - len(out))
    return out, out != line, score_gain

def rotate(grid):
    n = len(grid)
    return [[grid[n-1-c][r] for c in range(n)] for r in range(n)]

def move_grid(grid, direction):
    mapping = {"left": 0, "up": 1, "right": 2, "down": 3}
    rot = mapping[direction]
    g = [row[:] for row in grid]
    for _ in range(rot):
        g = rotate(g)
    moved_any, gained, new_rows = False, 0, []
    for row in g:
        new_row, moved, gain = compress(row)
        moved_any |= moved
        gained += gain
        new_rows.append(new_row)
    g = new_rows
    if moved_any:
        g = spawn_tile(g)
    for _ in range((4 - rot) % 4):
        g = rotate(g)
    return g, moved_any, gained

def has_moves(grid):
    n = len(grid)
    if any(0 in row for row in grid):
        return True
    for r in range(n):
        for c in range(n):
            if r + 1 < n and grid[r][c] == grid[r + 1][c]:
                return True
            if c + 1 < n and grid[r][c] == grid[r][c + 1]:
                return True
    return False

def check_win(grid, target=2048):
    return any(cell >= target for row in grid for cell in row)

@app.route('/2048/new', methods=['POST'])
def new_game():
    data = request.get_json(silent=True) or {}
    size = int(data.get("size", 4))
    target = int(data.get("target", 2048))
    gid = str(uuid.uuid4())
    grid = new_grid(size)
    state = {
        "game_id": gid,
        "size": size,
        "target": target,
        "grid": grid,
        "score": 0,
        "over": False,
        "won": check_win(grid, target)
    }
    GAMES[gid] = state
    logger.info("New game created %s", gid)
    from flask import Response
    resp = Response(json.dumps(state), mimetype="application/json")
    return _cors_headers(resp)

@app.route('/2048/move', methods=['POST'])
def move():
    data = request.get_json() or {}
    gid = data.get("game_id")
    direction = (data.get("direction") or "").lower()
    from flask import Response
    if gid not in GAMES:
        return _cors_headers(Response(json.dumps({"error":"invalid game_id"}), mimetype="application/json"))
    if direction not in {"up","down","left","right"}:
        return _cors_headers(Response(json.dumps({"error":"invalid direction"}), mimetype="application/json"))
    st = GAMES[gid]
    if st["over"]:
        return _cors_headers(Response(json.dumps(st), mimetype="application/json"))
    new_grid_state, moved, gained = move_grid(st["grid"], direction)
    if moved:
        st["grid"] = new_grid_state
        st["score"] += gained
    st["won"] = st["won"] or check_win(st["grid"], st["target"])
    st["over"] = not has_moves(st["grid"]) or st["won"]
    return _cors_headers(Response(json.dumps(st), mimetype="application/json"))

@app.route('/2048/state', methods=['GET'])
def get_state():
    gid = request.args.get("game_id")
    from flask import Response
    if not gid or gid not in GAMES:
        return _cors_headers(Response(json.dumps({"error":"invalid game_id"}), mimetype="application/json"))
    return _cors_headers(Response(json.dumps(GAMES[gid]), mimetype="application/json"))

@app.route('/2048', methods=['POST', 'GET'])
def logic_mux():
    from flask import Response
    if request.method == 'GET':
        return _cors_headers(Response(json.dumps({"status":"ok","endpoints":["POST /2048 (new|move|state)","POST /2048/new","POST /2048/move","GET /2048/state"]}), mimetype="application/json"))

    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").lower()

    if action == "new":
        size = int(payload.get("size", 4))
        target = int(payload.get("target", 2048))
        gid = str(uuid.uuid4())
        grid = new_grid(size)
        st = {
            "game_id": gid,
            "size": size,
            "target": target,
            "grid": grid,
            "score": 0,
            "over": False,
            "won": check_win(grid, target)
        }
        GAMES[gid] = st
        return _cors_headers(Response(json.dumps(st), mimetype="application/json"))

    if action == "move":
        gid = payload.get("game_id")
        direction = (payload.get("direction") or "").lower()
        if gid not in GAMES:
            return _cors_headers(Response(json.dumps({"error":"invalid game_id"}), mimetype="application/json"))
        if direction not in {"up","down","left","right"}:
            return _cors_headers(Response(json.dumps({"error":"invalid direction"}), mimetype="application/json"))
        st = GAMES[gid]
        if st["over"]:
            return _cors_headers(Response(json.dumps(st), mimetype="application/json"))
        new_grid_state, moved, gained = move_grid(st["grid"], direction)
        if moved:
            st["grid"] = new_grid_state
            st["score"] += gained
        st["won"] = st["won"] or check_win(st["grid"], st["target"])
        st["over"] = not has_moves(st["grid"]) or st["won"]
        return _cors_headers(Response(json.dumps(st), mimetype="application/json"))

    if action == "state":
        gid = payload.get("game_id")
        if not gid or gid not in GAMES:
            return _cors_headers(Response(json.dumps({"error":"invalid game_id"}), mimetype="application/json"))
        return _cors_headers(Response(json.dumps(GAMES[gid]), mimetype="application/json"))

    return _cors_headers(Response(json.dumps({"error":"unknown action"}), mimetype="application/json"))