"""Start agentctl without trusting the current directory.

    python3 -I tools/run.py <command> ...

`python3 -m agentctl` puts the current directory first on the import path, so a
file named agentctl.py (or json.py, or tomllib.py) in whatever directory you
happen to be in would run instead. That directory is sometimes a pull request's
checkout. With -I, Python ignores the current directory, PYTHONPATH and the
user's site-packages; this file then adds exactly one path: its own.
"""

import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
sys.argv[0] = "agentctl"
runpy.run_module("agentctl", run_name="__main__", alter_sys=True)
