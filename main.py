from fastapi import FastAPI, HTTPException, Header
import os
import secrets

app = FastAPI()

API_SECRET = os.getenv("API_SECRET_KEY", "")

def verify_token(authorization: str = Header(default="")):
    if not API_SECRET:
         raise HTTPException(status_code=500, detail="API secret not configured")
    expected = f"Bearer {API_SECRET}"
    if not secrets.compare_digest(authorization, expected):
         raise HTTPException(status_code=401, detail="Invalid API Token")
    return True

@app.post("/translate_video")
async def translate_video(token_valid: bool = Depends(verify_token)):
    # Placeholder for video translation logic
    return {"status": "processing", "message": "Video translation started"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    
