import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The query embedder loads a native ONNX runtime; keep it out of the bundle.
  serverExternalPackages: ["@huggingface/transformers", "onnxruntime-node", "sharp"],
  poweredByHeader: false,
};

export default nextConfig;
