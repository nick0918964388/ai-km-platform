import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        carbon: {
          blue: {
            10: "#edf5ff",
            20: "#d0e2ff",
            30: "#a6c8ff",
            40: "#78a9ff",
            50: "#4589ff",
            60: "#0f62fe",
            70: "#0043ce",
            80: "#002d9c",
            90: "#001d6c",
            100: "#001141",
          },
          gray: {
            10: "#f4f4f4",
            20: "#e0e0e0",
            30: "#c6c6c6",
            40: "#a8a8a8",
            50: "#8d8d8d",
            60: "#6f6f6f",
            70: "#525252",
            80: "#393939",
            90: "#262626",
            100: "#161616",
          },
        },
      },
    },
  },
  plugins: [],
};
export default config;
