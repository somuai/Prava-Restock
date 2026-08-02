import { describe, expect, it } from "vitest";

import {
  providerBrandForName,
  reviewerHomeProductPresentation,
  reviewerShowcaseNotifications,
  reviewerShowcaseProducts,
  reviewerShowcaseSubscriptions,
  reviewerTeamSubscriptionPresentation,
} from "./App";
import type { TrackedItem } from "./api";

const reviewerCoffee: TrackedItem = {
  item_id: "b99dd2bb-5b8f-45dc-aaf7-3bb4f0d655a0",
  user_id: "00000000-0000-0000-0000-000000000099",
  name: "Blue Tokai Attikan Estate coffee, 500 g",
  track: "home",
  trigger_type: "predicted",
  category: "coffee",
  preferred_merchant: "zepto",
  merchant_sku_id: "zepto-arabica-coffee-500g",
  currency: "INR",
  status: "active",
};

const reviewerCopilot: TrackedItem = {
  ...reviewerCoffee,
  item_id: "b33f95b3-59c3-4d09-870b-a57f68bf1da0",
  name: "GitHub Copilot Business",
  track: "teams",
  trigger_type: "known_date",
  category: "saas",
  preferred_merchant: "github",
  merchant_sku_id: "teamtool-pro-monthly",
};

describe("reviewer product presentation", () => {
  it("uses the official provider marks for approval surfaces", () => {
    expect(providerBrandForName("Zepto")).toMatchObject({
      name: "Zepto",
      logo: "/app/assets/providers/zepto.svg",
    });
    expect(providerBrandForName("GitHub Copilot Business")).toMatchObject({
      name: "GitHub Copilot",
      logo: "/app/assets/providers/githubcopilot.svg",
    });
    expect(providerBrandForName("Vercel Pro")).toMatchObject({
      name: "Vercel",
      logo: "/app/assets/providers/vercel.svg",
    });
  });

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

  it("restores the full real-pack shelf only for the isolated reviewer fixture", () => {
    const shelf = reviewerShowcaseProducts([reviewerCoffee]);
    expect(shelf).toHaveLength(8);
    expect(shelf.find((product) => product.name === "Attikan Estate coffee")).toMatchObject({
      image: "/app/assets/product-coffee-attikan-cutout.png",
      itemId: reviewerCoffee.item_id,
    });
    expect(shelf.find((product) => product.name === "Amul Taaza milk")).toMatchObject({
      image: "/app/assets/product-amul-taaza.png",
    });
    expect(shelf.find((product) => product.name === "Amul Taaza milk")).not.toHaveProperty("itemId");
    const presentationCoffee = reviewerShowcaseProducts([]).find((product) => product.name === "Attikan Estate coffee");
    expect(presentationCoffee).toMatchObject({ id: "coffee" });
    expect(presentationCoffee).not.toHaveProperty("itemId");
  });

  it("restores the complete provider-award shelf while binding only Copilot to the fixture", () => {
    const awards = reviewerShowcaseSubscriptions([reviewerCopilot]);
    expect(awards).toHaveLength(6);
    expect(awards.find((subscription) => subscription.name === "GitHub Copilot Business")).toMatchObject({
      itemId: reviewerCopilot.item_id,
      logo: "/app/assets/providers/githubcopilot.svg",
    });
    expect(awards.find((subscription) => subscription.name === "Vercel Pro")).toMatchObject({
      logo: "/app/assets/providers/vercel.svg",
    });
    expect(awards.find((subscription) => subscription.name === "Vercel Pro")).not.toHaveProperty("itemId");
    const presentationCopilot = reviewerShowcaseSubscriptions([]).find((subscription) => subscription.name === "GitHub Copilot Business");
    expect(presentationCopilot).toMatchObject({ id: "copilot" });
    expect(presentationCopilot).not.toHaveProperty("itemId");
  });

  it("keeps safe approval previews visible when the review account has no pending workflows", () => {
    const reviewNotifications = reviewerShowcaseNotifications([]);
    expect(reviewNotifications).toHaveLength(2);
    expect(reviewNotifications.map((notification) => notification.actions)).toEqual([
      ["approve", "adjust", "skip"],
      ["renew_as_is", "switch_plan", "skip"],
    ]);
    expect(reviewNotifications.every((notification) => notification.status === "preview")).toBe(true);
  });
});
