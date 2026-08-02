import { rand, pick } from "./rng.js";

const BED_DB = -5.0;
const VOICE_DB = -2.0;
const EVENT_DB = 0.0;
const SWELL_DB = -2.0;
const EVENT_KEEP = 0.125;
const EVENT_MAX_PER_SEC = 6;
const SEMITONES_AT_FAR = -12.0;
const SEMITONES_AT_NEAR = 4.0;
const CUTOFF_AT_FAR = 900.0;
const CUTOFF_AT_NEAR = 12000.0;
const VOICE_SECONDS = [5.0, 11.0];

function dbToGain(db) {
  return Math.pow(10, db / 20.0);
}

function depthTo(z, lo, hi) {
  const u = Math.max(0, Math.min(1, (z + 1.1) / 2.2));
  return lo + (hi - lo) * u;
}

export class ScoreEngine {
  constructor(bankUrl) {
    this.bankUrl = bankUrl;
    this.ctx = null;
    this.master = null;
    this.limiter = null;

    this.bank = null;
    this.audioBuffers = new Map();
    this.byKind = { bed: [], sustained: [], transient: [] };

    this.state = {
      voices: [],
      bedTimeout: null,
      lastEpoch: null,
      eventsThisSecond: 0,
      currentSecond: 0,
      previousFrameId: new Map(),
      previousCut: null,
      bedStopped: false
    };
  }

  initContext() {
    if (this.ctx) return;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();

    this.master = this.ctx.createGain();
    this.limiter = this.ctx.createDynamicsCompressor();
    this.limiter.threshold.value = -1.0;
    this.limiter.knee.value = 0.0;
    this.limiter.ratio.value = 20.0;
    this.limiter.attack.value = 0.005;
    this.limiter.release.value = 0.2;

    this.master.connect(this.limiter);
    this.limiter.connect(this.ctx.destination);

    // Safari unlock hack
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    gain.gain.value = 0.001;
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(0);
    osc.stop(this.ctx.currentTime + 0.1);
  }

  async load() {
    const res = await fetch(this.bankUrl);
    this.bank = await res.json();
    for (const g of this.bank.grains) {
      if (!this.byKind[g.kind]) this.byKind[g.kind] = [];
      this.byKind[g.kind].push(g);
    }
    for (const pool of Object.values(this.byKind)) {
      pool.sort((a, b) => a.id.localeCompare(b.id));
    }
  }

