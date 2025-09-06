import json
import logging

from flask import request

from routes import app

logger = logging.getLogger(__name__)


@app.route('/trivia', methods=['GET'])
def trivia():
    result = {
        "answers": [3, 1, 2, 2, 3, 4, 1, 5, 4, 3, 3, 2, 4, 4, 2, 2, 1, 2, 4, 3, 1, 2, 2, 4, 1]
    }
    logging.info("My result :%s", result)
    return json.dumps(result)
