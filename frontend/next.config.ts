import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* This app is operationally dynamic (live agent/financial data behind auth) --
     disable the experimental static/partial-prefetch caching features so dev
     output doesn't warn about client-rendered, auth-gated segments. */
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
