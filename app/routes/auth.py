import uuid
import random
import string

import bcrypt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr

from app.dependencies import create_access_token, get_current_user, theme_from_request
from app.models.user import LoginRequest, SignupRequest
from app.services.db_client import execute, execute_one

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/app", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    return templates.TemplateResponse(request=request, name="login.html", context={"theme": theme})


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = execute_one("SELECT id, email, password_hash, email_verified FROM users WHERE email = %s", (email,))
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return HTMLResponse(
            """<div id="error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Invalid email or password</div>""",
            status_code=200,
        )
    if not user.get("email_verified"):
        return HTMLResponse(
            """<div id="error" class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Email not verified. Please check your verification code.</div>""",
            status_code=200,
        )
    token = create_access_token(str(user["id"]))
    response = HTMLResponse(content="")
    response.headers["HX-Redirect"] = "/app"
    response.set_cookie(key="token", value=token, httponly=True, max_age=60 * 60 * 24 * 7)
    return response


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/app", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    return templates.TemplateResponse(request=request, name="signup.html", context={"theme": theme})



@router.post("/signup")
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    existing = execute_one("SELECT id, email_verified FROM users WHERE email = %s", (email,))
    if existing:
        if existing.get("email_verified"):
            return HTMLResponse(
                """<div id="error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Email already registered</div>""",
                status_code=200,
            )
        # Re-use unverified account — generate new code
        user_id = existing["id"]
        execute("UPDATE users SET password_hash = %s WHERE id = %s", (bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(), user_id))
    else:
        if len(password) < 6:
            return HTMLResponse(
                """<div id="error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Password must be at least 6 characters</div>""",
                status_code=200,
            )
        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
            (user_id, email, password_hash),
        )

    # Generate 6-digit verification code
    code = ''.join(random.choices(string.digits, k=6))
    execute(
        "UPDATE users SET verification_code = %s WHERE id = %s",
        (code, user_id)
    )

    return HTMLResponse(f"""
    <div id="signup-form-area" class="auth-animate space-y-5">
        <div class="p-5 rounded-2xl bg-emerald-500/5 border border-emerald-500/10 text-center">
            <div class="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
            </div>
            <p class="text-sm font-semibold text-emerald-400 mb-1">Verification code sent!</p>
            <p class="text-xs text-fg-dim mb-3">In production, this would be emailed to <strong class="text-fg">{email}</strong>. For development:</p>
            <div class="inline-block px-6 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <span class="text-2xl font-black tracking-[0.3em] text-emerald-400">{code}</span>
            </div>
        </div>
        <form hx-post="/auth/verify" hx-target="#signup-form-area" hx-swap="outerHTML">
            <input type="hidden" name="user_id" value="{user_id}">
            <div>
                <label class="block text-xs text-fg-dim font-medium mb-2">Enter verification code</label>
                <input type="text" name="code" required maxlength="6" placeholder="000000"
                    class="input-focus-ring w-full bg-bg-input border border-border rounded-xl px-4 py-3 text-sm text-fg placeholder-fg-dim focus:outline-none focus:border-fg-muted/50 transition-all duration-200 text-center text-lg tracking-[0.2em] font-mono">
            </div>
            <div id="verify-error" class="mt-3"></div>
            <button type="submit"
                class="w-full bg-fg text-bg rounded-xl py-3 text-sm font-semibold hover:opacity-90 transition-all duration-200 active:scale-[0.98] mt-4">
                Verify Email
            </button>
        </form>
        <p class="text-center text-xs text-fg-dim">
            Didn't get the code? <button onclick="location.reload()" class="text-fg font-medium hover:opacity-80 transition-opacity">Sign up again</button>
        </p>
    </div>
    """)


@router.post("/verify")
async def verify_email(request: Request, user_id: str = Form(...), code: str = Form(...)):
    user = execute_one(
        "SELECT id, email, verification_code FROM users WHERE id = %s",
        (user_id,)
    )
    if not user or user.get("verification_code") != code.strip():
        return HTMLResponse(
            """<div id="verify-error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Invalid verification code. Please try again.</div>""",
            status_code=200,
        )

    # Mark as verified
    execute(
        "UPDATE users SET email_verified = TRUE, verification_code = NULL WHERE id = %s",
        (user_id,)
    )

    token = create_access_token(user_id)
    response = HTMLResponse(content="")
    response.headers["HX-Redirect"] = "/app"
    response.set_cookie(key="token", value=token, httponly=True, max_age=60 * 60 * 24 * 7)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("token")
    return response
