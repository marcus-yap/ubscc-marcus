from flask import Flask

app = Flask(__name__)
import routes.square
import routes.ticketing_agent
import routes.trading_formula
import routes.trivia

import importlib.util, os, sys

_2048_path = os.path.join(os.path.dirname(__file__), "2048.py")
if os.path.exists(_2048_path):
    spec = importlib.util.spec_from_file_location("routes._2048", _2048_path)
    _mod = importlib.util.module_from_spec(spec)
    sys.modules["routes._2048"] = _mod
    spec.loader.exec_module(_mod)