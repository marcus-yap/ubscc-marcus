import json
import logging
import math
import re

from flask import request

from routes import app

logger = logging.getLogger(__name__)

GREEK = {
    r"\alpha": "alpha",
    r"\beta": "beta",
    r"\gamma": "gamma",
    r"\delta": "delta",
    r"\epsilon": "epsilon",
    r"\theta": "theta",
    r"\lambda": "lambda",
    r"\mu": "mu",
    r"\pi": "pi",
    r"\rho": "rho",
    r"\sigma": "sigma",
    r"\phi": "phi",
    r"\omega": "omega",
}

def replace_frac(expr: str) -> str:
    while r'\frac' in expr:
        m = re.search(r'\\frac\s*{', expr)
        if not m:
            break
        i = m.end()
        depth = 1
        start_num = i
        while i < len(expr) and depth:
            if expr[i] == '{':
                depth += 1
            elif expr[i] == '}':
                depth -= 1
            i += 1
        num = expr[start_num:i-1]
        if i >= len(expr) or expr[i] != '/':
            break
        i += 1
        if i >= len(expr) or expr[i] != '{':
            break
        i += 1
        depth = 1
        start_den = i
        while i < len(expr) and depth:
            if expr[i] == '{':
                depth += 1
            elif expr[i] == '}':
                depth -= 1
            i += 1
        den = expr[start_den:i-1]
        whole = expr[m.start():i]
        expr = expr[:m.start()] + f"(({num})/({den}))" + expr[i:]
    return expr

def replace_sum(expr: str) -> str:
    # Very simple \sum_{i=1}^{N}( body ) → sum((lambda i: body)(i) for i in range(1, N+1))
    # Handles one-letter index and body enclosed in parentheses right after the sum
    pattern = re.compile(r"""\\sum_\{([A-Za-z])=([^}]+)\}\^\{([^}]+)\}\s*\(([^()]*)\)""")
    def _repl(m):
        idx = m.group(1)
        lo  = m.group(2)
        hi  = m.group(3)
        body = m.group(4)
        return f"sum((lambda {idx}: ({body}))({idx}) for {idx} in range(int({lo}), int({hi})+1))"
    # Replace repeatedly in case of multiple sums
    prev = None
    while prev != expr:
        prev = expr
        expr = pattern.sub(_repl, expr)
    return expr

def latex_to_python(s: str) -> str:
    s = s.strip().replace('$$', '').replace('$', '')
    if '=' in s:
        s = s.split('=')[-1]
    # \text{...} → inner
    s = re.sub(r'\\text\s*{([^}]*)}', r'\1', s)
    # Remove spacing helpers
    for token in [r'\left', r'\right', r'\,', r'\;', r'\:', r'\!']:
        s = s.replace(token, '')
    # Greek
    for k, v in GREEK.items():
        s = s.replace(k, v)
    # Operators
    s = s.replace(r'\cdot', '*').replace(r'\times', '*')
    s = re.sub(r'\\max\s*{', 'max(', s).replace(r'\max', 'max')
    s = re.sub(r'\\min\s*{', 'min(', s).replace(r'\min', 'min')
    # Subscripts a_{b} → a_b
    s = re.sub(r'([A-Za-z0-9]+)_\{([^}]+)\}', r'\1_\2', s)
    # Expectations/brackets: E[R_m] → E_R_m
    s = re.sub(r'([A-Za-z]+)\[([A-Za-z0-9_\\]+)\]',
               lambda m: f"{m.group(1)}_{m.group(2).replace('\\','')}", s)
    # Fractions
    s = replace_frac(s)
    # Summation
    s = replace_sum(s)
    # e^{x}
    s = re.sub(r'e\s*\^\s*{([^}]+)}', r'(math.e)**(\1)', s)
    # Powers a^{b} and a^b
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*{([^}]+)}', r'(\1)**(\2)', s)
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*([A-Za-z0-9_]+)', r'(\1)**(\2)', s)
    # log(...)
    s = re.sub(r'(?<![A-Za-z0-9_])log\s*\(', 'math.log(', s)
    # Any remaining braces as grouping
    s = s.replace('{', '(').replace('}', ')')
    # As a final guard: remove any stray backslashes that could break eval
    s = s.replace('\\', '')
    # Cleanup spaces
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