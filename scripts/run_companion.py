"""Run the protected Astrakriti preparation companion service."""

import os

from astrakriti3d.companion_api import create_companion_app


app = create_companion_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("ASTRAKRITI_COMPANION_HOST", "127.0.0.1"),
        port=int(os.environ.get("ASTRAKRITI_COMPANION_PORT", "5001")),
    )
