export type Recording = { stop: () => Promise<Blob>; cancel: () => Promise<void> }

function encodeWav(samples: Float32Array, sourceRate: number): Blob {
  const targetRate = 16000
  const count = Math.ceil(samples.length * targetRate / sourceRate)
  const buffer = new ArrayBuffer(44 + count * 2)
  const view = new DataView(buffer)
  const write = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  write(0, 'RIFF'); view.setUint32(4, 36 + count * 2, true)
  write(8, 'WAVE'); write(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true)
  view.setUint16(22, 1, true); view.setUint32(24, targetRate, true)
  view.setUint32(28, targetRate * 2, true); view.setUint16(32, 2, true)
  view.setUint16(34, 16, true); write(36, 'data')
  view.setUint32(40, count * 2, true)
  for (let i = 0; i < count; i++) {
    const position = i * sourceRate / targetRate
    const left = Math.floor(position)
    const fraction = position - left
    const value = (samples[left] ?? 0) * (1 - fraction) + (samples[left + 1] ?? samples[left] ?? 0) * fraction
    view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, value)) * 32767, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export async function startRecording(): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone access is not available here.')
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } })
  const context = new AudioContext()
  try {
    await context.resume()
    const source = context.createMediaStreamSource(stream)
    const processor = context.createScriptProcessor(4096, 1, 1)
    const chunks: Float32Array[] = []
    processor.onaudioprocess = event => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
    source.connect(processor)
    processor.connect(context.destination)
    let ended = false
    const finish = async (save: boolean) => {
      if (ended) throw new Error('Recording already ended.')
      ended = true
      processor.disconnect(); source.disconnect()
      stream.getTracks().forEach(track => track.stop())
      await context.close()
      if (!save) return new Blob()
      const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
      const samples = new Float32Array(length)
      let offset = 0
      for (const chunk of chunks) { samples.set(chunk, offset); offset += chunk.length }
      return encodeWav(samples, context.sampleRate)
    }
    return { stop: () => finish(true), cancel: async () => { await finish(false) } }
  } catch (error) {
    stream.getTracks().forEach(track => track.stop())
    await context.close()
    throw error
  }
}
