<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Microphone } from '@element-plus/icons-vue'
import axios from 'axios'

const recording = ref(false)
const chunks = ref<Blob[]>([])
const recorder = ref<MediaRecorder>()
const UPLOAD_DELAY = 3000

const upload = () => {
  if (recording.value) {
    const file = new File(chunks.value, 'temp.mp3')

    const params = new FormData()
    params.append('file', file)

    axios
      .post(`/api/analyze`, params)
      .then((response) => {
        console.log(response)
        setTimeout(upload, UPLOAD_DELAY)
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
      })
  }
}
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
          chunks.value = []
        }
        setTimeout(upload, UPLOAD_DELAY)
      }
      recorder.value.start(1000)
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
  recording.value = false
  recorder.value?.stop()
}
</script>

<template>
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
