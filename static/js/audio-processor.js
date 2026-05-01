/**
 * AudioWorklet processor that captures mic input, resamples to 24 kHz,
 * converts Float32 → Int16 PCM, and posts chunks to the main thread.
 */
class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.targetRate = 24000;
    }

    process(inputs) {
        const input = inputs[0];
        if (!input || !input[0]) return true;

        const samples = input[0]; // mono channel
        const ratio = sampleRate / this.targetRate;

        // Resample: if device is 48 kHz and target is 24 kHz, take every other sample.
        // For other ratios, use linear interpolation.
        if (ratio === 2) {
            // Fast path: simple decimation by 2
            for (let i = 0; i < samples.length; i += 2) {
                this.buffer.push(samples[i]);
            }
        } else if (ratio === 1) {
            for (let i = 0; i < samples.length; i++) {
                this.buffer.push(samples[i]);
            }
        } else {
            // Linear interpolation for arbitrary ratios
            const srcLen = samples.length;
            const dstLen = Math.floor(srcLen / ratio);
            for (let i = 0; i < dstLen; i++) {
                const srcIdx = i * ratio;
                const lo = Math.floor(srcIdx);
                const hi = Math.min(lo + 1, srcLen - 1);
                const frac = srcIdx - lo;
                this.buffer.push(samples[lo] + (samples[hi] - samples[lo]) * frac);
            }
        }

        // Send chunks of ~1200 samples (~50ms at 24 kHz, as recommended by AssemblyAI docs)
        const chunkSize = 1200;
        while (this.buffer.length >= chunkSize) {
            const chunk = this.buffer.splice(0, chunkSize);
            const int16 = new Int16Array(chunk.length);
            for (let i = 0; i < chunk.length; i++) {
                const s = Math.max(-1, Math.min(1, chunk[i]));
                int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            this.port.postMessage(int16.buffer, [int16.buffer]);
        }

        return true;
    }
}

registerProcessor("pcm-processor", PCMProcessor);
