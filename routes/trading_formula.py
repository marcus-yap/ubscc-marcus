import json
import logging
import math
import re

from flask import request
from routes import app

logger = logging.getLogger(__name__)

GREEK = {
    r"\alpha": "alpha", r"\beta": "beta", r"\gamma": "gamma", r"\delta": "delta",
    r"\epsilon": "epsilon", r"\theta": "theta", r"\lambda": "lambda", r"\mu": "mu",
    r"\pi": "pi", r"\rho": "rho", r"\sigma": "sigma", r"\phi": "phi", r"\omega": "omega",
}

def _extract_braced(s: str, start: int):
    """Given s and index at '{', return (inner, next_index_after_closing_brace)."""
    assert s[start] == '{'
    depth = 0
    i = start
    while i < len(s):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                # return inner content (without outer braces) and next index
                return s[start+1:i], i + 1
        i += 1
    raise ValueError("Unbalanced braces in \\frac expression")

def replace_frac(expr: str) -> str:
    """Robustly replace all \frac / \dfrac / \tfrac with ((num)/(den)), allowing spaces."""
    expr = expr.replace(r'\dfrac', r'\frac').replace(r'\tfrac', r'\frac')
    i = 0
    out = []
    while i < len(expr):
        if expr.startswith(r'\frac', i):
            i += len(r'\frac')
            # skip spaces
            while i < len(expr) and expr[i].isspace():
                i += 1
            if i >= len(expr) or expr[i] != '{':
                # malformed, keep literal and continue
                out.append(r'\frac')
                continue
            # numerator
            num, i = _extract_braced(expr, i)

            # skip spaces up to '/'
            while i < len(expr) and expr[i].isspace():
                i += 1
            if i >= len(expr) or expr[i] != '/':
                # malformed; put back literal and numerator
                out.append(r'\frac{' + num + '}')
                continue
            i += 1
            # skip spaces to '{'
            while i < len(expr) and expr[i].isspace():
                i += 1
            if i >= len(expr) or expr[i] != '{':
                out.append(r'\frac{' + num + '}/')
                continue
            # denominator
            den, i = _extract_braced(expr, i)

            out.append(f"(({num})/({den}))")
        else:
            out.append(expr[i])
            i += 1
    return ''.join(out)

FUNC_NAMES = ("max", "min", "log", "math")

def insert_implicit_multiplication(s: str) -> str:
    # Insert * before '(' unless the preceding token is a known function
    def add_star_before_paren(m):
        before = m.group(1)
        # Look back for identifier just before '('
        start_ctx = max(0, m.start() - 64)
        context = s[start_ctx:m.start()+1]
        w = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', context)
        if w and w.group(1) in FUNC_NAMES:
            return before + '('  # keep function call
        return before + '*('
    s = re.sub(r'([0-9A-Za-z_)\]])\s*\(', add_star_before_paren, s)
    s = re.sub(r'\)\s*(?=[0-9A-Za-z_])', r')*', s)
    return s

def latex_to_python(s: str) -> str:
    s = s.strip().replace('$$', '').replace('$', '')
    if '=' in s:
        s = s.split('=')[-1]

    # Convert fractions FIRST (most brittle form)
    s = replace_frac(s)

    # \text{...} -> inner
    s = re.sub(r'\\text\s*{([^}]*)}', r'\1', s)

    # spacing helpers
    for token in [r'\left', r'\right', r'\,', r'\;', r'\:', r'\!']:
        s = s.replace(token, '')

    # Greek
    for k, v in GREEK.items():
        s = s.replace(k, v)

    # operators
    s = s.replace(r'\cdot', '*').replace(r'\times', '*')

    # max/min
    s = re.sub(r'\\max\s*{', 'max(', s)
    s = s.replace(r'\max', 'max')
    s = re.sub(r'\\min\s*{', 'min(', s)
    s = s.replace(r'\min', 'min')

    # subscripts a_{b} -> a_b
    s = re.sub(r'([A-Za-z0-9]+)_\{([^}]+)\}', r'\1_\2', s)

    # expectations: E[R_m] -> E_R_m
    s = re.sub(
        r'([A-Za-z]+)\[([A-Za-z0-9_\\]+)\]',
        lambda m: f"{m.group(1)}_{m.group(2).replace('\\','')}",
        s
    )

    # simple summation: \sum_{i=1}^{N}(body)
    sum_pat = re.compile(r"""\\sum_\{([A-Za-z])=([^}]+)\}\^\{([^}]+)\}\s*\(([^()]*)\)""")
    def _sum_repl(m):
        i, lo, hi, body = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"sum((lambda {i}: ({body}))({i}) for {i} in range(int({lo}), int({hi})+1))"
    prev = None
    while prev != s:
        prev, s = s, sum_pat.sub(_sum_repl, s)

    # e^{x}
    s = re.sub(r'e\s*\^\s*{([^}]+)}', r'(math.e)**(\1)', s)
    # powers a^{b} and a^b
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*{([^}]+)}', r'(\1)**(\2)', s)
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*([A-Za-z0-9_]+)', r'(\1)**(\2)', s)

    # log(...)
    s = re.sub(r'(?<![A-Za-z0-9_])log\s*\(', 'math.log(', s)

    # final grouping cleanup
    s = s.replace('{', '(').replace('}', ')')

    # implicit multiplication (safe)
    s = insert_implicit_multiplication(s)

    # cleanup
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def evaluate_formula(formula: str, variables: dict) -> float:
    expr = latex_to_python(formula)
    env = {"max": max, "min": min, "math": math}
    env.update(variables)
    val = eval(expr, {"__builtins__": {}}, env)
    return float(val)

@app.route('/trading-formula', methods=['POST'])
def trading_formula():
    data = request.get_json()
    logging.info("data sent for evaluation {}".format(data))

    results = []
    for case in data:
        try:
            formula = case.get("formula", "")
            variables = case.get("variables", {})
            value = evaluate_formula(formula, variables)
            results.append({"result": float(f"{value:.4f}")})
        except Exception as e:
            logging.exception("Error in case %s", case.get("name", "<unnamed>"))
            results.append({"error": str(e)})

    logging.info("My result :{}".format(results))
    return json.dumps(results)
