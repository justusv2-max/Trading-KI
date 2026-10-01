# GitHub upload
Upload the CONTENTS of this repository directory to the root of a GitHub repository (not the outer ZIP folder).

Keep these files/directories committed:
- `engine.py`, `server.py`, `bootstrap_current.py`
- `seed_state.pkl`
- `bootstrap_data/`
- `reference/`
- `tests/`
- `tradingview_cl_bar_sender.pine`
- Railway files (`railway.json`, `Procfile`, `requirements.txt`)
- all specs/checkpoints/hash manifests

Do NOT commit real secrets. Copy `.env.example` into Railway Variables and set real values there.

After upload, Railway can deploy the GitHub repository. Default intended mode is APEX until intentionally switched to EK.
