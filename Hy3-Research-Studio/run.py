"""Convenience launcher.  Usage:  python run.py  (then open http://localhost:8731)"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8731"))
    print("=" * 60)
    print("  Hy3 Research Studio")
    print(f"  打开浏览器访问: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
