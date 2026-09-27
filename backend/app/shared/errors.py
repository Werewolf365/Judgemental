from fastapi import HTTPException

def err(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})
