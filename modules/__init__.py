
# add directory of self to sys.path, so import is relative to self
import os, sys
modules_path = os.path.dirname(os.path.realpath(__file__))
if not modules_path in sys.path:
    sys.path.append(modules_path)