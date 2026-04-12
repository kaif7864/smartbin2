from fastapi import FastAPI
from routes import user, scan, admin
from routes import iot  # sirf yeh add karo

app = FastAPI()

app.include_router(user.router, prefix="/user")
app.include_router(scan.router, prefix="/iot")
app.include_router(admin.router, prefix="/admin")
app.include_router(iot.router, prefix="")  # /live, /api/reading, /history

@app.get("/")
def home():
    return {"message": "Smart Dustbin API Running"}