import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from astrakriti3d.web import app
app.run(host='127.0.0.1',port=8050,debug=False)
