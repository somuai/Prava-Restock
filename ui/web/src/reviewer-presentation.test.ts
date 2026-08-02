import { describe, expect, it } from "vitest";

import {
  reviewerHomeProductPresentation,
  reviewerTeamSubscriptionPresentation,
} from "./App";

describe("reviewer product presentation", () => {
  it("uses real pack imagery only for the four exact Home review fixtures", () => {
    expect(reviewerHomeProductPresentation("zepto-arabica-coffee-500g")).toMatchObject({
      name: "Attikan Estate coffee",
      image: "/app/assets/product-coffee-attikan-cutout.png",
    });
    expect(reviewerHomeProductPresentation("zepto-ro-filter-cartridge")).toMatchObject({
      name: "Aquaguard filter kit",
      image: "/app/assets/product-aquaguard-filter.png",
    });
    expect(reviewerHomeProductPresentation("swiggy-a4-paper-500")).toMatchObject({
      name: "JK A4 copier paper",
      image: "/app/assets/product-jk-paper-cutout.png",
    });
    expect(reviewerHomeProductPresentation("zepto-toothpaste-twin-pack")).toMatchObject({
      name: "Colgate Strong Teeth",
      image: "/app/assets/product-colgate-strong-teeth-cutout.png",
    });
  });

  it("uses the real GitHub Copilot provider treatment only for the Teams review fixture", () => {
    expect(reviewerTeamSubscriptionPresentation("teamtool-pro-monthly")).toMatchObject({
      name: "GitHub Copilot Business",
      logo: "/app/assets/providers/githubcopilot.svg",
    });
  });

  it("does not invent product imagery or a provider identity for unknown SKUs", () => {
    expect(reviewerHomeProductPresentation("user-private-sku")).toBeUndefined();
    expect(reviewerTeamSubscriptionPresentation("user-private-invoice")).toBeUndefined();
  });
});
