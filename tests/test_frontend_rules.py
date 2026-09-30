"""Run pure browser input rules without a browser or provider calls."""
import subprocess

def test_frontend_rules():
    result=subprocess.run(['node','--test','tests/frontend-rules.test.cjs'],capture_output=True,text=True)
    assert result.returncode==0, result.stdout+result.stderr
