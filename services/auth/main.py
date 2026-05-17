import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Annotated, Optional
import urllib.parse

from database import get_db
from models import User
from schemas import UserCreate, UserResponse, Token
from security import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    decode_access_token
)
from config import settings

from contextlib import asynccontextmanager

import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from database import engine
    from models import User
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all)
    yield

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Selp Auth Service", lifespan=lifespan)

# Note: In production, ensure allow_origins is specific and allow_credentials is True
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.BASE_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# --- Google OAuth ---
@app.get("/google/login")
async def google_login():
    logger.info(f"OAUTH: GOOGLE_CLIENT_ID={settings.GOOGLE_CLIENT_ID[:10]}...")
    logger.info(f"OAUTH: Redirect URI={settings.google_redirect_uri}")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"url": url}

@app.get("/google/callback")
async def google_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        token_res = await client.post(token_url, data=data)
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch token from Google")
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        user_info_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_info_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Google")
        
        user_info = user_info_res.json()
        email = user_info.get("email")
        name = user_info.get("name")
        sub = user_info.get("sub")

    # Check or Create User
    result = await db.execute(select(User).where(User.username == email))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            username=email,
            nickname=name,
            provider="google",
            provider_id=sub,
            is_admin=False
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # Generate JWT
    jwt_token = create_access_token(data={"sub": user.username})
    
    # Create RedirectResponse and set cookie
    redirect_res = RedirectResponse(url=f"{settings.BASE_URL}/home")
    redirect_res.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=1800,
        samesite="lax",
        secure=False,
    )
    return redirect_res

# --- Naver OAuth ---
@app.get("/naver/login")
async def naver_login():
    logger.info(f"OAUTH: NAVER_CLIENT_ID={settings.NAVER_CLIENT_ID[:10]}...")
    logger.info(f"OAUTH: Redirect URI={settings.naver_redirect_uri}")
    params = {
        "client_id": settings.NAVER_CLIENT_ID,
        "redirect_uri": settings.naver_redirect_uri,
        "response_type": "code",
        "state": "random_state_string" # Should be dynamic in prod
    }
    url = f"https://nid.naver.com/oauth2.0/authorize?{urllib.parse.urlencode(params)}"
    return {"url": url}

@app.get("/naver/callback")
async def naver_callback(code: str, state: str, response: Response, db: AsyncSession = Depends(get_db)):
    token_url = "https://nid.naver.com/oauth2.0/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": settings.NAVER_CLIENT_ID,
        "client_secret": settings.NAVER_CLIENT_SECRET,
        "code": code,
        "state": state
    }
    async with httpx.AsyncClient() as client:
        token_res = await client.get(token_url, params=params)
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch token from Naver")
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        user_info_res = await client.get(
            "https://openapi.naver.com/v1/nid/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_info_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Naver")
        
        res_data = user_info_res.json()
        profile = res_data.get("response")
        email = profile.get("email")
        name = profile.get("nickname") or profile.get("name")
        id_ = profile.get("id")

    # Check or Create User
    result = await db.execute(select(User).where(User.username == email))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            username=email,
            nickname=name,
            provider="naver",
            provider_id=id_,
            is_admin=False
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # Generate JWT
    jwt_token = create_access_token(data={"sub": user.username})
    
    # Create RedirectResponse and set cookie
    redirect_res = RedirectResponse(url=f"{settings.BASE_URL}/home")
    redirect_res.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=1800,
        samesite="lax",
        secure=False,
    )
    return redirect_res

@app.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    is_admin = False
    if user_in.is_admin:
        if user_in.admin_secret_key != settings.ADMIN_SECRET_KEY:
            raise HTTPException(status_code=403, detail="Invalid admin secret key")
        is_admin = True
    
    hashed_password = None
    if user_in.password:
        hashed_password = get_password_hash(user_in.password)
    
    new_user = User(
        username=user_in.username,
        nickname=user_in.nickname,
        hashed_password=hashed_password,
        is_admin=is_admin,
        provider=user_in.provider,
        provider_id=user_in.provider_id
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@app.post("/token", response_model=Token)
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    
    # Set HttpOnly cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=1800,  # 30 minutes
        expires=1800,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}

async def get_current_user(
    request: Request,
    token: Annotated[Optional[str], Depends(oauth2_scheme)], 
    db: AsyncSession = Depends(get_db)
):
    # Try to get token from cookie first, then fall back to Authorization header
    token = request.cookies.get("access_token") or token
    
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

@app.get("/me", response_model=UserResponse)
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
