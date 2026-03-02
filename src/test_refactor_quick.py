"""Quick smoke test for path_analyzer refactor."""
import sys, re
sys.path.insert(0, 'src')
from code_parsing.feedback import run_l1_validation
from utils.study_utils import load_json_or_jsonl

def strip_md(text):
    m = re.search(r'```(?:javascript|js)?\s*\n(.*?)```', text, re.DOTALL)
    return m.group(1).strip() if m else text

data = load_json_or_jsonl('data/test/generations_all_models_base_only_intent_deepseek (1).jsonl')
ok = 0
err = 0
for row in data[:200]:
    code = strip_md(row.get('generated', ''))
    t = row.get('trigger_apis', [])
    a = row.get('action_apis', [])
    try:
        l1 = run_l1_validation(code, t, a, 'en')
        if l1.syntax_ok:
            ok += 1
        else:
            err += 1
    except Exception as e:
        err += 1
        print(f'EXCEPTION: {type(e).__name__}: {e}')
print(f'OK: {ok}, ERR: {err}, Total: {ok+err}')
