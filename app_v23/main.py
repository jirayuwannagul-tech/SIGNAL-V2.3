# app_v23/main.py
from __future__ import annotations

import os
from flask import Flask, jsonify
from app_v23.run_once import run_once

app = Flask(__name__)

@app.get("/")
def root():
    return jsonify({"ok": True, "service": "SIGNAL-V2.3"})

@app.get("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)