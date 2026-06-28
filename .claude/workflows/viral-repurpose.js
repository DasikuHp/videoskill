export const meta = {
  name: 'viral-repurpose',
  description: 'Download a source video, mine viral hooks across angles, and produce a short-form clip plan',
  whenToUse: 'When the user gives a video URL (or topic) and wants short-form repurposes with strong hooks.',
  phases: [
    { title: 'Source', detail: 'fetch video metadata / download with yt-dlp' },
    { title: 'Hooks', detail: 'fan out hook variants across proven angles' },
    { title: 'Judge', detail: 'score hooks and assemble a clip plan' },
  ],
}

// args: { url?: string, topic?: string, platform?: string, download?: boolean }
const url = args?.url || ''
const platform = args?.platform || 'tiktok'
const download = args?.download === true

// ── Phase 1: Source ────────────────────────────────────────────────
phase('Source')
const sourceCmd = url
  ? (download
      ? `python3 tools/video_downloader.py --url "${url}" --write-subs --output-dir tmp/video_jobs/repurpose/source`
      : `python3 tools/video_downloader.py --url "${url}" --info-only`)
  : null

const SOURCE_SCHEMA = {
  type: 'object',
  required: ['topic', 'summary'],
  properties: {
    topic: { type: 'string' },
    summary: { type: 'string' },
    local_path: { type: 'string' },
    duration_seconds: { type: 'number' },
  },
}

const source = await agent(
  sourceCmd
    ? `Run this command from the repo root and parse its RESULT JSON line:\n\n${sourceCmd}\n\n` +
      `Then return the video's topic (one phrase), a 2-3 sentence summary of what it's about, ` +
      `the local_path if it was downloaded, and duration_seconds if known. ` +
      `If the command fails, infer the topic from the URL slug and say so in the summary.`
    : `No URL was given. The user wants short-form repurposes about: "${args?.topic || 'the topic in context'}". ` +
      `Return that as topic plus a 2-3 sentence summary from your own knowledge.`,
  { phase: 'Source', schema: SOURCE_SCHEMA, label: 'source' },
)

const topic = source?.topic || args?.topic || 'the video topic'

// ── Phase 2: Hooks (fan out, one agent per angle) ──────────────────
phase('Hooks')
const ANGLES = ['curiosity-gap', 'contrarian', 'stat-shock', 'stakes', 'story-tease', 'question']
const HOOK_SCHEMA = {
  type: 'object',
  required: ['hooks'],
  properties: {
    hooks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['angle', 'spoken', 'on_screen_text', 'predicted_strength'],
        properties: {
          angle: { type: 'string' },
          spoken: { type: 'string' },
          on_screen_text: { type: 'string' },
          why_it_works: { type: 'string' },
          predicted_strength: { type: 'number' },
        },
      },
    },
  },
}

const hookBatches = await parallel(
  ANGLES.map((angle) => () =>
    agent(
      `Write 2 short-form video hooks for "${topic}" on ${platform}, using ONLY the "${angle}" angle. ` +
        `Context: ${source?.summary || ''}\n` +
        `Each hook is the first 1-2 spoken lines (~3s). Be concrete and honest — no fake claims. ` +
        `For each, give: angle, spoken line, matching on_screen_text, why_it_works, predicted_strength (1-10).`,
      { phase: 'Hooks', schema: HOOK_SCHEMA, label: `hook:${angle}` },
    ),
  ),
)

const allHooks = hookBatches.filter(Boolean).flatMap((b) => b.hooks || [])

// ── Phase 3: Judge + clip plan ─────────────────────────────────────
phase('Judge')
const PLAN_SCHEMA = {
  type: 'object',
  required: ['top_hooks', 'clip_plan'],
  properties: {
    top_hooks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['spoken', 'on_screen_text', 'score'],
        properties: {
          spoken: { type: 'string' },
          on_screen_text: { type: 'string' },
          score: { type: 'number' },
          rationale: { type: 'string' },
        },
      },
    },
    clip_plan: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'hook', 'beats'],
        properties: {
          title: { type: 'string' },
          hook: { type: 'string' },
          aspect_ratio: { type: 'string' },
          beats: { type: 'array', items: { type: 'string' } },
          source_section: { type: 'string' },
        },
      },
    },
  },
}

const plan = await agent(
  `You are a ruthless short-form editor. Here are ${allHooks.length} candidate hooks for "${topic}" (${platform}):\n` +
    JSON.stringify(allHooks, null, 2) +
    `\n\nPick the 5 strongest, de-duplicating near-identical ones, and score each 1-10 with a one-line rationale. ` +
    `Then produce a clip_plan of 3 short-form videos: each with a title, the chosen hook, aspect_ratio ` +
    `(${platform === 'youtube' ? '16:9' : '9:16'}), 3-5 beats (hook → payoff → proof → CTA), and a ` +
    `source_section (timecode range to pull from if a source video exists, else 'generate').`,
  { phase: 'Judge', schema: PLAN_SCHEMA, label: 'judge', effort: 'high' },
)

return {
  topic,
  source: { local_path: source?.local_path || null, duration_seconds: source?.duration_seconds || null },
  hooks_considered: allHooks.length,
  top_hooks: plan?.top_hooks || [],
  clip_plan: plan?.clip_plan || [],
}
