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
face_detector = cv2.FaceDetectorYN_create(
    "face_detection_yunet_2023mar.onnx", "", (0, 0)
)
face_recognizer = cv2.FaceRecognizerSF_create("face_recognizer_fast.onnx", "")
user_file = "user.npy"


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
        detected = True
    else:
        result = f"不検知！ 振幅: {target_amplitude:.2f} (閾値: {threshold:.2f})"
        detected = False

    n_peaks = 1  # 抽出するピーク数
    # インデックスを振幅の降順でソート
    peak_indices = np.argsort(positive_fft)[::-1][:n_peaks]
    peak_frequencies = positive_freqs[peak_indices]
    peak_amplitudes = positive_fft[peak_indices]

    result += "\n振幅がトップの周波数:"
    for _, (freq, amp) in enumerate(zip(peak_frequencies, peak_amplitudes), 1):
        result += f"\n周波数: {freq:.2f} Hz, 振幅: {amp:.2f}"

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

    return {
        "detected": detected,
        "message": result
    }


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


@api_app.get("/register")
async def register_face():
    global latest_frame
    crop_ndarray = np.frombuffer(latest_frame, np.uint8)
    decoded = cv2.imdecode(crop_ndarray, cv2.IMREAD_UNCHANGED)
    print(decoded.shape)
    height, width, _ = decoded.shape
    face_detector.setInputSize((width, height))
    _, faces = face_detector.detect(decoded)
    faces = faces if faces is not None else []
    if len(faces) > 0:
        # 顔の切り抜き
        aligned_face = face_recognizer.alignCrop(decoded, faces[0])
        # 特徴量の抽出
        face_feature = face_recognizer.feature(aligned_face)
        # 特徴量ベクトルを保存
        np.save(user_file, face_feature)
        return "ok"
    else:
        return "ng"


@api_app.get("/check")
async def check_face():
    global latest_frame
    if os.path.exists(user_file):
        user_face = np.load(user_file)
        crop_ndarray = np.frombuffer(latest_frame, np.uint8)
        decoded = cv2.imdecode(crop_ndarray, cv2.IMREAD_UNCHANGED)
        print(decoded.shape)
        height, width, _ = decoded.shape
        face_detector.setInputSize((width, height))
        _, faces = face_detector.detect(decoded)
        faces = faces if faces is not None else []
        if len(faces) > 0:
            # 顔の切り抜き
            aligned_face = face_recognizer.alignCrop(decoded, faces[0])
            # 特徴量の抽出
            face_feature = face_recognizer.feature(aligned_face)
            score = face_recognizer.match(
                user_face, face_feature, cv2.FaceRecognizerSF_FR_COSINE
            )
            if score > 0.2:
                return {
                    "result": "ok",
                    "score": score
                }
            else:
                return {
                    "result": "ng",
                    "score": score
                }
        else:
            return {
                "result": "ng",
                "score": 0
            }
    else:
        return {
            "result": "ng",
            "score": 0
        }


app.mount("/api", api_app)
app.mount(
    "/",
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend"
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
