"""

Start AirfoilEditor when installed as clone/copy of GitHub repository 

"""

import sys

# dev or local mode: allow relative path import of airfoileditor package
import pathlib
ae_path = str(pathlib.Path(__file__).parent / "airfoileditor")
sys.path.insert (0, ae_path)            

from airfoileditor import app

if __name__ == '__main__':
    sys.exit(app.start())  