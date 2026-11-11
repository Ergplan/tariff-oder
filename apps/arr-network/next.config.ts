import type { NextConfig } from "next";

// The query embedder (lib/embed.ts) loads onnxruntime-node's native binary at run time, which
// the file tracer cannot see.  Ship the linux-x64 build (Vercel's runtime) with the two routes
// that embed queries; the other platforms' binaries stay out of the function.
const ONNX = "../../node_modules/.pnpm/onnxruntime-node@*/node_modules/onnxruntime-node/bin/napi-v3/linux/x64/**";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  serverExternalPackages: ["@huggingface/transformers", "onnxruntime-node", "sharp"],
  outputFileTracingIncludes: {
    "/search": [ONNX],
    "/api/v1/search": [ONNX],
  },
  outputFileTracingExcludes: {
    "*": [
      "../../node_modules/.pnpm/onnxruntime-node@*/node_modules/onnxruntime-node/bin/napi-v3/{darwin,win32}/**",
      "../../node_modules/.pnpm/onnxruntime-node@*/node_modules/onnxruntime-node/bin/napi-v3/linux/arm64/**",
    ],
  },
  poweredByHeader: false,
};

export default nextConfig;
