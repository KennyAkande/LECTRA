from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
import shutil
import os
import uuid

from database import SessionLocal, User
from ai_engine import process_lecture

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = "videos"
if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ai_results_store = {}


class YTReq(BaseModel):
    url: str


def get_password_hash(password): return pwd_context.hash(password)


def verify_password(plain_password, hashed_password): return pwd_context.verify(plain_password, hashed_password)


def ai_background_worker(task_id: str, source: str, is_url: bool = False, is_text: bool = False):
    try:
        results = process_lecture(source, is_url=is_url, is_text=is_text)
        ai_results_store[task_id] = {"status": "completed", **results}
    except Exception as e:
        ai_results_store[task_id] = {"status": "failed", "error": str(e)}


@app.get("/")
def home(): return {"Status": "Librarian is at the desk!"}


@app.post("/signup")
def signup(email: str, password: str):
    db = SessionLocal()
    hashed = get_password_hash(password)
    new_user = User(email=email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.close()
    return {"message": "Student registered successfully!"}


@app.post("/login")
def login(email: str, password: str):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong email or password")
    return {"access_token": email, "token_type": "bearer"}


@app.post("/upload")
async def receive_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)

    # Detect PDF/Text for direct processing
    is_text = save_path.endswith(('.txt', '.pdf'))

    ai_results_store[task_id] = {"status": "processing"}
    background_tasks.add_task(ai_background_worker, task_id, save_path, False, is_text)

    return {"Message": f"Successfully saved {file.filename}!", "task_id": task_id}


@app.post("/upload-url")
async def process_youtube(req: YTReq, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    ai_results_store[task_id] = {"status": "processing"}
    background_tasks.add_task(ai_background_worker, task_id, req.url, True, False)
    return {"Message": "YouTube processing started.", "task_id": task_id}


@app.get("/results/{task_id}")
def get_results(task_id: str):
    return ai_results_store.get(task_id, {"status": "not_found"})