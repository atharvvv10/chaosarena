"""user-service: registration, login and JWT issuance."""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from pydantic import BaseModel

from common.observability import create_app

app = create_app("user-service")
SECRET = os.getenv("JWT_SECRET", "chaosarena-demo-secret-change-me")
USERS: dict[str, dict] = {}


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@app.post("/register")
def register(payload: RegisterRequest) -> dict:
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(400, "username and password required")
    if username in USERS:
        raise HTTPException(409, "user already exists")
    USERS[username] = {"password_hash": _hash(payload.password), "id": str(uuid.uuid4())}
    return {"user_id": USERS[username]["id"], "username": username}


@app.post("/login")
def login(payload: LoginRequest) -> dict:
    user = USERS.get(payload.username.strip())
    if not user or user["password_hash"] != _hash(payload.password):
        raise HTTPException(401, "invalid credentials")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": payload.username, "iat": now, "exp": now + timedelta(hours=24)},
        SECRET,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/users/{user_id}")
def get_user(user_id: str) -> dict:
    for name, data in USERS.items():
        if data["id"] == user_id:
            return {"user_id": user_id, "username": name}
    raise HTTPException(404, "user not found")
