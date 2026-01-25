# Has all the security related functions like password hashing and verification
from fastapi import Request, HTTPException, status
from passlib.context import CryptContext
import os
from datetime import datetime, timedelta
from jose import JWTError, jwt

#Password context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

#JWT environment variables
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", 60))

# -------- Password hashing and verification --------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


#creates the jwt access token which is used for authentication
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    #the access token is a combination of the secret key, data, and the algorithm
    return jwt.encode( 
        to_encode,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


#gets the current user_id from the access token, the token doesnt contain the part of password
def get_current_user_id(request: Request) -> str:
    token = request.cookies.get("access_token")

    #if there is no token, no authentication
    if not token:
        return None

    try:
        #jwt decoding gives the user_id from the token
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = payload.get("sub")

        if user_id is None:
            return None

        return user_id

    except JWTError:
        return None
