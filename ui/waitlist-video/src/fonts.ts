import {loadFont} from "@remotion/fonts";
import {staticFile} from "remotion";

void loadFont({
  family: "Restock Inter",
  url: staticFile("fonts/inter-latin-wght-normal.woff2"),
  weight: "100 900",
  display: "block",
});
void loadFont({
  family: "Restock Display",
  url: staticFile("fonts/radio-canada-big-latin-wght-normal.woff2"),
  weight: "300 700",
  display: "block",
});
void loadFont({
  family: "Restock Pixel",
  url: staticFile("fonts/geist-pixel-square.woff2"),
  weight: "400",
  display: "block",
});

export const bodyFont = "Restock Inter, Arial, sans-serif";
export const displayFont = "Restock Display, Arial, sans-serif";
export const labelFont = "Restock Pixel, monospace";
