"""Trusted fixture grader, executed ONLY in a disposable no-network container."""
import ast
import copy
import json
import sys


def validate(source, name):
    if not isinstance(source, str) or len(source) > 16000:
        raise ValueError('invalid source size')
    tree = ast.parse(source)
    if not tree.body or any(not isinstance(n, ast.FunctionDef) for n in tree.body):
        raise ValueError('only function definitions allowed')
    if name not in {n.name for n in tree.body}:
        raise ValueError('missing function')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise ValueError('forbidden construct')
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.args.defaults or node.args.kw_defaults):
            raise ValueError('decorators and defaults not allowed')
        if isinstance(node, ast.Name) and (node.id.startswith('_') or node.id in {'eval', 'exec', 'open', 'compile', 'globals', 'locals', 'getattr', 'setattr', 'delattr', 'input', 'breakpoint'}):
            raise ValueError('forbidden name')
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise ValueError('private attribute forbidden')
    return tree


def grade(payload):
    tree = validate(payload['code'], payload['function'])
    allowed = {'len': len, 'range': range, 'min': min, 'max': max, 'sum': sum,
               'int': int, 'str': str, 'float': float, 'bool': bool, 'list': list,
               'dict': dict, 'set': set, 'tuple': tuple, 'zip': zip, 'enumerate': enumerate,
               'sorted': sorted, 'all': all, 'any': any, 'abs': abs, 'isinstance': isinstance,
               'map': map, 'filter': filter, 'reversed': reversed}
    namespace = {'__builtins__': allowed}
    exec(compile(tree, '<candidate>', 'exec'), namespace)
    for args, expected in payload['tests']:
        original = copy.deepcopy(args)
        result = namespace[payload['function']](*args)
        if result != expected or type(result) is not type(expected) or args != original:
            return {'passed': False, 'reason': 'fixture_mismatch_or_input_mutation'}
    return {'passed': True, 'reason': 'all_fixtures_pass'}


if __name__ == '__main__':
    try:
        result = grade(json.loads(sys.stdin.read(64000)))
    except Exception as exc:
        result = {'passed': False, 'reason': type(exc).__name__}
    print(json.dumps(result))
