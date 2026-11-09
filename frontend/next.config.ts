import type { NextConfig } from "next";

// "standalone" bundles only what the server needs, for a small Docker image.
const nextConfig: NextConfig = { output: "standalone" };

export default nextConfig;