  async resume() {
    this.initContext();
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }
  }

  async getAudio(grainId) {
    if (this.audioBuffers.has(grainId)) return this.audioBuffers.get(grainId);

    const url = new URL(`../public/bank/${grainId}.mp3`, window.location.href);
    try {
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const audioBuffer = await new Promise((resolve, reject) => {
        this.ctx.decodeAudioData(arrayBuffer, resolve, reject);
      });
      this.audioBuffers.set(grainId, audioBuffer);
      return audioBuffer;
    } catch (e) {
      console.warn(`Failed to load grain ${grainId}`, e);
      return null;
    }
  }

  choose(kind, seed, ...words) {
    const pool = this.byKind[kind] || [];
    if (!pool.length) return null;

    let toward = null;
    if (words.length > 0 && Array.isArray(words[words.length - 1])) {
      toward = words.pop();
    }

    if (!toward) return pick(pool, seed, ...words);

    const [axis, target] = toward;
    const values = pool.map(g => g[axis]);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const stdDev = Math.sqrt(values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / values.length);
    const scale = stdDev || 1.0;

    const weights = values.map(v => Math.exp(-Math.pow((v - target) / scale, 2)));
    const total = weights.reduce((a, b) => a + b, 0);

    if (total <= 0) return pick(pool, seed, ...words);

    const r = rand(seed, ...words) * total;
    let sum = 0;
    for (let i = 0; i < weights.length; i++) {
      sum += weights[i];
      if (sum >= r) return pool[i];
    }
    return pool[pool.length - 1];
  }

  playBuffer(buffer, options = {}) {
    if (!buffer || !this.ctx) {
      if (!this.ctx) console.warn("playBuffer: ctx is null");
      return null;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;

    const gainNode = this.ctx.createGain();
    gainNode.gain.value = options.gain ?? 1.0;
    source.playbackRate.value = options.playbackRate || 1.0;

    source.connect(gainNode);
    gainNode.connect(this.ctx.destination);

    const now = this.ctx.currentTime;
    if (options.fade) {
      gainNode.gain.setValueAtTime(0, now);
      gainNode.gain.linearRampToValueAtTime(options.gain ?? 1.0, now + options.fade);
      if (options.duration) {
        gainNode.gain.setValueAtTime(options.gain ?? 1.0, now + options.duration - options.fade);
        gainNode.gain.linearRampToValueAtTime(0, now + options.duration);
      }
    } else if (options.duration) {
      source.stop(now + options.duration);
    }

    source.start(now);
    return { source, gain: gainNode };
  }

  async loopBed(seed, i = 0) {
    if (this.state.bedStopped) return;

    const g = pick(this.byKind.bed || [], seed, i, 601);
    if (!g) return;
    const buffer = await this.getAudio(g.id);
    if (!buffer) return;

    const pan = (rand(seed, i, 602) - 0.5) * 0.5;
    const duration = buffer.duration;

    this.playBuffer(buffer, {
      gain: dbToGain(BED_DB),
      pan,
      fadeIn: 1.2,
      fadeOut: 1.2
    });

    const overlap = 1.2;
    const nextWait = Math.max(duration - overlap, 1.0);
    this.state.bedTimeout = setTimeout(() => this.loopBed(seed, i + 1), nextWait * 1000);
  }

  startBed(seed) {
    this.state.bedStopped = false;
    this.loopBed(seed, 0);
  }

  stopBed() {
    this.state.bedStopped = true;
    if (this.state.bedTimeout) clearTimeout(this.state.bedTimeout);
  }

  async handleVoices(seed, t, cast, spread, dt, layoutInfo) {
    const nVoices = 8;

    const placed = cast.map(c => {
      const l = layoutInfo.get(c.id) || { z: 0, x: 0, opacity: 1, area: 0.1 };
      return { ...c, z: l.z, x: l.x, area: l.area, opacity: l.opacity };
    });
    placed.sort((a, b) => a.z - b.z);

    for (let slot = 0; slot < nVoices; slot++) {
      if (!this.state.voices[slot]) {
        this.state.voices[slot] = { take: 0, timer: 0 };
      }

      let v = this.state.voices[slot];
      v.timer -= dt;

      if (v.timer <= 0 && placed.length > 0) {
        const stride = placed.length / Math.min(nVoices, placed.length);
        const pIndex = Math.min(placed.length - 1, Math.floor(slot * stride));
        const p = placed[pIndex];

        const span = VOICE_SECONDS[0] + (VOICE_SECONDS[1] - VOICE_SECONDS[0]) * rand(seed, slot, v.take, 701);
        v.timer = span;
        v.take++;

        const semis = depthTo(p.z, SEMITONES_AT_FAR, SEMITONES_AT_NEAR);
        const cutoff = depthTo(p.z, CUTOFF_AT_FAR, CUTOFF_AT_NEAR);
        const targetCentroid = depthTo(p.z, 350.0, 1800.0);

        const g = this.choose("sustained", seed, slot, v.take, 702, ["centroid", targetCentroid]);
        if (g) {
          this.getAudio(g.id).then(buffer => {
            if (!buffer) return;
            const playbackRate = Math.pow(2, semis / 12.0);
            const width = 0.15 + 0.85 * Math.min(1.0, spread * 1.6);
            const gain = dbToGain(VOICE_DB) * (0.45 + 0.55 * p.opacity) * (0.6 + 0.4 * Math.min(1.0, p.area * 40));

            this.playBuffer(buffer, {
              gain,
              pan: p.x * width,
              playbackRate,
              cutoff,
              fadeIn: 0.35,
              fadeOut: 0.9,
              duration: span
            });
          });
        }
      }
    }
  }

  async handleEvents(seed, t, cast, spread, cut, layoutInfo) {
    const sec = Math.floor(t);
    if (this.state.currentSecond !== sec) {
      this.state.currentSecond = sec;
      this.state.eventsThisSecond = 0;
    }

    // cast structure: { id, rect, layers: [{frame, weight}] }
    // A frame change in the primary layer (layer[0]) is a recast
    const nowMap = new Map(cast.map(c => [c.id, c.layers?.[0]?.frame]));

    if (this.state.previousFrameId.size > 0 && cut === this.state.previousCut) {
      let index = Math.floor(t * 100);

      for (const [id, frame] of nowMap.entries()) {
        if (this.state.previousFrameId.has(id) && this.state.previousFrameId.get(id) !== frame) {
          index++;
          const l = layoutInfo.get(id);
          if (!l) continue;

          if (rand(seed, index, 801) >= EVENT_KEEP) continue;
          if (this.state.eventsThisSecond >= EVENT_MAX_PER_SEC) continue;
          this.state.eventsThisSecond++;

          const z = l.z;
          const targetCentroid = depthTo(z, 500.0, 2200.0);
          const g = this.choose("transient", seed, index, 802, ["centroid", targetCentroid]);
          if (g) {
            this.getAudio(g.id).then(buffer => {
              if (!buffer) return;
              const playbackRate = Math.pow(2, depthTo(z, -7.0, 3.0) / 12.0);
              const cutoff = depthTo(z, 1400.0, 14000.0);
              const width = 0.2 + 0.8 * Math.min(1.0, spread * 1.6);
              const gain = dbToGain(EVENT_DB) * (0.5 + 0.5 * Math.min(1.0, l.area * 60));

              this.playBuffer(buffer, {
                gain,
                pan: l.x * width,
                playbackRate,
                cutoff,
                fadeIn: 0.001,
                fadeOut: 0.03
              });
            });
          }
        }
      }
    }
    this.state.previousFrameId = nowMap;
    this.state.previousCut = cut;
  }

  async handleReseed(seed, t, epoch) {
    if (this.state.lastEpoch === null) {
      this.state.lastEpoch = epoch;
      this.state.reseedK = 0;
      return;
    }

    if (epoch !== this.state.lastEpoch) {
      this.state.lastEpoch = epoch;
      const k = this.state.reseedK++;

      const g = pick(this.byKind.bed || [], seed, k, 901);
      if (g) {
        this.getAudio(g.id).then(buffer => {
          if (!buffer) return;
          const playbackRate = Math.pow(2, -24.0 / 12.0);
          const seconds = Math.max(1.6, 6.0 * Math.pow(0.72, k));

          this.playBuffer(buffer, {
            gain: dbToGain(SWELL_DB),
            pan: 0.0,
            playbackRate,
            fadeIn: seconds * 0.1,
            fadeOut: 0.25,
            duration: seconds
          });
        });
      }
    }
  }

  update(r, seed, t, layoutInfo) {
    if (!this.ctx) return;
    // Do NOT gate on ctx.state === "running": after ctx.resume() the state
    // may stay "suspended" for several frames on Chrome/Firefox. Queued
    // source.start() calls execute once the context actually resumes, so
    // scheduling while still suspended is correct and necessary.

    const dt = this.state.lastT !== undefined ? Math.max(0, t - this.state.lastT) : 0;
    this.state.lastT = t;

    const { state, cast } = r;
    this.handleVoices(seed, t, cast, state.spread, dt, layoutInfo);
    this.handleEvents(seed, t, cast, state.spread, state.cut, layoutInfo);
    this.handleReseed(seed, t, state.epoch);
  }
}
