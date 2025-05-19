pip install fastapi uvicorn sqlalchemy psycopg2-binary passlib[bcrypt] python-jose[cryptography] pydantic
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Dict

# 🔧 Configuration
DATABASE_URL = "sqlite:///./sii_gouvernance.db"  # Pour test local. Changer pour PostgreSQL
SECRET_KEY = "votre_cle_secrete_super_secure"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ⚙️ Base de données
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# 🔐 Authentification
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_password_hash(password): return pwd_context.hash(password)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def create_token(data: dict):
    data.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

# 👤 Modèles SQLAlchemy
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True)
    hashed_password = Column(String)

class Diagnostic(Base):
    __tablename__ = "diagnostics"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    score = Column(Integer)
    recommendations = Column(Text)
    raw_data = Column(Text)
    submitted_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# 📦 Pydantic schemas
class UserCreate(BaseModel):
    email: str
    password: str

class DiagnosticInput(BaseModel):
    answers: Dict[str, int]  # { "q1": 2, "q2": 4, ... }

# 🔐 Auth utils
def get_user(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(lambda: SessionLocal())):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        user = get_user(db, email)
        if user is None:
            raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
        return user
    except JWTError:
        raise HTTPException(status_code=403, detail="Token invalide")

# 🚀 FastAPI instance
app = FastAPI(title="API Gouvernance SII")

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(lambda: SessionLocal())):
    if get_user(db, user.email):
        raise HTTPException(status_code=400, detail="Email déjà enregistré")
    hashed = get_password_hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    return {"msg": "Utilisateur créé avec succès."}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(lambda: SessionLocal())):
    user = get_user(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    token = create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/diagnostic")
def soumettre_diagnostic(data: DiagnosticInput, user: User = Depends(get_current_user), db: Session = Depends(lambda: SessionLocal())):
    score = sum(data.answers.values())
    recommandations = "Renforcez la gouvernance selon COBIT si score < 70" if score < 70 else "Niveau satisfaisant"
    diag = Diagnostic(user_id=user.id, score=score, recommendations=recommandations, raw_data=str(data.answers))
    db.add(diag)
    db.commit()
    return {
        "score": score,
        "recommandations": recommandations
    }

@app.get("/me")
def read_user(user: User = Depends(get_current_user)):
    return {"email": user.email, "message": "Bienvenue dans l’évaluation SII"}
