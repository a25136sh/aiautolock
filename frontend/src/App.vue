<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { Check, Microphone } from '@element-plus/icons-vue'
import axios from 'axios'
import moment from 'moment'

const recording = ref(false)
const chunks = ref<Blob[]>([])
const recorder = ref<MediaRecorder>()
const camera_url = ref("/api/blank")
const fft_url = ref("/api/blank")
const upload_timeout = ref()
const UPLOAD_DELAY = 3000
const target_frequency = ref(758)
const threshold = ref(300)
const detected = ref(false)

const micOn = () => {
  recording.value = true
  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((stream) => {
      if (!recorder.value) {
        recorder.value = new MediaRecorder(stream)
        recorder.value.ondataavailable = async (event) => {
          const blob = event.data
          chunks.value.push(blob)
        }
        recorder.value.onstop = async () => {
          if (recording.value) {
            const file = new File(chunks.value, `${target_frequency.value}_${threshold.value}.webm`)

            const params = new FormData()
            params.append('file', file)

            axios
              .post(`/api/analyze`, params)
              .then((response) => {
                console.log(response)
                fft_url.value = `/api/fft?${Math.random()}`
                if (!detected.value && response.data.detected) {
                  ElMessage({
                    message: 'インターホンが鳴りました！',
                    type: 'warning',
                  })
                  setTimeout(() => {
                    axios
                      .get(`/api/check`)
                      .then((response) => {
                        console.log(response)
                        if (response.data.result == "ng") {
                          ElNotification({
                            title: '訪問者の通知',
                            message: `顔が登録されていない訪問者がありました（${moment().calendar()}）`,
                            duration: 0,
                            type: 'info',
                          })
                        } else {
                          ElNotification({
                            title: '訪問者の通知',
                            message: `登録されたユーザーがオートロックを鳴らしました（${moment().calendar()}）`,
                            duration: 0,
                            type: 'info',
                          })
                        }
                      })
                      .catch((err) => {
                        ElMessage.error({
                          message: '顔認証に失敗',
                        })
                        console.log(err)
                      })
                  }, 5000)
                }
                detected.value = response.data.detected
              })
              .catch((err) => {
                ElMessage.error({
                  message: '音声ファイルのアップロードに失敗',
                })
                console.log(err)
                recording.value = false
              })
              .finally(() => {
                chunks.value = []
                if (recording.value) {
                  recorder.value?.start()
                  upload_timeout.value = setTimeout(() => {
                    recorder.value?.stop()
                  }, UPLOAD_DELAY)
                }
              })
          }
        }
      }
      camera_url.value = "/api/camera"
      recorder.value.start()
      upload_timeout.value = setTimeout(() => {
        recorder.value?.stop()
      }, UPLOAD_DELAY)
    })
    .catch((err) => {
      console.log(err)
      ElMessage.error({
        message: 'マイクを許可してください',
      })
      recording.value = false
    })
}
const micOff = () => {
  camera_url.value = "/api/blank"
  recording.value = false
  recorder.value?.stop()
  clearTimeout(upload_timeout.value)
}
const register = () => {
  axios
    .get(`/api/register`)
    .then((response) => {
      console.log(response)
      if (response.data == "ok") {
        ElMessage({
          message: '顔認識の登録に成功',
          type: 'success',
        })
      } else {
        ElMessage({
          message: '顔が認識できませんでした',
          type: 'warning',
        })
      }
    })
    .catch((err) => {
      ElMessage.error({
        message: '顔認識の登録に失敗',
      })
      console.log(err)
    })
}
</script>

<template>
  <div>
    <el-image :src="camera_url" style="width: 640px; height: 480px; margin-bottom: 1em" />
  </div>
  <div style="display: flex; justify-content: center;">
    <div>
      <el-button circle style="width: 10em; height: 10em">
        <el-icon size="100" v-if="!recording">
          <Microphone @click="micOn" />
        </el-icon>
        <el-icon size="100" v-else>
          <Check @click="micOff" />
        </el-icon>
      </el-button>
      <div class="recording" v-if="recording">●REC</div>
    </div>
    <div>
      <el-image :src="fft_url" style="width: 235px; height: 141px; margin-left: 3em;" />
    </div>
    <div style="margin-left: 2em;">
      <div>検知する周波数</div>
      <el-input-number v-model="target_frequency" :min="20" :max="20000" />
      <div>閾値</div>
      <el-input-number v-model="threshold" :min="1" :max="2000" />
      <div style="margin-top: 1em;"><el-button @click="register">顔登録</el-button></div>
    </div>
  </div>
</template>

<style lang="css" scoped>
.recording {
  color: red;
  animation: blink 1s ease-in-out infinite alternate;
}

@keyframes blink {
  0% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
}
</style>
