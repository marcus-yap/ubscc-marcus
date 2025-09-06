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

def replace_frac(expr: str) -> str:
    while True:
        m = re.search(r'\\frac\s*{', expr)
        if not m:
            break
        i = m.end()
        # parse numerator
        depth, start = 1, i
        while i < len(expr) and depth:
            if expr[i] == '{': depth += 1
            elif expr[i] == '}': depth -= 1
            i += 1
        if depth != 0:  # unbalanced
            break
        num = expr[start:i-1]

        # expect '/{'
        if i >= len(expr) or expr[i] != '/':
            break
        i += 1
        if i >= len(expr) or expr[i] != '{':
            break
        i += 1

        # parse denominator
        depth, start = 1, i
        while i < len(expr) and depth:
            if expr[i] == '{': depth += 1
            elif expr[i] == '}': depth -= 1
            i += 1
        if depth != 0:
            break
        den = expr[start:i-1]

        expr = expr[:m.start()] + f"(({num})/({den}))" + expr[i:]
    return expr

def insert_implicit_multiplication(s: str) -> str:
    # identifier/number/close-bracket immediately followed by '('  -> insert '*'
    s = re.sub(r'(?<=[0-9A-Za-z_)\]])\s*\(', r'*(', s)
    # ')' immediately followed by identifier/number  -> insert '*'
    s = re.sub(r'\)\s*(?=[0-9A-Za-z_])', r')*', s)
    return s

def latex_to_python(s: str) -> str:
    s = s.strip().replace('$$', '').replace('$', '')
    # take RHS if an '=' exists
    if '=' in s:
        s = s.split('=')[-1]

    # \text{...} -> inner
    s = re.sub(r'\\text\s*{([^}]*)}', r'\1', s)

    # remove spacing helpers
    for token in [r'\left', r'\right', r'\,', r'\;', r'\:', r'\!']:
        s = s.replace(token, '')

    # Greek letters
    for k, v in GREEK.items():
        s = s.replace(k, v)

    # operators
    s = s.replace(r'\cdot', '*').replace(r'\times', '*')

    # max/min in both \max{...} and \max(...)
    s = re.sub(r'\\max\s*{', 'max(', s)
    s = s.replace(r'\max', 'max')
    s = re.sub(r'\\min\s*{', 'min(', s)
    s = s.replace(r'\min', 'min')

    # subscripts a_{b} -> a_b
    s = re.sub(r'([A-Za-z0-9]+)_\{([^}]+)\}', r'\1_\2', s)

    # expectations/brackets: E[R_m] -> E_R_m
    s = re.sub(r'([A-Za-z]+)\[([A-Za-z0-9_\\]+)\]',
               lambda m: f"{m.group(1)}_{m.group(2).replace('\\','')}", s)

    # fractions
    s = replace_frac(s)

    # summation (simple form): \sum_{i=1}^{N}(body)
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

    # leftover grouping braces -> parentheses
    s = s.replace('{', '(').replace('}', ')')

    # INSERT implicit multiplication (fixes "beta_i ( ... )")
    s = insert_implicit_multiplication(s)

    # final cleanup
    s = re.sub(r'\s+', ' ', s).strip()

    # sanity: if any \frac remains, it's unsafe to eval
    if r'\frac' in s:
        raise ValueError("Unconverted \\frac remains in expression")

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