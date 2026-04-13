from fastapi import FastAPI
from routes import user, scan, admin
from routes import iot  # sirf yeh add karo
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI() 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # sabko allow
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(user.router, prefix="/user")
app.include_router(scan.router, prefix="/iot")
app.include_router(admin.router, prefix="/admin")
app.include_router(iot.router, prefix="")  # /live, /api/reading, /history

@app.get("/")
def home():
    return {"message": "Smart Dustbin API Running"}