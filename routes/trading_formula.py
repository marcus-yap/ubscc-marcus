import json
import logging
import math
import re

from flask import request, Response
from routes import app

logger = logging.getLogger(__name__)

GREEK = {
    r"\alpha": "alpha", r"\beta": "beta", r"\gamma": "gamma", r"\delta": "delta",
    r"\epsilon": "epsilon", r"\theta": "theta", r"\lambda": "lambda", r"\mu": "mu",
    r"\pi": "pi", r"\rho": "rho", r"\sigma": "sigma", r"\phi": "phi", r"\omega": "omega",
}

def _extract_braced(s: str, start: int):
    """At s[start]=='{', return (inner, next_index_after_closing)."""
    depth = 0
    i = start
    while i < len(s):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return s[start+1:i], i + 1
        i += 1
    raise ValueError("Unbalanced braces in \\frac")

def replace_frac_braced(expr: str) -> str:
    """Replace \frac{...}{...} (incl. \dfrac, \tfrac), with spaces allowed around '/' or directly adjacent braces."""
    expr = expr.replace(r'\dfrac', r'\frac').replace(r'\tfrac', r'\frac')
    prev = None
    while prev != expr:
        prev = expr
        i, out = 0, []
        while i < len(expr):
            if expr.startswith(r'\frac', i):
                i += len(r'\frac')
                while i < len(expr) and expr[i].isspace():
                    i += 1
                # require a braced numerator
                if i >= len(expr) or expr[i] != '{':
                    out.append(r'\frac')
                    continue
                num, i = _extract_braced(expr, i)
                # skip spaces and accept either '/{den}' or simply '{den}'
                while i < len(expr) and expr[i].isspace():
                    i += 1
                # handle optional slash between braced groups
                has_slash = False
                if i < len(expr) and expr[i] == '/':
                    has_slash = True
                    i += 1
                    while i < len(expr) and expr[i].isspace():
                        i += 1
                # now expect a braced denominator
                if i < len(expr) and expr[i] == '{':
                    den, i = _extract_braced(expr, i)
                    out.append(f"(({num})/({den}))")
                else:
                    # fallback behaviour: if there was a slash but no brace, emit partial conversion
                    if has_slash:
                        out.append(r'\frac{' + num + '}/')
                    else:
                        out.append(r'\frac{' + num + '}')
            else:
                out.append(expr[i])
                i += 1
        expr = ''.join(out)
    return expr

def replace_frac_parenthesized(expr: str) -> str:
    """
    Fallback if braces were already converted to parentheses:
      \frac( A )/( B )  -> ((A)/(B))
    Be tolerant to spaces.
    """
    pattern = re.compile(r'\\frac\s*\(\s*([^()]*)\s*\)\s*/\s*\(\s*([^()]*)\s*\)')
    prev = None
    while prev != expr:
        prev = expr
        expr = pattern.sub(r'((\1)/(\2))', expr)
    return expr

FUNC_NAMES = ("max", "min", "log", "math")

def insert_implicit_multiplication(s: str) -> str:
    # Improved implicit multiplication:
    #  - keep original behavior for inserting '*' before '(' except for known functions
    #  - insert '*' between a digit and an identifier (2x -> 2*x)
    #  - insert '*' when a closing paren or digit is followed (possibly via spaces) by an identifier ( )x -> )*x or "2 x" -> "2*x")
    def _before_paren(m):
        before = m.group(1)
        ctx = s[max(0, m.start()-64):m.start()+1]
        w = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', ctx)
        if w and w.group(1) in FUNC_NAMES:
            return before + '('
        return before + '*('

    # keep previous rule for handling explicit '(' contexts
    s = re.sub(r'([0-9A-Za-z_)\]])\s*\(', _before_paren, s)
    # and after ')' if followed by identifier/number
    s = re.sub(r'\)\s*(?=[0-9A-Za-z_])', r')*', s)

    # insert '*' between a digit and an identifier (e.g., 2x -> 2*x)
    s = re.sub(r'(?<=\d)(?=[A-Za-z_])', '*', s)

    # insert '*' where a digit or closing paren is followed (with optional spaces) by an identifier (e.g., ") x" or "2 x")
    s = re.sub(r'([0-9\)])\s+(?=[A-Za-z_])', r'\1*', s)

    return s

def latex_to_python(s: str) -> str:
    s = s.strip().replace('$$', '').replace('$', '')
    if '=' in s:
        s = s.split('=')[-1]

    # 1) Normalize easy wrappers first
    s = re.sub(r'\\text\s*{([^}]*)}', r'\1', s)  # \text{X} -> X
    for token in [r'\left', r'\right', r'\,', r'\;', r'\:', r'\!']:
        s = s.replace(token, '')

    # 2) FRACTIONS (do this early and robustly)
    s = replace_frac_braced(s)
    s = replace_frac_parenthesized(s)  # fallback if braces were already '()'

    # 3) Greek and operators
    for k, v in GREEK.items():
        s = s.replace(k, v)
    s = s.replace(r'\cdot', '*').replace(r'\times', '*')

    # 4) max/min
    s = re.sub(r'\\max\s*{', 'max(', s)
    s = s.replace(r'\max', 'max')
    s = re.sub(r'\\min\s*{', 'min(', s)
    s = s.replace(r'\min', 'min')

    # 5) subscripts and expectations: a_{b}->a_b ; E[R_m]->E_R_m
    s = re.sub(r'([A-Za-z0-9]+)_\{([^}]+)\}', r'\1_\2', s)
    s = re.sub(r'([A-Za-z]+)\[([A-Za-z0-9_\\]+)\]',
               lambda m: f"{m.group(1)}_{m.group(2).replace('\\\\','')}", s)

    # 6) simple summation: \sum_{i=1}^{N}(body)
    sum_pat = re.compile(r"""\\sum_\{([A-Za-z])=([^}]+)\}\^\{([^}]+)\}\s*\(([^()]*)\)""")
    def _sum_repl(m):
        i, lo, hi, body = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"sum((lambda {i}: ({body}))({i}) for {i} in range(int({lo}), int({hi})+1))"
    prev = None
    while prev != s:
        prev, s = s, sum_pat.sub(_sum_repl, s)

    # 7) e^{x}, exponents, logs
    s = re.sub(r'e\s*\^\s*{([^}]+)}', r'(math.e)**(\1)', s)
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*{([^}]+)}', r'(\1)**(\2)', s)
    s = re.sub(r'([A-Za-z0-9_)\]]+)\s*\^\s*([A-Za-z0-9_]+)', r'(\1)**(\2)', s)
    s = re.sub(r'(?<![A-Za-z0-9_])log\s*\(', 'math.log(', s)

    # 8) Convert any leftover braces to parentheses (pure grouping)
    s = s.replace('{', '(').replace('}', ')')

    # 9) Implicit multiplication (guarded)
    s = insert_implicit_multiplication(s)

    # 10) Cleanup
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
    return Response(json.dumps(results), mimetype="application/json")
