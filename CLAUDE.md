# UQ Parkour Annotator

Local Flask app for labelling random 1 s video windows with FAABOS categories.
See `README.md` for usage and `PLAN.md` for the design and open decisions.

## Code conventions

- Concise, well-commented, highly modular code. One job per module.
- Standard library first. Third-party packages are limited to Flask,
  and imageio-ffmpeg.
- `app.py` holds routes only. Logic lives in the `parkour/` package.
- Storage is plain CSV. No database.
- The website is beautiful, minimal, professional and clean: plain HTML, one 
  stylesheet, one script, no front-end framework.

## Environment

- Python: `D:\anaconda3\python.exe` (not on PATH).
- Sample subject: `data/221125_SK_Test`.
- `private/` holds the user's older analysis code and data. Read-only reference.
