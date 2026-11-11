// The visitor's query embedding: BAAI/bge-small-en-v1.5 (384-d) through ONNX in Node, the same
// model the Librarian embeds chunks with (fastembed).  fastembed's recipe for this model is the
// [CLS] token's vector, L2-normalised, so that is what is used here (checked against fastembed
// 0.9.1: the vectors agree to about three decimals; mean pooling does not match).
// Loaded lazily on the first search, never at build time.  If the model cannot be loaded, search
// falls back to full text and says so.
export const EMBED_MODEL = "Xenova/bge-small-en-v1.5";
export const EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5";

type Extractor = (text: string, opts: { pooling: "cls" | "mean"; normalize: boolean }) => Promise<{ data: Float32Array }>;
const g = globalThis as unknown as { __arrEmbed?: Promise<Extractor> | null; __arrEmbedFailed?: { at: number; error: string } };

async function loadExtractor(): Promise<Extractor> {
  const mod = await import("@huggingface/transformers");
  const env = mod.env as { cacheDir?: string; allowLocalModels?: boolean };
  env.cacheDir = process.env.EMBED_CACHE_DIR || (process.env.VERCEL ? "/tmp/hf-cache" : `${process.cwd()}/.cache/hf`);
  env.allowLocalModels = false;
  const p = await mod.pipeline("feature-extraction", EMBED_MODEL, { dtype: "fp32" });
  return p as unknown as Extractor;
}

/** The query's embedding, or an error message.  A failure is remembered for five minutes. */
export async function embedQuery(text: string): Promise<{ ok: true; vector: number[] } | { ok: false; error: string }> {
  if (process.env.EMBED_DISABLED === "1") return { ok: false, error: "query embedding is turned off on this deployment" };
  const failed = g.__arrEmbedFailed;
  if (failed && Date.now() - failed.at < 5 * 60_000) return { ok: false, error: failed.error };
  try {
    if (!g.__arrEmbed) g.__arrEmbed = loadExtractor();
    const ext = await g.__arrEmbed;
    const out = await ext(text.slice(0, 2000), { pooling: "cls", normalize: true });
    return { ok: true, vector: Array.from(out.data) };
  } catch (e) {
    g.__arrEmbed = null;
    const error = `the embedding model could not be loaded (${(e as Error).message?.slice(0, 160) ?? "unknown error"})`;
    g.__arrEmbedFailed = { at: Date.now(), error };
    return { ok: false, error };
  }
}
