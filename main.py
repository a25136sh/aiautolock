from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
api_app = FastAPI()


@api_app.get("/")
async def root():
    return {"message": "Hello World"}


app.mount("/api", api_app)
app.mount(
    "/",
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend"
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
