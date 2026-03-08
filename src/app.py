from fastapi import FastAPI, Depends
from Routes import borrower_router, call_router
from Routes.public_router import router as public_router

#cors solution
from fastapi.middleware.cors import CORSMiddleware

#middleware for CORS
origins = [
    "http://localhost",
    "*", # Allow all origins (not recommended for production)
]


app = FastAPI(
    title="Collections Voice Bot",
    description="Voice Collections Bot for NBFC"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#adding routes
app.include_router(public_router)
app.include_router(borrower_router.router)
app.include_router(call_router.router)

