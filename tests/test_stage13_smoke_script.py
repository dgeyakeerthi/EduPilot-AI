from pathlib import Path

def test_deployment_checklist_and_smoke_script_exist():
    root=Path(__file__).resolve().parents[1]
    assert (root/'DEPLOYMENT_CHECKLIST.md').is_file()
    script=(root/'scripts'/'run_smoke_checks.py').read_text(encoding='utf-8')
    assert '/api/health' in script and '/api/ready' in script
