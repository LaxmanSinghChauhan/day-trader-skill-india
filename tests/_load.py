"""Load a script from a skill folder (the folder names have hyphens), and run its main()."""

import contextlib
import importlib.util
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")


def load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("trader_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fix(*parts):
    return os.path.join(FIX, *parts)


def run(mod, argv, cwd=None):
    """main(argv) with stdout and stderr captured -> (exit code, stdout, stderr). cwd: run inside this folder."""
    out, err = io.StringIO(), io.StringIO()
    here = os.getcwd()
    if cwd:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mod.main([str(a) for a in argv])
    finally:
        os.chdir(here)
    return code, out.getvalue(), err.getvalue()
