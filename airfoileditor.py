"""

Start AirfoilEditor when installed as clone/copy of GitHub repository 

"""

import sys
# new directory layout
# from airfoileditor import app
from modules import app

if __name__ == '__main__':
    sys.exit(app.start())  