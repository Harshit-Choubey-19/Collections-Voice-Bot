from fastapi import FastAPI, Depends
from Routes.public_router import router as public_router


app = FastAPI(
    title="Collections Voice Bot",
    description="Voice Collections Bot for NBFC"
)


#adding routes
app.include_router(public_router)

