import asyncio
import cv2
import numpy as np
from contextlib import asynccontextmanager
from io import BytesIO
from fastapi import FastAPI, File, UploadFile, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydub import AudioSegment


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cap
    cap = cv2.VideoCapture(0)
    asyncio.create_task(fetch_camera_frame())
    yield
    cap.release()
    cv2.destroyAllWindows()


app = FastAPI(lifespan=lifespan)
api_app = FastAPI()

cap = None
latest_frame = None


@api_app.get("/")
async def root():
    return {"message": "Hello World"}


@api_app.post("/analyze")
async def analyze_sound(
    file: UploadFile = File(...)
):
    file_content = await file.read()
    audio = AudioSegment.from_file(BytesIO(file_content), codec="opus")
    return audio


async def fetch_camera_frame():
    global latest_frame
    while True:
        ret, frame = cap.read()
        if ret:
            _, encoded = cv2.imencode(".png", frame)
            latest_frame = encoded.tobytes()
        await asyncio.sleep(1)


async def gen_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + latest_frame +
                   b'\r\n')
        await asyncio.sleep(1)


@api_app.get('/camera')
async def get_camera_stream():
    return StreamingResponse(
        gen_frames(),
        media_type="multipart/x-mixed-replace;boundary=frame"
    )


@api_app.get('/blank')
async def get_blank_image():
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    _, img_encoded = cv2.imencode('.png', img)
    img_byte_arr = img_encoded.tobytes()
    return Response(content=img_byte_arr, media_type="image/png")


app.mount("/api", api_app)
app.mount(
    "/",
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend"
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
