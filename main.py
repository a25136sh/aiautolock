import asyncio
import os
import tempfile
import cv2
import numpy as np
import matplotlib.pyplot as plt
from contextlib import asynccontextmanager
from io import BytesIO
from fastapi import FastAPI, File, UploadFile, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
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
fft_image = tempfile.NamedTemporaryFile(delete=False)


@api_app.get("/")
async def root():
    return {"message": "Hello World"}


@api_app.post("/analyze")
async def analyze_sound(
    file: UploadFile = File(...)
):
    global fft_image

    file_content = await file.read()
    basename, _ = os.path.splitext(file.filename)
    target_frequency, threshold = [int(x) for x in basename.split("_")]
    audio = AudioSegment.from_file(BytesIO(file_content), codec="opus")

    # オーディオデータをnumpy配列に変換（raw_dataを取得）
    raw_data = np.array(audio.get_array_of_samples())
    if audio.channels == 2:
        raw_data = raw_data.reshape((-1, 2)).mean(axis=1)  # ステレオの場合、平均を取る
    raw_data = raw_data.astype(np.float32) / 32768.0  # 正規化（16bit）

    # フーリエ変換（FFT）を実行
    fft_data = np.fft.fft(raw_data)
    frequencies = np.fft.fftfreq(len(fft_data), 1 / audio.frame_rate)

    # 振幅スペクトル（正の周波数のみ）
    positive_freqs = frequencies[:len(frequencies)//2]
    positive_fft = np.abs(fft_data[:len(fft_data)//2])

    # 特定の周波数の振幅を検知
    # 特定の周波数に最も近い周波数ビンを探す
    freq_bin = np.argmin(np.abs(positive_freqs - target_frequency))
    target_amplitude = positive_fft[freq_bin]

    # 反応の閾値
    threshold = 30
    if target_amplitude > threshold:
        result = f"検知！ 振幅: {target_amplitude:.2f} (閾値: {threshold:.2f})"
        # ここに追加の反応（例: 音を再生、LED点灯など）を記述
    else:
        result = f"不検知！ 振幅: {target_amplitude:.2f} (閾値: {threshold:.2f})"

    # グラフ化
    plt.figure(figsize=(10, 6))
    plt.plot(positive_freqs, positive_fft)
    plt.xscale('log')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Amplitude')
    plt.grid(True)
    plt.xlim(0, audio.frame_rate / 2)  # ナイキスト周波数まで
    buf = BytesIO()
    plt.savefig(buf, format="png")
    with open(fft_image.name, "wb") as tmp:
        tmp.write(buf.getvalue())
    plt.clf()

    return result


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
    global fft_image
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    _, img_encoded = cv2.imencode('.png', img)
    img_byte_arr = img_encoded.tobytes()
    with open(fft_image.name, "wb") as tmp:
        tmp.write(img_byte_arr)
    return Response(content=img_byte_arr, media_type="image/png")


@api_app.get('/fft')
async def get_fft_image():
    global fft_image
    return FileResponse(fft_image.name)


app.mount("/api", api_app)
app.mount(
    "/",
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend"
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
